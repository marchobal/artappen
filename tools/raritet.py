#!/usr/bin/env python3
"""Hur vanlig är varje art i Sverige? Antal fynd i Artportalen de senaste tio åren, per art.

Användning:
    python3 -I tools/raritet.py

Skriver data/raritet.json:
    {"years": "2016,2025", "fetched": "...", "grupper": {"birds": {"<speciesKey>": antal, ...}, ...}}
Appen räknar själv ut en percentil inom djurgruppen och ger varje art en raritetsklass.
Källa: GBIF.org, Artportalen (SLU Artdatabanken), CC0. Kör om ungefär en gång om året.
"""
import json
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = "38b4c89f-584c-41bb-bd8f-cd1def33e92f"
UA = "ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib"
GROUPS = {"mammals": [359], "birds": [212], "herps": [131, 11592253, 11418114]}
LAST = date.today().year - 1
YEARS = f"{LAST - 9},{LAST}"


def get(url):
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:  # GBIF svarar ibland 503
            print(f"  fel ({e}), försöker igen")
            time.sleep(2 ** attempt)
    raise RuntimeError("GBIF svarar inte")


def main():
    out = {}
    for gid, keys in GROUPS.items():
        tax = "".join(f"&taxonKey={k}" for k in keys)
        d = get(f"https://api.gbif.org/v1/occurrence/search?datasetKey={DATASET}&country=SE{tax}&year={YEARS}"
                f"&occurrenceStatus=PRESENT&limit=0&facet=speciesKey&facetLimit=5000")
        out[gid] = {c["name"]: c["count"] for c in d["facets"][0]["counts"]}
        print(f"{gid}: {len(out[gid])} arter, {d['count']} fynd")
    (ROOT / "data/raritet.json").write_text(json.dumps({
        "years": YEARS, "fetched": date.today().isoformat(),
        "källa": "GBIF.org, Artportalen (SLU Artdatabanken), CC0", "grupper": out,
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
