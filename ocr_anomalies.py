#!/usr/bin/env python3
"""
ocr_anomalies.py — Détection déterministe d'anomalies OCR dans un EPUB français.

Sortie JSONL, une anomalie par ligne :
  {"doc", "type", "extrait", "avant", "apres", "suggestion"?}
destinée à l'arbitrage LLM (qui décide fix/laisser et la correction exacte),
puis à ocr_apply.py.

Types détectés :
  mot_inconnu          absent du lexique corpus ET de hunspell fr, < 3 occ. dans le livre
  min_apres_point      « phrase. la suite » (point — pas ellipse —, hors abréviations)
  maj_apres_virgule    « réveillée, Elle questionne » (pronoms/conjonctions seulement)
  point_colle          « bien.de près »
  det_virgule          « une, étiquette » (déterminant + virgule)
  abrev_m              « M Panazol » (point d'abréviation perdu)
  mot_double           « le le chat »
  quatre_points        « .... »
  espace_avant_point   « mot , suite » / « mot . Suite »
  virgule_point        « ,. » « ., »
  cesure_residuelle    « exem- ple » (suggestion de recollage si le mot joint est connu)
  guillemet_desequilibre  « et » non appariés dans un paragraphe

Usage:
  python3 ocr_anomalies.py livre.epub --lexicon lexicon.txt [--hunspell fr_FR] > anomalies.jsonl
"""
import sys, re, json, zipfile, html, argparse, subprocess, unicodedata
from collections import Counter

TAG_RE = re.compile(r'(<[^>]+>|<!--.*?-->)', re.S)
HEAD_RE = re.compile(r'<head\b.*?</head>', re.S | re.I)
SKIP_CONTENT = {'style', 'script', 'pre', 'code', 'svg'}
WORD_RE = re.compile(r"[a-zà-öø-ÿœæA-ZÀ-ÖØ-ÞŒÆ]+(?:[-'’][a-zà-öø-ÿœæA-ZÀ-ÖØ-ÞŒÆ]+)*")

ABBREV_BEFORE_DOT = re.compile(
    r'\b(M|MM|Mme|Mmes|Mlle|Mlles|Dr|Pr|St|Ste|etc|cf|p|ex|art|chap|vol|n[o°]|av|J\.-C)\.$')
PRONOUNS_CAP = ('Elle', 'Il', 'Ils', 'Elles', 'On', 'Je', 'Tu', 'Nous', 'Vous',
                'Le', 'La', 'Les', 'Un', 'Une', 'Des', 'Ce', 'Cette', 'Ces',
                'Mais', 'Et', 'Ou', 'Donc', 'Or', 'Ni', 'Car', 'Puis', 'Alors')
DETS = ('un', 'une', 'le', 'la', 'les', 'des', 'du', 'ce', 'cette', 'ces',
        'mon', 'ma', 'mes', 'son', 'sa', 'ses', 'leur', 'notre', 'votre')
DOUBLE_OK = {'nous', 'vous', 'oui', 'non', 'très', 'tout', 'si', 'ah', 'oh', 'hé', 'ho'}


def norm_word(w):
    w = unicodedata.normalize('NFC', w).lower().replace('’', "'")
    # élisions : l'iran → iran (le lexique et hunspell stockent les formes nues)
    return re.sub(r"^(?:l|d|j|n|s|t|c|m|qu|jusqu|lorsqu|puisqu|quoiqu)'", '', w)


def doc_segments(htm):
    """Itère les segments texte (désentitisés) hors style/script/pre/code/svg."""
    skip = 0
    for part in TAG_RE.split(htm):
        if part.startswith('<'):
            m = re.match(r'</?\s*([a-zA-Z0-9]+)', part)
            tag = m.group(1).lower() if m else ''
            if tag in SKIP_CONTENT:
                skip += 1 if not part.startswith('</') else -1
                skip = max(skip, 0)
            continue
        if skip or not part:
            continue
        yield html.unescape(part)


def doc_text(htm):
    return '\n'.join(doc_segments(htm))


def ctx(text, start, end, n=60):
    return {'avant': text[max(0, start - n):start].lstrip(),
            'extrait': text[start:end],
            'apres': text[end:end + n].rstrip()}


class HunspellChecker:
    def __init__(self, dic='fr_FR'):
        self.ok = None
        try:
            subprocess.run(['hunspell', '-d', dic, '-l'], input='test\n',
                           capture_output=True, text=True, timeout=10)
            self.dic = dic
        except Exception:
            self.dic = None

    def unknown(self, words):
        """Retourne le sous-ensemble de mots inconnus de hunspell."""
        if not self.dic:
            return set(words)
        inp = '\n'.join(words)
        r = subprocess.run(['hunspell', '-d', self.dic, '-l'], input=inp,
                           capture_output=True, text=True, timeout=120)
        return {norm_word(w) for w in r.stdout.split()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('epub')
    ap.add_argument('--lexicon', help='lexique corpus (un mot/ligne, minuscules)')
    ap.add_argument('--hunspell', default='fr_FR')
    ap.add_argument('--max-per-type', type=int, default=400)
    args = ap.parse_args()

    lexicon = set()
    if args.lexicon:
        lexicon = {l.strip() for l in open(args.lexicon) if l.strip()}
    hs = HunspellChecker(args.hunspell)

    z = zipfile.ZipFile(args.epub)
    docs = [n for n in z.namelist() if n.lower().endswith(('.xhtml', '.html', '.htm'))]

    # ---- passe 1 : fréquences des mots dans le livre + casse d'origine
    book_freq = Counter()
    seen_lower = set()   # formes vues au moins une fois avec initiale minuscule
    texts = {}
    for name in docs:
        try:
            htm = z.read(name).decode('utf-8')
        except UnicodeDecodeError:
            htm = z.read(name).decode('latin-1', errors='replace')
        t = doc_text(HEAD_RE.sub('', htm))
        texts[name] = t
        for w in WORD_RE.findall(t):
            nw = norm_word(w)
            book_freq[nw] += 1
            if w[:1].islower():
                seen_lower.add(nw)

    # mots candidats inconnus (minuscules uniquement — les capitalisés sont
    # majoritairement des noms propres, traités seulement s'ils sont rares ET
    # absents du lexique ET très proches d'un mot du texte)
    lower_unknown = set()
    for w, c in book_freq.items():
        if c >= 3 or w in lexicon or len(w) < 3:
            continue
        if w not in seen_lower:
            continue   # toujours capitalisé dans le livre → nom propre probable
        if not re.fullmatch(r"[a-zà-öø-ÿœæ][a-zà-öø-ÿœæ'’-]*", w):
            continue
        lower_unknown.add(w)
    if lower_unknown:
        lower_unknown = hs.unknown(sorted(lower_unknown))

    out_counts = Counter()

    def emit(doc, typ, c, suggestion=None):
        out_counts[typ] += 1
        if out_counts[typ] > args.max_per_type:
            return
        rec = {'doc': doc, 'type': typ, **c}
        if suggestion:
            rec['suggestion'] = suggestion
        print(json.dumps(rec, ensure_ascii=False))

    for name in docs:
        t = texts[name]

        # mot_inconnu
        for m in WORD_RE.finditer(t):
            if norm_word(m.group()) in lower_unknown:
                emit(name, 'mot_inconnu', ctx(t, m.start(), m.end()))

        # min_apres_point (pas après ellipse ni abréviation)
        for m in re.finditer(r'(?<!\.)(?<!…)\. ([a-zà-öø-ÿ])', t):
            if ABBREV_BEFORE_DOT.search(t[max(0, m.start() - 8):m.start() + 1]):
                continue
            emit(name, 'min_apres_point', ctx(t, m.start(), m.end()))

        # maj_apres_virgule (pronoms / conjonctions seulement)
        for m in re.finditer(r', (%s)\b' % '|'.join(PRONOUNS_CAP), t):
            emit(name, 'maj_apres_virgule', ctx(t, m.start(), m.end()))

        # point_colle (exclut URL/domaines et initiales)
        for m in re.finditer(r'[a-zà-öø-ÿ]{2}\.[a-zà-öø-ÿ]{2}', t):
            frag = m.group()
            if re.search(r'\.(fr|com|net|org)\b', t[m.start():m.start() + 12]):
                continue
            emit(name, 'point_colle', ctx(t, m.start(), m.end()),
                 suggestion=frag.replace('.', '. ', 1))

        # det_virgule
        for m in re.finditer(r'\b(%s) ?, [a-zà-öø-ÿ]' % '|'.join(DETS), t):
            emit(name, 'det_virgule', ctx(t, m.start(), m.end()))

        # abrev_m
        for m in re.finditer(r'\bM ([A-ZÀ-Ö][a-zà-öø-ÿ]+)', t):
            emit(name, 'abrev_m', ctx(t, m.start(), m.end()),
                 suggestion='M. ' + m.group(1))

        # mot_double
        for m in re.finditer(r"\b([a-zà-öø-ÿ]{2,}) \1\b", t):
            if m.group(1) in DOUBLE_OK:
                continue
            emit(name, 'mot_double', ctx(t, m.start(), m.end()), suggestion=m.group(1))

        # quatre_points
        for m in re.finditer(r'\.{4,}', t):
            emit(name, 'quatre_points', ctx(t, m.start(), m.end()), suggestion='…')

        # espace avant , .
        for m in re.finditer(r'[a-zà-öø-ÿ] [,.](?=[ \n])', t):
            emit(name, 'espace_avant_point', ctx(t, m.start(), m.end()))

        # ,. ou .,
        for m in re.finditer(r'[,.][.,]', t):
            if '..' in m.group():
                continue
            emit(name, 'virgule_point', ctx(t, m.start(), m.end()))

        # cesure_residuelle (suggestion si le recollage est un mot connu)
        for m in re.finditer(r'\b([a-zà-öø-ÿ]{2,})- ([a-zà-öø-ÿ]{2,})\b', t):
            joined = norm_word(m.group(1) + m.group(2))
            sug = None
            if joined in lexicon or (hs.dic and not hs.unknown([joined])):
                sug = m.group(1) + m.group(2)
            emit(name, 'cesure_residuelle', ctx(t, m.start(), m.end()), suggestion=sug)

        # guillemets déséquilibrés au niveau du DOCUMENT (le dialogue français
        # ouvre « et referme » à plusieurs paragraphes d'écart : l'équilibre par
        # paragraphe n'a pas de sens). Informatif — à trancher en lecture intégrale.
        if t.count('«') != t.count('»'):
            emit(name, 'guillemet_desequilibre',
                 {'avant': '', 'extrait': f"« ×{t.count('«')} vs » ×{t.count('»')}",
                  'apres': ''})

    print(json.dumps({'_stats': dict(out_counts)}, ensure_ascii=False), file=sys.stderr)


if __name__ == '__main__':
    main()
