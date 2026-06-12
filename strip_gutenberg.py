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


ANCHOR_RE = re.compile(r'\b(?:id|name)\s*=\s*["\']([^"\']+)["\']')
BLOCK_CONTENT_RE = re.compile(r'<(?:%s)[\s>]' % '|'.join(BLOCKS), re.I)


def doc_has_block(htm):
    body = re.search(r'<body[^>]*>(.*)</body>', htm, re.S | re.I)
    return bool(BLOCK_CONTENT_RE.search(body.group(1) if body else htm))


def anchors_in(htm):
    body = re.search(r'<body[^>]*>(.*)</body>', htm, re.S | re.I)
    return set(ANCHOR_RE.findall(body.group(1) if body else htm))


def _target_ok(target, surviving, dropped_files):
    if not target:
        return True
    file_part = target.split('#')[0].split('/')[-1]
    frag = target.split('#')[1] if '#' in target else None
    if file_part and file_part in dropped_files:
        return False
    if frag is not None and frag not in surviving:
        return False
    return True


def prune_ncx(content, surviving, dropped_files):
    """Élague un NCX (navPoints imbriqués) via un vrai parseur XML, puis
    renumérote les playOrder. Retombe sur l'original en cas d'échec de parsing."""
    import xml.etree.ElementTree as ET
    try:
        ET.register_namespace('', 'http://www.daisy.org/z3986/2005/ncx/')
        root = ET.fromstring(content)
    except ET.ParseError:
        return content
    ns = '{http://www.daisy.org/z3986/2005/ncx/}'

    def src_of(np):
        c = np.find(f'{ns}content')
        return c.get('src') if c is not None else None

    def prune(parent):
        for np in list(parent.findall(f'{ns}navPoint')):
            prune(np)  # enfants d'abord
            kids = np.findall(f'{ns}navPoint')
            if not _target_ok(src_of(np), surviving, dropped_files) and not kids:
                parent.remove(np)

    navmap = root.find(f'{ns}navMap')
    if navmap is None:
        return content
    prune(navmap)
    order = [0]
    for np in navmap.iter(f'{ns}navPoint'):
        order[0] += 1
        np.set('playOrder', str(order[0]))
    return ET.tostring(root, encoding='unicode', xml_declaration=True)


def main():
    infile, outfile = sys.argv[1], sys.argv[2]
    zin = zipfile.ZipFile(infile)
    docs = {}        # filename -> html après strip
    dropped = set()  # docs vidés, retirés du spine
    total = 0
    other = {}       # autres fichiers (opf, ncx, images…)
    order = []
    for item in zin.infolist():
        if item.filename == 'mimetype':
            continue
        order.append(item)
        data = zin.read(item.filename)
        low = item.filename.lower()
        if low.endswith(('.html', '.htm', '.xhtml')):
            htm = data.decode('utf-8', errors='replace')
            if 'utenberg' in htm:
                new, removed = strip_doc(htm)
                if removed:
                    bal_o, bal_n = tag_balance(htm), tag_balance(new)
                    drift = any((bal_o[b][0] - bal_o[b][1]) != (bal_n[b][0] - bal_n[b][1])
                                for b in BLOCKS)
                    if drift:
                        print(f'⚠ {item.filename}: déséquilibre de balises — laissé intact')
                    else:
                        htm = new
                        total += removed
                        print(f'{item.filename}: −{removed} chars')
                if not doc_has_block(htm):
                    dropped.add(item.filename.split('/')[-1])
                    print(f'{item.filename}: document vidé (100 % boilerplate) → retiré du spine')
            docs[item.filename] = htm
        else:
            other[item.filename] = data

    # ancres survivantes (hors documents retirés)
    surviving = set()
    for fn, htm in docs.items():
        if fn.split('/')[-1] not in dropped:
            surviving |= anchors_in(htm)

    # écrire la sortie en réparant NCX, nav, OPF
    out = zipfile.ZipFile(outfile, 'w')
    out.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                 compress_type=zipfile.ZIP_STORED)
    for item in order:
        fn = item.filename
        if fn in docs:
            if fn.split('/')[-1] in dropped:
                continue  # ne pas réécrire le document vidé
            data = docs[fn].encode('utf-8')
        else:
            data = other[fn]
            low = fn.lower()
            if low.endswith('.ncx'):
                t = data.decode('utf-8', 'replace')
                t = prune_ncx(t, surviving, dropped)
                data = t.encode('utf-8')
            elif low.endswith('.opf'):
                t = data.decode('utf-8', 'replace')
                t = prune_opf(t, dropped)
                data = t.encode('utf-8')
            elif 'nav' in low.rsplit('/', 1)[-1] and low.endswith(('.xhtml', '.html')):
                pass  # nav docs traités comme docs ci-dessus
        info = zipfile.ZipInfo(fn, date_time=item.date_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        out.writestr(info, data)
    out.close()
    zin.close()
    print(f'total retiré : {total} chars'
          + (f', {len(dropped)} doc(s) retiré(s)' if dropped else ''))


def prune_opf(opf, dropped):
    """Retire du manifeste et du spine les items pointant vers un doc supprimé."""
    if not dropped:
        return opf
    # ids des items à retirer
    drop_ids = set()
    def item_repl(m):
        tag = m.group(0)
        href = re.search(r'href\s*=\s*["\']([^"\']+)["\']', tag)
        if href and href.group(1).split('/')[-1] in dropped:
            idm = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', tag)
            if idm:
                drop_ids.add(idm.group(1))
            return ''
        return tag
    opf = re.compile(r'<item\b[^>]*/?>', re.I).sub(item_repl, opf)
    def itemref_repl(m):
        idref = re.search(r'idref\s*=\s*["\']([^"\']+)["\']', m.group(0))
        if idref and idref.group(1) in drop_ids:
            return ''
        return m.group(0)
    opf = re.compile(r'<itemref\b[^>]*/?>', re.I).sub(itemref_repl, opf)
    return opf


if __name__ == '__main__':
    main()
