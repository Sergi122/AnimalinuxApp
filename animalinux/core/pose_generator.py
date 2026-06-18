"""
Generación PROCEDURAL de poses a partir de una sola imagen.

No usa IA: deforma la imagen base (balanceo, squash-and-stretch, inclinación)
para fabricar las poses que el modo Vida necesita. Para personajes chibi de
cuerpo completo queda muy natural, es instantáneo y no requiere GPU.

Poses generadas: walk, idle, greet, jump.
Todo se ancla en los "pies" (abajo-centro) para que no se despegue del suelo.
"""
import math
from pathlib import Path

from PIL import Image


def _canvas_metrics(base):
    w, h = base.size
    mx = max(8, round(w * 0.40))       # margen lateral (balanceo/rotación)
    top = max(12, round(h * 0.55))     # espacio arriba (saltos)
    bot = max(4, round(h * 0.12))
    cw, ch = w + 2 * mx, h + top + bot
    floor = ch - bot                    # los pies se apoyan aquí
    return cw, ch, floor, mx


def _render(base, cw, ch, floor, dx=0.0, dy=0.0, angle=0.0, sx=1.0, sy=1.0):
    """Coloca la base deformada sobre un lienzo, anclada en los pies."""
    w, h = base.size
    img = base
    if sx != 1.0 or sy != 1.0:
        img = base.resize((max(1, int(w * sx)), max(1, int(h * sy))),
                          Image.LANCZOS)
    iw, ih = img.size
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    px = int(cw / 2 - iw / 2 + dx)
    py = int(floor - ih + dy)           # base de la imagen sobre el "suelo"
    canvas.alpha_composite(img, (px, py))
    if angle:
        # rota TODO el lienzo alrededor del punto de los pies (sin recortar)
        canvas = canvas.rotate(angle, resample=Image.BICUBIC, expand=False,
                               center=(cw / 2, floor))
    return canvas


def _seq(base, n, fn):
    cw, ch, floor, _ = _canvas_metrics(base)
    out = []
    for i in range(n):
        t = i / n                       # 0..1 en el ciclo
        dx, dy, angle, sx, sy = fn(t)
        out.append(_render(base, cw, ch, floor, dx, dy, angle, sx, sy))
    return out


# ---------- definición de cada pose ----------
def gen_idle(base):
    # respiración suave
    def f(t):
        s = math.sin(2 * math.pi * t)
        return (0, -1 * s, 0, 1.0, 1.0 + 0.025 * s)
    return _seq(base, 8, f)


def gen_walk(base):
    # balanceo lado a lado + rebote vertical (pasos)
    def f(t):
        ang = 6 * math.sin(2 * math.pi * t)
        bob = -4 * abs(math.sin(2 * math.pi * t))
        return (0, bob, ang, 1.0, 1.0)
    return _seq(base, 8, f)


def gen_greet(base):
    # saludo: oscilación rápida e intensa, como diciendo "¡hola!"
    def f(t):
        ang = 12 * math.sin(4 * math.pi * t)
        bob = -3 * abs(math.sin(4 * math.pi * t))
        return (0, bob, ang, 1.0, 1.0)
    return _seq(base, 10, f)


def gen_jump(base):
    # squash (agacharse) -> stretch (despegar) -> apex -> caer -> aterrizar
    keys = [
        (0.0, 1.10, 0.90),   # squash inicial
        (-6, 1.05, 0.97),
        (-40, 0.95, 1.08),   # despegue estirado
        (-70, 0.98, 1.04),
        (-80, 1.00, 1.00),   # apex
        (-70, 1.00, 1.00),
        (-40, 0.98, 1.04),
        (-6, 1.05, 0.97),
        (0.0, 1.12, 0.88),   # aterrizaje squash
        (0.0, 1.0, 1.0),
    ]
    cw, ch, floor, _ = _canvas_metrics(base)
    out = []
    for dy, sx, sy in keys:
        out.append(_render(base, cw, ch, floor, 0, dy, 0, sx, sy))
    return out


def gen_angry(base):
    # temblor rápido de enojo + leve inclinación adelante
    def f(t):
        s = math.sin(8 * math.pi * t)
        return (2 * s, 0, 3 * s, 1.0 + 0.02 * abs(s), 1.0)
    return _seq(base, 8, f)


POSE_GENERATORS = {
    "idle": gen_idle,
    "walk": gen_walk,
    "greet": gen_greet,
    "jump": gen_jump,
    "angry": gen_angry,
}


def generate_poses(base_image_path, frames_dir, poses=None):
    """
    Crea las carpetas de poses (walk/idle/greet/jump) a partir de una imagen.
    Devuelve la lista de poses generadas.
    """
    poses = poses or list(POSE_GENERATORS.keys())
    base = Image.open(base_image_path).convert("RGBA")
    # recortar la base a su contenido para centrar bien
    bbox = base.getbbox()
    if bbox:
        base = base.crop(bbox)

    frames_dir = Path(frames_dir)
    made = []
    for pose in poses:
        gen = POSE_GENERATORS.get(pose)
        if not gen:
            continue
        frames = gen(base)
        if not frames:
            continue
        out_dir = frames_dir / pose
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(frames):
            f.save(out_dir / f"frame_{i:04d}.png")
        made.append(pose)
    return made
