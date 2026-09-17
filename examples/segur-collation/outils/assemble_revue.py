#!/usr/bin/env python3
"""
assemble_revue.py — Contrôle de réception d'une relecture de collation, puis liste finale des
corrections d'un volume.

Usage : python3 assemble_revue.py <id> [--epub copie.epub]

Lit collation-2026-09-16/<id>-items.json et revue/<id>-revue.json (dossier de travail
$SEGUR_WORKDIR). Vérifie que chaque item a exactement un verdict valide, qu'une
correction accompagne chaque décision qui en exige une, que les raisons sont écrites et que la
prose ne porte pas d'apostrophe droite ; puis écrit revue/<id>-corrections.jsonl (format
ocr_apply, chaque ligne tracée : item, décision, témoins, raison) et revue/<id>-bilan.json.
Un essai d'application (ocr_apply, sortie jetée) dit enfin quelles corrections ne passent pas.
Code de sortie 1 si la relecture est incomplète ou mal formée.
"""
import sys, os, json, argparse, subprocess, tempfile, re
from collections import Counter
import chemins

W = chemins.W
TOOLS = chemins.TOOLS
DECISIONS = {
    'N0': {'garder', 'veto', 'modifier'},
    'N1': {'garder', 'veto', 'modifier'},
    'J': {'garder', 'revenir', 'autre'},
    'N2': {'corriger', 'laisser', 'ouvert'},
    'L': {'laisser', 'corriger'},
    'E': {'corriger', 'ouvert'},          # compléments : coquilles relevées hors items par le relecteur, reprises et vérifiées
}
AVEC_CORRECTION = {'modifier', 'revenir', 'autre', 'corriger'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('id')
    ap.add_argument('--epub', required=True)
    args = ap.parse_args()
    items = {it['id']: it for it in json.load(open(f'{W}/collation-2026-09-16/{args.id}-items.json'))}
    revue = json.load(open(f'{W}/revue/{args.id}-revue.json'))
    comp_p = f'{W}/revue/{args.id}-complements.json'
    if os.path.exists(comp_p):
        for x in json.load(open(comp_p))['items']:
            if x['item'] in items:                       # reprise d'un verdict du relecteur
                revue['items'] = [v for v in revue['items'] if v.get('item') != x['item']]
            else:
                items[x['item']] = {'id': x['item'], 'type': 'complement', 'niveau': 'complément', 'temoins': {}}
            revue['items'].append(x)
    errs, verdicts = [], {}
    fam_v = {f['famille']: f for f in revue.get('familles', [])}
    for f, fv in fam_v.items():
        membres = [it for it in items.values() if it.get('famille') == f]
        if not membres:
            errs.append(f'famille inconnue : {f}')
            continue
        if fv.get('decision') not in ('garder', 'veto'):
            errs.append(f'famille {f} : décision « {fv.get("decision")} » invalide')
        if not (fv.get('raison') or '').strip():
            errs.append(f'famille {f} : raison manquante')
        relus = set(fv.get('echantillon_relu') or [])
        manquants = [it['id'] for it in membres if it.get('echantillon') and it['id'] not in relus]
        if manquants:
            errs.append(f'famille {f} : échantillon non relu {manquants}')
    for v in revue.get('items', []):
        iid = v.get('item')
        if iid not in items:
            errs.append(f'{iid} : item inconnu')
            continue
        if iid in verdicts:
            errs.append(f'{iid} : deux verdicts')
        verdicts[iid] = v
    for iid, it in items.items():
        if iid not in verdicts and it.get('famille') in fam_v:
            fv = fam_v[it['famille']]
            verdicts[iid] = {'item': iid, 'decision': fv['decision'], 'par_famille': True,
                             'raison': f'famille « {it["famille"]} », échantillon relu : {fv["raison"]}'}
        v = verdicts.get(iid)
        prefix = iid.split('-')[0]
        if v is None:
            errs.append(f'{iid} : sans verdict')
            continue
        d = v.get('decision')
        if d not in DECISIONS[prefix]:
            errs.append(f'{iid} : décision « {d} » invalide pour {prefix}')
        if not (v.get('raison') or '').strip():
            errs.append(f'{iid} : raison manquante')
        if d == 'ouvert' and not (v.get('question') or '').strip():
            errs.append(f'{iid} : ouvert sans question')
        if d in AVEC_CORRECTION:
            c = v.get('correction') or {}
            if not all(c.get(k) is not None for k in ('doc', 'chercher', 'remplacer')):
                errs.append(f'{iid} : {d} sans correction complète')
            elif "'" in c['remplacer']:
                errs.append(f'{iid} : apostrophe droite dans « remplacer »')
        if d == 'garder' and prefix in ('N0', 'N1') and not it.get('correction'):
            errs.append(f'{iid} : garder, mais la collation n’a pas de correction applicable '
                        f'({it.get("non_applicable", "?")}) — il faut « modifier »')

    corrections, bilan = [], Counter()
    for iid, it in items.items():
        v = verdicts.get(iid)
        if not v:
            continue
        d = v['decision']
        bilan[f'{iid.split("-")[0]}_{d}'] += 1
        c = None
        if d == 'garder' and iid.split('-')[0] in ('N0', 'N1'):
            c = dict(it.get('correction') or {})
        elif d in AVEC_CORRECTION:
            c = dict(v.get('correction') or {})
        if not c or not c.get('chercher'):
            continue
        tem = v.get('temoins') or ' · '.join(f'{n} « {l} »' for n, l in (it.get('temoins') or {}).items()
                                             if isinstance(l, str))
        c = {'doc': c['doc'], 'chercher': c['chercher'], 'remplacer': c['remplacer'],
             **{k: c[k] for k in ('avant', 'apres') if c.get(k)},
             'raison': f'{iid} ({d}) — {v["raison"]}' + (f' — témoins : {tem}' if tem else ''),
             'source': f'collation {it.get("niveau") or "juin"} — relecture', 'item': iid}
        corrections.append(c)

    out = f'{W}/revue/{args.id}-corrections.jsonl'
    with open(out, 'w') as f:
        for c in corrections:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
    juin = json.load(open(f'{W}/collation-2026-09-16/{args.id}-juin.json'))
    jb = Counter(r['bilan'] for r in juin)
    res = {
        'volume': args.id,
        'juin_total': len(juin),
        'juin_confirmees_temoins': jb['confirmée'],
        'juin_confirmees_relecture': bilan['J_garder'],
        'juin_infirmees': bilan['J_revenir'] + bilan['J_autre'],
        'nouvelles_proposees': sum(1 for c in corrections if not c['item'].startswith('J')),
        'n2_ouverts': sum(n for k, n in bilan.items() if k.endswith('_ouvert')),
        'decisions': dict(bilan),
        'questions': [{'item': iid, 'question': v['question']} for iid, v in verdicts.items()
                      if v.get('decision') == 'ouvert'],
        'remarques': revue.get('remarques', []),
    }

    # essai d'application
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([sys.executable, f'{TOOLS}/ocr_apply.py', args.epub, f'{tmp}/x.epub', out,
                            '--budget-pct', '1.5', '--max-edit', '16', '--insertion-max', '250', '--report', f'{tmp}/r.md'],
                           capture_output=True, text=True)
        rep = open(f'{tmp}/r.md').read() if os.path.exists(f'{tmp}/r.md') else r.stdout + r.stderr
    rej = rep.split('## Rejetées', 1)[1].strip() if '## Rejetées' in rep else ''
    res['essai'] = (r.stdout.strip().splitlines() or ['?'])[0]
    res['rejets'] = [l for l in rej.splitlines() if l.startswith('- ')]
    json.dump(res, open(f'{W}/revue/{args.id}-bilan.json', 'w'), ensure_ascii=False, indent=1)
    print(f'{args.id} : {len(verdicts)}/{len(items)} verdicts, {len(corrections)} corrections, '
          f'essai « {res["essai"]} », {len(errs)} anomalie(s)')
    for e in errs:
        print('  ✗', e)
    for l in res['rejets']:
        print('  rejet :', l[:220])
    sys.exit(1 if errs else 0)


if __name__ == '__main__':
    main()
