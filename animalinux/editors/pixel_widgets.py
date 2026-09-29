"""
Widgets del editor de píxeles (estilo Aseprite): selector de color HSV,
muestras FG/BG, paleta y línea de tiempo con capas × fotogramas.
"""
import colorsys
import math

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

import cairo

INK = (0.11, 0.11, 0.11)


def _rgb(c):
    return c[0] / 255, c[1] / 255, c[2] / 255


def _checker(cr, w, h, sq=4):
    for y in range(0, int(h), sq):
        for x in range(0, int(w), sq):
            v = 0.85 if (x // sq + y // sq) % 2 == 0 else 0.65
            cr.set_source_rgb(v, v, v)
            cr.rectangle(x, y, min(sq, w - x), min(sq, h - y)); cr.fill()


# ── selector de color HSV ────────────────────────────────────────────────────
class ColorPicker(Gtk.Box):
    """Cuadrado saturación/valor + barra de matiz. Llama a `on_change(rgba)`."""

    W, SV_H, HUE_H = 150, 92, 14

    def __init__(self, on_change):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.on_change = on_change
        self.h, self.s, self.v = 0.0, 0.0, 0.0
        self.a = 255

        self.sv = Gtk.DrawingArea()
        self.sv.set_content_width(self.W); self.sv.set_content_height(self.SV_H)
        self.sv.set_draw_func(self._draw_sv)
        self.hue = Gtk.DrawingArea()
        self.hue.set_content_width(self.W); self.hue.set_content_height(self.HUE_H)
        self.hue.set_draw_func(self._draw_hue)
        for area, cb in ((self.sv, self._sv_at), (self.hue, self._hue_at)):
            g = Gtk.GestureDrag(); g.set_button(0)
            g.connect("drag-begin", lambda g, x, y, cb=cb: (setattr(g, "_o", (x, y)), cb(x, y)))
            g.connect("drag-update", lambda g, dx, dy, cb=cb: cb(g._o[0] + dx, g._o[1] + dy))
            area.add_controller(g)
        self.append(self.sv); self.append(self.hue)

    def set_rgba(self, c):
        h, s, v = colorsys.rgb_to_hsv(*_rgb(c))
        if s > 0 and v > 0 or self.v == 0:
            if v > 0 and s > 0: self.h = h
        self.s, self.v, self.a = s, v, c[3]
        if s == 0 and v > 0: pass
        self.sv.queue_draw(); self.hue.queue_draw()

    def rgba(self):
        r, g, b = colorsys.hsv_to_rgb(self.h, self.s, self.v)
        return (round(r * 255), round(g * 255), round(b * 255), self.a if self.a else 255)

    def _emit(self):
        self.sv.queue_draw(); self.hue.queue_draw()
        self.on_change(self.rgba())

    def _sv_at(self, x, y):
        self.s = min(1, max(0, x / self.W))
        self.v = 1 - min(1, max(0, y / self.SV_H))
        self._emit()

    def _hue_at(self, x, y):
        self.h = min(0.9999, max(0, x / self.W)); self._emit()

    def _draw_sv(self, area, cr, w, h):
        r, g, b = colorsys.hsv_to_rgb(self.h, 1, 1)
        cr.set_source_rgb(r, g, b); cr.paint()
        wg = cairo.LinearGradient(0, 0, w, 0)
        wg.add_color_stop_rgba(0, 1, 1, 1, 1); wg.add_color_stop_rgba(1, 1, 1, 1, 0)
        cr.set_source(wg); cr.paint()
        bg = cairo.LinearGradient(0, 0, 0, h)
        bg.add_color_stop_rgba(0, 0, 0, 0, 0); bg.add_color_stop_rgba(1, 0, 0, 0, 1)
        cr.set_source(bg); cr.paint()
        x, y = self.s * w, (1 - self.v) * h
        cr.set_source_rgb(1, 1, 1); cr.set_line_width(2)
        cr.arc(x, y, 4, 0, 2 * math.pi); cr.stroke()
        cr.set_source_rgb(0, 0, 0); cr.set_line_width(1)
        cr.arc(x, y, 5.5, 0, 2 * math.pi); cr.stroke()

    def _draw_hue(self, area, cr, w, h):
        g = cairo.LinearGradient(0, 0, w, 0)
        for k in range(7):
            r, gg, b = colorsys.hsv_to_rgb(k / 6, 1, 1)
            g.add_color_stop_rgb(k / 6, r, gg, b)
        cr.set_source(g); cr.paint()
        x = self.h * w
        cr.set_source_rgb(0, 0, 0); cr.set_line_width(3); cr.move_to(x, 0); cr.line_to(x, h); cr.stroke()
        cr.set_source_rgb(1, 1, 1); cr.set_line_width(1); cr.move_to(x, 0); cr.line_to(x, h); cr.stroke()


# ── FG / BG ──────────────────────────────────────────────────────────────────
class FgBg(Gtk.DrawingArea):
    """Dos muestras superpuestas (primer plano / fondo) como en Aseprite."""

    def __init__(self, on_swap=None):
        super().__init__()
        self.fg = (0, 0, 0, 255)
        self.bg = (255, 255, 255, 255)
        self.set_content_width(56); self.set_content_height(42)
        self.set_draw_func(self._draw)
        self.set_tooltip_text("Color de primer plano y de fondo (X = intercambiar)")
        g = Gtk.GestureClick(); g.connect("pressed", lambda *_: on_swap and on_swap())
        self.add_controller(g)

    def set_colors(self, fg, bg):
        self.fg, self.bg = fg, bg; self.queue_draw()

    def _box(self, cr, x, y, s, c):
        _checker(cr, s, s) if False else None
        cr.save(); cr.translate(x, y); cr.rectangle(0, 0, s, s); cr.clip()
        _checker(cr, s, s)
        cr.set_source_rgba(c[0] / 255, c[1] / 255, c[2] / 255, c[3] / 255); cr.paint()
        cr.restore()
        cr.set_source_rgb(*INK); cr.set_line_width(1); cr.rectangle(x + .5, y + .5, s - 1, s - 1); cr.stroke()

    def _draw(self, a, cr, w, h):
        self._box(cr, 22, 14, 26, self.bg)
        self._box(cr, 4, 2, 26, self.fg)


# ── paleta ───────────────────────────────────────────────────────────────────
class PaletteGrid(Gtk.DrawingArea):
    COLS, CELL = 8, 15

    def __init__(self, colors, on_pick):
        super().__init__()
        self.colors = list(colors)
        self.on_pick = on_pick
        self.sel = -1
        self.set_draw_func(self._draw)
        self._resize()
        for btn in (1, 3):
            g = Gtk.GestureClick(); g.set_button(btn)
            g.connect("pressed", lambda g, n, x, y, b=btn: self._click(x, y, b == 3))
            self.add_controller(g)
        mo = Gtk.EventControllerMotion()
        mo.connect("motion", self._motion)
        self.add_controller(mo)

    def set_colors(self, colors):
        self.colors = list(colors); self._resize(); self.queue_draw()

    def _resize(self):
        rows = max(1, math.ceil(len(self.colors) / self.COLS))
        self.set_content_width(self.COLS * self.CELL)
        self.set_content_height(rows * self.CELL)

    def _index(self, x, y):
        i = int(y // self.CELL) * self.COLS + int(x // self.CELL)
        return i if 0 <= i < len(self.colors) and 0 <= x < self.COLS * self.CELL else -1

    def _click(self, x, y, right):
        i = self._index(x, y)
        if i >= 0:
            self.sel = i; self.queue_draw()
            self.on_pick(self.colors[i], right)

    def _motion(self, ctrl, x, y):
        i = self._index(x, y)
        if i >= 0:
            c = self.colors[i]
            self.set_tooltip_text(f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}  α{c[3]}   (clic izq. = primer plano, der. = fondo)")

    def _draw(self, a, cr, w, h):
        cs = self.CELL
        for i, c in enumerate(self.colors):
            x, y = (i % self.COLS) * cs, (i // self.COLS) * cs
            cr.save(); cr.rectangle(x, y, cs, cs); cr.clip()
            cr.translate(x, y); _checker(cr, cs, cs, 5); cr.restore()
            cr.set_source_rgba(c[0] / 255, c[1] / 255, c[2] / 255, c[3] / 255)
            cr.rectangle(x, y, cs, cs); cr.fill()
        if 0 <= self.sel < len(self.colors):
            x, y = (self.sel % self.COLS) * cs, (self.sel // self.COLS) * cs
            cr.set_source_rgb(1, 1, 1); cr.set_line_width(1)
            cr.rectangle(x + .5, y + .5, cs - 1, cs - 1); cr.stroke()
            cr.set_source_rgb(0, 0, 0)
            cr.rectangle(x + 1.5, y + 1.5, cs - 3, cs - 3); cr.stroke()


# ── línea de tiempo ──────────────────────────────────────────────────────────
class Timeline(Gtk.DrawingArea):
    """Rejilla capas × fotogramas dibujada a mano (rápida y clara)."""

    LW, CW, RH, HH = 168, 17, 20, 18

    def __init__(self, canvas, on_rename=None):
        super().__init__()
        self.canvas = canvas
        self.on_rename = on_rename
        self.set_draw_func(self._draw)
        g = Gtk.GestureClick(); g.set_button(1)
        g.connect("pressed", self._pressed)
        self.add_controller(g)
        self._playhead_drag = False
        d = Gtk.GestureDrag(); d.set_button(1)
        d.connect("drag-update", self._drag)
        d.connect("drag-begin", lambda g, x, y: setattr(self, "_dstart", (x, y)))
        self.add_controller(d)
        self.refresh()

    def refresh(self):
        c = self.canvas
        w = self.LW + max(c.frame_count, 12) * self.CW + 40
        h = self.HH + len(c.layers) * self.RH + 6
        self.set_content_width(w); self.set_content_height(h)
        self.queue_draw()

    # geometría -------------------------------------------------------------
    def _row_layer(self, y):
        r = int((y - self.HH) // self.RH)
        n = len(self.canvas.layers)
        return n - 1 - r if 0 <= r < n else -1

    def _col_frame(self, x):
        f = int((x - self.LW) // self.CW)
        return f if 0 <= f < self.canvas.frame_count else -1

    def _pressed(self, g, n, x, y):
        c = self.canvas
        if y < self.HH:
            f = self._col_frame(x)
            if f >= 0: c.go_to(f)
            return
        li = self._row_layer(y)
        if li < 0: return
        if x < self.LW:
            if x < 20: c.toggle_visible(li)
            elif x < 40: c.toggle_lock(li)
            else:
                c.set_active_layer(li)
                if n >= 2 and self.on_rename: self.on_rename(li)
        else:
            f = self._col_frame(x)
            c.set_active_layer(li)
            if f >= 0: c.go_to(f)
        self.refresh()

    def _drag(self, g, dx, dy):
        x = self._dstart[0] + dx
        if self._dstart[0] >= self.LW:
            f = self._col_frame(x)
            if f >= 0 and f != self.canvas._cur: self.canvas.go_to(f)

    # dibujo ----------------------------------------------------------------
    @staticmethod
    def _has_content(cel):
        return cel.count(0) != len(cel)

    def _draw(self, area, cr, w, h):
        c = self.canvas
        cr.set_source_rgb(0.776, 0.776, 0.776); cr.paint()
        LW, CW, RH, HH = self.LW, self.CW, self.RH, self.HH
        nf = c.frame_count
        # cabecera de fotogramas
        cr.set_source_rgb(0.49, 0.573, 0.62); cr.rectangle(0, 0, w, HH); cr.fill()
        cr.set_font_size(10)
        for f in range(nf):
            x = LW + f * CW
            if f == c._cur:
                cr.set_source_rgb(0.15, 0.2, 0.25); cr.rectangle(x, 0, CW, HH); cr.fill()
                cr.set_source_rgb(1, 1, 1)
            else:
                cr.set_source_rgb(0.05, 0.05, 0.05)
            t = str(f + 1)
            ext = cr.text_extents(t)
            cr.move_to(x + (CW - ext.width) / 2 - ext.x_bearing, HH - 5); cr.show_text(t)
        # filas
        n = len(c.layers)
        for r in range(n):
            li = n - 1 - r
            y = HH + r * RH
            layer = c.layers[li]
            active = li == c._layer
            cr.set_source_rgb(*(0.27, 0.42, 0.55) if active else (0.86, 0.86, 0.86))
            cr.rectangle(0, y, LW, RH); cr.fill()
            self._eye(cr, 5, y + 5, layer.visible, active)
            self._lock(cr, 25, y + 4, layer.locked, active)
            cr.set_source_rgb(*(1, 1, 1) if active else (0.05, 0.05, 0.05))
            cr.set_font_size(11)
            cr.move_to(46, y + RH - 6)
            cr.show_text(layer.name[:16] + (f"  {layer.opacity * 100 // 255}%" if layer.opacity < 255 else ""))
            for f in range(nf):
                x = LW + f * CW
                has = self._has_content(layer.frames[f])
                cur = (f == c._cur)
                if active and cur:
                    cr.set_source_rgb(0.27, 0.42, 0.55)
                elif cur:
                    cr.set_source_rgb(0.62, 0.7, 0.76)
                else:
                    cr.set_source_rgb(0.93, 0.93, 0.93) if has else cr.set_source_rgb(0.83, 0.83, 0.83)
                cr.rectangle(x, y, CW, RH); cr.fill()
                if has:
                    cr.set_source_rgb(1, 1, 1) if (active and cur) else cr.set_source_rgb(0.15, 0.15, 0.15)
                    cr.arc(x + CW / 2, y + RH / 2, 3, 0, 2 * math.pi); cr.fill()
                cr.set_source_rgba(0, 0, 0, 0.35); cr.set_line_width(1)
                cr.rectangle(x + .5, y + .5, CW, RH); cr.stroke()
            cr.set_source_rgba(0, 0, 0, 0.35)
            cr.rectangle(.5, y + .5, LW, RH); cr.stroke()

    @staticmethod
    def _eye(cr, x, y, on, active):
        col = (1, 1, 1) if active else (0.1, 0.1, 0.1)
        cr.set_source_rgba(*col, 1 if on else 0.25); cr.set_line_width(1.3)
        cr.save(); cr.translate(x + 7, y + 5)
        cr.scale(7, 4.2); cr.arc(0, 0, 1, 0, 2 * math.pi); cr.restore(); cr.stroke()
        cr.arc(x + 7, y + 5, 2, 0, 2 * math.pi); cr.fill()

    @staticmethod
    def _lock(cr, x, y, on, active):
        col = (1, 1, 1) if active else (0.1, 0.1, 0.1)
        cr.set_source_rgba(*col, 1 if on else 0.22); cr.set_line_width(1.3)
        cr.rectangle(x + 2.5, y + 6.5, 9, 6); (cr.fill_preserve() if on else None); cr.stroke()
        cr.arc(x + 7, y + 6, 3, math.pi, 2 * math.pi); cr.stroke()
