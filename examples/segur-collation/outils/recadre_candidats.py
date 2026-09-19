#!/usr/bin/env python3
"""recadre_candidats.py 720 726 727 : pour chaque candidat de la passe Gallica seul, découpe dans
l'image Gallica (IIIF) la ligne ALTO qui porte la leçon (et une ligne autour) ; une requête toutes
les 5 s, reprise sans refaire ce qui est là. Images : $SEGUR_WORKDIR/crops/<id>/<n>.jpg"""
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


for vol in sys.argv[1:]:
    d = json.load(open(f'{chemins.OUT}/propositions/gallica-seul/{vol}-candidats.json'))
    ark = d['ark']
    os.makedirs(f'{chemins.W}/crops/{vol}', exist_ok=True)
    for c in d['candidats']:
        out = f'{chemins.W}/crops/{vol}/{c["n"]}.jpg'
        if os.path.exists(out) or not c.get('vue'):
            continue
        L = lignes(ark, c['vue'])
        ctx = [w for w in re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)*", c['avant'])][-2:]
        cibles = [collate.key(c['gallica'].strip())] if c['gallica'].strip() else []
        cibles.append(collate.key(' '.join(ctx)))
        k = None
        for cible in cibles:
            k = next((i for i, l in enumerate(L) if cible and cible in l[4]), None)
            if k is not None:
                break
        if k is None and ctx:
            k = next((i for i, l in enumerate(L) if collate.key(ctx[-1]) in l[4]), None)
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
            if os.path.exists(out + '.tmp'):
                os.remove(out + '.tmp')
            if r.stdout == '429':
                time.sleep(60)
        time.sleep(5)
    print(vol, 'fini', flush=True)
print('TERMINÉ', flush=True)
