"""Genera animalinux.ico a partir del logo (se ejecuta en build.sh)."""
from pathlib import Path

from PIL import Image

root = Path(__file__).resolve().parents[2]
src = root / "animalinux" / "ui" / "assets" / "logo.png"
Image.open(src).convert("RGBA").save(
    Path(__file__).with_name("animalinux.ico"),
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
