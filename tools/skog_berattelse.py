#!/usr/bin/env python3
"""Detaljdata för berättelsen om skogen (/trend/skogen.html): skog och förlust i full upplösning
plus terräng, för ett utsnitt på ungefär 20 × 20 km runt varje plats.

Användning:
    python3 -I tools/skog_berattelse.py <tom mapp för rutorna>

För varje plats:
    data/skog/plats_<id>.png   tools/skog_forlust.swift med zoom 10 och F = 1 (≈ 30–45 m per pixel):
                               röd = år efter 2000 då skogen försvann, blå = 255 där det var skog år 2000
och gemensamt:
    data/skog/berattelse.json  {"platser": {id: {"nord", "vast", "syd", "ost", "hojd": {"w", "h", "m": [...]}}}}
Höjden kommer från AWS Terrain Tiles (zoom 11), samma källa som landskapets höjdkarta.

Platserna är valda ur data/skog/forlust.png där mönstren är tydligast (se SCENER).
"""
import json
import math
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from sverige_hojd import read_png, merc, URL, UA  # noqa: E402

HALV_KM = 10
HZ = 11            # terrängens zoom
HN = 128           # höjdpunkter per sida

# id: (lat, lon) mitt i utsnittet
SCENER = {
    "norrbotten": (66.10, 20.74),   # Norrbottens inland mellan Harads och Vuollerim: jämn avverkning, 45 % av skogen
    "gudrun": (56.73, 14.68),       # Kronoberg vid Alvesta/Växjö: en fjärdedel av skogen föll 2005
    "brand": (59.92, 16.13),        # Västmanlandsbranden 2014
    "barkborre": (58.88, 17.31),    # Sörmland: granbarkborren efter torkan 2018, topp 2019–2022
    "vinnare": (63.53, 18.17),      # Västernorrlands inland: lapptäcke av hyggen och ungskog
}


def terrain(cache, nord, vast, syd, ost):
    (mx0, my0), (mx1, my1) = merc(nord, vast), merc(syd, ost)
    n = 2 ** HZ
    tiles = {}
    out = []
    for j in range(HN):
        my = my0 + (j + 0.5) / HN * (my1 - my0)
        for i in range(HN):
            mx = mx0 + (i + 0.5) / HN * (mx1 - mx0)
            tx, ty = int(mx * n), int(my * n)
            if (tx, ty) not in tiles:
                f = cache / f"terrarium_{HZ}_{tx}_{ty}.png"
                if not f.exists():
                    req = urllib.request.Request(URL.format(z=HZ, x=tx, y=ty), headers={"User-Agent": UA})
                    with urllib.request.urlopen(req, timeout=60) as r:
                        f.write_bytes(r.read())
                    time.sleep(0.2)
                tiles[(tx, ty)] = read_png(f.read_bytes())
            w, h, ch, rows = tiles[(tx, ty)]
            px = min(w - 1, int((mx * n - tx) * w)); py = min(h - 1, int((my * n - ty) * h))
            r, g, b = rows[py][px * ch:px * ch + 3]
            out.append(max(0, round(r * 256 + g + b / 256 - 32768)))
    return {"w": HN, "h": HN, "m": out}


def main():
    cache = Path(sys.argv[1]); cache.mkdir(parents=True, exist_ok=True)
    platser = {}
    for pid, (lat, lon) in SCENER.items():
        dlat = HALV_KM / 111.0
        dlon = HALV_KM / (111.0 * math.cos(math.radians(lat)))
        nord, syd, vast, ost = lat + dlat, lat - dlat, lon - dlon, lon + dlon
        subprocess.run(["swift", str(ROOT / "tools/skog_forlust.swift"), str(ROOT / f"data/skog/plats_{pid}.png"),
                        str(cache), "10", "1", f"{nord:.5f}", f"{vast:.5f}", f"{syd:.5f}", f"{ost:.5f}"], check=True)
        platser[pid] = {"nord": round(nord, 5), "vast": round(vast, 5), "syd": round(syd, 5), "ost": round(ost, 5),
                        "hojd": terrain(cache, nord, vast, syd, ost)}
        print(f"{pid}: klar, högsta punkt {max(platser[pid]['hojd']['m'])} m", file=sys.stderr)
    (ROOT / "data/skog/berattelse.json").write_text(json.dumps({
        "källa": "Hansen m.fl. Global Forest Change v1.13 via Global Forest Watch (CC BY 4.0); "
                 "AWS Terrain Tiles (Mapzen/Tilezen)",
        "platser": platser}, separators=(",", ":")))


if __name__ == "__main__":
    main()
