#!/usr/bin/env python3
"""
complements_depuis_remarques.py — Reprend en compléments tracés les corrections que le relecteur a
proposées dans ses remarques, sous la forme
« (n) contexte : ws « … », gallica « … » ; [id-doc] chercher « … » → remplacer « … ». »
Chaque passage est retrouvé dans la copie (espaces fines et retours à la ligne tolérés) et doit y
être unique. Usage : python3 complements_depuis_remarques.py <id> [--douteux 12,13] [--origine "…"]
"""
import sys, re, json, difflib, argparse
import chemins
sys.path.insert(0, chemins.TOOLS)
import collate

W = chemins.W
S = r'[\s \xa0]'


def norm(x):
    return re.sub(r'[ \n \xa0]+', ' ', x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('id')
    ap.add_argument('--douteux', default='')
    ap.add_argument('--origine', default='relevé par le relecteur hors items (accord des témoins masqué, ou faute commune à ws et à la copie que gallica tranche)')
    args = ap.parse_args()
    T = {str(v['id']): v for v in json.load(open(f'{chemins.TOOLS}/examples/segur-collation/temoins-segur.json'))['volumes']}
    ep = f'{chemins.SAMPLES}/Comtesse-de-Segur-{T[args.id]["slug"]}.epub'
    toks, segments = collate.extract_epub(ep)
    docs = {}
    for d in segments:
        m = re.search(r'(\d+-(?:h|8)-\d+)', d)
        if m:
            docs[m.group(1)] = d
    R = json.load(open(f'{W}/revue/{args.id}-revue.json'))
    douteux = set(args.douteux.split(',')) if args.douteux else set()
    rx = (r'\((\w+)\)' + S + r'(.*?)\[([\w-]+)\]' + S + r'chercher' + S + r'«' + S + r'*(.*?)' + S + r'*»' + S
          + r'→' + S + r'remplacer' + S + r'«' + S + r'*(.*?)' + S + r'*»')
    out = []
    for txt in R.get('remarques', []):
        for m in re.finditer(rx, txt):
            num, ctx, dk, ch, rp = m.groups()
            doc = docs.get(dk)
            if not doc:
                print('✗ document inconnu', num, dk)
                continue
            pat = r'[ \n \xa0]*'.join(re.escape(w) for w in re.split(r'(?<=\S) (?=\S)', norm(ch)))
            pat = r'[ \n \xa0]+'.join(re.escape(w) for w in norm(ch).split(' '))
            hits = [(j, mm) for j, t in enumerate(segments[doc]) for mm in re.finditer(pat, t)]
            if len(hits) != 1:
                print('✗', num, len(hits), repr(ch))
                continue
            j, mm = hits[0]
            actual = mm.group(0)
            b = norm(rp)
            sm = difflib.SequenceMatcher(None, norm(actual), b, autojunk=False)
            new = ''.join(actual[i1:i2] if op == 'equal' else b[j1:j2] for op, i1, i2, j1, j2 in sm.get_opcodes())
            new = re.sub(r' ([?!;:])', ' \\1', new).replace("'", '’')
            if new == actual:
                print('✗ sans changement', num)
                continue
            out.append({'item': f'E-{num}', 'decision': 'corriger',
                        'correction': {'doc': doc, 'chercher': actual, 'remplacer': new},
                        'temoins': ctx.strip().rstrip(';').strip(),
                        'raison': args.origine + ' ; repris par l’orchestrateur'
                                  + (' ; jugé douteux par le relecteur, tranché selon la doctrine du 05/09' if num in douteux else '')})
            print(out[-1]['item'], repr(actual[:60]), '→', repr(new[:60]))
    json.dump({'volume': int(args.id), 'origine': 'remarques du relecteur, reprises mécaniquement par l’orchestrateur',
               'items': out}, open(f'{W}/revue/{args.id}-complements.json', 'w'), ensure_ascii=False, indent=1)
    print(len(out), 'compléments')


if __name__ == '__main__':
    main()
