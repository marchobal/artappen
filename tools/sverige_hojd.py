#!/usr/bin/env python3
"""Gör en liten höjdkarta över Sverige för landskapet (/trend/landskap.html).

Användning:
    python3 -I tools/sverige_hojd.py <tom mapp för rutorna>

Höjden kommer från AWS Terrain Tiles (Mapzen, Terrarium-format), zoomnivå 6, ungefär 1–2 km per
bildpunkt. Rutorna sparas i mappen man anger; bara den färdiga höjdkartan checkas in:
    data/sverige_hojd.json  {"w", "h", "x0", "y0", "x1", "y1", "m": [höjd i meter, rad för rad från norr]}
x/y är Web Mercator 0–1, samma som kartorna. Källor och villkor:
https://github.com/tilezen/joerd/blob/master/docs/attribution.md
"""
import json
import math
import os
import struct
import sys
import time
import urllib.request
import zlib
from pathlib import Path

os.chdir(Path(__file__).resolve().parent.parent)
URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
UA = "ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib"
Z = 6
W = 240                                   # höjdkartans bredd i punkter


def merc(lat, lon):
    la = math.radians(lat)
    return (lon + 180) / 360, (1 - math.log(math.tan(la) + 1 / math.cos(la)) / math.pi) / 2


X0, Y0 = merc(69.06, 10.95)
X1, Y1 = merc(55.33, 24.17)


def read_png(data):
    """Avkodar en 8-bitars RGB/RGBA-PNG utan tillägg. Returnerar (bredd, höjd, kanaler, rader)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        n, typ = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if typ == b"IHDR":
            w, h, depth, color = struct.unpack(">IIBB", body[:10])
            assert depth == 8 and color in (2, 6), "bara 8-bitars RGB/RGBA"
            ch = 3 if color == 2 else 4
        elif typ == b"IDAT":
            idat += body
        pos += 12 + n
    raw, stride, rows, prev = zlib.decompress(idat), w * ch, [], bytearray(w * ch)
    for r in range(h):
        f, line = raw[r * (stride + 1)], bytearray(raw[r * (stride + 1) + 1:(r + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - ch] if i >= ch else 0
            b, c = prev[i], prev[i - ch] if i >= ch else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c; pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line); prev = line
    return w, h, ch, rows


def main():
    cache = Path(sys.argv[1]); cache.mkdir(parents=True, exist_ok=True)
    n = 2 ** Z
    tx0, tx1 = int(X0 * n), int(X1 * n)
    ty0, ty1 = int(Y0 * n), int(Y1 * n)
    tiles = {}
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            f = cache / f"{Z}_{tx}_{ty}.png"
            if not f.exists():
                req = urllib.request.Request(URL.format(z=Z, x=tx, y=ty), headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    f.write_bytes(r.read())
                time.sleep(0.2)
            tiles[(tx, ty)] = read_png(f.read_bytes())
    print(f"{len(tiles)} rutor", file=sys.stderr)

    H = round(W * (Y1 - Y0) / (X1 - X0))
    out = []
    for j in range(H):
        my = Y0 + (j + 0.5) / H * (Y1 - Y0)
        for i in range(W):
            mx = X0 + (i + 0.5) / W * (X1 - X0)
            tx, ty = int(mx * n), int(my * n)
            w, h, ch, rows = tiles[(tx, ty)]
            px = min(w - 1, int((mx * n - tx) * w)); py = min(h - 1, int((my * n - ty) * h))
            r, g, b = rows[py][px * ch:px * ch + 3]
            out.append(max(0, round(r * 256 + g + b / 256 - 32768)))   # havet blir 0
    Path("data/sverige_hojd.json").write_text(json.dumps({
        "w": W, "h": H, "x0": X0, "y0": Y0, "x1": X1, "y1": Y1, "m": out,
        "källa": "AWS Terrain Tiles (Mapzen/Tilezen), bl.a. SRTM, GMTED och ETOPO1"}, separators=(",", ":")))
    print(f"Höjdkarta {W}×{H}, högsta punkt {max(out)} m", file=sys.stderr)


if __name__ == "__main__":
    main()
