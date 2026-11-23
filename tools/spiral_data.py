#!/usr/bin/env python3
"""Räknar flyttfåglarnas fynd per år och dag för årsspiralen (/flytt/spiral.html).

Användning:
    python3 -I tools/spiral_data.py

Läser samma GBIF-nedladdning som tools/gbif_nedladdning.py (Artportalen, alla flyttfåglar i
data/flock/arter.json) och skriver data/spiral/<speciesKey>.json:
    {"key", "namn", "flytt", "years": [...], "counts": [[antal per dag 1–366] per år],
     "arrival": [ankomstdag per år eller null], "trend": dagar per tio år}

Ankomstdag: dagen då 10 % av vårens fynd (februari–juni) har kommit, sedan vinterns nivå
(medel för januari) har dragits bort. Ett år räknas bara om det har minst 150 vårfynd.
Trenden är lutningen i en rak linje genom ankomstdagarna, i dagar per tio år (negativ = tidigare).
"""
import csv
import io
import json
import os
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

os.chdir(Path(__file__).resolve().parent.parent)
FIRST_YEAR, LAST_YEAR = 1990, 2025
OUT = Path("data/spiral")
SPRING = (32, 181)          # 1 februari – 30 juni
MIN_SPRING = 150


def arrival_day(counts):
    winter = sum(counts[0:31]) / 31
    spring = [max(0.0, counts[d - 1] - winter) for d in range(SPRING[0], SPRING[1] + 1)]
    total = sum(spring)
    if total < MIN_SPRING:
        return None
    acc = 0.0
    for i, v in enumerate(spring):
        acc += v
        if acc >= 0.1 * total:
            return SPRING[0] + i
    return None


def slope(xs, ys):
    n = len(xs)
    if n < 8:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else None


def main():
    arter = {int(a["key"]): a for a in json.loads(Path("data/flock/arter.json").read_text())["arter"]}
    key = json.loads(Path("data/flock/nedladdning.json").read_text())["key"]
    z = zipfile.ZipFile(f"lab/gbif/{key}.zip")
    csv.field_size_limit(1 << 24)
    years = list(range(FIRST_YEAR, LAST_YEAR + 1))
    counts = defaultdict(lambda: [[0] * 366 for _ in years])
    with z.open(next(n for n in z.namelist() if n.endswith(".csv"))) as raw:
        rows = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE)
        ix = {h: i for i, h in enumerate(next(rows))}
        for r in rows:
            try:
                sk = int(r[ix["speciesKey"]]); y = int(r[ix["year"]])
                if sk not in arter or not FIRST_YEAR <= y <= LAST_YEAR:
                    continue
                doy = date(y, int(r[ix["month"]]), int(r[ix["day"]])).timetuple().tm_yday
            except (ValueError, IndexError):
                continue
            counts[sk][y - FIRST_YEAR][doy - 1] += 1

    OUT.mkdir(parents=True, exist_ok=True)
    lst = []
    for sk, per_year in counts.items():
        a = arter[sk]
        arr = [arrival_day(c) for c in per_year]
        pts = [(y, d) for y, d in zip(years, arr) if d is not None]
        s = slope([p[0] for p in pts], [p[1] for p in pts])
        trend = round(s * 10, 1) if s is not None else None
        (OUT / f"{sk}.json").write_text(json.dumps({
            "key": sk, "namn": a["namn"], "flytt": a["flytt"], "years": years, "counts": per_year,
            "arrival": arr, "trend": trend,
            "källa": "GBIF.org, Artportalen (SLU Artdatabanken), CC0",
        }, ensure_ascii=False, separators=(",", ":")))
        lst.append({"key": sk, "namn": a["namn"], "flytt": a["flytt"], "trend": trend})
        print(f"{a['namn']:24s} {a['flytt']:10s} ankomst {len(pts)} år, trend {trend} dagar per tio år")
    lst.sort(key=lambda a: (a["flytt"] != "långflytt", a["namn"]))
    (OUT / "arter.json").write_text(json.dumps({"arter": lst}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
