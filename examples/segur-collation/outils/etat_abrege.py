#!/usr/bin/env python3
"""
etat_abrege.py — État chiffré d'une copie abrégée (721, Les Vacances) : chapitre par chapitre
(sous-pages Wikisource), mots du témoin complet, mots présents dans la copie, mots absents (en
lacunes de plus de 60 jetons, ou en coupes plus courtes), nombre de coupes ; puis la liste des
passages absents avec leurs vues Gallica. Écrit etat.json et etat.md dans le dossier de sortie.

Usage : python3 etat_abrege.py 721 [--out dossier]
"""
import sys, os, re, json, argparse
from collections import defaultdict, Counter
import chemins
sys.path.insert(0, chemins.TOOLS)
sys.path.insert(0, f'{chemins.W}/outils')
import collate
from restitue import ws_paragraphs, ws_tokens, vol_info, CONV, vue_de, fmt

W = chemins.W


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('id')
    ap.add_argument('--out', default=f'{chemins.OUT}/propositions/721-abrege')
    a = ap.parse_args()
    v = vol_info(a.id)
    toks, segs = collate.extract_epub(f'{chemins.SAMPLES}/Comtesse-de-Segur-{v["slug"]}.epub')
    A = collate.aligned(toks)
    paras = ws_paragraphs(f'{W}/ws/{a.id}.txt')
    Wt = ws_tokens(paras, CONV.get(a.id, {'ponct_label': '.'}))
    G = collate.aligned(collate.load_witness(f'{W}/gallica/{v["gallica"]["ark"]}.txt'))
    gal = collate.Alignment(Wt, G, collate.align(Wt, G))
    ops = collate.align(A, Wt)
    etat = defaultdict(Counter)
    coupes = []
    titres = {}
    for p in paras:
        if p['chap'] not in titres and p['nature'] == 'corps' and p['texte'].isupper():
            titres[p['chap']] = p['texte'].rstrip('.').capitalize()
    for t in Wt:
        if t.kind == 'w':
            etat[t.mark]['ws'] += 1
    for op, i1, i2, j1, j2 in ops:
        mots = [t for t in Wt[j1:j2] if t.kind == 'w']
        if op == 'equal':
            for t in mots:
                etat[t.mark]['present'] += 1
            continue
        if op in ('insert', 'replace') and len(mots) >= 8 and (i2 - i1) <= max(3, (j2 - j1) // 10):
            for t in mots:
                etat[t.mark]['absent'] += 1
            chap = Counter(t.mark for t in mots).most_common(1)[0][0]
            etat[chap]['coupes'] += 1
            vs = sorted({vue_de(g) for j in range(j1, j2) if not gal.uncovered[j]
                         for g in G[gal.jstart[j]:gal.jend[j]] if vue_de(g)})
            debut = ' '.join(t.s for t in Wt[j1:j1 + 14])
            coupes.append({'chap': chap, 'mots': len(mots), 'vues': [vs[0], vs[-1]] if vs else None,
                           'copie_avant': ' '.join(t.s for t in A[max(0, i1 - 8):i1]), 'debut': debut,
                           'fin': ' '.join(t.s for t in Wt[max(j1, j2 - 10):j2])})
        else:
            for t in mots:
                etat[t.mark]['present'] += 1      # divergences mot à mot : relevées par la collation
    tot = Counter()
    for c in etat.values():
        tot.update(c)
    res = {'volume': a.id, 'titre': v['titre'], 'chapitres': [{'chap': k, 'titre': titres.get(k, ''), **etat[k]} for k in etat],
           'total': dict(tot), 'coupes': coupes}
    os.makedirs(a.out, exist_ok=True)
    with open(f'{a.out}/etat.json.tmp', 'w') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    os.replace(f'{a.out}/etat.json.tmp', f'{a.out}/etat.json')
    for c in res['chapitres']:
        print(c['chap'], c['titre'][:30], c.get('ws', 0), c.get('present', 0), c.get('absent', 0), c.get('coupes', 0))
    print('total', dict(tot), len(coupes), 'coupes ≥ 8 mots')


if __name__ == '__main__':
    main()
