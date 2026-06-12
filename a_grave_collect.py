#!/usr/bin/env python3
"""
a_grave_collect.py — Collecte les « A » majuscules isolés candidats à l'accentuation
(« A quoi bon » → « À quoi bon ») avec leur contexte, pour arbitrage LLM.

Le même motif et le même ordre de parcours sont utilisés par epub_typo_fix.py
(--a-grave-decisions) : l'occurrence n° i du collecteur est l'occurrence n° i du fixer.

Usage : python3 a_grave_collect.py livre.epub > candidats.jsonl
Sortie : {"doc": ..., "idx": n, "avant": "...", "apres": "..."} par ligne.
Décisions attendues en retour : {"doc": ..., "idx": n, "accentuer": true/false}
"""
import sys, re, json, zipfile, html

# Un A isolé suivi d'une espace et d'une minuscule/déterminant — volontairement large,
# c'est le LLM qui tranche.
A_CAND_RE = re.compile(r'\bA(?= [a-zà-öø-ÿ])')
TAG_RE = re.compile(r'(<[^>]+>|<!--.*?-->)', re.S)

def main():
    epub = sys.argv[1]
    z = zipfile.ZipFile(epub)
    for name in z.namelist():
        if not name.lower().endswith(('.xhtml', '.html', '.htm')):
            continue
        try:
            htm = z.read(name).decode('utf-8')
        except UnicodeDecodeError:
            htm = z.read(name).decode('latin-1', errors='replace')
        idx = 0
        skip = 0
        for part in TAG_RE.split(htm):
            if part.startswith('<'):
                t = re.match(r'</?\s*([a-zA-Z0-9]+)', part)
                tag = t.group(1).lower() if t else ''
                if tag in ('style', 'script', 'pre', 'code', 'svg'):
                    skip += 1 if not part.startswith('</') else -1
                    skip = max(skip, 0)
                continue
            if skip or not part:
                continue
            text = html.unescape(part)
            for m in A_CAND_RE.finditer(text):
                print(json.dumps({
                    'doc': name, 'idx': idx,
                    'avant': text[max(0, m.start() - 60):m.start()].lstrip(),
                    'apres': text[m.start():m.start() + 70].rstrip(),
                }, ensure_ascii=False))
                idx += 1
    z.close()

if __name__ == '__main__':
    main()
