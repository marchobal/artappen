#!/usr/bin/env python3
"""Söker nya fotokandidater på Wikimedia Commons för arter som inte är godkända i granskningen.

Söker på det latinska namnet (Commons-kategorin och vanlig filsökning), sållar bort bilder som
uppenbart är fel (flykt, bo, ägg, ungar, museum, kartor, för små), och hämtar en miniatyr (640 px)
av de bästa till lab/pixel/cand/<slug>/. Metadata (fotograf, licens) sparas i lab/pixel/cand/<slug>.json.
Bilderna poängsätts sedan med tools/bedom_bilder.swift.

Användning: python3 -I tools/hitta_bilder.py [slug …]   (utan slug: Svenska fåglar-arter som inte är OK)
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

LAB = os.path.abspath('lab/pixel')
UA = {'User-Agent': 'ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib'}
API = 'https://commons.wikimedia.org/w/api.php?'
MAX = 16   # miniatyrer per art
SKIP = re.compile(r'egg|eier|oeuf|œuf|\bnest|nid\b|chick|pullus|juv|young|küken|flight|flying|in.flight|fly\b|vol\b|volo|vuelo|'
                  r'map|range|distribution|karte|skelet|skull|museum|specimen|stuffed|taxiderm|mhnt|naturalis|'
                  r'stamp|plate|illustration|drawing|painting|gould|naumann|audubon|hand|ringing|ringed|beringung|'
                  r'feather|feder|track|spoor|sono|spectro|\.svg$|\.gif$|\.png$|\.tif', re.I)


def get(url, raw=False):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                body = r.read()
            time.sleep(0.4)
            return body if raw else json.loads(body)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 5: raise
            time.sleep(int(e.headers.get('Retry-After') or 0) or 5 * 2 ** attempt)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 5: raise
            time.sleep(5)


def plain(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', h or '')).strip()


def files_for(sci):
    names = set()
    r = get(API + urllib.parse.urlencode({'action': 'query', 'list': 'categorymembers', 'cmtitle': f'Category:{sci}',
                                          'cmtype': 'file', 'cmlimit': 200, 'format': 'json'}))
    names |= {m['title'][5:] for m in r.get('query', {}).get('categorymembers', [])}
    r = get(API + urllib.parse.urlencode({'action': 'query', 'list': 'search', 'srsearch': f'"{sci}" filetype:bitmap',
                                          'srnamespace': 6, 'srlimit': 80, 'format': 'json'}))
    names |= {m['title'][5:] for m in r.get('query', {}).get('search', [])}
    return sorted(n for n in names if not SKIP.search(n) and n.lower().endswith(('.jpg', '.jpeg')))


def imageinfo(files):
    out = {}
    for i in range(0, len(files), 20):
        r = get(API + urllib.parse.urlencode({
            'action': 'query', 'titles': '|'.join('File:' + f for f in files[i:i + 20]), 'prop': 'imageinfo',
            'iiprop': 'url|extmetadata|size', 'iiurlwidth': 640,
            'iiextmetadatafilter': 'Artist|LicenseShortName|LicenseUrl|ImageDescription', 'format': 'json'}))
        for p in r['query']['pages'].values():
            if 'imageinfo' not in p: continue
            ii = p['imageinfo'][0]; md = ii.get('extmetadata', {})
            lic = md.get('LicenseShortName', {}).get('value', '')
            out[p['title'][5:]] = {'file': p['title'][5:], 'w': ii['width'], 'h': ii['height'], 'thumb': ii['thumburl'],
                                   'page': ii['descriptionurl'], 'artist': plain(md.get('Artist', {}).get('value', '')),
                                   'license': lic, 'licenseUrl': md.get('LicenseUrl', {}).get('value', ''),
                                   'desc': plain(md.get('ImageDescription', {}).get('value', ''))[:200]}
    return out


def main():
    reviews = json.load(open(f'{LAB}/reviews.json'))
    if len(sys.argv) > 1:
        slugs = sys.argv[1:]
    else:
        prio = json.load(open(f'{LAB}/prio.json'))
        slugs = [s for s in sorted(prio, key=prio.get) if reviews.get(s, {}).get('status') != 'ok' and os.path.exists(f'{LAB}/src/{s}.json')]
    os.makedirs(f'{LAB}/cand', exist_ok=True)
    for n, s in enumerate(slugs, 1):
        if os.path.exists(f'{LAB}/cand/{s}.json'):
            continue
        meta = json.load(open(f'{LAB}/src/{s}.json'))
        try:
            info = imageinfo(files_for(meta['sci']))
        except Exception as e:
            print(f'{n:3} {s}: fel {e}'); continue
        # bara fria licenser, tillräckligt stora, och liggande eller kvadratiska (profilbilder)
        ok = [c for c in info.values() if c['w'] >= 1000 and 0.9 <= c['w'] / c['h'] <= 2.2
              and not re.search(r'\bNC\b|\bND\b|non.?commercial|no.?deriv', c['license'], re.I) and c['license']
              and not SKIP.search(c['desc'])]
        ok.sort(key=lambda c: -min(c['w'], 3000))
        ok = ok[:MAX]
        os.makedirs(f'{LAB}/cand/{s}', exist_ok=True)
        for i, c in enumerate(ok):
            c['id'] = i
            path = f'{LAB}/cand/{s}/{i}.jpg'
            if not os.path.exists(path):
                try: open(path, 'wb').write(get(c['thumb'], raw=True))
                except Exception as e: c['fel'] = str(e)
        json.dump({'slug': s, 'sci': meta['sci'], 'swe': meta['swe'], 'cand': ok}, open(f'{LAB}/cand/{s}.json', 'w'), ensure_ascii=False, indent=1)
        print(f'{n:3}/{len(slugs)} {meta["swe"]:<28} {len(info):>3} hittade, {len(ok):>2} hämtade', flush=True)


if __name__ == '__main__':
    main()
