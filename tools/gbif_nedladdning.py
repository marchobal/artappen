#!/usr/bin/env python3
"""Beställer, hämtar och packar en GBIF-nedladdning med flyttfåglarnas fynd.

Steg:
    python3 -I tools/gbif_nedladdning.py bestall   # lägger beställningen hos GBIF
    python3 -I tools/gbif_nedladdning.py status    # visar om filen är klar
    python3 -I tools/gbif_nedladdning.py hamta     # laddar ner zip-filen till lab/gbif/
    python3 -I tools/gbif_nedladdning.py packa     # gör data/flock/<speciesKey>.json

Artlistan läses från data/flock/arter.json (byggs av tools/flyttfaglar.py).
Inloggningen läses från Macens nyckelring, posten "gbif.org". Lägg in den en gång med
    security add-generic-password -s gbif.org -a <användarnamn> -w
Lösenordet skrivs aldrig ut och sparas inte i någon fil.

Fynd i samma ruta (0,02° nord–syd × 0,04° öst–väst, ungefär 2 × 2 km), samma dag och
samma period slås ihop till en rad med vikt w. Perioderna är 0 = före 2000,
1 = 2000 till elva år före senaste året, 2 = de senaste tio åren. Utdata:
    {"speciesKey", "name", "n", "rows", "doi", "minYear", "maxYear", "periods",
     "lat":[…], "lon":[…], "doy":[…], "p":[…], "w":[…]}
"""
import base64
import csv
import io
import json
import re
import subprocess
import sys
import time
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

DATASET = "38b4c89f-584c-41bb-bd8f-cd1def33e92f"
API = "https://api.gbif.org/v1/occurrence/download"
UA = "ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib"
ARTER = Path("data/flock/arter.json")
STATE = Path("data/flock/nedladdning.json")
WORK = Path("lab/gbif")
GLAT, GLON = 0.02, 0.04  # rutstorlek i grader


def credentials():
    try:
        info = subprocess.run(["security", "find-generic-password", "-s", "gbif.org"],
                              capture_output=True, text=True, check=True).stdout
        pw = subprocess.run(["security", "find-generic-password", "-s", "gbif.org", "-w"],
                            capture_output=True, text=True, check=True).stdout.rstrip("\n")
    except subprocess.CalledProcessError:
        sys.exit("Hittar ingen GBIF-inloggning i nyckelringen (posten gbif.org).")
    user = re.search(r'"acct"<blob>="([^"]*)"', info).group(1)
    return user, pw


def request(url, data=None, auth=None):
    headers = {"User-Agent": UA}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
    return urllib.request.Request(url, data=data, headers=headers)


def arter():
    return json.loads(ARTER.read_text())["arter"]


def bestall():
    user, pw = credentials()
    keys = [int(a["key"]) for a in arter()]
    body = {
        "creator": user,
        "sendNotification": False,
        "format": "SIMPLE_CSV",
        "predicate": {"type": "and", "predicates": [
            {"type": "equals", "key": "DATASET_KEY", "value": DATASET},
            {"type": "in", "key": "TAXON_KEY", "values": [str(k) for k in keys]},
            {"type": "equals", "key": "HAS_COORDINATE", "value": "true"},
            {"type": "equals", "key": "OCCURRENCE_STATUS", "value": "PRESENT"},
        ]},
    }
    req = request(f"{API}/request", json.dumps(body).encode(), (user, pw))
    with urllib.request.urlopen(req, timeout=60) as r:
        key = r.read().decode().strip()
    STATE.write_text(json.dumps({"key": key, "bestalld": date.today().isoformat(),
                                 "arter": keys}, indent=1))
    print(f"Beställd: {key} ({len(keys)} arter). Kör 'status' om en stund.")


def info():
    key = json.loads(STATE.read_text())["key"]
    with urllib.request.urlopen(request(f"{API}/{key}"), timeout=60) as r:
        return json.load(r)


def status():
    d = info()
    print(f"{d['key']}: {d['status']}, {d.get('totalRecords', '?')} fynd, "
          f"{d.get('size', 0) / 1e6:.0f} MB, DOI {d.get('doi')}")
    s = json.loads(STATE.read_text())
    s.update({"status": d["status"], "doi": d.get("doi"), "fynd": d.get("totalRecords")})
    STATE.write_text(json.dumps(s, indent=1))


def hamta():
    d = info()
    if d["status"] != "SUCCEEDED":
        sys.exit(f"Inte klar än: {d['status']}")
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"{d['key']}.zip"
    with urllib.request.urlopen(request(d["downloadLink"]), timeout=120) as r, open(out, "wb") as f:
        total, t0 = 0, time.time()
        while chunk := r.read(1 << 20):
            f.write(chunk); total += len(chunk)
            if total % (100 << 20) < (1 << 20):
                print(f"  {total / 1e6:.0f} MB", file=sys.stderr)
    print(f"Hämtad: {out} ({total / 1e6:.0f} MB på {time.time() - t0:.0f} s)")


def packa():
    s = json.loads(STATE.read_text())
    z = zipfile.ZipFile(WORK / f"{s['key']}.zip")
    name = next(n for n in z.namelist() if n.endswith(".csv"))
    csv.field_size_limit(1 << 24)
    wanted = {int(a["key"]): a for a in arter()}
    cells = defaultdict(Counter)
    skipped = 0
    with z.open(name) as raw:
        rows = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE)
        head = next(rows)
        ix = {h: i for i, h in enumerate(head)}
        for n, r in enumerate(rows, 1):
            try:
                sk = int(r[ix["speciesKey"]])
                y, m, d = int(r[ix["year"]]), int(r[ix["month"]]), int(r[ix["day"]])
                doy = date(y, m, d).timetuple().tm_yday
                la, lo = float(r[ix["decimalLatitude"]]), float(r[ix["decimalLongitude"]])
            except (ValueError, IndexError):
                skipped += 1
                continue
            if sk in wanted:
                cells[sk][(y, doy, round(la / GLAT), round(lo / GLON))] += 1
            if n % 1_000_000 == 0:
                print(f"  {n / 1e6:.0f} miljoner rader", file=sys.stderr)
    print(f"{skipped} rader saknade datum eller position")

    max_year = max(k[0] for c in cells.values() for k in c)
    recent = max_year - 9
    periods = ["före 2000", f"2000–{recent - 1}", f"{recent}–{max_year}"]
    for sk, c in sorted(cells.items(), key=lambda x: -sum(x[1].values())):
        agg = Counter()
        for (y, doy, la, lo), w in c.items():
            agg[(0 if y < 2000 else 2 if y >= recent else 1, doy, la, lo)] += w
        rows = sorted(agg.items())
        out = ARTER.parent / f"{sk}.json"
        out.write_text(json.dumps({
            "speciesKey": sk, "name": wanted[sk]["namn"],
            "n": sum(c.values()), "rows": len(rows),
            "source": "GBIF.org, Artportalen (SLU Artdatabanken), CC0",
            "doi": s.get("doi"), "fetched": s.get("bestalld"),
            "minYear": min(k[0] for k in c), "maxYear": max_year, "periods": periods,
            "lat": [round(k[2] * GLAT, 2) for k, _ in rows],
            "lon": [round(k[3] * GLON, 2) for k, _ in rows],
            "doy": [k[1] for k, _ in rows], "p": [k[0] for k, _ in rows],
            "w": [w for _, w in rows],
        }, separators=(",", ":")))
        print(f"  {wanted[sk]['namn']}: {sum(c.values())} fynd, {len(rows)} rader, "
              f"{out.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"bestall": bestall, "status": status, "hamta": hamta, "packa": packa}.get(
        cmd, lambda: sys.exit(__doc__))()
