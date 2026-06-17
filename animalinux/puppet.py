"""
Animación POR PARTES (cutout puppet) — mueve brazos y piernas de verdad.

El usuario marca zonas sobre su imagen (rectángulos):
    head, torso, arm_l, arm_r, leg_l, leg_r   (todas opcionales salvo torso)
Cada parte se recorta y se anima rotándola sobre un PIVOTE anatómico:
    - brazos: pivote arriba (hombro)
    - piernas: pivote arriba (cadera)
    - cabeza: pivote abajo (cuello)
No usa IA ni inventa dibujo: reordena y rota lo que ya existe en la imagen.

Formato de las partes (en library.json, campo "rig"):
    { "torso": [x,y,w,h], "arm_l": [x,y,w,h], ... }   coords en px de la imagen base
"""
import math
from pathlib import Path

from PIL import Image

# pivote de cada parte, en fracción (px relativo) dentro de su recorte:
# (fx, fy) -> 0,0 esquina sup-izq ; 0.5,0 centro-arriba ; etc.
PIVOTS = {
    "head":  (0.5, 1.0),   # gira desde el cuello (abajo)
    "torso": (0.5, 1.0),
    "arm_l": (0.5, 0.0),   # gira desde el hombro (arriba)
    "arm_r": (0.5, 0.0),
    "leg_l": (0.5, 0.0),   # gira desde la cadera (arriba)
    "leg_r": (0.5, 0.0),
}
# orden de dibujo (atrás -> adelante)
Z_ORDER = ["arm_l", "leg_l", "torso", "leg_r", "head", "arm_r"]


def _crop_parts(base, rig):
    parts = {}
    for name, box in rig.items():
        x, y, w, h = box
        if w <= 0 or h <= 0:
            continue
        parts[name] = {
            "img": base.crop((x, y, x + w, y + h)),
            "box": (x, y, w, h),
        }
    return parts


def _rotate_about(img, angle, pivot_frac):
    """Rota 'img' alrededor de un pivote dado en fracción de su tamaño."""
    w, h = img.size
    cx, cy = pivot_frac[0] * w, pivot_frac[1] * h
    return img.rotate(angle, resample=Image.BICUBIC, expand=False,
                      center=(cx, cy))


def _canvas_metrics(base):
    w, h = base.size
    mx = max(8, round(w * 0.40))
    top = max(12, round(h * 0.55))
    bot = max(4, round(h * 0.12))
    return w + 2 * mx, h + top + bot, h + top + bot - bot, mx, top


def _compose(base, parts, angles, dx, dy):
    """Dibuja todas las partes con sus ángulos sobre un lienzo con holgura."""
    cw, ch, floor, mx, top = _canvas_metrics(base)
    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    # offset para colocar la imagen base (anclada por los pies, centrada)
    off_x = mx + dx
    off_y = top + dy
    for name in Z_ORDER:
        part = parts.get(name)
        if not part:
            continue
        x, y, w, h = part["box"]
        img = part["img"]
        ang = angles.get(name, 0.0)
        if ang:
            img = _rotate_about(img, ang, PIVOTS.get(name, (0.5, 0.5)))
        canvas.alpha_composite(img, (int(off_x + x), int(off_y + y)))
    # partes no riggeadas (lo que el usuario no marcó) NO se dibujan:
    # por eso 'torso' debería cubrir el cuerpo base. Si falta rig, caer a base.
    if not parts:
        canvas.alpha_composite(base, (int(off_x), int(off_y)))
    return canvas


def _seq(base, parts, n, fn):
    out = []
    for i in range(n):
        t = i / n
        angles, dx, dy = fn(t)
        out.append(_compose(base, parts, angles, dx, dy))
    return out


# ---------- poses por partes ----------
def gen_walk(base, parts):
    def f(t):
        s = math.sin(2 * math.pi * t)
        ang = {
            "leg_l":  18 * s, "leg_r": -18 * s,    # piernas alternan: pasos
            "arm_l": -14 * s, "arm_r":  14 * s,    # brazos contrabalancean
            "torso":  2 * s,
        }
        bob = -3 * abs(s)
        return ang, 0, bob
    return _seq(base, parts, 8, f)


def gen_idle(base, parts):
    def f(t):
        s = math.sin(2 * math.pi * t)
        return {"torso": 1.5 * s, "head": 1.0 * s}, 0, -1 * s
    return _seq(base, parts, 8, f)


def gen_greet(base, parts):
    # saludar: un brazo sube y agita
    def f(t):
        wave = math.sin(6 * math.pi * t)
        return {"arm_r": -70 + 18 * wave, "head": 4 * math.sin(2 * math.pi * t)}, 0, 0
    return _seq(base, parts, 12, f)


def gen_jump(base, parts):
    keys = []
    for dy, body in [(0, 6), (-8, 3), (-45, -8), (-72, -10), (-80, -10),
                     (-72, -10), (-45, -8), (-8, 3), (0, 8), (0, 0)]:
        keys.append(({"arm_l": -body * 2, "arm_r": body * 2,
                      "leg_l": body, "leg_r": -body}, 0, dy))
    out = []
    for angles, dx, dy in keys:
        out.append(_compose(base, parts, angles, dx, dy))
    return out


def gen_angry(base, parts):
    # enojo: brazos sacudiéndose y torso temblando
    def f(t):
        s = math.sin(8 * math.pi * t)
        return {"arm_l": 22 * s, "arm_r": -22 * s, "torso": 3 * s,
                "head": -2 * s}, 0, 0
    return _seq(base, parts, 8, f)


GENERATORS = {"walk": gen_walk, "idle": gen_idle,
              "greet": gen_greet, "jump": gen_jump, "angry": gen_angry}


def generate_poses_from_rig(base_image_path, rig, frames_dir, poses=None):
    """Genera poses moviendo las partes marcadas en 'rig'."""
    poses = poses or list(GENERATORS.keys())
    base = Image.open(base_image_path).convert("RGBA")
    parts = _crop_parts(base, rig)
    frames_dir = Path(frames_dir)
    made = []
    for pose in poses:
        gen = GENERATORS.get(pose)
        if not gen:
            continue
        frames = gen(base, parts)
        if not frames:
            continue
        out_dir = frames_dir / pose
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(frames):
            f.save(out_dir / f"frame_{i:04d}.png")
        made.append(pose)
    return made
