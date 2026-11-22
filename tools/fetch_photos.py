"""Hämtar ett foto per art från Wikimedia Commons, med fotograf och licens.

Kedjan är densamma som i appens informationskort:
  vetenskapligt namn → GBIF-nyckel → Wikidata (P846) → bild (P18) → Commons (foto + licens)

Snällt mot Wikimedia (https://meta.wikimedia.org/wiki/User-Agent_policy):
  - presenterar sig med namn och kontakt (länk till repot) i User-Agent
  - en enda SPARQL-fråga mot Wikidata för alla arter i stället för flera anrop per art
  - fotograf och licens från Commons för 50 bilder per anrop
  - bildfilerna hämtas en i taget med paus, och redan hämtade arter hoppas över
  - väntar enligt Retry-After om servern ber om det (429)

Användning: python3 -I tools/fetch_photos.py <utmapp> "Svenskt namn=Vetenskapligt namn" ...
Skriver <utmapp>/<slug>.jpg och <utmapp>/<slug>.json (en per art), samt <utmapp>/meta.json.
"""
import json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request

UA = {'User-Agent': 'ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib'}
PAUSE_IMAGE = 1.5   # sekunder mellan bildfiler
PAUSE_API = 1.0     # sekunder mellan API-anrop

def get(url, raw=False, data=None):
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers=UA, data=data)
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 5: raise
            wait = int(e.headers.get('Retry-After') or 0) or 5 * 2 ** attempt
            print(f'  (servern ber oss vänta {wait} s)', flush=True)
            time.sleep(wait)

def slug(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')

def plain(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', html or '')).strip()

def norm_file(name):
    """Commons-filnamn i samma form som API:t svarar med (mellanslag, stor första bokstav)."""
    name = urllib.parse.unquote(name).replace('_', ' ').strip()
    return name[:1].upper() + name[1:]

out = sys.argv[1]
species = [dict(zip(('swe', 'sci'), a.split('=', 1))) for a in sys.argv[2:]]
todo = [s for s in species if not (os.path.exists(f"{out}/{slug(s['swe'])}.json") and os.path.exists(f"{out}/{slug(s['swe'])}.jpg"))]
print(f'{len(species)} arter, {len(species) - len(todo)} redan hämtade, {len(todo)} kvar', flush=True)

# 1) GBIF-nycklar (GBIF:s eget API, inte Wikimedia)
for s in todo:
    s['gbif'] = get('https://api.gbif.org/v1/species/match?' + urllib.parse.urlencode({'name': s['sci']}))['usageKey']

# 2) En SPARQL-fråga mot Wikidata för alla arter: objekt, bild, Dyntaxa-id, svensk Wikipedia-artikel
if todo:
    values = ' '.join(f'"{s["gbif"]}"' for s in todo)
    query = f'''SELECT ?gbif ?item ?image ?dyntaxa ?article WHERE {{
      VALUES ?gbif {{ {values} }}
      ?item wdt:P846 ?gbif .
      OPTIONAL {{ ?item wdt:P18 ?image }}
      OPTIONAL {{ ?item wdt:P1939 ?dyntaxa }}
      OPTIONAL {{ ?article schema:about ?item ; schema:isPartOf <https://sv.wikipedia.org/> }}
    }}'''
    res = get('https://query.wikidata.org/sparql', data=urllib.parse.urlencode({'query': query, 'format': 'json'}).encode())
    found = {}
    for b in res['results']['bindings']:
        g = b['gbif']['value']
        f = found.setdefault(g, {'qid': b['item']['value'].rsplit('/', 1)[-1]})
        if 'image' in b and 'file' not in f: f['file'] = norm_file(b['image']['value'].rsplit('/', 1)[-1])
        if 'dyntaxa' in b: f['dyntaxa'] = b['dyntaxa']['value']
        if 'article' in b: f['wiki'] = b['article']['value']
    for s in todo: s.update(found.get(str(s['gbif']), {}))
    time.sleep(PAUSE_API)

# 3) Fotograf, licens och bildadress från Commons, 50 bilder per anrop
withfile = [s for s in todo if s.get('file')]
for i in range(0, len(withfile), 50):
    batch = withfile[i:i + 50]
    r = get('https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode({
        'action': 'query', 'titles': '|'.join('File:' + s['file'] for s in batch), 'prop': 'imageinfo',
        'iiprop': 'url|extmetadata', 'iiurlwidth': 1024, 'iiextmetadatafilter': 'Artist|LicenseShortName|LicenseUrl',
        'format': 'json'}))
    pages = {p['title'][5:]: p for p in r['query']['pages'].values() if 'imageinfo' in p}
    for s in batch:
        p = pages.get(s['file'])
        if not p: continue
        ii = p['imageinfo'][0]; em = ii.get('extmetadata', {})
        s.update({'thumb': ii['thumburl'], 'page': ii['descriptionurl'], 'artist': plain(em.get('Artist', {}).get('value')),
                  'license': em.get('LicenseShortName', {}).get('value', ''), 'licenseUrl': em.get('LicenseUrl', {}).get('value', '')})
    time.sleep(PAUSE_API)

# 4) Bildfilerna, en i taget. Uppgifterna sparas per art direkt, så ett avbrott går att återuppta.
for s in todo:
    name = slug(s['swe'])
    if not s.get('thumb'):
        print(f"{s['swe']:12} – ingen bild hittades på Wikidata/Commons", flush=True); continue
    img = get(s['thumb'], raw=True)  # hämta först, skriv sedan (ingen tom fil om det misslyckas)
    with open(f'{out}/{name}.jpg', 'wb') as f: f.write(img)
    meta = {'slug': name, 'swe': s['swe'], 'sci': s['sci'], 'gbif': s['gbif'], 'qid': s['qid'], 'file': s['file'],
            'page': s['page'], 'artist': s['artist'], 'license': s['license'], 'licenseUrl': s['licenseUrl'],
            'dyntaxa': s.get('dyntaxa'), 'wiki': s.get('wiki')}
    json.dump(meta, open(f'{out}/{name}.json', 'w'), ensure_ascii=False, indent=1)
    print(f"{s['swe']:12} {s['gbif']:>8} {s['qid']:>9}  {s['license']:14} {s['artist'][:40]}", flush=True)
    time.sleep(PAUSE_IMAGE)

# Sammanställning av alla arter som är klara
allmeta = [json.load(open(f"{out}/{slug(s['swe'])}.json")) for s in species if os.path.exists(f"{out}/{slug(s['swe'])}.json")]
json.dump(allmeta, open(f'{out}/meta.json', 'w'), ensure_ascii=False, indent=1)
print(f'Klart: {len(allmeta)} av {len(species)} arter har foto och uppgifter.', flush=True)
