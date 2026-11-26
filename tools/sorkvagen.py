#!/usr/bin/env python3
"""Packar data till flytt/sork.html: lappugglans fynd och SLU:s sork- och lämmelindex.

Indata (hämtade med GBIF:s API och från slu.se/mo-smagnagare):
  lapp.json    [[år, månad, dag, lat, lon, antal, observatör], …]  Artportalen via GBIF, lappuggla 2497522
  insats.json  {"55,60": {år: antal fågelfynd}, …}                  alla fågelfynd i Artportalen per breddgradsband
  vindeln.txt, ammarnas.txt   SLU:s fångstindex, utskrivna från Excelfilerna

Användning: python3 -I tools/sorkvagen.py lapp.json insats.json vindeln.txt ammarnas.txt data/sork/lappuggla.json
"""
import json, re, sys
from datetime import date

START = 2004  # första hösten som visas
GLAT, GLON = 0.02, 0.04


def slu(path):
    """{(år, årstid): [index …]} där årstid 1 = vår, 2 = höst."""
    out = {}
    for line in open(path):
        cells = dict(x.split('=', 1) for x in line.strip().split(' | ') if '=' in x)
        k = {re.sub(r'\d', '', a): v for a, v in cells.items()}
        try:
            y, s = int(k['A']), int(k['B'])
            out[(y, s)] = [float(k[c]) if k.get(c) else 0.0 for c in 'CDEFGHIJ']
        except (KeyError, ValueError):
            continue
    return out


def main():
    lapp, insats, vin, amm, dst = sys.argv[1:6]
    rows = json.load(open(lapp))
    eff = json.load(open(insats))['55,60']
    V, A = slu(vin), slu(amm)

    t0 = date(START, 7, 1)
    pts, seen = [], set()
    south = {}  # (år, månad) -> unika 10 km-rutor söder om 60° N
    for y, m, d, la, lo, *_ in rows:
        if not d or y < START: continue
        try: dd = date(y, m, d)
        except ValueError: continue
        t = (dd - t0).days
        if t < 0: continue
        key = (t, round(la / GLAT), round(lo / GLON))
        if key in seen: continue
        seen.add(key)
        pts.append((t, round(la, 2), round(lo, 2)))
        if la < 60:
            south.setdefault((y, m), set()).add((round(la / 0.1), round(lo / 0.2)))
    pts.sort()

    # lappugglor i söder per månad, per miljon fågelfynd i samma band (rapporteringen ökar över åren)
    months = []
    y, m = START, 7
    last = max(p[0] for p in pts)
    while (date(y, m, 15) - t0).days <= last:
        e = eff.get(str(y), 0) / 12
        n = len(south.get((y, m), ()))
        months.append(round(n / e * 1e6, 1) if e else 0)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    def series(S, cols):
        out = []
        for (y, s), v in sorted(S.items()):
            if y < START: continue
            t = (date(y, 5, 20 if s == 1 else 1) - t0).days if s == 1 else (date(y, 9, 20) - t0).days
            out.append([t, round(sum(v[i] for i in cols), 2)])
        return out

    data = {
        'start': t0.isoformat(),
        'lat': [p[1] for p in pts], 'lon': [p[2] for p in pts], 't': [p[0] for p in pts],
        'south': months,                       # en siffra per månad från juli START
        'sork': series(V, (0, 1, 2)),          # Vindeln: skogssork + gråsiding + åkersork
        'lammel': series(A, (6, 7)),           # Ammarnäs: fjällämmel + skogslämmel
        'source': 'Lappuggla: GBIF.org, Artportalen (SLU Artdatabanken), CC0. '
                  'Sork och lämmel: Ecke, F. och Hörnfeldt, B. (2026) Miljöövervakning av smågnagare, SLU.',
    }
    json.dump(data, open(dst, 'w'), separators=(',', ':'))
    print(len(pts), 'punkter,', len(months), 'månader,', len(data['sork']), 'sorkmätningar')


if __name__ == '__main__':
    main()
