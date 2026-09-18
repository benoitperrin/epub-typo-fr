# Protocole de relecture — collation Ségur (septembre 2026)

Tu relis la collation d’un lot de volumes de la comtesse de Ségur. Pour chaque volume, un
programme (`collate.py`) a aligné mot à mot notre copie (un EPUB restauré en juin 2026) sur deux
ou trois témoins indépendants, classé chaque divergence et proposé des corrections. Ton travail :
**juger chaque item**, avec une trace vérifiable, et écrire ton verdict dans un fichier.

## Principe éditorial (décidé, à appliquer, pas à rediscuter)

- **On ne corrige pas l’auteur, on corrige la copie.** Une faute de transcription, un mot sauté,
  une coquille se corrigent ; une graphie d’époque, une tournure d’auteur, le parler d’un personnage
  ne se touchent pas.
- **Doctrine du 05/09/2026** : « On est éditeur, on assume de corriger tant que c’est tracé. » Une
  leçon fautive que les témoins permettent de trancher **se corrige**, même si la copie reproduit
  fidèlement une édition qui portait déjà la faute (le prote n’est pas l’auteur). La trace — quel
  témoin, quelle leçon, quel raisonnement — est la condition. **Ne restent ouverts** que les cas sans
  témoin qui tranche, ou à deux lectures réellement équivalentes. Corriger en silence est interdit ;
  laisser ouvert ce qu’un témoin permet de trancher est une faute aussi.
- **À ne jamais toucher** : graphies d’époque (« très-joli », « grand’mère », « collége », « poëte »,
  « long-temps »), parler des personnages (« mam’selle », « bourri », patois, sabir, mots russes),
  majuscules et casse des **titres** (question réservée à Benoît), **noms de locuteurs** des
  dialogues (la copie compose « *Thérèse:*—réplique » là où l’édition imprime « THÉRÈSE. » sur sa
  ligne : c’est une question de présentation réservée à Benoît ; selon les volumes, le nom est aussi
  en capitales, « PAUL, » ou « SOPHIE. » ; tout item qui ne ferait que changer la ponctuation ou la
  forme d’un nom de locuteur est à écarter).

## Les témoins : ce qu’ils valent

- `ws` : **Wikisource**, transcription relue par des humains d’une édition Hachette précise (souvent
  tardive, 1880-1900). Fiable sur les mots ; elle reproduit parfois les **coquilles** de son édition
  (« un cou d’œil », « mon harnais étais ciré ») sans les signaler. Elle accentue les capitales.
- `gallica` : **OCR brut** d’une édition Hachette plus ancienne (1858-1880 le plus souvent). Bruit
  d’OCR fréquent (lettres confondues, mots collés, accents sur capitales absents), mais édition
  indépendante et proche de l’originale.
- `ia` : **OCR brut** Internet Archive (Hachette 1917 pour 719 ; Édito-Service, Genève, s. d., pour
  723). Même prudence que Gallica ; les en-têtes courants et numéros de page y traînent.
- Notre copie descend souvent de la **même impression** que Wikisource (Project Gutenberg). Une
  faute commune à la copie et à `ws`, que l’autre témoin n’a pas, est une **coquille de cette
  impression** si la grammaire ou le sens la condamnent (on corrige, en le disant) ; si les deux
  leçons se tiennent, c’est une **variante d’édition** (on laisse, en le disant).
- Deux témoins qui s’accordent contre la copie ne mentent presque jamais sur les mots ; sur la
  ponctuation, vérifie que le signe du témoin n’est pas accompagné d’un tiret ou de points de
  suspension que l’alignement n’a pas vus.

## Fichiers

Pour chaque volume `<id>` de ton lot (dossier `$SEGUR_WORKDIR/`) :

- `rapports/<id>-*.md` — le rapport : bilan, sections A (corrections de juin), B (N0), C (N1),
  D (N2 à trancher), E (ce qu’on laisse). Commence par lui.
- `collation-2026-09-16/<id>-items.json` — les mêmes items, complets : `id` (J-01, N0-07, N1-02,
  N2-11), contexte (`avant`, `nous`, `apres`), `temoins` (leçon de chaque témoin), `doc` (fichier
  XHTML dans l’EPUB), et `correction` (`chercher` / `remplacer`) quand une correction est proposée.
- `copie/<id>.txt` — le texte de la copie, document par document (`=== <doc>`), un paragraphe par
  ligne, pour vérifier un contexte ou l’unicité d’un passage (`grep -n`). Plusieurs volumes (724,
  726, 721, 722) gardent dans leurs paragraphes des retours à la ligne de composition : `items.json`
  les montre (`\n`), `copie/<id>.txt` les a remplacés par des espaces. Dans `chercher`, une espace
  à la place d’un retour à la ligne est acceptée par l’applicateur.
- Témoins en texte brut : `ws/<id>.txt` ; `gallica/<ark>.txt` (ark dans
  `examples/segur-collation/temoins-segur.json`) ; `ia/<id>-*.txt`.
  Les OCR ont des espaces doubles et des retours à la ligne : cherche avec `grep -o` sur un mot
  rare, ou aplatis d’abord (`tr '\n' ' ' | tr -s ' '`).
- Les greps sur ces fichiers doivent rester courts (`grep -o '.\{0,80\}motif.\{0,80\}'`, `| head`) :
  n’affiche jamais un fichier entier.

## Ce que tu décides, item par item

Tous les items du fichier `items.json` reçoivent **exactement un** verdict.

**N0-xx et N1-xx** (correction proposée) : `garder`, `veto` ou `modifier`.
- `garder` si les témoins portent bien la leçon et que la correction ne touche ni graphie d’époque,
  ni parler de personnage, ni nom de locuteur.
- `veto` sinon, en disant pourquoi (ex. « nom de locuteur », « variante d’édition, les deux leçons
  se tiennent », « le témoin a “—” après la virgule, la correction la supprimerait sans le tiret »).
- `modifier` si l’idée est juste mais la correction incomplète ou mal composée (ex. un point devenu
  virgule exige aussi la minuscule suivante) : donne la correction entière.

**J-xx** (correction faite en juin que les témoins ne confirment pas) : `garder` (juin avait raison,
ex. le témoin qui l’infirme porte une coquille), `revenir` (rétablir la leçon d’origine) ou `autre`
(une troisième correction, ex. « prairie. Et quand » → « prairie, et quand »). `revenir` et `autre`
exigent une correction **sur le texte actuel de la copie** (celui de `copie/<id>.txt`).

**L-xx** (graphie laissée par la collation : graphie d’époque ou choix d’édition présumé) : `laisser`
si c’est bien une graphie d’époque ou un choix d’édition, `corriger` si c’est en réalité une coquille
que les témoins corrigent (« son teint blanc et rosé » pour « rose »).

**N2-xx** (à trancher) : `corriger` (correction + témoins + raisonnement), `laisser` (variante
d’édition, lectures équivalentes, bruit de témoin, présentation, déjà traité par un autre item :
dis lequel) ou `ouvert` (aucun témoin ne tranche, ou deux lectures réellement équivalentes : écris
alors la **question** qu’on posera à Benoît, une phrase, avec les deux leçons).

Si deux items relèvent d’une même correction, porte la correction sur l’un et renvoie l’autre
(`"decision": "laisser"`, `"raison": "traité avec J-01"`).

**Familles (items qui portent `"famille"` dans `items.json`)** : même règle mécanique, même preuve
(deux témoins d’accord mot pour mot), en nombre. Tu ne rends pas un verdict par item mais **un
verdict par famille**, après avoir vérifié **chaque item de l’échantillon** (`"echantillon": true`,
marqués ★ dans le rapport) dans les témoins. `garder` si l’échantillon est bon ; si un item de
l’échantillon est faux pour une raison qui peut toucher les autres (règle qui se trompe, et non
accident isolé), relis toute la famille et rends des verdicts individuels. Tu peux toujours écarter
ou modifier un item précis de la famille par un verdict individuel, qui prime.
Une **famille N2** (écart de présentation que tous les témoins partagent, sans correction proposée :
par exemple « Mme » de la copie contre « madame » en toutes lettres) se juge de même, avec la
décision `laisser` pour la famille si l’échantillon ne montre que cet écart ; un item qui cache
autre chose (un signe, un mot) reçoit un verdict individuel.

**N2-ponct et N2-divergent** (témoins en désaccord entre eux) : verdict bref. Par défaut `laisser`
(« variante d’édition : ws … / gallica … »), sauf si la leçon de la copie est une faute que la
grammaire ou le sens condamnent : alors `corriger` d’après le témoin le plus sûr, en le disant.

## Comment écrire une correction

`{"doc": "<chemin XHTML exact, tel que dans items.json>", "chercher": "…", "remplacer": "…"}`

- `chercher` est copié **à l’identique** de la copie (espaces insécables U+202F comprises : copie-les
  depuis `items.json` ou `copie/<id>.txt`), **unique dans son document**, sans chevaucher de balise
  (reste dans un même paragraphe, hors italique d’un nom), au moins 8 caractères. Prends 3 à 8 mots
  de contexte.
- `remplacer` = le même passage corrigé, **rien d’autre** : typographie française de la copie
  (apostrophe courbe ’, espace fine insécable U+202F avant « ; : ! ? », rien avant « , . »,
  points de suspension « … »). Jamais d’apostrophe droite.
- Pas de réécriture : la correction restitue une leçon de témoin ou répare une faute évidente.

## Sortie — à écrire AVANT ton message final

Un fichier par volume : `$SEGUR_WORKDIR/revue/<id>-revue.json`

```json
{
 "volume": 723,
 "familles": [
  {"famille": "N0 · ponctuation (deux témoins)", "decision": "garder",
   "echantillon_relu": ["N0-01", "N0-11", "N0-21"], "raison": "échantillon vérifié dans ws et gallica : …"}
 ],
 "items": [
  {"item": "N1-06", "decision": "garder", "raison": "ws et ia : « et tâcher de ravoir les ânes » ; saut de la copie."},
  {"item": "N0-11", "decision": "veto", "raison": "deux-points après le nom de locuteur « Jacques » : présentation."},
  {"item": "J-01", "decision": "autre", "correction": {"doc": "…", "chercher": "…", "remplacer": "…"},
   "raison": "ws et ia lisent « prairie, et quand » : la faute était le point, pas la minuscule."},
  {"item": "N2-03", "decision": "corriger", "correction": {"doc": "…", "chercher": "…", "remplacer": "…"},
   "temoins": "ws « le visage » · ia « le Aisage » (OCR)", "raison": "« sur te visage » : t pour l, coquille de la copie."},
  {"item": "N2-05", "decision": "ouvert", "temoins": "…", "raison": "…",
   "question": "« à tire-d’aile » (ws) ou « à tires d’aile » (copie) ?"}
 ],
 "remarques": ["défauts de structure remarqués en passant (note de transcripteur restée dans le livre, etc.) : à signaler, rien à corriger ici"]
}
```

Écris le fichier d’un volume dès qu’il est fini, avant de passer au suivant (une coupure de quota
peut survenir : ce qui est écrit est gardé). Vérifie-le avec
`python3 -m json.tool <fichier> > /dev/null`.

## Règles de conduite

- Tu ne modifies **aucun** autre fichier : ni les EPUB, ni les rapports, ni les outils, ni les
  témoins. Aucune commande réseau. Aucun message à quiconque.
- Tu ne lances pas d’autre agent.
- Si un outil ou une donnée te semble faux (item incohérent avec les témoins, contexte tronqué),
  dis-le dans `remarques` au lieu de le contourner.
- Ne rapporte que ce que tu as vérifié : une leçon de témoin se cite depuis le fichier, pas de
  mémoire.
- Message final : pour chaque volume, le nombre de verdicts par décision, et la liste des items
  `ouvert` avec leur question. Rien d’autre.
