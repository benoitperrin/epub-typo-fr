#!/usr/bin/env python3
"""Tests de kobo_reancre.py — le recollage d'une ancre d'annotation."""
import sys, os, re, sqlite3, zipfile, tempfile, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kobo_reancre import cle, localiser, spans_du_fichier

FAILED = []
def check(nom, cond):
    print(('✓ ' if cond else '✗ ') + nom)
    if not cond:
        FAILED.append(nom)

# --- la clé de comparaison ignore la typographie, pas les mots ----------------
check('clé : l’insécable ne compte pas', cle('rien ! » dit') == cle('rien! » dit'))
check('clé : le cadratin vaut le trait d’union', cle('— Elle') == cle('-Elle'))
check('clé : « … » vaut « ... »', cle('froid… froid') == cle('froid... froid'))
check('clé : l’apostrophe courbe vaut la droite', cle('l’œil') == cle("l'oeil"))
check('clé : deux textes différents restent différents', cle('la meule') != cle('la moule'))

# --- localiser : le cas qui motive l'outil, un span absorbé par son voisin ----
AVANT = [('kobo.2.1', 'Si ce temps de chien ne cesse pas bientôt'),
         ('kobo.2.2', '! » déclara la femme.'),
         ('kobo.3.1', 'Une bourrasque s’engouffra.')]
APRES = [('kobo.2.1', 'Si ce temps de chien ne cesse pas bientôt ! » déclara la femme.'),
         ('kobo.2.2', 'Une bourrasque s’engouffra.')]
r = localiser(APRES, '! » déclara la femme.')
check('localiser : retrouve un texte passé dans le span précédent',
      r is not None and r[0] == 'kobo.2.1' and r[1] > 0)
r2 = localiser(APRES, 'Une bourrasque s’engouffra.')
check('localiser : suit le décalage de numérotation',
      r2 is not None and r2[0] == 'kobo.2.2')
check('localiser : texte absent → rien (on ne devine pas)',
      localiser(APRES, 'phrase qui n’existe pas ici') is None)
check('localiser : texte répété → rien (ambigu, on ne tranche pas)',
      localiser([('kobo.1.1', 'oui. oui.')], 'oui.') is None)
r3 = localiser(APRES, 'bientôt ! » déclara')
check('localiser : tolère la typographie changée entre les deux versions',
      r3 is not None and r3[0] == 'kobo.2.1')

# --- bout en bout : un vrai zip, une vraie base, l'écriture -------------------
def kepub(path, spans, fichier='OPS/book_0002.xhtml'):
    z = zipfile.ZipFile(path, 'w')
    z.writestr('mimetype', 'application/epub+zip')
    corps = ''.join('<span class="koboSpan" id="%s">%s</span>' % s for s in spans)
    z.writestr(fichier, '<html><body><p>%s</p></body></html>' % corps)
    z.close()

with tempfile.TemporaryDirectory() as t:
    av, ap = os.path.join(t, 'a.kepub'), os.path.join(t, 'b.kepub')
    kepub(av, AVANT); kepub(ap, APRES)
    dbp = os.path.join(t, 'KoboReader.sqlite')
    db = sqlite3.connect(dbp)
    db.execute('CREATE TABLE Bookmark (BookmarkID TEXT PRIMARY KEY, VolumeID TEXT NOT NULL, '
               'ContentID TEXT NOT NULL, StartContainerPath TEXT NOT NULL, StartOffset INTEGER, '
               'EndContainerPath TEXT NOT NULL, EndOffset INTEGER, Text TEXT, Type TEXT)')
    db.execute("INSERT INTO Bookmark VALUES ('b1','v','u!OPS!book_0002.xhtml',"
               "'span#kobo\\.2\\.2',0,'span#kobo\\.2\\.2',21,'! » déclara la femme.','highlight')")
    db.commit(); db.close()
    outil = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kobo_reancre.py')
    sec = subprocess.run([sys.executable, outil, dbp, '--avant', av, '--apres', ap],
                         capture_output=True, text=True)
    check('à blanc : annonce le recollage', '1 à recoller' in sec.stdout)
    db = sqlite3.connect(dbp)
    check('à blanc : n’écrit rien',
          db.execute('SELECT StartContainerPath FROM Bookmark').fetchone()[0] == 'span#kobo\\.2\\.2')
    db.close()
    subprocess.run([sys.executable, outil, dbp, '--avant', av, '--apres', ap, '--go'],
                   capture_output=True, text=True)
    db = sqlite3.connect(dbp)
    sp, so, eo = db.execute('SELECT StartContainerPath, StartOffset, EndOffset FROM Bookmark').fetchone()
    check('--go : l’ancre pointe le span fusionné', sp == 'span#kobo\\.2\\.1')
    z = zipfile.ZipFile(ap)
    h = z.read('OPS/book_0002.xhtml').decode()
    txt = re.search(r'id="kobo\.2\.1">(.*?)</span>', h).group(1)
    check('--go : les bornes désignent le texte surligné',
          cle(txt[so:eo]) == cle('! » déclara la femme.'))
    check('--go : une sauvegarde a été posée', os.path.exists(dbp + '.avant-reancrage'))
    db.close()

print('\n' + ('Tous les tests passent.' if not FAILED
              else '%d ÉCHEC(S) : %s' % (len(FAILED), ', '.join(FAILED))))
sys.exit(1 if FAILED else 0)
