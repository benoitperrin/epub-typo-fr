# Les outils de la campagne Ségur (septembre 2026)

Cinq scripts et une consigne, autour des outils du dépôt (`collate.py`, `collate_report.py`,
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

Le principe qui tient l'ensemble : une correction n'existe que tracée — item, décision, témoins,
raison —, et ce qui n'est pas tranché par un témoin reste ouvert, écrit, jamais corrigé en silence.
