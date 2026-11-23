#!/usr/bin/env python3
"""Läser Svensk Fågeltaxerings populationsindex (standardrutterna) för arterna på /trend/.
Artlistan är data/trend/sft/arter.json (byggs av tools/sft_rutter.py packa).

Användning:
    python3 -I tools/sft_index.py <sökväg till populationsindex.xlsx>

Filen laddas ner från https://www.fageltaxering.lu.se/resultat/populationstrender-enskilda-arter
(Excel-filen "Populationsindex"). Den checkas inte in; bara siffrorna för våra arter sparas i
data/trend/sft/index.json:
    {"källa": …, "program": "Standardrutterna", "arter": {"Trana": {"years": [...], "index": [...]}}}
Index är satt till 1 det första året (1998) och beräknat med TRIM av Svensk Fågeltaxering.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

os.chdir(Path(__file__).resolve().parent.parent)
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
SHEET = "Standardrutter"


def read_sheet(path, name):
    """Läser ett blad ur en xlsx-fil utan tillägg: lista av rader som {kolumn: värde}."""
    z = zipfile.ZipFile(path)
    shared = [''.join(t.text or '' for t in si.iter(f"{{{NS['m']}}}t"))
              for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)]
    names = [s.get("name") for s in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS)]
    root = ET.fromstring(z.read(f"xl/worksheets/sheet{names.index(name) + 1}.xml"))
    rows = []
    for r in root.iter(f"{{{NS['m']}}}row"):
        row = {}
        for c in r.findall("m:c", NS):
            v = c.find("m:v", NS)
            if v is not None:
                row[re.match(r"[A-Z]+", c.get("r")).group()] = shared[int(v.text)] if c.get("t") == "s" else v.text
        rows.append(row)
    return rows


def main():
    rows = read_sheet(sys.argv[1], SHEET)
    head = rows[0]
    year_cols = [(c, int(h)) for c, h in head.items() if h.isdigit()]
    wanted = {a["namn"] for a in json.loads(Path("data/trend/sft/arter.json").read_text())["arter"]}
    out = {}
    for r in rows[1:]:
        if r.get("B") in wanted:
            pts = [(y, float(r[c])) for c, y in year_cols if r.get(c) not in (None, "")]
            out[r["B"]] = {"years": [y for y, _ in pts], "index": [round(v, 4) for _, v in pts]}
    Path("data/trend/sft/index.json").write_text(json.dumps({
        "källa": "Svensk Fågeltaxering, Lunds universitet (fageltaxering.lu.se), populationsindex",
        "program": "Standardrutterna", "arter": out}, ensure_ascii=False, indent=1))
    print(f"Index för {len(out)} av {len(wanted)} arter: {', '.join(sorted(out))}")


if __name__ == "__main__":
    main()
