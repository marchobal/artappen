#!/usr/bin/env python3
"""Plockar ut flyttfåglarna ur Svenska djur och skriver artlistan för /flytt/.

Användning:
    python3 -I tools/flyttfaglar.py [~/Svenska djur/data] [data/flock/arter.json]

Styrdokumentet är Svenska djurs data: alla-arter.json (alla 254 fåglar) och
artfilerna med fältet "flytt" (kortflytt, långflytt eller vinterfågel) och
"gbifNycklar". Arter med kortflytt eller långflytt kommer med. Arter som
saknar flyttstatus listas, så att man ser vad som återstår att fylla i.
"""
import json
import sys
from pathlib import Path

src = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / "Svenska djur" / "data")
out = Path(sys.argv[2] if len(sys.argv) > 2 else "data/flock/arter.json")

alla = json.loads((src / "alla-arter.json").read_text())["arter"]
status = {}
for f in sorted(src.glob("*.json")):
    d = json.loads(f.read_text())
    for a in d.get("arter", []) if isinstance(d, dict) else []:
        if a.get("flytt") and a.get("gbifNycklar"):
            status[a["namn"]] = a

arter = []
for a in alla:
    s = status.get(a["namn"])
    if s and s["flytt"] in ("kortflytt", "långflytt"):
        arter.append({"key": str(s["gbifNycklar"][0]), "namn": a["namn"], "latin": a["latin"],
                      "nummer": a["nummer"], "flytt": s["flytt"],
                      "data": (out.parent / f"{s['gbifNycklar'][0]}.json").exists()})

saknas = [a["namn"] for a in alla if a["namn"] not in status]
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"källa": "Svenska djur (alla-arter.json och artfilerna)", "arter": arter},
                          ensure_ascii=False, indent=1))
print(f"{len(arter)} flyttfåglar skrivna till {out}")
print(f"{len(status) - len(arter)} vinterfåglar, {len(saknas)} arter saknar flyttstatus")
