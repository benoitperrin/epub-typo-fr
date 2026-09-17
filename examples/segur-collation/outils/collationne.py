#!/usr/bin/env python3
"""
collationne.py — Collation et rapport d'un ou plusieurs volumes Ségur, avec les témoins
disponibles sur disque (Wikisource toujours ; Gallica si son texte est là ; Internet Archive
pour 719 et 723).

Usage : python3 collationne.py 723 719 [--sans-gallica 719]
"""
import sys, os, re, json, zipfile, hashlib, subprocess, argparse
import chemins

W = chemins.W
TOOLS = chemins.TOOLS
SAMPLES = chemins.SAMPLES
IA = {
    '719': ('ia/719-nouveauxcontesde00sg.txt', 'Internet Archive (Hachette 1917)',
            'OCR Internet Archive nouveauxcontesde00sg, Hachette, Paris, 1917'),
    '723': ('ia/723-mmoiresdunne00sguoft.txt', 'Internet Archive (Édito-Service, Genève, s. d.)',
            'OCR Internet Archive mmoiresdunne00sguoft, Édito-Service, Genève, s. d., « Œuvre romanesque »'),
}
AVANCEMENT = {'T': 'transcription terminée', 'V': 'transcription validée', 'C': 'à corriger',
              'MS': 'à découper', 'OCR': 'OCR brut', 'L': 'à valider'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ids', nargs='+')
    ap.add_argument('--sans-gallica', action='append', default=[])
    args = ap.parse_args()
    T = {str(v['id']): v for v in json.load(open(f'{TOOLS}/examples/segur-collation/temoins-segur.json'))['volumes']}
    os.makedirs(f'{W}/rapports', exist_ok=True)
    for i in args.ids:
        v = T[i]
        epub = f'{SAMPLES}/Comtesse-de-Segur-{v["slug"]}.epub'
        md5 = hashlib.md5(open(epub, 'rb').read()).hexdigest()
        pg = sorted({m for n in zipfile.ZipFile(epub).namelist() for m in re.findall(r'@files@(\d+)@', n)})
        wsj = json.load(open(f'{W}/ws/{i}.json'))
        idx = wsj.get('index', {})
        ws_desc = (f'Wikisource FR, « {wsj["page"]} », {AVANCEMENT.get(idx.get("Avancement"), idx.get("Avancement", "?"))}, '
                   f'édition {idx.get("Editeur", "?")}{", " + idx["Lieu"] if idx.get("Lieu") else ""}, {idx.get("Annee", "?")}')
        cmd = [sys.executable, f'{TOOLS}/collate.py', epub, '--temoin', f'ws={W}/ws/{i}.txt',
               '--temoin-edition', f'ws=Wikisource ({idx.get("Editeur", "?")} {idx.get("Annee", "?")})']
        info = ['--temoin-info', f'ws={ws_desc}']
        g = v.get('gallica')
        gtxt = f'{W}/gallica/{g["ark"]}.txt' if g else None
        if g and os.path.exists(gtxt) and i not in args.sans_gallica:
            cmd += ['--temoin', f'gallica={gtxt}', '--temoin-edition', f'gallica=Gallica ({g["edition"]})']
            info += ['--temoin-info', f'gallica=OCR Gallica ark:/12148/{g["ark"]}, {g["edition"]}']
        if i in IA:
            f, ed, desc = IA[i]
            cmd += ['--temoin', f'ia={W}/{f}', '--temoin-edition', f'ia={ed}']
            info += ['--temoin-info', f'ia={desc}']
        cmd += ['--original', f'{W}/orig/{i}.epub', '--out', f'{W}/collation-2026-09-16', '--id', i,
                '--titre', v['titre']]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(f'{i} : collate.py a échoué\n{r.stderr[-2000:]}')
            continue
        src = (f'{os.path.basename(epub)} (restauration de juin 2026, md5 {md5})'
               + (f', texte Project Gutenberg n° {", ".join(pg)}' if pg else ''))
        rep = f'{W}/rapports/{i}-{v["slug"]}.md'
        r2 = subprocess.run([sys.executable, f'{TOOLS}/collate_report.py', f'{W}/collation-2026-09-16', i,
                             '--out', rep, '--titre', v['titre'].replace("'", '’'), '--source', src] + info,
                            capture_output=True, text=True)
        st = json.load(open(f'{W}/collation-2026-09-16/{i}-stats.json'))
        niv = {k[7:]: n for k, n in sorted(st['stats'].items()) if k.startswith('niveau_')}
        cov = {n: t['couverture'] for n, t in st['temoins'].items()}
        print(f'{i} {v["slug"]} : témoins {cov} ; {niv} ; {st["corrections"]} corrections ; '
              f'{r2.stdout.strip() or r2.stderr.strip()[-300:]}')


if __name__ == '__main__':
    main()
