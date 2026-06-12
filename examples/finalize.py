#!/usr/bin/env python3
"""
finalize.py — Assemble les corrections de l'usine et produit les EPUB finaux Ségur.

Par livre : fusionne corrections-anom + corrections-lecture-* → ocr_apply (diff HTML)
→ clean_opf (métadonnées domaine public) → epubcheck → ré-audit typo.
Écrit un manifeste récapitulatif JSON + Markdown.

Usage: python3 finalize.py
"""
import json, os, subprocess, glob, sys, re

REPO = os.path.expanduser('~/src/bp/epub-typo-fr')
BOOKS = {
    718: "Un bon petit diable", 719: "Nouveaux contes de fées pour les petits enfants",
    720: "Pauvre Blaise", 721: "Les vacances", 722: "Les petites filles modèles",
    723: "Les Mémoires d'un âne", 724: "Les malheurs de Sophie", 725: "Le Mauvais Génie",
    726: "Les deux nigauds", 727: "Le Général Dourakine",
    728: "Jean qui grogne et Jean qui rit", 729: "L'auberge de l'ange gardien",
    730: "François le Bossu",
}
AUTEUR = "Comtesse de Ségur"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def audit_one(epub):
    out = '/tmp/segur/_audit_tmp.jsonl'
    if os.path.exists(out):
        os.remove(out)
    d = '/tmp/segur/_audit_dir'
    os.makedirs(d, exist_ok=True)
    for f in glob.glob(d + '/*'):
        os.remove(f)
    import shutil
    shutil.copy(epub, d + '/x.epub')
    run(['python3', f'{REPO}/epub_typo_audit.py', d, out])
    rec = json.loads(open(out).readline())
    return rec


def main():
    manifest = []
    for bid, titre in BOOKS.items():
        merged = f'/tmp/segur/corrections-{bid}-all.jsonl'
        with open(merged, 'w') as out:
            for f in [f'/tmp/segur/corrections-anom-{bid}.jsonl'] + \
                     sorted(glob.glob(f'/tmp/segur/corrections-lecture-{bid}-*.jsonl')):
                if os.path.exists(f):
                    out.write(open(f).read())
        n_prop = sum(1 for l in open(merged) if l.strip() and 'chercher' in l)

        # appliquer
        applied_epub = f'/tmp/segur/{bid}-applied.epub'
        r = run(['python3', f'{REPO}/ocr_apply.py', f'/tmp/segur/{bid}-strip.epub',
                 applied_epub, merged, '--report-html', f'/tmp/segur/diff-{bid}.html',
                 '--titre', f'{titre} (#{bid})', '--budget-pct', '1.5'])
        m = re.search(r'(\d+) appliquées, (\d+) rejetées', r.stdout)
        n_app, n_rej = (int(m.group(1)), int(m.group(2))) if m else (0, 0)

        # nettoyer l'OPF
        final_epub = f'/tmp/segur/{bid}-final.epub'
        run(['python3', f'{REPO}/clean_opf.py', applied_epub, final_epub,
             '--titre', titre, '--auteur', AUTEUR])

        # epubcheck
        ec = run(['epubcheck', final_epub])
        ec_ok = ec.returncode == 0
        ec_errs = len(re.findall(r'\bERROR\b', ec.stdout + ec.stderr))

        # ré-audit
        a = audit_one(final_epub)
        manifest.append({
            'id': bid, 'titre': titre,
            'corrections_proposees': n_prop, 'appliquees': n_app, 'rejetees': n_rej,
            'epubcheck_ok': ec_ok, 'epubcheck_erreurs': ec_errs,
            'apos_droites': a.get('apos_straight'), 'apos_courbes': a.get('apos_curly'),
            'dlg_hyphen': a.get('dlg_hyphen'), 'dlg_emdash': a.get('dlg_emdash'),
            'mojibake': a.get('mojibake'), 'chars': a.get('chars'),
        })
        print(f"#{bid} {titre[:35]:35} : {n_app} appliquées/{n_prop}, "
              f"epubcheck {'OK' if ec_ok else 'KO('+str(ec_errs)+')'}, "
              f"apos {a.get('apos_straight')}/{a.get('apos_curly')}", flush=True)

    json.dump(manifest, open('/tmp/segur/manifeste.json', 'w'), ensure_ascii=False, indent=1)
    tot_app = sum(m['appliquees'] for m in manifest)
    ok = sum(1 for m in manifest if m['epubcheck_ok'])
    print(f"\nTOTAL : {tot_app} corrections appliquées, {ok}/13 epubcheck OK")


if __name__ == '__main__':
    main()
