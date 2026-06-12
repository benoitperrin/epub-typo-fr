#!/usr/bin/env python3
"""Tests des garde-fous d'ocr_apply.py — match unique, bornes, balises, espaces fines."""
import importlib.util, sys, os, zipfile, tempfile, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('oa', os.path.join(HERE, 'ocr_apply.py'))
oa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oa)

FAILED = []
def check(name, cond):
    print(('✓ ' if cond else '✗ ') + name)
    if not cond:
        FAILED.append(name)

# --- unités sur les helpers ---
check('norm_spaces : fine/insécable → espace',
      oa.norm_spaces('a b c') == 'a b c')
check('edit_distance simple', oa.edit_distance('chat', 'chot') == 1)
check('edit_distance cap', oa.edit_distance('a' * 50, 'b' * 50, cap=10) > 10)

# inline_diff_html : surligne del/ins
d = oa.inline_diff_html('le coute cher', 'le coute cher', 'le coûte cher')
check('inline_diff_html del+ins', '<del>' in d and '<ins>' in d)

# splice_replacement : préserve les espaces réelles de l'original
sp = oa.splice_replacement('Oh ! Charles', 'Oh ! Charles', 'Oh ! Charles,')
check('splice préserve la fine U+202F', ' ' in sp)

# --- test d'intégration sur un mini-EPUB ---
def make_epub(path, body):
    z = zipfile.ZipFile(path, 'w')
    z.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
    z.writestr('META-INF/container.xml',
        '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="c.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    z.writestr('c.opf', '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" unique-identifier="u" version="2.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="u">x</dc:identifier>'
        '<dc:title>t</dc:title><dc:language>fr</dc:language></metadata>'
        '<manifest><item id="c1" href="ch.xhtml" media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="c1"/></spine></package>')
    z.writestr('ch.xhtml', '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
        '<body>' + body + '</body></html>')
    z.close()

def apply(body, corrections, extra=None):
    d = tempfile.mkdtemp()
    src, dst = os.path.join(d, 'in.epub'), os.path.join(d, 'out.epub')
    make_epub(src, body)
    cj = os.path.join(d, 'c.jsonl')
    with open(cj, 'w') as f:
        for c in corrections:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
    r = subprocess.run([sys.executable, os.path.join(HERE, 'ocr_apply.py'), src, dst, cj]
                       + (extra or []), capture_output=True, text=True)
    out_body = None
    if os.path.exists(dst):
        z = zipfile.ZipFile(dst)
        out_body = z.read('ch.xhtml').decode('utf-8')
    return r.stdout + r.stderr, out_body

# correction simple appliquée
out, body = apply('<p>la pensée de courir apres Charles</p>',
                  [{'doc': 'ch.xhtml', 'chercher': 'courir apres Charles', 'remplacer': 'courir après Charles'}])
check('correction simple appliquée', body and 'courir après Charles' in body)
check('1 appliquée / 0 rejetée', '1 appliquées, 0 rejetées' in out)

# motif non unique → rejeté (≥8 chars pour dépasser le filtre de longueur)
out, body = apply('<p>le petit chat. le petit chat dort</p>',
                  [{'doc': 'ch.xhtml', 'chercher': 'le petit chat', 'remplacer': 'le grand chat'}])
check('motif non unique rejeté', body and 'le grand chat' not in body and '0 appliquées, 1 rejetées' in out)

# motif trop court → rejeté
out, body = apply('<p>abcde fghij</p>',
                  [{'doc': 'ch.xhtml', 'chercher': 'abc', 'remplacer': 'xyz'}])
check('motif <8 chars rejeté', body and 'xyz' not in body)

# au-delà des bornes (réécriture massive) → rejeté
out, body = apply('<p>une courte phrase ici présente</p>',
                  [{'doc': 'ch.xhtml', 'chercher': 'une courte phrase ici présente',
                    'remplacer': 'une phrase entièrement différente et beaucoup plus longue que tolérée'}])
check('réécriture massive rejetée', body and 'entièrement différente' not in body)

# tolérance espaces fines : chercher avec espace normale, texte avec U+202F
out, body = apply('<p>Oh ! Charles. si tu savais</p>',
                  [{'doc': 'ch.xhtml', 'chercher': 'Charles. si tu savais', 'remplacer': 'Charles, si tu savais'}])
check('tolérance fine : appliquée', body and 'Charles, si tu savais' in body)
check('tolérance fine : U+202F préservée', body and 'Oh !' in body)

# balises préservées (le remplacement ne doit pas casser le HTML)
out, body = apply('<p>avant <em>mot</em> apres ici</p>',
                  [{'doc': 'ch.xhtml', 'chercher': 'apres ici', 'remplacer': 'après ici'}])
check('balises préservées', body and '<em>mot</em>' in body and 'après ici' in body)

# budget dépassé → exit code 2, rien appliqué
out, body = apply('<p>' + ' '.join(['mot%d' % i for i in range(40)]) + '</p>',
                  [{'doc': 'ch.xhtml', 'chercher': 'mot%d xxxx' % i, 'remplacer': 'mot%d yyyy' % i} for i in range(30)],
                  extra=['--budget-pct', '0.01'])
check('budget dépassé bloque', 'budget' in out.lower())

print()
if FAILED:
    print(f'{len(FAILED)} ÉCHEC(S): ' + ', '.join(FAILED))
    sys.exit(1)
print('Tous les tests ocr_apply passent.')
