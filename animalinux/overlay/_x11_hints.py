"""
Hints EWMH para el backend X11 (GNOME, Cinnamon, MATE, Xfce...).

GTK4 quitó los setters cómodos que existían en GTK3 (set_keep_above,
set_type_hint, stick). Para lograr "siempre encima, fuera de la barra de
tareas, en todos los escritorios" hay que escribir las propiedades EWMH
directamente sobre el XID de la ventana, vía python-xlib. Todo va envuelto
en try/except: si algo falla (WM no EWMH, falta python-xlib...) la ventana
sigue funcionando, solo pierde el barniz de "siempre encima".
"""
try:
    import gi

    gi.require_version("GdkX11", "4.0")
    from gi.repository import GdkX11
except Exception:  # noqa: BLE001
    GdkX11 = None  # muy improbable (viene con gtk4), pero no debe crashear


_STATE_NAMES = (
    "_NET_WM_STATE_ABOVE",
    "_NET_WM_STATE_SKIP_TASKBAR",
    "_NET_WM_STATE_SKIP_PAGER",
    "_NET_WM_STATE_STICKY",
)


def apply_ewmh_hints(gtk_window):
    """Marca la ventana como always-on-top / skip-taskbar / skip-pager /
    sticky. Se llama tras 'map' (la ventana ya visible/gestionada por el WM):
    el protocolo EWMH exige mandar un ClientMessage _NET_WM_STATE a la raíz
    una vez mapeada; escribir la propiedad directamente NO basta, la mayoría
    de gestores (xfwm4 incluido, comprobado con Xvfb) la ignoran o la
    sobrescriben al tomar la ventana bajo su gestión."""
    if GdkX11 is None:
        return
    surface = gtk_window.get_surface()
    if surface is None or not isinstance(surface, GdkX11.X11Surface):
        return
    try:
        xid = surface.get_xid()
    except Exception:  # noqa: BLE001
        return
    try:
        from Xlib import X
        from Xlib import display as xlib_display
        from Xlib.protocol import event as xlib_event
    except Exception:  # noqa: BLE001
        return  # python-xlib no instalado: la ventana sigue igual, sin hints
    try:
        dpy = xlib_display.Display()
        root = dpy.screen().root
        win = dpy.create_resource_object("window", xid)
        state_atom = dpy.intern_atom("_NET_WM_STATE")
        add = 1  # _NET_WM_STATE_ADD
        source_app = 1  # source indication: aplicación normal
        mask = X.SubstructureRedirectMask | X.SubstructureNotifyMask
        for name in _STATE_NAMES:
            atom = dpy.intern_atom(name)
            ev = xlib_event.ClientMessage(
                window=win, client_type=state_atom,
                data=(32, (add, atom, 0, source_app, 0)),
            )
            root.send_event(ev, event_mask=mask)
        dpy.flush()
    except Exception:  # noqa: BLE001
        pass
