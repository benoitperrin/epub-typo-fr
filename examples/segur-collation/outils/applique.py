#!/usr/bin/env python3
"""
applique.py — Applique les corrections relues d'un volume Ségur et vérifie le résultat.

Usage : python3 applique.py 723 719 [--corrections fichier.jsonl] [--sortie dossier]

Pour chaque volume : ocr_apply (budget 1,5 %, insertions attestées jusqu'à 250 caractères, 16 modifications au plus,
rapport Markdown et diff HTML), epubcheck, audit typographique comparé avant / après, kepubify.
Écrit <sortie>/<id>-application.json. Ne touche jamais à la copie source.
"""
import sys, os, re, json, shutil, subprocess, tempfile, argparse, hashlib, glob
import chemins

W = chemins.W
TOOLS = chemins.TOOLS
SAMPLES = chemins.SAMPLES
EPUBCHECK = chemins.EPUBCHECK
AUDIT_KEYS = ('chars', 'apos_straight', 'apos_curly', 'nnbsp', 'nbsp', 'punct_none', 'punct_space',
              'guil_in_none', 'guil_in_space', 'dlg_hyphen', 'dlg_emdash', 'mojibake', 'lig_bad',
              'caps_bad', 'encoding_issues', 'ellipsis_dots')


def epubcheck(path):
    r = subprocess.run(['java', '-jar', EPUBCHECK, path], capture_output=True, text=True)
    m = re.search(r'Messages: (\d+) fatals? / (\d+) errors? / (\d+) warnings?', r.stdout + r.stderr)
    return {'fatals': int(m.group(1)), 'erreurs': int(m.group(2)), 'avertissements': int(m.group(3))} if m \
        else {'fatals': -1, 'erreurs': -1, 'avertissements': -1, 'sortie': (r.stdout + r.stderr)[-500:]}


def audit(paths):
    with tempfile.TemporaryDirectory() as tmp:
        for k, p in enumerate(paths):
            shutil.copy(p, f'{tmp}/{k}.epub')
        subprocess.run([sys.executable, f'{TOOLS}/epub_typo_audit.py', tmp, f'{tmp}/a.jsonl'],
                       capture_output=True, text=True)
        rows = {json.loads(l)['name']: json.loads(l) for l in open(f'{tmp}/a.jsonl')}
    return [{k: rows[str(i)].get(k) for k in AUDIT_KEYS} for i in range(len(paths))]


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ids', nargs='+')
    ap.add_argument('--corrections', help='(essai) fichier de corrections à la place de revue/<id>-corrections.jsonl')
    ap.add_argument('--sortie', default=f'{W}/sortie')
    args = ap.parse_args()
    T = {str(v['id']): v for v in json.load(open(f'{TOOLS}/examples/segur-collation/temoins-segur.json'))['volumes']}
    os.makedirs(f'{args.sortie}/application', exist_ok=True)
    for i in args.ids:
        v = T[i]
        base = f'Comtesse-de-Segur-{v["slug"]}'
        src = f'{SAMPLES}/{base}.epub'
        dst = f'{args.sortie}/{base}.epub'
        corr = args.corrections or f'{W}/revue/{i}-corrections.jsonl'
        r = subprocess.run([sys.executable, f'{TOOLS}/ocr_apply.py', src, dst, corr, '--budget-pct', '1.5',
                            '--max-edit', '16', '--insertion-max', '250', '--report', f'{args.sortie}/application/{i}.md',
                            '--report-html', f'{args.sortie}/{base}.diff.html',
                            '--titre', v['titre'].replace("'", '’')], capture_output=True, text=True)
        ligne = (r.stdout.strip().splitlines() or ['?'])[0]
        m = re.match(r'(\d+) appliquées, (\d+) rejetées', ligne)
        res = {'volume': i, 'titre': v['titre'], 'source_md5': md5(src), 'ocr_apply': ligne,
               'appliquees': int(m.group(1)) if m else None, 'rejetees': int(m.group(2)) if m else None}
        if not os.path.exists(dst) or r.returncode:
            res['echec'] = (r.stdout + r.stderr)[-800:]
            print(f'{i} : ÉCHEC ocr_apply — {res["echec"][-300:]}')
            json.dump(res, open(f'{args.sortie}/application/{i}.json', 'w'), ensure_ascii=False, indent=1)
            continue
        res['epub_md5'] = md5(dst)
        res['epubcheck_avant'] = epubcheck(src)
        res['epubcheck_apres'] = epubcheck(dst)
        avant, apres = audit([src, dst])
        res['audit'] = {k: [avant[k], apres[k]] for k in AUDIT_KEYS if avant[k] != apres[k]}
        # une correction ne doit dégrader aucun compteur de défaut typographique
        pires = [k for k in ('apos_straight', 'punct_none', 'punct_space', 'guil_in_none', 'guil_in_space',
                             'dlg_hyphen', 'mojibake', 'lig_bad', 'caps_bad', 'encoding_issues', 'ellipsis_dots')
                 if (apres[k] or 0) > (avant[k] or 0)]
        res['audit_regressions'] = pires
        with tempfile.TemporaryDirectory() as tmp:
            k = subprocess.run(['kepubify', '-o', tmp, dst], capture_output=True, text=True)
            outs = glob.glob(f'{tmp}/*.kepub.epub')
            if outs:
                shutil.move(outs[0], f'{args.sortie}/{base}.kepub.epub')
                os.chmod(f'{args.sortie}/{base}.kepub.epub', 0o644)
                res['kepub_md5'] = md5(f'{args.sortie}/{base}.kepub.epub')
            else:
                res['kepub_echec'] = (k.stdout + k.stderr)[-500:]
        json.dump(res, open(f'{args.sortie}/application/{i}.json', 'w'), ensure_ascii=False, indent=1)
        print(f'{i} {v["slug"]} : {ligne} ; epubcheck {res["epubcheck_avant"]["erreurs"]} → '
              f'{res["epubcheck_apres"]["erreurs"]} erreurs ; audit {res["audit"]} ; '
              f'régressions {pires or "aucune"} ; kepub {"ok" if "kepub_md5" in res else "ÉCHEC"}')


if __name__ == '__main__':
    main()
