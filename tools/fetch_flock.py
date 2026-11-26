#!/usr/bin/env python3
"""Hämtar alla Artportalen-fynd av en art från GBIF och packar dem kompakt.

Användning:
    python3 -I tools/fetch_flock.py 4408732 data/flock/4408732.json "Blåhake"

Samma format som tools/gbif_nedladdning.py packar (för en art som inte fanns med i nedladdningen):
fynd i samma ruta (0,02° × 0,04°, ungefär 2 × 2 km), samma dag och samma period slås ihop till en rad
med vikt w. Perioderna är 0 = före 2000, 1 = 2000 till elva år före senaste året, 2 = de senaste tio åren.
    {"speciesKey", "name", "n", "rows", "minYear", "maxYear", "periods",
     "lat":[…], "lon":[…], "doy":[…], "p":[…], "w":[…]}
"""
import json
import sys
import time
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

DATASET = "38b4c89f-584c-41bb-bd8f-cd1def33e92f"
API = "https://api.gbif.org/v1/occurrence/search"
UA = "ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib"
PAGE = 300
MAX_OFFSET = 99_000  # GBIF tillåter inte offset + limit över 100 000
GLAT, GLON = 0.02, 0.04  # samma rutor som tools/gbif_nedladdning.py


def get(params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # GBIF svarar ibland 503
            wait = 2 ** attempt
            print(f"  fel ({e}), försöker igen om {wait} s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("GBIF svarar inte")


def fetch(params, cells):
    """Hämtar alla sidor för params och räknar in fynden i cells."""
    offset = 0
    while True:
        d = get({**params, "limit": PAGE, "offset": offset})
        for r in d["results"]:
            try:
                dd = date(r["year"], r["month"], r["day"])
                la, lo = r["decimalLatitude"], r["decimalLongitude"]
            except (KeyError, TypeError, ValueError):
                continue  # saknar fullständigt datum eller position
            cells[(r["year"], dd.timetuple().tm_yday, round(la / GLAT), round(lo / GLON))] += 1
        offset += PAGE
        if d.get("endOfRecords") or offset >= d["count"]:
            return
        time.sleep(0.1)


def main():
    key, out = sys.argv[1], Path(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else str(key)
    base = {"datasetKey": DATASET, "taxonKey": key, "hasCoordinate": "true",
            "occurrenceStatus": "PRESENT"}
    facets = get({**base, "limit": 0, "facet": "year", "facetLimit": 400})
    years = {int(c["name"]): c["count"] for c in facets["facets"][0]["counts"]}
    print(f"[{name}] {facets['count']} fynd, {len(years)} år", file=sys.stderr)

    cells = Counter()
    for y in sorted(years):
        if years[y] > MAX_OFFSET:
            for m in range(1, 13):
                fetch({**base, "year": y, "month": m}, cells)
        else:
            fetch({**base, "year": y}, cells)
        print(f"[{name}] {y}: {sum(cells.values())} fynd, {len(cells)} rader", file=sys.stderr)

    max_year = max(k[0] for k in cells)
    recent = max_year - 9
    agg = Counter()
    for (y, doy, la, lo), w in cells.items():
        agg[(0 if y < 2000 else 2 if y >= recent else 1, doy, la, lo)] += w
    rows = sorted(agg.items())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "speciesKey": int(key), "name": name,
        "n": sum(cells.values()), "rows": len(rows),
        "source": "GBIF.org, Artportalen (SLU Artdatabanken), CC0",
        "fetched": date.today().isoformat(),
        "minYear": min(k[0] for k in cells), "maxYear": max_year,
        "periods": ["före 2000", f"2000–{recent - 1}", f"{recent}–{max_year}"],
        "lat": [round(k[2] * GLAT, 2) for k, _ in rows], "lon": [round(k[3] * GLON, 2) for k, _ in rows],
        "doy": [k[1] for k, _ in rows], "p": [k[0] for k, _ in rows],
        "w": [w for _, w in rows],
    }, separators=(",", ":")))
    print(f"[{name}] Sparat {len(rows)} rader ({sum(cells.values())} fynd) i {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
