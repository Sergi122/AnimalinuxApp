"""
Hints EWMH para el backend X11 (GNOME, Cinnamon, MATE, Xfce...).

GTK4 quitó los setters cómodos que existían en GTK3 (set_keep_above,
set_type_hint, stick). Para lograr "siempre encima, fuera de la barra de
tareas, en todos los escritorios" hay que escribir las propiedades EWMH
directamente sobre el XID de la ventana, vía python-xlib. Todo va envuelto
en try/except: si algo falla (WM no EWMH, falta python-xlib...) la ventana
sigue funcionando, solo pierde el barniz de "siempre encima".
"""
import os

try:
    import gi

    gi.require_version("GdkX11", "4.0")
    from gi.repository import GdkX11, GLib
except Exception:  # noqa: BLE001
    GdkX11 = None  # muy improbable (viene con gtk4), pero no debe crashear

from .. import settings


_STATE_NAMES = (
    "_NET_WM_STATE_ABOVE",
    "_NET_WM_STATE_SKIP_TASKBAR",
    "_NET_WM_STATE_SKIP_PAGER",
    "_NET_WM_STATE_STICKY",
)


def _reasserts_wm_hints_on_map() -> bool:
    """¿El WM de este escritorio reescribe WM_HINTS a sus valores por
    defecto (input=True) cuando GTK mapea la ventana, descartando lo que
    apply_ewmh_hints_early escribió en 'realize'?

    install.sh detecta el escritorio y guarda el resultado en
    ~/.config/animalinux/settings.json (clave "desktop_env"). Comprobado con
    xprop en vivo: Cinnamon/Muffin SÍ lo hace (WM_HINTS.input vuelve a 1 tras
    el map, y el foco de teclado acaba fijo en la ventana-proxy interna de
    GDK del propio overlay una vez que se agotan los reintentos de
    _revert_focus — reproduce el "se congela la pantalla" original); Xfce/
    xfwm4 NO lo hace, honra tal cual lo escrito en 'realize'. Si no hay
    valor guardado (instalación manual sin install.sh, escritorio no
    reconocido...) se asume que SÍ hace falta reafirmar: es el caso seguro
    para todos los probados salvo Xfce, donde reafirmarlo de más no hace
    ningún daño."""
    env = settings.get("desktop_env", None) or os.environ.get(
        "XDG_CURRENT_DESKTOP", ""
    ).lower()
    return "xfce" not in env


def _set_input_false(win):
    """WM_HINTS.input = False (ICCCM): la mascota es un overlay decorativo,
    click-through, sin barra de título; nunca debe robar el foco de teclado.
    GTK4 no expone un setter para esto y por defecto deja input=True. Se
    preservan flags/campos ya puestos por GTK (p.ej. window_group) y solo se
    apaga el input."""
    try:
        from Xlib import Xutil

        hints = win.get_wm_hints()
        hints.input = 0
        hints.flags |= Xutil.InputHint
        win.set_wm_hints(hints)
    except Exception:  # noqa: BLE001
        pass


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
        from Xlib import Xatom

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

        # WM_HINTS.input = False: ver _set_input_false. Si el gestor de
        # ventanas le da foco al mapearla de todos modos (Muffin, Mutter,
        # Marco...), dejando el teclado "muerto" para el resto del
        # escritorio, apply_ewmh_hints_late lo reafirma tras el mapeo — ver
        # _reasserts_wm_hints_on_map.
        _set_input_false(win)

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

        # En Cinnamon/GNOME/MATE (Muffin/Mutter/Marco) GTK reescribe
        # WM_HINTS a su valor por defecto (input=True) en algún punto de su
        # propio present()/map, descartando en silencio lo que
        # apply_ewmh_hints_early escribió en 'realize' — confirmado en vivo
        # con xprop. Sin reafirmarlo aquí, el foco de teclado acaba fijo en
        # la ventana-proxy interna de GDK del propio overlay una vez que
        # _revert_focus agota sus reintentos. Xfce/xfwm4 no lo necesita
        # (_reasserts_wm_hints_on_map lo sabe vía el "desktop_env" que
        # guardó install.sh), pero reafirmarlo de más ahí es inofensivo.
        reassert_xid = win.id if _reasserts_wm_hints_on_map() else None
        _revert_focus(reassert_xid)

        dpy.flush()
    except Exception:  # noqa: BLE001
        pass


def install_focus_guard(gtk_window):
    """Contraataca CADA VEZ que el WM le da foco a la mascota, en el mismo
    ciclo del bucle de eventos, en vez de pelear a ciegas con reintentos por
    tiempo (ver _revert_focus): medido en vivo en Marco (MATE) con
    xprop/Xlib, tras cada corrección por tiempo el WM le reafirma el foco de
    nuevo en menos de ~20ms — un sondeo a intervalos, por denso que sea,
    siempre deja huecos donde gana el WM antes del próximo intento (visto en
    vivo: con reintentos cada 40ms, el foco quedaba robado en más del 90% de
    las muestras). Seleccionando FocusChangeMask
    sobre la ventana (y su _NET_WM_USER_TIME_WINDOW, adonde GDK a veces
    redirige el foco X real — confirmado en vivo, es el destino más común
    del robo) reaccionamos apenas llega el FocusIn, sin ese hueco.

    Seguro de dejar instalado para toda la vida de la ventana: NO fuerza
    nada de forma continua ni interfiere con el foco de ninguna otra
    ventana — solo reacciona si ESTA ventana en concreto llega a tener el
    foco, que con WM_HINTS.input=False + tipo UTILITY no debería pasar
    nunca de forma legítima."""
    resolved = _x11_window(gtk_window)
    if resolved is None:
        return
    dpy, win = resolved
    try:
        from Xlib import X

        watched = [win]
        prop = win.get_full_property(
            dpy.intern_atom("_NET_WM_USER_TIME_WINDOW"), 0)
        if prop and prop.value:
            watched.append(dpy.create_resource_object("window", prop.value[0]))
        for w in watched:
            w.change_attributes(event_mask=X.FocusChangeMask)
        dpy.flush()

        reassert_xid = win.id if _reasserts_wm_hints_on_map() else None

        def on_readable(_channel, _condition):
            try:
                while dpy.pending_events():
                    ev = dpy.next_event()
                    if ev.type == X.FocusIn:
                        dpy.set_input_focus(
                            X.PointerRoot, X.RevertToPointerRoot, X.CurrentTime)
                        if reassert_xid is not None:
                            reasserted = dpy.create_resource_object(
                                "window", reassert_xid)
                            _set_input_false(reasserted)
                        dpy.flush()
            except Exception:  # noqa: BLE001
                pass
            return True  # seguir observando mientras viva la ventana

        channel = GLib.IOChannel.unix_new(dpy.fileno())
        GLib.io_add_watch(channel, GLib.PRIORITY_DEFAULT, GLib.IOCondition.IN,
                           on_readable)
        # mantener viva la conexión Xlib dedicada (si el GC se la lleva, el
        # fd bajo el io_add_watch deja de existir y GLib empieza a fallar)
        gtk_window._focus_guard_dpy = dpy
    except Exception:  # noqa: BLE001
        pass


def _revert_focus(reassert_input_xid=None):
    """Reafirma el foco tras el MAPEO inicial (ver apply_ewmh_hints_late):
    Muffin/Marco (Cinnamon/MATE) puede enfocar la ventana de la mascota al
    mapearla, de forma ASÍNCRONA un instante después del MapNotify, así que
    devolver el foco una sola vez, en el mismo instante en que procesamos el
    evento, pierde la carrera. Un puñado de reintentos espaciados en el
    primer medio segundo de vida de la ventana basta para este caso (no hay
    nada más compitiendo por el foco en ese instante). Para robos
    POSTERIORES —el mismo problema pero disparado por un click en cualquier
    momento de la vida de la ventana— install_focus_guard es la defensa:
    ahí sí hace falta reaccionar en el momento exacto en vez de adivinar
    tiempos, porque cualquier reintento a ciegas que dure varios segundos
    corre el riesgo de pisarle el foco a OTRA ventana si el usuario hace
    click en algo más durante esa ventana de tiempo (visto en vivo: probado
    y descartado).

    Si reassert_input_xid no es None, cada reintento también vuelve a poner
    WM_HINTS.input=False en esa ventana — el mismo WM que roba el foco es el
    que pisa este hint, así que le gana la carrera en el mismo ciclo."""
    try:
        from Xlib import X
        from Xlib import display as xlib_display
    except Exception:  # noqa: BLE001
        return

    def go():
        try:
            d = xlib_display.Display()
            d.set_input_focus(X.PointerRoot, X.RevertToPointerRoot, X.CurrentTime)
            if reassert_input_xid is not None:
                win = d.create_resource_object("window", reassert_input_xid)
                _set_input_false(win)
            d.flush()
            d.close()
        except Exception:  # noqa: BLE001
            pass
        return False

    go()
    for delay_ms in (30, 80, 150, 300, 600):
        GLib.timeout_add(delay_ms, go)
