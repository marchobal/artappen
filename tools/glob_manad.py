#!/usr/bin/env python3
"""Hämtar en arts fynd i hela världen, månad för månad, för jordgloben (/flytt/glob.html).

Användning:
    python3 -I tools/glob_manad.py              # alla flyttfåglar i data/flock/arter.json
    python3 -I tools/glob_manad.py 2492606      # en art

Använder GBIF:s kartrutor (alla dataset, hela världen), som räknar fynden i rutor på servern.
Rutorna är ungefär 1,4 × 1,4 grader. Antalen är bara relativa (GBIF:s kartor räknar
ungefär dubbelt mot sökningen), så sidan visar dem på en logaritmisk skala. Utdata: data/glob/<speciesKey>.json
    {"key", "namn", "cells": [[lat, lon, [antal per månad jan–dec]], ...]}
Källa: GBIF.org (varje dataset har sin licens; GBIF:s kartor får användas med källhänvisning).
"""
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

os.chdir(Path(__file__).resolve().parent.parent)
UA = "ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib"
URL = ("https://api.gbif.org/v2/map/occurrence/adhoc/{z}/{x}/{y}.mvt?srs=EPSG:4326&taxonKey={key}"
       "&month={m}&bin=square")
# Zoomnivå 2 i EPSG:4326: rutor på 45 × 45 grader, med kartrutor på ungefär 1,4 grader i varje.
# GBIF bestämmer själv rutstorleken efter zoomnivån. Vi tar bara Europa, Afrika och västra Asien,
# där de svenska flyttfåglarna finns.
Z = 2
TILES_X = range(3, 8)      # 45°V … 180°Ö
TILES_Y = range(0, 3)      # 90°N … 45°S
OUT = Path("data/glob")


# ---- minimal avkodare för Mapbox Vector Tiles (protobuf) ----
def varint(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 0x7F) << s; s += 7
        if c < 0x80:
            return r, i


def fields(b):
    i = 0
    while i < len(b):
        tag, i = varint(b, i)
        f, w = tag >> 3, tag & 7
        if w == 0:
            v, i = varint(b, i)
        elif w == 2:
            n, i = varint(b, i); v = b[i:i + n]; i += n
        elif w == 1:
            v = b[i:i + 8]; i += 8
        elif w == 5:
            v = b[i:i + 4]; i += 4
        else:
            raise ValueError(f"okänd typ {w}")
        yield f, w, v


def packed(b):
    out, i = [], 0
    while i < len(b):
        v, i = varint(b, i); out.append(v)
    return out


def zz(n):
    return (n >> 1) ^ -(n & 1)


def decode(tile):
    """Returnerar [(mitt-x, mitt-y, antal)] i rutans koordinater (0–extent)."""
    out = []
    for f, _, layer in fields(tile):
        if f != 3:
            continue
        keys, values, feats, extent = [], [], [], 4096
        for g, w, v in fields(layer):
            if g == 3: keys.append(v.decode())
            elif g == 4:
                val = None
                for h, hw, hv in fields(v):
                    val = hv if hw == 0 else (struct_double(hv) if hw == 1 else hv)
                values.append(val)
            elif g == 2: feats.append(v)
            elif g == 5: extent = v
        for feat in feats:
            tags, geom = [], []
            for g, w, v in fields(feat):
                if g == 2: tags = packed(v)
                elif g == 4: geom = packed(v)
            props = {keys[tags[k]]: values[tags[k + 1]] for k in range(0, len(tags), 2)}
            xs, ys, x, y, i = [], [], 0, 0, 0
            while i < len(geom):
                cmd, cnt = geom[i] & 7, geom[i] >> 3; i += 1
                if cmd in (1, 2):
                    for _ in range(cnt):
                        x += zz(geom[i]); y += zz(geom[i + 1]); i += 2
                        xs.append(x); ys.append(y)
            if xs:
                out.append(((min(xs) + max(xs)) / 2 / extent, (min(ys) + max(ys)) / 2 / extent, int(props.get("total", 0))))
    return out


def struct_double(b):
    import struct
    return struct.unpack("<d", b)[0]


def get_tile(m, tx, ty, key):
    req = urllib.request.Request(URL.format(z=Z, x=tx, y=ty, key=key, m=m), headers={"User-Agent": UA})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return m, tx, ty, r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):               # GBIF avvisar enstaka rutor över tomt hav; räkna dem som tomma
                return m, tx, ty, b""
            time.sleep(2 ** attempt); print(f"  fel ({e})", file=sys.stderr)
        except Exception as e:
            time.sleep(2 ** attempt); print(f"  fel ({e})", file=sys.stderr)
    raise RuntimeError("GBIF svarar inte")


def fetch(key):
    from concurrent.futures import ThreadPoolExecutor
    cells = defaultdict(lambda: [0] * 12)
    jobs = [(m, tx, ty) for m in range(1, 13) for tx in TILES_X for ty in TILES_Y]
    size = 360 / 2 ** (Z + 1)              # grader per kartruta (45 vid zoom 2)
    with ThreadPoolExecutor(4) as ex:
        for m, tx, ty, tile in ex.map(lambda j: get_tile(*j, key), jobs):
            for fx, fy, n in decode(tile):
                if not (0 <= fx < 1 and 0 <= fy < 1):
                    continue                       # buffert från grannrutan
                lon = -180 + (tx + fx) * size
                lat = 90 - (ty + fy) * size
                cells[(round(lat, 1), round(lon, 1))][m - 1] += n
    return cells


def main():
    arter = json.loads(Path("data/flock/arter.json").read_text())["arter"]
    keys = sys.argv[1:] or [a["key"] for a in arter]
    names = {a["key"]: a["namn"] for a in arter}
    OUT.mkdir(parents=True, exist_ok=True)
    for key in keys:
        cells = fetch(key)
        rows = [[lat, lon, v] for (lat, lon), v in sorted(cells.items())]
        (OUT / f"{key}.json").write_text(json.dumps({"key": int(key), "namn": names.get(key, key), "cells": rows},
                                                    ensure_ascii=False, separators=(",", ":")))
        tot = [sum(r[2][m] for r in rows) for m in range(12)]
        print(f"{names.get(key, key)}: {len(rows)} rutor, fynd per månad {tot}", file=sys.stderr)
    lst = [{"key": k, "namn": json.loads((OUT / f"{k}.json").read_text())["namn"]} for k in
           sorted({f.stem for f in OUT.glob('*.json') if f.stem.isdigit()}, key=lambda k: names.get(k, k))]
    (OUT / "arter.json").write_text(json.dumps({"arter": lst}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
