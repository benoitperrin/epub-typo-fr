#!/usr/bin/env python3
"""
chapdump.py — Extrait le texte de chaque document d'un EPUB vers des fichiers .txt,
pour relecture (humaine ou LLM). Produit aussi un index JSON.

Usage: python3 chapdump.py livre.epub <out_dir> [--min-chars 100]
"""
import sys, os, re, json, zipfile, html, argparse

TAG_RE = re.compile(r'(<[^>]+>|<!--.*?-->)', re.S)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('epub'); ap.add_argument('out_dir')
    ap.add_argument('--min-chars', type=int, default=100)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    z = zipfile.ZipFile(args.epub)
    chaps = []
    for n in z.namelist():
        if not n.lower().endswith(('.xhtml', '.html', '.htm')):
            continue
        htm = z.read(n).decode('utf-8', errors='replace')
        htm = re.sub(r'<head\b.*?</head>', '', htm, flags=re.S | re.I)
        htm = re.sub(r'</p>', '\n\n', htm, flags=re.I)
        t = html.unescape(TAG_RE.sub('', htm))
        t = re.sub(r'\n{3,}', '\n\n', t).strip()
        if len(t) < args.min_chars:
            continue
        fn = os.path.join(args.out_dir, n.replace('/', '_') + '.txt')
        with open(fn, 'w') as f:
            f.write(f'### DOC: {n}\n\n' + t)
        chaps.append({'doc': n, 'file': os.path.abspath(fn), 'chars': len(t)})
    json.dump(chaps, open(os.path.join(args.out_dir, 'index.json'), 'w'), ensure_ascii=False)
    print(f'{len(chaps)} documents → {args.out_dir}')

if __name__ == '__main__':
    main()
