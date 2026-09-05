#!/usr/bin/env python3
"""
kobo_reancre.py — Recoller les surlignages d'une Kobo après un changement de KEPUB.

Le problème : un surlignage est ancré sur « span#kobo.N.M » dans un fichier du
spine. Une passe typographique déplace ces ids — l'insécable posée entre « ! » et
« » » supprime une frontière de phrase pour kepubify, « ... » → « … » aussi — si
bien qu'après remplacement l'ancre pointe une phrase plus loin, en silence.
Mesuré : 44 % à 82 % d'ancres intactes selon les livres.

La prise : la table Bookmark garde dans `Text` une COPIE FIGÉE du texte surligné.
C'est l'invariant qui manque à l'ancre. On retrouve ce texte dans le nouveau
KEPUB et on réécrit StartContainerPath / StartOffset / EndContainerPath /
EndOffset. Le texte prime sur la position : c'est lui que le lecteur a choisi.

  kobo_reancre.py KoboReader.sqlite --avant ancien.kepub --apres nouveau.kepub
                  [--volume <VolumeID ou fragment>] [--go]

Sans --go, rien n'est écrit : le plan de réancrage est affiché.

⚠ Lire la base d'une Kobo demande ses trois fichiers — KoboReader.sqlite, -wal et
-shm — ou un démontage propre. Le mode WAL a déjà fait conclure à tort à une
destruction d'annotations (04/09/2026).
"""
import sys, os, re, html, sqlite3, zipfile, argparse, unicodedata, shutil

SPAN = re.compile(r'<span class="koboSpan" id="(kobo\.[\d.]+)">(.*?)</span>', re.S)


def spans_du_fichier(kepub, suffixe):
    """[(id, texte)] du fichier du spine dont le nom finit par `suffixe`."""
    z = zipfile.ZipFile(kepub)
    noms = [n for n in z.namelist()
            if n.lower().endswith(('.htm', '.html', '.xhtml')) and n.endswith(suffixe)]
    if not noms:
        base = suffixe.split('/')[-1]
        noms = [n for n in z.namelist() if n.endswith(base)]
    if not noms:
        return None, []
    h = z.read(noms[0]).decode('utf-8', 'replace')
    return noms[0], [(m.group(1), html.unescape(re.sub('<[^>]+>', '', m.group(2))))
                     for m in SPAN.finditer(h)]


def cle(t):
    """Texte comparable : la passe change la typographie, pas les mots."""
    t = unicodedata.normalize('NFKD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    for a, b in (('’', "'"), ('…', '...'), ('—', '-'), ('–', '-'), ('œ', 'oe'), ('Œ', 'OE'),
                 ('«', '"'), ('»', '"')):
        t = t.replace(a, b)
    return re.sub(r'\s+', '', t).lower()


def lecture(spans, sp, so, ep, eo):
    """Ce que l'ancre actuelle donne à lire, telle quelle."""
    d = sp.replace('span#', '').replace('\\', '')
    f = ep.replace('span#', '').replace('\\', '')
    idx = {sid: i for i, (sid, _) in enumerate(spans)}
    if d not in idx or f not in idx:
        return None
    if d == f:
        return spans[idx[d]][1][so:eo]
    i, j = idx[d], idx[f]
    if j < i:
        return None
    return spans[i][1][so:] + ''.join(t for _, t in spans[i + 1:j]) + spans[j][1][:eo]


def localiser(spans, texte):
    """Où le texte tombe-t-il dans cette suite de spans ?
    Rend (span_debut, offset_debut, span_fin, offset_fin) ou None."""
    plat, bornes = '', []          # bornes : (position dans `plat`, id, offset dans le span)
    for sid, s in spans:
        for i, c in enumerate(s):
            k = cle(c)
            if k:                  # on n'indexe que les caractères qui comptent
                bornes.append((len(plat), sid, i))
                plat += k
    k = cle(texte)
    if not k:
        return None
    p = plat.find(k)
    if p < 0 or plat.find(k, p + 1) >= 0:
        return None                # introuvable, ou ambigu : on ne devine pas
    fin = p + len(k) - 1
    deb_b = max((b for b in bornes if b[0] <= p), key=lambda b: b[0], default=None)
    fin_b = max((b for b in bornes if b[0] <= fin), key=lambda b: b[0], default=None)
    if not deb_b or not fin_b:
        return None
    return deb_b[1], deb_b[2], fin_b[1], fin_b[2] + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('db')
    ap.add_argument('--avant', help='KEPUB d’avant — facultatif : le recollage se fait '
                                    'sur le texte figé de l’annotation, pas sur l’ancienne ancre')
    ap.add_argument('--apres', required=True, help='KEPUB déployé')
    ap.add_argument('--volume', help='VolumeID ou fragment (défaut : tous les livres annotés)')
    ap.add_argument('--go', action='store_true', help='écrire (sinon : plan seulement)')
    a = ap.parse_args()

    if a.go:
        sauve = a.db + '.avant-reancrage'
        shutil.copy2(a.db, sauve)
        print(f'sauvegarde : {sauve}')

    db = sqlite3.connect(a.db)
    q = ("SELECT BookmarkID, ContentID, StartContainerPath, StartOffset, "
         "EndContainerPath, EndOffset, Text, Type FROM Bookmark "
         "WHERE Text IS NOT NULL AND Text <> ''")
    if a.volume:
        q += " AND VolumeID LIKE '%%%s%%'" % a.volume.replace("'", "''")
    rows = db.execute(q).fetchall()
    print(f'{len(rows)} annotation(s) à examiner\n')

    maj, inchange, perdu = [], 0, []
    for bid, cid, sp, so, ep, eo, texte, typ in rows:
        suffixe = cid.split('!')[-1]
        nom, spans = spans_du_fichier(a.apres, suffixe)
        if not spans:
            perdu.append((bid, texte, 'fichier « %s » absent du nouveau KEPUB' % suffixe))
            continue
        # Une ancre qui donne déjà à lire le bon texte n'est pas cassée : on n'y
        # touche pas, même si l'outil saurait l'écrire autrement. Un surlignage à
        # cheval sur deux spans s'écrit de plusieurs façons équivalentes, et
        # réécrire ce qui va bien, c'est prendre un risque pour rien.
        actuel = lecture(spans, sp, so, ep, eo)
        if actuel is not None and cle(actuel) == cle(texte):
            inchange += 1
            continue
        r = localiser(spans, texte)
        if not r:
            perdu.append((bid, texte, 'texte introuvable ou ambigu dans le nouveau KEPUB'))
            continue
        nsp, nso, nep, neo = r
        anc = (sp, so, ep, eo)
        nouv = ('span#' + nsp.replace('.', r'\.'), nso, 'span#' + nep.replace('.', r'\.'), neo)
        maj.append((bid, anc, nouv, texte, typ))

    def montre(a):
        d = a[0].replace('span#', '').replace('\\', '')
        f = a[2].replace('span#', '').replace('\\', '')
        return '%s+%d → %s+%d' % (d, a[1], f, a[3])
    for bid, anc, nouv, texte, typ in maj:
        print('  %-8s %-9s %-28s  ⇒  %s' % (bid[:8], typ, montre(anc), montre(nouv)))
        print('           « %s »' % re.sub(r'\s+', ' ', texte)[:70])
    print('\n%d à recoller, %d déjà justes, %d sans solution' % (len(maj), inchange, len(perdu)))
    for bid, texte, why in perdu:
        print('  ⚠ %-8s %s — « %s »' % (bid[:8], why, re.sub(r'\s+', ' ', texte)[:50]))

    if a.go and maj:
        for bid, _, (nsp, nso, nep, neo), _, _ in maj:
            db.execute('UPDATE Bookmark SET StartContainerPath=?, StartOffset=?, '
                       'EndContainerPath=?, EndOffset=? WHERE BookmarkID=?',
                       (nsp, nso, nep, neo, bid))
        db.commit()
        print(f'\n{len(maj)} annotation(s) recollée(s).')
    elif maj:
        print('\n(rien écrit — relancer avec --go)')


if __name__ == '__main__':
    main()
