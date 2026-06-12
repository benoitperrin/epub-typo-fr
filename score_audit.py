#!/usr/bin/env python3
"""
score_audit.py — Classe les livres audités par epub_typo_audit.py.

Classes :
  A  rédhibitoire   : mojibake, encodage cassé, OCR sale → re-télécharger / refaire
  B  majeur         : apostrophes droites, insécables absentes, dialogues au trait
                      d'union, ligatures œ perdues, guillemets anglais → fixable script
  C  mineur         : ... au lieu de …, capitales non accentuées → fix optionnel
  OK propre

Usage: python3 score_audit.py audit-full.jsonl [--csv out.csv] [--md out.md]
"""
import json, sys, argparse

def per10k(rec, key):
    c = rec.get('chars') or 0
    if c == 0: return 0.0
    return rec.get(key, 0) * 10000.0 / c

def classify(rec):
    """Retourne (classe, [défauts], score_gravité)."""
    defects = []
    score = 0.0
    chars = rec.get('chars') or 0
    lang = (rec.get('lang_opf') or rec.get('lang_db') or '').lower()
    is_fr = lang.startswith('fr') or lang in ('', 'und')

    if rec.get('error'):
        return 'ERR', [rec['error']], 999

    if chars < 2000:
        if rec.get('fixed_layout') or rec.get('n_images', 0) > rec.get('n_docs', 0) * 3:
            return 'IMG', ['livre image / fixed-layout — hors périmètre typo texte'], 0
        return 'ERR', [f'texte quasi vide ({chars} chars) — extraction ou epub suspect'], 900

    # ---------- Classe A ----------
    # Élisions absentes : un roman FR a ≥ ~30 apostrophes / 10k chars (Percy 136,
    # HP 114, Fantômette 100). En dessous de 12, le texte est déformé (apostrophes
    # supprimées par une mauvaise conversion — cas « larbre/quil » du Vent dans
    # les saules #1143, raté par tous les ratios).
    if is_fr and chars > 30000:
        apos10k = (rec.get('apos_straight', 0) + rec.get('apos_curly', 0)) * 10000.0 / chars
        if apos10k < 12:
            defects.append(f"élisions quasi absentes ({apos10k:.1f} apostrophes/10k chars : texte déformé ?)")
            score += 120
    moji = per10k(rec, 'mojibake')
    if rec.get('mojibake', 0) >= 5 and moji > 0.05:
        defects.append(f"mojibake ×{rec['mojibake']} (encodage double-décodé)")
        score += 100 + moji * 10
    if rec.get('encoding_issues', 0) > 0:
        defects.append(f"fichiers non-UTF8 ×{rec['encoding_issues']}")
        score += 80
    hyres = per10k(rec, 'hyphen_residue')
    if rec.get('hyphen_residue', 0) >= 20 and hyres > 0.5:
        defects.append(f"césures résiduelles OCR ×{rec['hyphen_residue']} ({hyres:.1f}/10k)")
        score += 60 + hyres * 5

    # ---------- Classe B (FR uniquement) ----------
    if is_fr:
        a_s, a_c = rec.get('apos_straight', 0), rec.get('apos_curly', 0)
        if a_s + a_c > 50 and a_s / (a_s + a_c) > 0.25:
            defects.append(f"apostrophes droites {a_s}/{a_s+a_c} ({100*a_s/(a_s+a_c):.0f} %)")
            score += 40 * a_s / (a_s + a_c)

        p_n, p_s, p_0 = rec.get('punct_nbsp', 0), rec.get('punct_space', 0), rec.get('punct_none', 0)
        tot_p = p_n + p_s + p_0
        if tot_p > 30:
            if (p_s + p_0) / tot_p > 0.30:
                detail = []
                if p_s: detail.append(f'{p_s} sécables')
                if p_0: detail.append(f'{p_0} sans espace')
                defects.append(f"insécables ponctuation manquantes : {' + '.join(detail)} / {tot_p}")
                score += 35 * (p_s + p_0) / tot_p
                if p_0 / tot_p > 0.5:
                    score += 15  # collé façon anglo = symptôme OCR/source EN

        g_n, g_s, g_0 = rec.get('guil_in_nbsp', 0), rec.get('guil_in_space', 0), rec.get('guil_in_none', 0)
        tot_g = g_n + g_s + g_0
        if tot_g > 20 and (g_s + g_0) / tot_g > 0.30:
            defects.append(f"guillemets sans insécable intérieure : {g_s+g_0}/{tot_g}")
            score += 10

        d_em, d_en, d_hy = rec.get('dlg_emdash', 0), rec.get('dlg_endash', 0), rec.get('dlg_hyphen', 0)
        tot_d = d_em + d_en + d_hy
        if tot_d > 20 and d_hy / tot_d > 0.30:
            defects.append(f"dialogues au trait d'union ×{d_hy}/{tot_d}")
            score += 30 * d_hy / tot_d

        lig_b, lig_g = rec.get('lig_bad', 0), rec.get('lig_good', 0)
        if lig_b > 3 and lig_b > lig_g:
            defects.append(f"ligatures œ perdues ×{lig_b} (vs {lig_g} correctes)")
            score += 15

        dq = rec.get('dq_straight', 0) + rec.get('dq_curly', 0)
        guil = rec.get('guil_open', 0) + rec.get('guil_close', 0)
        if dq > 50 and dq > guil:
            defects.append(f"guillemets anglais dominants ×{dq} (vs {guil} français)")
            score += 20

    # ---------- Classe C ----------
    if is_fr:
        e_d, e_c = rec.get('ellipsis_dots', 0), rec.get('ellipsis_char', 0)
        if e_d > 20 and e_d > e_c:
            defects.append(f"« ... » au lieu de « … » ×{e_d}")
            score += 3
        c_b, c_g = rec.get('caps_bad', 0), rec.get('caps_good', 0)
        if c_b > 10 and c_b > c_g:
            defects.append(f"capitales non accentuées ×{c_b} (vs {c_g})")
            score += 3
        if rec.get('softhyphen', 0) > 200:
            defects.append(f"soft hyphens ×{rec['softhyphen']}")
            score += 2

    if not is_fr:
        defects.insert(0, f"langue {lang} — critères FR non appliqués")

    if score >= 60: cls = 'A'
    elif score >= 18: cls = 'B'
    elif score >= 2: cls = 'C'
    else: cls = 'OK'
    return cls, defects, round(score, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('jsonl')
    ap.add_argument('--csv'), ap.add_argument('--md')
    args = ap.parse_args()

    rows = []
    with open(args.jsonl) as f:
        for line in f:
            rec = json.loads(line)
            cls, defects, score = classify(rec)
            rows.append((cls, score, rec, defects))

    order = {'A': 0, 'ERR': 1, 'B': 2, 'C': 3, 'IMG': 4, 'OK': 5}
    rows.sort(key=lambda r: (order.get(r[0], 9), -r[1]))

    from collections import Counter
    counts = Counter(r[0] for r in rows)
    print('Répartition :', dict(counts))
    print()
    for cls, score, rec, defects in rows:
        if cls in ('OK', 'IMG'): continue
        readers = rec.get('readers') or '—'
        print(f"[{cls}] {score:6.1f}  #{rec['id']:<5} {rec['title'][:55]:<55} ({readers})")
        for d in defects:
            print(f"          - {d}")

    if args.csv:
        import csv
        with open(args.csv, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['classe','score','id','titre','auteurs','lecteurs','defauts'])
            for cls, score, rec, defects in rows:
                w.writerow([cls, score, rec['id'], rec['title'],
                            rec.get('authors',''), rec.get('readers',''), ' | '.join(defects)])
        print(f"\nCSV → {args.csv}")

if __name__ == '__main__':
    main()
