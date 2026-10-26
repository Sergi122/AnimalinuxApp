"""
La cancha: una capa transparente del tamaño del monitor que, SOLO durante un
partido, dibuja arcos / red / aros, el balón, el marcador y los avisos, y
recibe el mouse (empujar, hacer clic a tiempo, agarrar y lanzar).

Wayland (Hyprland, Sway, KDE): superficie wlr-layer-shell en la capa OVERLAY
anclada a los cuatro bordes. X11: ventana sin decorar del tamaño del monitor
con los mismos hints EWMH que las mascotas. Las mascotas siguen siendo sus
propias ventanas: la cancha solo pinta lo que no es mascota.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from ..overlay import BACKEND  # noqa: E402

_CSS = False


def supported():
    return BACKEND in ("wayland", "x11")


def _transparent(display):
    global _CSS
    if _CSS:
        return
    prov = Gtk.CssProvider()
    css = ("window.animalinux-pitch, window.animalinux-pitch * {"
           " background: transparent; background-color: transparent;"
           " box-shadow: none; }")
    if hasattr(prov, "load_from_string"):
        prov.load_from_string(css)
    else:
        prov.load_from_data(css.encode())
    Gtk.StyleContext.add_provider_for_display(
        display, prov, Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
    _CSS = True


class PitchWindow(Gtk.Window):
    def __init__(self, app, monitor, geo, handlers):
        """geo = (x, y, w, h) del monitor; handlers: draw(cr, w, h),
        motion(x, y), press(x, y), release(x, y), key(nombre)."""
        super().__init__(application=app)
        self.geo = geo
        self.h = handlers
        self.add_css_class("animalinux-pitch")
        self.set_decorated(False)
        _transparent(self.get_display() or Gdk.Display.get_default())
        _x, _y, w, h = geo
        # tamaño explícito: una ventana no redimensionable o sin tamaño pedido
        # se queda en 200×200 aunque esté anclada a los cuatro bordes
        self.set_default_size(w, h)
        self.set_size_request(w, h)
        if BACKEND == "wayland":
            from gi.repository import Gtk4LayerShell as LS
            LS.init_for_window(self)
            LS.set_layer(self, LS.Layer.OVERLAY)
            LS.set_namespace(self, "animalinux-pitch")
            if monitor is not None:
                LS.set_monitor(self, monitor)
            for e in (LS.Edge.LEFT, LS.Edge.RIGHT, LS.Edge.TOP, LS.Edge.BOTTOM):
                LS.set_anchor(self, e, True)
                LS.set_margin(self, e, 0)
            LS.set_exclusive_zone(self, -1)
            LS.set_keyboard_mode(self, LS.KeyboardMode.ON_DEMAND)
        else:
            from ..overlay import _x11_hints
            self.set_default_size(w, h + 1)
            self.set_size_request(w, h + 1)
            self.connect("realize", lambda *_: _x11_hints.apply_ewmh_hints_early(self))
            self.connect("map", lambda *_: (_x11_hints.apply_ewmh_hints_late(self),
                                            GLib.idle_add(self._move_x11)))

        self.area = Gtk.DrawingArea()
        self.area.set_hexpand(True)
        self.area.set_vexpand(True)
        self.area.set_draw_func(lambda _a, cr, aw, ah: self.h["draw"](cr, aw, ah))
        self.set_child(self.area)

        mot = Gtk.EventControllerMotion()
        mot.connect("motion", lambda _c, x, y: self.h["motion"](x, y))
        self.add_controller(mot)
        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect("pressed", lambda g, n, x, y: self.h["press"](x, y, g.get_current_button()))
        click.connect("released", lambda g, n, x, y: self.h["release"](x, y, g.get_current_button()))
        self.add_controller(click)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", lambda _c, kv, _kc, _m: self.h["key"](Gdk.keyval_name(kv)) or False)
        self.add_controller(keys)

    def _move_x11(self):
        from ..overlay import _x11_hints
        r = _x11_hints._x11_window(self)
        if r is not None:
            dpy, win = r
            try:
                win.configure(x=int(self.geo[0]), y=int(self.geo[1]))
                dpy.flush()
            except Exception:  # noqa: BLE001
                pass
        return False

    def redraw(self):
        self.area.queue_draw()
