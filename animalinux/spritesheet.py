"""
Importador de SPRITESHEETS (tiras de sprites tipo vscode-pets / Shimeji).

Una hoja de sprites es UNA imagen con varios fotogramas dibujados (p.ej. el
caminar cuadro por cuadro). Aquí la cortamos en frames individuales. Así tu app
es compatible con los miles de sprites pixel que ya existen gratis en internet.

Dos formas de cortar:
  - REJILLA: das columnas (y filas) y se corta en celdas iguales.
  - AUTO:    detecta los fotogramas separados por columnas transparentes
             (típico en tiras con huecos entre cuadros).
"""
from pathlib import Path

from PIL import Image

from . import importer


def _open(path):
    img = Image.open(path)
    img.verify()
    return Image.open(path).convert("RGBA")


def slice_grid(path, cols, rows=1):
    im = _open(path)
    w, h = im.size
    cw, ch = w // max(1, cols), h // max(1, rows)
    frames = []
    for r in range(rows):
        for c in range(cols):
            frames.append(im.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)))
    return frames


def auto_slice(path):
    """Corta por columnas totalmente transparentes (huecos entre frames)."""
    im = _open(path)
    w, h = im.size
    alpha = im.getchannel("A")
    step = max(1, h // 40)
    opaque = [any(alpha.getpixel((x, y)) > 10 for y in range(0, h, step))
              for x in range(w)]
    frames, x = [], 0
    while x < w:
        if opaque[x]:
            start = x
            while x < w and opaque[x]:
                x += 1
            if x - start > 2:                     # ignorar ruido de 1-2 px
                frames.append(im.crop((start, 0, x, h)))
        else:
            x += 1
    return frames or [im]


def import_spritesheet(library, path, cols=0, rows=1, fps=8, name=None):
    """Corta la hoja y la registra como una animación nueva."""
    if cols and cols > 0:
        frames = slice_grid(path, cols, rows)
    else:
        frames = auto_slice(path)

    frames = [f for f in frames if f.getbbox()]   # descartar celdas vacías
    if not frames:
        raise RuntimeError("No se detectaron fotogramas en la hoja.")

    frames = importer._autocrop(frames)            # recorte uniforme
    w, h = frames[0].size

    aid = library.new_id()
    fd = library.frames_dir(aid)
    fd.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(frames):
        if f.size != (w, h):
            canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            canvas.alpha_composite(f, ((w - f.size[0]) // 2, h - f.size[1]))
            f = canvas
        f.save(fd / f"frame_{i:04d}.png")
    importer.ensure_flipped(fd)

    library.add(aid, name or Path(path).stem, len(frames), w, h)
    library.update(aid, fps=fps)
    return aid
