#!/usr/bin/env python3
"""Diff tabulaire avant/après pour epub_typo_fix.py.

Compare deux EPUB document par document, regroupe les micro-changements par
motif (avant → après) et par règle, et émet un HTML relisible.
"""
import sys, html, zipfile, difflib, re
from collections import Counter, defaultdict

CTX = 45

def docs(path):
    z = zipfile.ZipFile(path)
    out = {}
    for n in z.namelist():
        if re.search(r'\.(x?html|htm)$', n, re.I):
            out[n] = z.read(n).decode('utf-8', 'replace')
    return out

SP = {" ", "\u00a0", "\u202f"}

def classify(a, b):
    sa, sb = a.strip(" \u00a0\u202f"), b.strip(" \u00a0\u202f")
    if sa in ("'", "\u2032") and sb == "\u2019":
        return "R1 apostrophe courbe"
    if sa == "..." and sb == "\u2026":
        return "R5 points de suspension"
    if sa in ("-", "\u2013") and sb == "\u2014":
        return "R3 tiret cadratin"
    if a in ("'", "′") and b == "’":
        return "R1 apostrophe courbe"
    if a == "..." and b == "…":
        return "R5 points de suspension"
    if a in ("-", "–") and b == "—":
        return "R3 tiret cadratin"
    if a == "" and b in (" ", " "):
        return "R4 insécable insérée"
    if a == " " and b in (" ", " "):
        return "R4 espace → insécable"
    if set(b) <= {" ", " ", " "} and set(a) <= {" ", " ", " "}:
        return "R4 espacement"
    # R2 — ligature restaurée : « coeur » → « cœur », y compris quand la diff
    # englobe l'apostrophe que R1 vient de courber (« l'oeil » → « l’œil »).
    if (sa.replace("'", "").replace("’", "") in ("oe", "OE", "Oe")
            and sb.replace("'", "").replace("’", "") in ("œ", "Œ")):
        return "R2 ligature œ"
    # R6 — capitale accentuée : la diff ne porte que sur la lettre, éventuellement
    # précédée de cette même apostrophe (« l'Etat » → « l’État »).
    CAPS = {"E": "É", "A": "À", "O": "Ô", "U": "Ù", "I": "Î", "e": "é"}
    ta, tb = sa.lstrip("'’"), sb.lstrip("'’")
    if len(ta) == 1 and len(tb) == 1 and CAPS.get(ta) == tb:
        return "R6 capitale accentuée"
    # R3b/R3c — l'espace que le correcteur pose autour du cadratin : après lui en
    # début de réplique, des deux côtés pour une incise. La diff ne voit alors
    # qu'une espace apparaître à côté d'un tiret déjà présent.
    if a == "" and b and set(b) <= {" ", " ", " "}:
        return "R4/R3 espace insérée"
    return "AUTRE"

def vis(s):
    return (s.replace(" ", "⍽").replace(" ", "␣")
             .replace("’", "’").replace("—", "—").replace("…", "…"))

def residus(dst):
    """Ce que le correcteur a laissé passer — c'est là que se cachent ses trous."""
    z = zipfile.ZipFile(dst)
    R = ["<h2>Résidus après passe — relevé exhaustif</h2>",
         "<table><tr><th>Type</th><th>Document</th><th>Contexte</th></tr>"]
    n = 0
    for name in sorted(z.namelist()):
        if not re.search(r'\.(x?html|htm)$', name, re.I):
            continue
        t = re.sub(r'<[^>]*>', '', z.read(name).decode('utf-8', 'replace'))
        for lab, rx in (("apostrophe droite", r"'"), ("« sur espace sécable", "«[ \t]"),
                        ("espace sécable avant ponctuation double", "[ \t][?!;:»]"),
                        ("... non converti", r'\.\.\.')):
            for m in re.finditer(rx, t):
                n += 1
                ctx = " ".join(t[max(0, m.start() - 50):m.end() + 50].split())
                R.append("<tr><td>{}</td><td><small>{}</small></td><td>{}</td></tr>".format(
                    lab, html.escape(name), html.escape(vis(ctx))))
    R.append("</table>")
    R.insert(1, "<p><b>{}</b> résidus.</p>".format(n))
    return "\n".join(R)


def main(src, dst, out_html):
    A, B = docs(src), docs(dst)
    rules = Counter()
    patterns = defaultdict(Counter)          # rule -> (before,after) -> n
    examples = {}                            # (rule,before,after) -> (doc, context)
    others = []
    for name in sorted(A):
        a, b = A[name], B.get(name, A[name])
        if a == b:
            continue
        ua = re.findall(r'[^\n>]*[\n>]?', a)
        ub = re.findall(r'[^\n>]*[\n>]?', b)
        offa = []
        p = 0
        for u in ua:
            offa.append(p); p += len(u)
        pairs = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ua, ub, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            if i2 - i1 == j2 - j1:
                pairs += [(i1 + k, ua[i1 + k], ub[j1 + k]) for k in range(i2 - i1)]
            else:
                pairs.append((i1, "".join(ua[i1:i2]), "".join(ub[j1:j2])))
        micro = []
        for idx, la, lb in pairs:
            base = offa[idx]
            for tag, x1, x2, y1, y2 in difflib.SequenceMatcher(None, la, lb, autojunk=False).get_opcodes():
                if tag != 'equal':
                    micro.append((base + x1, base + x2, la[x1:x2], lb[y1:y2]))
        for i1, i2, before, after in micro:
            r = classify(before, after)
            rules[r] += 1
            patterns[r][(before, after)] += 1
            key = (r, before, after)
            ex = examples.setdefault(key, [])
            if len(ex) < 12:
                ctx = a[max(0, i1 - CTX):i1] + "\u3010{}\u3011".format(before) + a[i2:i2 + CTX]
                ex.append((name, " ".join(ctx.split())))
            if r == "AUTRE":
                ctx = a[max(0, i1 - CTX):i1] + "‹{}›".format(before) + a[i2:i2 + CTX]
                others.append((name, before, after, ctx.replace("\n", " ")))
    total = sum(rules.values())
    W = []
    W.append("<meta charset='utf-8'><style>body{font:15px/1.5 Palatino,Georgia,serif;background:#faf7f2;color:#241f1a;max-width:1100px;margin:2rem auto;padding:0 1rem}table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:13px}td,th{border:1px solid #ddd5c8;padding:.35rem .5rem;vertical-align:top;text-align:left}th{background:#efe8dc}code{font-family:ui-monospace,monospace;font-size:12px}del{background:#fbdcdc;text-decoration:none}ins{background:#d8f0d8;text-decoration:none}h2{margin-top:2.5rem;border-bottom:1px solid #ddd5c8}.n{text-align:right;font-variant-numeric:tabular-nums}</style>")
    W.append("<h1>Diff typographique — {}</h1>".format(html.escape(src.split('/')[-1])))
    W.append("<p><b>{}</b> changements. ⍽ = fine U+202F, ␣ = insécable U+00A0.</p>".format(total))
    W.append("<table><tr><th>Règle</th><th class=n>Nb</th><th class=n>Motifs distincts</th></tr>")
    for r, n in rules.most_common():
        W.append("<tr><td>{}</td><td class=n>{}</td><td class=n>{}</td></tr>".format(r, n, len(patterns[r])))
    W.append("</table>")
    for r, _ in rules.most_common():
        W.append("<h2>{} — {} changements, {} motifs</h2>".format(html.escape(r), rules[r], len(patterns[r])))
        W.append("<table><tr><th class=n>Nb</th><th>Avant → Après</th><th>Exemple in situ (document)</th></tr>")
        for (bef, aft), n in patterns[r].most_common():
            cell = "<br>".join("{}<br><small>{}</small>".format(html.escape(vis(c)), html.escape(d))
                               for d, c in examples[(r, bef, aft)])
            W.append("<tr><td class=n>{}</td><td><code><del>{}</del> \u2192 <ins>{}</ins></code></td>"
                     "<td>{}</td></tr>".format(n, html.escape(vis(bef)) or "\u2205",
                                               html.escape(vis(aft)) or "\u2205", cell))
        W.append("</table>")
    W.append(residus(dst))
    open(out_html, "w").write("\n".join(W))
    print("total:", total)
    for r, n in rules.most_common():
        print("  {:28s} {:6d}  ({} motifs)".format(r, n, len(patterns[r])))
    print("AUTRE (à relire un par un):", len(others))
    for o in others[:40]:
        print("   ", o[0], "|", repr(o[1]), "->", repr(o[2]), "|", o[3][:160])

main(*sys.argv[1:4])
