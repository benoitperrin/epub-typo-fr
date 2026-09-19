# Les outils de la campagne Ségur (septembre 2026)

Cinq scripts et une consigne pour la chaîne, six pièces pour les propositions, autour des outils du dépôt (`collate.py`, `collate_report.py`,
`ocr_apply.py`, `epub_typo_audit.py`). Ils portent les chemins de la campagne
(`chemins.py` : le dossier de travail, les EPUB restaurés, le dossier de livraison) : à adapter pour
une autre collection, la mécanique est la même.

| Fichier | Rôle |
|---|---|
| `collationne.py` | collationne un volume avec les témoins présents sur disque (Wikisource toujours, Gallica ou Internet Archive), puis écrit son rapport |
| `PROTOCOLE.md` | la consigne remise au relecteur : principe éditorial, ce que vaut chaque témoin, décisions possibles (dont les familles jugées sur échantillon), forme des corrections et du fichier de verdicts |
| `complements_depuis_remarques.py` | reprend en corrections tracées ce que le relecteur a trouvé hors items, quand il l'écrit dans la forme demandée |
| `assemble_revue.py` | contrôle de réception : chaque item a un verdict valide, chaque correction est complète, puis liste finale des corrections et essai d'application |
| `applique.py` | applique (`ocr_apply.py`), vérifie (epubcheck, audit typographique avant/après) et convertit (kepubify) |
| `livre.py` | livre les fichiers, écrit le LISEZMOI, la provenance (`collation-segur.json`) et le manifeste |

Pour ce que la chaîne ne peut pas appliquer, des propositions à part, qui ne touchent pas aux volumes livrés :

| Fichier | Rôle |
|---|---|
| `restitue.py` | rend les passages que la copie a perdus (pages ou chapitres entiers) : texte de Wikisource contrôlé mot à mot contre Gallica (confiance ALTO), leçons choisies tracées, légendes d'illustrations écartées, noms de locuteurs et titres composés comme dans la copie, chapitres renumérotés, `toc.ncx` et table imprimée retouchées ; EPUB proposé, rapport paragraphe par paragraphe (sous-page Wikisource, vues Gallica) |
| `etat_abrege.py` | chiffre, chapitre par chapitre, une copie abrégée contre le témoin complet |
| `passe_gallica.py` | reprend contre Gallica seul les sites où Wikisource reprend le texte de la copie ; filtre mécanique compté étape par étape |
| `recadre_candidats.py` | découpe, dans l'image Gallica (IIIF), la ligne ALTO de chaque candidat, pour juger sur la page imprimée |
| `PROTOCOLE-gallica-seul.md` | la consigne du relecteur de cette passe (faute, variante, OCR, douteux) |
| `rapport_gallica_seul.py` | rapport de la passe et corrections proposées, rejouables, non appliquées |
| `integre_arbitrages.py`, `installe_restitution.py` | une fois les propositions tranchées : les corrections adoptées rejoignent la chaîne en compléments tracés, l’EPUB restitué devient le volume livré |
| `recompose.py`, `rapport_recompose.py` | quand la copie n’est pas récupérable (abrégé) : texte recomposé depuis le témoin complet, contrôlé mot à mot sur l’autre, dans l’enveloppe de la copie (lettrines, notes, locuteurs, titres), puis livré avec son rapport |

Piège : les ALTO de Gallica se déclarent ISO-8859-1 mais sont en UTF-8 ; lus en Latin-1, les mots accentués perdent leur confiance.

Le principe qui tient l'ensemble : une correction n'existe que tracée — item, décision, témoins,
raison —, et ce qui n'est pas tranché par un témoin reste ouvert, écrit, jamais corrigé en silence.
