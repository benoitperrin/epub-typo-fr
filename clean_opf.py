#!/usr/bin/env python3
"""
clean_opf.py — Nettoie les métadonnées OPF d'un EPUB de domaine public retypographié,
pour une rediffusion propre (Wikisource, ELG, dépôt personnel).

- supprime les identifiants/sources Project Gutenberg / ebooksgratuits
- pose dc:rights = domaine public, dc:language = fr
- ajoute un dc:contributor décrivant la remise à niveau (typographie + OCR)
- conserve titre, auteur, dates d'origine de l'œuvre

Le reste de l'EPUB (texte, structure) est intact.

Usage:
  python3 clean_opf.py in.epub out.epub --titre "..." --auteur "..." \
      [--note "Édition retypographiée ..."] [--id "urn:..."]
"""
import sys, re, zipfile, argparse

# éléments purement supprimables (pas l'identifiant unique : voir plus bas)
GUT_PATTERNS = [
    re.compile(r'<dc:source[^>]*>[^<]*(?:gutenberg|ebooksgratuits)[^<]*</dc:source>', re.I),
    re.compile(r'<dc:publisher[^>]*>[^<]*(?:gutenberg|ebooksgratuits)[^<]*</dc:publisher>', re.I),
    re.compile(r'<dc:rights[^>]*>.*?</dc:rights>', re.I | re.S),
    re.compile(r'<dc:contributor[^>]*>[^<]*(?:gutenberg|distributed proofreaders)[^<]*</dc:contributor>', re.I),
]
IDENT_RE = re.compile(r'(<dc:identifier[^>]*>)([^<]*)(</dc:identifier>)', re.I)


def clean_opf(opf, titre, auteur, note, ident):
    # 1) identifiants Gutenberg/URL : remplacer le CONTENU (l'élément peut être
    #    l'unique-identifier du package — le supprimer casserait l'EPUB).
    new_id = ident or 'urn:epub-typo-fr:' + re.sub(r'\W+', '-', (titre or 'livre').lower()).strip('-')
    def repl_id(m):
        txt = m.group(2)
        if re.search(r'gutenberg|ebooksgratuits|^https?:', txt, re.I):
            return m.group(1) + new_id + m.group(3)
        return m.group(0)
    opf = IDENT_RE.sub(repl_id, opf)
    for p in GUT_PATTERNS:
        opf = p.sub('', opf)
    # 2) nom d'auteur mal formé fréquent (« comtesse de Sophie Ségur »)
    if auteur:
        opf = re.sub(r'(<dc:creator[^>]*>)[^<]*(</dc:creator>)', r'\g<1>' + auteur + r'\g<2>', opf)
    # injecter les métadonnées propres juste avant </metadata>
    add = []
    add.append('<dc:rights>Domaine public — œuvre. Édition (corrections typographiques et OCR) versée au domaine public / CC0.</dc:rights>')
    if note:
        add.append(f'<dc:contributor opf:role="edt">{note}</dc:contributor>')
    if titre and '<dc:title' not in opf:
        add.append(f'<dc:title>{titre}</dc:title>')
    if auteur and '<dc:creator' not in opf:
        add.append(f'<dc:creator>{auteur}</dc:creator>')
    if 'xmlns:opf' not in opf:
        opf = opf.replace('<metadata', '<metadata xmlns:opf="http://www.idpf.org/2007/opf"', 1)
    opf = re.sub(r'</metadata>', '\n  ' + '\n  '.join(add) + '\n</metadata>', opf, count=1)
    # nettoyer les lignes vides résiduelles
    opf = re.sub(r'\n\s*\n+', '\n', opf)
    return opf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('infile'); ap.add_argument('outfile')
    ap.add_argument('--titre', default=''); ap.add_argument('--auteur', default='')
    ap.add_argument('--note', default='Texte du domaine public ; typographie française et corrections OCR par epub-typo-fr.')
    ap.add_argument('--id', default='')
    args = ap.parse_args()
    zin = zipfile.ZipFile(args.infile)
    out = zipfile.ZipFile(args.outfile, 'w')
    out.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                 compress_type=zipfile.ZIP_STORED)
    for item in zin.infolist():
        if item.filename == 'mimetype':
            continue
        data = zin.read(item.filename)
        if item.filename.lower().endswith('.opf'):
            data = clean_opf(data.decode('utf-8', 'replace'),
                             args.titre, args.auteur, args.note, args.id).encode('utf-8')
        info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        out.writestr(info, data)
    out.close(); zin.close()
    print(f'OPF nettoyé → {args.outfile}')


if __name__ == '__main__':
    main()
