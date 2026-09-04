#!/usr/bin/env python3
"""Complète une fonte : ajoute U+202F (NARROW NO-BREAK SPACE) là où elle manque.

Beaucoup d'excellentes fontes de lecture — Literata, EB Garamond, Crimson Pro —
n'ont pas de glyphe pour la fine insécable. Les moteurs de rendu qui ne savent
pas la synthétiser (celui des liseuses Kobo, notamment) l'affichent alors en
largeur nulle : la ponctuation double se retrouve collée au mot. On ajoute donc
un glyphe vide, de la chasse d'une fine (1/6 cadratin par défaut), et on le
raccorde à toutes les sous-tables cmap Unicode.
"""
import argparse, sys
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._g_l_y_f import Glyph

NNBSP = 0x202F
NAME = "uni202F"


def has_cp(font, cp):
    return any(cp in t.cmap for t in font["cmap"].tables)


def add_nnbsp(font, ratio):
    upm = font["head"].unitsPerEm
    width = round(ratio * upm)
    glyf = font.get("glyf")
    if glyf is None:
        raise SystemExit("fonte CFF non gérée par ce script (glyf attendu)")
    if NAME not in font.getGlyphOrder():
        order = font.getGlyphOrder() + [NAME]
        font.setGlyphOrder(order)
        glyf.glyphOrder = order
        g = Glyph()                      # contours vides = espace
        g.numberOfContours = 0
        glyf.glyphs[NAME] = g
    font["hmtx"][NAME] = (width, 0)
    n = 0
    for t in font["cmap"].tables:
        if t.isUnicode():
            t.cmap[NNBSP] = NAME
            n += 1
    if "maxp" in font:
        font["maxp"].numGlyphs = len(font.getGlyphOrder())
    return width, upm, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--ratio", type=float, default=1 / 6,
                    help="chasse de la fine, en cadratins (défaut 1/6)")
    a = ap.parse_args()
    f = TTFont(a.src)
    if has_cp(f, NNBSP):
        print(f"{a.src} : U+202F déjà présent, rien à faire")
        f.save(a.dst)
        return
    w, upm, n = add_nnbsp(f, a.ratio)
    f.save(a.dst)
    chk = TTFont(a.dst, lazy=True)
    cps = {}
    for t in chk["cmap"].tables:
        cps.update(t.cmap)
    assert NNBSP in cps, "U+202F absent après écriture"
    assert chk["hmtx"][cps[NNBSP]][0] == w, "chasse incorrecte après écriture"
    print(f"{a.dst} : U+202F ajouté, chasse {w}/{upm} = {w/upm:.3f} em, "
          f"{n} sous-table(s) cmap — relu et vérifié")


main()
