#!/usr/bin/env python3
"""
integre_arbitrages.py — Verse dans la chaîne (revue/<id>-complements.json) les corrections que Benoît
a adoptées le 19/09/2026, pour que l'application les rejoue avec toutes les autres, tracées :
  - 725 : E-09 « morte » → « moree » (sabir de Georgey), question tranchée ;
  - 720, 726, 727 : les fautes de la passe contre Gallica seul qui ne sont pas déjà dans le volume
    livré (items E-Gnnn) ; 727 : le cas douteux n° 241, tranché pour 1866.
Chaque passage cité est retrouvé, unique, dans la copie source (restauration de juin).
Idempotent : relancer remplace les items E-G… et E-09 sans doublon.
"""
import sys, re, json, os, zipfile
import chemins
sys.path.insert(0, chemins.TOOLS)
import collate

W = chemins.W
P = f'{chemins.OUT}/propositions/gallica-seul'
SAMPLES = chemins.SAMPLES
T = {str(v['id']): v for v in json.load(open(f'{chemins.TOOLS}/examples/segur-collation/temoins-segur.json'))['volumes']}
DATE = 'tranché par Benoît le 19/09/2026'


def norm(x):
    return re.sub(r'[\s  ]+', ' ', x)


def textes(epub):
    toks, segs = collate.extract_epub(epub)
    return {d: norm(' '.join(s for s in ss if s)) for d, ss in segs.items()}


def trouve(tx, chercher):
    n = norm(chercher)
    return [d for d, t in tx.items() if t.count(n) == 1] if all(t.count(n) <= 1 for t in tx.values()) else []


def ecrit(p, obj):
    with open(p + '.tmp', 'w') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(p + '.tmp', p)


def complements(i):
    p = f'{W}/revue/{i}-complements.json'
    return p, (json.load(open(p)) if os.path.exists(p) else {'volume': int(i), 'origine': '', 'items': []})


def main():
    # 725 : « moree »
    p, c = complements('725')
    src = textes(f'{SAMPLES}/Comtesse-de-Segur-{T["725"]["slug"]}.epub')
    ch = 'Master Bonarde, morte pour la honte de Fridric'
    d = trouve(src, ch)
    assert len(d) == 1, d
    for x in c['items']:
        if x['item'] == 'E-09':
            x.update({'decision': 'corriger', 'correction': {'doc': d[0], 'chercher': ch, 'remplacer': ch.replace('morte', 'moree')},
                      'raison': x.get('raison', '') + f' — {DATE} : « Rétablir « moree » », leçon des deux éditions, parler du personnage.'})
            x.pop('question', None)
    ecrit(p, c)
    print('725 E-09 → corriger')
    # 720, 726, 727 : passe contre Gallica seul
    for i in ('720', '726', '727'):
        p, c = complements(i)
        c['items'] = [x for x in c['items'] if not x['item'].startswith('E-G')]
        src = textes(f'{SAMPLES}/Comtesse-de-Segur-{T[i]["slug"]}.epub')
        livre = textes(f'{W}/sortie/Comtesse-de-Segur-{T[i]["slug"]}.epub')
        props = [json.loads(l) for l in open(f'{P}/{i}-corrections-proposees.jsonl') if l.strip()]
        if i == '727':
            props.append({'doc': None, 'chercher': 'monsieur Jackson ; amusez-vous bien, grand',
                          'remplacer': 'monsieur Jackson ; amusez bien grand', 'item': 'G-241',
                          'raison': 'passe Gallica seul, candidat 241 (vue 256) — image : « amusez bien grand…. » (1866) : Natasha, '
                                    'interrompue, demande à Jackson d’amuser grand-père ; ' + DATE + ' : « Rétablir 1866 ».'})
        n_new = n_old = 0
        for q in props:
            ch = q['chercher'].replace(' ;', ' ;').replace(' :', ' :') if q['item'] == 'G-241' else q['chercher']
            if not trouve(livre, ch):
                n_old += 1                   # déjà faite par la collation (le passage a changé dans le livré)
                continue
            d = trouve(src, ch)
            if len(d) != 1:
                print(i, q['item'], 'introuvable ou multiple dans la source', d)
                continue
            rp = q['remplacer'].replace(' ;', ' ;').replace(' :', ' :') if q['item'] == 'G-241' else q['remplacer']
            c['items'].append({'item': f'E-{q["item"].replace("-", "")}', 'decision': 'corriger',
                               'correction': {'doc': d[0], 'chercher': ch, 'remplacer': rp},
                               'temoins': 'gallica (seul témoin indépendant)',
                               'raison': q['raison'] + ('' if DATE in q['raison'] else f' — {DATE} : « Oui, les 30 ».')})
            n_new += 1
        ecrit(p, c)
        print(i, n_new, 'compléments versés ;', n_old, 'déjà dans le livré')


if __name__ == '__main__':
    main()
