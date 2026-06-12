#!/usr/bin/env python3
"""
build_lexicon.py — Lexique de corpus à partir des livres OK de la bibliothèque.
Mot retenu s'il apparaît dans ≥ MIN_BOOKS livres distincts (filtre les coquilles
isolées et noms propres ultra-locaux). Sortie : un mot par ligne, minuscules NFC.

Usage: python3 build_lexicon.py <books_dir> <ids.txt> <inventory.tsv> <out.txt>
"""
import sys, os, re, zipfile, html, unicodedata
from collections import Counter

MIN_BOOKS = 2
TAG_RE = re.compile(r'<[^>]+>')
HEAD_RE = re.compile(r'<head\b.*?</head>', re.S | re.I)
WORD_RE = re.compile(r"[a-zà-öø-ÿœæ]+(?:[-'’][a-zà-öø-ÿœæ]+)*")

def book_words(epub):
    words = set()
    z = zipfile.ZipFile(epub)
    for n in z.namelist():
        if not n.lower().endswith(('.xhtml', '.html', '.htm')):
            continue
        try:
            t = z.read(n).decode('utf-8')
        except UnicodeDecodeError:
            continue
        t = HEAD_RE.sub('', t)
        t = TAG_RE.sub(' ', t)
        t = html.unescape(t)
        t = unicodedata.normalize('NFC', t).lower().replace('’', "'")
        words.update(WORD_RE.findall(t))
    z.close()
    return words

def main():
    books_dir, ids_path, inv_path, out_path = sys.argv[1:5]
    ids = {int(l) for l in open(ids_path) if l.strip()}
    inv = {}
    for l in open(inv_path):
        p = l.rstrip('\n').split('\t')
        inv[int(p[0])] = p
    df = Counter()
    done = 0
    for bid in sorted(ids):
        if bid not in inv:
            continue
        row = inv[bid]
        epub = os.path.join(books_dir, row[1], row[2] + '.epub')
        if not os.path.exists(epub):
            continue
        try:
            df.update(book_words(epub))
        except Exception as e:
            print(f'skip {bid}: {e}', flush=True)
        done += 1
        if done % 50 == 0:
            print(f'{done} livres, {len(df)} formes', flush=True)
    kept = sorted(w for w, c in df.items() if c >= MIN_BOOKS)
    with open(out_path, 'w') as f:
        f.write('\n'.join(kept))
    print(f'done: {done} livres, {len(df)} formes vues, {len(kept)} retenues (≥{MIN_BOOKS} livres)', flush=True)

if __name__ == '__main__':
    main()
