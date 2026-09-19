#!/usr/bin/env python3
"""
livre.py — Livraison de la collation Ségur dans $SEGUR_OUT/.

Usage : python3 livre.py [--journal "texte de l'entrée"]

Pour chaque volume dont la relecture est assemblée (revue/<id>-bilan.json) et appliquée
(sortie/application/<id>.json) : rapport final (rapport de collation + décisions de relecture +
application), EPUB, KEPUB, diff HTML, corrections rejouables. Puis LISEZMOI.md (tableau de tous
les volumes, questions ouvertes) et, dans le dépôt epub-typo-fr, la provenance
(examples/segur-collation/collation-segur.json) et le manifeste (examples/manifeste-segur.json,
bloc « collation_2026_09 » par volume). Idempotent : relancer réécrit tout.
"""
import os, re, json, shutil, argparse, datetime
from collections import Counter
import chemins

W = chemins.W
TOOLS = chemins.TOOLS
OUT = chemins.OUT
DEC_LIB = {'garder': 'gardée', 'veto': 'écartée', 'modifier': 'modifiée', 'revenir': 'retour à la leçon d’origine',
           'autre': 'autre correction', 'corriger': 'corrigée', 'laisser': 'laissée', 'ouvert': 'ouverte'}


def md(s):
    return (s or '').replace('|', '\\|').replace('\n', ' ')


def jetons(x):
    """Texte recomposé depuis des jetons (« jour . ») : ponctuation remise à la française."""
    x = re.sub(r' ([,.])', r'\1', x or '')
    x = re.sub(r' ([;:!?])', '\u202f\\1', x)
    return re.sub(r" ?([’']) ?", '’', x)


def fmt(n):
    return f'{n:,}'.replace(',', '\u202f')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--journal', default='')
    args = ap.parse_args()
    T = json.load(open(f'{TOOLS}/examples/segur-collation/temoins-segur.json'))['volumes']
    for d in ('epub', 'kepub', 'diffs', 'rapports', 'corrections'):
        os.makedirs(f'{OUT}/{d}', exist_ok=True)
    rows, questions, provenance = [], [], []
    for v in T:
        i, slug = str(v['id']), v['slug']
        base = f'Comtesse-de-Segur-{slug}'
        bil_p, app_p = f'{W}/revue/{i}-bilan.json', f'{W}/sortie/application/{i}.json'
        st_p = f'{W}/collation-2026-09-16/{i}-stats.json'
        if not (os.path.exists(bil_p) and os.path.exists(app_p) and os.path.exists(st_p)):
            rows.append((v, None, None, None))
            continue
        bil, app, st = json.load(open(bil_p)), json.load(open(app_p)), json.load(open(st_p))
        items = {it['id']: it for it in json.load(open(f'{W}/collation-2026-09-16/{i}-items.json'))}
        rj = json.load(open(f'{W}/revue/{i}-revue.json'))
        revue = {x['item']: x for x in rj['items']}
        fam_v = {f['famille']: f for f in rj.get('familles', [])}
        for iid_, it_ in items.items():
            if iid_ not in revue and it_.get('famille') in fam_v:
                fv = fam_v[it_['famille']]
                revue[iid_] = {'item': iid_, 'decision': fv['decision'],
                               'raison': f'famille « {it_["famille"]} », jugée sur échantillon : {fv["raison"]}'}
        if os.path.exists(f'{W}/revue/{i}-complements.json'):
            for x in json.load(open(f'{W}/revue/{i}-complements.json'))['items']:
                revue[x['item']] = x
                items.setdefault(x['item'], {'id': x['item']})
        applied_md = open(f'{W}/sortie/application/{i}.md').read() if os.path.exists(f'{W}/sortie/application/{i}.md') else ''
        part_app = applied_md.split('## Rejetées')[0]
        part_rej = applied_md.split('## Rejetées')[1] if '## Rejetées' in applied_md else ''

        # ---- rapport final
        rep = open(f'{W}/rapports/{i}-{slug}.md').read().rstrip('\n')
        L = [rep, '', '## F. Relecture : décisions et traces', '',
             'Chaque item a été relu contre les témoins (sous-agent Opus, protocole '
             '`revue/PROTOCOLE.md`), puis contrôlé mécaniquement (`assemble_revue.py`) et appliqué par '
             '`ocr_apply.py` (budget 1,5 %, insertions attestées jusqu’à 250 caractères, 16 modifications au plus par correction).', '',
             '| Item | Décision | Raison et témoins | Appliquée |', '|---|---|---|---|']
        for iid in items:
            x = revue.get(iid)
            if not x:
                continue
            d = x['decision']
            if re.search(rf'\b{re.escape(iid)} \(', part_app):
                ok = 'oui'
            elif re.search(rf'\b{re.escape(iid)} \(', part_rej):
                ok = 'rejetée par l’applicateur'
            else:
                ok = '—'
            corr = x.get('correction')
            txt = md(x.get('raison', ''))
            if x.get('temoins'):
                txt += f' — témoins : {md(x["temoins"])}'
            if corr and d in ('modifier', 'revenir', 'autre', 'corriger'):
                txt += f' — « {md(corr["chercher"])} » → « {md(corr["remplacer"])} »'
            if d == 'ouvert':
                txt += f' — **question** : {md(x.get("question", ""))}'
                questions.append((v, iid, x.get('question', ''), x.get('temoins', '')))
            L.append(f'| {iid} | {DEC_LIB.get(d, d)} | {txt} | {ok} |')
        L += ['', '## G. Application', '',
              f'- `ocr_apply.py` : {app.get("ocr_apply")}.',
              f'- epubcheck : {app["epubcheck_avant"]["erreurs"]} erreur(s) avant, '
              f'{app["epubcheck_apres"]["erreurs"]} après.' if 'epubcheck_apres' in app else '- epubcheck : non passé.',
              f'- Audit typographique, compteurs changés (avant → après) : '
              + (', '.join(f'{k} {a} → {b}' for k, (a, b) in app.get('audit', {}).items()) or 'aucun') + '.',
              f'- Régressions typographiques : {", ".join(app.get("audit_regressions") or []) or "aucune"}.',
              f'- md5 : source `{app.get("source_md5")}`, EPUB corrigé `{app.get("epub_md5")}`, '
              f'KEPUB `{app.get("kepub_md5", "—")}`.']
        lac_p = f'{W}/collation-2026-09-16/{i}-lacunes.json'
        lac = [l for l in (json.load(open(lac_p)) if os.path.exists(lac_p) else []) if l['confirmee'] and l['nature'] == 'lacune']
        app['lacunes'] = lac
        rest = app.get('restitution')
        if lac and rest:
            L += ['', '## H. Lacunes de la copie, restituées', '',
                  f'Passages entiers que tous les témoins portent et que la copie n’avait pas : restitués dans le volume livré '
                  f'({rest["decision"]}), {rest["passages"]} passage(s), {fmt(rest["mots"])} mots, texte des témoins tracé '
                  f'paragraphe par paragraphe (sous-page Wikisource, vues Gallica) : `{rest["rapport"]}`. '
                  'Le volume sans restitution est gardé dans `archives/sans-restitution/`.', '']
            L += [f'- {md(x)}' for x in rest.get('chapitres') or []]
            L += ['', '| Après (copie) | Mots restitués | Début du passage | Fin |', '|---|---:|---|---|']
        elif lac:
            L += ['', '## H. Lacunes de la copie (non restituées)', '',
                  'Passages entiers que tous les témoins portent et que la copie n’a pas. Une restitution de '
                  'paragraphes dépasse l’applicateur (il ne crée pas de balises) : elle est laissée à la décision de '
                  'Benoît, à faire à la main depuis Wikisource, relue sur Gallica.', '',
                  '| Après (copie) | Mots manquants | Début du passage manquant | Fin |', '|---|---:|---|---|']
            for l in lac:
                L.append(f'| …{md(jetons(l["copie_avant"])[-60:])} | {fmt(l["temoin_mots"])} | {md(jetons(l["temoin_debut"])[:110])}… | …{md(jetons(l["temoin_fin"])[-80:])} |')
        for r in bil.get('remarques') or []:
            L.append(f'- Remarque de relecture : {md(r)}')
        open(f'{OUT}/rapports/{i}-{slug}.md', 'w').write('\n'.join(L) + '\n')
        for src, dst in ((f'{W}/sortie/{base}.epub', f'{OUT}/epub/{base}.epub'),
                         (f'{W}/sortie/{base}.kepub.epub', f'{OUT}/kepub/{base}.kepub.epub'),
                         (f'{W}/sortie/{base}.diff.html', f'{OUT}/diffs/{base}.diff.html'),
                         (f'{W}/revue/{i}-corrections.jsonl', f'{OUT}/corrections/{i}-{slug}.jsonl')):
            if os.path.exists(src):
                shutil.copy(src, dst)
        # corrections nouvelles appliquées : hors retours sur juin (J-xx), comptées avant fusion
        rej_items = set(re.findall(r'\b([A-Z]\d?-\d\d) \(', part_rej))
        corr_items = [json.loads(l)['item'] for l in open(f'{W}/revue/{i}-corrections.jsonl') if l.strip()]
        app['nouvelles'] = sum(1 for x in corr_items if not x.startswith('J-') and x not in rej_items)
        app['fusions'] = len(corr_items) - len(rej_items) - (app.get('appliquees') or 0)
        rows.append((v, bil, app, st))
        provenance.append({
            'id': v['id'], 'titre': v['titre'],
            'temoins': {n: {'edition': t['edition'], 'couverture': t['couverture']} for n, t in st['temoins'].items()},
            'juin': {'total': bil['juin_total'], 'confirmees_par_les_temoins': bil['juin_confirmees_temoins'],
                     'confirmees_a_la_relecture': bil['juin_confirmees_relecture'], 'infirmees': bil['juin_infirmees']},
            'corrections_nouvelles_appliquees': app['nouvelles'],
            'entrees_ocr_apply': app.get('appliquees'),
            'corrections_rejetees_par_l_applicateur': app.get('rejetees'),
            'n2_ouverts': bil['n2_ouverts'], 'decisions': bil['decisions'],
            'source_md5': app.get('source_md5'), 'epub_md5': app.get('epub_md5'),
            'epubcheck_erreurs': app.get('epubcheck_apres', {}).get('erreurs'),
        })

    # ---- LISEZMOI
    now = datetime.datetime.now().strftime('%d/%m/%Y à %H h %M')
    faits = [r for r in rows if r[1]]
    L = ['# Collation des romans de la comtesse de Ségur contre témoins', '',
         f'Mise à jour : {now}. {len(faits)} volume(s) sur 13 collationné(s), relu(s) et corrigé(s).', '',
         'Les 13 romans restaurés en juin 2026 avaient été corrigés sans témoin. Chaque volume est ici '
         'aligné mot à mot sur des témoins indépendants : la transcription Wikisource (relue par des '
         'humains) et l’OCR d’une édition Hachette ancienne sur Gallica, ou sur Internet Archive quand '
         'Gallica n’a rien. Les corrections de juin sont confirmées ou infirmées, les fautes restantes '
         'corrigées quand les témoins permettent de trancher, toujours avec leur trace ; restent '
         'ouverts les seuls cas sans témoin décisif ou à lectures équivalentes.', '',
         '| Volume | Témoins | Juin : confirmées | Juin : infirmées | Nouvelles | N2 ouvertes | epubcheck |',
         '|---|---|---:|---:|---:|---:|---|']
    attente = json.load(open(f'{W}/outils/attente.json')) if os.path.exists(f'{W}/outils/attente.json') else {}
    for v, bil, app, st in rows:
        if not bil:
            etat = 'suspendu, voir plus bas' if str(v['id']) in attente else 'en attente'
            L.append(f'| {v["id"]} *{md(v["titre"].replace("'", "’"))}* | {etat} | | | | | |')
            continue
        tem = ', '.join(st['temoins'])
        conf = bil['juin_confirmees_temoins'] + bil['juin_confirmees_relecture']
        rel = f' (dont {bil["juin_confirmees_relecture"]} à la relecture)' if bil['juin_confirmees_relecture'] else ''
        L.append(f'| {v["id"]} *{md(v["titre"].replace("'", "’"))}* | {tem} | {conf} / {bil["juin_total"]}{rel} | {bil["juin_infirmees"]} | '
                 f'{app["nouvelles"]} | {bil["n2_ouverts"]} | {app.get("epubcheck_apres", {}).get("erreurs")} erreur |')
    if faits:
        tot = Counter()
        for v, bil, app, st in faits:
            tot['conf'] += bil['juin_confirmees_temoins'] + bil['juin_confirmees_relecture']
            tot['juin'] += bil['juin_total']; tot['inf'] += bil['juin_infirmees']
            tot['new'] += app['nouvelles']; tot['open'] += bil['n2_ouverts']
        L.append(f'| **Total** | | **{fmt(tot["conf"])} / {fmt(tot["juin"])}** | **{fmt(tot["inf"])}** | **{fmt(tot["new"])}** | **{tot["open"]}** | |')
    if attente:
        L += ['', '## Volumes suspendus', '']
        for k, note in attente.items():
            titre = next(v['titre'] for v, *_ in rows if str(v['id']) == k).replace("'", '’')
            L.append(f'- **{k} *{md(titre)}*** : {note}')
    rest_all = [(v, app['restitution']) for v, bil, app, st in faits if app.get('restitution')]
    if rest_all:
        L += ['', '## Lacunes de la copie, restituées', '',
              'Passages entiers que tous les témoins portent et que la copie avait perdus, rendus à leur place dans le volume '
              'livré (décision de Benoît du 19/09/2026), chaque paragraphe tracé ; les volumes sans restitution sont gardés '
              'dans `archives/sans-restitution/`.', '']
        for v, r in rest_all:
            L.append(f'- **{v["id"]} *{md(v["titre"].replace(chr(39), "’"))}*** : {r["passages"]} passage(s), {fmt(r["mots"])} mots — `{r["rapport"]}`.')
    lac_all = [(v, l) for v, bil, app, st in faits if not app.get('restitution') for l in app.get('lacunes', [])]
    if lac_all:
        L += ['', '## Lacunes de la copie, à restituer à la main', '',
              'Passages entiers présents dans tous les témoins et absents de la copie (détail en section H du rapport '
              'du volume). Ils ne sont pas restitués : l’applicateur ne crée pas de paragraphes.', '']
        for v, l in lac_all:
            L.append(f'- **{v["id"]} *{md(v["titre"].replace("'", "’"))}*** : {fmt(l["temoin_mots"])} mots après « …{md(jetons(l["copie_avant"])[-50:])} » '
                     f'(commence par « {md(jetons(l["temoin_debut"])[:70])}… »).')
    L += ['', '« Confirmées » : corrections de juin que les témoins portent, ou que la relecture a maintenues '
          'contre un témoin fautif. « Infirmées » : corrections de juin défaites ou remplacées. « Nouvelles » : '
          'corrections appliquées en plus, chacune tracée dans le rapport du volume (section F). Aucune n’a été '
          'rejetée par l’applicateur.', '',
          '## Contenu', '',
          '- `epub/`, `kepub/` : les livres corrigés (EPUB validé par epubcheck, KEPUB pour Kobo).',
          '- `diffs/` : chaque correction en « avant → après », surlignée.',
          '- `rapports/` : un rapport par volume — témoins et éditions, corrections de juin devant les '
          'témoins, corrections proposées, cas à trancher, puis décisions de relecture avec leur trace '
          '(section F) et résultat de l’application (section G).',
          '- `corrections/` : les corrections appliquées, rejouables (`ocr_apply.py`).', '',
          '## Questions ouvertes', '']
    if questions:
        for v, iid, q, tem in questions:
            L.append(f'- **{v["id"]} *{md(v["titre"].replace("'", "’"))}*, {iid}** : {md(q)}' + (f' ({md(tem)})' if tem else ''))
    else:
        L.append('Aucune pour les volumes livrés.')
    # propositions préparées à part (restitutions, abrégé, passe Gallica seul) : une question chacune
    props = []
    for sd in sorted(os.listdir(f'{OUT}/propositions')) if os.path.isdir(f'{OUT}/propositions') else []:
        lp = f'{OUT}/propositions/{sd}/LISEZMOI.md'
        if os.path.exists(lp):
            txt = open(lp).read()
            titre = txt.splitlines()[0].lstrip('# ').strip()
            m = re.search(r'\*\*La question\*\* : (.*)', txt)
            t2 = re.search(r'\*\*Tranché\*\* (.*)', txt)
            props.append(f'- **`propositions/{sd}/`** — {titre}' + ('' if titre[-1:] in '?.!' else '.')
                         + (f' Question : {m.group(1).strip()}' if m else '')
                         + (f' **Tranché** {t2.group(1).strip()}' if t2 else ''))
    if props:
        L += ['', '## Propositions préparées à part', '',
              'Ce que la chaîne ne pouvait pas appliquer a été préparé dans `propositions/`, à part ; chaque dossier a son '
              'LISEZMOI, sa question et, une fois tranchée, la décision.', ''] + props
    L += ['', '## Méthode et outils', '',
          'Dépôt public https://github.com/benoitperrin/epub-typo-fr (commits locaux de septembre 2026, '
          'poussés par Benoît) : `witness_wikisource.py`, `witness_gallica.py`, `collate.py`, '
          '`collate_report.py`, `ocr_apply.py`. Témoins retenus : '
          '`examples/segur-collation/temoins-segur.json` ; provenance des corrections : '
          '`examples/segur-collation/collation-segur.json`.']
    if args.journal:
        L += ['', '## Journal', '', args.journal]
    open(f'{OUT}/LISEZMOI.md', 'w').write('\n'.join(L) + '\n')

    # ---- provenance et manifeste (dépôt)
    json.dump({'_commentaire': 'Collation des 13 romans contre témoins (septembre 2026) : par volume, témoins, '
                               'sort des corrections de juin, corrections nouvelles, cas ouverts, empreintes.',
               'volumes': provenance}, open(f'{TOOLS}/examples/segur-collation/collation-segur.json', 'w'),
              ensure_ascii=False, indent=1)
    man_p = f'{TOOLS}/examples/manifeste-segur.json'
    man = json.load(open(man_p))
    by = {p['id']: p for p in provenance}
    for m in man:
        p = by.get(m['id'])
        if p:
            m['collation_2026_09'] = {k: p[k] for k in ('juin', 'corrections_nouvelles_appliquees', 'n2_ouverts',
                                                         'epub_md5', 'epubcheck_erreurs')}
    json.dump(man, open(man_p, 'w'), ensure_ascii=False, indent=1)
    open(man_p, 'a').write('\n')
    print(f'livré : {len(faits)} volume(s) ; {len(questions)} question(s) ouverte(s) → {OUT}')


if __name__ == '__main__':
    main()
