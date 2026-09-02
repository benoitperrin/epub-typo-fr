#!/usr/bin/env python3
"""Fabrique un jeu de 4 fontes statiques pour liseuse Kobo, fine insécable comprise.

Literata est une variable font dessinée pour la lecture sur encre électronique,
mais elle n'a pas U+202F. On fige quatre instances (opsz=12, wght=400/700, romain
et italique) puis on leur ajoute la fine avec patch_fine.py.
"""
import subprocess, sys, os
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

JOBS = [("Literata.ttf", 400, "Regular"), ("Literata.ttf", 700, "Bold"),
        ("Literata-Italic.ttf", 400, "Italic"), ("Literata-Italic.ttf", 700, "BoldItalic")]
OUT = "kobo-fonts"
os.makedirs(OUT, exist_ok=True)
for src, wght, style in JOBS:
    f = TTFont(src)
    inst = instancer.instantiateVariableFont(f, {"opsz": 12, "wght": wght}, inplace=False, updateFontNames=True)
    tmp = f"/tmp/_{style}.ttf"
    inst.save(tmp)
    dst = f"{OUT}/Literata-{style}.ttf"
    subprocess.run([sys.executable, "patch_fine.py", tmp, dst], check=True)
