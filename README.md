# epub-typo-fr

**Remise à niveau typographique et textuelle d'EPUB français** — audit, correction
mécanique sûre, et réparation des dégâts d'OCR assistée par LLM, avec garde-fous
prouvables et rapports de relecture.

*French ebook typography auditing & repair toolchain. French ebooks circulating in
the wild are often typographically broken (straight apostrophes, missing non-breaking
spaces, hyphens instead of em-dashes in dialogues, lost œ ligatures, OCR damage).
This toolchain audits entire libraries, fixes the mechanical issues with provable
guarantees, and provides a constrained pipeline for LLM-assisted repair of actual
OCR text corruption. Reports are human-reviewable HTML diffs. Reference:
Lacroux's* Orthotypographie.

## Le problème

Une grande partie des EPUB français en circulation sont typographiquement cassés :

- apostrophes droites `'` au lieu de l'apostrophe courbe `’`
- aucune espace insécable avant `! ? ; : »` (ponctuation rejetée en début de ligne)
- dialogues introduits par des traits d'union `-` au lieu du tiret cadratin `—`
- ligatures perdues (`coeur` pour `cœur`), capitales non accentuées (`Etat`)
- `...` au lieu de `…`, mojibake (`Ã©`), césures d'OCR résiduelles (`exem- ple`)
- et, sur les numérisations amateurs : du **texte corrompu** — mots avalés,
  lettres substituées (« sous une petite *plaie* fine » pour *pluie*),
  virgules/points intervertis.

## La chaîne

| Étape | Script | Nature |
|---|---|---|
| 1. Audit d'une bibliothèque | `epub_typo_audit.py` | déterministe — 27 métriques par livre |
| 2. Classement | `score_audit.py` | déterministe — classes A (rédhibitoire) / B (majeur) / C (mineur) / OK |
| 3. Correction typographique | `epub_typo_fix.py` | déterministe — règles R1-R7, garde-fous stricts |
| 4. Détection d'anomalies OCR | `ocr_anomalies.py` | déterministe — 12 détecteurs + lexique |
| 5. Arbitrage des anomalies | *JSONL → vous* | **pluggable** : LLM, ou relecture humaine |
| 6. Lecture intégrale | `chapdump.py` + *vous* | **pluggable** : un relecteur (LLM ou humain) par chapitre |
| 7. Application sous contrainte | `ocr_apply.py` | déterministe — motif unique, bornes, budget, diff HTML |

Les étapes 5 et 6 communiquent par JSONL : les collecteurs émettent des candidats
avec contexte, l'applicateur consomme des corrections `{doc, chercher, remplacer,
raison}`. **Aucune dépendance à un LLM particulier** — c'est l'applicateur qui
garantit l'innocuité, pas le modèle.

## Garde-fous (le cœur du projet)

`epub_typo_fix.py` :
- ne touche que les nœuds texte XHTML (jamais les balises ni `style/script/pre/code/svg`) ;
- la séquence de balises de chaque document doit rester strictement identique ;
- **invariant prouvable** : après normalisation inverse (`’→'`, `œ→oe`, `—→-`,
  insécables→espace…), le texte corrigé doit être identique à l'original —
  un document qui dévie est réécrit à l'identique ;
- idempotent (testé) ; refuse les livres non français sauf `--force`.

`ocr_apply.py` :
- chaque correction doit matcher **exactement une fois** dans son document
  (tolérance sur les espaces insécables/fines, préservées par alignement) ;
- distance d'édition plafonnée, delta de mots plafonné, budget global
  (≤ 0,2 % des mots par défaut) ;
- une correction proposée par un LLM qui ne matche pas verbatim est **rejetée et
  loggée** — les hallucinations ne passent pas ;
- rapport HTML : chaque modification surlignée dans son contexte
  (<del>supprimé</del>/<ins>ajouté</ins>), motifs de rejet listés.

## Démarrage rapide

```bash
# Auditer un dossier d'EPUB
python3 epub_typo_audit.py ~/mes-livres audit.jsonl
python3 score_audit.py audit.jsonl --csv classement.csv

# Corriger la typographie d'un livre (fine U+202F par défaut, U+00A0 : --space-style nbsp)
python3 epub_typo_fix.py livre.epub livre-fixe.epub

# Chasser les dégâts d'OCR
python3 ocr_anomalies.py livre-fixe.epub --lexicon lexicon-fr.txt.gz > anomalies.jsonl
# … arbitrer (LLM ou humain) → corrections.jsonl …
python3 chapdump.py livre-fixe.epub chapitres/   # pour la lecture intégrale
python3 ocr_apply.py livre-fixe.epub livre-final.epub corrections.jsonl \
    --report-html diff.html --titre "Mon livre"
```

## Choix typographiques (et comment en changer)

- Espace insécable : **fine U+202F** avant `! ? ; : »` et après `«` par défaut
  (Lacroux) ; `--space-style nbsp` pour U+00A0 (convention majoritaire des EPUB
  du commerce, plus sûre sur certaines liseuses anciennes). Les insécables déjà
  présentes ne sont jamais dégradées.
- Tiret de dialogue : cadratin `—` + insécable (Lacroux : le demi-cadratin est
  une « mode funeste »). Les livres déjà au demi-cadratin ne sont pas touchés.
- `A` → `À` en tête de phrase : jamais par regex — `a_grave_collect.py` émet les
  candidats avec contexte, un arbitre (LLM/humain) décide occurrence par
  occurrence, `--a-grave-decisions` applique. (Sur un roman réel : 41/41 corrects,
  y compris le refus de « mettre un A à tous mes devoirs ».)

## Lexique

`lexicon-fr.txt.gz` : ~93 000 formes fléchies françaises extraites d'un corpus de
romans jeunesse propres (mot retenu s'il apparaît dans ≥ 2 livres). Régénérable
sur votre propre corpus avec `build_lexicon.py` — un lexique de domaine réduit
drastiquement les faux positifs (noms propres récurrents, vocabulaire d'univers).
`ocr_anomalies.py` le combine avec hunspell `fr_FR` s'il est installé.

## Résultats sur un cas réel

Roman jeunesse des années 1970, numérisation amateur : 4 666 corrections
typographiques (validation stricte), puis 141 corrections textuelles dont
« sous une petite **plaie** fine » → **pluie**, « les mains sur son gros
**entre** » → **ventre**, « les dix **boulons** » → **boutons**, ~40 virgules
parasites — tandis que les déformations *voulues* par l'auteur (bafouillages
comiques d'un personnage, néologismes) ont été préservées par l'arbitrage.

## Limites connues

- Ponctuation séparée de son mot par une balise inline (`mot</i> !`) : non
  corrigée par le fixer (~1 % des cas), gérée par la passe OCR.
- La lecture intégrale par LLM est probabiliste : c'est l'applicateur et le diff
  relisible qui rendent le résultat sûr, pas le modèle.
- L'audit mesure des proportions ; le détecteur d'« élisions quasi absentes »
  attrape les textes massivement déformés, mais une relecture par extraits
  reste recommandée pour les classes douteuses.

## Licence

MIT — voir `LICENSE`. Les outils ne contiennent aucun texte sous droits ;
n'utilisez la chaîne que sur des fichiers que vous êtes en droit de modifier.
