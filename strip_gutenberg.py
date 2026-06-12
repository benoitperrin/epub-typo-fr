#!/usr/bin/env python3
"""
strip_gutenberg.py — Retire le boilerplate Project Gutenberg d'un EPUB
(en-tête avant « *** START OF … *** » et licence après « *** END OF … *** »).

Requis pour rediffuser une édition modifiée : la licence PG impose de retirer
la marque Project Gutenberg des textes dérivés. Le texte de l'œuvre (domaine
public) est conservé intégralement entre les deux marqueurs.

La coupe se fait aux frontières de blocs HTML ; l'équilibre des balises de
chaque document est vérifié avant/après (p, div, pre, h1-h6, table) — un
document qui dévierait est laissé intact et signalé.

Usage: python3 strip_gutenberg.py in.epub out.epub
"""
import sys, re, zipfile

START_RE = re.compile(r'\*\*\*\s*START OF [^*<]*\*{0,3}', re.I)
END_RE = re.compile(r'\*\*\*\s*END OF|End of (?:the |this )?Project Gutenberg', re.I)
PRODUCED_RE = re.compile(r'Produced by [^<]{0,400}?(?:format|gutenberg|ebooksgratuits)[^<]{0,200}', re.I)
LICENSE_DOC_RE = re.compile(r'accordance with paragraph|Literary Archive Foundation|full Project Gutenberg', re.I)
FR_HINT_RE = re.compile(r'[éèêàçœù]')
BODY_OPEN_RE = re.compile(r'<body[^>]*>', re.I)
BLOCKS = ('p', 'div', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'blockquote')


def tag_balance(htm):
    out = {}
    for b in BLOCKS:
        out[b] = (len(re.findall(r'<%s[\s>]' % b, htm, re.I)),
                  len(re.findall(r'</%s\s*>' % b, htm, re.I)))
    return out


def strip_doc(htm):
    """Retourne (nouveau_html, nb_chars_retirés)."""
    removed = 0
    # document de licence pure (suite de licence sans marqueur, conversions ELG) :
    # vocabulaire de licence présent ET quasi pas de caractères accentués français
    body_text = re.sub(r'<[^>]+>', ' ', re.sub(r'<head\b.*?</head>', '', htm, flags=re.S | re.I))
    if LICENSE_DOC_RE.search(body_text):
        accents = len(FR_HINT_RE.findall(body_text))
        if accents < len(body_text) / 2000:  # < 0,05 % de caractères accentués
            body = BODY_OPEN_RE.search(htm)
            close = htm.lower().rfind('</body>')
            if body and close > body.end():
                removed = close - body.end()
                return htm[:body.end()] + '\n' + htm[close:], removed
    # paragraphe de crédit « Produced by … » en tête de document
    m = PRODUCED_RE.search(htm[:6000])
    if m:
        close = re.compile(r'</(?:%s)\s*>' % '|'.join(BLOCKS), re.I)
        opens = [x for x in re.finditer(r'<(?:%s)[\s>]' % '|'.join(BLOCKS), htm[:m.start()], re.I)]
        c = close.search(htm, m.end())
        if opens and c:
            removed += c.end() - opens[-1].start()
            htm = htm[:opens[-1].start()] + '\n' + htm[c.end():]
    m = START_RE.search(htm)
    if m:
        body = BODY_OPEN_RE.search(htm)
        if body and body.end() < m.start():
            # fin du bloc contenant le marqueur : prochaine fermeture de bloc
            close = re.compile(r'</(?:%s)\s*>' % '|'.join(BLOCKS), re.I)
            c = close.search(htm, m.end())
            cut_end = c.end() if c else m.end()
            removed += cut_end - body.end()
            htm = htm[:body.end()] + '\n' + htm[cut_end:]
    m = END_RE.search(htm)
    if m:
        # début du bloc contenant le marqueur : dernière ouverture de bloc avant lui
        opens = [x for x in re.finditer(r'<(?:%s)[\s>]' % '|'.join(BLOCKS), htm[:m.start()], re.I)]
        body_close = htm.lower().rfind('</body>')
        if opens and body_close > m.start():
            cut_start = opens[-1].start()
            removed += body_close - cut_start
            htm = htm[:cut_start] + '\n' + htm[body_close:]
    return htm, removed


def main():
    infile, outfile = sys.argv[1], sys.argv[2]
    zin = zipfile.ZipFile(infile)
    out = zipfile.ZipFile(outfile, 'w')
    out.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                 compress_type=zipfile.ZIP_STORED)
    total = 0
    for item in zin.infolist():
        if item.filename == 'mimetype':
            continue
        data = zin.read(item.filename)
        if item.filename.lower().endswith(('.html', '.htm', '.xhtml')):
            htm = data.decode('utf-8', errors='replace')
            if 'utenberg' in htm:
                new, removed = strip_doc(htm)
                if removed:
                    bal_o, bal_n = tag_balance(htm), tag_balance(new)
                    drift = any((bal_o[b][0] - bal_o[b][1]) != (bal_n[b][0] - bal_n[b][1])
                                for b in BLOCKS)
                    if drift:
                        print(f'⚠ {item.filename}: déséquilibre de balises après coupe — laissé intact')
                    else:
                        data = new.encode('utf-8')
                        total += removed
                        print(f'{item.filename}: −{removed} chars')
        info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        out.writestr(info, data)
    out.close()
    zin.close()
    print(f'total retiré : {total} chars')


if __name__ == '__main__':
    main()
