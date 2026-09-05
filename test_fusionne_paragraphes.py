#!/usr/bin/env python3
"""Tests de fusionne_paragraphes.py — recoudre sans rien perdre."""
import sys, os, re, zipfile, tempfile, subprocess, html
ICI = os.path.dirname(os.path.abspath(__file__))
FAILED = []
def check(n, c):
    print(('✓ ' if c else '✗ ') + n)
    if not c: FAILED.append(n)

COUPE = ('<p class="a">Il aurait fallu un</p>\n'
         '<p class="a"><img src="im1.gif"/></p>\n'
         '<p class="a"> </p>\n'
         '<p class="a">tremblement de terre pour les empêcher.</p>\n'
         '<p class="a">Il s’interrompit.</p>')

def livre(p, corps):
    z = zipfile.ZipFile(p, 'w')
    z.writestr('mimetype', 'application/epub+zip')
    z.writestr('t.htm', '<html><body>%s</body></html>' % corps)
    z.close()

def lance(src, dst, **kw):
    c = [sys.executable, os.path.join(ICI, 'fusionne_paragraphes.py'), src, dst, '--doc', 't.htm']
    for k, v in kw.items():
        c += ['--' + k, v]
    return subprocess.run(c, capture_output=True, text=True)

def vu(p):
    h = zipfile.ZipFile(p).read('t.htm').decode()
    return re.sub(r'\s+', '', html.unescape(re.sub('<[^>]+>', ' ', h))), h

with tempfile.TemporaryDirectory() as t:
    src = os.path.join(t, 'a.epub'); livre(src, COUPE)
    dst = os.path.join(t, 'b.epub')
    r = lance(src, dst, fin='Il aurait fallu un', debut='tremblement de terre')
    check('recoud les deux moitiés', r.returncode == 0)
    av, _ = vu(src); ap, h = vu(dst)
    check('… sans perdre un caractère de texte', av == ap)
    check('… en une seule phrase', 'Il aurait fallu un tremblement de terre' in re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', '', h))))
    check('… avec l’image conservée', h.count('im1.gif') == 1)
    check('… et placée après le paragraphe',
          h.index('tremblement') < h.index('im1.gif'))
    check('… le paragraphe suivant est intact', 'Il s’interrompit.' in h)

    # l'image peut être DANS le premier paragraphe (cas du ch. XIX)
    src2 = os.path.join(t, 'c.epub')
    livre(src2, '<p class="a">répondit Paule. <img src="im2.gif"/></p>\n'
                '<p class="a"> </p>\n<p class="a">Mais Pierre est ici.</p>')
    r = lance(src2, os.path.join(t, 'd.epub'), fin='répondit Paule.', debut='Mais Pierre est ici')
    check('image en fin de premier paragraphe : sortie aussi', r.returncode == 0)
    _, h2 = vu(os.path.join(t, 'd.epub'))
    check('… texte recousu', 'répondit Paule. Mais Pierre est ici.' in
          re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', '', h2))))
    check('… image conservée une fois', h2.count('im2.gif') == 1)

    # refus
    r = lance(src, os.path.join(t, 'e.epub'), fin='inexistant', debut='tremblement de terre')
    check('refuse une ancre introuvable', r.returncode != 0)
    r = lance(src, os.path.join(t, 'f.epub'), fin='tremblement de terre pour les empêcher.',
              debut='Il aurait fallu un')
    check('refuse un ordre inversé', r.returncode != 0)
    src3 = os.path.join(t, 'g.epub')
    livre(src3, '<p class="a">un</p>\n<p class="a">DU TEXTE ENTRE</p>\n<p class="a">deux</p>')
    r = lance(src3, os.path.join(t, 'h.epub'), fin='un', debut='deux')
    check('refuse quand du texte sépare les deux moitiés', r.returncode != 0)
    check('rien écrit quand il refuse', not os.path.exists(os.path.join(t, 'h.epub')))

print('\n' + ('Tous les tests passent.' if not FAILED
              else '%d ÉCHEC(S) : %s' % (len(FAILED), ', '.join(FAILED))))
sys.exit(1 if FAILED else 0)
