# Comtesse de Ségur — édition numérique retypographiée (2026)

Collection des romans de **Sophie Rostopchine, comtesse de Ségur (1799-1874)**,
remis à niveau typographiquement et corrigés de leurs scories de numérisation,
à partir des transcriptions du domaine public (Project Gutenberg / Ebooks libres
et gratuits).

## Statut juridique

- **Œuvre** : domaine public. La comtesse de Ségur est morte en 1874 ; ses œuvres
  sont libres de droits dans le monde entier (très au-delà des 70 ans post mortem).
- **Texte** : rédigé en français par l'autrice — pas de droit de traduction en jeu.
- **Cette édition** : les corrections (typographie, OCR) sont versées au domaine
  public / CC0. Le boilerplate et les identifiants Project Gutenberg ont été
  retirés conformément à leur licence ; ces fichiers ne portent plus la marque PG.
- **Rediffusion libre** : Wikisource, Ebooks libres et gratuits, dépôt personnel,
  liseuses. Aucune restriction.

## Ce qui a été fait

Chaîne `epub-typo-fr` (https://github.com/benoitperrin/epub-typo-fr) :

1. **Typographie française** (déterministe, invariant de texte prouvé) :
   apostrophes courbes, espaces fines insécables U+202F avant `! ? ; :` et autour
   des guillemets, tirets cadratins de dialogue, ligatures œ, ellipses `…`.
2. **Retrait du boilerplate** Project Gutenberg / ELG.
3. **Réparation OCR** (détection déterministe + relecture intégrale assistée,
   application sous garde-fous, chaque correction tracée dans un diff relisible) :
   accents avalés (« apres » → « après », « coute » → « coûte »), lettres perdues
   (« lette » → « lettre »), points mis pour des virgules, mots avalés.
4. **Respect du style d'origine** : l'orthographe du XIXᵉ (« grand'mère »,
   « très-poli »), les patois des domestiques et le **sabir volontaire de
   M. Georgey** dans *Les deux nigauds* (« ridicoule », « dix-houit ») ont été
   préservés — ce sont des choix de l'autrice, pas des erreurs.
5. **Validation** : chaque EPUB passe `epubcheck` sans erreur.

## Les 13 titres

| # | Titre | Diff de relecture |
|---|-------|-------------------|
<!-- rempli par finalize -->

## Vérifier les corrections

Chaque livre est accompagné de son `diff-<id>.html` : un tableau listant chaque
correction, surlignée dans son contexte (supprimé en rouge, ajouté en vert), avec
sa justification. Aucune modification n'a été appliquée sans y figurer.
