"""
chemins.py — Les chemins de la campagne Ségur, réglables par variables d’environnement.

SEGUR_WORKDIR   dossier de travail : copies, témoins, collation, revue (défaut ~/segur-collation)
EPUB_TYPO_FR    dépôt epub-typo-fr (défaut ~/src/bp/epub-typo-fr)
SEGUR_EPUBS     EPUB des copies, Comtesse-de-Segur-<slug>.epub (défaut $SEGUR_WORKDIR/epubs)
SEGUR_OUT       dossier de livraison, propositions comprises (défaut ~/Condor-Share/claude/segur-collation)
EPUBCHECK_JAR   epubcheck.jar (défaut celui du paquet Python epubcheck, installé par pip --user)
"""
import os


def _chemin(variable, defaut):
    return os.path.expanduser(os.environ.get(variable) or defaut)


W = _chemin('SEGUR_WORKDIR', '~/segur-collation')
TOOLS = _chemin('EPUB_TYPO_FR', '~/src/bp/epub-typo-fr')
SAMPLES = _chemin('SEGUR_EPUBS', os.path.join(W, 'epubs'))
OUT = _chemin('SEGUR_OUT', '~/Condor-Share/claude/segur-collation')
EPUBCHECK = _chemin('EPUBCHECK_JAR', '~/.local/lib/python3.12/site-packages/epubcheck/epubcheck.jar')
