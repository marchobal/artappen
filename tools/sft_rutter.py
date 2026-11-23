#!/usr/bin/env python3
"""Svensk Fågeltaxerings standardrutter från GBIF: räkningar per rutt, år och art.

Steg (samma GBIF-konto i nyckelringen som tools/gbif_nedladdning.py):
    python3 -I tools/sft_rutter.py bestall
    python3 -I tools/sft_rutter.py status
    python3 -I tools/sft_rutter.py hamta
    python3 -I tools/sft_rutter.py packa

Datasetet "Swedish Bird Survey: Fixed routes (Standardrutterna)", Lunds universitet, CC0.
Det innehåller bara fynd. En rutt räknas som inventerad ett år om den har något fynd det året,
och då betyder att en art saknas där att den räknades till noll.

Utdata i data/trend/sft/:
    rutter.json   {"years": [...], "routes": [[id, lat, lon], ...], "surveyed": [[ruttindex...] per år]}
    <speciesKey>.json  {"key", "namn", "latin", "counts": {"ruttindex": [antal per år, null = ej inventerad]}}
    arter.json    artlistan: arter i Svenska djur som finns på minst 15 rutter
"""
import csv
import io
import json
import os
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

os.chdir(Path(__file__).resolve().parent.parent)
sys.path.insert(0, "tools")
from gbif_nedladdning import API, WORK, credentials, request  # noqa: E402

DATASET = "91fa1a0d-a208-40aa-8a6e-f2c0beb9b253"
OUT = Path("data/trend/sft")
STATE = OUT / "nedladdning.json"
SVENSKA_DJUR = Path.home() / "Svenska djur" / "data" / "alla-arter.json"
MIN_RUTTER = 15


def bestall():
    user, pw = credentials()
    body = {"creator": user, "sendNotification": False, "format": "SIMPLE_CSV",
            "predicate": {"type": "equals", "key": "DATASET_KEY", "value": DATASET}}
    with urllib.request.urlopen(request(f"{API}/request", json.dumps(body).encode(), (user, pw)), timeout=60) as r:
        key = r.read().decode().strip()
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"key": key, "bestalld": date.today().isoformat()}, indent=1))
    print(f"Beställd: {key}")


def info():
    key = json.loads(STATE.read_text())["key"]
    with urllib.request.urlopen(request(f"{API}/{key}"), timeout=60) as r:
        return json.load(r)


def status():
    d = info()
    print(f"{d['key']}: {d['status']}, {d.get('totalRecords', '?')} rader, DOI {d.get('doi')}")
    s = json.loads(STATE.read_text()); s.update({"status": d["status"], "doi": d.get("doi")})
    STATE.write_text(json.dumps(s, indent=1))


def hamta():
    d = info()
    if d["status"] != "SUCCEEDED":
        sys.exit(f"Inte klar än: {d['status']}")
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"{d['key']}.zip"
    with urllib.request.urlopen(request(d["downloadLink"]), timeout=120) as r, open(out, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    print(f"Hämtad: {out} ({out.stat().st_size / 1e6:.0f} MB)")


def packa():
    s = json.loads(STATE.read_text())
    z = zipfile.ZipFile(WORK / f"{s['key']}.zip")
    csv.field_size_limit(1 << 24)
    routes = {}                                   # rutt-id → (lat, lon)
    surveyed = defaultdict(set)                   # år → rutt-id
    counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))   # art → rutt → år → antal
    names = {}
    with z.open(next(n for n in z.namelist() if n.endswith(".csv"))) as raw:
        rows = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE)
        ix = {h: i for i, h in enumerate(next(rows))}
        for r in rows:
            try:
                route = r[ix["locality"]].rsplit(":", 1)[-1]
                year = int(r[ix["year"]])
                lat, lon = float(r[ix["decimalLatitude"]]), float(r[ix["decimalLongitude"]])
            except (ValueError, IndexError):
                continue
            routes.setdefault(route, (round(lat, 3), round(lon, 3)))
            surveyed[year].add(route)
            sk, latin = r[ix["speciesKey"]], r[ix["species"]]
            if not sk:
                continue
            n = r[ix["individualCount"]]
            counts[sk][route][year] += int(float(n)) if n else 1
            names[sk] = latin

    years = sorted(surveyed)
    rids = sorted(routes, key=lambda x: int(x) if x.isdigit() else x)
    rindex = {rid: i for i, rid in enumerate(rids)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "rutter.json").write_text(json.dumps({
        "years": years, "routes": [[rid, *routes[rid]] for rid in rids],
        "surveyed": [sorted(rindex[x] for x in surveyed[y]) for y in years],
        "källa": "Svensk Fågeltaxering, Lunds universitet: Swedish Bird Survey: Fixed routes (Standardrutterna), via GBIF.org, CC0",
        "doi": s.get("doi"),
    }, ensure_ascii=False, separators=(",", ":")))

    svenska = {a["latin"]: a["namn"] for a in json.loads(SVENSKA_DJUR.read_text())["arter"]}
    arter = []
    for sk, per_route in counts.items():
        namn = svenska.get(names[sk])
        if not namn or len(per_route) < MIN_RUTTER:
            continue
        out = {}
        for rid, per_year in per_route.items():
            out[rindex[rid]] = [per_year.get(y, 0) if rid in surveyed[y] else None for y in years]
        (OUT / f"{sk}.json").write_text(json.dumps({"key": int(sk), "namn": namn, "latin": names[sk], "counts": out},
                                                   ensure_ascii=False, separators=(",", ":")))
        arter.append({"key": int(sk), "namn": namn, "rutter": len(per_route)})
    arter.sort(key=lambda a: a["namn"])
    (OUT / "arter.json").write_text(json.dumps({"arter": arter}, ensure_ascii=False, indent=1))
    print(f"{len(routes)} rutter, åren {years[0]}–{years[-1]}, {len(arter)} arter från Svenska djur")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"bestall": bestall, "status": status, "hamta": hamta, "packa": packa}.get(cmd, lambda: sys.exit(__doc__))()
