#!/usr/bin/env python3
"""
rapport_gallica_seul.py — Rapport de la passe contre Gallica seul (720, 726, 727) : filtre mécanique
compté, verdicts de relecture (faute, variante, ocr, douteux), corrections proposées NON appliquées,
rejouables par ocr_apply si Benoît les adopte (<id>-corrections-proposees.jsonl).

Usage : python3 rapport_gallica_seul.py 720 726 727
"""
import sys, os, json, re, subprocess, tempfile
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
        hp = f'{OUT}/{i}-hors-candidats.json'
        if os.path.exists(hp):          # fautes vues par le relecteur hors des candidats, reprises à part
            h = json.load(open(hp))
            L += ['', f'### Hors candidats ({len(h["verdicts"])})', '', h.get('origine', ''), '']
            for v in h['verdicts']:
                cc = v['correction']
                L.append(f'- {v["n"]} : {md(v["raison"])} — « {md(cc["chercher"])} » → « {md(cc["remplacer"])} »')
                props.append({**cc, 'raison': f'passe Gallica seul, hors candidats {v["n"]} — {v["raison"]}',
                              'source': 'passe contre Gallica seul — proposée, non appliquée', 'item': f'G-{v["n"]}'})
        if r.get('remarques'):
            L += ['', '## Remarques de relecture', ''] + [f'- {md(m)}' for m in r['remarques']]
        ecrit(f'{OUT}/{i}-corrections-proposees.jsonl', ''.join(json.dumps(p, ensure_ascii=False) + '\n' for p in props))
        # essai sur le volume livré (qui a déjà reçu la collation) : ce qui s'appliquerait tel quel
        T = {str(v['id']): v for v in json.load(open(f'{chemins.TOOLS}/examples/segur-collation/temoins-segur.json'))['volumes']}
        livre = f'{W}/sortie/Comtesse-de-Segur-{T[i]["slug"]}.epub'
        essai = ''
        if props and os.path.exists(livre):
            with tempfile.TemporaryDirectory() as tmp:
                r = subprocess.run([sys.executable, f'{chemins.TOOLS}/ocr_apply.py', livre, f'{tmp}/x.epub',
                                    f'{OUT}/{i}-corrections-proposees.jsonl', '--budget-pct', '1.5', '--max-edit', '16',
                                    '--insertion-max', '250', '--report', f'{tmp}/r.md'], capture_output=True, text=True)
                rep = open(f'{tmp}/r.md').read() if os.path.exists(f'{tmp}/r.md') else ''
            essai = (r.stdout.strip().splitlines() or ['?'])[0]
            rej = [l for l in rep.split('## Rejetées', 1)[1].splitlines() if l.startswith('- ')] if '## Rejetées' in rep else []
            L += ['', '## Essai sur le volume livré', '',
                  f'Essai d’application (sans rien écrire) des {len(props)} corrections proposées sur l’EPUB livré, qui a déjà reçu la '
                  f'collation : {essai}.' + (' Refusées (le passage a changé à la collation, ou recoupe une correction faite) :' if rej else '')]
            L += [f'- {md(x[2:])}' for x in rej]
        ecrit(f'{OUT}/{i}-rapport.md', '\n'.join(L) + '\n')
        print(i, dict(cnt), len(props), 'corrections proposées ;', essai)


if __name__ == '__main__':
    main()
