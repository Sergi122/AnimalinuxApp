"""
Mascotas «chibi» en pixel art: cabeza grande + cuerpito + brazos que salen del
cuerpo (nunca tapan la cara), orejas y cola propias de cada animal.

Cada cuadro se dibuja con figuras geométricas a 4× y se baja a 64×64 por
mayoría de color (píxeles nítidos) con contorno oscuro de 1 px, igual que
roundpets.py. Las 15 poses son dibujos cuadro a cuadro con parámetros.

    python tools/pets/chibipets.py --sheet <carpeta>      → hojas de revisión
    python tools/pets/chibipets.py --install [especie…]    → a tu biblioteca
"""
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

N = 64
SS = 4
G = N * SS
YY, XX = np.mgrid[0:G, 0:G].astype(np.float32) / SS
INK = (40, 28, 46)
TAU = math.tau


class Canvas:
    def __init__(self):
        self.rgba = np.zeros((G, G, 4), np.uint8)

    def put(self, mask, color):
        self.rgba[mask] = np.array((*color[:3], 255), np.uint8)

    def to_image(self, outline=INK):
        a = self.rgba.reshape(N, SS, N, SS, 4).transpose(0, 2, 1, 3, 4).reshape(N, N, SS * SS, 4)
        out = np.zeros((N, N, 4), np.uint8)
        for y in range(N):
            for x in range(N):
                cell = a[y, x]
                op = cell[cell[:, 3] > 0]
                if len(op) * 2 < SS * SS:
                    continue
                out[y, x] = Counter(map(tuple, op)).most_common(1)[0][0]
        alpha = out[..., 3] > 0
        pad = np.pad(alpha, 1)
        ring = pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
        ring &= ~alpha
        out[ring] = (*outline, 255)
        return Image.fromarray(out, "RGBA")


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
    return (XX - (x0 + t * dx)) ** 2 + (YY - (y0 + t * dy)) ** 2 <= (w / 2) ** 2


def arc(cx, cy, r, a0, a1, w):
    ang = np.degrees(np.arctan2(YY - cy, XX - cx)) % 360
    d = np.sqrt((XX - cx) ** 2 + (YY - cy) ** 2)
    a0, a1 = a0 % 360, a1 % 360
    inside = (ang >= a0) & (ang <= a1) if a0 <= a1 else (ang >= a0) | (ang <= a1)
    return inside & (np.abs(d - r) <= w / 2)


def tri(p0, p1, p2):
    def side(a, b):
        return (XX - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (YY - b[1])
    d1, d2, d3 = side(p0, p1), side(p1, p2), side(p2, p0)
    neg = (d1 < 0) | (d2 < 0) | (d3 < 0)
    pos = (d1 > 0) | (d2 > 0) | (d3 > 0)
    return ~(neg & pos)


def heart(cx, cy, s):
    return circ(cx - s * 0.5, cy - s * 0.2, s * 0.55) | circ(cx + s * 0.5, cy - s * 0.2, s * 0.55) | \
        ((YY - (cy - s * 0.1)) >= 0) & (np.abs(XX - cx) <= (cy + s * 1.1 - YY) * 0.95) & (YY <= cy + s * 1.1)


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3])


def rot(px, py, cx, cy, deg):
    a = math.radians(deg)
    dx, dy = px - cx, py - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


# ── especies ───────────────────────────────────────────────────────────────
WHITE = (250, 248, 242)
PINK = (246, 168, 186)
SPECIES = {
    "panda": dict(name="Panda", body=(246, 246, 240), limb=(44, 42, 52), ears="round", ear=(44, 42, 52),
                  patch=(44, 42, 52), nose=(44, 42, 52), belly=None, muzzle=None, tail=None, cheek=(250, 178, 196)),
    "conejo": dict(name="Conejo", body=(226, 184, 142), limb=(226, 184, 142), ears="long", ear=(226, 184, 142),
                   inner=PINK, nose=(236, 120, 150), belly=(252, 238, 218), muzzle=(252, 238, 218), tail="puff",
                   tailc=(252, 244, 232), cheek=(246, 150, 160), paws=(252, 238, 218)),
    "raton": dict(name="Ratón", body=(170, 172, 188), limb=(170, 172, 188), ears="big", ear=(170, 172, 188),
                  inner=PINK, nose=(240, 130, 160), belly=(224, 224, 234), muzzle=(224, 224, 234), tail="rope",
                  tailc=(240, 160, 176), cheek=(246, 160, 180), whiskers=True, paws=(240, 170, 186)),
    "zorro": dict(name="Zorro", body=(236, 128, 52), limb=(236, 128, 52), paws=(72, 46, 42), ears="pointy", ear=(236, 128, 52),
                  inner=(72, 46, 42), nose=(44, 32, 36), belly=WHITE, muzzle=WHITE, tail="bushy",
                  tailc=(236, 128, 52), tailtip=WHITE, cheek=(250, 160, 120)),
    "gato": dict(name="Gato", body=(168, 170, 182), limb=(168, 170, 182), ears="cat", ear=(168, 170, 182), inner=PINK,
                 nose=(240, 130, 160), belly=WHITE, muzzle=WHITE, tail="curl", tailc=(168, 170, 182),
                 stripes=(112, 114, 130), cheek=(246, 160, 180), whiskers=True, paws=WHITE),
    "perro": dict(name="Perro", body=(232, 200, 150), limb=(232, 200, 150), ears="floppy", ear=(150, 96, 60),
                  nose=(44, 32, 36), belly=WHITE, muzzle=WHITE, tail="stub", tailc=(232, 200, 150),
                  spot=(150, 96, 60), cheek=(246, 150, 140), paws=WHITE, tongue=True),
    "oso": dict(name="Oso", body=(156, 104, 70), limb=(156, 104, 70), ears="round", ear=(156, 104, 70), inner=(226, 186, 150),
                nose=(44, 32, 36), belly=(226, 186, 150), muzzle=(232, 196, 160), tail=None, cheek=(236, 140, 130),
                paws=(226, 186, 150)),
    "koala": dict(name="Koala", body=(164, 170, 182), limb=(164, 170, 182), ears="fluffy", ear=(164, 170, 182),
                  inner=(240, 236, 240), bignose=(56, 52, 66), belly=(232, 232, 240), muzzle=None, tail=None,
                  cheek=(246, 170, 190), paws=(232, 232, 240)),
    "cerdito": dict(name="Cerdito", body=(250, 186, 198), limb=(250, 186, 198), ears="pig", ear=(250, 186, 198),
                    inner=(236, 140, 160), snout=(240, 150, 170), belly=(255, 214, 222), muzzle=None, tail="pigcurl",
                    tailc=(236, 150, 170), cheek=(240, 120, 150)),
    "rana": dict(name="Rana", body=(120, 200, 100), limb=(120, 200, 100), ears=None, frog=True, belly=(222, 244, 170),
                 muzzle=None, tail=None, cheek=(246, 150, 160), paws=(222, 244, 170), wide_mouth=True),
    "pollito": dict(name="Pollito", body=(255, 216, 80), limb=(250, 196, 60), ears=None, tuft=(255, 200, 60),
                    beak=(250, 140, 50), feet=(250, 140, 50), belly=(255, 236, 150), muzzle=None, tail=None,
                    cheek=(250, 150, 140)),
    "mapache": dict(name="Mapache", body=(150, 150, 160), limb=(88, 84, 96), ears="pointy", ear=(150, 150, 160),
                    inner=(70, 66, 78), mask=(70, 66, 78), nose=(40, 36, 44), belly=(214, 214, 222), muzzle=WHITE,
                    tail="ringed", tailc=(150, 150, 160), tailring=(70, 66, 78), cheek=(240, 150, 160)),
    "tigre": dict(name="Tigre", body=(246, 150, 52), limb=(246, 150, 52), ears="round", ear=(246, 150, 52),
                  inner=WHITE, nose=(236, 110, 130), belly=WHITE, muzzle=WHITE, tail="curl", tailc=(246, 150, 52),
                  stripes=(60, 40, 44), tailstripes=True, cheek=(250, 160, 130), whiskers=True, paws=WHITE),
    "claudio": dict(name="Claudio", box=True, body=(217, 119, 87), limb=(217, 119, 87), cheek=(240, 150, 140)),
    "pinguino": dict(name="Pingüino", body=(46, 56, 90), limb=(46, 56, 90), ears=None, face=WHITE,
                     belly=WHITE, muzzle=None, beak=(250, 172, 56), feet=(250, 172, 56), tail=None,
                     cheek=(250, 160, 176)),
}

DEF = dict(dy=0.0, hdy=0.0, sx=1.0, sy=1.0, tilt=0.0, htilt=0.0, eyes="open", mouth="smile", blush=1.0,
           armL=20.0, armR=20.0, footL=(0.0, 0.0), footR=(0.0, 0.0), look=0.0, ear=0.0, tail=0.0, extras=())

GROUND = 62.0


def draw(sp, **kw):
    if sp.get("box"):
        return draw_box(sp, **kw)
    p = dict(DEF)
    p.update(kw)
    c = Canvas()
    cx = N / 2
    # cuerpo
    by = GROUND - 9.5 + p["dy"]
    brx, bry = 10.5 * p["sx"], 8.5 * p["sy"]
    # cabeza
    hx = cx + p["look"] * 0.6
    hy = by - bry - 6.5 + p["hdy"] - (p["sy"] - 1) * 6
    hrx, hry = 16.5 * p["sx"] ** 0.5, 14.0 * p["sy"] ** 0.5
    piv = (cx, GROUND)
    T = lambda x, y: rot(x, y, *piv, p["tilt"])
    H = lambda x, y: T(*rot(x, y, hx, hy + hry * 0.6, p["htilt"]))
    ang = p["tilt"] + p["htilt"]
    body, limb = sp["body"], sp["limb"]

    # cola (detrás de todo)
    if sp.get("tail") == "bushy":
        w = p["tail"]
        x0, y0 = T(cx + 8, by + 3)
        x1, y1 = T(cx + 19 + 2 * w, by - 6 - 2 * abs(w))
        c.put(ell((x0 + x1) / 2, (y0 + y1) / 2, 8.5, 5.0, -50 + ang + 8 * w), sp["tailc"])
        c.put(ell(x1 - 0.5, y1, 3.6, 3.2, ang), sp["tailtip"])
    elif sp.get("tail") == "rope":
        w = p["tail"]
        pts = [T(cx + 8 + k * 2.2, by + 5 - 7 * math.sin(k / 6 * math.pi) - w * k * 0.5) for k in range(8)]
        for (a0, b0), (a1, b1) in zip(pts, pts[1:]):
            c.put(seg(a0, b0, a1, b1, 1.6), sp["tailc"])
    elif sp.get("tail") in ("curl", "ringed"):
        w = p["tail"]
        pts = [T(cx + 8 + k * 1.9 + w * k * 0.2, by + 4 - k * 2.4 + 0.25 * k * k - w * k * 0.3) for k in range(9)]
        for j, ((a0, b0), (a1, b1)) in enumerate(zip(pts, pts[1:])):
            colr = sp["tailc"]
            if sp.get("tail") == "ringed" and j % 2:
                colr = sp["tailring"]
            elif sp.get("tailstripes") and j % 3 == 2:
                colr = sp["stripes"]
            c.put(seg(a0, b0, a1, b1, 4.2 if sp.get("tail") == "ringed" else 2.6), colr)
    elif sp.get("tail") == "stub":
        x, y = T(cx + 10, by - 1)
        c.put(ell(x, y, 2.2, 4.0, 35 + 25 * p["tail"]), sp["tailc"])
    elif sp.get("tail") == "pigcurl":
        x, y = T(cx + 11, by)
        c.put(arc(x, y, 2.2, 0, 300 + 20 * p["tail"], 1.3), sp["tailc"])
    elif sp.get("tail") == "puff":
        x, y = T(cx + 10.5, by + 2 - p["tail"])
        c.put(circ(x, y, 3.4), sp["tailc"])

    # pies
    footc = sp.get("feet", limb if sp.get("paws") is None else body)
    for side, (fx, fy) in ((-1, p["footL"]), (1, p["footR"])):
        x, y = T(cx + side * 5.5 + fx, GROUND - 2.3 + fy + min(0, p["dy"]))
        c.put(ell(x, y, 4.4, 2.6, ang * 0.3), footc)
        if sp.get("paws"):
            c.put(ell(x, y + 0.6, 2.4, 1.2), sp["paws"])

    # cuerpo
    x, y = T(cx, by)
    bm = ell(x, y, brx, bry, p["tilt"])
    c.put(bm, body)
    c.put(bm & ~ell(x - 1.2, y - 1.4, brx * 0.97, bry * 0.95, p["tilt"]), shade(body, 0.82))
    if sp.get("belly"):
        c.put(bm & ell(x, y + 1.2, brx * 0.6, bry * 0.72, p["tilt"]), sp["belly"])

    # orejas (detrás de la cabeza)
    kind = sp.get("ears")
    e = p["ear"]  # 0 = arriba; 1 = caídas
    if kind == "round":
        for s in (-1, 1):
            x, y = H(hx + s * 12.5, hy - 10.5)
            c.put(circ(x, y, 5.2), sp["ear"])
    elif kind == "big":
        for s in (-1, 1):
            x, y = H(hx + s * (14 + 2 * e), hy - 8 + 4 * e)
            c.put(circ(x, y, 7.6), sp["ear"])
            c.put(circ(x + s * 0.4, y + 0.5, 4.8), sp["inner"])
    elif kind == "long":
        e = max(-0.2, min(0.55, e * 0.6))
        for s in (-1, 1):
            a = s * (12 + 55 * e)
            x, y = H(hx + s * (6 + 6 * e), hy - 19 + 13 * e)
            c.put(ell(x, y, 3.8, 10.5, a + ang), sp["ear"])
            c.put(ell(x, y + 0.8, 1.7, 7.2, a + ang), sp["inner"])
    elif kind == "cat":
        for s_ in (-1, 1):
            bx0, by0 = H(hx + s_ * 4.5, hy - 11)
            bx1, by1 = H(hx + s_ * 15.0, hy - 5)
            tx, ty = H(hx + s_ * (13 + 3 * e), hy - 18 + 8 * e)
            c.put(tri((bx0, by0), (bx1, by1), (tx, ty)), sp["ear"])
            ix, iy = H(hx + s_ * 10.5, hy - 9)
            c.put(tri((ix - s_ * 3.0, iy), (ix + s_ * 3.0, iy + 1.5), ((tx + ix) / 2 + s_ * 0.5, (ty + iy) / 2)), sp["inner"])
    elif kind == "fluffy":
        for s_ in (-1, 1):
            x, y = H(hx + s_ * 14.5, hy - 8)
            c.put(circ(x, y, 7.4), sp["ear"])
            c.put(circ(x + s_ * 0.6, y + 0.4, 4.4), sp["inner"])
    elif kind == "pig":
        for s_ in (-1, 1):
            bx0, by0 = H(hx + s_ * 6, hy - 11.5)
            bx1, by1 = H(hx + s_ * 14, hy - 7)
            tx, ty = H(hx + s_ * (14.5 + 2 * e), hy - 16 + 5 * e)
            c.put(tri((bx0, by0), (bx1, by1), (tx, ty)), sp["ear"])
    elif kind == "pointy":
        for s in (-1, 1):
            bx0, by0 = H(hx + s * 5, hy - 10)
            bx1, by1 = H(hx + s * 15.5, hy - 4)
            tx, ty = H(hx + s * (14 + 3 * e), hy - 20 + 9 * e)
            c.put(tri((bx0, by0), (bx1, by1), (tx, ty)), sp["ear"])
            ix, iy = H(hx + s * 10, hy - 8)
            c.put(tri((ix - s * 2.5, iy), (ix + s * 3.2, iy + 1.5), ((tx + ix) / 2 + s, (ty + iy) / 2)), sp["inner"])

    # brazos detrás (levantados por encima del hombro van detrás de la cabeza)
    arms = []
    for s, a_deg in ((-1, p["armL"]), (1, p["armR"])):
        a = math.radians(a_deg)
        sx_, sy_ = cx + s * 7.5, by - bry * 0.45
        L = 8.0
        hxp = sx_ + s * (L * math.sin(min(a, math.radians(115))) + max(0.0, a_deg - 90) * 0.06)
        hyp = sy_ + L * math.cos(a)
        arms.append((s, T(sx_, sy_), T(hxp, hyp), a_deg))

    # cabeza
    x, y = H(hx, hy)
    hm = ell(x, y, hrx, hry, ang)
    c.put(hm, body)
    c.put(hm & ~ell(x - 1.6, y - 1.8, hrx * 0.97, hry * 0.96, ang), shade(body, 0.84))
    c.put(hm & ell(x - hrx * 0.45, y - hry * 0.52, 3.4, 2.0, -25 + ang), shade(body, 1.1))
    if sp.get("face"):  # cara blanca del pingüino (corazón)
        f1x, f1y = H(hx - 5.2, hy + 0.5)
        f2x, f2y = H(hx + 5.2, hy + 0.5)
        c.put(hm & (ell(f1x, f1y, 6.6, 8.2, ang) | ell(f2x, f2y, 6.6, 8.2, ang)), sp["face"])
    if sp.get("spot"):
        sx0, sy0 = H(hx + 6.5, hy - 1)
        c.put(hm & ell(sx0, sy0, 5.0, 5.6, ang), sp["spot"])
    if sp.get("mask"):
        for s_ in (-1, 1):
            mx, my = H(hx + s_ * 6.4, hy + 1.6)
            c.put(hm & ell(mx, my, 5.6, 3.6, -s_ * 12 + ang), sp["mask"])
        bx_, by_ = H(hx, hy + 0.4)
        c.put(hm & ell(bx_, by_, 3.0, 1.6, ang), sp["mask"])
    if sp.get("muzzle"):
        mx, my = H(hx, hy + 6.5)
        c.put(hm & ell(mx, my, 7.2, 5.0, ang), sp["muzzle"])
    if sp.get("stripes"):
        for dx_ in (-3.2, 0, 3.2):
            x0, y0 = H(hx + dx_, hy - 13.5)
            x1, y1 = H(hx + dx_ * 0.8, hy - 9.5 + abs(dx_) * 0.3)
            c.put(hm & seg(x0, y0, x1, y1, 1.4), sp["stripes"])
        for s_ in (-1, 1):
            x0, y0 = H(hx + s_ * 16.5, hy + 1)
            x1, y1 = H(hx + s_ * 13.0, hy + 2)
            c.put(hm & seg(x0, y0, x1, y1, 1.3), sp["stripes"])
    if sp.get("frog"):  # ojos saltones arriba de la cabeza
        for s_ in (-1, 1):
            x, y = H(hx + s_ * 8, hy - 11.5)
            c.put(circ(x, y, 5.4), body)
    if sp.get("tuft"):
        for dx_, h_ in ((-2.2, 3.6), (0.4, 5.0), (2.8, 3.4)):
            x, y = H(hx + dx_, hy - 14 - h_ / 2)
            c.put(ell(x, y, 1.4, h_ / 2 + 0.6, dx_ * 8 + ang), sp["tuft"])
    if kind == "floppy":
        for s_ in (-1, 1):
            a_ = s_ * (18 - 22 * e)
            x, y = H(hx + s_ * 14.0, hy - 2 + 2 * e)
            c.put(ell(x, y, 4.2, 9.0, a_ + ang), sp["ear"])

    # brazos (delante, fuera de la cara)
    for s, (sx_, sy_), (hxp, hyp), a_deg in arms:
        c.put(seg(sx_, sy_, hxp, hyp, 5.2), limb)
        c.put(circ(hxp, hyp, 3.0), limb)
        if sp.get("paws") and limb == body:
            c.put(circ(hxp, hyp + 0.4, 1.6), sp["paws"])

    # manchas del panda (alrededor de los ojos, ojo visible adentro)
    ex_off, ey_off = (8.0, -11.5) if sp.get("frog") else (6.2, 1.2)
    lk = p["look"] * 0.9
    if sp.get("patch"):
        for s in (-1, 1):
            x, y = H(hx + s * ex_off + lk, hy + ey_off + 0.6)
            c.put(ell(x, y, 3.9, 4.9, -s * 30 + ang), sp["patch"])
    # mejillas
    if p["blush"] > 0:
        for s in (-1, 1):
            x, y = H(hx + s * 10.5, hy + 6.2)
            c.put(ell(x, y, 2.4, 1.3, ang), sp["cheek"])
    # ojos
    for s in (-1, 1):
        x, y = H(hx + s * ex_off + lk, hy + ey_off)
        _eye(c, sp, x, y, s, p["eyes"])
    # nariz / pico
    if sp.get("beak"):
        x, y = H(hx + lk * 0.5, hy + 5.6)
        c.put(ell(x, y, 2.6, 1.6, ang), sp["beak"])
        c.put(ell(x, y + 1.6, 2.0, 1.0, ang), shade(sp["beak"], 0.85))
    elif sp.get("bignose"):
        x, y = H(hx + lk * 0.5, hy + 4.4)
        c.put(ell(x, y, 3.0, 3.8, ang), sp["bignose"])
        c.put(ell(x - 1.0, y - 1.6, 0.9, 0.8, ang), (120, 116, 134))
    elif sp.get("snout"):
        x, y = H(hx + lk * 0.5, hy + 5.0)
        c.put(ell(x, y, 4.2, 2.9, ang), sp["snout"])
        for s_ in (-1, 1):
            nx, ny = H(hx + lk * 0.5 + s_ * 1.4, hy + 5.0)
            c.put(ell(nx, ny, 0.7, 1.0, ang), shade(sp["snout"], 0.6))
    elif sp.get("nose"):
        x, y = H(hx + lk * 0.5, hy + 4.6)
        c.put(ell(x, y, 1.9, 1.3, ang), sp["nose"])
    if sp.get("whiskers"):
        for s in (-1, 1):
            for k in (-1, 1):
                x0, y0 = H(hx + s * 5.0, hy + 6.6 + k * 0.5)
                x1, y1 = H(hx + s * 11.5, hy + 6.4 + k * 1.6)
                c.put(seg(x0, y0, x1, y1, 0.6), INK)
    # boca
    if not sp.get("beak") or p["mouth"] in ("open", "o", "grin"):
        my_ = 8.2 if sp.get("beak") else 8.6 if sp.get("snout") or sp.get("bignose") else 2.0 if sp.get("frog") else 7.0
        x, y = H(hx + lk * 0.5, hy + my_)
        if sp.get("wide_mouth") and p["mouth"] == "smile":
            c.put(arc(x, y - 3.0, 5.5, 30, 150, 1.0), INK)
        else:
            _mouth(c, x, y, p["mouth"], sp)
        if sp.get("tongue") and p["mouth"] in ("open", "grin"):
            c.put(ell(x, y + 2.6, 1.4, 1.6, ang), (236, 100, 120))
    for ex in p["extras"]:
        _extra(c, ex)
    return c.to_image()


def rect(cx, cy, w, h, ang=0.0):
    a = math.radians(ang)
    dx, dy = XX - cx, YY - cy
    u = dx * math.cos(a) + dy * math.sin(a)
    v = -dx * math.sin(a) + dy * math.cos(a)
    return (np.abs(u) <= w / 2) & (np.abs(v) <= h / 2)


def draw_box(sp, **kw):
    """Claudio: un bloque naranja de ojos cuadrados, bracitos de bloque a los
    lados y cuatro patitas finas (dos en cada borde, hueco al medio)."""
    p = dict(DEF)
    p.update(kw)
    c = Canvas()
    cx = N / 2
    T = lambda x, y: rot(x, y, cx, GROUND, p["tilt"])
    ang = p["tilt"]
    col = sp["body"]
    W, Hh = 38 * p["sx"], 27 * p["sy"]
    LEG = 8.5
    by = GROUND - LEG - Hh / 2 + p["dy"]
    top = by - Hh / 2
    # patitas
    for i, fr in enumerate((-0.45, -0.24, 0.22, 0.45)):
        side = -1 if fr < 0 else 1
        fx, fy = p["footL"] if side < 0 else p["footR"]
        lift = fy if i in (0, 3) else fy * 0.4
        t0 = by + Hh / 2 - 0.5
        bot = min(GROUND, GROUND + lift + min(0, p["dy"]))
        x, y = T(cx + fr * W + fx * 0.5, (t0 + bot) / 2)
        c.put(rect(x, y, 3.8, max(2.0, bot - t0), ang), col)
    # bracitos: bloques pegados a los lados, a media altura; suben al saludar
    for s_, a_deg in ((-1, p["armL"]), (1, p["armR"])):
        k = max(0.0, min(1.0, (a_deg - 20) / 140))
        x, y = T(cx + s_ * (W / 2 + 2.8), top + Hh * 0.47 - k * Hh * 0.42)
        c.put(rect(x, y, 6.0, Hh * 0.34, ang), col)
    # cuerpo
    x, y = T(cx, by)
    bm = rect(x, y, W, Hh, ang)
    c.put(bm, col)
    c.put(bm & ~rect(x - 1.2, y - 1.2, W, Hh, ang), shade(col, 0.86))
    # ojos cuadrados como el dibujo, alineados a la cuadrícula para que los dos
    # salgan iguales (simétricos respecto al centro del cuadro)
    lk = round(p["look"])
    ey = round(top + Hh * 0.40 + p["hdy"] * 0.5)
    for s_ in (-1, 1):
        x0 = (16 if s_ < 0 else 42) + lk
        x = x0 + 3.0
        st = p["eyes"]
        if st in ("closed", "sleep"):
            c.put(rect(x, ey + 4.0, 6.0, 2.0), INK)
        elif st in ("half", "happy"):
            c.put(rect(x, ey + 3.0 if st == "half" else ey + 2.0, 6.0, 4.0 if st == "happy" else 3.0), INK)
        elif st == "dizzy":
            c.put(seg(x - 2.4, ey + 0.6, x + 2.4, ey + 5.4, 1.4) | seg(x - 2.4, ey + 5.4, x + 2.4, ey + 0.6, 1.4), INK)
        else:
            g = 1 if st == "wide" else 0
            c.put(rect(x, ey + 3.0, 6.0 + 2 * g, 6.0 + 2 * g), INK)
            if st == "angry":
                c.put(seg(x - s_ * 3.6, ey - 2.4, x + s_ * 2.4, ey - 0.6, 1.4), INK)
            if st == "worried":
                c.put(seg(x - s_ * 3.4, ey - 0.6, x + s_ * 2.4, ey - 2.4, 1.3), INK)
    if p["mouth"] in ("open", "o", "grin", "kiss", "frown", "wavy"):
        mx, my = T(cx + lk, top + Hh * 0.66 + p["hdy"] * 0.5)
        _mouth(c, mx, my, p["mouth"], {})
    for e in p["extras"]:
        _extra(c, e)
    return c.to_image()


def _eye(c, sp, x, y, s, st):
    panda = bool(sp.get("patch"))
    line = (250, 250, 250) if panda else INK
    if st in ("closed", "sleep"):
        c.put(arc(x, y - 0.4, 2.2, 20, 160, 1.1), line)
    elif st == "happy":
        c.put(arc(x, y + 1.6, 2.2, 200, 340, 1.2), line)
    elif st == "half":
        c.put(ell(x, y + 0.8, 1.8, 1.3), (250, 250, 250) if panda else INK)
        if panda:
            c.put(circ(x, y + 0.9, 0.9), INK)
        c.put(seg(x - 2.4, y - 0.2, x + 2.4, y - 0.2, 1.1), line)
    elif st == "dizzy":
        c.put(seg(x - 2, y - 2, x + 2, y + 2, 1.0) | seg(x - 2, y + 2, x + 2, y - 2, 1.0), line)
    else:
        big = 1.3 if st == "wide" else 1.0
        if panda:
            c.put(circ(x, y, 1.9 * big), (250, 250, 250))
            c.put(circ(x + 0.3, y + 0.3, 1.1 * big), INK)
        else:
            c.put(ell(x, y, 1.9 * big, 2.5 * big), INK)
            c.put(circ(x - 0.6, y - 0.9 * big, 0.75), (255, 255, 255))
        brow = (250, 250, 250) if panda else INK
        if st == "angry":
            c.put(seg(x - s * 3.2, y - 4.6, x + s * 1.8, y - 3.0, 1.3), (230, 60, 70) if panda else brow)
        if st == "worried":
            c.put(seg(x - s * 3.0, y - 3.0, x + s * 1.8, y - 4.6, 1.2), brow)


def _mouth(c, x, y, m, sp):
    red = (204, 44, 74)
    if m == "smile":
        if sp.get("nose") and sp.get("muzzle"):  # boquita en «w»
            c.put(arc(x - 1.1, y - 0.6, 1.2, 20, 160, 0.9) | arc(x + 1.1, y - 0.6, 1.2, 20, 160, 0.9), INK)
        else:
            c.put(arc(x, y - 0.8, 1.9, 25, 155, 1.0), INK)
    elif m == "open":
        c.put(ell(x, y + 0.5, 2.2, 1.8), INK)
        c.put(ell(x, y + 1.3, 1.3, 0.9), red)
    elif m == "o":
        c.put(ell(x, y + 0.6, 1.4, 1.8), INK)
    elif m == "frown":
        c.put(arc(x, y + 1.8, 1.9, 205, 335, 1.0), INK)
    elif m == "kiss":
        c.put(circ(x + 0.6, y + 0.4, 1.1), red)
    elif m == "wavy":
        c.put(seg(x - 2.2, y, x - 0.7, y + 0.9, 0.9) | seg(x - 0.7, y + 0.9, x + 0.7, y, 0.9)
              | seg(x + 0.7, y, x + 2.2, y + 0.9, 0.9), INK)
    elif m == "grin":
        c.put(ell(x, y + 0.2, 2.8, 1.8) & (YY >= y - 0.2), INK)
        c.put(ell(x, y + 1.2, 1.6, 0.8), red)


def _extra(c, ex):
    kind = ex[0]
    if kind == "heart":
        _k, x, y, s = ex
        c.put(heart(x, y, s), (240, 70, 110))
    elif kind == "z":
        _k, x, y, s = ex
        c.put(seg(x, y, x + s, y, 1.1) | seg(x + s, y, x, y + s, 1.1) | seg(x, y + s, x + s, y + s, 1.1), (110, 140, 230))
    elif kind == "sweat":
        _k, x, y = ex
        c.put(ell(x, y, 1.6, 2.3) | seg(x, y - 3.4, x, y - 1.4, 1.2), (120, 190, 250))
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
              (110, 80, 210))
    elif kind == "star":
        _k, x, y = ex
        c.put(seg(x - 2, y, x + 2, y, 1.0) | seg(x, y - 2, x, y + 2, 1.0), (255, 210, 60))


# ── poses (cuadro a cuadro) ────────────────────────────────────────────────
def poses():
    P = {}
    br = lambda i, n: math.sin(i / n * TAU)
    top = 12
    P["default"] = [dict(), dict(hdy=0.4, sy=0.99)]
    P["idle"] = [dict(hdy=0.5 * (1 - br(i, 8)), sy=1 - 0.015 * br(i, 8), sx=1 + 0.015 * br(i, 8),
                      eyes="closed" if i == 5 else "open", armL=20 + 5 * br(i, 8), armR=20 - 5 * br(i, 8),
                      tail=br(i, 8)) for i in range(8)]
    P["walk"] = []
    for i in range(8):
        s = math.sin(i / 8 * TAU)
        P["walk"].append(dict(dy=-1.1 * abs(s), tilt=3 * s, footL=(2.2 * s, -2.4 * max(0, s)),
                              footR=(-2.2 * s, -2.4 * max(0, -s)), armL=20 + 28 * s, armR=20 - 28 * s,
                              eyes="closed" if i == 6 else "open", tail=s, ear=0.1 * abs(s)))
    P["jump"] = [dict(dy=1.5, sx=1.12, sy=0.86, armL=8, armR=8, eyes="closed", ear=0.25),
                 dict(dy=2.2, sx=1.18, sy=0.8, armL=5, armR=5, eyes="closed", mouth="o", ear=0.35),
                 dict(dy=-4, sx=0.9, sy=1.12, armL=150, armR=150, eyes="wide", mouth="open", footL=(0, -1), footR=(0, -1)),
                 dict(dy=-7, sx=0.94, sy=1.08, armL=165, armR=165, eyes="happy", mouth="grin", footL=(0, -2), footR=(0, -2), ear=-0.1),
                 dict(dy=-7, sx=0.96, sy=1.05, armL=160, armR=160, eyes="happy", mouth="grin", footL=(0, -2), footR=(0, -2),
                      extras=[("star", 7, top + 4), ("star", N - 8, top + 6)]),
                 dict(dy=-5, sx=0.97, sy=1.03, armL=120, armR=120, eyes="open", mouth="open", footL=(0, -1), footR=(0, -1), ear=0.15),
                 dict(dy=-1, armL=60, armR=60, eyes="open", mouth="o", ear=0.3),
                 dict(dy=1.5, sx=1.14, sy=0.84, armL=15, armR=15, eyes="closed", ear=0.3)]
    P["greet"] = [dict(armR=80 if i == 0 else 150 + 22 * math.sin(i * 1.4), armL=18, look=-0.5,
                       eyes="happy" if i % 3 != 2 else "open", mouth="open" if i % 2 else "smile",
                       htilt=-4 * math.sin(i * 1.4), tail=math.sin(i * 1.4)) for i in range(8)]
    P["kiss"] = [dict(eyes="closed", mouth="kiss", armR=120 if 2 <= i <= 4 else 40, armL=20, htilt=-6 if i >= 2 else 0,
                      extras=[("heart", N - 14 + i * 0.6, top + 10 - i * 1.6, 2.2 + i * 0.25)] if i >= 3 else [])
                 for i in range(8)]
    P["angry"] = [dict(eyes="angry", mouth="frown", armL=55 + 12 * (i % 2), armR=55 + 12 * ((i + 1) % 2),
                       dy=-0.8 * (i % 2), tilt=(-2, 2)[i % 2], ear=-0.1, tail=(-1, 1)[i % 2],
                       extras=[("anger", N - 12, top + 4)]) for i in range(8)]
    P["grab"] = [dict(eyes="wide" if i % 3 else "open", mouth="o", armL=165, armR=165, dy=-2 - (i % 2),
                      sx=0.94, sy=1.08, footL=(0, -1 - (i % 2)), footR=(0, -1 - ((i + 1) % 2)), ear=0.2,
                      tail=(-1, 1)[i % 2], extras=[("sweat", N - 13, top + 8)]) for i in range(6)]
    P["fall"] = [dict(eyes="dizzy", mouth="wavy", tilt=(-30, -18, -6, 6, 18, 30, 18, 6)[i] * 0.6,
                      armL=120 + 30 * math.sin(i), armR=90 + 30 * math.cos(i), dy=-1, ear=0.5,
                      extras=[("star", 12 + i * 3, top + 2), ("star", N - 12 - i * 2, top + 4)]) for i in range(8)]
    P["sleep"] = [dict(eyes="sleep", mouth="smile", dy=1.2, hdy=2.2 - 0.6 * br(i, 8), sx=1.06 + 0.02 * br(i, 8), sy=0.92,
                       armL=10, armR=10, htilt=8, blush=0.6, ear=0.8,
                       extras=[("z", N - 13 + (i % 4), top + 6 - (i % 4) * 2, 3 + (i % 4) * 0.5)]) for i in range(8)]
    P["dance"] = [dict(armL=(160, 35)[i % 2], armR=(35, 160)[i % 2], tilt=(-9, 9)[i % 2] * (1 if i % 4 < 2 else 0.6),
                       dy=-1.6 * (i % 2), eyes="happy", mouth="grin", footL=(0, -2 * (i % 2)), footR=(0, -2 * ((i + 1) % 2)),
                       tail=(-1.5, 1.5)[i % 2], ear=0.1 * (i % 2),
                       extras=[("note", 5 + (i % 3) * 2, top + 3 + (i % 2) * 3), ("note", N - 10, top + 8 - (i % 3) * 2)])
                  for i in range(8)]
    P["tired"] = [dict(eyes="half", mouth="open" if i % 3 == 0 else "wavy", htilt=7, hdy=1.5, dy=1, sx=1.05, sy=0.95,
                       armL=6, armR=6, ear=0.7, extras=[("sweat", N - 13, top + 9 + i)]) for i in range(6)]
    P["worried"] = [dict(eyes="worried", mouth="wavy", armL=40 + 8 * (i % 2), armR=40 + 8 * ((i + 1) % 2),
                         htilt=(-2, 2)[i % 2], ear=0.45, extras=[("sweat", 10, top + 9 + (i % 3))]) for i in range(6)]
    P["surprised"] = [dict(eyes="wide", mouth="o", armL=110 if i else 30, armR=110 if i else 30,
                           dy=-3 if 1 <= i <= 3 else 0, sx=0.94 if 1 <= i <= 3 else 1, sy=1.08 if 1 <= i <= 3 else 1,
                           ear=-0.15 if i else 0, extras=[("bang", N - 11, top - 1)] if i >= 1 else []) for i in range(6)]
    st = [0, 0.3, 0.7, 1.0, 1.0, 1.0, 0.6, 0.2]
    P["stretch"] = [dict(armL=30 + 140 * k, armR=30 + 140 * k, sy=1 + 0.08 * k, sx=1 - 0.05 * k, dy=-1.5 * k,
                         eyes="closed" if k > 0.5 else "open", mouth="open" if k > 0.8 else "smile",
                         footL=(-k, 0), footR=(k, 0), ear=-0.1 * k) for k in st]
    return P


def build(sp, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    P = poses()
    for name, frames in P.items():
        d = out if name == "default" else out / name
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("frame_*.png"):
            f.unlink()
        for f in d.glob("flip_*.png"):
            f.unlink()
        for i, kw in enumerate(frames):
            draw(sp, **kw).save(d / f"frame_{i:04d}.png")
    return list(P)


def sheet(sp, path, k=3):
    P = poses()
    rows = [[draw(sp, **kw).resize((N * k, N * k), Image.NEAREST) for kw in fr[:8]] for fr in P.values()]
    s = Image.new("RGBA", (8 * N * k, len(rows) * N * k), (64, 70, 90, 255))
    for r, ims in enumerate(rows):
        for j, im in enumerate(ims):
            s.alpha_composite(im, (j * N * k, r * N * k))
    s.save(path)


def install(keys):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from animalinux.core.library import Library
    lib = Library()
    for i, key in enumerate(keys):
        sp = SPECIES[key]
        name = sp["name"]
        existing = next((a for a in lib.animations.values() if a.get("name") == name), None)
        aid = existing["id"] if existing else lib.new_id()
        ps = build(sp, lib.frames_dir(aid))
        if not existing:
            lib.add(aid, name, 2, N, N)
            lib.update(aid, x=250 + 180 * i, y=900, on_desktop=True)
        lib.update(aid, mode="life", poses=ps, width=N, height=N, frame_count=2, scale=2.3, fps=8, author="AnimaLinux")
        print("instalada", name, aid)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--install":
        install(a[1:] or list(SPECIES))
    elif a and a[0] == "--sheet":
        for k, sp in SPECIES.items():
            sheet(sp, f"{a[1]}/{k}_sheet.png")
    else:
        out = Path(a[0] if a else "out_pets")
        for k, sp in SPECIES.items():
            build(sp, out / k)
