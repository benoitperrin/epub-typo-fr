#!/usr/bin/env python3
"""Tests de restaure_balise.py — il ajoute une balise, et rien d'autre."""
import sys, os, re, zipfile, tempfile, subprocess
ICI = os.path.dirname(os.path.abspath(__file__))
FAILED = []
def check(n, c):
    print(('✓ ' if c else '✗ ') + n)
    if not c: FAILED.append(n)

def livre(p, corps):
    z = zipfile.ZipFile(p, 'w')
    z.writestr('mimetype', 'application/epub+zip')
    z.writestr('t.htm', '<html><body>%s</body></html>' % corps)
    z.close()

def lance(src, dst, **kw):
    cmd = [sys.executable, os.path.join(ICI, 'restaure_balise.py'), src, dst, '--doc', 't.htm']
    for k, v in kw.items():
        cmd += ['--' + k, v]
    return subprocess.run(cmd, capture_output=True, text=True)

with tempfile.TemporaryDirectory() as t:
    src = os.path.join(t, 'a.epub')
    livre(src, '<p>on a quelquefois beaucoup du tourment dans notre métier</p>'
               '<p>et du pain, et du vin</p>')
    dst = os.path.join(t, 'b.epub')
    r = lance(src, dst, texte='du', contexte='beaucoup du tourment')
    check('pose la balise au bon endroit', r.returncode == 0)
    h = zipfile.ZipFile(dst).read('t.htm').decode()
    check('… et seulement là', h.count('<i>') == 1 and 'beaucoup <i>du</i> tourment' in h)
    check('… sans toucher aux autres « du »', 'et du pain, et du vin' in h)
    check('… sans changer le texte visible',
          re.sub('<[^>]+>', '', h) == re.sub('<[^>]+>', '',
                 zipfile.ZipFile(src).read('t.htm').decode()))

    r = lance(src, os.path.join(t, 'c.epub'), texte='du', contexte='du')
    check('refuse un contexte non unique', r.returncode != 0 and 'fois' in r.stdout + r.stderr)
    r = lance(src, os.path.join(t, 'd.epub'), texte='du', contexte='beaucoup du tourment',
              balise='script')
    check('refuse une balise qui n’est pas en ligne', r.returncode != 0)
    r = lance(src, os.path.join(t, 'e.epub'), texte='zz', contexte='beaucoup du tourment')
    check('refuse un texte absent du contexte', r.returncode != 0)
    r = lance(src, os.path.join(t, 'f.epub'), texte='du', contexte='phrase inexistante')
    check('refuse un contexte introuvable', r.returncode != 0)
    check('rien écrit quand il refuse', not os.path.exists(os.path.join(t, 'f.epub')))

print('\n' + ('Tous les tests passent.' if not FAILED
              else '%d ÉCHEC(S) : %s' % (len(FAILED), ', '.join(FAILED))))
sys.exit(1 if FAILED else 0)
