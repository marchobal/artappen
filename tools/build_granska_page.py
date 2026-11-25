#!/usr/bin/env python3
"""Bygger en lätt, tillfällig granskningssida i appen: granska/index.html med små bilder.

Samma kort som lab/pixel/index.html (foto, friläggning, 24 × 24, 16 × 16, färgschema) men utan
lokal server: OK och ÄNDRA sparas hos mellanservern (POST /granska, kräver nyckeln), och Macen hämtar
svaren med tools/hamta_granskning.py. Att byta bild görs på Macen i den vanliga granskningen.

Nyckeln ges en gång i länken: .../granska/#nyckel=… och sparas sedan i telefonen.

Användning:  python3 -I tools/build_granska_page.py      (tas bort ur appen när granskningen är klar)
"""
import html, json, os, subprocess

ROOT = os.path.abspath('lab/pixel')
OUT = os.path.abspath('granska')
IMG = os.path.join(OUT, 'img')
os.makedirs(IMG, exist_ok=True)
esc = lambda t: html.escape(str(t or ''))
load = lambda p, d: json.load(open(p)) if os.path.exists(p) else d

slugs = sorted({f[:-7] for f in os.listdir(f'{ROOT}/out') if f.endswith('-16.png')})
meta = [json.load(open(f'{ROOT}/src/{s}.json')) for s in slugs if os.path.exists(f'{ROOT}/src/{s}.json')]
meta.sort(key=lambda m: -(m.get('obs') or 10**9))  # vanligast först
reviews, flags = load(f'{ROOT}/reviews.json', {}), load(f'{ROOT}/flags.json', {})


def small(src, dst, h, fmt):
    """Krymper en bild till höjden h (bara om källan är nyare än den förra kopian)."""
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return
    subprocess.run(['sips', '-s', 'format', fmt, *(['-s', 'formatOptions', '70'] if fmt == 'jpeg' else []),
                    '--resampleHeight', str(h), src, '--out', dst], check=True, capture_output=True)


# friläggningarna läggs på grå bakgrund som JPEG (PNG med genomskinlighet blir fyra gånger större)
FLAT = os.path.join(ROOT, '.bin', 'flatten')
if not os.path.exists(FLAT) or os.path.getmtime(FLAT) < os.path.getmtime('tools/flatten.swift'):
    subprocess.run(['swiftc', '-O', 'tools/flatten.swift', '-o', FLAT], check=True)
todo = [f'{ROOT}/out/{m["slug"]}-cutout.png' for m in meta
        if not os.path.exists(f'{IMG}/{m["slug"]}-cutout.jpg')
        or os.path.getmtime(f'{IMG}/{m["slug"]}-cutout.jpg') < os.path.getmtime(f'{ROOT}/out/{m["slug"]}-cutout.png')]
for i in range(0, len(todo), 100):
    subprocess.run([FLAT, '220', IMG, *todo[i:i + 100]], check=True)

cards, palettes = [], {}
for nr, m in enumerate(meta, 1):
    s = m['slug']
    small(f'{ROOT}/src/{s}.jpg', f'{IMG}/{s}.jpg', 220, 'jpeg')
    for n in (16, 24):  # pixelfigurerna är redan små
        subprocess.run(['cp', f'{ROOT}/out/{s}-{n}.png', f'{IMG}/{s}-{n}.png'], check=True)
    p = load(f'{ROOT}/out/{s}-palette.json', {})
    palettes[s] = p.get('full') or p.get('16') or []
    cards.append(f'''
<section class="card" data-slug="{s}">
  <header><span class="nr">{nr}.</span> <b>{esc(m['swe'])}</b> <em>{esc(m['sci'])}</em>
    <span class="flag"></span><span class="status"></span></header>
  <div class="row">
    <figure><img loading="lazy" class="photo" src="img/{s}.jpg" alt=""><figcaption>Foto</figcaption></figure>
    <figure><img loading="lazy" class="cut" src="img/{s}-cutout.jpg" alt=""><figcaption>Friläggning</figcaption></figure>
    <figure class="chk"><img loading="lazy" class="px" src="img/{s}-24.png" alt=""><figcaption>24 × 24</figcaption></figure>
    <figure class="chk"><img loading="lazy" class="px" src="img/{s}-16.png" alt=""><figcaption>16 × 16</figcaption></figure>
    <figure><div class="swatch"></div><figcaption>Färgschema</figcaption></figure>
  </div>
  <p class="credit">Foto: <a href="{esc(m['page'])}" target="_blank" rel="noopener">{esc(m['artist'])}</a> · {esc(m['license'])} · Wikimedia Commons</p>
  <div class="actions"><button class="ok">OK</button><button class="change">ÄNDRA</button></div>
  <div class="panel" hidden>
    <label>Vad vill du ändra?<textarea placeholder="T.ex. fel färger, vill ha en hane, fel art …"></textarea></label>
    <div class="panelbtns"><button class="save primary">Spara kommentar</button></div>
    <p class="note">Andra bilder att välja bland finns i granskningen på Macen.</p>
  </div>
</section>''')

data = json.dumps({'reviews': reviews, 'flags': flags, 'palettes': palettes}, ensure_ascii=False, separators=(',', ':'))
page = '''<!doctype html>
<html lang="sv"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Granska fågelbilder · Artappen</title>
<style>
  :root { --bg:#f6f5f1; --card:#fff; --text:#1d1f1c; --muted:#6b6f68; --line:#e3e1da; --accent:#2f6b3a; --warn:#b4530a; --bad:#b3261e; }
  @media (prefers-color-scheme: dark) { :root { --bg:#141613; --card:#1d201c; --text:#ecebe6; --muted:#9a9e96; --line:#2e322d; --accent:#7fc28b; --warn:#f0a35e; --bad:#f2827a; } }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:15px/1.4 -apple-system, BlinkMacSystemFont, sans-serif; }
  main { max-width:1100px; margin:0 auto; padding:0 12px 40px; }
  .top { position:sticky; top:0; z-index:10; background:var(--bg); padding:calc(env(safe-area-inset-top) + 10px) 0 10px; border-bottom:1px solid var(--line); margin-bottom:12px; }
  h1 { font-size:1.15rem; margin:0 0 4px; } h1 a { color:var(--muted); font-size:.85rem; font-weight:400; margin-left:8px; }
  .progress { color:var(--muted); font-size:.85rem; margin-bottom:8px; }
  .progress.bad { color:var(--bad); }
  .filters { display:flex; flex-wrap:wrap; gap:6px; }
  button { font:inherit; padding:6px 12px; border-radius:9px; border:1px solid var(--line); background:var(--card); color:var(--text); cursor:pointer; }
  button.on, button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px 14px; margin:12px 0; }
  .card.is-ok { border-color:var(--accent); } .card.is-change { border-color:var(--warn); }
  header { margin-bottom:8px; } header em { color:var(--muted); } .nr { color:var(--muted); }
  .flag:not(:empty) { margin-left:8px; font-size:.8rem; color:#fff; background:var(--bad); border-radius:6px; padding:1px 7px; }
  .status:not(:empty) { margin-left:6px; font-size:.8rem; border-radius:6px; padding:1px 7px; border:1px solid currentColor; }
  .is-ok .status { color:var(--accent); } .is-change .status { color:var(--warn); }
  .row { display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; }
  figure { margin:0; text-align:center; } figcaption { font-size:.72rem; color:var(--muted); margin-top:3px; }
  .photo, .cut { height:110px; border-radius:8px; }
  .px { width:72px; height:72px; image-rendering:pixelated; }
  .chk { background:repeating-conic-gradient(#8881 0 25%, transparent 0 50%) 0 0/14px 14px; border-radius:8px; padding:4px; }
  .swatch { display:flex; width:150px; height:26px; border-radius:6px; overflow:hidden; }
  .credit { font-size:.72rem; color:var(--muted); margin:6px 0; } .credit a { color:inherit; }
  .actions { display:flex; gap:8px; } .actions button { min-width:80px; padding:8px 14px; }
  .card.is-ok .ok { background:var(--accent); color:#fff; border-color:var(--accent); }
  .card.is-change .change { background:var(--warn); color:#fff; border-color:var(--warn); }
  .panel { margin-top:10px; padding-top:10px; border-top:1px dashed var(--line); }
  .panel label { display:block; font-size:.85rem; color:var(--muted); }
  textarea { display:block; width:100%; min-height:56px; margin-top:4px; font:inherit; font-size:16px; padding:8px; border-radius:8px;
             border:1px solid var(--line); background:var(--bg); color:var(--text); }
  .panelbtns { display:flex; gap:8px; margin:8px 0; }
  .note { color:var(--muted); font-size:.8rem; margin:0; }
  .hidden { display:none; }
</style></head><body><main>
<div class="top">
  <h1>Granska fågelbilder <a href="../">Till appen</a></h1>
  <div class="progress" id="progress">Hämtar granskningen …</div>
  <div class="filters" id="filters">
    <button data-f="todo" class="on">Ej granskade</button>
    <button data-f="flagged">Mina anmärkningar</button>
    <button data-f="change">Ändra</button>
    <button data-f="ok">OK</button>
    <button data-f="all">Alla</button>
  </div>
</div>
''' + ''.join(cards) + '''
</main>
<script>
const API = 'https://artappen-api.marchobal.workers.dev/granska';
const DATA = ''' + data + ''';
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
// nyckeln kommer en gång i länken (#nyckel=…) och sparas sedan i telefonen
const m = location.hash.match(/nyckel=([\\w-]+)/);
if (m) { localStorage.setItem('artappen.granskaNyckel', m[1]); history.replaceState(null, '', location.pathname); }
const KEY = localStorage.getItem('artappen.granskaNyckel');
let reviews = { ...DATA.reviews }, filter = 'todo';
const flags = DATA.flags;

function swatch(card) {
  const cols = DATA.palettes[card.dataset.slug] || [], total = cols.reduce((a, c) => a + c[3], 0) || 1;
  card.querySelector('.swatch').innerHTML = cols.map(c => `<i style="background:rgb(${c[0]},${c[1]},${c[2]});flex:${Math.max(c[3] / total, 0.08)}"></i>`).join('');
}
function paint(card) {
  const s = card.dataset.slug, r = reviews[s] || {};
  card.classList.toggle('is-ok', r.status === 'ok');
  card.classList.toggle('is-change', r.status === 'change');
  card.querySelector('.status').textContent = r.status === 'ok' ? 'OK' : r.status === 'change' ? 'Ändra' : '';
  card.querySelector('.flag').textContent = flags[s] || '';
  const ta = card.querySelector('textarea');
  if (document.activeElement !== ta) ta.value = r.note || '';
  const show = filter === 'all' || (filter === 'flagged' && flags[s]) || (filter === 'todo' && !r.status)
            || (filter === 'change' && r.status === 'change') || (filter === 'ok' && r.status === 'ok');
  card.classList.toggle('hidden', !show);
}
function progress(msg) {
  const el = document.getElementById('progress');
  if (msg) { el.textContent = msg; el.classList.add('bad'); return; }
  const cards = $$('.card'), vals = cards.map(c => reviews[c.dataset.slug]?.status);
  const ok = vals.filter(v => v === 'ok').length, ch = vals.filter(v => v === 'change').length;
  el.classList.remove('bad');
  el.textContent = `${ok + ch} av ${cards.length} granskade · ${ok} OK · ${ch} att ändra`;
}
async function setReview(card, status) {
  const s = card.dataset.slug, note = card.querySelector('textarea').value;
  if (!KEY) { progress('Nyckeln saknas: öppna sidan via länken med #nyckel=… en gång.'); return; }
  const before = reviews[s];
  reviews[s] = { ...before, status, note };   // visa direkt, ångra om det inte gick att spara
  paint(card); progress();
  try {
    const r = await fetch(API, { method: 'POST', headers: { 'content-type': 'application/json', 'x-nyckel': KEY }, body: JSON.stringify({ slug: s, status, note }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.fel || r.status);
    reviews[s] = d; paint(card); progress();
  } catch (e) {
    reviews[s] = before; paint(card); progress('Kunde inte spara: ' + e.message);
  }
}
document.addEventListener('click', e => {
  const card = e.target.closest('.card'); if (!card) return;
  if (e.target.matches('.ok')) { card.querySelector('.panel').hidden = true; setReview(card, 'ok'); }
  if (e.target.matches('.change')) { const p = card.querySelector('.panel'); p.hidden = !p.hidden; if (!p.hidden) p.querySelector('textarea').focus(); }
  if (e.target.matches('.save')) { card.querySelector('.panel').hidden = true; setReview(card, 'change'); }
});
document.getElementById('filters').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  filter = b.dataset.f; $$('#filters button').forEach(x => x.classList.toggle('on', x === b));
  $$('.card').forEach(paint); window.scrollTo(0, 0);
};
$$('.card').forEach(c => { swatch(c); paint(c); });
progress();
fetch(API).then(r => r.ok ? r.json() : Promise.reject()).then(d => { Object.assign(reviews, d); $$('.card').forEach(paint); progress(); })
  .catch(() => progress('Kunde inte hämta granskningen just nu.'));
</script>
</body></html>'''
open(f'{OUT}/index.html', 'w').write(page)
size = sum(os.path.getsize(os.path.join(IMG, f)) for f in os.listdir(IMG))
print(f'{len(cards)} arter → {OUT}/index.html, bilder {size / 1e6:.1f} MB')
