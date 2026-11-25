"""Flyttar in färgscheman och pixelfigurer från labbet i appen.

Läser lab/pixel/src/<slug>.json (foto, fotograf, licens) och lab/pixel/out/<slug>-*.png/-palette.json,
slår upp artens nyckel så som den förekommer i Artportalens observationer på GBIF, och skriver:
  data/palettes.json          { "<speciesKey>": { colors, sprite, credit } }
  img/sprites/<key>-16.png, img/sprites/<key>-24.png

Användning: python3 -I tools/export_palettes.py [labbmapp]

Bara arter som är OK i granskningen (reviews.json) tas med, plus de som redan finns i appen.
"""
import json, os, shutil, sys, time, urllib.error, urllib.parse, urllib.request

lab = sys.argv[1] if len(sys.argv) > 1 else 'lab/pixel'
DATASET = '38b4c89f-584c-41bb-bd8f-cd1def33e92f'  # Artportalen

def occurrence_key(sci):
    """Artnyckeln som appen ser i observationerna (kan skilja sig från namnmatchningen)."""
    url = 'https://api.gbif.org/v1/occurrence/search?' + urllib.parse.urlencode(
        {'datasetKey': DATASET, 'scientificName': sci, 'limit': 1})
    req = urllib.request.Request(url, headers={'User-Agent': 'ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib'})
    for tries in range(6):  # GBIF svarar ibland "för många anrop" (429): vänta och försök igen
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r)['results']
            time.sleep(0.3)
            return str(res[0]['speciesKey']) if res else None
        except urllib.error.HTTPError as e:
            if e.code != 429 or tries == 5: raise
            time.sleep(5 * (tries + 1))

os.makedirs('data', exist_ok=True); os.makedirs('img/sprites', exist_ok=True)
reviews = json.load(open(f'{lab}/reviews.json')) if os.path.exists(f'{lab}/reviews.json') else {}
in_app = {v['name'] for v in json.load(open('data/palettes.json')).values()} if os.path.exists('data/palettes.json') else set()
out = {}
for f in sorted(os.listdir(f'{lab}/src')):
    if not f.endswith('.json') or f == 'meta.json': continue
    m = json.load(open(f'{lab}/src/{f}'))
    s = m['slug']
    if reviews.get(s, {}).get('status') != 'ok' and m['swe'] not in in_app: continue
    pal_file = f'{lab}/out/{s}-palette.json'
    if not os.path.exists(pal_file): continue
    key = occurrence_key(m['sci']) or str(m['gbif'])
    for n in (16, 24):
        shutil.copyfile(f'{lab}/out/{s}-{n}.png', f'img/sprites/{key}-{n}.png')
    colors = json.load(open(pal_file))['full']
    total = sum(c[3] for c in colors) or 1
    out[key] = {
        'name': m['swe'],
        'colors': [[c[0], c[1], c[2], round(c[3] / total, 4)] for c in colors],  # r, g, b, andel
        'sprite': f'img/sprites/{key}-24.png',
        'credit': {'artist': m['artist'], 'license': m['license'], 'licenseUrl': m['licenseUrl'], 'page': m['page']},
    }
    print(f"{m['swe']:10} {key:>9}  {len(colors)} färger")
json.dump(out, open('data/palettes.json', 'w'), ensure_ascii=False, separators=(',', ':'))
print(f'{len(out)} arter → data/palettes.json')
