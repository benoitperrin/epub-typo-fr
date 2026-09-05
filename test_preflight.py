#!/usr/bin/env python3
"""Tests du contrôle d'avant-vol : il doit laisser passer ce qui ne risque rien,
et arrêter ce qui ferait glisser une annotation."""
import sys, os, json, zipfile, tempfile, subprocess
ICI = os.path.dirname(os.path.abspath(__file__))
FAILED = []
def check(nom, cond):
    print(('✓ ' if cond else '✗ ') + nom)
    if not cond: FAILED.append(nom)

def kepub(path, spans):
    z = zipfile.ZipFile(path, 'w')
    z.writestr('mimetype', 'application/epub+zip')
    z.writestr('OPS/book_0002.xhtml', '<html><body><p>%s</p></body></html>' %
               ''.join('<span class="koboSpan" id="%s">%s</span>' % s for s in spans))
    z.close()

def registre(path, entrees):
    json.dump({'liseuses': {'N1': {'nom': 'Témoin', 'vu': '2026-09-05'}},
               'annotations': entrees}, open(path, 'w'), ensure_ascii=False)

def annot(sid, texte):
    return {'liseuse': 'N1', 'bookmark': 'b', 'uuid': 'U', 'titre': 'T',
            'content_id': 'u!OPS!book_0002.xhtml', 'debut': 'span#' + sid.replace('.', '\\.'),
            'debut_offset': 0, 'fin': 'span#' + sid.replace('.', '\\.'),
            'fin_offset': len(texte), 'texte': texte, 'note': None,
            'type': 'highlight', 'cree': '2026-01-01'}

def lance(reg, kep, epub):
    return subprocess.run([sys.executable, os.path.join(ICI, 'deploy_preflight.py'),
                           '--registre', reg, '--uuid', 'U', '--kepub-actuel', kep,
                           '--epub-nouveau', epub], capture_output=True, text=True)

AV = [('kobo.2.1', 'Première phrase.'), ('kobo.2.2', 'Deuxième phrase.')]
with tempfile.TemporaryDirectory() as t:
    kep = os.path.join(t, 'actuel.kepub'); kepub(kep, AV)
    # l'« epub nouveau » est passé à kepubify : on lui donne le même contenu,
    # ce qui suffit à vérifier les verdicts sans dépendre du contenu réel
    epub = os.path.join(t, 'nouveau.epub')
    z = zipfile.ZipFile(epub, 'w')
    z.writestr('mimetype', 'application/epub+zip')
    z.writestr('META-INF/container.xml', '<?xml version="1.0"?><container version="1.0" '
               'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
               '<rootfile full-path="OPS/c.opf" media-type="application/oebps-package+xml"/>'
               '</rootfiles></container>')
    z.writestr('OPS/c.opf', '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
               'version="2.0" unique-identifier="i"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<dc:title>T</dc:title><dc:language>fr</dc:language><dc:identifier id="i">x</dc:identifier>'
               '</metadata><manifest><item id="a" href="book_0002.xhtml" media-type="application/xhtml+xml"/>'
               '</manifest><spine><itemref idref="a"/></spine></package>')
    z.writestr('OPS/book_0002.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
               '<p>Première phrase. Deuxième phrase.</p></body></html>')
    z.close()

    reg = os.path.join(t, 'r.json')
    registre(reg, [])
    r = lance(reg, kep, epub)
    check('livre non annoté → laisse passer (0)', r.returncode == 0 and 'rien en jeu' in r.stdout)

    registre(reg, [annot('kobo.2.2', 'Deuxième phrase.')])
    r = lance(reg, kep, epub)
    check('livre annoté, ancre déplacée → arrête (3)', r.returncode == 3)
    check('… et dit laquelle', 'glissement' in r.stdout or 'ancre morte' in r.stdout)
    check('… et nomme le porteur', 'Témoin' in r.stdout)

    r = lance(os.path.join(t, 'pas-de-registre.json'), kep, epub)
    check('registre illisible → arrête plutôt que de supposer (3)',
          r.returncode == 3 and 'on ne sait donc PAS' in r.stdout)

    registre(reg, [annot('kobo.2.1', 'Première phrase.')])
    r = lance(reg, os.path.join(t, 'absent.kepub'), epub)
    check('KEPUB actuel introuvable → arrête plutôt que de supposer (3)', r.returncode == 3)

print('\n' + ('Tous les tests passent.' if not FAILED
              else '%d ÉCHEC(S) : %s' % (len(FAILED), ', '.join(FAILED))))
sys.exit(1 if FAILED else 0)
