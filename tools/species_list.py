"""Gör en lista över arter i en djurgrupp som rapporterats till Artportalen (via GBIF).

Artnycklar och antal observationer kommer från GBIF. Vetenskapligt namn och svenskt namn
hämtas med EN SPARQL-fråga mot Wikidata (P846 = GBIF-nyckel), så Wikimedia belastas minimalt.

Användning: python3 -I tools/species_list.py <taxonKey> <minsta antal obs> <utfil.json>
  t.ex. fåglar: python3 -I tools/species_list.py 212 50 lab/pixel/birds.json
"""
import json, sys, time, urllib.parse, urllib.request

UA = {'User-Agent': 'ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib'}
DATASET = '38b4c89f-584c-41bb-bd8f-cd1def33e92f'  # Artportalen
taxon, min_obs, outfile = sys.argv[1], int(sys.argv[2]), sys.argv[3]

def get(url, data=None):
    req = urllib.request.Request(url, headers=UA, data=data)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

# 1) Alla arter i gruppen med antal observationer (GBIF)
fac = get('https://api.gbif.org/v1/occurrence/search?' + urllib.parse.urlencode(
    {'datasetKey': DATASET, 'taxonKey': taxon, 'limit': 0, 'facet': 'speciesKey', 'facetLimit': 3000}))
counts = {c['name']: c['count'] for c in fac['facets'][0]['counts'] if c['count'] >= min_obs}
print(f'{len(fac["facets"][0]["counts"])} arter totalt, {len(counts)} med minst {min_obs} observationer')

# 2) Namn från Wikidata, en fråga för alla
values = ' '.join(f'"{k}"' for k in counts)
query = f'''SELECT ?gbif ?sci ?sv WHERE {{
  VALUES ?gbif {{ {values} }}
  ?item wdt:P846 ?gbif .
  OPTIONAL {{ ?item wdt:P225 ?sci }}
  OPTIONAL {{ ?item rdfs:label ?sv FILTER(LANG(?sv) = "sv") }}
}}'''
res = get('https://query.wikidata.org/sparql', data=urllib.parse.urlencode({'query': query, 'format': 'json'}).encode())
names = {}
for b in res['results']['bindings']:
    n = names.setdefault(b['gbif']['value'], {})
    if 'sci' in b: n.setdefault('sci', b['sci']['value'])
    if 'sv' in b: n.setdefault('swe', b['sv']['value'])

# 3) Arter som saknas på Wikidata: namn från GBIF i stället
out = []
for key, n_obs in sorted(counts.items(), key=lambda kv: -kv[1]):
    n = names.get(key, {})
    if 'sci' not in n:
        sp = get(f'https://api.gbif.org/v1/species/{key}')
        n['sci'] = sp.get('canonicalName') or sp.get('scientificName')
    swe = n.get('swe') or n['sci']
    out.append({'gbif': int(key), 'sci': n['sci'], 'swe': swe[:1].upper() + swe[1:], 'obs': n_obs})
json.dump(out, open(outfile, 'w'), ensure_ascii=False, indent=1)
print(f'{len(out)} arter → {outfile}  ({sum(1 for k in counts if k in names)} hittade på Wikidata)')
