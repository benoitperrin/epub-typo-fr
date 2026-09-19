#!/usr/bin/env python3
"""
restitue.py — Proposition de restitution des lacunes d'une copie Ségur : passages entiers que
tous les témoins portent et que la copie n'a pas (collate.py les signale dans <id>-lacunes.json).

Texte restitué : base Gallica (édition ancienne, vues consultables), contrôlée mot à mot contre
Wikisource (transcription relue). Mécanique :
  - où les deux témoins s'accordent, le texte passe tel quel (forme Wikisource, typographie de
    la copie) ;
  - où ils divergent sur les mots (variante d'édition, mot ajouté ou omis), la leçon de Gallica
    est retenue si l'OCR en est sûr (confiance ALTO WC = 1) ; sinon celle de Wikisource ; chaque
    cas est listé, et le fichier de décisions `<id>-decisions.json` (dossier de sortie) peut
    forcer un choix, avec sa raison ;
  - ponctuation et graphies (accents, traits d'union, « très bien ») : celles de Wikisource, qui
    sont celles du reste de la copie ; l'OCR n'est pas assez sûr sur les signes pour trancher ;
  - noms de locuteurs (que l'OCR filtre) et titres de chapitre : Wikisource, composés selon la
    convention de la copie ; légendes d'illustrations : écartées.
Chaque paragraphe restitué garde sa trace : sous-page Wikisource, vues Gallica.

Rien n'est remplacé dans les volumes livrés : la proposition (rapport, plan JSON, EPUB et KEPUB
proposés) est écrite dans $SEGUR_OUT/propositions/lacunes/.

Usage :
  python3 restitue.py 718 --analyse     # lacunes, bornes, divergences à regarder (rien d'écrit)
  python3 restitue.py 718               # plan, rapport, EPUB proposé (epubcheck, kepubify)
"""
import sys, os, re, json, html, zipfile, argparse, subprocess, tempfile, shutil, hashlib, glob, difflib
from collections import Counter, defaultdict
import chemins

sys.path.insert(0, chemins.TOOLS)
import collate

W = chemins.W
TOOLS = chemins.TOOLS
OUT = f'{chemins.OUT}/propositions/lacunes'
EPUBCHECK = chemins.EPUBCHECK
NNBSP = '\u202f'

# Convention de la copie, volume par volume : noms de locuteurs (casse du nom, signe avant la
# réplique) et composition des titres de chapitre.
CONV = {
    '718': {'casse': 'titre', 'sep': ':—', 'ponct_label': ':', 'titres': 'h3', 'tiret': '—'},
    # 726 : Gallica est une réimpression de 1909, Wikisource transcrit l'originale de 1863, dont descend la copie :
    # la base est Wikisource, Gallica ne corrige que ses fautes de lecture
    '726': {'casse': 'capitales', 'sep': '.—', 'ponct_label': '.', 'titres': 'h3h5', 'base': 'ws', 'tiret': '—'},
    '729': {'casse': 'capitales', 'sep': '.—', 'ponct_label': '.', 'titres': 'pb', 'tiret': '—'},
    # 721 : copie abrégée ; titres « IV. Une rencontre inattendue. » dans un seul paragraphe
    '721': {'casse': 'capitales', 'sep': '.—', 'ponct_label': '.', 'titres': 'p1'},
}
ROMAINS = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
           (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]
ROMAN_P = re.compile(r'^[IVXLC]+\.?$')
LABEL_P = re.compile(r"^[a-zàâäçéèêëîïôöûùüÿœæ][a-zàâäçéèêëîïôöûùüÿœæ’' ,\-]{0,60}\.$")
# nom de locuteur en capitales, didascalie éventuelle en minuscules (« MADAME BLIDOT, riant. », 729)
LABEL_CAP = re.compile(r"^[A-ZÀÂÄÇÉÈÊËÎÏÔÖÛÙÜŸŒÆ][A-ZÀÂÄÇÉÈÊËÎÏÔÖÛÙÜŸŒÆ’' .\-]{1,40}(?:, [a-zàâäçéèêëîïôöûùüÿœæ’' ,\-]{1,60})?\.$")
FIN_PHRASE = re.compile(r'[.!?…»:;]\s*$')


def romain(n):
    s = ''
    for v, r in ROMAINS:
        while n >= v:
            s += r; n -= v
    return s


def vol_info(i):
    T = {str(v['id']): v for v in json.load(open(f'{TOOLS}/examples/segur-collation/temoins-segur.json'))['volumes']}
    return T[i]


def ecrit(path, data):
    """Écriture atomique (fichier .tmp puis renommage)."""
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        f.write(data)
    os.replace(path + '.tmp', path)


# ---------------------------------------------------------------- témoin Wikisource en paragraphes
def ws_paragraphs(path):
    """Paragraphes du témoin Wikisource : texte (lignes jointes), lignes, sous-page, nature
    (numero, titre, locuteur, corps)."""
    raw = open(path, encoding='utf-8').read()
    paras, chap, en_tete = [], None, False
    for block in re.split(r'\n[ \t]*\n', raw):
        body = []
        for l in block.split('\n'):
            if l.startswith('### '):
                chap, en_tete = l[4:].strip(), True
            elif l.strip():
                body.append(l.strip())
        if not body:
            continue
        text = ' '.join(body)
        if en_tete and ROMAN_P.match(text):
            nat = 'numero'
        elif en_tete and paras and paras[-1]['nature'] in ('numero', 'titre') and \
                ((text[:1].islower() and not LABEL_P.match(text)) or (text.isupper() and len(text) < 120)):
            nat = 'titre'
        else:
            en_tete = False
            nat = 'locuteur' if (LABEL_P.match(text) or LABEL_CAP.match(text)) else 'corps'
        paras.append({'n': len(paras), 'chap': chap, 'texte': text, 'lignes': body, 'nature': nat})
    return paras


def ws_tokens(paras, conv):
    """Tokens alignables du témoin, avec paragraphe et positions ; le point final d'un nom de
    locuteur prend le signe de la copie (« Marianne: » / « MOUTIER. ») pour l'alignement."""
    out = []
    for p in paras:
        toks = [t for t in collate.tokenize_text(p['texte']) if t[1] != 'x']
        for k, (s, kind, a, b) in enumerate(toks):
            if p['nature'] == 'locuteur' and k == len(toks) - 1 and s == '.':
                s = conv['ponct_label']
            out.append(collate.Tok(s, kind, off=a, end=b, para=p['n'], mark=p['chap']))
    return out


def legendes_gallica(gtxt):
    """Légendes d'illustrations de l'édition Gallica : « Texte. (Page 293.) »."""
    caps = []
    for l in gtxt.split('\n'):
        m = re.search(r'\(\s*P\s*a\s*[gq]\s*e\b', l)
        if m and m.start() > 8:
            caps.append(collate.letters_only(l[:m.start()]))
    return caps


def est_legende(ws_toks, caps):
    s = collate.letters_only(''.join(t.s for t in ws_toks if t.kind == 'w'))
    if len(s) < 8:
        return False
    if any(re.fullmatch(r'pa[gq]e?', t.s.lower()) and k + 1 < len(ws_toks) and ws_toks[k + 1].s.isdigit()
           for k, t in enumerate(ws_toks)):
        return True
    return any(collate.edit_distance(s, c, cap=40) <= max(3, len(c) // 5) for c in caps if abs(len(c) - len(s)) < 40)


# ---------------------------------------------------------------- typographie de la copie
def typo(x):
    x = x.replace("'", '’').replace('...', '…')
    x = re.sub(r'\s+([,.])', r'\1', x)
    x = re.sub(r'[ \u00a0\u202f]*([;:!?»])', NNBSP + r'\1', x)
    x = re.sub(r'(^|[(\[])' + NNBSP + r'([;:!?»])', r'\1\2', x)
    x = re.sub(r'«[ \u00a0\u202f]*', '«' + NNBSP, x)
    x = re.sub(r'([!?;:»,])(?=[^\s\u202f\u00a0,.;:!?»…)\]—-])', r'\1 ', x)
    x = re.sub(r'([!?])' + NNBSP + r'([!?])', r'\1\2', x)          # « ?! » reste collé
    x = re.sub(r'[ \t]{2,}', ' ', x)
    return x.strip()


def esc(x):
    return html.escape(x, quote=False)


# ---------------------------------------------------------------- Gallica : confiance ALTO
class Alto:
    def __init__(self, ark):
        self.dir = f'{W}/gallica/{ark}'
        self.cache = {}

    def page(self, vue):
        if vue not in self.cache:
            p = f'{self.dir}/p{int(vue):04d}.xml'
            toks = []
            if os.path.exists(p):
                b = open(p, 'rb').read()
                try:                            # déclarés ISO-8859-1, les ALTO de Gallica sont en UTF-8
                    s = b.decode('utf-8')
                except UnicodeDecodeError:
                    s = b.decode('iso-8859-1')
                for m in re.finditer(r'<String\b([^>]*)/>', s):
                    at = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
                    c = html.unescape(at.get('CONTENT', ''))
                    wc = float(at.get('WC', '0') or 0)
                    for t in collate.tokenize_text(c):
                        if t[1] != 'x':
                            toks.append((collate.key(t[0]), wc))
            self.cache[vue] = toks
        return self.cache[vue]


def wc_map(G, alto):
    """Confiance ALTO de chaque token Gallica (texte de la vue aligné sur ses chaînes ALTO)."""
    by_vue = defaultdict(list)
    for j, t in enumerate(G):
        m = re.match(r'vue (\d+)', t.mark or '')
        if m:
            by_vue[int(m.group(1))].append(j)
    wc = {}
    for vue, idx in by_vue.items():
        at = alto.page(vue)
        sm = difflib.SequenceMatcher(None, [G[j].k for j in idx], [a[0] for a in at], autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == 'equal':
                for d in range(i2 - i1):
                    wc[idx[i1 + d]] = at[j1 + d][1]
    return wc


def vue_de(t):
    m = re.match(r'vue (\d+)', t.mark or '')
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- copie : positions brutes
def raw_index(part, off):
    """Indice dans le texte brut (entités comprises) d'un décalage mesuré sur le texte désentité."""
    if off <= 0:
        return 0
    n = i = 0
    while i < len(part):
        m = re.match(r'&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);', part[i:]) if part[i] == '&' else None
        i += len(m.group(0)) if m else 1
        n += 1
        if n >= off:
            return i
    return len(part)


class Copie:
    def __init__(self, epub):
        self.epub = epub
        self.toks, self.segments = collate.extract_epub(epub)
        self.A = collate.aligned(self.toks)
        z = zipfile.ZipFile(epub)
        self.names = z.namelist()
        self.raw = {d: z.read(d).decode('utf-8') for d in self.segments}
        self.parts = {d: collate.TAG_RE.split(self.raw[d]) for d in self.segments}

    def pos(self, tok, fin=True):
        parts = self.parts[tok.doc]
        base = sum(len(p) for p in parts[:tok.seg])
        return base + raw_index(parts[tok.seg], tok.end if fin else tok.off)


# ---------------------------------------------------------------- lacunes
def lacunes(copie, Wt, paras):
    def debut_logique(a):          # un nom de locuteur et sa réplique forment un seul paragraphe
        return a == 0 or (Wt[a - 1].para != Wt[a].para and paras[Wt[a - 1].para]['nature'] != 'locuteur')

    ops = collate.align(copie.A, Wt)
    res = []
    for op, i1, i2, j1, j2 in ops:
        if op == 'equal' or (j2 - j1) <= collate.BIG_GAP:
            continue
        if op == 'replace' and (i2 - i1) <= 3 and ROMAN_P.match(copie.A[i1].s) and ROMAN_P.match(Wt[j2 - 1].s):
            # la copie renumérote : son numéro de chapitre répond au dernier numéro du témoin ; le passage
            # absent s'insère devant ce numéro, que la renumérotation corrigera
            op, i2, j2 = 'insert', i1, j2 - 1
        elif op == 'replace' and (i2 - i1) <= 3 and ROMAN_P.match(copie.A[i2 - 1].s) and ROMAN_P.match(Wt[j2 - 1].s):
            op, i1, j2 = 'insert', i2 - 1, j2 - 1
            i2 = i1
        if op != 'insert':
            print(f'  ⚠ zone non alignée copie [{i1}:{i2}] / ws [{j1}:{j2}] ({op}) : à traiter à la main')
            continue
        # glissement : un trou entre deux leçons identiques peut se placer à plusieurs endroits ;
        # on préfère celui qui commence (puis finit) sur une frontière de paragraphe logique
        cands = [(j1, j2)]
        a, b = j1, j2
        while b < len(Wt) and Wt[a].k == Wt[b].k:
            a, b = a + 1, b + 1; cands.append((a, b))
        a, b = j1, j2
        while a > 0 and Wt[a - 1].k == Wt[b - 1].k:
            a, b = a - 1, b - 1; cands.append((a, b))
        best = max(cands, key=lambda c: ((2 if debut_logique(c[0]) else 0) + (1 if c[1] >= len(Wt) or debut_logique(c[1]) else 0),
                                         -abs(c[0] - j1)))
        d = best[0] - j1
        res.append((i1 + d, best[0], best[1]))
    return res


# ---------------------------------------------------------------- divergences ws / gallica
def deplace(ws_toks, G, b1, fen=700):
    """La phrase (≥ 3 mots) se retrouve-t-elle telle quelle dans Gallica, un peu plus loin ou plus haut ?
    C'est alors une légende d'illustration, que chaque témoin place à un endroit différent."""
    k = [t.k for t in ws_toks if t.kind == 'w']
    if len(k) < 3:
        return False
    gk = [t.k for t in G[max(0, b1 - fen):b1 + fen] if t.kind == 'w']
    return any(gk[x:x + len(k)] == k for x in range(len(gk) - len(k) + 1))


def divergences(Wt, G, gops, j1, j2, lex, wc, paras, caps, base='gallica'):
    out = []
    legs = []
    for op, a1, a2, b1, b2 in gops:
        if op == 'equal' or a2 <= j1 or a1 >= j2 or (a1 == a2 and not (j1 < a1 < j2)):
            continue
        a1, a2 = max(a1, j1), min(a2, j2)
        # les noms de locuteurs et titres (filtrés par l'OCR) ne sont pas des divergences
        while a1 < a2 and paras[Wt[a1].para]['nature'] in ('locuteur', 'numero', 'titre'):
            a1 += 1
        while a2 > a1 and paras[Wt[a2 - 1].para]['nature'] in ('locuteur', 'numero', 'titre'):
            a2 -= 1
        if a1 == a2 and op != 'insert' and b1 == b2:
            continue
        if a1 == a2 and paras[Wt[min(a1, len(Wt) - 1)].para]['nature'] in ('numero', 'titre'):
            continue
        ws, ga = Wt[a1:a2], G[b1:b2]
        if not ws and not ga:
            continue
        sw, sg = ' '.join(t.s for t in ws), ' '.join(t.s for t in ga)
        conf = [wc.get(j) for j in range(b1, b2)]
        sure = bool(ga) and all(c is not None and c >= 1 for c in conf)
        voisins = [wc.get(j) for j in (b1 - 1, b2) if 0 <= j < len(G)]
        vue = next((vue_de(t) for t in (ga or G[max(0, b1 - 1):b1 + 1]) if vue_de(t)), None)
        wsw = [t for t in ws if t.kind == 'w']
        if ws and not ga and len(wsw) >= 3 and (est_legende(ws, caps) or deplace(ws, G, b1)):
            cl, choix = 'légende', 'supprimer'
            legs.append([t.k for t in wsw])
        elif ga and len([t for t in ga if t.kind == 'w']) >= 3 and any(
                any([t.k for t in ga if t.kind == 'w'][x:x + len(lg)] == lg for x in range(len(ga)))
                for lg in legs) :
            cl, choix = 'bruit', 'ws'          # la même légende, à l'endroit où Gallica l'imprime
        elif re.search(r'\bPa[gq]e\s*[\dIl]', sg) or (ga and not ws and all(
                re.fullmatch(r"[^\W\d_]|\d+|[.,;:!?'’]", t.s) or t.s.isupper() for t in ga)):
            cl, choix = 'bruit', 'ws'
        elif all(t.kind == 'p' for t in ws + ga):
            cl, choix = 'ponctuation', 'ws'
        elif ws and ga and collate.letters_only(''.join(t.s for t in ws)) == collate.letters_only(''.join(t.s for t in ga)):
            cl, choix = 'graphie', 'ws'
        elif not ga:
            cl = 'omission gallica'
            choix = 'gallica' if (len(voisins) == 2 and all(c is not None and c >= 1 for c in voisins)
                                   and all(t.kind == 'w' for t in ws) and len(ws) <= 3) else 'ws'
        elif any(t.kind == 'w' and not lex.known(t.s) for t in ga) or \
                any(len(t.s) == 1 and t.kind == 'w' and t.s.lower() not in 'aày' for t in ga):
            cl, choix = 'ocr', 'ws'
        else:
            cl = 'variante' if ws else 'ajout gallica'
            voisin_egal = ws == [] and any(G[j].k == ga[0].k for j in (b1 - 1,) if j >= 0) or \
                          (not ws and b2 < len(G) and G[b2].k == ga[-1].k)
            choix = 'gallica' if sure and not voisin_egal else 'ws'
        if base == 'ws' and choix == 'gallica' and cl in ('variante', 'ajout gallica', 'omission gallica') \
                and all(lex.known(t.s) for t in wsw):
            choix = 'ws'                    # leçon de l'édition de base, que Gallica ne fait que contrôler
        out.append({'ws': sw, 'gallica': sg, 'classe': cl, 'choix': choix, 'a1': a1, 'a2': a2,
                    'b1': b1, 'b2': b2, 'vue': vue, 'wc': conf, 'raison': '',
                    'contexte': ' '.join(t.s for t in Wt[max(0, a1 - 7):a1]) + ' ⟦' + sw + '⟧ ' +
                                ' '.join(t.s for t in Wt[a2:a2 + 5])})
    return out


def rendu_gallica(ga_toks):
    return typo(' '.join(t.s for t in ga_toks))


# ---------------------------------------------------------------- composition des paragraphes
def formes_noms(copie):
    """Formes de la copie pour composer un nom de locuteur : d'abord les noms de locuteurs
    qu'elle emploie déjà (« Le juge », « Mme Mac’Miche »), clé = nom en minuscules ; puis les
    noms propres (mot plus souvent en capitale initiale qu'en minuscule)."""
    labels = Counter()
    for d, segs in copie.segments.items():
        for t in segs:
            m = re.match(r'\s*([^:—«»,.!?]{1,50}?)(?:,[^:—«»]{0,60})?[:.]—', t or '')
            if m:
                labels[m.group(1).strip()] += 1
    f = {}
    for lab, n in labels.most_common():
        f.setdefault(('*', lab.lower()), lab)
    c = Counter(t.s for t in copie.A if t.kind == 'w')
    for s_, n in c.most_common():
        if s_[:1].isupper() and n >= 2 and n > 2 * c.get(s_.lower(), 0):
            f.setdefault(s_.lower(), s_)
    return f


def nom_locuteur(label, conv, noms):
    """« le juge, souriant. » → « Le juge, souriant » (718) ; « madame blidot, riant. » →
    « MADAME BLIDOT, riant » (729)."""
    x = label.rstrip('.').strip()
    nom, sep, reste = x.partition(',')
    if conv['casse'] == 'capitales':
        nom = nom.upper()
    elif ('*', nom.strip().lower()) in noms:
        nom = noms[('*', nom.strip().lower())]
    else:
        nom = ' '.join(noms.get(m.lower(), m) for m in nom.split(' '))
        nom = nom[:1].upper() + nom[1:]
    return typo(nom + (sep + reste if sep else ''))


def texte_para(p, Wt, idx, dv):
    """Texte d'un paragraphe Wikisource (tokens idx), avec les décisions : leçon de Gallica
    substituée, légende retirée."""
    t = p['texte']
    lo = 0 if (idx[0] == 0 or Wt[idx[0] - 1].para != p['n']) else Wt[idx[0]].off
    hi = len(t) if (idx[-1] + 1 >= len(Wt) or Wt[idx[-1] + 1].para != p['n']) else Wt[idx[-1]].end
    seg = t[lo:hi]
    reps = []
    for d in dv:
        a1, a2 = d['a1'], d['a2']
        if d['choix'] == 'supprimer' and a1 < a2 and idx[0] <= a1 and a2 - 1 <= idx[-1]:
            s, e = Wt[a1].off - lo, Wt[a2 - 1].end - lo
            m = re.search(r'\s*»?\s*(\(\s*Page[^)]*\))?\s*', seg[e:])
            e += m.end() if m else 0
            m = re.search(r'«\s*$', seg[:s])
            s -= len(m.group(0)) if m else 0
            reps.append((s, e, ' '))
        elif d['choix'] == 'gallica':
            k = d.get('etendre', 0)            # la décision couvre aussi k mots de Wikisource à droite
            if a1 < a2 and idx[0] <= a1 and a2 - 1 + k <= idx[-1]:
                reps.append((Wt[a1].off - lo, Wt[a2 - 1 + k].end - lo, d['rendu']))
            elif a1 == a2 and idx[0] <= a1 <= idx[-1]:
                s = Wt[a1].off - lo
                if k:
                    reps.append((s, Wt[a1 + k - 1].end - lo, d['rendu']))
                else:
                    reps.append((s, s, d['rendu'] + ' '))
    for s, e, r in sorted(reps, reverse=True):
        seg = seg[:s] + r + seg[e:]
    return typo(seg)


def blocs_du_trou(j1, j2, Wt, paras, dv, conv, noms, G, gal):
    par_idx = defaultdict(list)
    for j in range(j1, j2):
        par_idx[Wt[j].para].append(j)
    blocs, tete, locuteur = [], None, None
    for pn in sorted(par_idx):
        p, idx = paras[pn], par_idx[pn]
        if p['nature'] == 'numero':
            tete = {'type': 'titre', 'numero': p['texte'].rstrip('.'), 'lignes': [], 'chap': p['chap'], 'para': pn}
            blocs.append(tete); continue
        if p['nature'] == 'titre':
            if tete is None:            # le numéro est resté dans la copie, juste avant le trou
                tete = {'type': 'titre', 'numero': None, 'lignes': [], 'chap': p['chap'], 'para': pn}
                blocs.append(tete)
            tete['lignes'] += p['lignes']; continue
        tete = None
        if p['nature'] == 'locuteur':
            locuteur = (p, idx); continue
        txt = texte_para(p, Wt, idx, dv)
        if conv.get('tiret'):
            txt = re.sub(r'^—\s+', conv['tiret'], txt)
        debut, fin = idx[0], idx[-1]
        if locuteur:
            txt = nom_locuteur(locuteur[0]['texte'], conv, noms) + conv['sep'] + txt
            debut, locuteur = locuteur[1][0], None
        gv = sorted({vue_de(t) for j in range(debut, fin + 1) if not gal.uncovered[j]
                     for t in G[gal.jstart[j]:gal.jend[j]] if vue_de(t)})
        blocs.append({'type': 'p', 'texte': txt, 'chap': p['chap'], 'vues': gv, 'j': [debut, fin], 'para': pn})
    return blocs


# ---------------------------------------------------------------- composition XHTML
def titre_xhtml(bl, conv, n, forces=None, noms=None):
    lignes = [typo(l) for l in bl['lignes']]
    if forces and bl['numero'] in forces:          # titre fixé par la décision (lignes coupées au milieu d'une phrase)
        lignes = [typo(forces[bl['numero']])]
    if conv['titres'] == 'pb':                     # « Querelle pour rire. » : casse de phrase, noms propres gardés
        t = ' '.join(l.rstrip('.') for l in lignes).lower()
        t = ' '.join((noms or {}).get(w, w) for w in t.split(' '))
        t = (t[:1].upper() + t[1:] + '.') if t else ''
        num = f'<p><br/></p>\n<p class="restitution"><b>{esc(bl["numero"])}</b></p>' if bl['numero'] else ''
        tit = f'<p class="restitution"><b>{esc(t)}</b></p>' if t else ''
        return '\n'.join(x for x in (num, tit) if x)
    if not bl['numero'] or not lignes:
        if conv['titres'] in ('h3', 'h3h5'):
            num = f'<h3 id="restitution-{n}">{esc(bl["numero"])}</h3>' if bl['numero'] else ''
            tag = 'h3' if conv['titres'] == 'h3' else 'h5'
            tit = f'<{tag}>{esc(". ".join(l.rstrip(".").upper() for l in lignes))}</{tag}>' if lignes else ''
            return '\n'.join(x for x in (num, tit) if x)
    if conv['titres'] == 'h3':
        t = '. '.join(l.rstrip('.').upper() for l in lignes)
        return f'<h3 id="restitution-{n}">{esc(bl["numero"])}</h3>\n<h3>{esc(t)}</h3>'
    if conv['titres'] == 'h3h5':
        t = '. '.join(l.rstrip('.').upper() for l in lignes)
        return f'<h3 id="restitution-{n}" style="margin-top: 3em">{esc(bl["numero"])}</h3>\n<h5>{esc(t)}</h5>'
    t = '. '.join(l.rstrip('.') for l in lignes) + '.'
    t = t[:1].upper() + t[1:]
    if conv['titres'] == 'p1':
        return f'<p style="margin-top: 2em">{esc(bl["numero"])}. {esc(t)}</p>'
    return f'<p><br/></p>\n<p><b>{esc(bl["numero"])}</b></p>\n<p><b>{esc(t)}</b></p>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('id')
    ap.add_argument('--analyse', action='store_true')
    ap.add_argument('--epub', help='copie de base (par défaut : EPUB livré, sortie/)')
    args = ap.parse_args()
    i = args.id
    v = vol_info(i)
    conv = CONV[i]
    base = f'Comtesse-de-Segur-{v["slug"]}'
    epub = args.epub or f'{W}/sortie/{base}.epub'
    copie = Copie(epub)
    paras = ws_paragraphs(f'{W}/ws/{i}.txt')
    Wt = ws_tokens(paras, conv)
    ark = v['gallica']['ark']
    gtxt = open(f'{W}/gallica/{ark}.txt', encoding='utf-8').read()
    G = collate.aligned(collate.load_witness(f'{W}/gallica/{ark}.txt'))
    gops = collate.align(Wt, G)
    gal = collate.Alignment(Wt, G, gops)
    wc = wc_map(G, Alto(ark))
    lex = collate.Lexicon(f'{TOOLS}/lexicon-fr.txt.gz', copie.toks)
    caps = legendes_gallica(gtxt)
    noms = formes_noms(copie)
    dec_p = f'{OUT}/{i}-decisions.json'
    dec = json.load(open(dec_p)) if os.path.exists(dec_p) else {}
    forces = {}
    for d in dec.get('decisions', []):
        forces[d.get('contexte') or (str(d['vue']), d['ws'], d['gallica'])] = d
    gaps = lacunes(copie, Wt, paras)
    wsinfo = json.load(open(f'{W}/ws/{i}.json'))
    plan = {'volume': i, 'titre': v['titre'], 'copie': os.path.basename(epub),
            'copie_md5': hashlib.md5(open(epub, 'rb').read()).hexdigest(),
            'temoins': {'ws': {'page': wsinfo.get('page'), **wsinfo.get('index', {})},
                        'gallica': {'ark': ark, 'edition': v['gallica']['edition']}},
            'lacunes': []}
    vus = set()
    for n, (i1, j1, j2) in enumerate(gaps, 1):
        a = copie.A[i1 - 1]
        b = copie.A[i1] if i1 < len(copie.A) else None
        dv = divergences(Wt, G, gops, j1, j2, lex, wc, paras, caps, conv.get('base', 'gallica'))
        for d in dv:
            cle = d['contexte'] if d['contexte'] in forces else (str(d['vue']), d['ws'], d['gallica'])
            f = forces.get(cle)
            if f:
                vus.add(cle)
                d['choix'], d['raison'] = f['choix'], f.get('raison', '')
                d['force'] = True
                for k in ('rendu', 'etendre'):
                    if k in f:
                        d[k] = f[k]
            if d['choix'] == 'gallica' and 'rendu' not in d:
                d['rendu'] = rendu_gallica(G[d['b1']:d['b2']])
        blocs = blocs_du_trou(j1, j2, Wt, paras, dv, conv, noms, G, gal)
        tete_inline = j1 > 0 and Wt[j1 - 1].para == Wt[j1].para
        queue_inline = j2 < len(Wt) and Wt[j2 - 1].para == Wt[j2].para
        lac = {'n': n, 'copie_i': i1, 'ws': [j1, j2], 'doc': a.doc,
               'avant': ' '.join(t.s for t in copie.A[max(0, i1 - 14):i1]),
               'apres': ' '.join(t.s for t in copie.A[i1:i1 + 12]),
               'copie_meme_paragraphe': bool(b and a.para == b.para and a.doc == b.doc),
               'tete_inline': tete_inline, 'queue_inline': queue_inline,
               'mots': sum(1 for j in range(j1, j2) if Wt[j].kind == 'w'),
               'chapitres_ws': sorted({paras[Wt[j].para]['chap'] for j in range(j1, j2)}, key=lambda c: (len(c or ''), c or '')),
               'vues': sorted({x for bl in blocs if bl['type'] == 'p' for x in bl['vues']}),
               'blocs': blocs, 'divergences': dv}
        plan['lacunes'].append(lac)
        print(f'\n=== L{n} copie [{i1}] ws [{j1}:{j2}] = {lac["mots"]} mots, chapitres ws {lac["chapitres_ws"]}, '
              f'vues {lac["vues"][:1]}–{lac["vues"][-1:]} ; copie même ¶ : {lac["copie_meme_paragraphe"]} ; '
              f'tête inline {tete_inline}, queue inline {queue_inline}')
        print('  copie :', lac['avant'][-80:], '⟦⟧', lac['apres'][:60])
        print('  blocs :', Counter(bl['type'] for bl in blocs), '| titres :',
              [(bl['numero'], bl['lignes']) for bl in blocs if bl['type'] == 'titre'])
        print('  divergences :', dict(Counter((d['classe'], d['choix']) for d in dv)))
        if args.analyse:
            for d in dv:
                if d['classe'] in ('variante', 'ajout gallica', 'omission gallica', 'légende') or d['choix'] == 'gallica':
                    print(f'    [{d["classe"]} → {d["choix"]}{" (forcé)" if d.get("force") else ""}] vue {d["vue"]} '
                          f'wc {d["wc"]} : ws « {d["ws"]} » / gallica « {d["gallica"]} » — {d["contexte"]}')
    manquants = set(forces) - vus
    if manquants:
        print('\n⚠ décisions sans divergence correspondante :', manquants)
    if args.analyse:
        return
    os.makedirs(OUT, exist_ok=True)
    ecrit(f'{OUT}/{i}-plan.json', json.dumps(plan, ensure_ascii=False, indent=1))
    construit(i, v, conv, copie, plan, dec)


# ---------------------------------------------------------------- EPUB proposé
def paragraphe_ouvrant(raw, pos):
    """Balise ouvrante du paragraphe qui contient pos."""
    k = raw.rfind('<p', 0, pos)
    return raw[k:raw.index('>', k) + 1] if k >= 0 else '<p>'


def construit(i, v, conv, copie, plan, dec):
    docs = {d: copie.raw[d] for d in copie.raw}
    edits = defaultdict(list)          # doc → (position, longueur remplacée, texte)
    ntitre = 0
    notes = []
    for lac in plan['lacunes']:
        A = copie.A
        a = A[lac['copie_i'] - 1]
        b = A[lac['copie_i']] if lac['copie_i'] < len(A) else None
        blocs = lac['blocs']
        ps = [bl for bl in blocs]
        tete = ps[0]['texte'] if lac['tete_inline'] and ps and ps[0]['type'] == 'p' else None
        if tete is not None:
            ps = ps[1:]
        queue = ps[-1]['texte'] if lac['queue_inline'] and ps and ps[-1]['type'] == 'p' else None
        if queue is not None:
            ps = ps[:-1]
        corps = []
        for bl in ps:
            if bl['type'] == 'titre':
                ntitre += 1
                corps.append(titre_xhtml(bl, conv, ntitre, dec.get('titres'), formes_noms(copie)))
            else:
                corps.append(f'<p>{esc(bl["texte"])}</p>')
        raw = docs[a.doc]
        pa = copie.pos(a)
        if lac['copie_meme_paragraphe']:
            pb = copie.pos(b, fin=False)
            entre = raw[pa:pb]
            if '<' in entre:
                raise SystemExit(f'L{lac["n"]} : balise entre les deux mots de la copie ({entre!r}), à traiter à la main')
            ouv = paragraphe_ouvrant(raw, pa)
            ouv = re.sub(r'\s+id="[^"]*"', '', ouv)
            if not corps and tete is not None and queue is None and not lac['queue_inline']:
                ins = ' ' + esc(tete) + entre
            elif not corps and tete is not None and lac['queue_inline'] and queue is None:
                ins = ' ' + esc(tete) + ' '         # le trou tient dans un seul paragraphe
            else:
                ins = ((' ' + esc(tete)) if tete else '') + '</p>\n' + '\n'.join(corps) + '\n' + ouv + \
                      ((esc(queue) + ' ') if queue else '')
            edits[a.doc].append((pa, pb - pa, ins))
            notes.append(f'L{lac["n"]} : paragraphe de la copie coupé après « …{lac["avant"][-40:]} »')
        else:
            if tete:
                edits[a.doc].append((pa, 0, ' ' + esc(tete)))
            k = raw.find('</p>', pa)
            if k < 0:
                raise SystemExit(f'L{lac["n"]} : fin de paragraphe introuvable')
            if corps:
                edits[a.doc].append((k + 4, 0, '\n' + '\n'.join(corps)))
            if queue:
                if b is None:
                    raise SystemExit(f'L{lac["n"]} : queue sans suite dans la copie')
                pb = copie.pos(b, fin=False)
                rb = docs[b.doc]
                avant_b = rb[rb.rfind('>', 0, pb) + 1:pb]
                if avant_b.strip():
                    notes.append(f'L{lac["n"]} : signes avant la reprise de la copie : {avant_b!r}')
                edits[b.doc].append((pb, 0, esc(queue) + ' '))
    for d, ed in edits.items():
        raw = docs[d]
        for p, ln, txt in sorted(ed, key=lambda e: e[0], reverse=True):
            raw = raw[:p] + txt + raw[p + ln:]
        docs[d] = raw
    # renumérotation des chapitres et retitrages décidés
    retit = dec.get('retitrer', {})
    chap_log, chaps = renumerote(docs, conv, copie, retit)
    # table des matières imprimée dans le livre (729) : refaite d'après les titres
    if conv['titres'] == 'pb' and chaps:
        for d in docs:
            m = re.search(r'(>Table des matières</p>\s*<p[^>]*>)(.*?)(</p>)', docs[d], re.S)
            if m:
                # les lignes de la copie gardent leur texte (casse comprise), seul leur numéro change ;
                # les chapitres rendus reçoivent une ligne composée d'après leur titre
                anciennes = [re.sub(r'^\s*[IVXLC]+\.?\s*', '', l) for l in re.split(r'<br\s*/>\s*', m.group(2).strip())]
                lignes, k = [], 0
                for _, _, num, _, t1, neuf_ in chaps:
                    if neuf_ or k >= len(anciennes):
                        lignes.append(f'{num}. ' + esc(re.sub(r'\.$', '', t1.strip())))
                    else:
                        lignes.append(f'{num}. ' + anciennes[k]); k += 1
                docs[d] = docs[d][:m.start(2)] + '<br/>\n'.join(lignes) + docs[d][m.end(2):]
                chap_log.append('table des matières du livre : numéros refaits, lignes des chapitres rendus ajoutées')
    # table des matières (toc.ncx) : retouchée, pas régénérée
    z = zipfile.ZipFile(copie.epub)
    ncx_n = next((n for n in copie.names if n.endswith('.ncx')), None)
    ncx = z.read(ncx_n).decode('utf-8') if ncx_n else None
    if ncx and conv['titres'] in ('h3', 'h3h5') and any(c[0] for c in chaps):
        ncx = refait_ncx(ncx, chaps, copie)
    os.makedirs(OUT, exist_ok=True)
    base = f'Comtesse-de-Segur-{v["slug"]}'
    dst = f'{OUT}/{base}.restitution.epub'
    with zipfile.ZipFile(dst + '.tmp', 'w') as zo:
        zo.writestr(zipfile.ZipInfo('mimetype'), z.read('mimetype'), compress_type=zipfile.ZIP_STORED)
        for n in copie.names:
            if n == 'mimetype':
                continue
            data = docs[n].encode('utf-8') if n in docs else (ncx.encode('utf-8') if n == ncx_n and ncx else z.read(n))
            zo.writestr(n, data, compress_type=zipfile.ZIP_DEFLATED)
    os.replace(dst + '.tmp', dst)
    r = subprocess.run(['java', '-jar', EPUBCHECK, dst], capture_output=True, text=True)
    m = re.search(r'Messages: (\d+) fatals? / (\d+) errors? / (\d+) warnings?', r.stdout + r.stderr)
    ec = {'fatals': int(m.group(1)), 'erreurs': int(m.group(2)), 'avertissements': int(m.group(3))} if m else {'sortie': (r.stdout + r.stderr)[-800:]}
    kep = None
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['kepubify', '-o', tmp, dst], capture_output=True, text=True)
        outs = glob.glob(f'{tmp}/*.kepub.epub')
        if outs:
            kep = f'{OUT}/{base}.restitution.kepub.epub'
            shutil.move(outs[0], kep)
            os.chmod(kep, 0o644)
    res = {'epub': os.path.basename(dst), 'epub_md5': hashlib.md5(open(dst, 'rb').read()).hexdigest(),
           'epubcheck': ec, 'kepub': os.path.basename(kep) if kep else None, 'notes': notes, 'chapitres': chap_log}
    plan['resultat'] = res
    ecrit(f'{OUT}/{i}-plan.json', json.dumps(plan, ensure_ascii=False, indent=1))
    rapport(i, v, conv, plan, dec)
    print(f'\n{i} : EPUB proposé {dst} ; epubcheck {ec} ; kepub {"ok" if kep else "ÉCHEC"}')
    for x in notes + chap_log:
        print('  ', x)


def renumerote(docs, conv, copie, retit):
    """Numéros de chapitre refaits dans l'ordre du livre ; titres changés selon `retit`
    (ancien numéro de la copie → nouveau titre). Rend (journal, chapitres) où chapitres =
    [(ancre, ancien numéro, nouveau numéro, ancien titre, nouveau titre, restitué)]."""
    log, chaps = [], []
    n = 0
    for d in [d for d in copie.segments if d in docs]:
        raw = docs[d]
        if conv['titres'] in ('h3', 'h3h5'):
            pat = re.compile(r'(<h3\b[^>]*>)\s*([IVXLC]+)\s*(</h3>)(\s*<h[35]\b[^>]*>)(.*?)(</h[35]>)', re.S)
        elif conv['titres'] == 'p1':
            pat = re.compile(r'(<p\b[^>]*margin-top: 2em[^>]*>)\s*([IVXLC]+)(\.)(\s)(.*?)(</p>)', re.S)
        else:
            pat = re.compile(r'(<p[^>]*><b>)\s*([IVXLC]+)\s*(</b></p>)(\s*<p[^>]*><b>)(.*?)(</b></p>)', re.S)
        out, last = [], 0
        for m in pat.finditer(raw):
            n += 1
            num, ancien, titre = romain(n), m.group(2), m.group(5)
            # chapitre rendu : son numéro (h3) ou son titre (729, où le numéro peut rester celui de la copie)
            neuf_ = 'restitution' in (m.group(4) if conv['titres'] == 'pb' else m.group(1))
            if not neuf_ and retit.get(ancien):
                titre = esc(typo(retit[ancien]))
            if not neuf_ and (num != ancien or titre != m.group(5)):
                log.append(f'chapitre {ancien} « {html.unescape(m.group(5))[:60]} » → {num} « {html.unescape(titre)[:60]} »')
            ida = re.search(r'\bid="([^"]+)"', m.group(1))
            chaps.append((ida.group(1) if ida else None, ancien, num, html.unescape(m.group(5)), html.unescape(titre), neuf_))
            out.append(raw[last:m.start()] + m.group(1) + num + m.group(3) + m.group(4) + titre + m.group(6))
            last = m.end()
        out.append(raw[last:])
        docs[d] = ''.join(out)
    return log, chaps


def refait_ncx(ncx, chaps, copie):
    """Retouche minimale de toc.ncx : libellé des chapitres renumérotés ou retitrés, entrées
    nouvelles pour les chapitres restitués (après le chapitre qui les précède, même niveau),
    playOrder refait dans l'ordre."""
    ncx_dir = os.path.dirname(next(n for n in copie.names if n.endswith('.ncx')))
    doc_of = {}
    for d in copie.segments:
        for a in re.findall(r'<h3\b[^>]*\bid="([^"]+)"', copie.raw[d]):
            doc_of[a] = d
    prec = None
    for ancre, ancien, num, t0, t1, neuf_ in chaps:
        lab = f'{num} {re.sub(r"<[^>]+>", "", t1).strip()}'
        if not neuf_:
            if num != ancien or t0 != t1:
                m = re.search(r'(<content\s+src="[^"#]*#' + re.escape(ancre) + r'"\s*/>)', ncx)
                k = ncx.rfind('<navPoint', 0, m.start()) if m else -1
                t = re.compile(r'<text>.*?</text>', re.S).search(ncx, k) if k >= 0 else None
                if t:
                    ncx = ncx[:t.start()] + f'<text>{html.escape(lab, quote=False)}</text>' + ncx[t.end():]
            prec = ancre
            continue
        # chapitre restitué : son ancre est dans le document du chapitre précédent ou suivant
        m = re.search(r'<content\s+src="([^"#]*)#' + re.escape(prec) + r'"\s*/>', ncx)
        fin = ncx.index('</navPoint>', m.end()) + len('</navPoint>')
        src = m.group(1)
        pt = (f'\n<navPoint id="np-{ancre}" playOrder="0"><navLabel><text>{html.escape(lab, quote=False)}</text>'
              f'</navLabel><content src="{src}#{ancre}"/></navPoint>')
        ncx = ncx[:fin] + pt + ncx[fin:]
        prec = ancre
    k = [0]

    def po(m):
        k[0] += 1
        return f'playOrder="{k[0]}"'
    return re.sub(r'playOrder="\d+"', po, ncx)


# ---------------------------------------------------------------- rapport
def rapport(i, v, conv, plan, dec):
    ark = plan['temoins']['gallica']['ark']
    ws = plan['temoins']['ws']
    L = [f'# Restitution proposée des lacunes — *{v["titre"].replace(chr(39), "’")}*, comtesse de Ségur', '',
         f'- **Copie** : `{plan["copie"]}` (volume livré, md5 `{plan["copie_md5"]}`) ; rien n’y est remplacé.',
         f'- **Témoin de base** : Gallica, {plan["temoins"]["gallica"]["edition"]}, https://gallica.bnf.fr/ark:/12148/{ark} '
         '(OCR ALTO, confiance mot à mot).',
         f'- **Témoin de contrôle** : Wikisource, « {ws.get("page")} », {ws.get("Editeur", "?")}, {ws.get("Annee", "?")} '
         '(transcription relue).',
         f'- **Proposé** : `{plan["resultat"]["epub"]}` (md5 `{plan["resultat"]["epub_md5"]}`), epubcheck '
         f'{plan["resultat"]["epubcheck"].get("erreurs", "?")} erreur, et son KEPUB.',
         '', '## Règles', '',
         '- Là où Gallica et Wikisource s’accordent, le texte passe tel quel, en typographie de la copie.',
         '- Là où ils divergent sur les mots, la leçon de Gallica est retenue quand l’OCR en est sûr (confiance ALTO 1) '
         'et qu’elle n’est pas un bruit de lecture ; sinon celle de Wikisource. Chaque cas est listé plus bas, décision et raison.',
         '- Ponctuation et graphies (accents, traits d’union) : celles de Wikisource, qui sont celles du reste de la copie ; '
         'l’OCR n’est pas assez sûr sur les signes pour trancher.',
         '- Noms de locuteurs : ceux de Wikisource (l’OCR les filtre), composés comme dans la copie ; légendes '
         'd’illustrations écartées ; italiques non restituées (aucun des deux témoins texte ne les porte).', '']
    if dec.get('note'):
        L += [dec['note'], '']
    for lac in plan['lacunes']:
        vs = lac['vues']
        L += [f'## Lacune {lac["n"]} — {fmt(lac["mots"])} mots (Wikisource, sous-pages {", ".join(lac["chapitres_ws"])} ; '
              f'Gallica, vues {vs[0]}–{vs[-1]})' if vs else f'## Lacune {lac["n"]} — {fmt(lac["mots"])} mots', '',
              f'Dans la copie, entre « …{collate_txt(lac["avant"])[-70:]} » et « {collate_txt(lac["apres"])[:60]}… ».', '']
        for bl in lac['blocs']:
            if bl['type'] == 'titre':
                L += [f'**{bl["numero"]}** — *{" / ".join(bl["lignes"])}* (titre de chapitre, Wikisource « {bl["chap"]} »)', '']
            else:
                tr = f'Wikisource « {v["ws"]["page"]}/{bl["chap"]} » ; Gallica ' + (
                    ', '.join(f'[vue {x}](https://gallica.bnf.fr/ark:/12148/{ark}/f{x}.item)' for x in bl['vues']) if bl['vues'] else '—')
                L += [f'> {bl["texte"]}', f'> <small>{tr}</small>', '']
        dv = [d for d in lac['divergences'] if d['classe'] not in ('ponctuation', 'bruit', 'graphie', 'ocr')]
        cnt = Counter(d['classe'] for d in lac['divergences'])
        L += [f'**Divergences Wikisource / Gallica** : {", ".join(f"{k} {n}" for k, n in sorted(cnt.items()))}. '
              'Ponctuation, graphie, bruit et erreurs d’OCR : leçon de Wikisource (détail dans le plan JSON).', '']
        if dv:
            L += ['| Vue | Wikisource | Gallica | Retenu | Raison |', '|---|---|---|---|---|']
            for d in dv:
                raison = d.get('raison') or {
                    'légende': 'légende d’illustration, écartée',
                    'omission gallica': 'mot absent de Gallica' + (', lecture sûre autour : Gallica' if d['choix'] == 'gallica'
                                                                  else ', lecture incertaine autour : Wikisource'),
                    'ajout gallica': 'mot en plus dans Gallica' + (', lecture sûre : Gallica' if d['choix'] == 'gallica'
                                                                   else ', lecture incertaine ou doublon : Wikisource'),
                    'variante': 'leçons différentes' + (', lecture sûre : Gallica' if d['choix'] == 'gallica'
                                                        else ', lecture de l’OCR incertaine : Wikisource'),
                }.get(d['classe'], '')
                ret = {'gallica': 'Gallica', 'ws': 'Wikisource', 'supprimer': '—'}[d['choix']]
                vl = f'[{d["vue"]}](https://gallica.bnf.fr/ark:/12148/{ark}/f{d["vue"]}.item)' if d['vue'] else '—'
                L.append(f'| {vl} | {md(collate_txt(d["ws"])) or "∅"} | {md(collate_txt(d["gallica"])) or "∅"} | {ret} | {md(raison)} |')
            L.append('')
    res = plan['resultat']
    if res['chapitres'] or res['notes']:
        L += ['## Structure', ''] + [f'- {x}' for x in res['notes'] + res['chapitres']] + ['']
    ecrit(f'{OUT}/{i}-{v["slug"]}-restitution.md', '\n'.join(L) + '\n')


def collate_txt(x):
    x = re.sub(r' ([,.])', r'\1', x or '')
    x = re.sub(r' ([;:!?])', NNBSP + r'\1', x)
    return re.sub(r" ?([’']) ?", '’', x)


def md(s):
    return (s or '').replace('|', '\\|').replace('\n', ' ')


def fmt(n):
    return f'{n:,}'.replace(',', NNBSP)


if __name__ == '__main__':
    main()
