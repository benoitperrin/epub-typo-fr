#!/usr/bin/env python3
"""recadre_candidats.py 720 726 727 : pour chaque candidat de la passe Gallica seul, découpe dans
l'image Gallica (IIIF) la ligne ALTO qui porte la leçon (et une ligne autour) ; une requête toutes
les 5 s, reprise sans refaire ce qui est là. Images : $SEGUR_WORKDIR/crops/<id><suffixe>/<n>.jpg
(--suffixe=-v2 : nouveau dossier, la ligne située par le contexte et non par la leçon seule)."""
import sys, os, re, json, html, subprocess, time
import chemins
sys.path.insert(0, chemins.TOOLS)
import collate
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'


def lignes(ark, vue):
    b = open(f'{chemins.W}/gallica/{ark}/p{vue:04d}.xml', 'rb').read()
    try:
        s = b.decode('utf-8')
    except UnicodeDecodeError:
        s = b.decode('iso-8859-1')
    out = []
    for m in re.finditer(r'<TextLine\b([^>]*)>(.*?)</TextLine>', s, re.S):
        at = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
        words = [html.unescape(x) for x in re.findall(r'<String\b[^>]*CONTENT="([^"]*)"', m.group(2))]
        out.append((int(at['HPOS']), int(at['VPOS']), int(at['WIDTH']), int(at['HEIGHT']),
                    collate.key(' '.join(words))))
    return out


def mots(x):
    return [collate.key(t[0]) for t in collate.tokenize_text(x or '') if t[1] == 'w']


def ligne_du_candidat(L, c):
    """Ligne de la page qui porte la leçon : on cherche la suite « fin du contexte + leçon (+ début de
    la suite) » dans les mots de la page, de la plus longue à la plus courte ; la leçon seule (un
    mot court comme « à ») ne suffit jamais à situer la ligne."""
    page = [(k, i) for i, l in enumerate(L) for k in mots(l[4])]
    keys = [k for k, _ in page]
    av, g, ap = mots(c['avant']), mots(c['gallica']), mots(c['apres'])
    essais = [(av[-3:], g, ap[:1]), (av[-3:], g, []), (av[-2:], g, ap[:2]), (av[-2:], g, []),
              ([], g, ap[:3]), (av[-4:], [], []), (av[-3:], [], []), ([], [], ap[:4])]
    for a, b, c_ in essais:
        seq = a + b + c_
        if len(seq) < 3:
            continue
        for x in range(len(keys) - len(seq) + 1):
            if keys[x:x + len(seq)] == seq:
                return page[x + len(a)][1] if b else page[min(x + len(seq) - 1, len(page) - 1)][1]
    return None


suffixe = ''
args = sys.argv[1:]
if args and args[0].startswith('--suffixe='):
    suffixe, args = args[0].split('=', 1)[1], args[1:]
for vol in args:
    d = json.load(open(f'{chemins.OUT}/propositions/gallica-seul/{vol}-candidats.json'))
    ark = d['ark']
    dossier = f'{chemins.W}/crops/{vol}{suffixe}'
    os.makedirs(dossier, exist_ok=True)
    for c in d['candidats']:
        out = f'{dossier}/{c["n"]}.jpg'
        if os.path.exists(out) or not c.get('vue'):
            continue
        L = lignes(ark, c['vue'])
        k = ligne_du_candidat(L, c)
        if k is None:
            print(vol, c['n'], 'ligne introuvable', flush=True)
            continue
        sel = L[max(0, k - 1):k + 2]
        x = min(l[0] for l in sel) - 10; y = min(l[1] for l in sel) - 8
        x2 = max(l[0] + l[2] for l in sel) + 10; y2 = max(l[1] + l[3] for l in sel) + 8
        url = f'https://gallica.bnf.fr/iiif/ark:/12148/{ark}/f{c["vue"]}/{max(0, x)},{max(0, y)},{x2 - x},{y2 - y}/full/0/native.jpg'
        r = subprocess.run(['curl', '-s', '-m', '40', '-A', UA, '-o', out + '.tmp', '-w', '%{http_code}', url],
                           capture_output=True, text=True)
        if r.stdout == '200':
            os.replace(out + '.tmp', out)
        else:
            print(vol, c['n'], 'HTTP', r.stdout, flush=True)
            if r.stdout == '429':
                time.sleep(60)
        time.sleep(5)
    print(vol, 'fini', flush=True)
print('TERMINÉ', flush=True)
