#!/usr/bin/env python3
"""Hämtar BirdLife Sveriges raritetskatalog (Raritetskommittén, Rk) till data/rk.json.

Katalogen har en sida per art med antalet godkända fynd i Sverige, och för arter som blivit vanligare
från vilket år Rk slutade granska dem. Arterna kopplas till GBIF:s artnycklar via det vetenskapliga namnet.

Användning:
    python3 -I tools/rk_katalog.py

Skriver data/rk.json:
    {"source", "hamtad", "arter": {gbif-nyckel: {"sv", "sci", "fynd", "ind", "slutat"}}}
där "slutat" är året Rk slutade granska arten (då är den inte längre en raritet), annars null,
och "kat" är kategorin i Sverigelistan (A–C vilda, D kanske förrymda, E förrymda).
"""
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import sys
sys.stdout.reconfigure(line_buffering=True)
UA = "ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib"
BASE = "https://birdlife.se/rk/raritetskatalogen/"
OUT = Path(__file__).resolve().parent.parent / "data" / "rk.json"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for tries in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if tries == 3:
                raise
            time.sleep(3 * (tries + 1))


def links(page, prefix):
    return sorted({u for u in re.findall(r'href="(' + re.escape(prefix) + r'[^"#?]+/)"', page) if u != prefix})


def text_lines(page):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return [l.strip() for l in t.split("\n") if l.strip()]


def species_page(url):
    page = get(url)
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    full = html.unescape(title.group(1)) if title else ""
    cat = re.search(r"\[([A-E])\]", full)
    sv = re.sub(r"\s*\[[A-E]\]\s*$", "", full.split(" / ")[0].strip())
    # underarter, hybrider och obestämda par räknas inte: de skulle göra en vanlig art till raritet
    if re.search(r"\bssp\b|\bsspp\b| x |obest|\bobs?\.", full, re.I):
        return None
    lines = text_lines(page)
    i = next((i for i, l in enumerate(lines) if l.startswith("Antal fynd")), None)
    if i is None:
        return None
    # antalet står ibland utspritt på flera rader, med årtal och fotnoter: "118 (2022, excl. 2021) / 184** (**2022)"
    t = re.sub(r"Antal fynd/individer|\(?[Nn]umber of records/individuals\)?:?", " ", " ".join(lines[i:i + 6]))
    m = re.search(r"(\d+)\**(?:\s*\([^)]*\))?\s*/\s*\**\s*(\d+)", t)
    if not m:
        return None
    # det vetenskapliga namnet står närmast under rubriken "Svenskt / Engelskt namn"
    head = full.split(" - BirdLife")[0].strip()
    h = next((j for j, l in enumerate(lines) if l == head), None)
    sci = next((l for l in lines[(h + 1 if h is not None else max(0, i - 8)):i]
                if re.fullmatch(r"[A-Z][a-z]+ [a-z]+", l)), None)
    stop = next((re.search(r"(\d{4})", l) for l in lines[(h or 0):i] if "bedöms inte" in l), None)
    return {"sv": sv, "sci": sci, "fynd": int(m.group(1)), "ind": int(m.group(2)),
            "slutat": int(stop.group(1)) if stop else None, "kat": cat.group(1) if cat else "A", "url": url}


def gbif_key(sci):
    q = urllib.parse.urlencode({"name": sci, "kingdom": "Animalia", "class": "Aves"})
    d = json.loads(get("https://api.gbif.org/v1/species/match?" + q))
    # stavfel i katalogen ("Croicocephalus") klaras av en säker ungefärlig träff
    ok = d.get("matchType") == "EXACT" or (d.get("matchType") == "FUZZY" and d.get("confidence", 0) >= 90)
    if ok and d.get("rank") == "SPECIES" and d.get("class") == "Aves":
        return d.get("speciesKey") or d.get("usageKey")
    return None


def main():
    index = get(BASE)
    groups = links(index, BASE)
    arter, missing = {}, []
    for g in groups:
        for url in links(get(g), g):
            time.sleep(0.4)
            sp = species_page(url)
            if not sp or not sp["sci"]:
                missing.append(url)
                continue
            key = gbif_key(sp["sci"])
            if not key:
                missing.append(url)
                continue
            # samma art kan ha flera sidor (underarter): räkna ihop fynden
            old = arter.get(str(key))
            if old:
                old["fynd"] += sp["fynd"]; old["ind"] += sp["ind"]
                continue
            arter[str(key)] = {k: sp[k] for k in ("sv", "sci", "fynd", "ind", "slutat", "kat")}
            print(f"{sp['sv']:<28} {sp['sci']:<30} {sp['fynd']:>5}  {sp['slutat'] or ''}")
    OUT.write_text(json.dumps({"source": "BirdLife Sverige, Raritetskommitténs raritetskatalog (birdlife.se/rk/raritetskatalogen)",
                               "hamtad": date.today().isoformat(), "arter": arter}, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(arter)} arter → {OUT}")
    if missing:
        print("Kunde inte läsas eller kopplas:", *missing, sep="\n  ")


if __name__ == "__main__":
    main()
