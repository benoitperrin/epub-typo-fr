#!/usr/bin/env python3
"""
epub_typo_fix.py — Correction typographique française robuste d'un EPUB.

Règles (toutes idempotentes, appliquées aux seuls nœuds texte XHTML) :
  R1 apostrophes droites → courbes (entre lettres uniquement : l'arbre → l'arbre)
  R2 ligatures œ perdues (liste blanche : coeur→cœur, soeur→sœur, …)
  R3 tirets de dialogue : « - » en début de <p> → tiret cadratin + insécable
  R4 espaces insécables : avant ! ? ; : » et après « (U+00A0, comme les EPUB
     du commerce ; les espaces sécables existantes sont normalisées, les
     manquantes insérées)
  R5 « ... » → « … »
  R6 capitales accentuées (liste blanche : Etat→État, A devant complément → À, …)
  R7 réparation mojibake (--mojibake : segment ré-encodé cp1252→utf-8 si et
     seulement si ça élimine les marqueurs sans en créer)

Garde-fous :
  - La séquence de balises de chaque document est strictement inchangée.
  - Le texte, après normalisation inverse (’→', œ→oe, —→-, …→..., insécables→espace,
    É→E…), doit être STRICTEMENT identique à l'original (sauf docs réparés R7).
  - Tout le reste du zip (images, CSS, fontes, OPF, NCX) est copié tel quel.
  - Refus de traiter un livre dont la langue OPF n'est pas le français (--force).

Usage:
  python3 epub_typo_fix.py in.epub out.epub [--mojibake] [--force] [--dry-run]
"""
import sys, os, re, html, zipfile, argparse, json
from collections import Counter

NBSP = '\u00a0'
SP_CLASS = '[ \u00a0\u202f\u2009]'   # toute espace horizontale
BRK_CLASS = '[ \u2009]'             # espaces sécables uniquement
LETTER = 'A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u00ff'

SPLIT_RE = re.compile(r'(<[^>]+>|<!--.*?-->)', re.S)
SKIP_CONTENT = {'style', 'script', 'pre', 'code', 'svg'}
INLINE_TAGS = {'span', 'em', 'strong', 'i', 'b', 'a', 'small', 'sup', 'sub', 'u'}

# R2 — ligatures : mots et préfixes sûrs (préfixe éventuellement vide : œil, œuf, œuvre…)
LIG_WORDS_RE = re.compile(
    r'\b([cC]h?|[sS]|[nN]|[bB]|[vV]|[mM]an|[mM]|)(oe|OE|Oe)'
    r'(urs?|uds?|ufs?|uvr\w*|ux|u|ils?|illets?|illades?|sophages?)\b')

# R6 — capitales accentuées (liste blanche prudente)
CAPS_MAP = {
    'Etat': 'État', 'Etats': 'États', 'Eglise': 'Église', 'Eglises': 'Églises',
    'Ecole': 'École', 'Ecoles': 'Écoles', 'Etre': 'Être', 'Epoque': 'Époque',
    'Evidemment': 'Évidemment', 'Ecoute': 'Écoute', 'Ecoutez': 'Écoutez',
    'Etrange': 'Étrange', 'Etranges': 'Étranges', 'Etrangement': 'Étrangement',
    'Etais': 'Étais', 'Etait': 'Était', 'Etant': 'Étant', 'Eteins': 'Éteins',
    'Eternel': 'Éternel', 'Eternelle': 'Éternelle', 'Ete': 'Été', 'Egypte': 'Égypte',
    'Equipe': 'Équipe', 'Etage': 'Étage', 'Etages': 'Étages', 'Etoile': 'Étoile',
    'Etoiles': 'Étoiles', 'Enorme': 'Énorme', 'Enormes': 'Énormes', 'Epee': 'Épée',
    'Eclair': 'Éclair', 'Eclairs': 'Éclairs', 'Etang': 'Étang', 'Evidence': 'Évidence',
    'Evenement': 'Événement', 'Evenements': 'Événements',
    'Ete': 'Été', 'Etes': 'Êtes', 'Etaient': 'Étaient', 'Etions': 'Étions',
}
CAPS_RE = re.compile(r'\b(' + '|'.join(CAPS_MAP) + r')\b')
A_GRAVE_RE = re.compile(
    r'\bA(?= (?:quoi|qui|cette|cet|ce point|ces|la|le|les|chaque|votre|'
    r'peine|côté|cause|droite|gauche|travers|moitié|présent|partir|peu près|'
    r'mon avis|vrai dire|table|nouveau|demain|bientôt|cheval|pied|terre|midi|minuit)\b)')

MOJIBAKE_RE = re.compile('Ã[ -ÿ]|â€™|â€œ|â€|â€“|â€”|Å“|Å’|Â«|Â»|Â |�')

# A isolé candidat à À — DOIT rester identique à a_grave_collect.py
A_CAND_RE = re.compile(r'\bA(?= [a-zà-öø-ÿ])')


class Rules:
    """space_style :
      'fine' (défaut) — U+202F avant ! ? ; : » et après « (règle Lacroux/Benoît) ;
      'nbsp'          — U+00A0 partout (convention des EPUB du commerce, repli si
                        une fonte Kobo rend mal la fine).
    Les insécables déjà en place (00A0 ou 202F) ne sont jamais dégradées.
    a_grave : 'off' (défaut) ou 'wordlist' — la correction « A »→« À » est
    désormais arbitrée par LLM par occurrence (cf. README), le wordlist regex
    reste disponible explicitement."""
    def __init__(self, mojibake=False, space_style='fine', a_grave='off', decisions=None):
        self.mojibake = mojibake
        self.sp = '\u202f' if space_style == 'fine' else '\u00a0'
        self.a_grave = a_grave
        self.decisions = decisions or {}   # {doc: {idx, \u2026}} valid\u00e9s par LLM
        self._doc = None
        self._a_idx = 0
        self.counts = Counter()

    def begin_doc(self, name):
        self._doc = name
        self._a_idx = 0

    # ---- A\u2192\u00c0 par d\u00e9cisions LLM (cf. a_grave_collect.py \u2014 m\u00eame motif, m\u00eame ordre)
    def fix_a_grave_decisions(self, t):
        if not self.decisions:
            return t
        approved = self.decisions.get(self._doc, set())
        def repl(m):
            i = self._a_idx
            self._a_idx += 1
            if i in approved:
                self.counts['R6_a_grave_llm'] += 1
                return '\u00c0'
            return 'A'
        return A_CAND_RE.sub(repl, t)

    # ---- R7 ----
    def fix_mojibake(self, t):
        if not self.mojibake or not MOJIBAKE_RE.search(t):
            return t
        for enc in ('cp1252', 'latin-1'):
            try:
                t2 = t.encode(enc).decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if not MOJIBAKE_RE.search(t2) and '�' not in t2:
                self.counts['R7_mojibake'] += 1
                return t2
        return t

    # ---- R1 ----
    def fix_apostrophes(self, t):
        t, n = re.subn(r"(?<=[%s])'(?=[%s])" % (LETTER, LETTER), '’', t)
        self.counts['R1_apostrophes'] += n
        return t

    # ---- R2 ----
    def fix_ligatures(self, t):
        def repl(m):
            self.counts['R2_ligatures'] += 1
            oe = m.group(2)
            lig = 'œ' if oe == 'oe' else ('Œ' if oe == 'OE' else 'Œ')
            return m.group(1) + lig + (m.group(3) or '')
        return LIG_WORDS_RE.sub(repl, t)

    # ---- R5 ----
    def fix_ellipsis(self, t):
        t, n = re.subn(r'(?<!\.)\.\.\.(?!\.)', '…', t)
        self.counts['R5_ellipsis'] += n
        return t

    # ---- R6 ----
    def fix_caps(self, t):
        def repl(m):
            self.counts['R6_capitales'] += 1
            return CAPS_MAP[m.group(1)]
        t = CAPS_RE.sub(repl, t)
        if self.a_grave == 'wordlist':
            t, n = A_GRAVE_RE.subn('À', t)
            self.counts['R6_capitales'] += n
        return t

    # ---- R4 ----
    def fix_nbsp(self, t):
        sp = self.sp
        # normaliser les espaces SÉCABLES avant ! ? ; : » (les insécables — fines
        # comprises — déjà en place sont respectées)
        t, n1 = re.subn(BRK_CLASS + r'+([!?;:»])', sp + r'\1', t)
        # insérer l'insécable manquante avant ! ? ; (pas dans une rafale ?! déjà traitée)
        t, n2 = re.subn(r'(?<=[%s0-9)»…’])(?=[!?;])' % LETTER, sp, t)
        # deux-points : insérer seulement si suivi d'espace (épargne 10:30, URLs)
        t, n3 = re.subn(r'(?<=[%s)»])(?=:\s)' % LETTER, sp, t)
        # guillemet ouvrant : normaliser l'espace sécable / insérer si collé
        t, n4 = re.subn(r'«' + BRK_CLASS + r'+', '«' + sp, t)
        t, n5 = re.subn(r'«(?=\S)', '«' + sp, t)
        # guillemet fermant : insérer si collé (\S exclut déjà 00A0/202F)
        t, n6 = re.subn(r'(?<=[^\s«])(?=»)', sp, t)
        self.counts['R4_insecables'] += n1 + n2 + n3 + n4 + n5 + n6
        return t

    def apply_text(self, t):
        t = self.fix_a_grave_decisions(t)
        t = self.fix_mojibake(t)
        t = self.fix_apostrophes(t)
        t = self.fix_ligatures(t)
        t = self.fix_ellipsis(t)
        t = self.fix_caps(t)
        t = self.fix_nbsp(t)
        return t


def transform_doc(htm, rules):
    """Transforme un document XHTML. Retourne (nouveau_doc, nb_dialogues_fixés)."""
    parts = SPLIT_RE.split(htm)
    out = []
    skip_depth = 0
    at_para_start = False
    dlg = 0
    for part in parts:
        if part.startswith('<'):
            if not part.startswith('<!--'):
                tname = re.match(r'</?\s*([a-zA-Z0-9]+)', part)
                tag = tname.group(1).lower() if tname else ''
                if tag in SKIP_CONTENT:
                    skip_depth += 1 if not part.startswith('</') else -1
                    skip_depth = max(skip_depth, 0)
                if part.startswith('</'):
                    if tag == 'p':
                        at_para_start = False
                elif tag == 'p':
                    at_para_start = True
                elif tag not in INLINE_TAGS and tag != 'br':
                    at_para_start = False
            out.append(part)
            continue
        if skip_depth > 0 or not part:
            out.append(part)
            continue
        t = html.unescape(part)
        # R3 — tiret de dialogue en début de paragraphe
        if at_para_start:
            t, n = re.subn(r'^(\s*)-' + SP_CLASS + r'+', r'\1—' + NBSP, t, count=1)
            if n:
                dlg += n
                rules.counts['R3_dialogues'] += n
        if t.strip():
            at_para_start = False
        t = rules.apply_text(t)
        out.append(html.escape(t, quote=False))
    return ''.join(out), dlg


# ---------- Validation ----------
NORM_MAP = str.maketrans({
    '\u2019': "'", '\u2014': '-', '\u2013': '-',
    '\u00a0': ' ', '\u202f': ' ', '\u2009': ' ',
    '\u0153': '_oe_', '\u0152': '_OE_',
    '\u00c9': 'E', '\u00c0': 'A', '\u00c8': 'E', '\u00ca': 'E',
})

def normalize_for_check(text):
    t = text.translate(NORM_MAP)
    t = t.replace('_oe_', 'oe').replace('_OE_', 'OE')
    t = t.replace('…', '...')
    # neutraliser l'espacement de la ponctuation française (R4 insère des espaces)
    t = re.sub(r'[ \t]*([!?;:»])', r'\1', t)
    t = re.sub(r'(«)[ \t]*', r'\1', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()

def doc_text(htm):
    body = re.sub(r'<(style|script)\b.*?</\1>', '', htm, flags=re.S | re.I)
    body = SPLIT_RE.sub('\x00', body)  # marqueur de balise pour préserver les frontières
    return html.unescape(body)

def tag_sequence(htm):
    return [p for p in SPLIT_RE.findall(htm)]

def validate(orig, fixed, mojibake_repaired):
    tags_o = tag_sequence(orig)
    tags_f = tag_sequence(fixed)
    if tags_o != tags_f:
        for i, (a, b) in enumerate(zip(tags_o, tags_f)):
            if a != b:
                return f'séquence de balises modifiée (tag {i}: {a!r} → {b!r})'
        return f'séquence de balises modifiée (longueur {len(tags_o)} → {len(tags_f)})'
    if mojibake_repaired:
        return None  # le texte change réellement, diff manuel requis
    n_o = normalize_for_check(doc_text(orig))
    n_f = normalize_for_check(doc_text(fixed))
    if n_o != n_f:
        # localiser la première divergence pour le rapport
        for i in range(min(len(n_o), len(n_f))):
            if n_o[i] != n_f[i]:
                return (f'texte modifié hors règles @ {i}: '
                        f'…{n_o[max(0,i-40):i+40]!r} → …{n_f[max(0,i-40):i+40]!r}')
        return f'texte modifié hors règles (longueur {len(n_o)} → {len(n_f)})'
    return None


def get_opf_lang(z):
    for n in z.namelist():
        if n.lower().endswith('.opf'):
            opf = z.read(n).decode('utf-8', errors='replace')
            m = re.search(r'<dc:language[^>]*>([^<]+)</dc:language>', opf)
            if m:
                return m.group(1).strip().lower()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('infile'); ap.add_argument('outfile')
    ap.add_argument('--mojibake', action='store_true')
    ap.add_argument('--space-style', choices=['fine', 'nbsp'], default='fine')
    ap.add_argument('--a-grave', choices=['off', 'wordlist'], default='off')
    ap.add_argument('--a-grave-decisions', metavar='FILE',
                    help='JSONL {doc, idx, accentuer} validé par LLM (cf. a_grave_collect.py)')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    zin = zipfile.ZipFile(args.infile)
    lang = get_opf_lang(zin)
    if lang and not lang.startswith('fr') and not args.force:
        print(f'REFUS: langue OPF = {lang!r} (utiliser --force pour passer outre)')
        sys.exit(2)

    decisions = {}
    if args.a_grave_decisions:
        import collections
        decisions = collections.defaultdict(set)
        for line in open(args.a_grave_decisions):
            d = json.loads(line)
            if d.get('accentuer'):
                decisions[d['doc']].add(d['idx'])
    rules = Rules(mojibake=args.mojibake, space_style=args.space_style,
                  a_grave=args.a_grave, decisions=dict(decisions))
    errors, changed_docs = [], 0
    entries = zin.infolist()
    out_zip = None
    if not args.dry_run:
        out_zip = zipfile.ZipFile(args.outfile, 'w')
        out_zip.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                         compress_type=zipfile.ZIP_STORED)

    for item in entries:
        if item.filename == 'mimetype':
            continue
        data = zin.read(item.filename)
        if item.filename.lower().endswith(('.xhtml', '.html', '.htm')):
            try:
                htm = data.decode('utf-8')
            except UnicodeDecodeError:
                htm = data.decode('latin-1')
                rules.counts['encodage_latin1_converti'] += 1
            rules.begin_doc(item.filename)
            before = dict(rules.counts)
            moji_before = rules.counts['R7_mojibake']
            fixed, _ = transform_doc(htm, rules)
            if fixed != htm:
                err = validate(htm, fixed, rules.counts['R7_mojibake'] > moji_before)
                if err:
                    errors.append(f'{item.filename}: {err}')
                    fixed = htm  # on n'écrit JAMAIS un doc qui échoue la validation
                    rules.counts = Counter(before)
                else:
                    changed_docs += 1
            data = fixed.encode('utf-8')
        if out_zip:
            info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            out_zip.writestr(info, data)
    if out_zip:
        out_zip.close()
    zin.close()

    print(f'Documents modifiés : {changed_docs}')
    for k in sorted(rules.counts):
        print(f'  {k}: {rules.counts[k]}')
    if errors:
        print(f'\n⚠ {len(errors)} document(s) NON modifié(s) (validation échouée) :')
        for e in errors[:10]:
            print(f'  - {e}')
        sys.exit(1)

if __name__ == '__main__':
    main()
