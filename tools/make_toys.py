"""Dibuja los juguetes (pixel art 16×16, escalado ×3 sin suavizar).

    python tools/make_toys.py   → animalinux/ui/assets/toys/{ball,yarn}/frame_0000.png
"""
from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "animalinux" / "ui" / "assets" / "toys"
S, K = 16, 3
OUTLINE = (40, 30, 48, 255)

# pelota: gajos rojo / blanco / azul con luz arriba a la izquierda
BALL = [
    "......oooo......",
    "....ooRRWWoo....",
    "...oRRRWWWBBo...",
    "..oRhRRWWWBBBo..",
    "..oRRRRWWWBBBo..",
    ".oRRRRRWWWBBBBo.",
    ".oRRRRRWWWBBBBo.",
    ".orRRRRWWWBBBbo.",
    ".orrRRRwWWBBbbo.",
    ".orrrRRwwWBbbbo.",
    "..orrrrwwwbbbo..",
    "..orrrrwwwbbbo..",
    "...orrrwwwbbo...",
    "....oorrwwoo....",
    "......oooo......",
    "................",
]
BALL_PAL = {"o": OUTLINE, "R": (232, 72, 72, 255), "r": (170, 40, 58, 255),
            "W": (250, 246, 236, 255), "w": (200, 194, 196, 255),
            "B": (76, 140, 232, 255), "b": (46, 90, 170, 255),
            "h": (255, 200, 190, 255)}

# ovillo: lana rosa con hebras y una punta suelta
YARN = [
    "......oooo......",
    "....ooPPPPoo....",
    "...oPhhPPpPPo...",
    "..oPhPPPpPPPPo..",
    "..oPPPPpPPPPpo..",
    ".oppPPpPPPPpPPo.",
    ".oPPppPPPPpPPPo.",
    ".oPPPPppPPpPPpo.",
    ".opPPPPPppPPpPo.",
    ".oPppPPPPPppPpo.",
    "..oPPppPPPPPpo..",
    "..opPPPpppPPpo..",
    "...oppPPPPppo.oo",
    "....ooppppooooo.",
    "......oooo......",
    "................",
]
YARN_PAL = {"o": OUTLINE, "P": (240, 128, 172, 255), "p": (190, 80, 132, 255),
            "h": (255, 210, 228, 255)}

# balón de vóley: gajos blanco / amarillo / azul
VOLLEY = [
    "......oooo......",
    "....ooWWYYoo....",
    "...oWhWWYYYBo...",
    "..oWhWWYYYBBBo..",
    "..oWWWYYYBBBWo..",
    ".oYWWYYYBBBWWWo.",
    ".oYYWYYBBBWWWWo.",
    ".oyYYWYBBWWWWwo.",
    ".oyyYYWBWWWWwwo.",
    ".oyyyYYWWWwwwbo.",
    "..oyyyyWWwwbbo..",
    "..obyyywwwbbbo..",
    "...obbyywwbbo...",
    "....oobbbboo....",
    "......oooo......",
    "................",
]
VOLLEY_PAL = {"o": OUTLINE, "W": (250, 248, 240, 255), "w": (198, 196, 200, 255),
              "Y": (255, 214, 64, 255), "y": (206, 154, 30, 255),
              "B": (60, 120, 220, 255), "b": (36, 76, 160, 255), "h": (255, 255, 255, 255)}

# balón de básquet: naranja con costuras oscuras
BASKET = [
    "......oooo......",
    "....ooOOkOoo....",
    "...oOhOOkOOOo...",
    "..oOhOOOkOOOkO..",
    "..oOOOOOkOOkOo..",
    ".okOOOOOkOkOOOo.",
    ".oOkkOOOkkOOOOo.",
    ".oOOOkkkkkkkkko.",
    ".ooOOOOkkOOOOoo.",
    ".oOOOOkOkOOOOro.",
    "..oOOkOOkOOOro..",
    "..orkOOOkOOrro..",
    "...orrrrkrrro...",
    "....oorrkroo....",
    "......oooo......",
    "................",
]
BASKET_PAL = {"o": OUTLINE, "O": (236, 128, 46, 255), "r": (180, 84, 30, 255),
              "k": (60, 34, 24, 255), "h": (255, 196, 140, 255)}

# balón de fútbol: blanco con parches negros
SOCCER = [
    "......oooo......",
    "....ooWWWWoo....",
    "...oWhWKKWWWo...",
    "..oWhWKKKKWWWo..",
    "..oKWWKKKKWWKo..",
    ".oKKWWWKKWWWKKo.",
    ".oKKWWWWWWWWKKo.",
    ".oWWWWWWWWWWWwo.",
    ".oWWKKWWWWKKWwo.",
    ".oWKKKKWWKKKKwo.",
    "..oWKKWWWWKKwo..",
    "..oWWWWKKWwwwo..",
    "...owwwKKwwwo...",
    "....oowwwwoo....",
    "......oooo......",
    "................",
]
SOCCER_PAL = {"o": OUTLINE, "W": (248, 248, 244, 255), "w": (196, 198, 206, 255),
              "K": (44, 42, 56, 255), "h": (255, 255, 255, 255)}


def draw(rows, pal, name):
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in pal:
                im.putpixel((x, y), pal[ch])
    im = im.resize((S * K, S * K), Image.NEAREST)
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    im.save(d / "frame_0000.png")


if __name__ == "__main__":
    draw(BALL, BALL_PAL, "ball")
    draw(YARN, YARN_PAL, "yarn")
    draw(VOLLEY, VOLLEY_PAL, "volley")
    draw(SOCCER, SOCCER_PAL, "soccer")
    draw(BASKET, BASKET_PAL, "basket")
    print("ok", OUT)


# ── balones de deporte (24×24, dibujados por geometría y cuantizados) ──────
N = 24


def _sphere(pattern, base_light, base_dark, name):
    """Esfera con luz arriba-izquierda: pattern(u, v, x, y) -> color base o
    None (usa base); u,v en [-1,1]. Sombra en 3 escalones + contorno."""
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    c = (N - 1) / 2.0
    r = N / 2.0 - 0.6
    for y in range(N):
        for x in range(N):
            dx, dy = (x - c) / r, (y - c) / r
            d2 = dx * dx + dy * dy
            if d2 > 1.0:
                continue
            col = pattern(dx, dy, x, y) or base_light
            # luz: producto con dirección (-0.5,-0.6)
            dz = (1 - d2) ** 0.5
            lit = -0.5 * dx - 0.6 * dy + 0.62 * dz
            if lit < 0.12:
                col = _shade(col, 0.62)
            elif lit < 0.38:
                col = _shade(col, 0.82)
            if lit > 0.86 and d2 < 0.5:
                col = _shade(col, 1.18)
            im.putpixel((x, y), col)
    # contorno de 1 px
    px = im.load()
    out = im.copy()
    for y in range(N):
        for x in range(N):
            if px[x, y][3]:
                continue
            for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xx, yy = x + ox, y + oy
                if 0 <= xx < N and 0 <= yy < N and px[xx, yy][3]:
                    out.putpixel((x, y), OUTLINE)
                    break
    out = out.resize((N * 2, N * 2), Image.NEAREST)
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    out.save(d / "frame_0000.png")


def _shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c[:3]) + (255,)


def _in_star(px, py, cx, cy, R, rot):
    """¿(px,py) dentro de una estrella de 5 puntas (radio interior 0.42 R)?"""
    import math
    pts = []
    for i in range(10):
        rr = R if i % 2 == 0 else R * 0.42
        a = rot + i * math.pi / 5 - math.pi / 2
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _champions(u, v, x, y):
    """Blanco con estrellas azul marino (como el balón de la Champions):
    una grande al centro con su interior claro y medias estrellas en el borde."""
    navy, sky = (28, 38, 96, 255), (120, 160, 220, 255)
    if _in_star(u, v, -0.02, 0.06, 0.72, 0.0):
        return sky if _in_star(u, v, -0.02, 0.06, 0.36, 0.0) else navy
    for (sx, sy, sr, rot) in ((0.86, -0.72, 0.5, 0.3), (-0.86, -0.7, 0.5, 0.6),
                              (0.82, 0.86, 0.5, 0.15), (-0.84, 0.84, 0.5, 0.45)):
        if _in_star(u, v, sx, sy, sr, rot):
            return navy
    return None


def _molten(u, v, x, y):
    """Blanco con dos franjas curvas roja y verde (estilo Molten)."""
    import math
    red, green = (214, 40, 52, 255), (30, 150, 84, 255)
    w1 = v - 0.55 * math.sin(2.2 * u + 0.6) + 0.1
    w2 = v - 0.55 * math.sin(2.2 * u + 0.6) - 0.62
    w3 = v - 0.55 * math.sin(2.2 * u + 0.6) + 0.82
    if abs(w1) < 0.17:
        return red
    if abs(w2) < 0.15:
        return green
    if abs(w3) < 0.15:
        return green
    return None


def _wilson(u, v, x, y):
    """Cuero naranja-marrón con costuras negras y grano (estilo Wilson)."""
    seam = (34, 22, 18, 255)
    if abs(u) < 0.07 or abs(v) < 0.07:
        return seam
    for s in (-1, 1):                      # costuras laterales curvas
        if abs((u - s * 0.95) ** 2 + v * v - 0.42) < 0.09:
            return seam
    if (x * 7 + y * 13) % 11 == 0:         # grano del cuero
        return (186, 92, 38, 255)
    return None


def volley_hd(size=128, ss=3, name="volley"):
    """Balón de vóley estilo Molten (sin letras), en alta resolución y suave:
    el patrón clásico de 18 paneles (cada cara de un cubo proyectado en la
    esfera = 3 franjas, perpendiculares en caras vecinas) con la franja del
    medio curvada en «S» y de color: rojo al frente y arriba, verde a los
    lados; costuras finas, luz arriba a la izquierda y contorno oscuro."""
    import numpy as np
    n = size * ss
    c = (n - 1) / 2.0
    R = n / 2.0 - 2.5 * ss
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    u, v = (xx - c) / R, (yy - c) / R
    d2 = u * u + v * v
    inside = d2 <= 1.0
    z = np.sqrt(np.clip(1.0 - d2, 0, 1))
    pts = np.stack([u, -v, z], axis=-1)                 # x derecha, y arriba, z hacia ti
    # vista girada para que se vean tres caras, como en la foto
    import math
    ay, ax = math.radians(-12), math.radians(14)
    ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]])
    rx = np.array([[1, 0, 0], [0, math.cos(ax), -math.sin(ax)], [0, math.sin(ax), math.cos(ax)]])
    P = pts @ (rx @ ry).T
    X, Y, Z = P[..., 0], P[..., 1], P[..., 2]
    aX, aY, aZ = np.abs(X), np.abs(Y), np.abs(Z)
    face = np.where((aZ >= aX) & (aZ >= aY), 2, np.where(aX >= aY, 0, 1))
    eps = 1e-9
    # coordenadas en la cara (cíclicas: franjas perpendiculares entre vecinas)
    s = np.where(face == 2, X / (aZ + eps), np.where(face == 0, Y / (aX + eps), Z / (aY + eps)))
    t = np.where(face == 2, Y / (aZ + eps), np.where(face == 0, Z / (aX + eps), X / (aY + eps)))
    sign = np.where(face == 2, np.sign(Z), np.where(face == 0, np.sign(X), np.sign(Y)))
    sw = s + 0.34 * np.sin(np.pi * t) * sign            # la «S» de Molten
    white = np.array([246, 245, 238.0])
    red = np.array([206, 32, 44.0])
    green = np.array([24, 142, 80.0])
    colored = np.abs(sw) < 0.46
    col_face = np.where(face[..., None] == 0, green, red)
    base = np.where(colored[..., None], col_face, white)
    # costuras: bordes de franja y de cara
    seam = (np.abs(np.abs(sw) - 0.46) < 0.035) | (np.maximum(np.abs(s), np.abs(t)) > 0.975)
    base = np.where(seam[..., None], base * 0.72, base)
    # luz
    L = np.array([-0.45, 0.55, 0.70])
    L = L / np.linalg.norm(L)
    ndl = np.clip(pts @ L, 0, 1)
    shade = 0.5 + 0.55 * ndl
    rim = np.clip((d2 - 0.75) / 0.25, 0, 1)
    shade = shade * (1 - 0.25 * rim)
    rgb = base * shade[..., None]
    H = np.clip(pts @ (L + np.array([0, 0, 1.0])) / np.linalg.norm(L + np.array([0, 0, 1.0])), 0, 1)
    rgb = rgb + 255 * 0.16 * (H ** 30)[..., None]
    rgb = np.clip(rgb, 0, 255)
    # contorno oscuro fino
    ring = (d2 > 1.0) & (np.sqrt(d2) <= 1.0 + 2.2 * ss / R)
    alpha = np.where(inside | ring, 255, 0)
    rgb = np.where(ring[..., None], np.array([40, 30, 48.0]), rgb)
    img = np.dstack([rgb, alpha]).astype(np.uint8)
    im = Image.fromarray(img, "RGBA").resize((size, size), Image.LANCZOS)
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    im.save(d / "frame_0000.png")
    return im


def _hd_ball(name, size, color_fn, ss=3):
    """Pelota lisa en alta resolución: color_fn(X, Y, Z) -> rgb (numpy) sobre
    la esfera; luz arriba a la izquierda, brillo y contorno oscuro fino."""
    import numpy as np
    n = size * ss
    c = (n - 1) / 2.0
    R = n / 2.0 - 2.5 * ss
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    u, v = (xx - c) / R, (yy - c) / R
    d2 = u * u + v * v
    inside = d2 <= 1.0
    z = np.sqrt(np.clip(1.0 - d2, 0, 1))
    pts = np.stack([u, -v, z], axis=-1)
    base = color_fn(pts[..., 0], pts[..., 1], pts[..., 2])
    L = np.array([-0.45, 0.55, 0.70])
    L = L / np.linalg.norm(L)
    ndl = np.clip(pts @ L, 0, 1)
    shade = (0.5 + 0.55 * ndl) * (1 - 0.25 * np.clip((d2 - 0.75) / 0.25, 0, 1))
    rgb = base * shade[..., None]
    Hv = L + np.array([0, 0, 1.0])
    H = np.clip(pts @ (Hv / np.linalg.norm(Hv)), 0, 1)
    rgb = np.clip(rgb + 255 * 0.22 * (H ** 30)[..., None], 0, 255)
    ring = (d2 > 1.0) & (np.sqrt(d2) <= 1.0 + 2.2 * ss / R)
    alpha = np.where(inside | ring, 255, 0)
    rgb = np.where(ring[..., None], np.array([40, 30, 48.0]), rgb)
    img = np.dstack([rgb, alpha]).astype(np.uint8)
    im = Image.fromarray(img, "RGBA").resize((size, size), Image.LANCZOS)
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    im.save(d / "frame_0000.png")
    return im


def pingpong_hd(size=96):
    """Pelota de ping-pong naranja (de las reglamentarias), lisa, sin letras."""
    import numpy as np
    return _hd_ball("pingpong", size,
                    lambda X, Y, Z: np.broadcast_to(np.array([255, 138, 36.0]), X.shape + (3,)))


def tennis_hd(size=96):
    """Pelota de tenis amarillo fosforito con su costura blanca curva (la
    «costura de pelota de tenis»: dos lóbulos que se enlazan)."""
    import math
    import numpy as np

    def col(X, Y, Z):
        # dos arcos enfrentados (la vista típica de la costura), algo girados
        t = math.radians(28)
        u = X * math.cos(t) - Y * math.sin(t)
        v = X * math.sin(t) + Y * math.cos(t)
        a1 = np.abs(np.hypot(u + 1.12, v) - 0.8) < 0.06
        a2 = np.abs(np.hypot(u - 1.12, v) - 0.8) < 0.06
        felt = np.array([214, 236, 52.0])
        white = np.array([248, 250, 240.0])
        out = np.where((a1 | a2)[..., None], white, felt)
        noise = (np.sin(X * 91.0) * np.cos(Y * 77.0) * 6.0)[..., None]   # fieltro
        return np.clip(out + noise, 0, 255)
    return _hd_ball("tennis", size, col)


if __name__ == "__main__":
    _sphere(_champions, (246, 246, 242, 255), None, "soccer")
    pingpong_hd()
    tennis_hd()
    volley_hd()
    _sphere(_wilson, (214, 112, 46, 255), None, "basket")
    print("balones ok")
