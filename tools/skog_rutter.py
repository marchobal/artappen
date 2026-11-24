#!/usr/bin/env python3
"""Hur gick det för fåglarna där det höggs mycket skog, jämfört med där det höggs lite?

Användning:
    python3 -I tools/skog_rutter.py

Läser data/skog/forlust.png (tools/skog_forlust.swift, Hansen m.fl.) och Svensk Fågeltaxerings
standardrutter (data/trend/sft/). Skriver data/trend/skog.json.

Metod
- Runt varje rutt (fönster på ±R km) räknas skogsandelen år 2000 och hur stor del av skogen som
  huggits 2001–2025. Hansens pixlar är ~0,6 km och oftast bara delvis huggna, så mängden räknas om
  till en andel på samma sätt som i landskapet.
- Bara skogsrutter (minst SKOG av marken skog) är med.
- För att norr och söder inte ska blandas ihop delas rutterna i BAND lika stora breddgradsband.
  Inom varje band jämförs halvan med mest avverkning mot halvan med minst.
- Varje arts förändring i en grupp = log(antal sent / antal tidigt), där tidigt = TIDIGT och sent = SENT,
  summerat över rutter som räknats minst två år i båda perioderna.
- Bara typiska skogsfåglar (SKOGSARTER). Skillnaden (mycket − lite) vägs ihop över banden.
  Osäkerheten skattas med bootstrap över rutter; "tydlig" = 95 %-intervallet ligger helt på ena sidan om noll.
Detta visar samvariation, inte orsak.
"""
import json
import math
import random
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R_KM = 3.0                 # fönstrets halva sida; en standardrutt är en kvadrat på 2 × 2 km
SKOG = 0.4
BAND = 4
TIDIGT, SENT = range(2001, 2007), range(2020, 2026)
# Typiska skogsfåglar: arter som främst häckar i skog. Listan är handplockad, eftersom skogsandelen runt
# rutterna är hög nästan överallt och inte skiljer skogsfåglar från andra (kanadagås fick mer "skog" än lavskrika).
SKOGSARTER = {
    # barrskog och taiga
    "Tjäder", "Orre", "Järpe", "Lavskrika", "Lappmes", "Tretåig hackspett", "Talltita", "Tofsmes", "Svartmes",
    "Kungsfågel", "Domherre", "Mindre korsnäbb", "Större korsnäbb", "Bändelkorsnäbb", "Tallbit", "Sidensvans",
    "Bergfink", "Videsparv", "Rödvingetrast", "Dubbeltrast", "Spillkråka", "Nötkråka", "Sparvuggla", "Pärluggla",
    "Slaguggla", "Lappuggla", "Hökuggla", "Duvhök", "Sparvhök", "Bivråk", "Morkulla", "Skogssnäppa",
    "Gransångare", "Trädkrypare", "Grönsiska", "Brandkronad kungsfågel",
    # skog i allmänhet och lövskog
    "Bofink", "Rödhake", "Taltrast", "Koltrast", "Gärdsmyg", "Järnsparv", "Lövsångare", "Trädpiplärka",
    "Grå flugsnappare", "Svartvit flugsnappare", "Mindre flugsnappare", "Rödstjärt", "Större hackspett",
    "Mindre hackspett", "Gråspett", "Nötväcka", "Entita", "Stjärtmes", "Svarthätta", "Trädgårdssångare",
    "Nötskrika", "Skogsduva", "Stenknäck", "Göktyta", "Kattuggla",
}
MIN_RUTTER = 25            # arten ska finnas på minst så många av de jämförda rutterna
BOOT = 1000


def read_png(path):
    """Läser PNG:n som skog_forlust.swift skriver: RGB, 8 bitar, filter Sub på varje rad."""
    b = path.read_bytes()
    pos, idat, w, h = 8, b"", None, None
    while pos < len(b):
        n = int.from_bytes(b[pos:pos + 4], "big"); t = b[pos + 4:pos + 8]; body = b[pos + 8:pos + 8 + n]
        if t == b"IHDR":
            w, h = int.from_bytes(body[:4], "big"), int.from_bytes(body[4:8], "big")
            assert body[8] == 8 and body[9] == 2, "väntade RGB med 8 bitar"
        elif t == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    stride = w * 3
    out = bytearray(h * stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        row = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        assert f in (0, 1), f"oväntat filter {f}"
        if f == 1:
            for x in range(3, stride):
                row[x] = (row[x] + row[x - 3]) & 255
        out[y * stride:(y + 1) * stride] = row
    return w, h, out


def merc(lat, lon):
    la = math.radians(lat)
    return (lon + 180) / 360, (1 - math.log(math.tan(la) + 1 / math.cos(la)) / math.pi) / 2


def main():
    w, h, px = read_png(ROOT / "data/skog/forlust.png")
    (x0, y0), (x1, y1) = merc(69.06, 10.95), merc(55.33, 24.17)
    rutter = json.loads((ROOT / "data/trend/sft/rutter.json").read_text())
    years = rutter["years"]
    surveyed = [set(s) for s in rutter["surveyed"]]

    # ---- skog och avverkning runt varje rutt ----
    info = []
    for idx, (rid, lat, lon) in enumerate(rutter["routes"]):
        mx, my = merc(lat, lon)
        cx, cy = (mx - x0) / (x1 - x0) * w, (my - y0) / (y1 - y0) * h
        km_per_px = (x1 - x0) * 40075 * math.cos(math.radians(lat)) / w
        k = max(1, round(R_KM / km_per_px))
        tot = forest = 0
        cut = 0.0
        for yy in range(int(cy) - k, int(cy) + k + 1):
            for xx in range(int(cx) - k, int(cx) + k + 1):
                if not (0 <= xx < w and 0 <= yy < h):
                    continue
                o = (yy * w + xx) * 3
                tot += 1
                if px[o + 2] > 127:
                    forest += 1
                if px[o]:
                    cut += min(1.0, (px[o + 1] / 255 + 0.03) * 1.5)
        info.append({"idx": idx, "lat": lat, "skog": forest / tot if tot else 0,
                     "hugget": cut / forest if forest else 0})

    # rutter som räknats minst två år i båda perioderna
    def ok(idx):
        e = sum(1 for y in TIDIGT if y in years and idx in surveyed[years.index(y)])
        l = sum(1 for y in SENT if y in years and idx in surveyed[years.index(y)])
        return e >= 2 and l >= 2
    skogsrutter = [r for r in info if r["skog"] >= SKOG and ok(r["idx"])]
    skogsrutter.sort(key=lambda r: r["lat"])
    bands = [skogsrutter[i * len(skogsrutter) // BAND:(i + 1) * len(skogsrutter) // BAND] for i in range(BAND)]
    for b in bands:
        b.sort(key=lambda r: r["hugget"])
        half = len(b) // 2
        for r in b[:half]:
            r["grupp"] = "lite"
        for r in b[half:]:
            r["grupp"] = "mycket"
    hi = [r["hugget"] for r in skogsrutter if r.get("grupp") == "mycket"]
    lo = [r["hugget"] for r in skogsrutter if r.get("grupp") == "lite"]
    print(f"{len(skogsrutter)} skogsrutter. Huggen andel av skogen: mycket {sum(hi)/len(hi):.0%}, lite {sum(lo)/len(lo):.0%}")

    # ---- arternas förändring ----
    def period_mean(c, idx, period):
        v = [(c[years.index(y)] or 0) for y in period if y in years and idx in surveyed[years.index(y)]]
        return sum(v) / len(v)

    def effect(band_rows):
        """Vägd skillnad i log-förändring mellan mycket och lite, över banden."""
        num = den = 0.0
        for rows in band_rows:
            s = {"mycket": [0.0, 0.0], "lite": [0.0, 0.0]}
            for g, e, l in rows:
                s[g][0] += e; s[g][1] += l
            if min(s["mycket"][0] + s["mycket"][1], s["lite"][0] + s["lite"][1]) < 3:
                continue
            d = math.log((s["mycket"][1] + 0.5) / (s["mycket"][0] + 0.5)) - math.log((s["lite"][1] + 0.5) / (s["lite"][0] + 0.5))
            wgt = sum(e + l for _, e, l in rows)
            num += d * wgt; den += wgt
        return num / den if den else None

    random.seed(1)
    arter = json.loads((ROOT / "data/trend/sft/arter.json").read_text())["arter"]
    result = {}
    for a in arter:
        if a["namn"] not in SKOGSARTER:
            continue
        art = json.loads((ROOT / f"data/trend/sft/{a['key']}.json").read_text())
        counts = art["counts"]
        band_rows, present = [], 0
        for b in bands:
            rows = []
            for r in b:
                c = counts.get(str(r["idx"]))
                if c is None:
                    e = l = 0.0
                else:
                    e, l = period_mean(c, r["idx"], TIDIGT), period_mean(c, r["idx"], SENT)
                if e + l > 0:
                    present += 1
                rows.append((r["grupp"], e, l))
            band_rows.append(rows)
        if present < MIN_RUTTER:
            continue
        d = effect(band_rows)
        if d is None:
            continue
        boots = []
        for _ in range(BOOT):
            bd = effect([[random.choice(rows) for _ in rows] for rows in band_rows])
            if bd is not None:
                boots.append(bd)
        boots.sort()
        lo_ci, hi_ci = boots[int(len(boots) * 0.025)], boots[int(len(boots) * 0.975)]
        result[str(a["key"])] = {
            "namn": a["namn"], "rutter": present,
            "skillnad": round(math.exp(d) - 1, 3),           # t.ex. −0,30 = gick 30 % sämre där det höggs mycket
            "intervall": [round(math.exp(lo_ci) - 1, 3), round(math.exp(hi_ci) - 1, 3)],  # 95 %
            "tydlig": lo_ci > 0 or hi_ci < 0,
        }
    out = {
        "källa": "Svensk Fågeltaxering (standardrutter, CC0) och Hansen m.fl. Global Forest Change v1.13 (CC BY 4.0)",
        "metod": f"Skogsrutter (minst {SKOG:.0%} skog inom ±{R_KM:g} km), {BAND} breddgradsband, "
                 f"halvan med mest mot halvan med minst avverkning 2001–2025 inom varje band; "
                 f"förändring {TIDIGT[0]}–{TIDIGT[-1]} till {SENT[0]}–{SENT[-1]}; 95 % bootstrapintervall; bara typiska skogsfåglar.",
        "skogsrutter": len(skogsrutter),
        "hugget": {"mycket": round(sum(hi) / len(hi), 3), "lite": round(sum(lo) / len(lo), 3)},
        "arter": result,
    }
    (ROOT / "data/trend/skog.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(result)} arter, {sum(r['tydlig'] for r in result.values())} med tydlig skillnad")
    for k, r in sorted(result.items(), key=lambda kv: kv[1]["skillnad"]):
        mark = "*" if r["tydlig"] else " "
        print(f" {mark} {r['namn']:<24} {r['skillnad']:+.0%}  ({r['intervall'][0]:+.0%} – {r['intervall'][1]:+.0%})  {r['rutter']} rutter")


if __name__ == "__main__":
    main()
