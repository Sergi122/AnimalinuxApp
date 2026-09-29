#!/usr/bin/env python3
"""Mide el coste de CARGA del overlay (igual que MascotWindow._load_poses, sin ventana):
tiempo, texturas y RAM descomprimida (RGBA) por mascota. Solo lectura."""
import json, os, time, glob, sys
from pathlib import Path
from PIL import Image
cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
lib = json.load(open(f"{cfg}/animalinux/library.json")); anims = lib.get("animations", lib)
tot = 0
print(f"{'nombre':16}{'texturas':>9}{'RAM MB':>9}{'estirados':>10}{'carga s':>9}{'PNG KB':>8}")
for aid, a in anims.items():
    base = Path(f"{data}/animalinux/animations/{aid}")
    t0 = time.time(); ntex = ram = stretched = 0; disk = 0
    folders = [base] + sorted(p for p in base.iterdir() if p.is_dir())
    bsize = None
    for f in folders:
        fr = sorted(f.glob("frame_*.png")); fl = sorted(f.glob("flip_*.png"))
        if not fr: continue
        if bsize is None: bsize = Image.open(fr[0]).size
        for p in fr + (fl or fr):          # el overlay carga normal + flip (si no hay flip, reusa normal)
            im = Image.open(p); im.load(); disk += os.path.getsize(p)
            sz = im.size
            if sz != bsize: stretched += 1; sz = bsize
            if p in fr or fl: ntex += 1 if (p in fr or fl) else 0
            ram += sz[0] * sz[1] * 4
    tot += ram
    print(f"{a.get('name','?')[:15]:16}{ntex:>9}{ram/2**20:>9.1f}{stretched:>10}{time.time()-t0:>9.2f}{disk//1024:>8}")
print(f"TOTAL RAM texturas si todas están activas: {tot/2**20:.0f} MB")
