"""
Paneles del editor de animación (estilo Toon Boom Harmony):
línea de tiempo con hoja de exposición, propiedades de herramienta, color, capa y cámara.
"""
import math

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

import cairo

from . import anim_engine as ae
from .pixel_widgets import ColorPicker, FgBg, PaletteGrid

C_BG = (0.235, 0.235, 0.235)
C_ROW = (0.29, 0.29, 0.29)
C_ROW_ACTIVE = (0.36, 0.38, 0.42)
C_BAR = (0.56, 0.58, 0.60)
C_TEXT = (0.86, 0.86, 0.86)
C_RED = (0.86, 0.15, 0.15)
C_SEL = (0.47, 0.62, 0.82)

LAYER_COLORS = [(0.9, 0.5, 0.2), (0.4, 0.75, 0.4), (0.4, 0.6, 0.9), (0.85, 0.4, 0.75),
                (0.9, 0.8, 0.3), (0.4, 0.8, 0.8)]


# ═════════════════════════ línea de tiempo ═══════════════════════════════════
class Timeline(Gtk.DrawingArea):
    LW, CW, RH, HH = 236, 14, 21, 24

    def __init__(self, canvas, on_rename=None, on_menu=None, on_range=None):
        super().__init__()
        self.canvas = canvas
        self.on_rename = on_rename
        self.on_menu = on_menu
        self.on_range = on_range
        self.set_draw_func(self._draw)
        self._drag = None
        d = Gtk.GestureDrag(); d.set_button(1)
        d.connect("drag-begin", self._begin); d.connect("drag-update", self._update)
        d.connect("drag-end", lambda g, dx, dy: setattr(self, "_drag", None))
        self.add_controller(d)
        c = Gtk.GestureClick(); c.set_button(1)
        c.connect("pressed", self._clicked)
        self.add_controller(c)
        r = Gtk.GestureClick(); r.set_button(3)
        r.connect("pressed", self._right)
        self.add_controller(r)
        self.refresh()

    # geometría ---------------------------------------------------------------
    def refresh(self):
        s = self.canvas.scene
        w = self.LW + max(s.frame_count + 30, 80) * self.CW
        rows = len(s.layers) + (1 if s.audio else 0)
        self.set_content_width(w); self.set_content_height(self.HH + rows * self.RH + 8)
        self.queue_draw()

    def _li_at(self, y):
        r = int((y - self.HH) // self.RH)
        n = len(self.canvas.scene.layers)
        return n - 1 - r if 0 <= r < n else -1

    def _frame_at(self, x):
        return max(0, int((x - self.LW) // self.CW))

    def _fx(self, f):
        return self.LW + f * self.CW

    # interacción -------------------------------------------------------------
    def _begin(self, g, x, y):
        self._start = (x, y)
        s = self.canvas.scene
        if x >= self.LW and y < self.HH:
            for which, f in (("start", s.start), ("stop", s.stop)):
                if abs(x - (self._fx(f) + (0 if which == "start" else self.CW))) < 7:
                    self._drag = which; return
            self._drag = "scrub"; self._scrub(x); return
        if x >= self.LW and y >= self.HH:
            li = self._li_at(y)
            if li >= 0:
                self.canvas.set_layer(li)
                self._drag = "scrub"; self._scrub(x)

    def _update(self, g, dx, dy):
        x = self._start[0] + dx
        if self._drag == "scrub": self._scrub(x)
        elif self._drag in ("start", "stop"):
            f = self._frame_at(x - (0 if self._drag == "start" else self.CW // 2))
            s = self.canvas.scene
            if self._drag == "start": s.start = max(0, min(f, s.stop))
            else:
                s.stop = max(s.start, min(f, s.frame_count - 1)) if f < s.frame_count else s.stop
            if self.on_range: self.on_range()
            self.queue_draw()

    def _scrub(self, x):
        f = self._frame_at(x)
        s = self.canvas.scene
        if f >= s.frame_count: f = s.frame_count - 1
        self.canvas.go_to(f)

    def _clicked(self, g, n, x, y):
        if x >= self.LW or y < self.HH: return
        li = self._li_at(y)
        if li < 0: return
        c = self.canvas; l = c.scene.layers[li]
        if x < 22: l.visible = not l.visible; c._changed(True)
        elif x < 42: l.locked = not l.locked; c._changed(True)
        elif x < 62: l.onion = not l.onion; c._changed(True)
        else:
            c.set_layer(li)
            if n >= 2 and self.on_rename: self.on_rename(li)
        self.refresh()

    def _right(self, g, n, x, y):
        li = self._li_at(y)
        if li < 0: return
        self.canvas.set_layer(li)
        f = self._frame_at(x) if x >= self.LW else self.canvas.cur
        if x >= self.LW: self.canvas.go_to(min(f, self.canvas.scene.frame_count - 1))
        if self.on_menu: self.on_menu(self, x, y)

    # dibujo ------------------------------------------------------------------
    def _draw(self, area, cr, w, h):
        c = self.canvas; s = c.scene
        LW, CW, RH, HH = self.LW, self.CW, self.RH, self.HH
        cr.set_source_rgb(*C_BG); cr.paint()
        cr.select_font_face("sans", cairo.FontSlant.NORMAL, cairo.FontWeight.NORMAL)
        n = len(s.layers)
        # rango de reproducción
        cr.set_source_rgba(1, 1, 1, 0.045)
        cr.rectangle(self._fx(s.start), HH, (s.stop - s.start + 1) * CW, h - HH); cr.fill()
        # filas
        for r in range(n):
            li = n - 1 - r; l = s.layers[li]; y = HH + r * RH
            active = li == c.li
            cr.set_source_rgb(*(C_ROW_ACTIVE if active else C_ROW)); cr.rectangle(0, y, LW, RH); cr.fill()
            cr.set_source_rgb(*(0.31, 0.31, 0.31)); cr.rectangle(LW, y, w - LW, RH); cr.fill()
            if active:
                cr.set_source_rgba(1, 1, 1, 0.05); cr.rectangle(LW, y, w - LW, RH); cr.fill()
            self._icons(cr, y, l, active)
            # nombre
            cr.set_font_size(11.5); cr.set_source_rgb(*(1, 1, 1) if active else C_TEXT)
            cr.move_to(88, y + RH - 6.5); cr.show_text(l.name[:22])
            cr.set_font_size(9); cr.set_source_rgba(1, 1, 1, 0.45)
            cr.move_to(LW - 22, y + RH - 7); cr.show_text("V" if l.kind == "vector" else "R")
            # celdas / exposición
            f = 0
            while f < s.frame_count:
                di = l.exposure[f]
                if di < 0: f += 1; continue
                g = f
                while g + 1 < s.frame_count and l.exposure[g + 1] == di: g += 1
                x0 = self._fx(f)
                col = LAYER_COLORS[li % len(LAYER_COLORS)]
                cr.set_source_rgba(col[0], col[1], col[2], 0.85 if active else 0.6)
                cr.rectangle(x0 + 1, y + 3, (g - f + 1) * CW - 2, RH - 6); cr.fill()
                cr.set_source_rgba(0, 0, 0, 0.55)
                cr.arc(x0 + CW / 2, y + RH / 2, 2.6, 0, 2 * math.pi); cr.fill()
                cr.set_font_size(8.5); cr.set_source_rgba(0, 0, 0, 0.75)
                if g > f:
                    cr.move_to(x0 + CW + 2, y + RH - 7); cr.show_text(str(di + 1))
                f = g + 1
            cr.set_source_rgba(0, 0, 0, 0.35); cr.set_line_width(1)
            cr.move_to(0, y + RH + .5); cr.line_to(w, y + RH + .5); cr.stroke()
        if s.audio:
            y = HH + n * RH
            cr.set_source_rgb(0.27, 0.32, 0.27); cr.rectangle(0, y, w, RH); cr.fill()
            cr.set_font_size(11); cr.set_source_rgb(*C_TEXT)
            cr.move_to(66, y + RH - 6.5); cr.show_text("♪ " + s.audio.split("/")[-1][:26])
        # cuadrícula vertical
        cr.set_source_rgba(0, 0, 0, 0.22); cr.set_line_width(1)
        for f in range(s.frame_count + 31):
            x = self._fx(f) + .5
            if f % 5 == 0: cr.move_to(x, HH); cr.line_to(x, h)
        cr.stroke()
        # regla
        cr.set_source_rgb(0.20, 0.20, 0.20); cr.rectangle(0, 0, w, HH); cr.fill()
        cr.set_font_size(10)
        for f in range(s.frame_count + 30):
            x = self._fx(f)
            if (f + 1) % 10 == 0 or f == 0:
                cr.set_source_rgb(*C_TEXT); cr.move_to(x + 1, HH - 12); cr.show_text(str(f + 1))
            cr.set_source_rgba(1, 1, 1, 0.5 if (f + 1) % 5 == 0 else 0.22)
            cr.move_to(x + .5, HH - (6 if (f + 1) % 5 == 0 else 3)); cr.line_to(x + .5, HH); cr.stroke()
        # cabecera de capas
        cr.set_source_rgb(0.20, 0.20, 0.20); cr.rectangle(0, 0, LW, HH); cr.fill()
        cr.set_font_size(11); cr.set_source_rgb(*C_TEXT); cr.move_to(88, HH - 8); cr.show_text("Capas")
        # marcadores inicio / fin
        cr.set_source_rgb(*C_RED)
        for f, off in ((s.start, 0), (s.stop, CW)):
            x = self._fx(f) + off
            cr.move_to(x - 5, 0); cr.line_to(x + 5, 0); cr.line_to(x, 8); cr.close_path(); cr.fill()
        # cabezal
        x = self._fx(c.cur)
        cr.set_source_rgba(*C_RED, 0.28); cr.rectangle(x, 0, CW, h); cr.fill()
        cr.set_source_rgb(*C_RED); cr.set_line_width(1.5)
        cr.move_to(x + CW / 2, 0); cr.line_to(x + CW / 2, h); cr.stroke()

    def _icons(self, cr, y, l, active):
        col = (1, 1, 1) if active else C_TEXT
        cy = y + self.RH / 2
        # ojo
        cr.set_source_rgba(*col, 1 if l.visible else 0.25); cr.set_line_width(1.2)
        cr.save(); cr.translate(11, cy); cr.scale(6, 3.6); cr.arc(0, 0, 1, 0, 2 * math.pi); cr.restore(); cr.stroke()
        cr.arc(11, cy, 1.7, 0, 2 * math.pi); cr.fill()
        # candado
        cr.set_source_rgba(*col, 1 if l.locked else 0.25)
        cr.rectangle(27, cy - 1, 8, 6); (cr.fill_preserve() if l.locked else None); cr.stroke()
        cr.arc(31, cy - 1, 2.6, math.pi, 2 * math.pi); cr.stroke()
        # papel cebolla
        cr.set_source_rgba(*col, 1 if l.onion else 0.25)
        cr.arc(51, cy, 4, 0, 2 * math.pi); cr.stroke()
        cr.arc(51, cy, 1.8, 0, 2 * math.pi); (cr.fill() if l.onion else cr.new_path())
        # muestra de color de la capa
        cr.set_source_rgb(*LAYER_COLORS[self.canvas.scene.layers.index(l) % len(LAYER_COLORS)])
        cr.rectangle(70, y + 5, 8, self.RH - 10); cr.fill()


# ═════════════════════════ propiedades de herramienta ════════════════════════
def _scale(lo, hi, val, step=1, digits=0, width=140):
    s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
    s.set_value(val); s.set_digits(digits); s.set_draw_value(True); s.set_value_pos(Gtk.PositionType.RIGHT)
    s.set_size_request(width, -1); s.set_hexpand(True)
    return s


class ToolProps(Gtk.Box):
    """Muestra solo las opciones de la herramienta activa."""

    GROUPS = {
        "brush":    ("kind", "size:brush_size", "hardness", "opacity", "spacing", "smoothing", "pressure"),
        "pencil":   ("size:pencil_size", "opacity", "smoothing"),
        "eraser":   ("size:eraser_size", "hardness"),
        "smudge":   ("size:smudge_size", "hardness"),
        "paint":    ("tol", "gap", "contig", "fill_all", "opacity"),
        "gradient": ("radial", "opacity"),
        "line":     ("width", "opacity"), "rect": ("width", "fill", "opacity"),
        "ellipse":  ("width", "fill", "opacity"), "polyline": ("width", "fill", "opacity", "polyhint"),
        "dropper":  ("dropper_all",),
        "select":   ("selops",), "lasso": ("selops",), "contour": ("contourhint",),
        "hand":     ("viewops",), "zoom": ("viewops",), "camera": ("camhint",),
    }

    def __init__(self, canvas, actions):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.canvas = canvas; self.actions = actions
        self.set_margin_start(10); self.set_margin_end(10); self.set_margin_top(8); self.set_margin_bottom(8)
        self.title = Gtk.Label(xalign=0); self.title.add_css_class("heading"); self.append(self.title)
        self.rows = {}
        p = canvas.props

        def row(key, label, widget):
            b = Gtk.Box(spacing=8)
            lb = Gtk.Label(label=label, xalign=0); lb.set_size_request(92, -1)
            b.append(lb); b.append(widget); self.append(b); self.rows[key] = b

        def bind(scale, key, mul=1.0):
            scale.connect("value-changed", lambda w: p.__setitem__(key, w.get_value() * mul))

        kind = Gtk.DropDown.new_from_strings(ae.BRUSH_LABELS)
        kind.connect("notify::selected", lambda w, _p: p.__setitem__("brush_kind", ae.BRUSH_TYPES[w.get_selected()]))
        row("kind", "Pincel", kind)
        self.size_scale = _scale(1, 300, 14); self.size_key = "brush_size"
        self.size_scale.connect("value-changed", lambda w: p.__setitem__(self.size_key, w.get_value()))
        row("size", "Tamaño", self.size_scale)
        hd = _scale(0, 100, 60); hd.connect("value-changed", lambda w: p.__setitem__("hardness", w.get_value() / 100))
        row("hardness", "Dureza", hd)
        op = _scale(1, 100, 100); op.connect("value-changed", lambda w: p.__setitem__("opacity", int(w.get_value() * 2.55)))
        row("opacity", "Opacidad %", op)
        sp = _scale(3, 100, 14); sp.connect("value-changed", lambda w: p.__setitem__("spacing", w.get_value() / 100))
        row("spacing", "Espaciado %", sp)
        sm = _scale(0, 95, 35); sm.connect("value-changed", lambda w: p.__setitem__("smoothing", w.get_value() / 100))
        row("smoothing", "Suavizado %", sm)
        c1 = Gtk.CheckButton(label="Presión → tamaño"); c1.set_active(True)
        c1.connect("toggled", lambda w: p.__setitem__("pressure_size", w.get_active()))
        c2 = Gtk.CheckButton(label="Presión → opacidad")
        c2.connect("toggled", lambda w: p.__setitem__("pressure_opacity", w.get_active()))
        pb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); pb.append(c1); pb.append(c2)
        row("pressure", "Tableta", pb)
        tol = _scale(0, 255, 32, 1); tol.connect("value-changed", lambda w: p.__setitem__("fill_tol", int(w.get_value())))
        row("tol", "Tolerancia", tol)
        gap = _scale(0, 10, 3); gap.connect("value-changed", lambda w: p.__setitem__("fill_gap", int(w.get_value())))
        row("gap", "Cerrar huecos px", gap)
        cont = Gtk.CheckButton(label="Solo región contigua"); cont.set_active(True)
        cont.connect("toggled", lambda w: p.__setitem__("fill_contig", w.get_active())); row("contig", "", cont)
        fa = Gtk.CheckButton(label="Usar todas las capas como límite")
        fa.connect("toggled", lambda w: p.__setitem__("fill_all", w.get_active())); row("fill_all", "", fa)
        rad = Gtk.CheckButton(label="Degradado radial")
        rad.connect("toggled", lambda w: p.__setitem__("grad_radial", w.get_active())); row("radial", "", rad)
        wd = _scale(1, 60, 3); wd.connect("value-changed", lambda w: p.__setitem__("shape_width", w.get_value()))
        row("width", "Grosor", wd)
        fl = Gtk.CheckButton(label="Rellenar forma")
        fl.connect("toggled", lambda w: p.__setitem__("shape_fill", w.get_active())); row("fill", "", fl)
        da = Gtk.CheckButton(label="Muestrear todas las capas"); da.set_active(True)
        da.connect("toggled", lambda w: p.__setitem__("dropper_all", w.get_active())); row("dropper_all", "", da)

        def hint(text):
            l = Gtk.Label(label=text, xalign=0); l.set_wrap(True); l.add_css_class("dim-label"); return l
        row("polyhint", "", hint("Clic para añadir puntos · Enter cierra · doble Enter o Esc termina."))
        row("contourhint", "", hint("Selecciona un trazo vectorial y arrastra sus puntos. Clic sobre la línea añade un punto; Supr en un punto lo quita."))
        row("camhint", "", hint("Vista Cámara: arrastra para mover, Alt+arrastrar gira, rueda cambia la escala. Cada cambio crea/actualiza una clave en el fotograma."))

        selops = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for label, name in (("Voltear horizontal", "flip_h"), ("Voltear vertical", "flip_v"),
                            ("Girar 90° horario", "rot_cw"), ("Copiar", "copy"), ("Cortar", "cut"),
                            ("Pegar", "paste"), ("Invertir selección", "invert"), ("Borrar", "clear")):
            b = Gtk.Button(label=label); b.connect("clicked", lambda _b, n=name: self.actions(n)); selops.append(b)
        row("selops", "", selops)
        viewops = Gtk.Box(spacing=6)
        for label, name in (("100%", "zoom100"), ("Ajustar", "fit")):
            b = Gtk.Button(label=label); b.connect("clicked", lambda _b, n=name: self.actions(n)); viewops.append(b)
        row("viewops", "", viewops)
        self.show_tool("brush")

    def show_tool(self, tool):
        keys = {k.split(":")[0]: (k.split(":")[1] if ":" in k else None) for k in self.GROUPS.get(tool, ())}
        names = {"brush": "Pincel", "pencil": "Lápiz", "eraser": "Borrador", "smudge": "Dedo", "paint": "Pintar",
                 "gradient": "Degradado", "line": "Línea", "rect": "Rectángulo", "ellipse": "Elipse",
                 "polyline": "Polilínea", "dropper": "Cuentagotas", "select": "Seleccionar",
                 "lasso": "Lazo", "contour": "Editor de contorno", "hand": "Mano", "zoom": "Zoom",
                 "camera": "Cámara"}
        self.title.set_text(names.get(tool, tool))
        for k, b in self.rows.items(): b.set_visible(k in keys)
        if "size" in keys and keys["size"]:
            self.size_key = keys["size"]
            self.size_scale.set_value(self.canvas.props[self.size_key])


# ═════════════════════════ panel de capa ═════════════════════════════════════
class LayerProps(Gtk.Box):
    def __init__(self, canvas, on_change):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.canvas = canvas; self.on_change = on_change; self._sync = False
        for m in ("start", "end", "top", "bottom"): getattr(self, f"set_margin_{m}")(10)
        self.name = Gtk.Entry(); self.name.connect("changed", self._name)
        self.append(Gtk.Label(label="Nombre", xalign=0)); self.append(self.name)
        self.kind = Gtk.Label(xalign=0); self.kind.add_css_class("dim-label"); self.append(self.kind)
        self.append(Gtk.Label(label="Opacidad", xalign=0))
        self.op = _scale(0, 100, 100); self.op.connect("value-changed", self._op); self.append(self.op)
        self.append(Gtk.Label(label="Modo de mezcla", xalign=0))
        self.blend = Gtk.DropDown.new_from_strings(ae.BLEND_MODES)
        self.blend.connect("notify::selected", self._blend); self.append(self.blend)
        self.alock = Gtk.CheckButton(label="Bloquear transparencia (pintar solo lo dibujado)")
        self.alock.connect("toggled", self._alock); self.append(self.alock)
        self.onion = Gtk.CheckButton(label="Mostrar en papel cebolla")
        self.onion.connect("toggled", self._onion); self.append(self.onion)
        self.refresh()

    def refresh(self):
        c = self.canvas; l = c.layer
        self._sync = True
        self.name.set_text(l.name)
        self.kind.set_text("Capa vectorial (trazos editables)" if l.kind == "vector" else "Capa de dibujo (píxeles)")
        self.op.set_value(round(l.opacity * 100 / 255))
        self.blend.set_selected(ae.BLEND_MODES.index(l.blend) if l.blend in ae.BLEND_MODES else 0)
        self.alock.set_active(l.alpha_locked); self.alock.set_sensitive(l.kind == "raster")
        self.onion.set_active(l.onion)
        self._sync = False

    def _name(self, e):
        if self._sync: return
        self.canvas.layer.name = e.get_text() or "Capa"; self.on_change()

    def _op(self, w):
        if self._sync: return
        self.canvas.layer.opacity = int(w.get_value() * 2.55); self.canvas.queue_draw()

    def _blend(self, w, _p):
        if self._sync: return
        self.canvas.layer.blend = ae.BLEND_MODES[w.get_selected()]; self.canvas.queue_draw()

    def _alock(self, w):
        if not self._sync: self.canvas.layer.alpha_locked = w.get_active()

    def _onion(self, w):
        if not self._sync: self.canvas.layer.onion = w.get_active(); self.on_change()


# ═════════════════════════ color ═════════════════════════════════════════════
class ColorDock(Gtk.Box):
    def __init__(self, canvas, palette, on_palette_change):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.canvas = canvas; self.palette = palette; self.on_palette_change = on_palette_change
        for m in ("start", "end", "top", "bottom"): getattr(self, f"set_margin_{m}")(10)
        top = Gtk.Box(spacing=8)
        self.fgbg = FgBg(on_swap=self.swap); top.append(self.fgbg)
        ent = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.fg_e = Gtk.Entry(); self.bg_e = Gtk.Entry()
        for e in (self.fg_e, self.bg_e): e.set_width_chars(9)
        self.fg_e.connect("activate", lambda e: self._hex(e, False)); self.bg_e.connect("activate", lambda e: self._hex(e, True))
        ent.append(self.fg_e); ent.append(self.bg_e); top.append(ent)
        self.append(top)
        self.picker = ColorPicker(self._picked); self.append(self.picker)
        al = Gtk.Box(spacing=6); al.append(Gtk.Label(label="Alfa"))
        self.alpha = _scale(0, 255, 255); self.alpha.connect("value-changed", self._alpha); al.append(self.alpha)
        self.append(al)
        self.pal = PaletteGrid(palette, self._pal_pick); self.append(self.pal)
        row = Gtk.Box(spacing=4)
        add = Gtk.Button(label="+"); add.set_tooltip_text("Añadir el color a la paleta"); add.connect("clicked", lambda _: self._add())
        rem = Gtk.Button(label="−"); rem.set_tooltip_text("Quitar el color seleccionado"); rem.connect("clicked", lambda _: self._remove())
        row.append(add); row.append(rem); self.append(row)
        self.set_colors(canvas.fg, canvas.bg)

    def set_colors(self, fg, bg):
        self.canvas.fg, self.canvas.bg = tuple(fg), tuple(bg)
        self.fgbg.set_colors(tuple(fg), tuple(bg))
        self.fg_e.set_text("#%02x%02x%02x" % tuple(fg[:3])); self.bg_e.set_text("#%02x%02x%02x" % tuple(bg[:3]))
        self.picker.set_rgba(tuple(fg))
        self._sync_alpha = True; self.alpha.set_value(fg[3]); self._sync_alpha = False

    def swap(self):
        self.set_colors(self.canvas.bg, self.canvas.fg)

    def _hex(self, e, bg):
        t = e.get_text().strip().lstrip("#")
        if len(t) == 6:
            try: c = tuple(int(t[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
            except ValueError: return
            (self.set_colors(self.canvas.fg, c) if bg else self.set_colors(c, self.canvas.bg))

    def _picked(self, c):
        self.set_colors((c[0], c[1], c[2], self.canvas.fg[3]), self.canvas.bg)

    def _alpha(self, w):
        if getattr(self, "_sync_alpha", False): return
        f = self.canvas.fg
        self.canvas.fg = (f[0], f[1], f[2], int(w.get_value())); self.fgbg.set_colors(self.canvas.fg, self.canvas.bg)

    def _pal_pick(self, color, right):
        if right: self.set_colors(self.canvas.fg, color)
        else: self.set_colors(color, self.canvas.bg)

    def _add(self):
        c = tuple(self.canvas.fg)
        if c not in self.palette: self.palette.append(c)
        self.pal.set_colors(self.palette); self.on_palette_change()

    def _remove(self):
        i = self.pal.sel
        if 0 <= i < len(self.palette) and len(self.palette) > 1:
            self.palette.pop(i); self.pal.sel = -1; self.pal.set_colors(self.palette); self.on_palette_change()


# ═════════════════════════ cámara ════════════════════════════════════════════
class CameraDock(Gtk.Box):
    def __init__(self, canvas):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.canvas = canvas; self._sync = False
        for m in ("start", "end", "top", "bottom"): getattr(self, f"set_margin_{m}")(10)
        self.spins = {}
        for label, key, lo, hi, step, digits in (("Traslación X", "tx", -4000, 4000, 1, 0), ("Traslación Y", "ty", -4000, 4000, 1, 0),
                                                  ("Escala", "scale", 0.05, 10, 0.05, 2), ("Rotación °", "rot", -360, 360, 1, 1)):
            r = Gtk.Box(spacing=8); l = Gtk.Label(label=label, xalign=0); l.set_size_request(96, -1); r.append(l)
            sp = Gtk.SpinButton.new_with_range(lo, hi, step); sp.set_digits(digits); sp.set_hexpand(True)
            sp.connect("value-changed", lambda w, k=key: self._edit(k, w.get_value()))
            self.spins[key] = sp; r.append(sp); self.append(r)
        btns = Gtk.Box(spacing=6)
        for label, cb in (("Crear clave", canvas.camera_key), ("Borrar clave", canvas.camera_remove_key),
                          ("Reiniciar", canvas.camera_reset)):
            b = Gtk.Button(label=label); b.connect("clicked", lambda _b, f=cb: (f(), self.refresh())); btns.append(b)
        self.append(btns)
        self.info = Gtk.Label(xalign=0); self.info.set_wrap(True); self.info.add_css_class("dim-label"); self.append(self.info)
        self.refresh()

    def refresh(self):
        c = self.canvas
        cam = c.scene.camera_at(c.cur)
        self._sync = True
        for k, sp in self.spins.items(): sp.set_value(cam[k])
        keys = sorted(c.scene.cam_keys)
        self.info.set_text(("Claves de cámara en los fotogramas: " + ", ".join(str(k + 1) for k in keys))
                           if keys else "Sin claves: la cámara está quieta. Cambia un valor para crear una clave.")
        self._sync = False

    def _edit(self, key, val):
        if self._sync: return
        c = self.canvas
        cam = dict(c.scene.camera_at(c.cur)); cam[key] = val
        if c.cur not in c.scene.cam_keys: c.scene.snap()
        c.scene.cam_keys[c.cur] = {k: float(cam[k]) for k in ae.CAM_DEFAULT}
        c._changed()
