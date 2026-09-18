#!/usr/bin/env python3
"""
collate_report.py — Rapport Markdown d'une collation (sorties de collate.py), et table des
items numérotés que la relecture et l'application se partagent.

Usage :
  python3 collate_report.py dossier/ 723 --out 723-les-memoires-d-un-ane.md \
      [--titre "Les Mémoires d'un âne"] [--source "fichier.epub (md5 …)"] \
      [--temoin-info ws="Wikisource, Hachette 1894, terminé"] [--temoin-info ia="…"]

Lit <id>-stats.json, <id>-sites.json, <id>-juin.json, <id>-corrections.jsonl ; écrit le rapport
et <id>-items.json : un identifiant stable par item (J-03 correction de juin, N0-07, N1-02,
N2-11), trié dans l'ordre du livre, avec la correction proposée quand il y en a une.

Principe rappelé en tête de chaque rapport : on ne corrige pas l'auteur, on corrige la copie ;
une leçon fautive que les témoins permettent de trancher se corrige, avec sa trace (témoin,
leçon, raisonnement) ; restent ouverts les cas sans témoin ou à lectures équivalentes.
"""
import os, re, json, argparse, difflib
from collections import Counter

N2_LEVELS = ('N2', 'N2-divergent', 'N2-seul', 'N2-ponct', 'N2-ponct-consensus')
# Familles mécaniques : même règle, même preuve (deux témoins d'accord mot pour mot). Au-delà de
# FAMILLE_MIN items, la relecture juge la famille sur un échantillon régulier (un sur dix, huit au
# moins) au lieu de chaque item ; elle garde le droit d'écarter n'importe quel item.
FAMILLES = {'N0': None,  # toutes les règles N0
            'N1': {'accent fautif (deux témoins)', 'apostrophe (deux témoins)', 'accent grammatical',
                   'accent avalé'}}
FAMILLE_MIN = 8
# Famille N2 de présentation : la copie abrège une civilité que tous les témoins impriment en toutes
# lettres (« Mme Blidot » / « madame Blidot »). Aucune correction proposée : même question pour chaque
# item, jugée une fois sur échantillon (729 : 140 items).
CIVILITES = {'Mme': 'madame', 'Mlle': 'mademoiselle', 'Mmes': 'mesdames', 'Mlles': 'mesdemoiselles',
             'M .': 'monsieur', 'MM .': 'messieurs'}
FAMILLE_CIVILITE = 'N2 · civilité abrégée dans la copie (témoins en toutes lettres)'
NIVEAU_LIBELLE = {
    'N2': 'deux témoins d’accord, mais pas sur une faute que la règle sait trancher',
    'N2-divergent': 'les témoins divergent entre eux',
    'N2-seul': 'un seul témoin couvre le passage',
    'N2-ponct': 'ponctuation, témoins en désaccord',
    'N2-ponct-consensus': 'ponctuation, témoins d’accord, application non sûre',
}


def fmt(n):
    return f'{n:,}'.replace(',', '\u202f')


def md(s):
    """Texte cité dans un tableau Markdown : barres échappées, espaces visibles gardées."""
    return (s or '').replace('|', '\\|').replace('\n', ' ')


def bold(x):
    """Gras Markdown qui rend : les espaces du bord restent dehors."""
    core = x.strip(' \u202f\xa0')
    if not core:
        return x + '‸' if x else '‸'
    i = x.index(core)
    return x[:i] + '**' + core + '**' + x[i + len(core):]


def diff_inline(a, b):
    """« avant » et « après » avec la partie changée en gras (sur la citation `chercher`)."""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    av, ap = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            av.append(a[i1:i2]); ap.append(b[j1:j2])
        else:
            av.append(bold(a[i1:i2]) if i2 > i1 else '‸')
            ap.append(bold(b[j1:j2]) if j2 > j1 else '‸')
    return ''.join(av), ''.join(ap)


def lecons(temoins):
    return ' · '.join((f'{n} « {md(v)} »' if v else f'{n} ∅') if v is not None else f'{n} (non couvert)'
                      for n, v in temoins.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('dossier'); ap.add_argument('id')
    ap.add_argument('--out', required=True)
    ap.add_argument('--titre', default='')
    ap.add_argument('--source', default='')
    ap.add_argument('--temoin-info', action='append', default=[], help='nom=« description »')
    args = ap.parse_args()
    p = lambda suffix: os.path.join(args.dossier, f'{args.id}-{suffix}')
    stats = json.load(open(p('stats.json')))
    sites = json.load(open(p('sites.json')))
    juin = json.load(open(p('juin.json'))) if os.path.exists(p('juin.json')) else []
    info = dict(x.split('=', 1) for x in args.temoin_info)
    titre = args.titre or stats.get('titre') or args.id
    st = Counter(stats['stats'])

    # ---- items numérotés, dans l'ordre du livre
    items, n_by = [], Counter()

    def new_id(prefix):
        n_by[prefix] += 1
        return f'{prefix}-{n_by[prefix]:02d}'

    for r in sorted(juin, key=lambda r: r['i1']):
        if r['bilan'] == 'confirmée' and 'correction' not in r:
            continue
        items.append({'id': new_id('J'), 'type': 'juin', **r})
    for lvl in ('N0', 'N1') + N2_LEVELS + ('laisse',):
        for s in sites:
            if s.get('niveau') == lvl:
                prefix = {'laisse': 'L'}.get(lvl, 'N2' if lvl.startswith('N2') else lvl)
                it = {'id': new_id(prefix), 'type': 'site', **s}
                raison = (s.get('correction') or {}).get('raison', '').split(' — ')[0]
                if lvl in FAMILLES and raison and (FAMILLES[lvl] is None or raison in FAMILLES[lvl]):
                    it['famille'] = f'{lvl} · {raison}'
                elif lvl == 'N2' and s.get('nous') in CIVILITES:
                    lec = [x for x in (s.get('temoins') or {}).values() if isinstance(x, str)]
                    if len(lec) >= 2 and all(x.lower() == CIVILITES[s['nous']] for x in lec):
                        it['famille'] = FAMILLE_CIVILITE
                items.append(it)
    familles = {}
    for it in items:
        if it.get('famille'):
            familles.setdefault(it['famille'], []).append(it)
    for f, membres in list(familles.items()):
        if len(membres) < FAMILLE_MIN:
            for it in membres:
                del it['famille']
            del familles[f]
            continue
        k = max(1, len(membres) // max(FAMILLE_MIN, len(membres) // 10))
        for n, it in enumerate(membres):
            it['echantillon'] = (n % k == 0)

    # ---- rapport
    L = []
    w = L.append
    w(f'# Collation — *{titre}*, comtesse de Ségur')
    w('')
    if args.source:
        w(f'- **Copie collationnée** : {args.source}.')
    for n, t in stats['temoins'].items():
        desc = info.get(n) or t.get('edition') or ''
        pct = f'{t["couverture"] * 100:.1f}'.replace('.', ',')
        w(f'- **Témoin `{n}`** : {desc} — {fmt(t["tokens"])} jetons, couverture {pct}\u202f%.')
    w(f'- **Méthode** : `collate.py` (ancres de 6 mots uniques puis alignement mot à mot, '
      f'{fmt(stats["mots"])} mots), classement automatique, puis relecture de chaque correction '
      f'proposée et de chaque cas ouvert.')
    w('- **Cadre** : on ne corrige pas l’auteur, on corrige la copie. N0 typographie et ponctuation, '
      'N1 restitution qu’une seule lecture permet, N2 cas à trancher. Doctrine du 05/09/2026 : une '
      'leçon fautive que les témoins permettent de trancher se corrige, avec sa trace ; restent '
      'ouverts les seuls cas sans témoin ou à lectures réellement équivalentes.')
    w('')
    w('## Bilan')
    w('')
    jb = Counter(r['bilan'] for r in juin)
    w('| | Nombre |')
    w('|---|---:|')
    w(f'| Corrections de juin retrouvées par différence avec l’original | {len(juin)} |')
    for b in ('confirmée', 'infirmée', 'contradictoire', 'autre leçon', 'non collationnée'):
        if jb[b]:
            w(f'| — {b}s | {jb[b]} |')
    for lvl in ('N0', 'N1') + N2_LEVELS:
        if st[f'niveau_{lvl}']:
            w(f'| Sites {lvl} ({NIVEAU_LIBELLE.get(lvl, "correction proposée")}) | {st["niveau_" + lvl]} |')
    w(f'| Corrections proposées à l’application | {stats["corrections"]} |')
    pres = {k.split('_', 1)[1]: v for k, v in st.items() if k.startswith('presentation_')}
    if pres:
        w('| Écarts de présentation, relevés sans correction | '
          + ', '.join(f'{k} {v}' for k, v in sorted(pres.items())) + ' |')
    if st['niveau_laisse']:
        w(f'| Graphies laissées (époque ou choix d’édition) | {st["niveau_laisse"]} |')
    bruit = sum(v for k, v in st.items() if k.startswith('bruit_'))
    w(f'| Divergences d’un seul témoin, les autres lisant comme la copie (bruit d’OCR, variantes) | {bruit} |')
    if st['non_applicable']:
        w(f'| Corrections non applicables telles quelles (motif non unique, frontière de balise) | {st["non_applicable"]} |')
    w('')

    # ---- A. corrections de juin
    w('## A. Les corrections de juin devant les témoins')
    w('')
    by_nat = Counter((r['nature'], r['bilan']) for r in juin)
    if juin:
        w('| Nature | ' + ' | '.join(b for b in ('confirmée', 'infirmée', 'contradictoire', 'autre leçon', 'non collationnée')) + ' |')
        w('|---|---:|---:|---:|---:|---:|')
        for nat in sorted({r['nature'] for r in juin}):
            w(f'| {nat} | ' + ' | '.join(str(by_nat[(nat, b)]) for b in ('confirmée', 'infirmée', 'contradictoire', 'autre leçon', 'non collationnée')) + ' |')
        w('')
    ouvertes = [it for it in items if it['type'] == 'juin']
    if ouvertes:
        w('Corrections de juin que les témoins ne confirment pas :')
        w('')
        w('| # | Chap. | Contexte | Juin | Témoins | Bilan |')
        w('|---|---|---|---|---|---|')
        for it in ouvertes:
            ctx = f'…{md(it["contexte_avant"][-50:])} ⟦·⟧ {md(it["contexte_apres"][:40])}…'
            tem = ' · '.join(f'{n} {v["verdict"]} « {md(v["lecon"])} »' for n, v in it['temoins'].items())
            w(f'| {it["id"]} | {md(it.get("chap") or "")} | {ctx} | « {md(it["avant_juin"])} » → « {md(it["apres_juin"])} » | {tem} | {it["bilan"]} |')
        w('')
    conf = [r for r in juin if r['bilan'] == 'confirmée']
    if conf:
        w(f'<details><summary>Les {len(conf)} corrections confirmées</summary>')
        w('')
        for r in conf:
            w(f'- « {md(r["avant_juin"])} » → « {md(r["apres_juin"])} » ({r["nature"]}) : …{md(r["contexte_avant"][-40:])} ⟦·⟧ {md(r["contexte_apres"][:30])}…')
        w('')
        w('</details>')
        w('')

    if familles:
        w('## Relecture par familles')
        w('')
        w('Les familles mécaniques de plus de huit items sont jugées sur un échantillon régulier '
          '(marqué ★ ci-dessous) ; tout item peut encore être écarté. Une famille N2 ne propose aucune '
          'correction : c’est un écart de présentation, laissé ou tranché une fois pour toute la famille.')
        w('')
        w('| Famille | Items | Échantillon |')
        w('|---|---:|---|')
        for f, membres in familles.items():
            w(f'| {f} | {len(membres)} | {", ".join(it["id"] for it in membres if it["echantillon"])} |')
        w('')

    # ---- B. corrections proposées
    for lvl, head in (('N0', 'B. N0 — typographie et ponctuation attestées'),
                      ('N1', 'C. N1 — restitutions attestées')):
        sel = [it for it in items if it['type'] == 'site' and it.get('niveau') == lvl]
        w(f'## {head}')
        w('')
        if not sel:
            w('Aucune.')
            w('')
            continue
        w('| # | Chap. | Avant | Après | Témoins | Raison |')
        w('|---|---|---|---|---|---|')
        for it in sel:
            c = it.get('correction')
            if c:
                av, apr = diff_inline(c['chercher'], c['remplacer'])
            else:
                av, apr = f'…{it["avant"][-40:]} **{it["nous"]}** {it["apres"][:30]}…', f'✗ {it.get("non_applicable", "")}'
            raison = (c['raison'].split(' — ')[0] if c else '')
            star = ' ★' if it.get('echantillon') else ''
            w(f'| {it["id"]}{star} | {md(it.get("chap") or "")} | {md(av)} | {md(apr)} | {lecons(it["temoins"])} | {md(raison)} |')
        w('')

    # ---- D. N2
    sel = [it for it in items if it['type'] == 'site' and it.get('niveau', '').startswith('N2')]
    w('## D. N2 — à trancher')
    w('')
    if not sel:
        w('Aucun.')
    for lvl in N2_LEVELS:
        part = [it for it in sel if it['niveau'] == lvl]
        if not part:
            continue
        w(f'### {lvl} — {NIVEAU_LIBELLE[lvl]} ({len(part)})')
        w('')
        w('| # | Chap. | Contexte | Copie | Témoins | Nature |')
        w('|---|---|---|---|---|---|')
        for it in part:
            ctx = f'…{md(it["avant"][-55:])} ⟦·⟧ {md(it["apres"][:40])}…'
            star = ' ★' if it.get('echantillon') else ''
            w(f'| {it["id"]}{star} | {md(it.get("chap") or "")} | {ctx} | « {md(it["nous"])} » | {lecons(it["temoins"])} | {it.get("classe", "")} |')
        w('')

    # ---- E. ce qu'on laisse
    w('## E. Ce qu’on laisse')
    w('')
    laisse = [it for it in items if it['id'].startswith('L-')]
    if laisse:
        w('Graphies d’époque ou choix d’édition, jamais « modernisés » par la collation (chacune est '
          'néanmoins relue : une coquille classée ici par erreur se corrige) :')
        w('')
        for it in laisse:
            w(f'- {it["id"]} « {md(it["nous"])} » ({lecons(it["temoins"])}) : …{md(it["avant"][-40:])} ⟦·⟧ {md(it["apres"][:30])}…')
        w('')
    if pres:
        w('Écarts de présentation, comptés et non corrigés : '
          + ', '.join(f'**{k}** {v}' for k, v in sorted(pres.items()))
          + '. « locuteur » : la copie compose « <i>Nom:</i>—réplique » là où l’édition imprime le nom '
            'sur sa ligne, suivi d’un point ; harmoniser est un choix d’éditeur.')
        w('')
    loc = Counter(s['nous'] for s in sites if s.get('niveau') == 'presentation' and s.get('classe') == 'locuteur')
    if loc:
        w('Formes de locuteurs les plus fréquentes : ' + ', '.join(f'« {md(k)} » ×{v}' for k, v in loc.most_common(8)) + '.')
        w('')
    with open(args.out, 'w') as f:
        f.write('\n'.join(L) + '\n')
    json.dump(items, open(p('items.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'{args.out} : {len(items)} items ({dict(n_by)})')


if __name__ == '__main__':
    main()
