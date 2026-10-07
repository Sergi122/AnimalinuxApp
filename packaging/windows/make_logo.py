"""Dibuja el logo de AnimaWin (AnimaLinux para Windows) con pycairo y genera los
PNG/ICO. Concepto: la mascota sentada en el borde de una ventana, que es justo lo
que hace la app. Uso: python packaging/windows/make_logo.py"""
import math
from pathlib import Path

import cairo
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
N = 1024


def rrect(c, x, y, w, h, r):
    c.new_sub_path()
    c.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    c.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    c.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    c.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    c.close_path()


def rounded_tri(c, pts, color, r=26):
    c.set_source_rgba(*color)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    c.set_line_width(r * 2)
    c.move_to(*pts[0]); c.line_to(*pts[1]); c.line_to(*pts[2]); c.close_path()
    c.stroke_preserve(); c.fill()


def draw():
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, N, N)
    c = cairo.Context(s)
    # fondo: cuadrado redondeado con degradado violeta -> rosa
    rrect(c, 48, 48, N - 96, N - 96, 220)
    g = cairo.LinearGradient(120, 80, 920, 960)
    g.add_color_stop_rgb(0, 0.36, 0.30, 1.0)
    g.add_color_stop_rgb(0.55, 0.80, 0.36, 0.93)
    g.add_color_stop_rgb(1, 1.0, 0.44, 0.65)
    c.set_source(g); c.fill_preserve()
    c.clip()
    hl = cairo.RadialGradient(330, 220, 10, 330, 220, 620)   # brillo suave arriba-izquierda
    hl.add_color_stop_rgba(0, 1, 1, 1, 0.28); hl.add_color_stop_rgba(1, 1, 1, 1, 0)
    c.set_source(hl); c.paint()
    c.reset_clip()

    # ventana (la mascota camina por su borde superior)
    wx, wy, ww, wh = 150, 640, 724, 250
    rrect(c, wx + 6, wy + 22, ww, wh, 56); c.set_source_rgba(0.1, 0.05, 0.25, 0.28); c.fill()   # sombra
    rrect(c, wx, wy, ww, wh, 56); c.set_source_rgba(1, 1, 1, 0.95); c.fill()
    c.save(); rrect(c, wx, wy, ww, wh, 56); c.clip()      # recorte con la forma completa de la ventana
    c.rectangle(wx, wy, ww, 78); c.set_source_rgba(0.90, 0.88, 1.0, 1); c.fill(); c.restore()
    for i, col in enumerate(((1.0, 0.42, 0.45), (1.0, 0.78, 0.30), (0.40, 0.85, 0.55))):
        c.arc(wx + 62 + i * 54, wy + 39, 15, 0, 2 * math.pi); c.set_source_rgb(*col); c.fill()
    for k in range(3):                                      # líneas de "contenido"
        rrect(c, wx + 60, wy + 118 + k * 38, ww - 120 - (k == 2) * 220, 16, 8)
        c.set_source_rgba(0.64, 0.58, 0.92, 0.55); c.fill()

    # mascota sentada sobre el borde
    body = (0.55, 0.88, 1.0, 1)
    ear_in = (1.0, 0.62, 0.78, 1)
    rounded_tri(c, [(372, 470), (400, 300), (528, 400)], body)
    rounded_tri(c, [(652, 470), (624, 300), (496, 400)], body)
    rounded_tri(c, [(398, 450), (412, 350), (480, 410)], ear_in, 12)
    rounded_tri(c, [(626, 450), (612, 350), (544, 410)], ear_in, 12)
    c.save(); c.translate(512, 530); c.scale(1.0, 0.82)
    c.arc(0, 0, 215, 0, 2 * math.pi); c.restore()
    g2 = cairo.RadialGradient(470, 450, 20, 512, 540, 260)
    g2.add_color_stop_rgb(0, 0.78, 0.95, 1.0); g2.add_color_stop_rgb(1, *body[:3])
    c.set_source(g2); c.fill()
    for ex in (440, 584):                                    # ojos
        c.arc(ex, 520, 30, 0, 2 * math.pi); c.set_source_rgb(0.10, 0.10, 0.28); c.fill()
        c.arc(ex + 9, 509, 10, 0, 2 * math.pi); c.set_source_rgb(1, 1, 1); c.fill()
    for cx in (385, 639):                                    # mofletes
        c.arc(cx, 575, 26, 0, 2 * math.pi); c.set_source_rgba(1.0, 0.55, 0.72, 0.65); c.fill()
    c.set_line_width(11); c.set_line_cap(cairo.LINE_CAP_ROUND); c.set_source_rgb(0.10, 0.10, 0.28)
    c.arc(512, 560, 30, math.radians(20), math.radians(160)); c.stroke()   # sonrisa
    c.arc(512, 640, 150, math.radians(200), math.radians(340))              # sombra bajo el cuerpo
    c.set_source_rgba(0.1, 0.05, 0.25, 0); c.stroke()
    return s


def main():
    tmp = ROOT / "build"; tmp.mkdir(exist_ok=True)
    surf = draw(); master = tmp / "animawin_logo_1024.png"; surf.write_to_png(str(master))
    im = Image.open(master).convert("RGBA")
    out_png = ROOT / "animalinux" / "ui" / "assets" / "animawin.png"
    im.resize((256, 256), Image.LANCZOS).save(out_png, optimize=True)
    im.save(Path(__file__).with_name("animawin.ico"),
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    web = ROOT / "website" / "landing" / "public" / "assets"
    if web.is_dir():
        im.resize((256, 256), Image.LANCZOS).save(web / "animawin.png", optimize=True)
    print("logo generado:", out_png)


if __name__ == "__main__":
    main()
