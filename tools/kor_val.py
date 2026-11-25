#!/usr/bin/env python3
"""Byter foto för arterna i lab/pixel/cand/val.json och gör om friläggning och pixelfigur.

val.json: { slug: [vald kandidat, [fler kandidater för färgerna]] }  (kandidaterna från tools/hitta_bilder.py)
Den valda bilden hämtas i större storlek (1280 px) till lab/pixel/src/, med fotograf och licens.
Formen kommer från den valda bilden, färgschemat från den och de andra kandidaterna tillsammans.
Den gamla bilden sparas i lab/pixel/prev/. I granskningen blir arten ogranskad igen, med en anteckning.

Användning: python3 -I tools/kor_val.py [slug …]
"""
import json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.request

LAB = os.path.abspath('lab/pixel')
UA = {'User-Agent': 'ArtappenTools/1.1 (https://github.com/marchobal/artappen; privat artapp) python-urllib'}
BIN = os.path.join(LAB, '.bin', 'pixelate')


def get(url):
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                body = r.read()
            time.sleep(0.5)
            return body
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == 5: raise
            time.sleep(int(e.headers.get('Retry-After') or 0) or 5 * 2 ** attempt)


def main():
    val = json.load(open(f'{LAB}/cand/val.json'))
    slugs = sys.argv[1:] or list(val)
    os.makedirs(f'{LAB}/prev', exist_ok=True)
    reviews = json.load(open(f'{LAB}/reviews.json'))
    for n, s in enumerate(slugs, 1):
        main_id, extra = val[s]
        cands = {c['id']: c for c in json.load(open(f'{LAB}/cand/{s}.json'))['cand']}
        c = cands[main_id]
        # spara den gamla bilden en gång
        for ext in ('jpg', 'json'):
            if os.path.exists(f'{LAB}/src/{s}.{ext}') and not os.path.exists(f'{LAB}/prev/{s}.{ext}'):
                shutil.copy(f'{LAB}/src/{s}.{ext}', f'{LAB}/prev/{s}.{ext}')
        width = min(1280, c['w'])
        url = re.sub(r'/\d+px-', f'/{width}px-', c['thumb'])
        try:
            img = get(url)
        except Exception:
            img = get(c['thumb'])  # miniatyren finns alltid
        open(f'{LAB}/src/{s}.jpg', 'wb').write(img)
        meta = json.load(open(f'{LAB}/src/{s}.json'))
        meta.update({'file': c['file'], 'page': c['page'], 'artist': c['artist'], 'license': c['license'], 'licenseUrl': c['licenseUrl']})
        json.dump(meta, open(f'{LAB}/src/{s}.json', 'w'), ensure_ascii=False, indent=1)
        extras = [f'{LAB}/cand/{s}/{i}.jpg' for i in extra if os.path.exists(f'{LAB}/cand/{s}/{i}.jpg')]
        p = subprocess.run([BIN, f'{LAB}/src/{s}.jpg', f'{LAB}/out', '16,24', '8', *extras], capture_output=True, text=True)
        ok = p.returncode == 0
        old = reviews.get(s, {})
        reviews[s] = {'photo': c['file'], 'note': 'Ny bild, vald efter profil och ljus' + (f', färger från {1 + len(extras)} foton' if extras else '') + '.',
                      't': time.strftime('%Y-%m-%d %H:%M')}
        if old.get('status') == 'ok': reviews[s]['status'] = 'ok'
        json.dump(reviews, open(f'{LAB}/reviews.json', 'w'), ensure_ascii=False, indent=1)
        print(f'{n:3}/{len(slugs)} {meta["swe"]:<26} {"klar" if ok else "FEL: " + (p.stdout + p.stderr).strip()[:80]}', flush=True)


if __name__ == '__main__':
    main()
