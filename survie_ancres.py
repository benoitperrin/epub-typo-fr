#!/usr/bin/env python3
"""survie_ancres.py — taux de survie des ancres d'annotation entre deux KEPUB : pour chaque (fichier, id) de la
version d'avant, l'ancre existe-t-elle encore, et désigne-t-elle le même texte ?

C'est la question que se pose un surlignage : il porte un StartContainerPath
« span#kobo.N.M » dans un ContentID de fichier. S'il résout sur un autre texte,
il glisse en silence."""
import sys, re, zipfile, html, unicodedata

SPAN = re.compile(r'<span class="koboSpan" id="(kobo\.[\d.]+)">(.*?)</span>', re.S)

def carte(kepub):
    z, out = zipfile.ZipFile(kepub), {}
    for n in sorted(x for x in z.namelist() if x.lower().endswith(('.htm', '.html', '.xhtml'))):
        h = z.read(n).decode('utf-8', 'replace')
        for m in SPAN.finditer(h):
            t = html.unescape(re.sub('<[^>]+>', '', m.group(2)))
            # on compare le TEXTE, pas sa typographie : la passe la change exprès
            t = unicodedata.normalize('NFKD', t)
            # l'espacement n'est PAS une différence de texte : la passe en ajoute
            # exprès (« «A comparu » → « « A comparu »), et une ancre désigne une
            # phrase, pas sa typographie. On ne compare que les caractères visibles.
            t = re.sub(r'\s+', '', t)
            t = t.replace('’', "'").replace('…', '...').replace('—', '-').replace('œ', 'oe')
            t = ''.join(c for c in t if not unicodedata.combining(c))
            out[(n.split('/')[-1], m.group(1))] = t
    return out

a, b = carte(sys.argv[1]), carte(sys.argv[2])
resolvent = [k for k in a if k in b]
memes = [k for k in resolvent if a[k] == b[k]]
proches = [k for k in resolvent if a[k] != b[k] and (a[k][:20] == b[k][:20] or b[k].startswith(a[k]) or a[k].startswith(b[k]))]
print('  ancres avant : %d      après : %d' % (len(a), len(b)))
print('  résolvent encore        : %d  (%.1f %%)' % (len(resolvent), 100*len(resolvent)/max(1,len(a))))
print('  … sur le MÊME texte     : %d  (%.1f %% du total)' % (len(memes), 100*len(memes)/max(1,len(a))))
print('  … sur un texte VOISIN   : %d' % len(proches))
print('  … sur un AUTRE texte    : %d  ← le glissement silencieux' % (len(resolvent)-len(memes)-len(proches)))
print('  ne résolvent plus       : %d  ← l’ancre est morte' % (len(a)-len(resolvent)))
for k in [x for x in resolvent if a[x] != b[x] and x not in proches][:3]:
    print('     ex. %s  «%s» → «%s»' % (k, a[k][:46], b[k][:46]))
