"""Liberación de ventanas al cerrarlas.

PyGObject no libera una ventana si algún widget hijo tiene una señal conectada a
un método suyo (ciclo ventana → widget → cierre → ventana que pasa por GTK y el
recolector de Python no ve). Al cerrar se destruyen todos los manejadores de
señales del árbol de widgets, sus controladores de eventos y las acciones."""
import types

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GObject, Gtk


def _walk(w):
    yield w
    for ctl in list(w.observe_controllers()):
        yield ctl
    c = w.get_first_child()
    while c is not None:
        yield from _walk(c)
        c = c.get_next_sibling()


def release_signals(window, groups=()):
    for o in list(_walk(window)):
        GObject.signal_handlers_destroy(o)
        if isinstance(o, Gtk.DrawingArea):
            o.set_draw_func(None)                    # la función de dibujo también retiene la ventana
        for k, v in list(vars(o).items()):          # callbacks guardados en nuestros widgets
            if isinstance(v, (types.MethodType, types.FunctionType)):
                setattr(o, k, None)
    for grp in groups:
        for name in grp.list_actions():
            GObject.signal_handlers_destroy(grp.lookup_action(name))
