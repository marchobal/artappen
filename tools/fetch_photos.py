"""Hämtar ett foto per art från Wikimedia Commons, med fotograf och licens.

Kedjan är densamma som i appens informationskort:
  vetenskapligt namn → GBIF-nyckel → Wikidata (P846) → bild (P18) → Commons (foto + licens)

Användning: python3 -I tools/fetch_photos.py <utmapp> "Svenskt namn=Vetenskapligt namn" ...
Skriver <utmapp>/<slug>.jpg och <utmapp>/meta.json.
"""
import json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request

UA = {'User-Agent': 'artappen-tools/1.0 (privat artapp; skript för att hämta artfoton)'}

def get(url, raw=False):
    # Wikimedia begränsar hur ofta man får fråga: vänta och försök igen vid 429
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            return data if raw else json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5: raise
            wait = int(e.headers.get('Retry-After') or 0) or 2 ** (attempt + 1)
            print(f'  (för många anrop – väntar {wait} s)', flush=True)
            time.sleep(wait)

def slug(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')

def plain(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html or '')).strip()

out = sys.argv[1]
meta = []
for arg in sys.argv[2:]:
    swe, sci = arg.split('=', 1)
    name = slug(swe)
    # Redan klar? (uppgifterna sparas per art, så ett avbrott inte gör att allt måste hämtas om)
    if os.path.exists(f'{out}/{name}.json') and os.path.exists(f'{out}/{name}.jpg'):
        meta.append(json.load(open(f'{out}/{name}.json'))); print(f'{swe:10} (redan hämtad)'); continue
    key = get('https://api.gbif.org/v1/species/match?' + urllib.parse.urlencode({'name': sci}))['usageKey']
    q = get('https://www.wikidata.org/w/api.php?' + urllib.parse.urlencode(
        {'action': 'query', 'list': 'search', 'srsearch': f'haswbstatement:P846={key}', 'srlimit': 1, 'format': 'json'}))
    qid = q['query']['search'][0]['title']
    ent = get('https://www.wikidata.org/w/api.php?' + urllib.parse.urlencode(
        {'action': 'wbgetentities', 'ids': qid, 'props': 'claims', 'format': 'json'}))['entities'][qid]
    image = ent['claims']['P18'][0]['mainsnak']['datavalue']['value']
    ii = get('https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(
        {'action': 'query', 'titles': f'File:{image}', 'prop': 'imageinfo', 'iiprop': 'url|extmetadata', 'iiurlwidth': 1024,
         'iiextmetadatafilter': 'Artist|LicenseShortName|LicenseUrl', 'format': 'json'}))
    info = list(ii['query']['pages'].values())[0]['imageinfo'][0]
    em = info.get('extmetadata', {})
    img = get(info['thumburl'], raw=True)  # hämta först, skriv sedan (ingen tom fil om det misslyckas)
    with open(f'{out}/{name}.jpg', 'wb') as f:
        f.write(img)
    meta.append({'slug': name, 'swe': swe, 'sci': sci, 'gbif': key, 'qid': qid, 'file': image,
                 'page': info['descriptionurl'], 'artist': plain(em.get('Artist', {}).get('value')),
                 'license': em.get('LicenseShortName', {}).get('value', ''), 'licenseUrl': em.get('LicenseUrl', {}).get('value', '')})
    json.dump(meta[-1], open(f'{out}/{name}.json', 'w'), ensure_ascii=False, indent=1)
    print(f'{swe:10} {key:>8} {qid:>9}  {meta[-1]["license"]:14} {meta[-1]["artist"][:40]}', flush=True)
    time.sleep(4)  # snällt tempo mot Wikimedia
with open(f'{out}/meta.json', 'w') as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)
