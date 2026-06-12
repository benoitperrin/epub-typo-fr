#!/usr/bin/env python3
"""
extract_samples.py — Extrait des échantillons de texte de chaque EPUB flaggé,
pour vérification humaine/LLM des défauts détectés par l'audit regex.

Usage: python3 extract_samples.py <books_dir> <ids.txt> <inventory.tsv> <out_dir>
Échantillons : 3 tranches (début/milieu/fin du livre), ~1500 chars chacune,
prises au début d'un document du spine (= début de chapitre, le plus souvent).
"""
import sys, os, re, zipfile, html

TAG_RE = re.compile(r'<[^>]+>')
HEAD_RE = re.compile(r'<head\b.*?</head>', re.S | re.I)
STYLE_RE = re.compile(r'<style\b.*?</style>', re.S | re.I)

def doc_text(z, name):
    raw = z.read(name)
    try:
        htm = raw.decode('utf-8')
    except UnicodeDecodeError:
        htm = raw.decode('latin-1', errors='replace')
    body = HEAD_RE.sub('', htm)
    body = STYLE_RE.sub('', body)
    body = re.sub(r'</p>', '\n\n', body, flags=re.I)
    body = TAG_RE.sub('', body)
    body = html.unescape(body)
    return re.sub(r'\n{3,}', '\n\n', body).strip()

def main():
    books_dir, ids_path, inv_path, out_dir = sys.argv[1:5]
    os.makedirs(out_dir, exist_ok=True)
    ids = {int(l.strip()) for l in open(ids_path) if l.strip()}
    inv = {}
    for l in open(inv_path):
        p = l.rstrip('\n').split('\t')
        inv[int(p[0])] = p
    for bid in sorted(ids):
        if bid not in inv:
            continue
        row = inv[bid]
        epub = os.path.join(books_dir, row[1], row[2] + '.epub')
        out = [f"# {row[3]} — {row[4] if len(row) > 4 else ''} (id {bid})"]
        try:
            z = zipfile.ZipFile(epub)
            docs = [n for n in z.namelist() if n.lower().endswith(('.xhtml', '.html', '.htm'))
                    and not re.search(r'(cover|titlepage|copyright|nav|toc)', n.lower())]
            docs.sort()
            if not docs:
                docs = [n for n in z.namelist() if n.lower().endswith(('.xhtml', '.html', '.htm'))]
            picks = []
            if docs:
                n = len(docs)
                for idx in {min(1, n - 1), n // 2, min(n - 2, n - 1) if n > 2 else n - 1}:
                    picks.append(docs[idx])
            for name in picks:
                t = doc_text(z, name)
                if len(t) < 200 and len(docs) > 5:  # doc trop court (page de garde), suivant
                    k = docs.index(name)
                    for alt in docs[k + 1:k + 4]:
                        t = doc_text(z, alt)
                        if len(t) >= 200:
                            name = alt
                            break
                out.append(f"\n## Extrait — {name}\n")
                out.append(t[:1500])
            z.close()
        except Exception as e:
            out.append(f"ERREUR: {e}")
        with open(os.path.join(out_dir, f'{bid}.txt'), 'w') as f:
            f.write('\n'.join(out))
    print(f'{len(ids)} samples → {out_dir}', flush=True)

if __name__ == '__main__':
    main()
