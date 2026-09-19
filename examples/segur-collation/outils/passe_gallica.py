#!/usr/bin/env python3
"""
passe_gallica.py — Passe contre Gallica seul, pour les volumes où Wikisource dérive en partie de la
copie (720, 726, 727) : la collation y a classé en bruit les sites où Wikisource et la copie
s'accordent contre Gallica (un seul témoin contre deux leçons). On les reprend ici, sans rien
appliquer, pour y chercher les fautes communes à la copie et à Wikisource que Gallica corrige.

Filtre mécanique, du plus large au plus étroit (chaque étape comptée) :
  1. sites « témoin seul » où Wikisource suit la copie et Gallica diverge ;
  2. hors ponctuation seule, légendes (« Page N »), en-têtes, noms de locuteurs ;
  3. hors graphie (mêmes lettres : accents, casse, traits d'union, apostrophes) ;
  4. leçon de Gallica faite de mots connus du lexique (sinon : faute de lecture de l'OCR) ;
  5. lecture sûre : chaque mot de Gallica lu avec la confiance ALTO 1 sur sa vue.
Restent les candidats, à juger sur l'image de la vue (recadrage IIIF de la ligne ALTO).

Usage : python3 passe_gallica.py 726 [--out dossier]
"""
import sys, os, re, json, html, argparse
from collections import Counter
import chemins

sys.path.insert(0, chemins.TOOLS)
sys.path.insert(0, f'{chemins.W}/outils')
import collate
from restitue import Alto, vol_info

W = chemins.W
TOOLS = chemins.TOOLS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('id')
    ap.add_argument('--out', default=f'{chemins.OUT}/propositions/gallica-seul')
    args = ap.parse_args()
    i = args.id
    v = vol_info(i)
    ark = v['gallica']['ark']
    alto = Alto(ark)
    lex = collate.Lexicon(f'{TOOLS}/lexicon-fr.txt.gz', [])
    sites = json.load(open(f'{W}/collation-2026-09-16/{i}-sites.json'))
    cnt = Counter()
    cands = []
    for s in sites:
        if s.get('niveau') is not None or s.get('accord_nous') != ['ws']:
            continue
        g = (s.get('temoins') or {}).get('gallica')
        if g is None:
            continue
        cnt['1 témoin seul, ws = copie'] += 1
        gt = [t for t in collate.tokenize_text(g) if t[1] != 'x']
        nt = [t for t in collate.tokenize_text(s.get('nous') or '') if t[1] != 'x']
        gw = [t[0] for t in gt if t[1] == 'w']
        nw = [t[0] for t in nt if t[1] == 'w']
        if not gw and not nw:
            continue                                     # ponctuation seule
        if re.search(r'\bPa[gq]e?\s*\d', g) or any(t.isupper() and len(t) > 1 for t in gw + nw) \
                or any(re.fullmatch(r'[IVXLC]+', t) for t in gw + nw):
            continue                                     # légende, titre, numéro, locuteur en capitales
        if len(gw) + len(nw) > 12:
            continue                                     # bloc déplacé (légende, note) plutôt que leçon
        cnt['2 hors ponctuation, légendes, en-têtes'] += 1
        if collate.letters_only(''.join(nw)) == collate.letters_only(''.join(gw)):
            continue
        cnt['3 hors graphie'] += 1
        if not all(lex.known(w) for w in gw) or any(len(w) == 1 and w.lower() not in 'aày' for w in gw):
            continue
        cnt['4 leçon faite de mots connus'] += 1
        m = re.match(r'vue (\d+)', (s.get('marques') or {}).get('gallica') or '')
        vue = int(m.group(1)) if m else None
        sure = False
        if vue and gw:
            at = alto.page(vue)
            keys = [collate.key(w) for w in gw]
            for k in range(len(at) - len(keys) + 1):
                if [a[0] for a in at[k:k + len(keys)]] == keys and all(a[1] >= 1 for a in at[k:k + len(keys)]):
                    sure = True
                    break
        elif vue and not gw:
            sure = True                                  # mot absent de Gallica : pas de confiance à lire
        if not sure:
            continue
        cnt['5 lecture sûre (ALTO 1)'] += 1
        cands.append({'n': len(cands) + 1, 'doc': s['doc'], 'chap': s.get('chap'), 'vue': vue,
                      'copie': s.get('nous'), 'ws': s['temoins'].get('ws'), 'gallica': g,
                      'avant': (s.get('avant') or '')[-70:], 'apres': (s.get('apres') or '')[:50],
                      'image': f'https://gallica.bnf.fr/ark:/12148/{ark}/f{vue}.item' if vue else None})
    os.makedirs(args.out, exist_ok=True)
    res = {'volume': i, 'titre': v['titre'], 'ark': ark, 'edition': v['gallica']['edition'],
           'filtre': dict(sorted(cnt.items())), 'candidats': cands}
    p = f'{args.out}/{i}-candidats.json'
    with open(p + '.tmp', 'w') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    os.replace(p + '.tmp', p)
    print(i, dict(sorted(cnt.items())), '→', len(cands), 'candidats')


if __name__ == '__main__':
    main()
