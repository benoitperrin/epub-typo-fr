#!/usr/bin/env python3
"""Découpe les dumps de chapitres en fenêtres de lecture ~TARGET chars,
coupées sur des frontières de paragraphe, avec léger chevauchement.
Usage: make_windows.py <chapdump_dir> <out_dir> <livre_id>"""
import sys, os, json

TARGET = 25000
OVERLAP = 400

def main():
    chap_dir, out_dir, livre = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    index = json.load(open(os.path.join(chap_dir, 'index.json')))
    windows = []
    w = 0
    for entry in index:
        text = open(entry['file']).read()
        # retire l'en-tête "### DOC:" du dump
        body = text.split('\n\n', 1)[1] if text.startswith('### DOC:') else text
        paras = body.split('\n\n')
        cur, cur_len = [], 0
        chunks = []
        for p in paras:
            cur.append(p)
            cur_len += len(p) + 2
            if cur_len >= TARGET:
                chunks.append('\n\n'.join(cur))
                # chevauchement : reprend la fin du chunk précédent
                tail = chunks[-1][-OVERLAP:]
                cur, cur_len = [f'[…suite — contexte précédent : …{tail}]'], 0
        if cur and any(p.strip() for p in cur):
            chunks.append('\n\n'.join(cur))
        for k, chunk in enumerate(chunks):
            w += 1
            fn = os.path.join(out_dir, f'{livre}-w{w:03d}.txt')
            with open(fn, 'w') as f:
                f.write(f"### LIVRE {livre} — DOC: {entry['doc']} — fenêtre {k+1}/{len(chunks)}\n\n")
                f.write(chunk)
            windows.append({'livre': int(livre), 'doc': entry['doc'],
                            'file': os.path.abspath(fn), 'chars': len(chunk)})
    json.dump(windows, open(os.path.join(out_dir, 'windows.json'), 'w'), ensure_ascii=False)
    print(f'livre {livre}: {len(windows)} fenêtres')

if __name__ == '__main__':
    main()
