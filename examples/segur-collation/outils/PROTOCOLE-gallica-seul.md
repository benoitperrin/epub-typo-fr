# Protocole — passe contre Gallica seul (septembre 2026)

Pour trois volumes de la comtesse de Ségur (720 *Pauvre Blaise*, 726 *Les Deux Nigauds*, 727 *Le Général
Dourakine*), la transcription Wikisource (`ws`) a été établie en partie sur le texte Project Gutenberg
de notre copie : là où elle s’accorde avec la copie contre Gallica, son accord ne prouve rien. La
collation a classé ces sites en bruit (« un seul témoin contre deux leçons »). Cette passe les reprend.
**Rien n’est appliqué** : ton travail nourrit un rapport pour Benoît.

## Le principe éditorial (inchangé, à appliquer)

On ne corrige pas l’auteur, on corrige la copie. Doctrine du 05/09/2026 : « On est éditeur, on assume
de corriger tant que c’est tracé. » Une leçon fautive que le témoin permet de trancher se corrige ;
restent ouverts les cas sans témoin qui tranche ou à lectures réellement équivalentes. Ne jamais
toucher aux graphies d’époque, au parler des personnages, aux noms de locuteurs, à la casse des titres.

## Ce que tu as

- `$SEGUR_OUT/propositions/gallica-seul/<id>-candidats.json` :
  les candidats, déjà filtrés mécaniquement (hors ponctuation seule, légendes, titres, locuteurs,
  graphies ; leçon de Gallica faite de mots connus et lue par l’OCR avec la confiance maximale). Chaque
  candidat : `n`, `vue` (Gallica), `copie` (leçon de la copie, que ws partage), `gallica` (leçon de
  l’OCR), `avant` / `apres` (contexte dans la copie), `doc` (fichier XHTML).
- Le texte de la copie, un paragraphe par ligne : `$SEGUR_WORKDIR/copie/<id>.txt`
  (la copie livrée a reçu depuis des corrections : c’est le texte d’avant collation).
- L’OCR Gallica : `$SEGUR_WORKDIR/gallica/<ark>.txt` (ark dans le fichier des
  candidats), avec des marqueurs « #### vue N ». Greps courts seulement (`grep -o '.\{0,80\}motif.\{0,80\}'`).
- L’image de la ligne imprimée, pour chaque candidat : `$SEGUR_WORKDIR/crops/<id>/<n>.jpg`
  (recadrage de la page Gallica sur la ligne, plus une ligne autour). **Regarde-la chaque fois que ton
  verdict dépend de ce que la page imprime vraiment** (en pratique : avant tout verdict « faute de la
  copie » ou « variante », et pour trancher un doute sur la lecture de l’OCR). Si l’image manque,
  dis-le et juge sur le texte.

## Les verdicts, un par candidat

- `faute` — la copie (et ws avec elle) porte une faute que Gallica corrige : accord, conjugaison,
  mot sauté ou estropié, sens rompu. Donne la correction proposée au format habituel
  `{"doc": …, "chercher": …, "remplacer": …}` (texte de la copie à l’identique, unique dans son
  document, 3 à 8 mots de contexte, typographie française de la copie, apostrophe courbe).
- `variante` — les deux leçons se tiennent : la copie suit une autre édition (ex. « les mains » /
  « la main », « était » / « est »). On ne touche pas.
- `ocr` — l’image montre la leçon de la copie : l’OCR a mal lu, malgré sa confiance.
- `douteux` — tu ne peux pas trancher : écris la **question**, une phrase, avec les deux leçons.

Chaque verdict porte une `raison` brève (ce que montre l’image, pourquoi c’est une faute, ou pourquoi
les deux leçons se tiennent) et `image: true` si tu as regardé l’image.

## Sortie — à écrire au fil de l’eau

`$SEGUR_WORKDIR/revue/<id>-gallica-seul.json` :

```json
{"volume": 726, "verdicts": [
  {"n": 21, "verdict": "faute", "image": true, "raison": "« un petit jeune homme qui est tombée » : accord fautif ; l’image lit « tombé ».",
   "correction": {"doc": "…", "chercher": "petit jeune homme qui est tombée", "remplacer": "petit jeune homme qui est tombé"}},
  {"n": 49, "verdict": "variante", "raison": "« baisent-ils les mains » / « la main » : les deux se disent."}
 ],
 "remarques": ["ce que tu as remarqué de général : édition suivie par la copie, familles de variantes…"]}
```

Écris le fichier dès les premiers verdicts, puis complète-le (une coupure de quota peut survenir) ;
vérifie-le avec `python3 -m json.tool`. Tu ne modifies aucun autre fichier ; scripts d’aide
seulement dans le dossier indiqué par ta consigne ; aucune commande réseau ; aucun autre agent.

Message final, court : par volume, le nombre de verdicts de chaque sorte, puis les questions des
candidats `douteux`.
