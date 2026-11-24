#!/usr/bin/env python3
"""Hur vanlig är varje art i Sverige? Utbredning i kommunerna de senaste tio åren.

Användning:
    python3 -I tools/raritet.py

Antalet fynd i Artportalen säger mest hur gärna folk rapporterar en art: ingen rapporterar varje
brunråtta eller kråka. Utbredningen tål det bättre: i hur många av Sveriges kommuner (GADM nivå 2)
har arten hittats minst en gång på tio år? En vanlig art finns nästan överallt, en sällsynt på få ställen.

Skriver data/raritet.json:
    {"years": "2016,2025", "fetched": "...", "omraden": antal kommuner med fynd,
     "grupper": {"birds": {"<speciesKey>": [kommuner, fynd], ...}, ...}}
Källa: GBIF.org, Artportalen (SLU Artdatabanken), CC0. Kör om ungefär en gång om året.
"""
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = "38b4c89f-584c-41bb-bd8f-cd1def33e92f"
UA = "ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib"
GROUPS = {"mammals": [359], "birds": [212], "herps": [131, 11592253, 11418114]}
LAST = date.today().year - 1
YEARS = f"{LAST - 9},{LAST}"
BASE = f"https://api.gbif.org/v1/occurrence/search?datasetKey={DATASET}&country=SE&year={YEARS}&occurrenceStatus=PRESENT&limit=0"


def get(url):
    for attempt in range(7):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:  # GBIF svarar ibland 503 eller 429
            print(f"  fel ({e}), försöker igen", flush=True)
            time.sleep(2 ** attempt)
    raise RuntimeError("GBIF svarar inte")


def facet(url, field="speciesKey", limit=5000):
    d = get(f"{url}&facet={field}&facetLimit={limit}")
    return {c["name"]: c["count"] for c in (d["facets"][0]["counts"] if d["facets"] else [])}


def main():
    tax = {g: "".join(f"&taxonKey={k}" for k in keys) for g, keys in GROUPS.items()}
    alla = "".join(tax.values())
    # antal fynd per art och grupp (som förut)
    counts = {g: facet(BASE + t) for g, t in tax.items()}
    for g in counts:
        print(f"{g}: {len(counts[g])} arter", flush=True)
    # kommunerna, och vilka arter som finns i var och en
    omraden = [k for k in facet(BASE + alla, "gadmLevel2Gid", 1000) if k.startswith("SWE.")]
    print(f"{len(omraden)} kommuner", flush=True)
    spread = {}

    def one(gid):
        return facet(f"{BASE}{alla}&gadmLevel2Gid={gid}")

    with ThreadPoolExecutor(4) as pool:
        for i, sp in enumerate(pool.map(one, omraden)):
            for k in sp:
                spread[k] = spread.get(k, 0) + 1
            if i % 40 == 0:
                print(f"  {i + 1} av {len(omraden)}", flush=True)
    out = {g: {k: [spread.get(k, 0), n] for k, n in m.items()} for g, m in counts.items()}
    (ROOT / "data/raritet.json").write_text(json.dumps({
        "years": YEARS, "fetched": date.today().isoformat(), "omraden": len(omraden),
        "källa": "GBIF.org, Artportalen (SLU Artdatabanken), CC0", "grupper": out,
    }, separators=(",", ":")))
    print("klart", flush=True)


if __name__ == "__main__":
    main()
