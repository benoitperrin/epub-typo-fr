#!/usr/bin/env python3
"""rapport_recompose.py 721 — Rapport de la recomposition (recompose.py) et installation comme volume
livré : sortie/<base>.epub et .kepub.epub, sortie/application/<id>.json (« recomposition »), rapport
propositions/721-abrege/<id>-recompose.md ; le volume sort de outils/attente.json."""
import sys, os, json, shutil, hashlib, re
from collections import Counter
import chemins
W = chemins.W
PR = f'{chemins.OUT}/propositions/721-abrege'
NN = '\u202f'
T = {str(v['id']): v for v in json.load(open(f'{chemins.TOOLS}/examples/segur-collation/temoins-segur.json'))['volumes']}


def fmt(n):
    return f'{n:,}'.replace(',', NN)


def md(s):
    return (s or '').replace('|', '\\|').replace('\n', ' ')


def tx(x):
    x = re.sub(r' ([,.])', r'\1', x or '')
    x = re.sub(r' ([;:!?])', NN + r'\1', x)
    return re.sub(r" ?([’']) ?", '’', x)


i = sys.argv[1]
v = T[i]; base = f'Comtesse-de-Segur-{v["slug"]}'
P = json.load(open(f'{PR}/{i}-recompose.json'))
dec = json.load(open(f'{PR}/{i}-decisions.json'))
ark = P['temoins']['gallica']['ark']; ws = P['temoins']['ws']
cnt = Counter(d['classe'] for d in P['divergences'])
L = [f'# *{v["titre"].replace(chr(39), "’")}* (721) — texte recomposé depuis Wikisource, contrôlé sur Gallica', '',
     f'- **Décision** : {P["decision"]} (la copie Gutenberg était un abrégé : 25 % du texte absent, voir `etat.md`).',
     f'- **Base** : Wikisource, « Les Vacances », {ws.get("Editeur")}, {ws.get("Annee")}, transcription relue.',
     f'- **Contrôle** : Gallica, {P["temoins"]["gallica"]["edition"]}, https://gallica.bnf.fr/ark:/12148/{ark} (OCR ALTO).',
     f'- **Enveloppe** : celle de la copie (métadonnées, feuille de style, couverture, page de titre, « (1859) », dédicace) ; '
     'table des matières du livre refaite pour 14 chapitres.',
     f'- **Résultat** : `{P["resultat"]["epub"]}` (md5 `{P["resultat"]["epub_md5"]}`), epubcheck '
     f'{P["resultat"]["epubcheck"].get("erreurs")} erreur, {P["resultat"]["epubcheck"].get("avertissements")} avertissement ; '
     f'{len(P["chapitres"])} chapitres, {fmt(P["mots"])} mots.', '',
     '## Ce qui change par rapport à la copie livrée en juin', '',
     '- Le texte intégral remplace l’abrégé : les 95 coupes (14 270 mots) sont rendues, dont le chapitre « Biribi » ; '
     'la copie comptait 12 chapitres, le livre en a 14 (le dernier était fondu dans « La comtesse Blagowski »).',
     '- Les titres de chapitres sont ceux de l’édition (« Arrivée », « Visite au moulin »…), en casse de phrase comme dans la copie.',
     '- Les onze notes de l’édition reviennent, en fin de chapitre, avec leur appel.',
     '- Perdu avec l’abrégé : ses corrections de juin (elles portaient sur un texte qui n’est plus) et ses italiques (aucun des '
     'deux témoins texte ne les porte).', '',
     '## Contrôle mot à mot', '',
     f'Divergences entre Wikisource et Gallica : {", ".join(f"{k} {n}" for k, n in sorted(cnt.items()))}. '
     'Ponctuation, graphies, bruit et erreurs de lecture de l’OCR : leçon de Wikisource. Variantes entre les éditions de 1861 et '
     'de 1884 : leçon de 1884, la base choisie, chacune listée ci-dessous. Légendes d’illustrations écartées.', '',
     '| Vue | Wikisource (1884, retenu) | Gallica (1861) |', '|---|---|---|']
for d in P['divergences']:
    if d['classe'] in ('variante', 'ajout gallica', 'omission gallica'):
        vl = f'[{d["vue"]}](https://gallica.bnf.fr/ark:/12148/{ark}/f{d["vue"]}.item)' if d['vue'] else '—'
        ret = '' if d['choix'] == 'ws' else ' (Gallica retenu)'
        L.append(f'| {vl} | {md(tx(d["ws"])) or "∅"}{ret} | {md(tx(d["gallica"])) or "∅"} |')
L += ['', '## Lettrines et notes', ''] + [f'- Lettrine : {x}' for x in P['lettrines']] + [f'- Note : {x}' for x in P['notes']]
L += ['', '## Chapitres', '', '| Chapitre | Titre (Wikisource) | Paragraphes | Vues Gallica | Notes |', '|---|---|---:|---|---:|']
for c in P['chapitres']:
    vs = c['vues']
    L.append(f'| {c["numero"]} | {md(c["titre"].rstrip("."))} | {c["paragraphes"]} | '
             + (f'[{vs[0]}](https://gallica.bnf.fr/ark:/12148/{ark}/f{vs[0]}.item)–{vs[1]}' if vs else '—') + f' | {len(c["notes"])} |')
open(f'{PR}/{i}-recompose.md.tmp', 'w').write('\n'.join(L) + '\n'); os.replace(f'{PR}/{i}-recompose.md.tmp', f'{PR}/{i}-recompose.md')
# installation
md5 = lambda p: hashlib.md5(open(p, 'rb').read()).hexdigest()
shutil.copy(f'{PR}/{base}.recompose.epub', f'{W}/sortie/{base}.epub')
shutil.copy(f'{PR}/{base}.recompose.kepub.epub', f'{W}/sortie/{base}.kepub.epub')
app = {'volume': i, 'titre': v['titre'], 'recomposition': {'decision': P['decision'], 'rapport': f'propositions/721-abrege/{i}-recompose.md',
       'chapitres': len(P['chapitres']), 'mots': P['mots'], 'variantes_1861_1884': sum(1 for d in P['divergences'] if d['classe'] in ('variante', 'ajout gallica', 'omission gallica'))},
       'epub_md5': md5(f'{W}/sortie/{base}.epub'), 'kepub_md5': md5(f'{W}/sortie/{base}.kepub.epub'),
       'epubcheck_apres': P['resultat']['epubcheck'], 'appliquees': 0, 'rejetees': 0,
       'ocr_apply': 'sans objet (texte recomposé depuis Wikisource)'}
with open(f'{W}/sortie/application/{i}.json.tmp', 'w') as f:
    json.dump(app, f, ensure_ascii=False, indent=1)
os.replace(f'{W}/sortie/application/{i}.json.tmp', f'{W}/sortie/application/{i}.json')
att = f'{W}/outils/attente.json'
a = json.load(open(att)); a.pop(i, None)
with open(att + '.tmp', 'w') as f:
    json.dump(a, f, ensure_ascii=False, indent=1)
os.replace(att + '.tmp', att)
print(i, 'installé ; rapport', f'{PR}/{i}-recompose.md', '; md5', app['epub_md5'])
