#!/usr/bin/env python3
"""Genera hojas de contacto (una por animación) en ./sheets/ para inspección visual."""
import json, os, glob
from PIL import Image, ImageDraw
cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
lib = json.load(open(f"{cfg}/animalinux/library.json")); anims = lib.get("animations", lib)
os.makedirs("sheets", exist_ok=True)
T = 96; N = 8
for aid, a in anims.items():
    d = f"{data}/animalinux/animations/{aid}"
    rows = []
    top = sorted(glob.glob(f"{d}/*.png"))
    if top: rows.append(("base", top))
    for pd in sorted(p for p in glob.glob(f"{d}/*") if os.path.isdir(p)):
        rows.append((os.path.basename(pd), sorted(glob.glob(f"{pd}/*.png"))))
    im = Image.new("RGB", (70 + N * T, max(1, len(rows)) * T), (38, 42, 54)); dr = ImageDraw.Draw(im)
    for r, (nm, fs) in enumerate(rows):
        dr.text((4, r * T + 4), f"{nm}\n{len(fs)}f", fill=(230, 230, 230))
        pick = [fs[int(i * (len(fs) - 1) / max(1, N - 1))] for i in range(min(N, len(fs)))] if fs else []
        for c, p in enumerate(pick):
            f = Image.open(p).convert("RGBA"); f.thumbnail((T - 4, T - 4))
            im.paste(f, (70 + c * T + 2, r * T + 2), f)
    im.save(f"sheets/{a.get('name','x')}_{aid}.png")
