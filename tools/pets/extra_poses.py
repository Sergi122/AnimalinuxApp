"""
Poses nuevas (dance, tired, worried, surprised, stretch) para mascotas que ya
tienen sus poses dibujadas: se usan SUS PROPIOS cuadros (saludo, salto,
agarre, reposo) y se les dibujan encima efectos en pixel art (notas, gotas
de sudor, «!», «zZ»). No se deforma, gira ni espeja nada.

    python tools/pets/extra_poses.py <carpeta_de_la_mascota> [...]
"""
import sys
from pathlib import Path

from PIL import Image

OUT = (40, 28, 46, 255)
BLUE = (120, 190, 250, 255)
RED = (235, 60, 70, 255)
PURPLE = (110, 80, 210, 255)

# iconos de 7×9 dibujados a mano (· = vacío, o = contorno, x = color, w = brillo)
NOTE = ["··oo···", "··oxo··", "··oxxo·", "··ox·oo", "··ox···", "ooox···", "oxxx···", "oxxo···", "·oo····"]
DROP = ["···o···", "··oxo··", "··oxo··", "·oxxxo·", "·oxwxo·", "oxxwxxo", "oxxxxxo", "·oxxxo·", "··ooo··"]
BANG = ["·ooo···", "·oxo···", "·oxo···", "·oxo···", "·oxo···", "·ooo···", "·ooo···", "·oxo···", "·ooo···"]


def icon(rows, color, k):
    im = Image.new("RGBA", (len(rows[0]), len(rows)), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "o":
                im.putpixel((x, y), OUT)
            elif ch == "x":
                im.putpixel((x, y), color)
            elif ch == "w":
                im.putpixel((x, y), (235, 248, 255, 255))
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def frames(d):
    return [Image.open(p).convert("RGBA") for p in sorted(Path(d).glob("frame_*.png"))]


def place(base, ic, fx, fy, pad=1):
    """Pega el icono en (fx, fy) relativo a la caja del dibujo (0..1)."""
    im = base.copy()
    box = im.getbbox() or (0, 0, im.width, im.height)
    x = int(box[0] + (box[2] - box[0]) * fx - ic.width / 2)
    y = int(box[1] + (box[3] - box[1]) * fy - ic.height / 2)
    x = max(pad, min(im.width - ic.width - pad, x))
    y = max(pad, min(im.height - ic.height - pad, y))
    im.alpha_composite(ic, (x, y))
    return im


def save(d, name, ims):
    out = Path(d) / name
    out.mkdir(exist_ok=True)
    for f in out.glob("frame_*.png"):
        f.unlink()
    for i, im in enumerate(ims):
        im.save(out / f"frame_{i:04d}.png")
    return name


def build(pet_dir):
    d = Path(pet_dir)
    base = frames(d) or frames(d / "idle")
    h = base[0].height
    k = max(1, round(h / 56))
    idle = frames(d / "idle") or base
    greet = frames(d / "greet") or idle
    grab = frames(d / "grab") or greet
    sleep = frames(d / "sleep") or idle
    made = []
    # dance: su saludo (brazo arriba) con notas que suben y bajan
    note = icon(NOTE, PURPLE, k)
    dance = []
    for i in range(8):
        f = greet[(i * len(greet)) // 8]
        f = place(f, note, 0.08, 0.12 + 0.05 * (i % 2))
        f = place(f, note, 0.95, 0.2 - 0.05 * (i % 2))
        dance.append(f)
    made.append(save(d, "dance", dance))
    # tired: reposo con gota de sudor que resbala
    drop = icon(DROP, BLUE, k)
    tired = [place(sleep[min(i, len(sleep) - 1) * 0] if i % 3 else idle[i % len(idle)], drop, 0.9, 0.1 + 0.04 * i)
             for i in range(6)]
    made.append(save(d, "tired", tired))
    # worried: reposo con gotas a ambos lados
    worried = []
    for i in range(6):
        f = idle[i % len(idle)]
        f = place(f, drop, 0.06, 0.16 + 0.03 * (i % 3))
        f = place(f, drop, 0.94, 0.2 + 0.03 * ((i + 1) % 3))
        worried.append(f)
    made.append(save(d, "worried", worried))
    # surprised: de frente (sus cuadros de saludo) con «!» que aparece de golpe
    bang = icon(BANG, RED, k)
    surprised = [greet[min(i, len(greet) - 1) if i < 2 else 0] if i == 0
                 else place(greet[0], bang, 0.92, 0.08 - 0.02 * (i == 1)) for i in range(6)]
    made.append(save(d, "surprised", surprised))
    # stretch: sus cuadros con los brazos arriba (agarre), ida y vuelta
    seq = grab[: max(1, len(grab) // 2)]
    stretch = seq + list(reversed(seq))
    made.append(save(d, "stretch", stretch[:10]))
    return made


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, build(p))
