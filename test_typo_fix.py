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

# R1 — lettres hors Latin-1 (œ, Œ, Ÿ) : l'apostrophe qui les touche doit être courbée
check('R1 apostrophe devant œ', run("<p>un coup d'œil sur l'œuvre</p>"),
      doc('<p>un coup d’œil sur l’œuvre</p>'))
check('R1 apostrophe après œ', run("<p>l'œuf'un</p>"),
      doc('<p>l’œuf’un</p>'))
check('R1 majuscules ligaturées', run("<p>d'Œdipe et d'Ÿs</p>"),
      doc('<p>d’Œdipe et d’Ÿs</p>'))

# R4 — ponctuation double séparée du texte par une balise en ligne
check('R4 » enveloppé dans <i>', run('<p>que faire ? <i>»</i></p>'),
      doc('<p>que faire' + NB + '?' + NB + '<i>»</i></p>'))
check('R4 » enveloppé et collé', run('<p>que faire ?<i>»</i></p>'),
      doc('<p>que faire' + NB + '?' + NB + '<i>»</i></p>'))
check('R4 « suivi d’une balise', run('<p>« <i>Bonjour</i> »</p>'),
      doc('<p>«' + NB + '<i>Bonjour</i>' + NB + '»</p>'))
check('R4 « enveloppé dans <i>', run('<p><i>«</i> Bonjour »</p>'),
      doc('<p><i>«</i>' + NB + 'Bonjour' + NB + '»</p>'))
check('R4 ne franchit pas une frontière de bloc',
      run('<p>fin </p><p>» suite</p>'),
      doc('<p>fin </p><p>» suite</p>'))
check('R4 inline : idempotence',
      run(run('<p>que faire ? <i>»</i></p>').replace('<html><head><title>t</title></head><body>', '').replace('</body></html>', '')),
      doc('<p>que faire' + NB + '?' + NB + '<i>»</i></p>'))

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

# fausses insécables (U+2008 PUNCTUATION SPACE, U+2009 THIN SPACE : sécables malgré leur nom)
# → R4 doit les normaliser comme n'importe quelle espace sécable, en mode fine comme en mode nbsp
check('R4 U+2008 normalisée (fine)', run('<p>Vraiment\u2008? Bon\u2009; Oui\u2008» «\u2008Là</p>', space_style='fine'),
      doc('<p>Vraiment\u202f? Bon\u202f; Oui\u202f» «\u202fLà</p>'))
check('R4 U+2008 normalisée (nbsp)', run('<p>Vraiment\u2008?</p>'),
      doc('<p>Vraiment\u00a0?</p>'))
check('R4 U+2007 (GL) respectée', run('<p>Vraiment\u2007?</p>', space_style='fine'),
      doc('<p>Vraiment\u2007?</p>'))
check('R4 autres sécables Unicode (U+2003, U+205F)', run('<p>Eh\u2003! Oh\u205f?</p>', space_style='fine'),
      doc('<p>Eh\u202f! Oh\u202f?</p>'))

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

# ---- T1 : R4 devant « : » en fin de nœud texte -------------------------------
check('R4 deux-points en fin de nœud', run('<p>Il disait:</p>'),
      doc('<p>Il disait' + NB + ':</p>'))
check('R4 deux-points suivi d’une balise en ligne', run('<p>voici<i>x</i>comment:</p>'),
      doc('<p>voici<i>x</i>comment' + NB + ':</p>'))
check('R4 deux-points : l’heure reste intacte', run('<p>rendez-vous à 10:30</p>'),
      doc('<p>rendez-vous à 10:30</p>'))
check('R4 deux-points : fin de nœud numérique épargnée', run('<p>page 10:</p>'),
      doc('<p>page 10:</p>'))
check('R4 deux-points : idempotence', run(run('<p>Il disait:</p>').split('<body>')[1].split('</body>')[0]),
      doc('<p>Il disait' + NB + ':</p>'))

# ---- T2 : R1 à travers une balise en ligne -----------------------------------
check('R1 apostrophe avant une balise en ligne', run("<p>le bateau l'<i>Émilie</i></p>"),
      doc('<p>le bateau l’<i>Émilie</i></p>'))
check('R1 ne franchit pas une frontière de bloc', run("<p>fin l'</p><p>Suite</p>"),
      doc("<p>fin l'</p><p>Suite</p>"))
check('R1 inline : pas de lettre à droite → intact', run("<p>l'<i>1789</i></p>"),
      doc("<p>l'<i>1789</i></p>"))

# ---- T3 (R8) : rafales d’espaces ---------------------------------------------
check('R8 insécable + espace entre deux mots', run('<p>depuis\u00a0 une semaine</p>'),
      doc('<p>depuis une semaine</p>'))
check('R8 rafale après un guillemet ouvrant', run('<p>«\u00a0 Je vois</p>'),
      doc('<p>«' + NB + 'Je vois</p>'))
check('R8 épargne l’indentation de ligne', run('<p>a\n    b</p>'),
      doc('<p>a\n    b</p>'))
check('R8 idempotence', run(run('<p>depuis\u00a0 une semaine</p>').split('<body>')[1].split('</body>')[0]),
      doc('<p>depuis une semaine</p>'))

# ---- R4 : la fin de ligne du source vaut espace sécable ----------------------
check('R4 saut de ligne devant »', run('<p>ces sources\n»</p>'),
      doc('<p>ces sources' + NB + '»</p>'))
check('R4 « suivi d’un saut de ligne', run('<p>«\nDormez bien</p>'),
      doc('<p>«' + NB + 'Dormez bien</p>'))
check('R4 saut de ligne ordinaire préservé', run('<p>un mot\net un autre</p>'),
      doc('<p>un mot\net un autre</p>'))

# ---- R8 : rafale en fin de nœud ---------------------------------------------
check('R8 rafale close par la fin du nœud', run('<p><b>«  </b>Je suis</p>'),
      doc('<p><b>«' + NB + '</b>Je suis</p>'))
check('R8 fin de nœud : indentation toujours épargnée', run('<p>a\n    </p>'),
      doc('<p>a\n    </p>'))
