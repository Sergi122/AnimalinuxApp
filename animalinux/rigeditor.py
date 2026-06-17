"""
Editor visual de PARTES (rig). Muestra la imagen de la mascota y dejas marcar,
arrastrando el mouse, dónde está cada parte: cabeza, torso, brazos y piernas.
Luego genera las poses articuladas con puppet.py.

Eliges una parte en el desplegable y arrastras un rectángulo sobre la imagen.
Repites por cada parte. «Generar» crea caminar/idle/saludar/saltar articuladas.
"""
import cairo

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402

PARTS = [
    ("torso", "Torso", (0.30, 0.45, 0.95)),
    ("head", "Cabeza", (0.95, 0.75, 0.20)),
    ("arm_l", "Brazo izq.", (0.30, 0.85, 0.40)),
    ("arm_r", "Brazo der.", (0.95, 0.45, 0.30)),
    ("leg_l", "Pierna izq.", (0.45, 0.80, 0.95)),
    ("leg_r", "Pierna der.", (0.95, 0.55, 0.30)),
]
PART_LABELS = [p[1] for p in PARTS]
PART_KEYS = [p[0] for p in PARTS]
PART_COLORS = {p[0]: p[2] for p in PARTS}


class RigEditor(Gtk.ApplicationWindow):
    def __init__(self, app, anim_id):
        super().__init__(application=app, title="Marcar partes del cuerpo")
        self.app = app
        self.anim_id = anim_id
        self.set_default_size(640, 600)

        anim = app.library.animations.get(anim_id, {})
        self.rig = dict(anim.get("rig", {}))

        first = app.library.frames_dir(anim_id) / "frame_0000.png"
        self.surface = None
        self.img_w, self.img_h = 100, 100
        if first.exists():
            try:
                self.surface = cairo.ImageSurface.create_from_png(str(first))
                self.img_w = self.surface.get_width()
                self.img_h = self.surface.get_height()
            except Exception:  # noqa: BLE001
                pass

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for m in ("top", "bottom", "start", "end"):
            getattr(root, f"set_margin_{m}")(12)
        self.set_child(root)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.append(Gtk.Label(label="Parte:"))
        self.part_dd = Gtk.DropDown.new_from_strings(PART_LABELS)
        bar.append(self.part_dd)
        clear = Gtk.Button(label="Borrar esta parte")
        clear.connect("clicked", self._on_clear)
        bar.append(clear)
        root.append(bar)

        hint = Gtk.Label(
            label="Arrastra sobre la imagen para marcar la parte elegida. "
                  "Marca al menos torso, brazos y piernas.", xalign=0)
        hint.add_css_class("dim-label")
        root.append(hint)

        self.area = Gtk.DrawingArea()
        self.area.set_vexpand(True)
        self.area.set_draw_func(self._draw)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", self._drag_end)
        self.area.add_controller(drag)
        root.append(self.area)

        gen = Gtk.Button(label="Generar poses con estas partes ✨")
        gen.add_css_class("suggested-action")
        gen.connect("clicked", self._on_generate)
        root.append(gen)
        self.status = Gtk.Label(label="", xalign=0)
        self.status.add_css_class("dim-label")
        root.append(self.status)

        self._drag_rect = None
        self._start = (0, 0)

    def _fit(self, width, height):
        if self.img_w == 0 or self.img_h == 0:
            return 1.0, 0, 0
        scale = min(width / self.img_w, height / self.img_h)
        return scale, (width - self.img_w * scale) / 2, (height - self.img_h * scale) / 2

    def _to_img(self, sx, sy, w, h):
        scale, ox, oy = self._fit(w, h)
        return ((sx - ox) / scale, (sy - oy) / scale)

    def _draw(self, area, cr, width, height):
        scale, ox, oy = self._fit(width, height)
        # checker suave de fondo
        cr.set_source_rgb(0.16, 0.16, 0.18)
        cr.rectangle(ox, oy, self.img_w * scale, self.img_h * scale)
        cr.fill()
        # imagen de la mascota
        if self.surface:
            cr.save()
            cr.translate(ox, oy)
            cr.scale(scale, scale)
            cr.set_source_surface(self.surface, 0, 0)
            cr.paint()
            cr.restore()
        # rectángulos de las partes
        for key, label, color in PARTS:
            box = self.rig.get(key)
            if not box:
                continue
            x, y, ww, hh = box
            rx, ry, rw, rh = ox + x * scale, oy + y * scale, ww * scale, hh * scale
            cr.set_source_rgba(*color, 0.25); cr.rectangle(rx, ry, rw, rh); cr.fill()
            cr.set_source_rgba(*color, 1); cr.set_line_width(2)
            cr.rectangle(rx, ry, rw, rh); cr.stroke()
            cr.move_to(rx + 3, ry + 14); cr.show_text(label)
        if self._drag_rect:
            x, y, ww, hh = self._drag_rect
            cr.set_source_rgba(1, 1, 1, 0.9); cr.set_line_width(1.5)
            cr.rectangle(ox + x * scale, oy + y * scale, ww * scale, hh * scale)
            cr.stroke()

    def _drag_begin(self, g, sx, sy):
        self._start = self._to_img(sx, sy, self.area.get_width(),
                                   self.area.get_height())

    def _drag_update(self, g, ox, oy):
        scale, _, _ = self._fit(self.area.get_width(), self.area.get_height())
        x0, y0 = self._start
        dx, dy = ox / scale, oy / scale
        self._drag_rect = (min(x0, x0 + dx), min(y0, y0 + dy), abs(dx), abs(dy))
        self.area.queue_draw()

    def _drag_end(self, g, ox, oy):
        if self._drag_rect and self._drag_rect[2] > 4 and self._drag_rect[3] > 4:
            key = PART_KEYS[self.part_dd.get_selected()]
            x, y, ww, hh = self._drag_rect
            self.rig[key] = [int(max(0, x)), int(max(0, y)), int(ww), int(hh)]
            self.app.library.update(self.anim_id, rig=self.rig)
        self._drag_rect = None
        self.area.queue_draw()

    def _on_clear(self, _b):
        key = PART_KEYS[self.part_dd.get_selected()]
        self.rig.pop(key, None)
        self.app.library.update(self.anim_id, rig=self.rig)
        self.area.queue_draw()

    def _on_generate(self, _b):
        if "torso" not in self.rig:
            self.status.set_text("Marca al menos el torso.")
            return
        self.status.set_text("Generando poses articuladas…")
        made = self.app.generate_puppet_poses(self.anim_id, self.rig)
        self.status.set_text("Listo: " + ", ".join(made) +
                             ". Pon la mascota en modo «Vida».")
