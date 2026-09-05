#!/usr/bin/env python3
"""
fusionne_paragraphes.py — Recoudre une phrase qu'une illustration a coupée en deux.

Défaut de série des numérisations amateur passées par Word : l'image est insérée au
milieu d'un paragraphe, ce qui force la fermeture du <p> avant elle et l'ouverture
d'un autre après. Le texte est complet, mais il se lit en deux morceaux, avec un
alinéa au milieu d'une phrase :

    <p>… Il aurait fallu un</p>
    <p><img src="image021.gif"/></p>
    <p> </p>
    <p>tremblement de terre pour les empêcher de travailler ! »</p>

Trois cas dans La locomotive du Club des Cinq #649. ocr_apply.py ne peut rien ici :
il refuse par construction de toucher au balisage. Cet outil ne fait que ce geste —
réunir les deux moitiés et sortir l'illustration du milieu de la phrase.

  fusionne_paragraphes.py in.epub out.epub --doc <fichier>
      --fin "…fallu un" --debut "tremblement de terre" [--raison "…"]

`--fin` : la fin du premier morceau. `--debut` : le début du second. Les deux doivent
être uniques dans le document. L'illustration est replacée APRÈS le paragraphe
recousu, sa place naturelle : on lit la phrase entière, puis on voit l'image.

Garanties vérifiées après coup, sinon rien n'est écrit :
  - chaque ancre apparaît exactement une fois ;
  - les deux paragraphes se suivent, ne séparés que par des images ou du blanc ;
  - le texte visible est conservé mot pour mot (une espace apparaît à la jointure) ;
  - aucune balise n'est perdue : l'image est déplacée, jamais supprimée.
"""
import sys, re, html, zipfile, argparse

P_RE = re.compile(r'<p\b[^>]*>.*?</p>', re.S)
TAG_RE = re.compile(r'(<[^>]+>|<!--.*?-->)', re.S)


def texte(p):
    return html.unescape(TAG_RE.sub('', p))


def mots(s):
    return re.sub(r'\s+', ' ', s).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('infile'); ap.add_argument('outfile')
    ap.add_argument('--doc', required=True)
    ap.add_argument('--fin', required=True, help='fin du premier morceau')
    ap.add_argument('--debut', required=True, help='début du second morceau')
    ap.add_argument('--raison', default='')
    a = ap.parse_args()

    zin = zipfile.ZipFile(a.infile)
    if a.doc not in zin.namelist():
        sys.exit('document absent du livre : %s' % a.doc)
    htm = zin.read(a.doc).decode('utf-8', 'replace')

    blocs = [(m.start(), m.end(), m.group(0)) for m in P_RE.finditer(htm)]
    i1 = [k for k, (_, _, p) in enumerate(blocs) if mots(texte(p)).endswith(mots(a.fin))]
    i2 = [k for k, (_, _, p) in enumerate(blocs) if mots(texte(p)).startswith(mots(a.debut))]
    if len(i1) != 1 or len(i2) != 1:
        sys.exit('ancres non uniques : %d paragraphe(s) finissent par « %s », '
                 '%d commencent par « %s »' % (len(i1), a.fin, len(i2), a.debut))
    k1, k2 = i1[0], i2[0]
    if k2 <= k1:
        sys.exit('le second morceau ne suit pas le premier')
    # entre les deux : seulement des images ou du blanc
    for k in range(k1 + 1, k2):
        t = mots(texte(blocs[k][2]))
        if t or ('<img' not in blocs[k][2] and t == '' and '<' not in blocs[k][2]):
            if t:
                sys.exit('du texte sépare les deux morceaux : « %s »' % t[:60])

    images = [blocs[k][2] for k in range(k1 + 1, k2) if '<img' in blocs[k][2]]
    # une image peut aussi être DANS le premier paragraphe, en fin (cas du ch. XIX)
    p1, p2 = blocs[k1][2], blocs[k2][2]
    imgs_p1 = re.findall(r'<img\b[^>]*/?>', p1)
    p1_sans = re.sub(r'<img\b[^>]*/?>', '', p1)

    ouvrant = re.match(r'<p\b[^>]*>', p1).group(0)
    corps = re.sub(r'</p>\s*$', '', p1_sans[len(ouvrant):]).rstrip()
    suite = re.sub(r'^<p\b[^>]*>', '', p2)
    fusion = ouvrant + corps + ' ' + suite
    bloc_img = ''.join('\n\n%s%s</p>' % (ouvrant, im) for im in imgs_p1 + [
        i for b in (b for b in blocs[k1 + 1:k2] if '<img' in b[2])
        for i in re.findall(r'<img\b[^>]*/?>', b[2])])

    neuf = htm[:blocs[k1][0]] + fusion + bloc_img + htm[blocs[k2][1]:]

    # contrôle 1 — le texte visible est conservé mot pour mot
    if mots(texte(neuf)) != mots(texte(htm)):
        sys.exit('REFUS : le texte visible aurait changé')
    # contrôle 2 — aucune image perdue
    av, ap_ = re.findall(r'src="([^"]+)"', htm), re.findall(r'src="([^"]+)"', neuf)
    if sorted(av) != sorted(ap_):
        sys.exit('REFUS : %d image(s) au lieu de %d' % (len(ap_), len(av)))
    # contrôle 3 — les <p> ne diminuent que du nombre attendu
    n_av, n_ap = len(P_RE.findall(htm)), len(P_RE.findall(neuf))
    if n_ap >= n_av:
        sys.exit('REFUS : le nombre de paragraphes n’a pas diminué (%d → %d)' % (n_av, n_ap))

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
    j = mots(texte(fusion))
    d = len(mots(corps))
    print('✓ recousu dans %s — …%s…' % (a.doc, j[max(0, d - 45):d + 45]))
    print('  %d paragraphe(s) en moins, %d illustration(s) replacée(s) après'
          % (n_av - n_ap, len(imgs_p1) + len(images)))
    if a.raison:
        print('  %s' % a.raison)


if __name__ == '__main__':
    main()
