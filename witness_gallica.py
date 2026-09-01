#!/usr/bin/env python3
"""
witness_gallica.py — Récupère l'OCR d'un document Gallica page par page via l'API
publique ALTO (RequestDigitalElement), puis le convertit en texte témoin.

Pourquoi ALTO et pas `texteBrut` : `texteBrut` est servi derrière une vérification
anti-robot (ALTCHA) ; l'API ALTO répond directement, avec en prime la structure
(blocs, césures résolues, légendes et pieds de page identifiés).

Usage :
  python3 witness_gallica.py fetch bpt6k6577498m dossier/ [--pause 2] [--from 1] [--to N]
  python3 witness_gallica.py text dossier/ temoin-gallica.txt

Le dossier reçoit pagination.xml + une page ALTO par vue (p0001.xml…). Reprise
idempotente : les vues déjà présentes ne sont pas retéléchargées. Le texte de sortie
contient un marqueur « #### vue N » par page (tolérés par collate.py, jamais alignés).
Merci de respecter Gallica : une requête toutes les deux secondes par défaut.
"""
import sys, os, re, time, html, argparse, urllib.request

UA = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/128.0 Safari/537.36 epub-typo-fr/collation')


def get(url, timeout=90):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503, 502, 500):
                time.sleep(30 * (attempt + 1))
                continue
            return e.code, b''
        except Exception:
            time.sleep(10 * (attempt + 1))
    return 0, b''


def fetch(ark, d, pause, p_from, p_to):
    os.makedirs(d, exist_ok=True)
    pag = os.path.join(d, 'pagination.xml')
    if not os.path.exists(pag):
        st, x = get(f'https://gallica.bnf.fr/services/Pagination?ark={ark}')
        if st != 200 or b'<nbVueImages>' not in x:
            sys.exit(f'pagination indisponible pour {ark} (HTTP {st})')
        open(pag, 'wb').write(x)
        time.sleep(pause)
    n = int(re.search(rb'<nbVueImages>(\d+)', open(pag, 'rb').read()).group(1))
    p_to = min(p_to or n, n)
    todo = [p for p in range(p_from, p_to + 1)
            if not os.path.exists(os.path.join(d, f'p{p:04d}.xml'))]
    print(f'{ark} : {n} vues, {len(todo)} à récupérer', flush=True)
    for k, p in enumerate(todo, 1):
        st, x = get(f'https://gallica.bnf.fr/RequestDigitalElement?O={ark}&E=ALTO&Deb={p}')
        if st == 200 and b'<alto' in x:
            open(os.path.join(d, f'p{p:04d}.xml'), 'wb').write(x)
        elif st == 404:
            open(os.path.join(d, f'p{p:04d}.xml'), 'wb').write(b'')   # vue sans OCR
        else:
            print(f'  vue {p} : HTTP {st}, on passe', flush=True)
        if k % 25 == 0:
            print(f'  {k}/{len(todo)}', flush=True)
        time.sleep(pause)
    print(f'{ark} : terminé', flush=True)


SKIP_PARAMS = ('caption', 'footer', 'header', 'pagenum', 'page number', 'running')


def coverage_blocks(x):
    """Blocs de la section CoverageInfo : (hpos, vpos, w, h, type, params)."""
    out = []
    for m in re.finditer(r'<BLOCK\s+([^>]*)/?>', x):
        a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        try:
            out.append((int(a['HPOS']), int(a['VPOS']), int(a['WIDTH']), int(a['HEIGHT']),
                        a.get('Type', ''), a.get('ProcParams', '')))
        except (KeyError, ValueError):
            pass
    return out


def overlap(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    w = min(ax + aw, bx + bw) - max(ax, bx)
    h = min(ay + ah, by + bh) - max(ay, by)
    return max(0, w) * max(0, h)


def page_text(x):
    blocks = coverage_blocks(x)
    paras = []
    for tb in re.finditer(r'<TextBlock\b([^>]*)>(.*?)</TextBlock>', x, re.S):
        a = dict(re.findall(r'(\w+)="([^"]*)"', tb.group(1)))
        try:
            box = (int(a['HPOS']), int(a['VPOS']), int(a['WIDTH']), int(a['HEIGHT']))
        except (KeyError, ValueError):
            box = None
        if box and blocks:
            best = max(blocks, key=lambda b: overlap(box, b[:4]))
            if overlap(box, best[:4]) > 0 and any(s in best[5].lower() for s in SKIP_PARAMS):
                continue
        lines = []
        for tl in re.finditer(r'<TextLine\b[^>]*>(.*?)</TextLine>', tb.group(2), re.S):
            words = []
            for s in re.finditer(r'<String\b([^>]*)/?>', tl.group(1)):
                sa = dict(re.findall(r'(\w+)="([^"]*)"', s.group(1)))
                c = html.unescape(sa.get('CONTENT', ''))
                st = sa.get('SUBS_TYPE', '')
                if st == 'HypPart1':
                    c = html.unescape(sa.get('SUBS_CONTENT', c))
                elif st == 'HypPart2':
                    continue
                if c:
                    words.append(c)
            if words:
                lines.append(' '.join(words))
        t = ' '.join(lines).strip()
        # bruit résiduel : folios seuls, titres courants en capitales
        if not t or re.fullmatch(r'[\divxlcIVXLC.\- ]+', t):
            continue
        if len(t) < 60 and t == t.upper() and re.search(r'[A-ZÉÈ]{4,}', t):
            continue
        paras.append(t)
    return paras


def to_text(d, out):
    pages = sorted(f for f in os.listdir(d) if re.fullmatch(r'p\d{4}\.xml', f))
    chunks, n_par = [], 0
    for f in pages:
        x = open(os.path.join(d, f), encoding='utf-8', errors='replace').read()
        if not x:
            continue
        paras = page_text(x)
        if not paras:
            continue
        n_par += len(paras)
        chunks.append(f'#### vue {int(f[1:5])}\n\n' + '\n\n'.join(paras))
    with open(out, 'w') as fo:
        fo.write('\n\n'.join(chunks) + '\n')
    print(f'{len(pages)} vues, {n_par} blocs de texte → {out}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['fetch', 'text'])
    ap.add_argument('a'); ap.add_argument('b')
    ap.add_argument('--pause', type=float, default=2.0)
    ap.add_argument('--from', dest='p_from', type=int, default=1)
    ap.add_argument('--to', dest='p_to', type=int, default=0)
    args = ap.parse_args()
    if args.cmd == 'fetch':
        fetch(args.a, args.b, args.pause, args.p_from, args.p_to)
    else:
        to_text(args.a, args.b)


if __name__ == '__main__':
    main()
