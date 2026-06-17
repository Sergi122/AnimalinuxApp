"""
Editor de sprites FRAME POR FRAME (ventana gráfica).

Lienzo con papel cebolla (ves el cuadro anterior en transparencia), línea de
tiempo para añadir/duplicar/borrar/mover cuadros, controles para posar cada
cuadro (mover/rotar/escalar/voltear), importar un dibujo en un cuadro,
reproducir la animación, validar y guardar como pose.
"""
import io

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

from .framedit import FrameModel

POSES = ["default", "walk", "idle", "greet", "jump", "angry"]


def _pil_to_surface(pil):
    buf = io.BytesIO()
    pil.save(buf, "PNG")
    buf.seek(0)
    return cairo.ImageSurface.create_from_png(buf)


class FrameEditor(Gtk.ApplicationWindow):
    def __init__(self, app, anim_id, guided=False):
        super().__init__(application=app, title="Editor de sprites (frame por frame)")
        self.app = app
        self.anim_id = anim_id
        self.guided = guided
        self.set_default_size(820, 640)

        fd = app.library.frames_dir(anim_id)
        self.model = FrameModel(fd / "frame_0000.png")
        self.current = 0
        self.playing = False
        self._play_id = None
        self._play_idx = 0
        self._surf_cache = {}

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        for m in ("top", "bottom", "start", "end"):
            getattr(root, f"set_margin_{m}")(10)
        self.set_child(root)

        # ---- columna izquierda: lienzo + timeline ----
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left.set_hexpand(True)
        self.area = Gtk.DrawingArea()
        self.area.set_vexpand(True)
        self.area.set_draw_func(self._draw)
        left.append(self.area)

        # línea de tiempo
        self.timeline = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tl_scroll = Gtk.ScrolledWindow()
        tl_scroll.set_child(self.timeline)
        tl_scroll.set_min_content_height(56)
        left.append(tl_scroll)

        tl_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        for label, cb in [("➕ Añadir", self._add), ("⧉ Duplicar", self._dup),
                          ("🗑 Borrar", self._del), ("◀", self._left),
                          ("▶", self._right), ("🖼 Importar dibujo", self._import)]:
            b = Gtk.Button(label=label)
            b.connect("clicked", cb)
            tl_btns.append(b)
        left.append(tl_btns)
        root.append(left)

        # ---- columna derecha: controles ----
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_size_request(240, -1)

        self.play_btn = Gtk.ToggleButton(label="▶ Reproducir")
        self.play_btn.connect("toggled", self._toggle_play)
        right.append(self.play_btn)

        right.append(Gtk.Label(label="Cuadro actual:", xalign=0))
        self.dx = self._spin(right, "Mover X", -300, 300, 0)
        self.dy = self._spin(right, "Mover Y", -300, 300, 0)
        self.angle = self._spin(right, "Rotar °", -180, 180, 0)
        self.scale = self._spin(right, "Escala %", 20, 400, 100)
        self.flip = Gtk.CheckButton(label="Voltear horizontal")
        self.flip.connect("toggled", self._apply)
        right.append(self.flip)

        right.append(Gtk.Separator())
        right.append(Gtk.Label(label="Guardar como pose:", xalign=0))
        self.pose_dd = Gtk.DropDown.new_from_strings(POSES)
        self.pose_dd.connect("notify::selected", lambda *_: self._update_tips())
        right.append(self.pose_dd)
        self.fps = self._spin(right, "fps", 1, 30, 8)

        # panel de tips de animación (guía)
        self.tips_label = Gtk.Label(label="", xalign=0, wrap=True)
        self.tips_label.add_css_class("dim-label")
        right.append(self.tips_label)

        val = Gtk.Button(label="Validar (revisar)")
        val.connect("clicked", self._validate)
        right.append(val)
        save = Gtk.Button(label="Guardar pose")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._save)
        right.append(save)

        self.status = Gtk.Label(label="", xalign=0, wrap=True)
        self.status.add_css_class("dim-label")
        right.append(self.status)
        root.append(right)

        self._rebuild_timeline()
        self._load_controls()
        if self.guided:
            self._start_guided()
        self._update_tips()

    def _start_guided(self):
        """En modo guiado, apunta a la siguiente acción que falta por crear."""
        from . import tips
        done = self.app.library.animations.get(self.anim_id, {}).get(
            "poses", ["default"])
        nxt = tips.next_missing(done) or "walk"
        if nxt in POSES:
            self.pose_dd.set_selected(POSES.index(nxt))

    def _update_tips(self):
        from . import tips
        pose = POSES[self.pose_dd.get_selected()]
        t = tips.tip_for(pose)
        txt = f"🎬 {t['titulo']}  (~{t['frames']} cuadros)\n"
        txt += "\n".join("• " + s for s in t["tips"])
        if self.guided:
            txt += "\n\nConsejo: crea esta acción, pulsa «Guardar pose» y sigue con la próxima."
        self.tips_label.set_text(txt)

    # ---- helpers UI ----
    def _spin(self, parent, label, lo, hi, val):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(Gtk.Label(label=label))
        sp = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=val, lower=lo, upper=hi,
                                      step_increment=1))
        sp.connect("value-changed", self._apply)
        row.append(sp)
        parent.append(row)
        return sp

    def _rebuild_timeline(self):
        child = self.timeline.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.timeline.remove(child)
            child = nxt
        for i in range(len(self.model.frames)):
            b = Gtk.ToggleButton(label=str(i + 1))
            b.set_active(i == self.current)
            b.connect("toggled", self._pick, i)
            self.timeline.append(b)

    def _load_controls(self):
        fr = self.model.frames[self.current]
        self._loading = True
        self.dx.set_value(fr["dx"]); self.dy.set_value(fr["dy"])
        self.angle.set_value(fr["angle"]); self.scale.set_value(fr["sx"] * 100)
        self.flip.set_active(fr["flip"])
        self._loading = False
        self.area.queue_draw()

    # ---- callbacks ----
    def _pick(self, btn, i):
        if btn.get_active():
            self.current = i
            self._rebuild_timeline()
            self._load_controls()

    def _apply(self, _w):
        if getattr(self, "_loading", False):
            return
        s = self.scale.get_value() / 100.0
        self.model.set(self.current, dx=self.dx.get_value(),
                       dy=self.dy.get_value(), angle=self.angle.get_value(),
                       sx=s, sy=s, flip=self.flip.get_active())
        self.area.queue_draw()

    def _add(self, _b):
        self.model.add(); self.current = len(self.model.frames) - 1
        self._rebuild_timeline(); self._load_controls()

    def _dup(self, _b):
        self.model.duplicate(self.current); self._rebuild_timeline()

    def _del(self, _b):
        self.model.delete(self.current)
        self.current = min(self.current, len(self.model.frames) - 1)
        self._rebuild_timeline(); self._load_controls()

    def _left(self, _b):
        if self.current > 0:
            self.model.move(self.current, self.current - 1)
            self.current -= 1; self._rebuild_timeline()

    def _right(self, _b):
        if self.current < len(self.model.frames) - 1:
            self.model.move(self.current, self.current + 1)
            self.current += 1; self._rebuild_timeline()

    def _import(self, _b):
        dlg = Gtk.FileDialog(); dlg.set_title("Importar dibujo a este cuadro")
        dlg.open(self, None, self._import_done)

    def _import_done(self, dlg, res):
        try:
            gf = dlg.open_finish(res)
        except GLib.Error:
            return
        self.model.import_drawn(self.current, gf.get_path())
        self._surf_cache.clear()
        self.area.queue_draw()

    def _toggle_play(self, btn):
        self.playing = btn.get_active()
        if self.playing:
            self._play_idx = 0
            interval = int(1000 / max(1, int(self.fps.get_value())))
            self._play_id = GLib.timeout_add(interval, self._play_tick)
        elif self._play_id:
            GLib.source_remove(self._play_id); self._play_id = None
            self.area.queue_draw()

    def _play_tick(self):
        self._play_idx = (self._play_idx + 1) % len(self.model.frames)
        self.area.queue_draw()
        return self.playing

    # ---- dibujo del lienzo ----
    def _frame_surface(self, i, metrics):
        pil = self.model.render_frame(i, metrics)
        return _pil_to_surface(pil)

    def _draw(self, area, cr, width, height):
        metrics = self.model._metrics()
        cw, ch = metrics[0], metrics[1]
        scale = min(width / cw, height / ch) if cw and ch else 1
        ox, oy = (width - cw * scale) / 2, (height - ch * scale) / 2
        # fondo
        cr.set_source_rgb(0.14, 0.14, 0.16)
        cr.rectangle(ox, oy, cw * scale, ch * scale); cr.fill()

        if self.playing:
            idx = self._play_idx
            surf = self._frame_surface(idx, metrics)
            self._paint(cr, surf, ox, oy, scale)
            return
        # papel cebolla: cuadro anterior tenue
        if self.current > 0:
            prev = self._frame_surface(self.current - 1, metrics)
            self._paint(cr, prev, ox, oy, scale, alpha=0.3)
        # cuadro actual
        cur = self._frame_surface(self.current, metrics)
        self._paint(cr, cur, ox, oy, scale)

    def _paint(self, cr, surf, ox, oy, scale, alpha=1.0):
        cr.save()
        cr.translate(ox, oy); cr.scale(scale, scale)
        cr.set_source_surface(surf, 0, 0)
        cr.paint_with_alpha(alpha)
        cr.restore()

    # ---- validar / guardar ----
    def _validate(self, _b):
        self.status.set_text("\n".join(self.model.validate()))

    def _save(self, _b):
        pose = POSES[self.pose_dd.get_selected()]
        fd = self.app.library.frames_dir(self.anim_id)
        try:
            n, w, h = self.model.save_as_pose(fd, pose)
            self.app.register_pose(self.anim_id, pose,
                                   fps=int(self.fps.get_value()))
            msg = f"Pose «{pose}» guardada ({n} cuadros)."
            if self.guided:
                from . import tips
                done = self.app.library.animations.get(self.anim_id, {}).get(
                    "poses", ["default"])
                nxt = tips.next_missing(done)
                if nxt and nxt in POSES:
                    self.pose_dd.set_selected(POSES.index(nxt))
                    self._update_tips()
                    msg += f" Sigue con: {tips.tip_for(nxt)['titulo']}."
                else:
                    msg += " ¡Todas las acciones listas! Pon la mascota en Vida."
            else:
                msg += " Pon la mascota en modo Vida."
            self.status.set_text(msg)
        except Exception as e:  # noqa: BLE001
            self.status.set_text(f"Error al guardar: {e}")
