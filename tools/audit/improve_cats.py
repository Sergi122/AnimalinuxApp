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
PX = LIB / "f33a629551c6"
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


# ───────────────────── poses que faltaban: sleep / kiss / fall / grab ───────
HEART = ["..XX.XX..", ".XXXXXXX.", "XXXXXXXXX", ".XXXXXXX.", "..XXXXX..", "...XXX...", "....X...."]
HEART_S = [".X.X.", "XXXXX", ".XXX.", "..X.."]
ZZ_S = ["XXX", ".X.", "XXX"]
ZZ_L = ["XXXXX", "...X.", "..X..", ".X...", "XXXXX"]
PINK = (255, 100, 140, 255)
PINK_HI = (255, 190, 210, 255)
ZCOL = (110, 150, 255, 255)


def stamp(im, pattern, x, y, color, hi=None):
    a = np.asarray(im).copy()
    for j, row in enumerate(pattern):
        for i, c in enumerate(row):
            if c == "X" and 0 <= y + j < a.shape[0] and 0 <= x + i < a.shape[1]:
                a[y + j, x + i] = color
    if hi is not None:                       # brillo de 1 px arriba a la izquierda
        a[y + 1, x + 1] = hi
    return Image.fromarray(a, "RGBA")


def free_spot(folder_src, w, h):
    """Esquina libre (en TODOS los cuadros de todas las poses) para un adorno wxh."""
    occ = None
    for f in Path(folder_src).glob("*/frame_*.png"):
        a = np.asarray(Image.open(f).convert("RGBA"))[..., 3] > 0
        occ = a if occ is None else occ | a
    H, W = occ.shape
    best = None
    for y in range(0, H - h):
        for x in range(W - w, -1, -1):        # prefiere arriba a la derecha
            if not occ[y:y + h, x:x + w].any():
                score = y * 2 + (W - w - x)
                if best is None or score < best[0]:
                    best = (score, x, y)
    return best[1:] if best else None


def breathe(im, dh):
    """Respiración con píxeles enteros: comprime dh filas (vecino más cercano)."""
    w, h = im.size
    if not dh:
        return im
    sq = im.resize((w, h - dh), Image.NEAREST)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.alpha_composite(sq, (0, dh))
    return out


BREATH = [0, 0, 1, 1, 2, 1, 1, 0]


def pixel_sleep(closed_base, spot):
    out = []
    for i, dh in enumerate(BREATH):
        f = breathe(closed_base, dh)
        if spot:
            x, y = spot
            f = stamp(f, ZZ_L if i >= 4 else ZZ_S, x, y + (i % 4) // 2, ZCOL)
        out.append(f)
    return out


def pixel_kiss(happy_base, spot):
    out = []
    for i in range(8):
        f = happy_base
        if spot and i >= 1:
            x, y = spot
            f = stamp(f, HEART if i in (3, 4, 5) else HEART_S, x, y - (1 if i >= 5 else 0), PINK, PINK_HI)
        out.append(f)
    return out


def pixel_fall(jump_frames):
    mid = jump_frames[1:5] if len(jump_frames) >= 5 else jump_frames
    out = []
    for i, f in enumerate(mid * 2):
        sh = (1, -1, 1, -1)[i % 4]           # temblor de pánico de 1 px
        g = Image.new("RGBA", f.size, (0, 0, 0, 0))
        g.alpha_composite(f, (sh, 0))
        out.append(g)
    return out


def ej_heart(im, cx, cy, r):
    def draw(d, k):
        d.ellipse([(cx - r) * k, (cy - r) * k, (cx) * k, (cy + r * 0.2) * k], fill=PINK)
        d.ellipse([(cx) * k, (cy - r) * k, (cx + r) * k, (cy + r * 0.2) * k], fill=PINK)
        d.polygon([((cx - r) * k, (cy - r * 0.15) * k), ((cx + r) * k, (cy - r * 0.15) * k),
                   (cx * k, (cy + r * 1.35) * k)], fill=PINK)
    return ss_draw(im, draw)


def ej_kiss(base):
    out = []
    for i in range(10):
        f = ej_eyes(base, "closed")
        f = transform(f, sy=1 + 0.02 * math.sin(math.pi * i / 5), rot=3 * math.sin(math.pi * i / 5))
        if i >= 2:
            t = (i - 2) / 7
            f = ej_heart(f, 135 + 6 * math.sin(t * 6), 100 - 55 * t, 6 + 8 * min(1, t * 2))
        out.append(f)
    return out


def ej_fall(base):
    def wide(d, k):
        for cx, cy in EYES:
            d.ellipse([(cx - 12) * k, (cy - 13) * k, (cx + 12) * k, (cy + 13) * k], fill=(255, 255, 255, 255), outline=LINE, width=int(2 * k))
            d.ellipse([(cx - 3) * k, (cy - 3) * k, (cx + 3) * k, (cy + 3) * k], fill=(10, 10, 20, 255))
        d.ellipse([80 * k, 166 * k, 100 * k, 184 * k], fill=(60, 30, 50, 255))       # boca abierta
    out = []
    for i in range(6):
        s = math.sin(2 * math.pi * i / 6)
        f = ss_draw(base, wide)
        out.append(transform(f, sy=1.09, sx=0.94, rot=5 * s, dx=2 * s))
    return out


def ej_grab(base):
    feet = {"l": (54, 195, 86, 220), "r": (94, 195, 128, 220)}
    out = []
    for i in range(8):
        s = math.sin(2 * math.pi * i / 8)
        f = base.copy()
        crops = {k: base.crop(b) for k, b in feet.items()}
        for b in feet.values():
            f.paste(Image.new("RGBA", (b[2] - b[0], b[3] - b[1]), (0, 0, 0, 0)), b[:2])
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        for k, sign in (("l", 1), ("r", -1)):
            b = feet[k]
            layer.alpha_composite(crops[k], (b[0] + int(4 * sign * s), int(b[1] + 5 + 3 * abs(s))))
        f.alpha_composite(layer)
        f = ss_draw(f, lambda d, k: d.ellipse([131 * k, 118 * k, 137 * k, 128 * k], fill=(190, 230, 255, 255)))  # gota de sudor
        out.append(transform(f, sy=1.06, sx=0.96, rot=6 * s, anchor=(90, 108)))
    return out


def extra_poses(base_ej):
    save_pose(EJ / "kiss", ej_kiss(base_ej))
    save_pose(EJ / "fall", ej_fall(base_ej))
    save_pose(EJ / "grab", ej_grab(base_ej))
    for root, closed_idx, name in ((MC, None, "mc"), (PX, 2, "px")):
        src = BAK / root.name
        idle = sorted((src / "idle").glob("frame_*.png"))
        greet = sorted((src / "greet").glob("frame_*.png"))
        jump = [Image.open(f).convert("RGBA") for f in sorted((src / "jump").glob("frame_*.png"))]
        if name == "mc":
            closed = mc_edit(Image.open(idle[0]).convert("RGBA"), "closed")
            happy = mc_edit(Image.open(greet[1]).convert("RGBA"), "happy")
        else:
            closed = Image.open(idle[closed_idx]).convert("RGBA")
            happy = Image.open(greet[1]).convert("RGBA")
        save_pose(root / "sleep", pixel_sleep(closed, free_spot(src, 5, 6)))
        save_pose(root / "kiss", pixel_kiss(happy, free_spot(src, 9, 8)))
        save_pose(root / "fall", pixel_fall(jump))


def main():
    base = ej_base()
    save_pose(EJ / "idle", ej_idle(base))
    save_pose(EJ / "angry", ej_angry(base))
    save_pose(EJ / "sleep", ej_sleep(base))
    save_pose(EJ / "walk", ej_walk(base))
    mc_pose("idle", lambda i, f: mc_edit(f, "closed") if i in (2, 3) else f)
    mc_pose("greet", lambda i, f: mc_edit(f, "happy") if 1 <= i <= 4 else f)
    mc_pose("angry", lambda i, f: mc_tint(mc_edit(f, "angry"), 0.2 + 0.5 * (i % 2)))
    extra_poses(base)
    print("listo")


if __name__ == "__main__":
    main()
