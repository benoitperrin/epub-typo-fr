#!/usr/bin/env python3
"""Tests unitaires d'epub_typo_fix.py — règles, garde-fous, idempotence."""
import importlib.util, sys

spec = importlib.util.spec_from_file_location('f', __file__.replace('test_typo_fix', 'epub_typo_fix'))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)

NB = ' '
FAILED = []

def check(name, got, want):
    if got != want:
        FAILED.append(f'{name}:\n  got : {got!r}\n  want: {want!r}')
        print(f'✗ {name}')
    else:
        print(f'✓ {name}')

def doc(body):
    return f'<html><head><title>t</title></head><body>{body}</body></html>'

def run(body, **kw):
    # les attentes historiques des tests sont en U+00A0 + A→À wordlist
    kw.setdefault('space_style', 'nbsp')
    kw.setdefault('a_grave', 'wordlist')
    rules = f.Rules(**kw)
    out, _ = f.transform_doc(doc(body), rules)
    err = f.validate(doc(body), out, mojibake_repaired=kw.get('mojibake', False))
    if err:
        FAILED.append(f'VALIDATION: {err}')
    return out

# R1 apostrophes
check('R1 élision', run("<p>l'arbre d'Artagnan jusqu'à aujourd'hui</p>"),
      doc('<p>l’arbre d’Artagnan jusqu’à aujourd’hui</p>'))
check('R1 anglais préservé hors lettres', run("<p>'quoted' rock 'n' roll</p>"),
      doc("<p>'quoted' rock 'n' roll</p>"))

# R2 ligatures
check('R2 cœur/sœur/œil/mœurs', run('<p>le coeur, la soeur, un oeil, les moeurs, la manoeuvre</p>'),
      doc('<p>le cœur, la sœur, un œil, les mœurs, la manœuvre</p>'))
check('R2 pas de faux positifs', run('<p>le poele moelleux de Noel</p>'),
      doc('<p>le poele moelleux de Noel</p>'))

# R3 dialogues
check('R3 tiret début de p', run('<p>- Bonjour, dit-il.</p>'),
      doc(f'<p>—{NB}Bonjour, dit-il.</p>'))
check('R3 pas en milieu de phrase', run('<p>un mot - et un autre</p>'),
      doc('<p>un mot - et un autre</p>'))
check('R3 avec span', run('<p><span>- Oui.</span></p>'),
      doc(f'<p><span>—{NB}Oui.</span></p>'))
check('R3 mot composé intact', run('<p>-il vient ?</p>'),
      doc(f'<p>-il vient{NB}?</p>'))

# R4 insécables
check('R4 normalise sécable', run('<p>Quoi ? Non ! Si ; voire : oui.</p>'),
      doc(f'<p>Quoi{NB}? Non{NB}! Si{NB}; voire{NB}: oui.</p>'))
check('R4 insère manquante', run('<p>Quoi? Non! « Salut »</p>'),
      doc(f'<p>Quoi{NB}? Non{NB}! «{NB}Salut{NB}»</p>'))
check('R4 guillemets collés', run('<p>«Salut»</p>'),
      doc(f'<p>«{NB}Salut{NB}»</p>'))
check('R4 heure et URL épargnées', run('<p>à 10:30 sur http://a.fr</p>'),
      doc('<p>à 10:30 sur http://a.fr</p>'))
check('R4 fine existante respectée', run(f'<p>Quoi ?</p>'),
      doc('<p>Quoi ?</p>'))
check('R4 rafale ?!', run('<p>Quoi?!</p>'), doc(f'<p>Quoi{NB}?!</p>'))

# R5 ellipses
check('R5 trois points', run('<p>Eh bien... voilà....</p>'),
      doc(f'<p>Eh bien… voilà....</p>'))

# R6 capitales
check('R6 wordlist', run('<p>Etait-ce l’Etat ? Ecoutez. A demain. A bientôt. Etes-vous là ?</p>'),
      doc(f'<p>Était-ce l’État{NB}? Écoutez. À demain. À bientôt. Êtes-vous là{NB}?</p>'))
check('R6 pas de faux positif A', run('<p>A priori on garde. Le point A est loin.</p>'),
      doc('<p>A priori on garde. Le point A est loin.</p>'))

# entités
check('entités &nbsp; et &amp;', run('<p>Tom &amp; Jerry&nbsp;!</p>'),
      doc(f'<p>Tom &amp; Jerry{NB}!</p>'))

# zones à ne pas toucher
check('style/pre intacts', run("<style>p:before{content:'-'}</style><pre>l'an...</pre>"),
      doc("<style>p:before{content:'-'}</style><pre>l'an...</pre>"))

# mode fine (défaut produit) : U+202F inséré, espaces sécables normalisées,
# insécable 00A0 existante respectée
fine = run('<p>Quoi? Non ! D\u00e9j\u00e0\u00a0!</p>', space_style='fine')
check('fine: U+202F', fine,
      doc('<p>Quoi\u202f? Non\u202f! D\u00e9j\u00e0\u00a0!</p>'))
check('a_grave off par défaut produit', f.Rules().a_grave, 'off')

# idempotence
once = run("<p>- L'oeil du coeur... Quoi? «Etat»</p>")
rules2 = f.Rules()
twice, _ = f.transform_doc(once, rules2)
check('idempotence', twice, once)
check('idempotence: zéro nouvelle correction',
      sum(v for k, v in rules2.counts.items()), 0)

# validateur : détecte une vraie altération
bad = doc('<p>texte modifié ici</p>')
orig = doc('<p>texte original ici</p>')
check('validateur détecte altération', f.validate(orig, bad, False) is not None, True)
bad_tags = doc('<p><b>texte</b></p>')
orig_tags = doc('<p><i>texte</i></p>')
check('validateur détecte balise', f.validate(orig_tags, bad_tags, False) is not None, True)

print()
if FAILED:
    print(f'{len(FAILED)} ÉCHEC(S) :')
    for x in FAILED:
        print(x)
    sys.exit(1)
print('Tous les tests passent.')
