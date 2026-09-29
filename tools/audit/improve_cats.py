"""Mejora las poses de las mascotas de ejemplo (Ejemplo Vida azul y Gato Minecraft).

Rehace los cuadros que estaban casi estáticos: parpadeo, respiración, ceño
fruncido, pasos alternos, ojos cerrados al dormir. Uso: improve_cats.py
(las copias originales quedan en ~/animalinux-audit/backup_cats/)."""
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from animalinux.core import image_processor  # noqa: E402

LIB = Path.home() / ".local/share/animalinux/animations"
BAK = Path.home() / "animalinux-audit/backup_cats"   # originales: la fuente, para poder repetir
EJ = LIB / "34804bcae130"
MC = LIB / "848c5a0b4a37"
SS = 4  # supersampling para dibujar trazos suaves


def save_pose(folder, frames):
    folder.mkdir(exist_ok=True)
    for f in folder.glob("frame_*.png"):
        f.unlink()
    for f in folder.glob("flip_*.png"):
        f.unlink()
    for i, im in enumerate(frames):
        im.save(folder / f"frame_{i:04d}.png")
    image_processor.ensure_flipped(folder)


# ───────────────────────── Ejemplo Vida (azul, vectorial) ──────────────────
BODY = (116, 184, 232, 255)
LINE = (40, 70, 120, 255)
EYES = [(70, 146), (110, 146)]


def ss_draw(im, fn):
    big = im.resize((im.width * SS, im.height * SS), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    fn(d, SS)
    return big.resize(im.size, Image.LANCZOS)


def ej_eyes(im, mode):
    """mode: 'closed' (arco hacia abajo) | 'angry' (párpado inclinado + ceja)."""
    def draw(d, k):
        if mode == "closed":
            for cx, cy in EYES:
                d.ellipse([(cx - 11) * k, (cy - 12) * k, (cx + 11) * k, (cy + 12) * k], fill=BODY)
                d.arc([(cx - 8) * k, (cy - 6) * k, (cx + 8) * k, (cy + 6) * k], 20, 160,
                      fill=LINE, width=int(2.5 * k))
        else:
            d.polygon([(56 * k, 124 * k), (84 * k, 124 * k), (84 * k, 143 * k), (56 * k, 134 * k)], fill=BODY)
            d.polygon([(96 * k, 124 * k), (124 * k, 124 * k), (124 * k, 134 * k), (96 * k, 143 * k)], fill=BODY)
            d.line([(57 * k, 133 * k), (83 * k, 142 * k)], fill=LINE, width=int(4 * k))
            d.line([(123 * k, 133 * k), (97 * k, 142 * k)], fill=LINE, width=int(4 * k))
    return ss_draw(im, draw)


def transform(im, sy=1.0, sx=1.0, dx=0, dy=0, rot=0.0, anchor=(90, 217)):
    """Escala/rota/desplaza anclando los pies."""
    ax, ay = anchor
    out = im.transform(im.size, Image.AFFINE,
                       (1 / sx, 0, ax - ax / sx - dx / sx, 0, 1 / sy, ay - ay / sy - dy / sy),
                       resample=Image.BICUBIC)
    if rot:
        out = out.rotate(rot, resample=Image.BICUBIC, center=anchor)
    return out


def tint_red(im, amount):
    a = np.asarray(im).astype(float)
    a[..., 0] = np.minimum(255, a[..., 0] + 80 * amount)
    a[..., 1] *= 1 - 0.28 * amount
    a[..., 2] *= 1 - 0.28 * amount
    return Image.fromarray(a.astype("uint8"), "RGBA")


def ej_base():
    return Image.open(BAK / EJ.name / "idle" / "frame_0000.png").convert("RGBA")


def ej_idle(base):
    out = []
    for i in range(12):
        s = math.sin(2 * math.pi * i / 12)
        f = transform(base, sy=1 + 0.014 * s, sx=1 - 0.008 * s)
        if i in (8, 9):
            f = ej_eyes(f, "closed")
        out.append(f)
    return out


def ej_angry(base):
    out = []
    for i in range(10):
        s = math.sin(2 * math.pi * i / 5)
        f = ej_eyes(base, "angry")
        f = tint_red(f, 0.25 + 0.3 * abs(math.sin(math.pi * i / 5)))
        f = transform(f, sy=1 + 0.03 * abs(s), sx=1 + 0.03 * s, dx=3 * s, rot=2.5 * s)
        out.append(f)
    return out


def ej_sleep(base):
    out = []
    for i in range(12):
        s = math.sin(2 * math.pi * i / 12)
        f = ej_eyes(base, "closed")
        out.append(transform(f, sy=1 + 0.03 * s, sx=1 - 0.015 * s, rot=4))
    return out


def ej_walk(base):
    feet = {"l": (54, 195, 86, 220), "r": (94, 195, 128, 220)}
    out = []
    for i in range(8):
        ph = i / 8
        lift_l = max(0.0, math.sin(2 * math.pi * ph)) * 9
        lift_r = max(0.0, -math.sin(2 * math.pi * ph)) * 9
        f = base.copy()
        crops = {k: base.crop(b) for k, b in feet.items()}
        for k, b in feet.items():
            f.paste(Image.new("RGBA", (b[2] - b[0], b[3] - b[1]), (0, 0, 0, 0)), b[:2])
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        for k, lift in (("l", lift_l), ("r", lift_r)):
            b = feet[k]
            layer.alpha_composite(crops[k], (b[0], int(b[1] - lift)))
        f.alpha_composite(layer)
        bob = abs(math.sin(2 * math.pi * ph)) * 5
        f = transform(f, dy=-bob, rot=3 * math.sin(2 * math.pi * ph))
        out.append(f)
    return out


# ───────────────────────── Gato Minecraft (pixel art 48x48) ────────────────
ORANGE = (210, 122, 18, 255)
DARK = (20, 10, 0, 255)
LIME = (148, 210, 0)
PUPIL = (8, 8, 8)


def mc_eye_boxes(a):
    m = (a[..., 3] > 0) & ((a[..., :3] == LIME).all(2) | (a[..., :3] == PUPIL).all(2))
    ys, xs = np.where(m)
    if not len(xs):
        return []   # ya trae los ojos cerrados
    mid = (xs.min() + xs.max()) // 2
    boxes = []
    for sel in (xs <= mid, xs > mid):
        boxes.append((xs[sel].min(), ys[sel].min(), xs[sel].max(), ys[sel].max()))
    return boxes


def mc_edit(im, mode):
    a = np.asarray(im).copy()
    for x0, y0, x1, y1 in mc_eye_boxes(np.asarray(im)):
        if mode in ("closed", "happy"):
            a[y0:y1 + 1, x0:x1 + 1] = ORANGE
        if mode == "closed":
            a[y1 - 1, x0:x1 + 1] = DARK
        elif mode == "happy":
            w = x1 - x0
            a[y0 + 2, x0] = a[y0 + 2, x1] = DARK
            a[y0 + 1, x0 + 1] = a[y0 + 1, x1 - 1] = DARK
            a[y0, x0 + 2:x1 - 1] = DARK
            a[y0 + 3, x0 + w // 2] = a[y0 + 3, x0 + w // 2 + 1] = (255, 145, 145, 255)  # rubor
        elif mode == "angry":
            inner_left = x0 < 24
            for x in range(x0, x1 + 1):
                t = (x - x0) / max(1, x1 - x0)
                depth = t if inner_left else 1 - t         # el borde interno queda más bajo
                yy = y0 - 2 + int(round(depth * 2))
                a[yy, x] = DARK
                a[yy + 1, x] = DARK if depth > 0.4 else a[yy + 1, x]
    return Image.fromarray(a, "RGBA")


def mc_tint(im, amount):
    a = np.asarray(im).astype(int)
    m = (a[..., :3] == ORANGE[:3]).all(2) & (a[..., 3] > 0)
    a[m, 0] = min(255, int(210 + 30 * amount))
    a[m, 1] = int(122 - 60 * amount)
    a[m, 2] = int(18 + 10 * amount)
    return Image.fromarray(a.astype("uint8"), "RGBA")


def mc_pose(name, fn):
    frames = [Image.open(f).convert("RGBA") for f in sorted((BAK / MC.name / name).glob("frame_*.png"))]
    save_pose(MC / name, [fn(i, f) for i, f in enumerate(frames)])


def main():
    base = ej_base()
    save_pose(EJ / "idle", ej_idle(base))
    save_pose(EJ / "angry", ej_angry(base))
    save_pose(EJ / "sleep", ej_sleep(base))
    save_pose(EJ / "walk", ej_walk(base))
    mc_pose("idle", lambda i, f: mc_edit(f, "closed") if i in (2, 3) else f)
    mc_pose("greet", lambda i, f: mc_edit(f, "happy") if 1 <= i <= 4 else f)
    mc_pose("angry", lambda i, f: mc_tint(mc_edit(f, "angry"), 0.2 + 0.5 * (i % 2)))
    print("listo")


if __name__ == "__main__":
    main()
