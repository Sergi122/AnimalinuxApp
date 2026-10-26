"""
Mascotas redondas dibujadas en pixel art (por ahora, el PANDA de ejemplo).

Cada cuadro se dibuja con figuras geométricas a 4× (elipses, arcos, puntos),
se baja a 56×56 por MAYORÍA de color (sin mezclar → píxeles nítidos) y se le
pone contorno oscuro de 1 px. Las poses (idle, walk, jump, greet, kiss,
angry, grab, fall, sleep, dance, tired, worried, surprised, stretch) son
dibujos cuadro a cuadro con parámetros: posición de brazos y pies, ojos,
boca, mejillas, inclinación y extras (corazón, zZ, gota, «!», notas…).

    python tools/pets/roundpets.py <carpeta_salida>      → <salida>/<mascota>/<pose>/frame_NNNN.png
    python tools/pets/roundpets.py --install              → añade el panda a tu biblioteca
"""
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

N = 56            # lado del cuadro (px reales)
SS = 4            # superscaling
G = N * SS
YY, XX = np.mgrid[0:G, 0:G].astype(np.float32) / SS


# ── lienzo ─────────────────────────────────────────────────────────────────
class Canvas:
    def __init__(self):
        self.rgba = np.zeros((G, G, 4), np.uint8)

    def put(self, mask, color):
        c = np.array(color if len(color) == 4 else (*color, 255), np.uint8)
        self.rgba[mask] = c

    def to_image(self, outline=(38, 26, 40)):
        # bajar por mayoría de color dentro de cada celda SS×SS
        a = self.rgba.reshape(N, SS, N, SS, 4).transpose(0, 2, 1, 3, 4).reshape(N, N, SS * SS, 4)
        out = np.zeros((N, N, 4), np.uint8)
        for y in range(N):
            for x in range(N):
                cell = a[y, x]
                op = cell[cell[:, 3] > 0]
                if len(op) * 2 < SS * SS:
                    continue
                col = Counter(map(tuple, op)).most_common(1)[0][0]
                out[y, x] = col
        im = Image.fromarray(out, "RGBA")
        # contorno exterior de 1 px
        px = im.load()
        res = im.copy()
        for y in range(N):
            for x in range(N):
                if px[x, y][3]:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < N and 0 <= yy < N and px[xx, yy][3] and px[xx, yy][:3] != outline:
                        res.putpixel((x, y), (*outline, 255))
                        break
        return res


def ell(cx, cy, rx, ry, ang=0.0):
    a = math.radians(ang)
    dx, dy = XX - cx, YY - cy
    u = dx * math.cos(a) + dy * math.sin(a)
    v = -dx * math.sin(a) + dy * math.cos(a)
    return (u / rx) ** 2 + (v / ry) ** 2 <= 1.0


def circ(cx, cy, r):
    return ell(cx, cy, r, r)


def seg(x0, y0, x1, y1, w):
    dx, dy = x1 - x0, y1 - y0
    L2 = dx * dx + dy * dy or 1e-6
    t = np.clip(((XX - x0) * dx + (YY - y0) * dy) / L2, 0, 1)
    px, py = x0 + t * dx, y0 + t * dy
    return (XX - px) ** 2 + (YY - py) ** 2 <= (w / 2) ** 2


def arc(cx, cy, r, a0, a1, w):
    ang = np.degrees(np.arctan2(YY - cy, XX - cx)) % 360
    d = np.sqrt((XX - cx) ** 2 + (YY - cy) ** 2)
    a0, a1 = a0 % 360, a1 % 360
    inside = (ang >= a0) & (ang <= a1) if a0 <= a1 else (ang >= a0) | (ang <= a1)
    return inside & (np.abs(d - r) <= w / 2)


def heart(cx, cy, s):
    return circ(cx - s * 0.5, cy - s * 0.2, s * 0.55) | circ(cx + s * 0.5, cy - s * 0.2, s * 0.55) | \
        ((YY - (cy - s * 0.1)) >= 0) & (np.abs(XX - cx) <= (cy + s * 1.1 - YY) * 0.95) & (YY <= cy + s * 1.1)


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3])


# ── especies ───────────────────────────────────────────────────────────────
PANDA = dict(body=(246, 246, 240), feet=(42, 40, 48), arm=(42, 40, 48), cheek=(250, 180, 196),
             ear=(42, 40, 48), patch=(42, 40, 48), eye_style="dot", nose=(42, 40, 48), R=19.0)

DEF = dict(dy=0.0, sx=1.0, sy=1.0, tilt=0.0, eyes="open", mouth="smile", blush=1.0,
           armL=25.0, armR=25.0, footL=(0.0, 0.0), footR=(0.0, 0.0), look=0.0, extras=())


def rot(px, py, cx, cy, deg):
    a = math.radians(deg)
    dx, dy = px - cx, py - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def draw(sp, **kw):
    p = dict(DEF)
    p.update(kw)
    c = Canvas()
    R = sp["R"]
    cx, cy = N / 2, N - 4 - R * p["sy"] - 5 + p["dy"]
    T = lambda x, y: rot(x, y, cx, cy + R, p["tilt"])      # gira alrededor de los pies
    body = sp["body"]

    # pies (detrás)
    for side, (fx, fy) in ((-1, p["footL"]), (1, p["footR"])):
        x, y = T(cx + side * R * 0.48 + fx, cy + R * p["sy"] * 0.86 + fy)
        c.put(ell(x, y, R * 0.42, R * 0.26, p["tilt"]), sp["feet"])
        c.put(ell(x - 1.5, y - 1.2, R * 0.2, R * 0.1, p["tilt"]), shade(sp["feet"], 1.25))
    # orejas (panda)
    if sp["ear"]:
        for side in (-1, 1):
            x, y = T(cx + side * R * 0.68, cy - R * p["sy"] * 0.72)
            c.put(circ(x, y, R * 0.32), sp["ear"])
    # brazo trasero (cuando está levantado va detrás del cuerpo)
    arms = []
    for side, ang in ((-1, p["armL"]), (1, p["armR"])):
        a = math.radians(ang)
        ax = cx + side * (R * p["sx"] * 0.92) * math.sin(max(a, 0.35)) + side * 1.0
        ay = cy + R * 0.25 - R * 0.95 * (1 - math.cos(a)) * 0.62
        ax, ay = T(ax, ay)
        arms.append((side, ax, ay, ang))
    # cuerpo con sombreado de 3 tonos
    bm = ell(cx, cy, R * p["sx"], R * p["sy"], p["tilt"])
    c.put(bm, body)
    c.put(bm & ~ell(cx - R * 0.12, cy - R * 0.14, R * p["sx"] * 0.98, R * p["sy"] * 0.98, p["tilt"]),
          shade(body, 0.84))
    c.put(bm & ell(cx - R * 0.42, cy - R * 0.5, R * 0.24, R * 0.16, -30), shade(body, 1.08))
    # brazos (delante)
    for side, ax, ay, ang in arms:
        c.put(ell(ax, ay, R * 0.27, R * 0.32, side * (ang - 20)), sp["arm"])
    fx_, fy_ = cx + p["look"] * 2.2, cy - R * 0.05
    # manchas de los ojos (panda)
    if sp["patch"]:
        for side in (-1, 1):
            # gota inclinada: la punta de abajo hacia afuera, sin tocar la nariz
            x, y = T(fx_ + side * R * 0.42, fy_ - R * 0.06)
            c.put(ell(x, y, R * 0.19, R * 0.27, -side * 28 + p["tilt"]), sp["patch"])
    # mejillas
    if p["blush"] > 0:
        col = sp["cheek"] if p["blush"] >= 1 else shade(sp["cheek"], 0.9 + 0.1 * p["blush"])
        for side in (-1, 1):
            off = 0.7 if sp["patch"] else 0.62
            x, y = T(fx_ + side * R * off, fy_ + R * (0.34 if sp["patch"] else 0.22))
            c.put(ell(x, y, R * (0.13 if sp["patch"] else 0.17), R * 0.08), col)
    # ojos
    for side in (-1, 1):
        x, y = T(fx_ + side * R * (0.41 if sp["patch"] else 0.27), fy_ - R * (0.1 if sp["patch"] else 0.12))
        _eye(c, sp, x, y, side, p["eyes"], R)
    # nariz (panda)
    if sp["nose"]:
        x, y = T(fx_, fy_ + R * 0.24)
        c.put(ell(x, y, R * 0.1, R * 0.065), sp["nose"])
    # boca
    x, y = T(fx_, fy_ + R * (0.4 if sp["nose"] else 0.2))
    _mouth(c, x, y, p["mouth"], R)
    # extras
    for ex in p["extras"]:
        _extra(c, ex, cx, cy, R)
    return c.to_image()


INK = (40, 28, 46)


def _eye(c, sp, x, y, side, st, R):
    w = INK if not sp["patch"] else (250, 250, 250)
    if st in ("closed", "sleep"):
        c.put(arc(x, y - R * 0.05, R * 0.12, 20, 160, 1.2), w)
    elif st == "happy":
        c.put(arc(x, y + R * 0.1, R * 0.12, 200, 340, 1.3), w)
    elif st == "half":
        c.put(ell(x, y + R * 0.05, R * 0.1, R * 0.07), w if sp["patch"] else INK)
        c.put(seg(x - R * 0.13, y - R * 0.02, x + R * 0.13, y - R * 0.02, 1.2), w)
    elif st == "dizzy":
        c.put(seg(x - 2.2, y - 2.2, x + 2.2, y + 2.2, 1.1) | seg(x - 2.2, y + 2.2, x + 2.2, y - 2.2, 1.1), w)
    else:
        big = 1.25 if st == "wide" else 1.0
        if sp["eye_style"] == "oval":
            c.put(ell(x, y, R * 0.11 * big, R * 0.22 * big), INK)
            c.put(ell(x, y + R * 0.1 * big, R * 0.08 * big, R * 0.08 * big), (60, 90, 200))
            c.put(ell(x - R * 0.03, y - R * 0.09 * big, R * 0.05, R * 0.07), (255, 255, 255))
        else:
            c.put(circ(x, y, R * 0.085 * big), (250, 250, 250))
            c.put(circ(x + 0.4, y + 0.3, R * 0.045 * big), INK)
        if st == "angry":
            c.put(seg(x - side * R * 0.18, y - R * 0.34, x + side * R * 0.12, y - R * 0.2, 1.6), INK if not sp["patch"] else (250, 90, 90))
        if st == "worried":
            c.put(seg(x - side * R * 0.18, y - R * 0.2, x + side * R * 0.12, y - R * 0.34, 1.4), INK if not sp["patch"] else (250, 250, 250))


def _mouth(c, x, y, m, R):
    red = (200, 40, 70)
    if m == "smile":
        c.put(arc(x, y - R * 0.04, R * 0.1, 25, 155, 1.2), INK)
    elif m == "open":
        c.put(ell(x, y + R * 0.03, R * 0.12, R * 0.1), INK)
        c.put(ell(x, y + R * 0.08, R * 0.07, R * 0.05), red)
    elif m == "o":
        c.put(ell(x, y + R * 0.04, R * 0.08, R * 0.1), INK)
    elif m == "frown":
        c.put(arc(x, y + R * 0.1, R * 0.1, 205, 335, 1.2), INK)
    elif m == "kiss":
        c.put(circ(x + R * 0.04, y + R * 0.03, R * 0.06), red)
    elif m == "wavy":
        c.put(seg(x - R * 0.12, y, x - R * 0.04, y + R * 0.05, 1.1) | seg(x - R * 0.04, y + R * 0.05, x + R * 0.04, y, 1.1)
              | seg(x + R * 0.04, y, x + R * 0.12, y + R * 0.05, 1.1), INK)
    elif m == "grin":
        c.put(ell(x, y + R * 0.02, R * 0.16, R * 0.09) & (YY >= y), INK)
        c.put(ell(x, y + R * 0.07, R * 0.09, R * 0.04), red)


def _extra(c, ex, cx, cy, R):
    kind = ex[0]
    if kind == "heart":
        _k, x, y, s = ex
        c.put(heart(x, y, s), (240, 70, 110))
    elif kind == "z":
        _k, x, y, s = ex
        c.put(seg(x, y, x + s, y, 1.1) | seg(x + s, y, x, y + s, 1.1) | seg(x, y + s, x + s, y + s, 1.1), (110, 140, 230))
    elif kind == "sweat":
        _k, x, y = ex
        c.put(ell(x, y, 1.6, 2.4) | (seg(x, y - 3.6, x, y - 1.4, 1.2)), (120, 190, 250))
    elif kind == "bang":
        _k, x, y = ex
        c.put(seg(x, y, x, y + 5, 1.8), (235, 60, 70))
        c.put(circ(x, y + 7.2, 1.0), (235, 60, 70))
    elif kind == "anger":
        _k, x, y = ex
        for a in (0, 90, 180, 270):
            dx, dy = math.cos(math.radians(a + 45)) * 2.2, math.sin(math.radians(a + 45)) * 2.2
            c.put(arc(x + dx, y + dy, 1.6, a + 90, a + 180, 1.0), (230, 50, 60))
    elif kind == "note":
        _k, x, y = ex
        c.put(ell(x, y + 4, 1.5, 1.2, -20) | seg(x + 1.2, y + 4, x + 1.2, y - 1, 1.0) | seg(x + 1.2, y - 1, x + 3.4, y, 1.0),
              (90, 70, 200))
    elif kind == "star":
        _k, x, y = ex
        c.put(seg(x - 2, y, x + 2, y, 1.0) | seg(x, y - 2, x, y + 2, 1.0), (255, 220, 70))


# ── poses (cuadro a cuadro) ────────────────────────────────────────────────
TAU = math.tau


def poses(sp):
    R = sp["R"]
    top = N - 4 - 2 * R - 5          # parte de arriba de la cabeza, aprox.
    P = {}
    br = lambda i, n: math.sin(i / n * TAU)
    P["default"] = [dict(), dict(dy=0.3, sy=0.99)]
    P["idle"] = [dict(dy=0.4 * (1 - br(i, 8)), sx=1 + 0.012 * br(i, 8), sy=1 - 0.012 * br(i, 8),
                      eyes="closed" if i == 5 else "open", armL=25 + 4 * br(i, 8), armR=25 - 4 * br(i, 8))
                 for i in range(8)]
    P["walk"] = []
    for i in range(8):
        s = math.sin(i / 8 * TAU)
        P["walk"].append(dict(dy=-1.2 * abs(s), tilt=3 * s, footL=(2.2 * s, -2.5 * max(0, s)),
                              footR=(-2.2 * s, -2.5 * max(0, -s)), armL=25 + 22 * s, armR=25 - 22 * s,
                              eyes="closed" if i == 6 else "open"))
    J = [dict(dy=2, sx=1.12, sy=0.86, armL=10, armR=10, eyes="closed", mouth="smile"),
         dict(dy=3, sx=1.18, sy=0.8, armL=5, armR=5, eyes="closed", mouth="o"),
         dict(dy=-3, sx=0.88, sy=1.14, armL=150, armR=150, eyes="wide", mouth="open", footL=(0, -1), footR=(0, -1)),
         dict(dy=-5, sx=0.92, sy=1.1, armL=165, armR=165, eyes="happy", mouth="grin", footL=(0, -2), footR=(0, -2)),
         dict(dy=-5, sx=0.95, sy=1.06, armL=160, armR=160, eyes="happy", mouth="grin", footL=(0, -2), footR=(0, -2),
              extras=[("star", 6, top + 4), ("star", N - 7, top + 6)]),
         dict(dy=-4, sx=0.96, sy=1.04, armL=120, armR=120, eyes="open", mouth="open", footL=(0, -1), footR=(0, -1)),
         dict(dy=-1, sx=1.0, sy=1.0, armL=70, armR=70, eyes="open", mouth="o"),
         dict(dy=2, sx=1.14, sy=0.84, armL=20, armR=20, eyes="closed", mouth="smile")]
    P["jump"] = J
    P["greet"] = [dict(armR=150 + 22 * math.sin(i * 1.4) if i >= 1 else 80, armL=22,
                       eyes="happy" if i % 3 != 2 else "open", mouth="open" if i % 2 else "smile",
                       tilt=-3 * math.sin(i * 1.4), dy=-0.6 * abs(math.sin(i * 1.4))) for i in range(8)]
    P["kiss"] = []
    for i in range(8):
        ex = [("heart", N - 13 + i * 0.6, top + 8 - i * 1.6, 2.2 + i * 0.25)] if i >= 3 else []
        P["kiss"].append(dict(eyes="closed", mouth="kiss", armR=110 if 2 <= i <= 4 else 40, armL=25,
                              blush=1.0, tilt=-4 if i >= 2 else 0, extras=ex))
    P["angry"] = [dict(eyes="angry", mouth="frown", armL=60 + 10 * (i % 2), armR=60 + 10 * ((i + 1) % 2),
                       dy=-0.8 * (i % 2), tilt=(-2, 2)[i % 2], blush=1.0,
                       extras=[("anger", N - 11, top + 6)]) for i in range(8)]
    P["grab"] = [dict(eyes="wide" if i % 3 else "open", mouth="o", armL=165, armR=165, dy=-2 - (i % 2),
                      sx=0.94, sy=1.08, footL=(0, -1 - (i % 2)), footR=(0, -1 - ((i + 1) % 2)),
                      extras=[("sweat", N - 12, top + 8)]) for i in range(6)]
    P["fall"] = [dict(eyes="dizzy", mouth="wavy", tilt=(-30, -18, -6, 6, 18, 30, 18, 6)[i] * 0.6,
                      armL=120 + 30 * math.sin(i), armR=90 + 30 * math.cos(i), dy=-1,
                      extras=[("star", 10 + i * 3, top + 2), ("star", N - 12 - i * 2, top + 4)]) for i in range(8)]
    P["sleep"] = [dict(eyes="sleep", mouth="smile", dy=1.4 - 0.6 * br(i, 8), sx=1.06 + 0.02 * br(i, 8), sy=0.92,
                       armL=12, armR=12, tilt=6, blush=0.6,
                       extras=[("z", N - 12 + (i % 4), top + 6 - (i % 4) * 2, 3 + (i % 4) * 0.5)]) for i in range(8)]
    P["dance"] = [dict(armL=(160, 40)[i % 2], armR=(40, 160)[i % 2], tilt=(-10, 10)[i % 2] * (1 if i % 4 < 2 else 0.6),
                       dy=-1.6 * (i % 2), eyes="happy", mouth="grin", footL=(0, -2 * (i % 2)),
                       footR=(0, -2 * ((i + 1) % 2)),
                       extras=[("note", 5 + (i % 3) * 2, top + 3 + (i % 2) * 3), ("note", N - 10, top + 8 - (i % 3) * 2)])
                  for i in range(8)]
    P["tired"] = [dict(eyes="half", mouth="open" if i % 3 == 0 else "wavy", tilt=7, dy=1.5, sx=1.06, sy=0.94,
                       armL=8, armR=8, blush=1.0, extras=[("sweat", N - 12, top + 9 + i)]) for i in range(6)]
    P["worried"] = [dict(eyes="worried", mouth="wavy", armL=40 + 6 * (i % 2), armR=40 + 6 * ((i + 1) % 2),
                         tilt=(-2, 2)[i % 2], extras=[("sweat", 9, top + 9 + (i % 3))]) for i in range(6)]
    P["surprised"] = [dict(eyes="wide", mouth="o", armL=110 if i else 40, armR=110 if i else 40,
                           dy=-3 if 1 <= i <= 3 else 0, sx=0.94 if 1 <= i <= 3 else 1, sy=1.08 if 1 <= i <= 3 else 1,
                           extras=[("bang", N - 10, top + 1)] if i >= 1 else []) for i in range(6)]
    st = [0, 0.3, 0.7, 1.0, 1.0, 1.0, 0.6, 0.2]
    P["stretch"] = [dict(armL=40 + 135 * k, armR=40 + 135 * k, sy=1 + 0.1 * k, sx=1 - 0.06 * k, dy=-2 * k,
                         eyes="closed" if k > 0.5 else "open", mouth="open" if k > 0.8 else "smile",
                         footL=(-k, 0), footR=(k, 0)) for k in st]
    return P


def build(sp, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    P = poses(sp)
    for name, frames in P.items():
        d = out if name == "default" else out / name
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("frame_*.png"):
            f.unlink()
        for i, kw in enumerate(frames):
            draw(sp, **kw).save(d / f"frame_{i:04d}.png")
    return list(P)


def sheet(sp, path):
    P = poses(sp)
    rows = []
    for name, frames in P.items():
        ims = [draw(sp, **kw).resize((N * 3, N * 3), Image.NEAREST) for kw in frames[:8]]
        rows.append(ims)
    W = 8 * N * 3
    s = Image.new("RGBA", (W, len(rows) * N * 3), (64, 70, 90, 255))
    for r, ims in enumerate(rows):
        for k, im in enumerate(ims):
            s.alpha_composite(im, (k * N * 3, r * N * 3))
    s.save(path)


def install():
    """Añade el panda a TU biblioteca de AnimaLinux."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from animalinux.core.library import Library
    lib = Library()
    for key, sp, name in (("panda", PANDA, "Panda"),):
        existing = next((a for a in lib.animations.values() if a.get("name") == name), None)
        aid = existing["id"] if existing else lib.new_id()
        poses_ = build(sp, lib.frames_dir(aid))
        if not existing:
            lib.add(aid, name, 2, N, N)
        lib.update(aid, mode="life", poses=poses_, scale=2.6, fps=8, on_desktop=True,
                   x=300, y=900, author="AnimaLinux")
        print("instalada", name, aid)


if __name__ == "__main__":
    if sys.argv[1:] == ["--install"]:
        install()
    elif len(sys.argv) > 1 and sys.argv[1] == "--sheet":
        sheet(PANDA, sys.argv[2] + "/panda_sheet.png")
    else:
        out = sys.argv[1] if len(sys.argv) > 1 else "out_pets"
        build(PANDA, Path(out) / "panda")
