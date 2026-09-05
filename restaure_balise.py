#!/usr/bin/env python3
"""
restaure_balise.py — Rendre à un mot l'emphase que la copie lui a prise.

ocr_apply.py refuse par construction de toucher au balisage : c'est ce qui garantit
son innocuité. Mais une numérisation perd aussi des ITALIQUES, et les restaurer
demande précisément d'ajouter une balise. « on a quelquefois beaucoup du tourment
dans notre métier » — le témoin Wikisource met « du » en italique, marqueur
d'idiotisme comme « pountoura » deux lignes plus haut ; notre copie l'a perdu.

Cet outil fait ce geste-là, et rien d'autre : envelopper une chaîne UNIQUE d'un
élément en ligne, sous garanties vérifiées.

  restaure_balise.py in.epub out.epub --doc <fichier> --texte "du" \\
      --contexte "beaucoup du tourment" [--balise i] [--raison "…"]

Garanties, toutes vérifiées après coup, sinon le document est laissé intact :
  - le contexte apparaît EXACTEMENT une fois dans le document, hors balise ;
  - le texte visible du document est strictement inchangé (on ajoute du balisage,
    jamais un caractère de texte) ;
  - la séquence de balises ne gagne QUE la paire demandée, au bon endroit.
"""
import sys, re, html, zipfile, argparse

TAG_RE = re.compile(r'(<[^>]+>|<!--.*?-->)', re.S)
INLINE = {'i', 'em', 'b', 'strong', 'span', 'sup', 'sub', 'u', 'small'}


def texte_visible(htm):
    corps = re.sub(r'<(style|script)\b.*?</\1>', '', htm, flags=re.S | re.I)
    return html.unescape(TAG_RE.sub('', corps))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('infile'); ap.add_argument('outfile')
    ap.add_argument('--doc', required=True)
    ap.add_argument('--texte', required=True, help='le mot à envelopper')
    ap.add_argument('--contexte', required=True, help='chaîne unique qui le contient')
    ap.add_argument('--balise', default='i')
    ap.add_argument('--raison', default='')
    a = ap.parse_args()

    if a.balise not in INLINE:
        sys.exit('balise « %s » non autorisée : seulement %s' % (a.balise, ', '.join(sorted(INLINE))))
    if a.texte not in a.contexte:
        sys.exit('le texte « %s » n’est pas dans le contexte donné' % a.texte)

    zin = zipfile.ZipFile(a.infile)
    if a.doc not in zin.namelist():
        sys.exit('document absent du livre : %s' % a.doc)
    htm = zin.read(a.doc).decode('utf-8', 'replace')

    # le contexte doit vivre dans UN seul nœud de texte, et n'y être qu'une fois
    parts = TAG_RE.split(htm)
    cibles = [i for i, p in enumerate(parts)
              if not p.startswith('<') and html.unescape(p).count(a.contexte) == 1]
    total = sum(html.unescape(p).count(a.contexte) for p in parts if not p.startswith('<'))
    if total != 1 or len(cibles) != 1:
        sys.exit('contexte trouvé %d fois (attendu 1, dans un seul nœud)' % total)

    i = cibles[0]
    avant = html.unescape(parts[i])
    d = avant.index(a.contexte) + a.contexte.index(a.texte)
    f = d + len(a.texte)
    parts[i] = (html.escape(avant[:d], quote=False)
                + '<%s>' % a.balise + html.escape(avant[d:f], quote=False) + '</%s>' % a.balise
                + html.escape(avant[f:], quote=False))
    neuf = ''.join(parts)

    # contrôle 1 — le texte visible n'a pas bougé d'un caractère
    if texte_visible(neuf) != texte_visible(htm):
        sys.exit('REFUS : le texte visible aurait changé')
    # contrôle 2 — la séquence de balises ne gagne que la paire demandée
    av, ap_ = TAG_RE.findall(htm), TAG_RE.findall(neuf)
    gain = [t for t in ap_ if t not in av] or []
    if len(ap_) != len(av) + 2:
        sys.exit('REFUS : %d balises au lieu de %d attendues' % (len(ap_), len(av) + 2))
    # les deux balises ajoutées doivent être exactement <balise> et </balise>
    import difflib
    ajouts = [t for op, s in ((o[0], o) for o in difflib.SequenceMatcher(a=av, b=ap_).get_opcodes())
              if op == 'insert' for t in ap_[s[3]:s[4]]]
    if sorted(ajouts) != sorted(['<%s>' % a.balise, '</%s>' % a.balise]):
        sys.exit('REFUS : balises ajoutées inattendues %r' % ajouts)

    out = zipfile.ZipFile(a.outfile, 'w')
    out.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                 compress_type=zipfile.ZIP_STORED)
    for item in zin.infolist():
        if item.filename == 'mimetype':
            continue
        data = neuf.encode('utf-8') if item.filename == a.doc else zin.read(item.filename)
        info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        out.writestr(info, data)
    out.close()
    ctx = avant[max(0, d - 40):f + 30].replace('\n', ' ')
    print('✓ <%s> posé dans %s — …%s…' % (a.balise, a.doc, ctx))
    if a.raison:
        print('  %s' % a.raison)


if __name__ == '__main__':
    main()
