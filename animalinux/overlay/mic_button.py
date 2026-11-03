"""
Botón de micrófono flotante (hablar con la mascota).

  clic izquierdo   escucha una frase (o abre «escribir» si no hay voz)
  clic derecho     escribirle en vez de hablar
  arrastrar        moverlo; la posición se guarda

Es una ventanita redonda de 56 px siempre encima: layer-shell en Wayland
(como las mascotas), EWMH «utility + above» en X11 y WS_EX_TOPMOST en Windows.
Mientras escucha late en rojo (animación a 30 fps solo en ese estado; en
reposo no hay temporizador).
"""
import math
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import settings  # noqa: E402
from ..i18n import tr  # noqa: E402
from . import BACKEND  # noqa: E402

SIZE = 56
MARGIN = 24


class MicButton(Gtk.Window):
    def __init__(self, brain):
        super().__init__(title="AnimaLinux mic")
        self.brain = brain
        self._state = "idle"
        self._anim_id = 0
        self._t0 = time.monotonic()
        self._hover = False
        self._drag_from = None
        self._moved = False
        pos = settings.get("talk_btn_pos")
        pos = pos if isinstance(pos, dict) else {}
        try:
            self._mx = max(0, min(4000, int(pos.get("right", MARGIN))))   # al borde derecho
            self._my = max(0, min(4000, int(pos.get("bottom", MARGIN + 60))))
        except (TypeError, ValueError):
            self._mx, self._my = MARGIN, MARGIN + 60
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(SIZE, SIZE)
        self.add_css_class("animalinux-mic")
        _css(self.get_display())

        area = Gtk.DrawingArea()
        area.set_content_width(SIZE)
        area.set_content_height(SIZE)
        area.set_draw_func(self._draw)
        area.set_tooltip_text(tr("Hablar con tu mascota (clic derecho: escribirle)"))
        self._area = area
        self.set_child(area)

        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect("released", self._on_click)
        area.add_controller(click)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        area.add_controller(drag)
        hov = Gtk.EventControllerMotion()
        hov.connect("enter", lambda *_a: self._set_hover(True))
        hov.connect("leave", lambda *_a: self._set_hover(False))
        area.add_controller(hov)

        self._native_init()

    # ── plataforma ────────────────────────────────────────────────────────
    def _native_init(self):
        if BACKEND == "wayland":
            gi.require_version("Gtk4LayerShell", "1.0")
            from gi.repository import Gtk4LayerShell as LS
            self._ls = LS
            LS.init_for_window(self)
            LS.set_layer(self, LS.Layer.OVERLAY)
            LS.set_namespace(self, "animalinux-mic")
            LS.set_anchor(self, LS.Edge.RIGHT, True)
            LS.set_anchor(self, LS.Edge.BOTTOM, True)
            LS.set_exclusive_zone(self, -1)
            LS.set_keyboard_mode(self, LS.KeyboardMode.NONE)
            self._apply_pos()
        elif BACKEND == "x11":
            from . import _x11_hints as xh
            self._x = None                 # (display, ventana) de Xlib, una sola conexión
            self.connect("realize", lambda *_a: xh.apply_ewmh_hints_early(self))
            self.connect("map", self._on_map_x11)
        else:
            self.connect("map", lambda *_a: GLib.idle_add(self._win32_init))

    def _on_map_x11(self, *_a):
        from . import _x11_hints as xh
        xh.apply_ewmh_hints_late(self)
        # GTK/el gestor de ventanas pueden recolocarla justo después de
        # mostrarla: se reaplica la posición un par de veces
        for ms in (0, 250, 1000):
            GLib.timeout_add(ms, self._apply_pos)

    def _win32_init(self):
        try:
            from ..backends.windows import win32
            h = win32.hwnd_from_gtk(self)
            if h:
                win32.make_overlay_window(h)
                self._hwnd = h
                self._apply_pos()
        except Exception:  # noqa: BLE001
            pass
        return False

    def _monitor_geom(self):
        disp = self.get_display() or Gdk.Display.get_default()
        mons = disp.get_monitors()
        mon = mons.get_item(0) if mons.get_n_items() else None
        if mon is None:
            return 0, 0, 1920, 1080
        g = mon.get_geometry()
        return g.x, g.y, g.width, g.height

    def _apply_pos(self):
        if BACKEND == "wayland":
            self._ls.set_margin(self, self._ls.Edge.RIGHT, self._mx)
            self._ls.set_margin(self, self._ls.Edge.BOTTOM, self._my)
            return False
        gx, gy, gw, gh = self._monitor_geom()
        x, y = gx + gw - SIZE - self._mx, gy + gh - SIZE - self._my
        if BACKEND == "x11":
            from . import _x11_hints as xh
            if self._x is None:
                self._x = xh._x11_window(self)      # abre UNA conexión y se reusa
            if self._x is not None:
                dpy, win = self._x
                try:
                    win.configure(x=int(x), y=int(y))
                    dpy.flush()
                except Exception:  # noqa: BLE001
                    pass
        elif getattr(self, "_hwnd", None):
            from ..backends.windows import win32
            k = win32.system_scale()
            win32.move_window(self._hwnd, x * k, y * k)
        return False

    def do_unrealize(self):
        x = getattr(self, "_x", None)
        if x is not None:
            try:
                x[0].close()
            except Exception:  # noqa: BLE001
                pass
            self._x = None
        Gtk.Window.do_unrealize(self)

    # ── estado ────────────────────────────────────────────────────────────
    def set_state(self, st):
        if st == self._state:
            return
        self._state = st
        self._t0 = time.monotonic()
        if st != "idle" and not self._anim_id:
            self._anim_id = GLib.timeout_add(33, self._tick)
        self._area.queue_draw()

    def _tick(self):
        if self._state == "idle":
            self._anim_id = 0
            self._area.queue_draw()
            return False
        self._area.queue_draw()
        return True

    def _set_hover(self, on):
        self._hover = on
        self._area.queue_draw()

    # ── entrada ───────────────────────────────────────────────────────────
    def _on_click(self, gesture, _n, _x, _y):
        if self._moved:
            return
        if gesture.get_current_button() == 3:
            self.brain.open_type()
        else:
            self.brain.ask()

    def _on_drag_begin(self, _g, _x, _y):
        self._drag_from = (self._mx, self._my)
        self._moved = False

    def _on_drag_update(self, _g, dx, dy):
        if self._drag_from is None:
            return
        if abs(dx) + abs(dy) > 6:
            self._moved = True
        if self._moved:
            _gx, _gy, gw, gh = self._monitor_geom()
            self._mx = int(min(max(0, self._drag_from[0] - dx), gw - SIZE))
            self._my = int(min(max(0, self._drag_from[1] - dy), gh - SIZE))
            self._apply_pos()
            # la ventana se movió bajo el puntero: el siguiente delta del
            # gesto se mide desde la ventana ya movida
            self._drag_from = (self._mx + dx, self._my + dy)

    def _on_drag_end(self, *_a):
        if self._moved:
            settings.set_val("talk_btn_pos", {"right": self._mx, "bottom": self._my})
            GLib.timeout_add(50, self._clear_moved)
        self._drag_from = None

    def _clear_moved(self):
        self._moved = False
        return False

    # ── dibujo ────────────────────────────────────────────────────────────
    def _draw(self, _area, cr, w, h):
        t = time.monotonic() - self._t0
        cx, cy = w / 2, h / 2
        r = min(w, h) / 2 - 6
        listening = self._state == "listen"
        if listening:
            # anillos que se expanden
            for i in range(2):
                p = ((t * 0.9) + i * 0.5) % 1.0
                cr.arc(cx, cy, r + 1 + p * 6, 0, 2 * math.pi)
                cr.set_source_rgba(0.95, 0.30, 0.35, 0.45 * (1 - p))
                cr.set_line_width(2.5)
                cr.stroke()
        # sombra
        cr.arc(cx + 1, cy + 2, r, 0, 2 * math.pi)
        cr.set_source_rgba(0, 0, 0, 0.25)
        cr.fill()
        # cuerpo
        import cairo
        g = cairo.LinearGradient(0, cy - r, 0, cy + r)
        if listening:
            g.add_color_stop_rgb(0, 0.98, 0.42, 0.45)
            g.add_color_stop_rgb(1, 0.82, 0.18, 0.26)
        else:
            k = 0.08 if self._hover else 0.0
            g.add_color_stop_rgb(0, 0.52 + k, 0.47 + k, 0.98)
            g.add_color_stop_rgb(1, 0.33 + k, 0.27 + k, 0.82)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source(g)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.35)
        cr.set_line_width(1.2)
        cr.stroke()
        # micrófono
        cr.set_source_rgb(1, 1, 1)
        mw, mh = r * 0.36, r * 0.62
        top = cy - r * 0.48
        _round_rect(cr, cx - mw / 2, top, mw, mh, mw / 2)
        cr.fill()
        cr.set_line_width(max(1.8, r * 0.09))
        cr.arc(cx, top + mh * 0.62, r * 0.36, 0.1 * math.pi, 0.9 * math.pi)
        cr.stroke()
        cr.move_to(cx, top + mh * 0.62 + r * 0.36)
        cr.line_to(cx, cy + r * 0.52)
        cr.stroke()
        cr.move_to(cx - r * 0.2, cy + r * 0.52)
        cr.line_to(cx + r * 0.2, cy + r * 0.52)
        cr.stroke()


def _round_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


_CSS_DONE = False


def _css(display):
    global _CSS_DONE
    if _CSS_DONE or display is None:
        return
    p = Gtk.CssProvider()
    css = ("window.animalinux-mic, window.animalinux-mic * {"
           " background: transparent; background-color: transparent;"
           " background-image: none; box-shadow: none; border: none; }")
    if hasattr(p, "load_from_string"):
        p.load_from_string(css)
    else:
        p.load_from_data(css.encode())
    # el tema de la app va en PRIORITY_USER: hay que ganarle (como las mascotas)
    Gtk.StyleContext.add_provider_for_display(display, p, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
    _CSS_DONE = True
