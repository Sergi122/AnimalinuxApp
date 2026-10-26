"""
Globos de texto y cartelitos que la mascota muestra sobre la cabeza.

Se rasterizan UNA vez por cambio de texto (cairo + Pango) a una Gdk.Texture
pequeña y el ScaledPaintable de cada backend la dibuja encima del sprite, fuera
de las transformaciones de squash/inclinación/espejo. Así sirve igual en
Wayland, X11 y Windows, sin ventanas extra.

Tipos:
  "speech" — globo blanco con piquito (recordatorios, avisos)
  "sign"   — cartel de madera sostenido por un palito (Pomodoro)
  "alert"  — «!» pequeño y rojo (sobresalto por una notificación)
"""
import math

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Pango, PangoCairo  # noqa: E402

_FONT = "Sans Bold 11"
_MAX_W = 220          # ancho máximo del texto antes de partir la línea


def _layout(cr, text, font=_FONT):
    lay = PangoCairo.create_layout(cr)
    lay.set_font_description(Pango.FontDescription.from_string(font))
    lay.set_width(_MAX_W * Pango.SCALE)
    lay.set_wrap(Pango.WrapMode.WORD_CHAR)
    lay.set_alignment(Pango.Alignment.CENTER)
    lay.set_text(text, -1)
    return lay


def _measure(text, font=_FONT):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)
    lay = _layout(cairo.Context(surf), text, font)
    _ink, logical = lay.get_pixel_extents()
    return max(1, logical.width), max(1, logical.height), logical.x


def _rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def _to_texture(surf):
    surf.flush()
    w, h = surf.get_width(), surf.get_height()
    data = bytes(surf.get_data())
    # cairo ARGB32 = BGRA premultiplicado en little-endian
    fmt = Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED
    return Gdk.MemoryTexture.new(w, h, fmt, GLib.Bytes.new(data), surf.get_stride())


def render(text, kind="speech"):
    """Devuelve (Gdk.Texture, ancho, alto, ancla_y). ancla_y = cuántos px de la
    imagen quedan por debajo del borde superior del sprite (el palito del
    cartel baja hasta las manos)."""
    if kind == "alert":
        return _render_alert()
    tw, th, tx = _measure(text)
    padx, pady = (10, 6) if kind == "speech" else (9, 5)
    bw, bh = tw + 2 * padx, th + 2 * pady
    tail = 9 if kind == "speech" else 0
    stick = 22 if kind == "sign" else 0
    W, H = bw + 4, bh + tail + stick + 4
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    ox, oy = 2, 2
    if kind == "sign":
        # palito
        cr.set_source_rgb(0.42, 0.27, 0.14)
        cr.rectangle(W / 2 - 2, oy + bh - 2, 4, stick + 2)
        cr.fill()
        # tabla
        _rounded(cr, ox, oy, bw, bh, 4)
        cr.set_source_rgb(0.86, 0.66, 0.40)
        cr.fill_preserve()
        cr.set_line_width(2)
        cr.set_source_rgb(0.45, 0.29, 0.15)
        cr.stroke()
        # vetas
        cr.set_source_rgba(0.55, 0.38, 0.20, 0.35)
        cr.set_line_width(1)
        for k in (0.33, 0.66):
            cr.move_to(ox + 5, oy + bh * k)
            cr.line_to(ox + bw - 5, oy + bh * k)
            cr.stroke()
        fg = (0.20, 0.11, 0.04)
    else:
        _rounded(cr, ox, oy, bw, bh, 9)
        cr.move_to(W / 2 - 7, oy + bh - 1)
        cr.line_to(W / 2, oy + bh + tail)
        cr.line_to(W / 2 + 7, oy + bh - 1)
        cr.set_source_rgba(1, 1, 1, 0.96)
        cr.fill_preserve()
        cr.set_line_width(1.6)
        cr.set_source_rgba(0.15, 0.17, 0.24, 0.85)
        cr.stroke()
        # tapar el trazo entre el globo y el piquito
        cr.set_source_rgba(1, 1, 1, 0.96)
        cr.rectangle(W / 2 - 6, oy + bh - 2.2, 12, 2.6)
        cr.fill()
        fg = (0.12, 0.13, 0.18)
    lay = _layout(cr, text)
    cr.set_source_rgb(*fg)
    cr.move_to(ox + padx - tx + (tw - min(tw, _MAX_W)) / 2, oy + pady)
    PangoCairo.show_layout(cr, lay)
    anchor = stick + 2 if kind == "sign" else 0
    return _to_texture(surf), W, H, anchor


def _render_alert():
    W, H = 22, 30
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    cr.set_source_rgb(0.92, 0.22, 0.25)
    _rounded(cr, 7, 2, 8, 18, 4)
    cr.fill()
    cr.arc(11, 25, 4, 0, 2 * math.pi)
    cr.fill()
    return _to_texture(surf), W, H, 0


def snapshot_bubble(snapshot, bubble, width):
    """Dibuja el globo centrado sobre el sprite. `bubble` = (tex, w, h, anchor)."""
    from gi.repository import Graphene
    tex, bw, bh, anchor = bubble
    rect = Graphene.Rect().init(width / 2.0 - bw / 2.0, -bh - 4 + anchor, bw, bh)
    snapshot.append_texture(tex, rect)
