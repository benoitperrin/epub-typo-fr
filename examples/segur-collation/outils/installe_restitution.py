#!/usr/bin/env python3
"""installe_restitution.py 718 726 729 — Installe comme volume livré l'EPUB où les lacunes sont
restituées (propositions/lacunes/, décision de Benoît du 19/09/2026) : copie dans sortie/, puis
application/<id>.json porte la restitution (md5, epubcheck, rapport) pour que livre.py la livre et la
décrive. À relancer après chaque applique.py + restitue.py du volume."""
import sys, os, json, shutil, hashlib, datetime
import chemins
W = chemins.W
PR = f'{chemins.OUT}/propositions/lacunes'
T = {str(v['id']): v for v in json.load(open(f'{chemins.TOOLS}/examples/segur-collation/temoins-segur.json'))['volumes']}
for i in sys.argv[1:]:
    slug = T[i]['slug']; base = f'Comtesse-de-Segur-{slug}'
    plan = json.load(open(f'{PR}/{i}-plan.json'))
    app_p = f'{W}/sortie/application/{i}.json'
    app = json.load(open(app_p))
    if plan['copie_md5'] != app.get('epub_md5') and app.get('restitution', {}).get('base_md5') != plan['copie_md5']:
        sys.exit(f'{i} : la restitution a été construite sur un autre EPUB que le livré ; relancer restitue.py {i}')
    shutil.copy(f'{PR}/{base}.restitution.epub', f'{W}/sortie/{base}.epub')
    shutil.copy(f'{PR}/{base}.restitution.kepub.epub', f'{W}/sortie/{base}.kepub.epub')
    md5 = lambda p: hashlib.md5(open(p, 'rb').read()).hexdigest()
    app['restitution'] = {'decision': 'Benoît, 19/09/2026 : « Oui, les trois »', 'base_md5': plan['copie_md5'],
                          'passages': len(plan['lacunes']), 'mots': sum(l['mots'] for l in plan['lacunes']),
                          'rapport': f'propositions/lacunes/{i}-{slug}-restitution.md',
                          'chapitres': plan['resultat']['chapitres']}
    app['epub_md5'] = md5(f'{W}/sortie/{base}.epub')
    app['kepub_md5'] = md5(f'{W}/sortie/{base}.kepub.epub')
    app['epubcheck_apres'] = plan['resultat']['epubcheck']
    with open(app_p + '.tmp', 'w') as f:
        json.dump(app, f, ensure_ascii=False, indent=1)
    os.replace(app_p + '.tmp', app_p)
    print(i, 'installé :', app['restitution']['passages'], 'passages,', app['restitution']['mots'], 'mots ; md5', app['epub_md5'])
