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


# ═══════════════════════ nube animada (hablar con la mascota) ═══════════════
#
# La nube sale de la cabeza: primero tres burbujitas (de pequeña a grande),
# luego la nube con un «pop» elástico; flota suave mientras está; al cerrar se
# encoge y se desvanece. El texto aparece letra a letra (los caracteres aún
# ocultos se dibujan transparentes, así la nube no cambia de forma). Mientras
# escucha o piensa muestra tres puntitos que laten.
#
# Todo se dibuja con texturas pequeñas ya rasterizadas: el tick solo mueve,
# escala y funde (Gtk.Snapshot), no vuelve a pintar con cairo salvo cuando
# cambia el texto.
import time as _time

CLOUD_FONT = "Sans Bold 11"
CLOUD_MAX_W = 230
PUFF_SPACE = 30          # px entre la cabeza y la base de la nube
_PUFFS = ((5, 0.18), (7.5, 0.55), (10, 0.92))   # (radio, fracción de altura)


def _ease_back(t):
    t = min(max(t, 0.0), 1.0)
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _ease_out(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def _cloud_shapes(x, y, w, h):
    """Círculos que forman la nube (además de la píldora base): bultos grandes
    y solapados arriba, más pequeños abajo y uno a cada lado."""
    rt = min(max(h * 0.46, 10), 16)
    out = []
    n = max(2, round((w - rt) / (rt * 1.25)))
    for i in range(n):
        cx = x + rt * 0.75 + (w - rt * 1.5) * (i / (n - 1) if n > 1 else 0.5)
        r = rt * (1.0 if i % 2 == 0 else 0.82)
        out.append((cx, y + rt * 0.32, r))
    rb = rt * 0.66
    nb = max(2, n - 1)
    for i in range(nb):
        cx = x + w * (i + 0.5) / nb + (4 if i % 2 else -4)
        out.append((cx, y + h - rb * 0.25, rb))
    out.append((x + 3, y + h * 0.5, h * 0.44))
    out.append((x + w - 3, y + h * 0.5, h * 0.44))
    return out


def _cloud_path(cr, x, y, w, h):
    r = h / 2
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, math.pi / 2)
    cr.arc(x + r, y + r, r, math.pi / 2, 3 * math.pi / 2)
    cr.close_path()
    for cx, cy, rr in _cloud_shapes(x, y, w, h):
        cr.new_sub_path()
        cr.arc(cx, cy, rr, 0, 2 * math.pi)


def _circle_tex(radius, shadow=True):
    s = int(radius * 2 + 6)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, s, s)
    cr = cairo.Context(surf)
    c = s / 2
    if shadow:
        cr.set_source_rgba(0.1, 0.12, 0.2, 0.16)
        cr.arc(c + 1, c + 2, radius, 0, 2 * math.pi)
        cr.fill()
    cr.arc(c, c, radius, 0, 2 * math.pi)
    cr.set_source_rgba(1, 1, 1, 0.97)
    cr.fill_preserve()
    cr.set_line_width(1.5)
    cr.set_source_rgba(0.24, 0.27, 0.40, 0.85)
    cr.stroke()
    return _to_texture(surf), s


def _dot_tex():
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 10, 10)
    cr = cairo.Context(surf)
    cr.arc(5, 5, 3.6, 0, 2 * math.pi)
    cr.set_source_rgba(0.30, 0.34, 0.52, 1)
    cr.fill()
    return _to_texture(surf)


_PUFF_TEX = None
_DOT_TEX = None


def _cloud_layout(cr, text):
    lay = PangoCairo.create_layout(cr)
    lay.set_font_description(Pango.FontDescription.from_string(CLOUD_FONT))
    lay.set_width(CLOUD_MAX_W * Pango.SCALE)
    lay.set_wrap(Pango.WrapMode.WORD_CHAR)
    lay.set_alignment(Pango.Alignment.CENTER)
    lay.set_text(text, -1)
    return lay


def _render_cloud_body(text, shown, min_w=0):
    """Textura de la nube con `shown` caracteres visibles de `text`."""
    probe = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4))
    lay = _cloud_layout(probe, text or " ")
    _ink, lg = lay.get_pixel_extents()
    tw, th, tx = max(1, lg.width), max(1, lg.height), lg.x
    padx, pady = 16, 10
    bw = max(tw + 2 * padx, min_w, 64)
    bh = th + 2 * pady
    M = 18                                    # margen para bultos y sombra
    W, H = int(bw + 2 * M), int(bh + 2 * M)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    cr = cairo.Context(surf)
    ox, oy = M, M
    # sombra
    cr.save()
    cr.translate(1.5, 3)
    _cloud_path(cr, ox, oy, bw, bh)
    cr.set_source_rgba(0.1, 0.12, 0.2, 0.18)
    cr.fill()
    cr.restore()
    # contorno + relleno (el trazo primero, ancho, y el relleno encima tapa
    # las costuras internas entre círculos: queda solo el borde exterior)
    _cloud_path(cr, ox, oy, bw, bh)
    cr.set_line_width(3.2)
    cr.set_source_rgba(0.24, 0.27, 0.40, 0.9)
    cr.stroke()
    _cloud_path(cr, ox, oy, bw, bh)
    grad = cairo.LinearGradient(0, oy - 10, 0, oy + bh + 8)
    grad.add_color_stop_rgba(0, 1, 1, 1, 1)
    grad.add_color_stop_rgba(1, 0.92, 0.94, 1.0, 1)
    cr.set_source(grad)
    cr.fill()
    if text:
        lay = _cloud_layout(cr, text)
        if shown < len(text):
            attrs = Pango.AttrList()
            start = len(text[:shown].encode("utf-8"))
            a = Pango.attr_foreground_alpha_new(1)
            a.start_index = start
            a.end_index = len(text.encode("utf-8"))
            attrs.insert(a)
            lay.set_attributes(attrs)
        cr.set_source_rgb(0.12, 0.13, 0.20)
        cr.move_to(ox + (bw - tw) / 2 - tx, oy + pady)
        PangoCairo.show_layout(cr, lay)
    return _to_texture(surf), W, H


class Cloud:
    """Estado de una nube. mode: "listen" | "think" | "say"."""

    APPEAR = 0.52        # s hasta que la nube está entera
    CLOSE = 0.30
    CPS = 38.0           # letras por segundo al escribir

    def __init__(self, mode="listen", text=""):
        global _PUFF_TEX, _DOT_TEX
        if _PUFF_TEX is None:
            _PUFF_TEX = [_circle_tex(r) for r, _f in _PUFFS]
            _DOT_TEX = _dot_tex()
        self.t0 = _time.monotonic()
        self.mode = mode
        self.text = ""
        self.shown = 0.0
        self.closing_at = None
        self.shift_x = 0.0
        self.head_frac = 0.0      # fracción de la altura del sprite vacía arriba
        self.head_px = 0.0
        self._tex = None
        self._w = self._h = 0
        self._shown_drawn = -1
        self.set(mode, text)

    # -- contenido
    def set(self, mode, text=""):
        if mode != getattr(self, "mode", None) or not hasattr(self, "mode_t"):
            self.mode_t = _time.monotonic()      # desde cuándo está en este modo
        self.mode = mode
        if mode != "say":
            text = ""
        if text != self.text:
            if not text.startswith(self.text):
                self.shown = 0.0
            self.text = text
            self._shown_drawn = -1
        if mode != "say":
            if self._shown_drawn != -2:
                self._tex, self._w, self._h = _render_cloud_body("", 0, min_w=78)
                self._shown_drawn = -2
        else:
            self.step(0.0)

    def close(self):
        if self.closing_at is None:
            self.closing_at = _time.monotonic()

    def finished(self):
        return (self.closing_at is not None
                and _time.monotonic() - self.closing_at > self.CLOSE + 0.12)

    def typing_done(self):
        return self.mode != "say" or self.shown >= len(self.text)

    # -- tick: avanza el escrito; devuelve True si hay que redibujar
    def step(self, dt):
        if self.mode == "say" and self.shown < len(self.text):
            self.shown = min(len(self.text), self.shown + dt * self.CPS)
        n = int(self.shown) if self.mode == "say" else -2
        if self.mode == "say" and n != self._shown_drawn:
            self._tex, self._w, self._h = _render_cloud_body(self.text, n)
            self._shown_drawn = n
        return True

    def size(self):
        """(ancho, alto total sobre el sprite, ancla) — para reservar sitio."""
        return max(self._w, 40), self._h - 14 + PUFF_SPACE + 4, int(self.head_px)

    # -- dibujo
    def snapshot(self, snapshot, width, height=0):
        from gi.repository import Graphene
        now = _time.monotonic()
        t = now - self.t0
        k_close = 1.0
        if self.closing_at is not None:
            k_close = 1.0 - _ease_out((now - self.closing_at) / self.CLOSE)
            if k_close <= 0:
                return
        bob = math.sin(t * 2.3) * 2.0
        cx = width / 2.0 + self.shift_x
        head_x = width / 2.0
        head_y = self.head_frac * height      # dónde empieza el dibujo de verdad
        base_y = head_y - PUFF_SPACE          # base de la nube (y negativa = encima)
        # burbujitas: de la cabeza hacia la nube
        for i, ((r, frac), (tex, s)) in enumerate(zip(_PUFFS, _PUFF_TEX)):
            k = _ease_back((t - i * 0.08) / 0.2) * k_close
            if k <= 0.01:
                continue
            px = head_x + (cx - head_x) * frac + (i - 1) * 3
            py = head_y - 4 - (PUFF_SPACE - 6) * frac + math.sin(t * 2.3 + i) * 1.2
            size = s * k
            snapshot.append_texture(tex, Graphene.Rect().init(px - size / 2, py - size / 2,
                                                               size, size))
        k = _ease_back((t - 0.24) / 0.28) * k_close
        if k <= 0.01 or self._tex is None:
            return
        w, h = self._w, self._h
        snapshot.save()
        snapshot.translate(Graphene.Point().init(cx, base_y + bob))
        snapshot.scale(k, k)
        alpha = min(1.0, max(0.0, k_close * 1.4))
        if alpha < 1.0:
            snapshot.push_opacity(alpha)
        # la textura trae 18 px de margen: la base visible queda en base_y
        snapshot.append_texture(self._tex, Graphene.Rect().init(-w / 2, -h + 14, w, h))
        if self.mode in ("listen", "think"):
            speed = 6.0 if self.mode == "think" else 3.5
            for i in range(3):
                a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * speed - i * 0.9))
                dy = -2.5 * max(0.0, math.sin(t * speed - i * 0.9))
                snapshot.push_opacity(a)
                snapshot.append_texture(_DOT_TEX, Graphene.Rect().init(
                    -17 + i * 12, -h / 2 + 14 - 5 + dy, 10, 10))
                snapshot.pop()
        if alpha < 1.0:
            snapshot.pop()
        snapshot.restore()


def bubble_size(b):
    """(ancho, alto, ancla) de un globo/cartel (tupla) o de una Cloud."""
    if isinstance(b, Cloud):
        return b.size()
    _tex, bw, bh, anchor = b
    return bw, bh, anchor


def snapshot_any(snapshot, bubble, width, height=0):
    if isinstance(bubble, Cloud):
        bubble.snapshot(snapshot, width, height)
    else:
        snapshot_bubble(snapshot, bubble, width)
