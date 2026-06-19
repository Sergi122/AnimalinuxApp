#!/usr/bin/env python3
"""
Crea una mascota de EJEMPLO con vida para demostrar las mejoras del modo Vida
(squash&stretch, caminado sincronizado, dormir, andar por ventanas, etc.).

Dibuja un personaje chibi sencillo con Pillow (fondo transparente), genera
TODAS las poses procedurales (idle, walk, greet, jump, angry, sleep) y registra
la mascota en la librería marcada para mostrarse en el escritorio.

Uso:
    python -m examples.crear_ejemplo
o:
    python examples/crear_ejemplo.py

Al terminar, abre/relanza AnimaLinux y verás "Ejemplo Vida" caminando.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

# permitir ejecutar tanto como módulo como script suelto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from animalinux import paths                              # noqa: E402
from animalinux.core.library import Library               # noqa: E402
from animalinux.core import pose_generator, image_processor  # noqa: E402
from animalinux.core.pose_generator import _canvas_metrics, _render  # noqa: E402

ANIM_ID = "ejemplo_vida"
NAME = "Ejemplo Vida"


def dibujar_personaje():
    """Un gatito-blob chibi de cuerpo entero, anclable en los pies."""
    W, H = 132, 150
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cuerpo = (120, 190, 235, 255)   # azul pastel
    borde = (60, 90, 130, 255)
    cx = W // 2

    # orejas (triángulos)
    for sx in (-1, 1):
        ex = cx + sx * 34
        d.polygon([(ex - 16, 46), (ex + 16, 46), (ex, 8)],
                  fill=cuerpo, outline=borde)
        d.polygon([(ex - 8, 42), (ex + 8, 42), (ex, 20)],
                  fill=(255, 200, 215, 255))

    # cuerpo (óvalo grande que llega a los pies)
    d.ellipse([cx - 46, 36, cx + 46, 140], fill=cuerpo, outline=borde, width=3)

    # patitas
    d.ellipse([cx - 34, 126, cx - 6, 148], fill=cuerpo, outline=borde, width=2)
    d.ellipse([cx + 6, 126, cx + 34, 148], fill=cuerpo, outline=borde, width=2)

    # ojos
    for sx in (-1, 1):
        ex = cx + sx * 20
        d.ellipse([ex - 9, 64, ex + 9, 86], fill=(255, 255, 255, 255),
                  outline=borde, width=2)
        d.ellipse([ex - 5, 70, ex + 5, 82], fill=(30, 30, 40, 255))
        d.ellipse([ex - 3, 71, ex + 1, 75], fill=(255, 255, 255, 255))

    # mejillas
    for sx in (-1, 1):
        ex = cx + sx * 34
        d.ellipse([ex - 8, 90, ex + 8, 102], fill=(255, 170, 190, 180))

    # boca :3
    d.arc([cx - 12, 88, cx - 1, 100], 0, 160, fill=borde, width=2)
    d.arc([cx + 1, 88, cx + 12, 100], 20, 180, fill=borde, width=2)

    return img


def main():
    paths.ensure_dirs()
    fd = paths.ANIMATIONS_DIR / ANIM_ID
    fd.mkdir(parents=True, exist_ok=True)

    base = dibujar_personaje()
    raw = base.crop(base.getbbox() or (0, 0, base.width, base.height))

    # frame por defecto (neutro) en el MISMO lienzo que las poses → mismo tamaño
    cw, ch, floor, _ = _canvas_metrics(raw)
    _render(raw, cw, ch, floor).save(fd / "frame_0000.png")

    # generar TODAS las poses procedurales desde la imagen base
    raw_path = fd / "_base_tmp.png"
    raw.save(raw_path)
    made = pose_generator.generate_poses(str(raw_path), fd)
    raw_path.unlink(missing_ok=True)

    # espejos (flip_*) para mirar a izquierda/derecha
    image_processor.ensure_flipped(fd)
    for pose in made:
        image_processor.ensure_flipped(fd / pose)

    # registrar en la librería, en modo Vida y en el escritorio
    lib = Library()
    lib.add(ANIM_ID, NAME, 1, cw, ch)
    lib.update(ANIM_ID, mode="life", poses=["default"] + made,
               on_desktop=True, scale=1.0, x=300, y=100, fps=10)

    print(f"✓ Mascota de ejemplo creada: id={ANIM_ID}")
    print(f"  poses: {['default'] + made}")
    print(f"  frames en: {fd}")
    print("  Relanza AnimaLinux (o ya aparece) para verla con vida.")


if __name__ == "__main__":
    main()
