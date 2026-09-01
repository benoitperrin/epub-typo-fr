#!/usr/bin/env python3
"""Tests unitaires d'epub_typo_audit.py — classement des espaces devant la ponctuation haute.

Seules U+00A0, U+2007 et U+202F sont insécables (Line_Break = GL). U+2008 et U+2009
doivent tomber dans `punct_fakespace`, jamais dans `punct_nbsp` (cf. fiche
cadratin/docs/espaces-insecables-pieges.md : avant correctif, U+2008 n'entrait dans
aucun compteur et U+2009 passait pour conforme)."""
import importlib.util, sys
from collections import Counter

spec = importlib.util.spec_from_file_location('a', __file__.replace('test_typo_audit', 'epub_typo_audit'))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

FAILED = []

def check(name, got, want):
    if got != want:
        FAILED.append(f'{name}: got {got!r}, want {want!r}')
        print(f'✗ {name}')
    else:
        print(f'✓ {name}')

def metrics(text):
    m = Counter()
    a.text_metrics(text, m)
    return m

m = metrics('Oui\u00a0! Là\u202f: Fin\u2007; Vraiment\u2008? Bon\u2009; Sec ! Collé!')
check('GL comptées comme insécables (00A0, 202F, 2007)', m['punct_nbsp'], 3)
check('U+2008 et U+2009 = fausses insécables', m['punct_fakespace'], 2)
check('U+2008/U+2009 jamais dans punct_nbsp', m['punct_nbsp'] + m['punct_space'] + m['punct_none'], 5)
check('espace ordinaire', m['punct_space'], 1)
check('collée', m['punct_none'], 1)

m = metrics('«\u2008Salut\u2008» et «\u202fBonjour\u202f»')
check('fausse insécable devant »', m['punct_fakespace'], 1)
check('guillemets : GL seulement dans guil_in_nbsp', m['guil_in_nbsp'], 2)

m = metrics('Rien à signaler.')
check('texte neutre : tous compteurs à zéro', m['punct_fakespace'] + m['punct_nbsp'] + m['punct_space'] + m['punct_none'], 0)

print()
if FAILED:
    print(f'{len(FAILED)} ÉCHEC(S) :')
    for x in FAILED:
        print(x)
    sys.exit(1)
print('Tous les tests passent.')
