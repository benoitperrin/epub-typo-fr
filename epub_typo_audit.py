#!/usr/bin/env python3
"""
epub_typo_audit.py — Audit typographique (FR) de tous les EPUB d'une bibliothèque Calibre.

Produit un JSONL de métriques brutes par livre (le scoring se fait en aval).
Conçu pour tourner sur Hirondelle (1 Go RAM) : un livre à la fois, un fichier à la fois.
Reprise sur incident : les ids déjà présents dans out.jsonl sont sautés.

Usage: python3 epub_typo_audit.py <books_dir> <inventory.tsv> <out.jsonl>
  inventory.tsv: id<TAB>path<TAB>name<TAB>title<TAB>authors<TAB>readers<TAB>lang
"""
import sys, os, re, json, zipfile, html

NBSP = ' '      # espace insécable
NNBSP = ' '     # espace fine insécable
THIN = ' '      # espace fine (sécable mais souvent utilisée comme fine)
# Ne compter comme insécables QUE les trois espaces de classe GL (UAX #14) : U+00A0, U+2007, U+202F.
NBS_CLASS = '[\u00a0\u2007\u202f]'
# Fausses insécables : sécables malgré leur nom (U+2008 PUNCTUATION SPACE, U+2009 THIN SPACE…) —
# sans ce compteur, une ponctuation précédée de U+2008 n'entre dans aucune case (faux négatif silencieux).
FAKE_NBS = '[\u2000-\u2006\u2008\u2009\u200a\u205f\u3000]'
RSQUO = '’'     # apostrophe courbe
LDQUO, RDQUO = '“', '”'
EMDASH, ENDASH = '—', '–'
ELLIP = '…'
SHY = '­'

TAG_RE = re.compile(r'<[^>]+>')
HEAD_RE = re.compile(r'<head\b.*?</head>', re.S | re.I)
STYLE_RE = re.compile(r'<style\b.*?</style>', re.S | re.I)
# Paragraphes de dialogue : <p ...> suivi (espaces, insécables, balises inline) d'un tiret
PARA_DASH_RE = re.compile(
    r'<p[^>]*>(?:\s|&#160;|&nbsp;|&#xa0;|&#8239;|<[^>]+>)*'
    r'(—|–|\-|&#8212;|&#x2014;|&#8211;|&#x2013;|&mdash;|&ndash;)',
    re.I)

LIG_BAD_RE = re.compile(
    r'\b(?:coeurs?|choeurs?|soeurs?|oeuvres?|oeufs?|noeuds?|oeil|voeux?|boeufs?|'
    r'moeurs|manoeuvr\w*|oeillet\w*|oesophage\w*)\b', re.I)
LIG_GOOD_RE = re.compile(
    r'\b(?:cœurs?|chœurs?|sœurs?|œuvres?|œufs?|nœuds?|'
    r'œil|vœux?|bœufs?|mœurs|manœuvr\w*)\b', re.I)

CAPS_BAD_RE = re.compile(
    r'\b(?:Etat|Eglise|Ecole|Etre|Epoque|Evidemment|Ecoutez?|Etrange\w*|Etais|Etait|Etant|'
    r'Eteins|Eternel\w*|Ete|Egypte|Equipe|Etage|Etoile\w*|Enorme\w*|Epee|Eclair\w*|'
    r'Etang|Evidence|Evenement\w*|'
    r'A(?= (?:quoi|qui|cette|cet|ce|ces|la|le|les|chaque|votre|peine|côté|cause|'
    r'droite|gauche|travers|moitié|présent|partir|peu près)\b))\b')
CAPS_GOOD_RE = re.compile(
    r'\b(?:État|Église|École|Être|Époque|Évidemment|'
    r'Écoutez?|Étrange\w*|Étais|Était|Étant|Éteins|'
    r'Éternel\w*|Été|Égypte|Équipe|Étage|Étoile\w*|'
    r'Énorme\w*|Épée|Éclair\w*|Étang|Évidence|'
    r'Événement\w*|À)\b')

MOJIBAKE_RE = re.compile(
    'Ã[©¨§ª ¤¢ª«®¯´¶»¼§]'
    '|â€™|â€œ|â€“|Å“|Â«|Â»|Â |�')

# césure résiduelle d'OCR : minuscule + "- " + minuscule
HYPHEN_RESIDUE_RE = re.compile(r'[a-zà-öø-ÿ]- [a-zà-öø-ÿ]')

LETTER = 'A-Za-zÀ-ÖØ-öø-ÿ'

def text_metrics(t, m):
    m['chars'] += len(t)
    m['apos_straight'] += t.count("'")
    m['apos_curly'] += t.count(RSQUO)
    m['dq_straight'] += t.count('"')
    m['dq_curly'] += t.count(LDQUO) + t.count(RDQUO)
    m['guil_open'] += t.count('«')
    m['guil_close'] += t.count('»')
    m['nbsp'] += t.count(NBSP)
    m['nnbsp'] += t.count(NNBSP)
    m['softhyphen'] += t.count(SHY)
    m['emdash'] += t.count(EMDASH)
    m['endash'] += t.count(ENDASH)
    m['ellipsis_char'] += t.count(ELLIP)
    m['ellipsis_dots'] += len(re.findall(r'(?<!\.)\.\.\.(?!\.)', t))
    # ponctuation haute ! ? ; — espace avant ?
    m['punct_nbsp'] += len(re.findall(NBS_CLASS + r'[!?;]', t))
    m['punct_space'] += len(re.findall(r'[' + LETTER + r'0-9)»…] [!?;]', t))
    m['punct_none'] += len(re.findall(r'[' + LETTER + r'][!?;]', t))
    # deux-points (exclure heures/URLs pour "aucune espace")
    m['punct_nbsp'] += len(re.findall(NBS_CLASS + r':', t))
    m['punct_space'] += len(re.findall(r'[' + LETTER + r')»] :', t))
    m['punct_none'] += len(re.findall(r'[' + LETTER + r']:(?![/0-9])', t))
    # espace typographique d'apparence correcte mais sécable devant ! ? ; : »
    m['punct_fakespace'] += len(re.findall(FAKE_NBS + r'[!?;:»]', t))
    # guillemets : espaces intérieures
    m['guil_in_nbsp'] += len(re.findall(r'«' + NBS_CLASS, t)) + len(re.findall(NBS_CLASS + r'»', t))
    m['guil_in_space'] += len(re.findall(r'« ', t)) + len(re.findall(r' »', t))
    m['guil_in_none'] += len(re.findall(r'«\S', t)) + len(re.findall(r'\S»', t))
    m['mojibake'] += len(MOJIBAKE_RE.findall(t))
    m['lig_bad'] += len(LIG_BAD_RE.findall(t))
    m['lig_good'] += len(LIG_GOOD_RE.findall(t))
    m['caps_bad'] += len(CAPS_BAD_RE.findall(t))
    m['caps_good'] += len(CAPS_GOOD_RE.findall(t))
    m['hyphen_residue'] += len(HYPHEN_RESIDUE_RE.findall(t))

def audit_epub(path):
    m = dict.fromkeys([
        'chars','apos_straight','apos_curly','dq_straight','dq_curly',
        'guil_open','guil_close','nbsp','nnbsp','softhyphen','emdash','endash',
        'ellipsis_char','ellipsis_dots','punct_nbsp','punct_space','punct_none','punct_fakespace',
        'guil_in_nbsp','guil_in_space','guil_in_none','mojibake','lig_bad','lig_good',
        'caps_bad','caps_good','hyphen_residue',
        'dlg_emdash','dlg_endash','dlg_hyphen'], 0)
    info = {'n_docs':0,'n_css':0,'n_fonts':0,'n_images':0,'has_ncx':False,'has_nav':False,
            'fixed_layout':False,'lang_opf':None,'epub_version':None,'encoding_issues':0}
    z = zipfile.ZipFile(path)
    names = z.namelist()
    opf_name = next((n for n in names if n.lower().endswith('.opf')), None)
    if opf_name:
        opf = z.read(opf_name).decode('utf-8', errors='replace')
        info['fixed_layout'] = 'pre-paginated' in opf
        lm = re.search(r'<dc:language[^>]*>([^<]+)</dc:language>', opf)
        if lm: info['lang_opf'] = lm.group(1).strip()
        vm = re.search(r'<package[^>]*version="([^"]+)"', opf)
        if vm: info['epub_version'] = vm.group(1)
    for n in names:
        ln = n.lower()
        if ln.endswith(('.ttf','.otf','.woff','.woff2')): info['n_fonts'] += 1
        elif ln.endswith('.css'): info['n_css'] += 1
        elif ln.endswith(('.jpg','.jpeg','.png','.gif','.svg','.webp')): info['n_images'] += 1
        elif ln.endswith('.ncx'): info['has_ncx'] = True
        if ln.endswith(('.xhtml','.html','.htm')):
            if 'nav' in ln.rsplit('/',1)[-1]: info['has_nav'] = True
            info['n_docs'] += 1
            try:
                raw = z.read(n)
                try:
                    htm = raw.decode('utf-8')
                except UnicodeDecodeError:
                    htm = raw.decode('latin-1', errors='replace')
                    info['encoding_issues'] += 1
                for d in PARA_DASH_RE.findall(htm):
                    d2 = html.unescape(d)
                    if d2 == EMDASH: m['dlg_emdash'] += 1
                    elif d2 == ENDASH: m['dlg_endash'] += 1
                    else: m['dlg_hyphen'] += 1
                body = HEAD_RE.sub('', htm)
                body = STYLE_RE.sub('', body)
                body = TAG_RE.sub('', body)
                body = html.unescape(body)
                text_metrics(body, m)
            except Exception:
                info['encoding_issues'] += 1
    z.close()
    m.update(info)
    return m

def collect_rows(args):
    """Deux modes : bibliothèque Calibre (--calibre BOOKS_DIR INVENTORY.TSV)
    ou simple dossier scanné récursivement pour ses .epub."""
    if args.calibre:
        with open(args.calibre[1]) as f:
            return args.calibre[0], [l.rstrip('\n').split('\t') for l in f if l.strip()]
    rows = []
    i = 0
    for root, _dirs, files in sorted(os.walk(args.path)):
        for fn in sorted(files):
            if fn.lower().endswith('.epub'):
                i += 1
                rel = os.path.relpath(root, args.path)
                rows.append([str(i), '' if rel == '.' else rel,
                             fn[:-5], fn[:-5], '', '', ''])
    return args.path, rows


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('path', nargs='?', help='dossier contenant des .epub (scan récursif)')
    ap.add_argument('out', nargs='?', help='sortie JSONL')
    ap.add_argument('--calibre', nargs=2, metavar=('BOOKS_DIR', 'INVENTORY_TSV'),
                    help='mode Calibre (inventory : id<TAB>path<TAB>name<TAB>titre<TAB>auteurs<TAB>lecteurs<TAB>langue)')
    args = ap.parse_args()
    out_path = args.out if not args.calibre else (args.path or args.out)
    if not out_path:
        ap.error('sortie JSONL manquante')
    books_dir, rows = collect_rows(args)
    done = set()
    if os.path.exists(out_path):
        with open(out_path) as f:
            for line in f:
                try: done.add(json.loads(line)['id'])
                except Exception: pass
    out = open(out_path, 'a')
    for i, row in enumerate(rows, 1):
        bid = int(row[0])
        if bid in done: continue
        rec = {'id': bid, 'path': row[1], 'name': row[2], 'title': row[3],
               'authors': row[4] if len(row) > 4 else '',
               'readers': row[5] if len(row) > 5 else '',
               'lang_db': row[6] if len(row) > 6 else ''}
        epub = os.path.join(books_dir, row[1], row[2] + '.epub')
        if not os.path.exists(epub):
            rec['error'] = 'epub_not_found'
        else:
            rec['size'] = os.path.getsize(epub)
            try:
                rec.update(audit_epub(epub))
            except Exception as e:
                rec['error'] = f'{type(e).__name__}: {e}'
        out.write(json.dumps(rec, ensure_ascii=False) + '\n')
        out.flush()
        if i % 50 == 0:
            print(f'{i}/{len(rows)}', flush=True)
    out.close()
    print('done', flush=True)

if __name__ == '__main__':
    main()
