"""Bygger en jämförelsesida för friläggning och 8-bitarsfigurer: lab/pixel/index.html"""
import html, json, os, sys

root = sys.argv[1] if len(sys.argv) > 1 else 'lab/pixel'
# Uppgifter per art (src/<slug>.json); arter utan uppgifter visas ändå, utan fotografnamn
slugs = sorted({f[:-7] for f in os.listdir(f'{root}/out') if f.endswith('-16.png')})
meta = [json.load(open(f'{root}/src/{s}.json')) if os.path.exists(f'{root}/src/{s}.json')
        else {'slug': s, 'swe': s.capitalize(), 'sci': '', 'page': '#', 'artist': '(uppgifter saknas än)', 'license': ''} for s in slugs]
rows = []
for m in meta:
    s = m['slug']
    if not os.path.exists(f'{root}/out/{s}-16.png'):
        continue
    pj = json.load(open(f'{root}/out/{s}-palette.json'))
    pal = pj.get('full') or pj.get('16', [])
    total = sum(p[3] for p in pal) or 1
    # Bredd efter andel, men minst 8 % så att små accentfärger (steglitsens röda) syns
    swatch = ''.join(f'<i title="{100 * p[3] / total:.1f} %" style="background:rgb({p[0]},{p[1]},{p[2]});flex:{max(p[3] / total, 0.08):.3f}"></i>' for p in pal)
    rows.append(f'''
  <section>
    <h2>{html.escape(m['swe'])} <em>{html.escape(m['sci'])}</em></h2>
    <div class="row">
      <figure><img class="photo" src="src/{s}.jpg" alt=""><figcaption>Foto</figcaption></figure>
      <figure class="chk"><img class="cut" src="out/{s}-cutout.png" alt=""><figcaption>Friläggning</figcaption></figure>
      <figure class="chk"><img class="px" src="out/{s}-24.png" alt=""><figcaption>24 × 24</figcaption></figure>
      <figure class="chk"><img class="px" src="out/{s}-16.png" alt=""><figcaption>16 × 16</figcaption></figure>
      <figure><div class="small"><img src="out/{s}-16.png" alt=""><img src="out/{s}-24.png" alt=""></div><figcaption>Ikonstorlek</figcaption></figure>
      <figure><div class="swatch">{swatch}</div><figcaption>Färgschema</figcaption></figure>
    </div>
    <p class="credit">Foto: <a href="{html.escape(m['page'])}">{html.escape(m['artist'])}</a> · {html.escape(m['license'])} · Wikimedia Commons.
      Friläggning och pixelfigur är bearbetningar under samma licens.</p>
  </section>''')

page = f'''<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pixelfåglar – test</title>
<style>
  :root {{ --bg:#f6f5f1; --card:#fff; --text:#1d1f1c; --muted:#6b6f68; --line:#e3e1da; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141613; --card:#1d201c; --text:#ecebe6; --muted:#9a9e96; --line:#2e322d; }} }}
  body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.4 -apple-system, BlinkMacSystemFont, sans-serif; }}
  main {{ max-width:1100px; margin:0 auto; padding:16px; }}
  h1 {{ font-size:1.2rem; }} .lead {{ color:var(--muted); max-width:70ch; }}
  section {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px 14px; margin:12px 0; }}
  h2 {{ font-size:1rem; margin:0 0 8px; }} h2 em {{ color:var(--muted); font-weight:400; }}
  .row {{ display:flex; flex-wrap:wrap; gap:14px; align-items:flex-end; }}
  figure {{ margin:0; text-align:center; }} figcaption {{ font-size:.75rem; color:var(--muted); margin-top:4px; }}
  .photo {{ height:120px; border-radius:8px; }}
  .cut {{ height:120px; }}
  .px {{ width:120px; height:120px; image-rendering:pixelated; }}
  .chk {{ background:repeating-conic-gradient(#8881 0 25%, transparent 0 50%) 0 0/16px 16px; border-radius:8px; padding:4px; }}
  .small {{ display:flex; gap:8px; align-items:flex-end; height:120px; }}
  .small img {{ width:32px; height:32px; image-rendering:pixelated; }}
  .swatch {{ display:flex; width:180px; height:28px; border-radius:6px; overflow:hidden; }}
  .credit {{ font-size:.72rem; color:var(--muted); margin:8px 0 0; }} .credit a {{ color:inherit; }}
</style></head><body><main>
<h1>Test: frilagda fåglar och 8-bitarsfigurer</h1>
<p class="lead">Foton från Wikimedia Commons, frilagda med macOS inbyggda motivigenkänning och sedan nerskalade
till 24×24 och 16×16 pixlar med ett färgschema som räknas från den frilagda bilden (så att små accentfärger kommer med), mättade färger och en mörk kontur. Inget AI-genererat – färgerna kommer från fotot.</p>
{''.join(rows)}
</main></body></html>'''
open(f'{root}/index.html', 'w').write(page)
print(f'{len(rows)} arter → {root}/index.html')
