#!/usr/bin/env python3
"""
rapport_gallica_seul.py — Rapport de la passe contre Gallica seul (720, 726, 727) : filtre mécanique
compté, verdicts de relecture (faute, variante, ocr, douteux), corrections proposées NON appliquées,
rejouables par ocr_apply si Benoît les adopte (<id>-corrections-proposees.jsonl).

Usage : python3 rapport_gallica_seul.py 720 726 727
"""
import sys, os, json, re
from collections import Counter
import chemins

W = chemins.W
OUT = f'{chemins.OUT}/propositions/gallica-seul'
NN = '\u202f'
LIB = {'faute': 'faute de la copie', 'variante': 'variante d’édition', 'ocr': 'lecture de l’OCR', 'douteux': 'douteux'}


def md(s):
    return (s or '').replace('|', '\\|').replace('\n', ' ')


def tx(x):
    x = re.sub(r' ([,.])', r'\1', x or '')
    x = re.sub(r' ([;:!?])', NN + r'\1', x)
    return re.sub(r" ?([’']) ?", '’', x)


def ecrit(p, s):
    with open(p + '.tmp', 'w') as f:
        f.write(s)
    os.replace(p + '.tmp', p)


def main():
    tot = {}
    for i in sys.argv[1:]:
        c = json.load(open(f'{OUT}/{i}-candidats.json'))
        rp = f'{W}/revue/{i}-gallica-seul.json'
        r = json.load(open(rp)) if os.path.exists(rp) else {'verdicts': [], 'remarques': []}
        ver = {v['n']: v for v in r['verdicts']}
        cnt = Counter(v['verdict'] for v in ver.values())
        cnt['non jugé'] = sum(1 for x in c['candidats'] if x['n'] not in ver)
        tot[i] = (c, cnt)
        L = [f'# Passe contre Gallica seul — *{c["titre"].replace(chr(39), "’")}* ({i})', '',
             f'Témoin : Gallica, {c["edition"]}, https://gallica.bnf.fr/ark:/12148/{c["ark"]} — seul témoin indépendant de la copie '
             'pour ce volume (la transcription Wikisource y reprend en partie le texte Gutenberg de la copie).', '',
             '**Rien n’est appliqué.** Les corrections proposées sont rejouables (`' + f'{i}-corrections-proposees.jsonl' + '`) si tu les adoptes.', '',
             '## Filtre mécanique', '', '| Étape | Sites |', '|---|---:|']
        for k, n in c['filtre'].items():
            L.append(f'| {k[2:]} | {n} |')
        L += ['', '## Verdicts de relecture', '', '| Verdict | Candidats |', '|---|---:|']
        for k in ('faute', 'variante', 'ocr', 'douteux', 'non jugé'):
            if cnt[k]:
                L.append(f'| {LIB.get(k, k)} | {cnt[k]} |')
        props = []
        for k in ('faute', 'douteux', 'variante', 'ocr'):
            sel = [x for x in c['candidats'] if ver.get(x['n'], {}).get('verdict') == k]
            if not sel:
                continue
            L += ['', f'### {LIB[k].capitalize()} ({len(sel)})', '', '| # | Vue | Contexte (copie) | Copie | Gallica | Raison |', '|---:|---|---|---|---|---|']
            for x in sel:
                v = ver[x['n']]
                vl = f'[{x["vue"]}](https://gallica.bnf.fr/ark:/12148/{c["ark"]}/f{x["vue"]}.item)' if x['vue'] else '—'
                rs = md(v.get('raison', '')) + (' (image vue)' if v.get('image') else '')
                if k == 'douteux' and v.get('question'):
                    rs += f' — **question** : {md(v["question"])}'
                if k == 'faute' and v.get('correction'):
                    cc = v['correction']
                    rs += f' — « {md(cc["chercher"])} » → « {md(cc["remplacer"])} »'
                    props.append({**cc, 'raison': f'passe Gallica seul, candidat {x["n"]} (vue {x["vue"]}) — {v.get("raison", "")}',
                                  'source': 'passe contre Gallica seul — proposée, non appliquée', 'item': f'G-{x["n"]:03d}'})
                L.append(f'| {x["n"]} | {vl} | …{md(x["avant"][-45:])} | {md(x["copie"]) or "∅"} | {md(tx(x["gallica"])) or "∅"} | {rs} |')
        if r.get('remarques'):
            L += ['', '## Remarques de relecture', ''] + [f'- {md(m)}' for m in r['remarques']]
        ecrit(f'{OUT}/{i}-rapport.md', '\n'.join(L) + '\n')
        ecrit(f'{OUT}/{i}-corrections-proposees.jsonl', ''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in props))
        print(i, dict(cnt), len(props), 'corrections proposées')


if __name__ == '__main__':
    main()
