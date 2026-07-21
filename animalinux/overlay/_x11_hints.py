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
    from gi.repository import GdkX11, GLib
except Exception:  # noqa: BLE001
    GdkX11 = None  # muy improbable (viene con gtk4), pero no debe crashear


_STATE_NAMES = (
    "_NET_WM_STATE_ABOVE",
    "_NET_WM_STATE_SKIP_TASKBAR",
    "_NET_WM_STATE_SKIP_PAGER",
    "_NET_WM_STATE_STICKY",
)


def _x11_window(gtk_window):
    """Resuelve (dpy, win) para la superficie X11 de gtk_window, o None si no
    aplica (Wayland, sin python-xlib, superficie no realizada aún...)."""
    if GdkX11 is None:
        return None
    surface = gtk_window.get_surface()
    if surface is None or not isinstance(surface, GdkX11.X11Surface):
        return None
    try:
        xid = surface.get_xid()
    except Exception:  # noqa: BLE001
        return None
    try:
        from Xlib import display as xlib_display
    except Exception:  # noqa: BLE001
        return None  # python-xlib no instalado: la ventana sigue igual, sin hints
    try:
        dpy = xlib_display.Display()
        win = dpy.create_resource_object("window", xid)
        return dpy, win
    except Exception:  # noqa: BLE001
        return None


def apply_ewmh_hints_early(gtk_window):
    """Pone el TIPO de ventana y otras propiedades que los gestores de
    ventanas solo leen UNA VEZ, al gestionar la ventana por primera vez.

    Se llama en 'realize' (superficie X11 ya creada, pero TODAVÍA no
    mapeada/gestionada por el WM): a diferencia de _NET_WM_STATE, que exige
    ClientMessage tras el mapeo (ver apply_ewmh_hints_late más abajo),
    _NET_WM_WINDOW_TYPE es una propiedad normal que la spec EWMH dice que
    debe escribirse ANTES de mapear. Comprobado en Xfce/xfwm4: si se escribe
    después de mapear (como hacía antes esta función, en 'map'), xfwm4 la
    ignora por completo y dibuja la ventana como NORMAL decorada de tamaño
    fijo — la mascota queda encerrada en esa ventana pequeña en vez de
    ocupar la pantalla completa. Escrita aquí, en 'realize', xfwm4 sí la
    respeta (misma prueba confirma que además dejar de decorar pasa a
    funcionar solo, sin tocar Motif hints a mano). No se ha visto que este
    cambio de timing rompa nada en GNOME/Cinnamon/MATE: son propiedades
    EWMH estándar, honradas por cualquier WM compatible ya sea que se
    escriban antes o después del primer mapeo."""
    resolved = _x11_window(gtk_window)
    if resolved is None:
        return
    dpy, win = resolved
    try:
        from Xlib import Xatom, Xutil

        # _NET_WM_BYPASS_COMPOSITOR: algunos compositores (Muffin en
        # Cinnamon) "unredirigen" automáticamente las ventanas sin decoración
        # que coinciden exactamente con la geometría del monitor, tratándolas
        # como si fueran un juego/vídeo a pantalla completa. Esto rompe el
        # compositing alpha y deja "fantasmas" de lo que hubiera debajo.
        # 2 = never bypass, según la spec EWMH.
        bypass_atom = dpy.intern_atom("_NET_WM_BYPASS_COMPOSITOR")
        win.change_property(bypass_atom, Xatom.CARDINAL, 32, [2])

        # _NET_WM_WINDOW_TYPE_UTILITY: por convención EWMH los gestores de
        # ventanas NO dan foco automático a este tipo (paletas de
        # herramientas), a diferencia de _NET_WM_WINDOW_TYPE_NORMAL (el que
        # pone GTK4 por defecto), que Muffin/Cinnamon SÍ enfoca al mapearla
        # aunque WM_HINTS.input sea False. Sin esto la mascota se lleva el
        # foco de teclado nada más aparecer.
        type_atom = dpy.intern_atom("_NET_WM_WINDOW_TYPE")
        utility_atom = dpy.intern_atom("_NET_WM_WINDOW_TYPE_UTILITY")
        win.change_property(type_atom, Xatom.ATOM, 32, [utility_atom])

        # _NET_WM_STATE antes de mapear: propiedad normal (no ClientMessage),
        # válida según la spec para ventanas todavía "withdrawn". Es un
        # refuerzo temprano; apply_ewmh_hints_late la reafirma tras el mapeo
        # por si el WM la ignora en esta fase (ocurre en algunos gestores).
        state_atom = dpy.intern_atom("_NET_WM_STATE")
        state_atoms = [dpy.intern_atom(name) for name in _STATE_NAMES]
        win.change_property(state_atom, Xatom.ATOM, 32, state_atoms)

        # WM_HINTS.input = False (ICCCM): la mascota es un overlay decorativo,
        # click-through, sin barra de título; nunca debe robar el foco de
        # teclado. GTK4 no expone un setter para esto y por defecto deja
        # input=True, así que el gestor de ventanas le da foco al mapearla,
        # dejando el teclado "muerto" para el resto del escritorio (parece
        # que la pantalla se congela) hasta que el usuario hace clic en otra
        # ventana. Se preservan flags/campos ya puestos por GTK (p.ej.
        # window_group) y solo se apaga el input.
        try:
            hints = win.get_wm_hints()
            hints.input = 0
            hints.flags |= Xutil.InputHint
            win.set_wm_hints(hints)
        except Exception:  # noqa: BLE001
            pass

        dpy.flush()
    except Exception:  # noqa: BLE001
        pass


def apply_ewmh_hints_late(gtk_window):
    """Refuerza always-on-top / skip-taskbar / skip-pager / sticky tras
    'map' (la ventana ya visible/gestionada por el WM): el protocolo EWMH
    exige mandar un ClientMessage _NET_WM_STATE a la raíz para cambiar el
    estado de una ventana YA mapeada; escribir la propiedad directamente en
    este punto no basta, la mayoría de gestores (xfwm4 incluido) la ignoran
    o la sobrescriben al tomar la ventana bajo su gestión. El tipo de
    ventana y demás hints "de una sola vez" van en apply_ewmh_hints_early."""
    resolved = _x11_window(gtk_window)
    if resolved is None:
        return
    dpy, win = resolved
    try:
        from Xlib import X
        from Xlib.protocol import event as xlib_event

        root = dpy.screen().root
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

        _revert_focus()

        dpy.flush()
    except Exception:  # noqa: BLE001
        pass


def _revert_focus():
    """Muffin (Cinnamon) foca las ventanas normales nuevas AL MAPEARLAS,
    ignorando WM_HINTS.input y el tipo de ventana (ese campo solo evita el
    foco por click, no el foco automático al aparecer). Y lo hace de forma
    ASÍNCRONA tras procesar el MapNotify, así que devolver el foco una sola
    vez, en el mismo instante en que mandamos los hints, pierde la carrera:
    Muffin lo pisa un instante después. Por eso reintentamos varias veces con
    pequeños retrasos, hasta ganarle la carrera de forma fiable, sin importar
    cuánto tarde su gestor de foco en reaccionar."""
    try:
        from Xlib import X
        from Xlib import display as xlib_display
    except Exception:  # noqa: BLE001
        return

    def go():
        try:
            d = xlib_display.Display()
            d.set_input_focus(X.PointerRoot, X.RevertToPointerRoot, X.CurrentTime)
            d.flush()
            d.close()
        except Exception:  # noqa: BLE001
            pass
        return False

    go()
    for delay_ms in (30, 80, 150, 300, 600):
        GLib.timeout_add(delay_ms, go)
