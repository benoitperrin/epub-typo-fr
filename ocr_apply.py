#!/usr/bin/env python3
"""
ocr_apply.py — Applique des corrections textuelles ciblées à un EPUB, sous contrainte.

Entrée corrections (JSONL) : {"doc", "chercher", "remplacer", "raison"?, "source"?}
  - `chercher` doit apparaître EXACTEMENT UNE FOIS dans les segments texte du doc
    (jamais à cheval sur une balise) ;
  - distance d'édition ≤ --max-edit (12), delta mots ≤ 2, delta longueur ≤ 40 ;
  - budget global : ≤ max(25, 0,2 % des mots du livre).
Toute correction rejetée est loggée avec sa raison ; rien n'est appliqué en force.

Sortie : EPUB corrigé + rapport markdown (--report) listant chaque modification
avec contexte, pour relecture humaine.

Usage:
  python3 ocr_apply.py in.epub out.epub corrections.jsonl --report diff.md
"""
import sys, os, re, json, zipfile, html, argparse
from collections import defaultdict

TAG_RE = re.compile(r'(<[^>]+>|<!--.*?-->)', re.S)
SKIP_CONTENT = {'style', 'script', 'pre', 'code', 'svg'}
# Le NCX et l'OPF sont du XML à nœuds texte : libellés de la table des matières,
# titre, auteur. Ils portent les mêmes fautes que le corps du livre et le
# correcteur typographique, lui, ne les traite pas.
PATCHABLE = ('.xhtml', '.html', '.htm', '.ncx', '.opf')


def edit_distance(a, b, cap=50):
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = cap + 1
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            best = min(best, v)
        if best > cap:
            return cap + 1
        prev = cur
    return prev[-1]


SPACE_ANY = '\u00a0\u202f\u2009\n'   # insécable, fine insécable, fine, retour à la ligne (source composée ligne à ligne)

def norm_spaces(s):
    for c in SPACE_ANY:
        s = s.replace(c, ' ')
    return s


def tolerant_find(seg_texts, ch):
    """Recherche de `ch` avec tolérance sur les espaces insécables/fines.
    Retourne (seg_idx, span_réel) si match unique, sinon (None, total_hits)."""
    chn = norm_spaces(ch)
    hits = []
    for i, t in seg_texts:
        tn = norm_spaces(t)
        start = 0
        while True:
            p = tn.find(chn, start)
            if p < 0:
                break
            hits.append((i, p))
            start = p + 1
    if len(hits) != 1:
        return None, len(hits)
    return hits[0], 1


def splice_replacement(actual, ch, rp):
    """Construit le remplacement en préservant les espaces réelles (fines) de
    `actual` partout où chercher/remplacer coïncident (modulo espaces)."""
    import difflib
    chn, rpn = norm_spaces(ch), norm_spaces(rp)
    sm = difflib.SequenceMatcher(a=chn, b=rpn, autojunk=False)
    out = []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == 'equal':
            out.append(actual[a1:a2])      # garde les caractères réels (fines)
        else:
            out.append(rp[b1:b2])          # texte nouveau tel que fourni
    return ''.join(out)


def fuse_overlapping(todo, seg_texts, rejected):
    """Deux corrections dont les citations se chevauchent dans le même nœud de texte ne
    s'appliquent pas l'une après l'autre : la première change le contexte que cite la
    seconde (« en revenant, … grâce à Mme Juivet, … » : deux virgules, deux corrections,
    la seconde « introuvable »). On les fond en une seule qui cite l'union des passages,
    pourvu que leurs changements eux-mêmes ne se touchent pas ; sinon elles sont en
    conflit et rejetées toutes deux."""
    located, rest = [], []
    for c in todo:
        ch = c['chercher']
        where = [(i, t.find(ch)) for i, t in seg_texts if ch in t]
        if len(where) == 1 and sum(t.count(ch) for _, t in seg_texts) == 1:
            located.append((where[0][0], where[0][1], c))
        else:
            rest.append(c)
    located.sort(key=lambda x: (x[0], x[1]))
    texts, out, k = dict(seg_texts), [], 0
    while k < len(located):
        i, a, c = located[k]
        group, end = [(a, c)], a + len(c['chercher'])
        k += 1
        while k < len(located) and located[k][0] == i and located[k][1] < end:
            group.append((located[k][1], located[k][2]))
            end = max(end, located[k][1] + len(located[k][2]['chercher']))
            k += 1
        if len(group) == 1:
            out.append(c)
            continue
        changes = []
        for pos, cc in group:
            ch, rp = cc['chercher'], cc['remplacer']
            pre = 0
            while pre < min(len(ch), len(rp)) and ch[pre] == rp[pre]:
                pre += 1
            suf = 0
            while suf < min(len(ch), len(rp)) - pre and ch[-1 - suf] == rp[-1 - suf]:
                suf += 1
            changes.append((pos + pre, pos + len(ch) - suf, rp[pre:len(rp) - suf]))
        changes.sort()
        if any(changes[j][1] > changes[j + 1][0] for j in range(len(changes) - 1)):
            rejected.extend((cc, 'corrections en conflit sur le même passage') for _, cc in group)
            continue
        merged = texts[i][a:end]
        for s0, e0, new in reversed(changes):
            merged = merged[:s0 - a] + new + merged[e0 - a:]
        fused = dict(group[0][1])
        fused.update(chercher=texts[i][a:end], remplacer=merged, fusion=len(group),
                     _parts=[cc for _, cc in group],
                     raison=' + '.join(cc.get('raison', '') for _, cc in group),
                     source=' + '.join(dict.fromkeys(cc.get('source', '') for _, cc in group)))
        out.append(fused)
    return out + rest


def split_doc(htm):
    """[(is_tag, fragment, in_skip)], reconstruction = concat des fragments."""
    parts = []
    skip = 0
    for part in TAG_RE.split(htm):
        if part.startswith('<'):
            m = re.match(r'</?\s*([a-zA-Z0-9]+)', part)
            tag = m.group(1).lower() if m else ''
            if tag in SKIP_CONTENT:
                skip += 1 if not part.startswith('</') else -1
                skip = max(skip, 0)
            parts.append((True, part, skip > 0))
        else:
            parts.append((False, part, skip > 0))
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('infile'); ap.add_argument('outfile'); ap.add_argument('corrections')
    ap.add_argument('--report')
    ap.add_argument('--report-html', help='rapport HTML (tableau, diff inline surligné)')
    ap.add_argument('--titre', default='', help='titre du livre pour le rapport HTML')
    ap.add_argument('--max-edit', type=int, default=12)
    ap.add_argument('--max-word-delta', type=int, default=2)
    ap.add_argument('--budget-pct', type=float, default=0.2)
    ap.add_argument('--insertion-max', type=int, default=0,
                    help="accepter une insertion pure jusqu'à N caractères et 30 mots (restitution d'une "
                         "omission attestée par collation) ; 0 = bornes ordinaires")
    args = ap.parse_args()

    corrections = defaultdict(list)
    n_corr = 0
    for line in open(args.corrections):
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        if c.get('chercher') and c.get('remplacer') is not None and c['chercher'] != c['remplacer']:
            corrections[c['doc']].append(c)
            n_corr += 1

    zin = zipfile.ZipFile(args.infile)
    zin_names = zin.namelist()
    applied, rejected = [], []

    # budget global
    total_words = 0
    for n in zin.namelist():
        if n.lower().endswith(('.xhtml', '.html', '.htm')):
            try:
                total_words += len(zin.read(n).decode('utf-8', 'replace').split())
            except Exception:
                pass
    budget = max(25, int(total_words * args.budget_pct / 100))
    if n_corr > budget:
        print(f'⚠ {n_corr} corrections demandées > budget {budget} — vérifier avant de forcer.')
        sys.exit(2)

    out = zipfile.ZipFile(args.outfile, 'w')
    out.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                 compress_type=zipfile.ZIP_STORED)

    for item in zin.infolist():
        if item.filename == 'mimetype':
            continue
        data = zin.read(item.filename)
        todo = corrections.get(item.filename, [])
        if todo and item.filename.lower().endswith(PATCHABLE):
            htm = data.decode('utf-8', errors='replace')
            parts = split_doc(htm)
            # texte par segment (désentitisé)
            seg_texts = [(i, html.unescape(frag)) for i, (is_tag, frag, skp) in enumerate(parts)
                         if not is_tag and not skp and frag]
            todo = fuse_overlapping(todo, seg_texts, rejected)
            for c in todo:
                ch, rp = c['chercher'], c['remplacer']
                # garde-fous taille (suppression pure d'un bloc contigu — doublon
                # de phrase — autorisée plus largement)
                wd = abs(len(rp.split()) - len(ch.split()))
                ed = edit_distance(ch, rp, cap=max(40, args.insertion_max))
                pure_deletion = norm_spaces(rp) in norm_spaces(ch) and len(rp) < len(ch)
                max_ed = 30 if pure_deletion else args.max_edit
                max_wd = 6 if pure_deletion else args.max_word_delta
                # Restituer un membre de phrase que la copie a sauté (« pour prévenir les
                # gendarmes ‸ et tâcher de ravoir les ânes ») : une insertion pure, rien
                # d'enlevé. Permise au-delà des bornes seulement sur demande
                # (--insertion-max), quand les corrections viennent d'une collation.
                pre = len(os.path.commonprefix([ch, rp]))
                suf = len(os.path.commonprefix([ch[pre:][::-1], rp[pre:][::-1]]))
                insertion = bool(args.insertion_max and len(rp) > len(ch) and pre + suf >= len(ch)
                                 and len(rp) - len(ch) <= args.insertion_max)
                if insertion:
                    max_ed, max_wd = len(rp) - len(ch), 30
                # Un motif court est ambigu… sauf quand il occupe À LUI SEUL un
                # nœud de texte : sa position est alors déterminée par le balisage,
                # pas par le voisinage. Fabrication Word→Calibre courante —
                # « <span lang="EN-US">Mlick </span> » ne peut pas être allongé.
                noeud_entier = any(norm_spaces(t).strip() == norm_spaces(ch).strip()
                                   for _, t in seg_texts)
                if len(ch) < 8 and not noeud_entier:
                    rejected.append((c, 'motif trop court (<8 chars), ambigu'))
                    continue
                if ed > max_ed or wd > max_wd or (abs(len(rp) - len(ch)) > 60 and not insertion):
                    rejected.append((c, f'au-delà des bornes (édition {ed}, mots Δ{wd})'))
                    continue
                # 1) correspondance exacte
                hits = [(i, t.find(ch)) for i, t in seg_texts if ch in t]
                total_hits = sum(t.count(ch) for _, t in seg_texts)
                if total_hits == 1:
                    i, pos = hits[0]
                    t_old = dict(seg_texts)[i]
                    t_new = t_old.replace(ch, rp, 1)
                elif total_hits > 1:
                    # Le motif se répète, mais un seul nœud de texte le vaut EXACTEMENT :
                    # sa position est alors donnée par le balisage. Fabrication
                    # Word→Calibre courante, qui isole une ponctuation dans son propre
                    # élément — « En tout cas <sub class="calibre28">;</sub> le bon
                    # vieux Dago », où le « ; » ne peut être atteint autrement.
                    entiers = [(i, t) for i, t in seg_texts
                               if norm_spaces(t).strip() == norm_spaces(ch).strip()]
                    if len(entiers) > 1 and (c.get('avant') or c.get('apres')):
                        # Le même nœud se répète (« <i>riant</i> » à chaque didascalie) : la
                        # correction dit ce qui l'entoure, texte des nœuds voisins compris.
                        flat = lambda x: re.sub(r'\s+', ' ', norm_spaces(x))
                        ordre = [j for j, _ in seg_texts]
                        textes = dict(seg_texts)
                        def voisinage(i):
                            k = ordre.index(i)
                            return (flat(''.join(textes[j] for j in ordre[max(0, k - 6):k])),
                                    flat(''.join(textes[j] for j in ordre[k + 1:k + 7])))
                        av, ap = flat(c.get('avant', '')).strip(), flat(c.get('apres', '')).strip()
                        entiers = [(i, t) for i, t in entiers
                                   if voisinage(i)[0].rstrip().endswith(av) and voisinage(i)[1].lstrip().startswith(ap)]
                    if len(entiers) != 1:
                        rejected.append((c, f'motif non unique ({total_hits} occurrences)'))
                        continue
                    i, t_old = entiers[0]
                    pos = t_old.find(ch)
                    if pos < 0:
                        pos = norm_spaces(t_old).find(norm_spaces(ch))
                    t_new = t_old[:pos] + rp + t_old[pos + len(ch):]
                else:
                    # 2) tolérance espaces insécables/fines (citations d'agents)
                    hit, n = tolerant_find(seg_texts, ch)
                    if hit is None:
                        why = ('motif introuvable dans les segments texte' if n == 0
                               else f'motif non unique avec tolérance espaces ({n})')
                        rejected.append((c, why))
                        continue
                    i, pos_n = hit
                    t_old = dict(seg_texts)[i]
                    # retrouve la position réelle : les normalisations ne changent
                    # pas les longueurs (espaces 1:1), l'index est donc le même
                    actual = t_old[pos_n:pos_n + len(ch)]
                    t_new = t_old[:pos_n] + splice_replacement(actual, ch, rp) + t_old[pos_n + len(ch):]
                    pos = pos_n
                seg_texts = [(j, t_new if j == i else t) for j, t in seg_texts]
                applied.append((item.filename, c,
                                t_old[max(0, pos - 55):pos],
                                t_old[pos:pos + len(ch)],
                                t_old[pos + len(ch):pos + len(ch) + 55]))
            # réinjection
            seg_map = dict(seg_texts)
            rebuilt = []
            for j, (is_tag, frag, skp) in enumerate(parts):
                if not is_tag and not skp and frag and j in seg_map:
                    rebuilt.append(html.escape(seg_map[j], quote=False))
                else:
                    rebuilt.append(frag)
            new_htm = ''.join(rebuilt)
            # garde-fou : balises inchangées
            if TAG_RE.findall(new_htm) != TAG_RE.findall(htm):
                print(f'⚠ {item.filename}: séquence de balises altérée — doc laissé intact')
                rejected.extend((c, 'doc entier rejeté (balises)') for c in todo)
                applied = [a for a in applied if a[0] != item.filename]
            else:
                data = new_htm.encode('utf-8')
        info = zipfile.ZipInfo(item.filename, date_time=item.date_time)
        info.compress_type = zipfile.ZIP_DEFLATED
        out.writestr(info, data)
    out.close()
    zin.close()

    # Aucune correction ne doit disparaître en silence : celle dont le `doc` ne
    # correspond à aucune entrée du zip, ou à une entrée non patchable, n'était
    # jusqu'ici ni appliquée ni rejetée — elle s'évaporait, et le compte final
    # paraissait bon.
    vus = {id(x) for _, c, *_ in applied for x in [c] + c.get('_parts', [])} \
        | {id(x) for c, _ in rejected for x in [c] + c.get('_parts', [])}
    noms = set(zin_names)
    for doc, lot in corrections.items():
        for c in lot:
            if id(c) in vus:
                continue
            if doc not in noms:
                rejected.append((c, f'document absent du livre : {doc}'))
            elif not doc.lower().endswith(PATCHABLE):
                rejected.append((c, f'document non patchable ({doc}) — attendu {"/".join(PATCHABLE)}'))
            else:
                rejected.append((c, 'non traitée (cause inconnue)'))

    print(f'{len(applied)} appliquées, {len(rejected)} rejetées (budget {budget})')
    if args.report:
        with open(args.report, 'w') as f:
            f.write(f'# Corrections OCR — {args.infile}\n\n'
                    f'{len(applied)} appliquées / {len(rejected)} rejetées '
                    f'(budget {budget} sur ~{total_words} mots)\n\n## Appliquées\n\n')
            for doc, c, before, actual, after in applied:
                f.write(f'- **{doc}** [{c.get("source", "?")}] {c.get("raison", "")}\n'
                        f'  - avant : `…{before}{actual}{after}…`\n'
                        f'  - `{c["chercher"]}` → `{c["remplacer"]}`\n')
            f.write('\n## Rejetées\n\n')
            for c, why in rejected:
                f.write(f'- **{c["doc"]}** `{c["chercher"][:60]}` → `{str(c["remplacer"])[:60]}` — {why}\n')
        print(f'rapport → {args.report}')
    if args.report_html:
        write_html_report(args.report_html, args.titre or args.infile,
                          applied, rejected, budget, total_words)
        print(f'rapport HTML → {args.report_html}')


def inline_diff_html(actual, ch, rp):
    """Rend le changement en HTML : supprimé rouge barré, ajouté vert gras.
    `actual` = texte réel trouvé (espaces fines comprises), ch/rp = chercher/remplacer."""
    import difflib
    esc = lambda s: html.escape(s, quote=False)
    chn, rpn = norm_spaces(ch), norm_spaces(rp)
    sm = difflib.SequenceMatcher(a=chn, b=rpn, autojunk=False)
    out = []
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == 'equal':
            out.append(esc(actual[a1:a2]))
        else:
            if a2 > a1:
                out.append(f'<del>{esc(actual[a1:a2])}</del>')
            if b2 > b1:
                out.append(f'<ins>{esc(rp[b1:b2])}</ins>')
    return ''.join(out)


def write_html_report(path, titre, applied, rejected, budget, total_words):
    esc = lambda s: html.escape(str(s), quote=False)
    rows = []
    for n, (doc, c, before, actual, after) in enumerate(applied, 1):
        chap = re.sub(r'^.*/|\.x?html?$', '', doc)
        diff = inline_diff_html(actual, c['chercher'], c['remplacer'])
        src = c.get('source', '')
        badge = ('ocr' if src.startswith('lecture') else 'règle')
        conf = 'moyenne' if 'moyenne' in src else ''
        rows.append(
            f'<tr><td class="n">{n}</td><td class="doc">{esc(chap)}</td>'
            f'<td class="ctx">…{esc(before)}<span class="hit">{diff}</span>{esc(after)}…</td>'
            f'<td class="raison">{esc(c.get("raison", ""))}'
            f'{" <span class=conf>confiance moyenne</span>" if conf else ""}</td>'
            f'<td class="src">{badge}</td></tr>')
    rej_rows = []
    for c, why in rejected:
        chap = re.sub(r'^.*/|\.x?html?$', '', c['doc'])
        rej_rows.append(
            f'<tr><td class="doc">{esc(chap)}</td>'
            f'<td class="ctx"><del>{esc(c["chercher"][:80])}</del> → <ins>{esc(str(c["remplacer"])[:80])}</ins></td>'
            f'<td class="raison">{esc(why)}</td></tr>')
    doc_html = f'''<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Corrections — {esc(titre)}</title>
<style>
 body {{ font-family: Georgia, serif; max-width: 1100px; margin: 2em auto; padding: 0 1em; color:#222; }}
 h1 {{ font-size: 1.4em; }} .meta {{ color:#666; }}
 table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
 th {{ background:#f0f0f0; text-align:left; padding:6px 8px; font-size:.85em; position:sticky; top:0; }}
 td {{ border-top:1px solid #e3e3e3; padding:6px 8px; vertical-align:top; font-size:.92em; }}
 td.n {{ color:#999; font-size:.8em; }} td.doc {{ white-space:nowrap; color:#888; font-size:.78em; }}
 td.ctx {{ line-height:1.5; }} td.raison {{ color:#555; font-size:.82em; max-width:260px; }}
 td.src {{ font-size:.75em; color:#999; }}
 del {{ color:#b30000; background:#ffe5e5; text-decoration: line-through; }}
 ins {{ color:#006400; background:#e2f5e2; text-decoration:none; font-weight:bold; }}
 .hit {{ outline: 1px dotted #bbb; }}
 .conf {{ color:#b36b00; font-size:.9em; border:1px solid #e0c080; border-radius:3px; padding:0 4px; }}
 tr:hover td {{ background:#fafaf2; }}
</style></head><body>
<h1>Corrections appliquées — {esc(titre)}</h1>
<p class="meta">{len(applied)} appliquées · {len(rejected)} rejetées · budget {budget} sur ≈{total_words} mots.
<del>supprimé</del> <ins>ajouté</ins></p>
<table>
<tr><th>#</th><th>doc</th><th>contexte</th><th>raison</th><th>origine</th></tr>
{''.join(rows)}
</table>
<h1>Rejetées ({len(rejected)})</h1>
<p class="meta">Doublons auto-neutralisés (déjà corrigés par une règle antérieure) ou hors bornes — aucune n'a modifié le livre.</p>
<table>
<tr><th>doc</th><th>proposition</th><th>motif du rejet</th></tr>
{''.join(rej_rows)}
</table>
</body></html>'''
    with open(path, 'w') as f:
        f.write(doc_html)


if __name__ == '__main__':
    main()
