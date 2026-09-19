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
        # déjà faites par la collation : celles que l'essai sur le volume livré d'avant les arbitrages a refusées
        # (« motif introuvable »), listées dans le rapport de la passe ; relancer ce script ne change donc rien
        rapport = open(f'{P}/{i}-rapport.md').read().split('## Essai sur le volume livré')[-1]
        refusees = set(re.findall(r'`([^`]+)` → `[^`]+` — motif introuvable', rapport))
        n_new = n_old = 0
        for q in props:
            ch = q['chercher'].replace(' ;', ' ;').replace(' :', ' :') if q['item'] == 'G-241' else q['chercher']
            if q['chercher'] in refusees:
                n_old += 1                   # déjà faite par la collation : refusée à l'essai sur le livré d'avant
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


def noms_729():
    """729 (décision du 19/09, « Noms et parler seulement ») : « Inkermann », « Bagnols » et le « Mamzelle » de
    Moutier, là seulement où les deux éditions s'accordent contre la copie (items E-Mnn)."""
    p, c = complements('729')
    c['items'] = [x for x in c['items'] if not x['item'].startswith('E-M')]
    src = textes(f'{SAMPLES}/Comtesse-de-Segur-{T["729"]["slug"]}.epub')
    sites = json.load(open(f'{W}/collation-2026-09-16/729-sites.json'))
    n = 0
    for x in sites:
        nous = x.get('nous') or ''
        m = re.search(r'Inkerman|Bagnoles|Mam’selle', nous)
        if not m:
            continue
        mot = m.group(0)
        nous = re.sub(r' ([,.])', r'\1', nous)
        nous = re.sub(r' ([;:!?])', ' \\1', nous)
        lec =[re.sub(r'[^\w’]', '', l.split()[0] if mot != 'Inkerman' or not l.startswith(('À', 'A ')) else l.split()[1])
               for l in (x['temoins'].get('ws') or '', x['temoins'].get('gallica') or '') if l]
        cible = {'Inkerman': 'inkermann', 'Bagnoles': 'bagnols', 'Mam’selle': 'mamzelle'}[mot]
        if len(lec) < 2 or any(l.lower() != cible for l in lec):
            continue                      # les éditions ne s'accordent pas sur la forme d'époque : on laisse
        neuf = lec[0]                     # casse de Wikisource (« mamzelle » ou « Mamzelle »)
        av, ap = (x.get('avant') or '')[-22:], (x.get('apres') or '')[:14]
        ch = (av + nous + ap).replace('\n', ' ')
        # le contexte « avant » peut porter des signes corrigés ailleurs : on retient le plus long passage unique
        for k in range(len(av), -1, -2):
            chk = (av[len(av) - k:] + nous + ap).replace('\n', ' ')
            d = trouve(src, chk)
            if len(d) == 1 and len(chk) >= 12:
                ch = chk
                break
        else:
            print('729', nous, 'contexte introuvable ou multiple :', repr(ch))
            continue
        rp = ch.replace(mot, neuf, 1)
        # une correction déjà versée qui couvre le même mot (ex. E-5 « après Inkerman, ils ») : on y porte le nom,
        # plutôt qu'une seconde correction au même point, que la fusion d'ocr_apply composerait mal (« Inkerman,n »)
        voisine = next((y for y in c['items'] if not y['item'].startswith('E-M') and y.get('correction')
                        and y['correction']['doc'] == d[0] and mot in y['correction']['chercher']
                        and norm(y['correction']['chercher']) in norm(ch) + norm(y['correction']['chercher'])
                        and (norm(nous) in norm(y['correction']['chercher']))
                        and any(w in norm(y['correction']['chercher']) for w in norm(ap).split()[:1] + norm(av).split()[-1:])), None)
        if voisine and neuf in voisine['correction']['remplacer']:
            continue                                    # déjà porté (relance du script)
        if voisine and mot in voisine['correction']['remplacer']:
            voisine['correction']['remplacer'] = voisine['correction']['remplacer'].replace(mot, neuf, 1)
            if DATE not in voisine['raison']:
                voisine['raison'] += f' ; nom rétabli selon les deux éditions (« {neuf} »), {DATE} : « Noms et parler seulement ».'
            print('729', voisine['item'], 'porte aussi', neuf)
            continue
        n += 1
        c['items'].append({'item': f'E-M{n:02d}', 'decision': 'corriger',
                           'correction': {'doc': d[0], 'chercher': ch, 'remplacer': rp},
                           'temoins': f'ws « {x["temoins"].get("ws")} » · gallica « {x["temoins"].get("gallica")} »',
                           'raison': f'forme des deux éditions (1876 et 1888) contre la copie remaniée ; {DATE} : « Noms et parler seulement ».'})
    ecrit(p, c)
    print('729', n, 'noms et formes de parler rétablis')


if __name__ == '__main__':
    main()
    noms_729()
