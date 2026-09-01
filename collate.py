#!/usr/bin/env python3
"""
collate.py — Collationne le texte d'un EPUB contre un ou plusieurs témoins (autres
éditions : transcription Wikisource, OCR Gallica/Internet Archive…) et classe les
divergences, pour distinguer ce qui est une faute de la copie de ce qui est une
variante d'édition ou une graphie d'auteur.

Principe : « on ne corrige pas l'auteur, on corrige la copie ».
  - deux témoins qui s'accordent contre notre texte → correction N1 (mot mal lu,
    lettre substituée, mot doublé, accent avalé) ou N0 (ponctuation) ;
  - un seul témoin → conjecture N2, listée, jamais appliquée ;
  - témoins qui divergent entre eux → variante d'édition, consignée ;
  - graphies d'époque (« très-poli », « grand'mère », « collége ») → protégées.

Alignement : ancres (n-grammes uniques dans les deux textes) puis difflib mot à mot
entre ancres ; texte normalisé (apostrophes, ligatures, casse, espaces ; les
guillemets, tirets et points de suspension ne sont pas alignés).

Usage :
  python3 collate.py livre.epub --temoin ws=temoin-ws.txt --temoin gallica=temoin-gallica.txt \
      [--original livre-avant-corrections.epub] [--lexicon lexicon-fr.txt.gz] \
      --out dossier/ --id 724 --titre "Les malheurs de Sophie" \
      [--temoin-edition ws="Hachette, 1929"] [--temoin-edition gallica="Hachette, 1880"]

Sorties (dans dossier/) : <id>-sites.json (toutes les divergences classées),
<id>-corrections.jsonl (N0/N1 pour ocr_apply.py), <id>-juin.json (corrections
antérieures confirmées/infirmées si --original), <id>-stats.json.
Le rapport Markdown est produit par collate_report.py à partir de ces fichiers.
"""
import sys, os, re, json, html, gzip, zipfile, argparse, difflib, unicodedata
from collections import Counter, defaultdict

TAG_RE = re.compile(r'(<[^>]+>|<!--.*?-->)', re.S)
SKIP_CONTENT = {'style', 'script', 'pre', 'code', 'svg', 'head', 'title'}
BLOCK_TAGS = {'p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'br', 'td', 'th', 'tr',
              'blockquote', 'hr', 'table', 'dd', 'dt', 'body', 'html', 'section', 'figure'}
HEAD_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

# mot (lettres, apostrophes et traits d'union intérieurs) | nombre | ponctuation alignée | reste
TOK_RE = re.compile(r"[^\W\d_]+(?:['’ʼ][^\W\d_]+|-[^\W\d_]+)*|\d+|\.(?:\s*\.)+|[.,;:!?]|[^\s\w]")
ALIGNED_PUNCT = set('.,;:!?')
ROMAN = re.compile(r'^(?:CHAPITRE\s+)?([IVXLC]+)(?:\s*[.—–\-:]\s*|\s+|$)', re.I)
BIG_GAP = 60          # au-delà : zone non couverte (chapitre absent, boilerplate), pas une divergence
CTX = 70

EPOQUE_RE = [re.compile(p) for p in (
    r"^très-", r"^grand'", r"ûment$", r"^long-temps$", r"^remerc[iî]ments?$",
    r"(?:ll|si|pi|sacril|privil|coll)[ée]ge?s?$", r"^r[ée]glement", r"^av[ée]nement", r"^[ée]v[ée]nement",
    r"^po[ëe](?:te|me|sie)s?$", r"^(?:enfans|parens|momens|sentimens|tems|savans|talens)$",
    r"^aujourd'hui$", r"^jusques", r"^encor$",
)]


# ---------------------------------------------------------------- normalisation
def nfc(s):
    return unicodedata.normalize('NFC', s)


def key(s):
    s = nfc(s).lower().replace('’', "'").replace('ʼ', "'").replace('œ', 'oe').replace('æ', 'ae')
    s = s.replace('ﬁ', 'fi').replace('ﬂ', 'fl')
    return s


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def letters_only(s):
    return re.sub(r"[-' ]", '', strip_accents(key(s)))


def edit_distance(a, b, cap=20):
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------- extraction EPUB
class Tok:
    __slots__ = ('s', 'k', 'kind', 'doc', 'seg', 'off', 'end', 'para', 'chap', 'mark')

    def __init__(self, s, kind, doc=None, seg=None, off=None, end=None, para=None, chap=None, mark=None):
        self.s, self.k, self.kind = s, key(s), kind
        self.doc, self.seg, self.off, self.end, self.para, self.chap, self.mark = doc, seg, off, end, para, chap, mark


def tokenize_text(t):
    """→ liste de (surface, kind, start, end) ; kind = w (mot/nombre), p (ponctuation alignée), x (ignoré)."""
    out = []
    for m in TOK_RE.finditer(t):
        s = m.group(0)
        if s[0].isalnum() or s[0] in "'’":
            kind = 'w'
        elif s in ALIGNED_PUNCT:
            kind = 'p'
        else:
            kind = 'x'
        out.append((s, kind, m.start(), m.end()))
    return out


def spine_docs(z):
    cont = z.read('META-INF/container.xml').decode('utf-8', 'replace')
    opf = re.search(r'full-path="([^"]+)"', cont).group(1)
    opf_dir = os.path.dirname(opf)
    x = z.read(opf).decode('utf-8', 'replace')
    items = {m.group(1): m.group(2) for m in re.finditer(r'<item\b[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', x)}
    items.update({m.group(2): m.group(1) for m in re.finditer(r'<item\b[^>]*\bhref="([^"]+)"[^>]*\bid="([^"]+)"', x)})
    docs = []
    for m in re.finditer(r'<itemref\b[^>]*\bidref="([^"]+)"', x):
        href = items.get(m.group(1))
        if href:
            p = os.path.normpath(os.path.join(opf_dir, html.unescape(href))).replace('\\', '/')
            if p in z.namelist() and p.lower().endswith(('.xhtml', '.html', '.htm', '.xml')):
                docs.append(p)
    if not docs:
        docs = [n for n in z.namelist() if n.lower().endswith(('.xhtml', '.html', '.htm'))]
    return docs


def extract_epub(path):
    """Tokens (alignables + ignorés) avec position (doc, segment, offsets), paragraphe et chapitre.
    Retourne (tokens, segments) où segments[doc] = liste des textes de segments (index = seg)."""
    z = zipfile.ZipFile(path)
    toks, segments = [], {}
    para = 0
    chap = None
    for doc in spine_docs(z):
        htm = z.read(doc).decode('utf-8', 'replace')
        parts = TAG_RE.split(htm)
        segs = [''] * len(parts)
        skip = 0
        in_head = False
        para_buf = []           # (seg_idx, texte) du paragraphe courant, pour détecter les titres
        para_start_tok = len(toks)

        def close_para():
            nonlocal chap, para, para_buf, para_start_tok
            ptxt = ' '.join(t for _, t in para_buf).strip()
            m = ROMAN.match(ptxt) if ptxt else None
            if ptxt and (m or in_head) and len(ptxt) < 90:
                label = m.group(1).upper() if m else ptxt[:40]
                if m or re.search(r'[A-ZÉÈ]{3,}', ptxt):
                    chap = label
                    for t in toks[para_start_tok:]:
                        t.chap = chap
            para += 1
            para_buf = []
            para_start_tok = len(toks)

        for j, part in enumerate(parts):
            if part.startswith('<'):
                m = re.match(r'</?\s*([a-zA-Z0-9]+)', part)
                tag = m.group(1).lower() if m else ''
                closing = part.startswith('</')
                if tag in SKIP_CONTENT:
                    skip += -1 if closing else 1
                    skip = max(skip, 0)
                if tag in HEAD_TAGS:
                    in_head = not closing
                if tag in BLOCK_TAGS:
                    close_para()
                continue
            if skip or not part.strip():
                continue
            t = html.unescape(part)
            segs[j] = t
            para_buf.append((j, t))
            for s, kind, a, b in tokenize_text(t):
                toks.append(Tok(s, kind, doc, j, a, b, para, chap))
        close_para()
        segments[doc] = segs
    return toks, segments


def load_witness(path):
    """Texte témoin → tokens ; lignes « ### » (chapitre) et « #### » (vue) = marqueurs, non alignés."""
    raw = open(path, encoding='utf-8', errors='replace').read()
    toks, mark = [], None
    for block in raw.split('\n'):
        if block.startswith('### ') or block.startswith('#### '):
            mark = block.lstrip('#').strip()
            continue
        # césures de fin de ligne (OCR brut) : « pour- raient » ne survient pas ici car on
        # travaille ligne par ligne ; on recolle plus bas au niveau du texte complet.
        for s, kind, a, b in tokenize_text(block):
            toks.append(Tok(s, kind, mark=mark))
    return toks


def dehyphenate_file(path):
    t = open(path, encoding='utf-8', errors='replace').read()
    t = re.sub(r"([^\W\d_])-\n[ \t]*([^\W\d_])", r"\1\2", t)
    return t


# ---------------------------------------------------------------- alignement
def aligned(toks):
    return [t for t in toks if t.kind in ('w', 'p')]


def anchors(A, B, n=6, min_gap=2500):
    """Ancres = n-grammes de clés présents exactement une fois dans A et dans B, chaîne monotone."""
    def grams(X):
        c = Counter()
        pos = {}
        for i in range(len(X) - n + 1):
            g = tuple(x.k for x in X[i:i + n])
            c[g] += 1
            pos[g] = i
        return c, pos
    ca, pa = grams(A)
    cb, pb = grams(B)
    cand = sorted((pa[g], pb[g]) for g in pa if ca[g] == 1 and cb.get(g) == 1)
    # plus longue chaîne croissante sur B (ancres monotones)
    import bisect
    tails, back, idx = [], [], []
    for k, (ia, ib) in enumerate(cand):
        j = bisect.bisect_left(tails, ib)
        if j == len(tails):
            tails.append(ib); idx.append(k)
        else:
            tails[j] = ib; idx[j] = k
        back.append(idx[j - 1] if j else -1)
    chain = []
    k = idx[-1] if idx else -1
    while k >= 0:
        chain.append(cand[k]); k = back[k]
    chain.reverse()
    # espacer les ancres retenues
    out, last = [], -10**9
    for ia, ib in chain:
        if ia - last >= min_gap:
            out.append((ia, ib)); last = ia
    return out


def align(A, B):
    """Opcodes (op, i1, i2, j1, j2) sur les listes de tokens alignables A (nous) et B (témoin)."""
    ka, kb = [t.k for t in A], [t.k for t in B]
    cuts = anchors(A, B)
    bounds = [(0, 0)] + cuts + [(len(A), len(B))]
    ops = []
    for (a0, b0), (a1, b1) in zip(bounds, bounds[1:]):
        if a1 <= a0 and b1 <= b0:
            continue
        sm = difflib.SequenceMatcher(None, ka[a0:a1], kb[b0:b1], autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            ops.append((op, i1 + a0, i2 + a0, j1 + b0, j2 + b0))
    # fusion des blocs equal contigus
    merged = []
    for o in ops:
        if merged and o[0] == 'equal' and merged[-1][0] == 'equal' and merged[-1][2] == o[1] and merged[-1][4] == o[3]:
            merged[-1] = ('equal', merged[-1][1], o[2], merged[-1][3], o[4])
        else:
            merged.append(o)
    return merged


class Alignment:
    """Projection de nos indices vers ceux du témoin + zones non couvertes."""

    def __init__(self, A, B, ops):
        self.A, self.B, self.ops = A, B, ops
        n = len(A)
        self.jstart = [0] * (n + 1)
        self.jend = [0] * (n + 1)
        self.uncovered = [False] * (n + 1)
        self.jstart[n] = self.jend[n] = len(B)
        for op, i1, i2, j1, j2 in ops:
            if op == 'equal':
                for i in range(i1, i2):
                    self.jstart[i] = j1 + (i - i1); self.jend[i] = self.jstart[i] + 1
            else:
                big = (op == 'delete' and i2 - i1 > BIG_GAP) or (op == 'replace' and (i2 - i1 > BIG_GAP or j2 - j1 > BIG_GAP))
                for i in range(i1, i2):
                    self.jstart[i] = j1; self.jend[i] = j2
                    self.uncovered[i] = big
        self.covered_ratio = 1 - sum(self.uncovered[:n]) / max(1, n)

    def reading(self, a, b):
        """Tokens du témoin alignés sur notre intervalle [a, b) (vide si a == b : insertion)."""
        if a < b:
            if any(self.uncovered[a:b]):
                return None
            return self.B[self.jstart[a]:self.jend[b - 1]]
        lo = self.jend[a - 1] if a > 0 else 0
        hi = self.jstart[a] if a < len(self.A) else len(self.B)
        if a > 0 and self.uncovered[a - 1] or a < len(self.A) and self.uncovered[a]:
            return None
        return self.B[lo:hi] if hi > lo else []

    def sites(self):
        """Divergences brutes (i1, i2) hors zones non couvertes / bruit massif du témoin."""
        out = []
        for op, i1, i2, j1, j2 in self.ops:
            if op == 'equal':
                continue
            if (i2 - i1 > BIG_GAP) or (j2 - j1 > BIG_GAP):
                continue
            out.append((i1, i2))
        return out


# ---------------------------------------------------------------- lexique
class Lexicon:
    def __init__(self, path, book_tokens):
        self.words = set()
        if path and os.path.exists(path):
            op = gzip.open if path.endswith('.gz') else open
            with op(path, 'rt', encoding='utf-8') as f:
                self.words = {key(l.strip()) for l in f if l.strip()}
        self.book = Counter(t.k for t in book_tokens if t.kind == 'w')
        self.hun = None
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from ocr_anomalies import HunspellChecker
            h = HunspellChecker('fr_FR')
            self.hun = h if getattr(h, 'ok', False) else None
        except Exception:
            self.hun = None
        self.cache = {}

    @staticmethod
    def bare(w):
        w = key(w)
        w = re.sub(r"^(?:l|d|j|n|s|t|c|m|qu|jusqu|lorsqu|puisqu|quoiqu)'", '', w)
        return w

    def known(self, w):
        k = key(w)
        if k in self.cache:
            return self.cache[k]
        parts = re.split(r"[-']", k)
        core = self.bare(k)
        ok = (k in self.words or core in self.words or self.book[k] >= 3
              or (parts and all(p in self.words or p.isdigit() or self.book[p] >= 3 for p in parts if p)))
        if not ok and self.hun is not None:
            try:
                ok = bool(self.hun.check(core)) if hasattr(self.hun, 'check') else False
            except Exception:
                ok = False
        self.cache[k] = ok
        return ok


def epoque(w):
    k = key(w)
    return any(r.search(k) for r in EPOQUE_RE)


# ---------------------------------------------------------------- classement
def surf(toks):
    return ' '.join(t.s for t in toks)


def keys(toks):
    return [t.k for t in toks]


def nature(ours, theirs, lex):
    """Nature de la différence entre nos tokens et ceux du témoin (listes alignables)."""
    ko, kt = keys(ours), keys(theirs)
    if ko == kt:
        return 'identique'
    po = all(t.kind == 'p' for t in ours); pt = all(t.kind == 'p' for t in theirs)
    if (po or not ours) and (pt or not theirs):
        return 'ponctuation'
    wo = [t for t in ours if t.kind == 'w']; wt = [t for t in theirs if t.kind == 'w']
    if keys(wo) == keys(wt):
        return 'ponctuation'            # seuls des signes diffèrent autour des mêmes mots
    jo, jt = ''.join(keys(wo)), ''.join(keys(wt))
    if not wo or not wt:
        if wo and len(wo) == 1 and len(ours) == 1:
            # mot présent chez nous, absent du témoin : doublon ?
            return 'ajout_nous'
        return 'omission_nous' if not wo else 'ajout_nous'
    if letters_only(jo) == letters_only(jt):
        if strip_accents(jo) != strip_accents(jt) or len(wo) != len(wt) or any('-' in k or "'" in k for k in keys(wo) + keys(wt)):
            # même lettres : espace, trait d'union, apostrophe ou accent
            if len(wo) != len(wt) and not any('-' in k or "'" in k for k in keys(wo) + keys(wt)):
                return 'espace'
            if strip_accents(jo) == strip_accents(jt):
                return 'graphie'
            return 'accent'
        return 'accent'
    if len(wo) == 1 and len(wt) == 1:
        a, b = wo[0].k, wt[0].k
        ed = edit_distance(a, b)
        ok_o, ok_t = lex.known(a), lex.known(b)
        if epoque(a):
            return 'graphie'
        if not ok_o and ok_t and ed <= (2 if len(b) < 8 else 3):
            return 'ocr_nous'
        if ok_o and not ok_t:
            return 'ocr_temoin'
        if ok_o and ok_t:
            return 'lecture' if ed <= 2 else 'variante'
        return 'incertain'
    # plusieurs mots : lettres presque identiques → lecture ; sinon variante
    ed = edit_distance(jo, jt, cap=6)
    if ed <= 3:
        if any(not lex.known(t.k) for t in wo) and all(lex.known(t.k) for t in wt):
            return 'ocr_nous'
        if all(lex.known(t.k) for t in wo) and any(not lex.known(t.k) for t in wt):
            return 'ocr_temoin'
        return 'lecture'
    return 'variante'


def compatible(r1, r2, lex):
    """Deux leçons de témoins sont « compatibles » si identiques, ou si l'une est du bruit OCR
    (mot inconnu) à ≤ 2 lettres de l'autre."""
    k1, k2 = keys(r1), keys(r2)
    if k1 == k2:
        return True
    w1, w2 = [t for t in r1 if t.kind == 'w'], [t for t in r2 if t.kind == 'w']
    if keys(w1) == keys(w2):
        return True                       # ne diffèrent que par la ponctuation
    if len(w1) == len(w2) == 1:
        a, b = w1[0].k, w2[0].k
        if edit_distance(a, b) <= 2 and (not lex.known(a) or not lex.known(b)):
            return True
    return False


def punct_pattern(ours, theirs, prev_tok, next_tok):
    """Motif de ponctuation typique d'une corruption de copie → N0 ; sinon None."""
    so, st = ''.join(t.s for t in ours), ''.join(t.s for t in theirs)
    nxt = next_tok.s if next_tok else ''
    if so == '.' and st == ',' and nxt[:1].islower():
        return 'point pour virgule devant une minuscule'
    if so == ',' and st == '.' and nxt[:1].isupper():
        return 'virgule pour point devant une majuscule'
    if so == '' and st in ('.', ',') and (not next_tok or (st == '.' and nxt[:1].isupper())):
        return 'point final manquant' if st == '.' else 'virgule manquante'
    if so == '.' and st == '' and nxt[:1].islower():
        return 'point parasite au milieu d’une phrase'
    if so in (',', '.') and st == '' and prev_tok and prev_tok.kind == 'p':
        return 'ponctuation doublée'
    return None


# ---------------------------------------------------------------- corrections
def make_correction(site, toks_all, segments, new_text, raison, source, level):
    """Construit une entrée {doc, chercher, remplacer, raison} pour ocr_apply.py."""
    a, b = site['i1'], site['i2']
    A = site['_A']
    if a < b:
        first, last = A[a], A[b - 1]
        doc, seg = first.doc, first.seg
        if last.doc != doc or last.seg != seg:
            return None, 'à cheval sur deux segments'
        start, end = first.off, last.end
    else:
        # insertion : entre A[a-1] et A[a]
        ref = A[a - 1] if a > 0 else A[a]
        doc, seg = ref.doc, ref.seg
        if a > 0 and a < len(A) and (A[a].doc != doc or A[a].seg != seg):
            return None, 'insertion en frontière de segment'
        start = end = A[a - 1].end if a > 0 else A[a].off
    text = segments[doc][seg]
    docs_text = [s for s in segments[doc] if s]
    for pad in (45, 70, 100, 150, 250):
        cs = max(0, start - pad); ce = min(len(text), end + pad)
        while cs > 0 and not text[cs - 1].isspace():
            cs -= 1
        while ce < len(text) and not text[ce].isspace():
            ce += 1
        chercher = text[cs:ce]
        n = sum(s.count(chercher) for s in docs_text)
        if n == 1 and len(chercher) >= 8:
            remplacer = text[cs:start] + new_text + text[end:ce]
            return {'doc': doc, 'chercher': chercher, 'remplacer': remplacer,
                    'raison': raison, 'source': source, 'niveau': level}, None
        if cs == 0 and ce == len(text):
            break
    return None, 'motif non unique dans le document'


def adapt_case(new, old):
    if old[:1].isupper() and new[:1].islower():
        return new[0].upper() + new[1:]
    if old.isupper() and len(old) > 1:
        return new.upper()
    return new


# ---------------------------------------------------------------- juin (corrections antérieures)
def previous_corrections(A_orig, A_ours):
    """Diff original → nôtre : liste de {i1, i2 (chez nous), avant (tokens originaux), nature}."""
    ops = align(A_orig, A_ours)
    out = []
    for op, i1, i2, j1, j2 in ops:
        if op == 'equal':
            # différences de casse ou de surface à clé égale (Je → je, coeur → cœur…)
            for d in range(i2 - i1):
                o, n = A_orig[i1 + d], A_ours[j1 + d]
                if o.s != n.s and key(o.s) == key(n.s):
                    so, sn = nfc(o.s).replace('œ', 'oe').replace('’', "'"), nfc(n.s).replace('œ', 'oe').replace('’', "'")
                    if so != sn and so.lower() == sn.lower():
                        out.append({'i1': j1 + d, 'i2': j1 + d + 1, 'avant': [o], 'nature': 'casse'})
            continue
        if i2 - i1 > BIG_GAP or j2 - j1 > BIG_GAP:
            continue
        before, after = A_orig[i1:i2], A_ours[j1:j2]
        nat = 'texte'
        if keys(before) and keys(after) and strip_accents(''.join(keys(before))) == strip_accents(''.join(keys(after))):
            nat = 'accent'
            # A → À, E → É en tête de mot : passe typographique, pas correction OCR
            if all(len(t.s) == 1 and t.s in 'AE' for t in before) or all(
                    strip_accents(t.s[0]) == t.s[0] and t.s[0].isupper() for t in before if t.kind == 'w'):
                nat = 'typo-capitale'
        elif all(t.kind == 'p' for t in before) and all(t.kind == 'p' for t in after):
            nat = 'ponctuation'
        out.append({'i1': j1, 'i2': j2, 'avant': before, 'nature': nat})
    return out


# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('epub')
    ap.add_argument('--temoin', action='append', default=[], help='nom=fichier.txt')
    ap.add_argument('--temoin-edition', action='append', default=[], help='nom=« édition »')
    ap.add_argument('--original', help='EPUB avant corrections (pour confirmer/infirmer)')
    ap.add_argument('--lexicon', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lexicon-fr.txt.gz'))
    ap.add_argument('--out', required=True)
    ap.add_argument('--id', default='livre')
    ap.add_argument('--titre', default='')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    toks, segments = extract_epub(args.epub)
    A = aligned(toks)
    lex = Lexicon(args.lexicon, toks)
    editions = dict(e.split('=', 1) for e in args.temoin_edition)
    witnesses = {}
    for spec in args.temoin:
        name, path = spec.split('=', 1)
        B = aligned(load_witness(path))
        ops = align(A, B)
        witnesses[name] = Alignment(A, B, ops)
        print(f'{name}: {len(B)} tokens, couverture {witnesses[name].covered_ratio:.1%}', file=sys.stderr)
    names = list(witnesses)

    # ---- sites : union des divergences de tous les témoins, fusionnées par recouvrement
    raw = sorted(set(s for w in witnesses.values() for s in w.sites()))
    sites = []
    for i1, i2 in raw:
        if sites and i1 <= sites[-1][1] and not (i1 == i2 == sites[-1][1] and False):
            if i1 < sites[-1][1] or (i1 == sites[-1][1] and (i1 == i2 or sites[-1][0] == sites[-1][1])):
                sites[-1] = (sites[-1][0], max(sites[-1][1], i2))
                continue
        sites.append((i1, i2))
    # étendre chaque site aux blocs complets de chaque témoin
    blocks = {n: [(o[1], o[2]) for o in w.ops if o[0] != 'equal'] for n, w in witnesses.items()}
    ext = []
    for i1, i2 in sites:
        a, b = i1, i2
        changed = True
        while changed:
            changed = False
            for n in names:
                for x1, x2 in blocks[n]:
                    if x2 - x1 > BIG_GAP:
                        continue
                    if x1 < b and x2 > a or (x1 == x2 and a <= x1 <= b) or (a == b and x1 <= a <= x2):
                        if x1 < a or x2 > b:
                            a, b = min(a, x1), max(b, x2); changed = True
        if ext and a <= ext[-1][1] and (a < ext[-1][1] or a == b or ext[-1][0] == ext[-1][1]):
            ext[-1] = (ext[-1][0], max(ext[-1][1], b))
        else:
            ext.append((a, b))
    sites = ext

    results, corrections, stats = [], [], Counter()
    cov_stats = {n: round(w.covered_ratio, 4) for n, w in witnesses.items()}
    for i1, i2 in sites:
        ours = A[i1:i2]
        readings = {n: w.reading(i1, i2) for n, w in witnesses.items()}
        covered = [n for n in names if readings[n] is not None]
        if not covered:
            stats['non_couvert'] += 1
            continue
        differing = [n for n in covered if keys(readings[n]) != keys(ours)]
        if not differing:
            continue
        agreeing = [n for n in covered if n not in differing]
        natures = {n: nature(ours, readings[n], lex) for n in differing}
        prev_tok = A[i1 - 1] if i1 > 0 else None
        next_tok = A[i2] if i2 < len(A) else None
        ctx_seg = segments[A[i1].doc][A[i1].seg] if i1 < len(A) else ''
        c0 = A[i1].off if i1 < len(A) else (A[i1 - 1].end if i1 > 0 else 0)
        c1 = A[i2 - 1].end if i2 > i1 else c0
        before = ctx_seg[max(0, c0 - CTX):c0]
        after = ctx_seg[c1:c1 + CTX]
        rec = {'i1': i1, 'i2': i2, 'doc': A[min(i1, len(A) - 1)].doc, 'chap': A[min(i1, len(A) - 1)].chap,
               'nous': surf(ours), 'avant': before, 'apres': after,
               'temoins': {n: (surf(readings[n]) if readings[n] is not None else None) for n in names},
               'marques': {n: (readings[n][0].mark if readings[n] else (witnesses[n].B[witnesses[n].jstart[i1]].mark if witnesses[n].jstart[i1] < len(witnesses[n].B) else None)) for n in names},
               'natures': natures, 'accord_nous': agreeing}
        # consensus ?
        if agreeing:
            # au moins un témoin lit comme nous : divergence du côté des autres témoins
            rec['classe'] = 'temoin_seul'
            rec['verdict'] = 'soutenu'
            for n in differing:
                stats[f'bruit_{natures[n]}'] += 1
        else:
            if len(differing) >= 2:
                r = [readings[n] for n in differing]
                cons = all(compatible(r[0], x, lex) for x in r[1:])
                # la leçon de référence = celle d'un témoin dont les mots sont connus, sinon la première
                ref = next((n for n in differing if all(lex.known(t.k) for t in readings[n] if t.kind == 'w')), differing[0])
            else:
                cons, ref = False, differing[0]
            rec['reference'] = ref
            nat = natures[ref]
            rec['nature'] = nat
            theirs = readings[ref]
            # niveau
            level, action, raison = 'N2', None, ''
            if nat in ('graphie',):
                level = 'laisse'
            elif nat == 'ocr_temoin':
                level = 'bruit'
            elif nat == 'ponctuation':
                pat = punct_pattern([t for t in ours if t.kind == 'p'], [t for t in theirs if t.kind == 'p'], prev_tok, next_tok)
                if pat and cons and all(keys(readings[n]) == keys(theirs) for n in differing):
                    level, action, raison = 'N0', 'remplacer', pat
                else:
                    level = 'N2-ponct' if not cons else 'N2-ponct-consensus'
            elif cons and len(differing) >= 2:
                if nat in ('ocr_nous', 'espace'):
                    level, action = 'N1', 'remplacer'
                    raison = 'mot mal lu dans la copie' if nat == 'ocr_nous' else 'espace mal placée'
                elif nat == 'accent':
                    jo = ''.join(keys([t for t in ours if t.kind == 'w']))
                    jt = ''.join(keys([t for t in theirs if t.kind == 'w']))
                    if strip_accents(jo) == jo and jt != jo and not lex.known(jo):
                        level, action, raison = 'N1', 'remplacer', 'accent avalé'
                    else:
                        level = 'laisse'          # collége/collège : graphie d'époque ou choix d'édition
                elif nat == 'lecture' and all(keys(readings[n]) == keys(theirs) for n in differing):
                    level, action, raison = 'N1', 'remplacer', 'lettre substituée (deux témoins)'
                elif nat == 'ajout_nous' and len(ours) == 1 and prev_tok is not None and prev_tok.k == ours[0].k:
                    level, action, raison = 'N1', 'supprimer', 'mot doublé (dittographie)'
                else:
                    level = 'N2'
            elif len(covered) == 1:
                level = 'N2-seul' if nat not in ('ocr_temoin', 'incertain') else 'bruit'
            else:
                level = 'N2-divergent'
            rec['niveau'] = level
            rec['classe'] = nat
            stats[f'niveau_{level}'] += 1
            stats[f'nature_{nat}'] += 1
            if action:
                if action == 'remplacer':
                    wt = [t for t in theirs]
                    if nat == 'ponctuation':
                        # ne remplacer que les signes : on reconstruit à partir du témoin
                        new = ''.join(t.s for t in theirs if t.kind == 'p')
                    else:
                        new = surf(wt)
                        if len(ours) == 1 and len(wt) == 1:
                            new = adapt_case(wt[0].s, ours[0].s)
                            new = nfc(new).replace("'", '’')
                    if new.startswith((',', '.', ';', ':')) and i1 < i2 and False:
                        pass
                else:
                    new = ''
                # espace : si l'on supprime un mot doublé, retirer aussi l'espace qui le précède
                site = {'i1': i1, 'i2': i2, '_A': A}
                if action == 'supprimer' and i1 > 0:
                    seg_text = segments[A[i1].doc][A[i1].seg]
                    # étendre le début au blanc précédent
                    class _T: pass
                    site = {'i1': i1, 'i2': i2, '_A': A}
                temoins_txt = ', '.join(f"{n} ({editions.get(n, '?')}) : « {surf(readings[n])} »" for n in differing)
                corr, why = make_correction(site, toks, segments, new, f'{raison} — {temoins_txt}',
                                            f'collation {level} ({"+".join(differing)})', level)
                if action == 'supprimer' and corr:
                    # retirer l'espace doublée laissée par la suppression
                    corr['remplacer'] = re.sub(r'(\s)\s+', r'\1', corr['remplacer'])
                if corr:
                    corr['i1'] = i1
                    corrections.append(corr)
                    rec['correction'] = corr
                else:
                    rec['non_applicable'] = why
                    stats['non_applicable'] += 1
        results.append(rec)

    # ---- corrections antérieures (juin) confirmées / infirmées
    juin = []
    if args.original:
        toks_o, _ = extract_epub(args.original)
        A_o = aligned(toks_o)
        for c in previous_corrections(A_o, A):
            i1, i2 = c['i1'], c['i2']
            ours = A[i1:i2]
            verdicts = {}
            for n, w in witnesses.items():
                r = w.reading(i1, i2)
                if r is None:
                    verdicts[n] = ('non couvert', None)
                    continue
                if c['nature'] == 'casse':
                    same_ours = r and nfc(r[0].s).replace('’', "'") == nfc(ours[0].s).replace('’', "'") if ours and r else False
                    same_orig = r and nfc(r[0].s).replace('’', "'") == nfc(c['avant'][0].s).replace('’', "'") if r else False
                    v = 'confirme' if same_ours else ('infirme' if same_orig else 'autre')
                elif keys(r) == keys(ours):
                    v = 'confirme'
                elif keys(r) == keys(c['avant']):
                    v = 'infirme'
                elif compatible(r, ours, lex) and not compatible(r, c['avant'], lex):
                    v = 'confirme~'
                elif compatible(r, c['avant'], lex) and not compatible(r, ours, lex):
                    v = 'infirme~'
                else:
                    v = 'autre'
                verdicts[n] = (v, surf(r))
            vs = [v for v, _ in verdicts.values()]
            if any(v.startswith('confirme') for v in vs) and not any(v.startswith('infirme') for v in vs):
                bilan = 'confirmée'
            elif any(v.startswith('infirme') for v in vs) and not any(v.startswith('confirme') for v in vs):
                bilan = 'infirmée'
            elif any(v.startswith('infirme') for v in vs):
                bilan = 'contradictoire'
            elif all(v == 'non couvert' for v in vs):
                bilan = 'non collationnée'
            else:
                bilan = 'autre leçon'
            ctx_seg = segments[A[min(i1, len(A) - 1)].doc][A[min(i1, len(A) - 1)].seg]
            c0 = A[i1].off if i1 < len(A) else 0
            c1 = A[i2 - 1].end if i2 > i1 else c0
            rec = {'i1': i1, 'i2': i2, 'chap': A[min(i1, len(A) - 1)].chap, 'nature': c['nature'],
                   'avant_juin': surf(c['avant']), 'apres_juin': surf(ours),
                   'contexte_avant': ctx_seg[max(0, c0 - CTX):c0], 'contexte_apres': ctx_seg[c1:c1 + CTX],
                   'temoins': {n: {'verdict': v, 'lecon': l} for n, (v, l) in verdicts.items()}, 'bilan': bilan}
            if bilan == 'infirmée' and c['nature'] != 'typo-capitale':
                # proposer le retour à la leçon transmise si les deux témoins s'accordent exactement
                agree = [n for n, (v, l) in verdicts.items() if v == 'infirme']
                if len(agree) >= 2 and c['nature'] != 'casse':
                    new = surf(c['avant'])
                    site = {'i1': i1, 'i2': i2, '_A': A}
                    corr, why = make_correction(site, toks, segments, new,
                                                f'retour à la leçon transmise, infirmation de la correction de juin — '
                                                + ', '.join(f"{n} ({editions.get(n, '?')}) : « {l} »" for n, (v, l) in verdicts.items() if l),
                                                'collation N1-retour (' + '+'.join(agree) + ')', 'N1')
                    if corr:
                        corr['i1'] = i1
                        corrections.append(corr); rec['correction'] = corr
                    else:
                        rec['non_applicable'] = why
            juin.append(rec)
        for r in juin:
            stats[f"juin_{r['nature']}_{r['bilan']}"] += 1

    # ---- sorties
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if not k.startswith('_')}
        if isinstance(o, list):
            return [clean(v) for v in o]
        return o
    idp = os.path.join(args.out, str(args.id))
    json.dump(clean(results), open(idp + '-sites.json', 'w'), ensure_ascii=False, indent=1)
    with open(idp + '-corrections.jsonl', 'w') as f:
        for c in sorted(corrections, key=lambda c: c['i1']):
            f.write(json.dumps({k: v for k, v in c.items() if k != 'i1'}, ensure_ascii=False) + '\n')
    json.dump(clean(juin), open(idp + '-juin.json', 'w'), ensure_ascii=False, indent=1)
    meta = {'id': args.id, 'titre': args.titre, 'epub': os.path.basename(args.epub), 'tokens': len(A),
            'mots': sum(1 for t in A if t.kind == 'w'), 'temoins': {n: {'edition': editions.get(n, ''), 'tokens': len(w.B),
            'couverture': cov_stats[n]} for n, w in witnesses.items()}, 'stats': dict(stats),
            'sites': len(results), 'corrections': len(corrections), 'juin': len(juin)}
    json.dump(meta, open(idp + '-stats.json', 'w'), ensure_ascii=False, indent=1)
    print(json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
