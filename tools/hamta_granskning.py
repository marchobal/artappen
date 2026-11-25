#!/usr/bin/env python3
"""Hämtar granskningarna som gjorts i appen (/granska/) och lägger in dem i lab/pixel/reviews.json.

Den nyaste granskningen av varje art vinner (fältet "t", "ÅÅÅÅ-MM-DD TT:MM").
Användning: python3 -I tools/hamta_granskning.py
"""
import json, os, urllib.request

UA = "ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib"
REVIEWS = os.path.abspath('lab/pixel/reviews.json')
req = urllib.request.Request('https://artappen-api.marchobal.workers.dev/granska', headers={'User-Agent': UA})
remote = json.load(urllib.request.urlopen(req, timeout=30))
local = json.load(open(REVIEWS)) if os.path.exists(REVIEWS) else {}
nya = 0
for slug, r in remote.items():
    if (r.get('t') or '') > (local.get(slug, {}).get('t') or ''):
        local[slug] = {**local.get(slug, {}), **r}; nya += 1
json.dump(local, open(REVIEWS, 'w'), ensure_ascii=False, indent=1)
print(f'{nya} nya eller ändrade av {len(remote)} granskningar från appen → {REVIEWS}')
