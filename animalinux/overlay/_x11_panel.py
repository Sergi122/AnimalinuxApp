"""Detecta cuánto espacio ocupa un panel/barra anclado ABAJO en X11.

Los gestores de ventanas EWMH (Muffin, Mutter, KWin, xfwm4, Marco, Openbox,
i3, bspwm...) no coinciden en cómo exponen el área útil: _NET_WORKAREA es una
unión de todos los monitores (falla en multi-monitor) y algunos WM tiling ni
la rellenan. Lo que SÍ comparten todos los paneles/docks (Cinnamon, Xfce,
MATE, KDE, tint2, polybar, Plank, Dash to Dock...) es que reservan su borde
con _NET_WM_STRUT(_PARTIAL) en su propia ventana, así que se leen los struts
y se usa _NET_WORKAREA solo como respaldo.
"""

MAX_GAP = 120   # ninguna barra real mide más; mayor = medida disparatada


def _cardinals(win, atom, d, Xatom):
    try:
        prop = win.get_full_property(d.intern_atom(atom), Xatom.CARDINAL)
    except Exception:  # noqa: BLE001
        return None
    return [int(v) for v in prop.value] if prop is not None else None


def _candidate_windows(d, root, Xatom):
    seen, out = set(), []
    for atom in ("_NET_CLIENT_LIST", "_NET_CLIENT_LIST_STACKING"):
        try:
            prop = root.get_full_property(d.intern_atom(atom), Xatom.WINDOW)
        except Exception:  # noqa: BLE001
            prop = None
        for wid in (prop.value if prop is not None else []):
            if int(wid) not in seen:
                seen.add(int(wid))
                out.append(d.create_resource_object("window", int(wid)))
    # docks sin gestionar (tint2, polybar con override-redirect) no salen en
    # _NET_CLIENT_LIST: se miran también los hijos directos de la raíz
    try:
        for w in root.query_tree().children:
            if w.id not in seen:
                seen.add(w.id)
                out.append(w)
    except Exception:  # noqa: BLE001
        pass
    return out


def bottom_gap(mon_x, mon_y, mon_w, mon_h):
    """Píxeles reservados abajo en el monitor dado, o None si no se pudo medir
    (en ese caso el llamador conserva el valor guardado)."""
    try:
        from Xlib import display, Xatom
    except Exception:  # noqa: BLE001
        return None
    try:
        d = display.Display()
    except Exception:  # noqa: BLE001
        return None
    try:
        screen = d.screen()
        root = screen.root
        root_h = screen.height_in_pixels
        below_mon = max(0, root_h - (mon_y + mon_h))   # raíz bajo este monitor
        gap, found = 0, False
        for win in _candidate_windows(d, root, Xatom):
            s = _cardinals(win, "_NET_WM_STRUT_PARTIAL", d, Xatom)
            if s is not None and len(s) >= 12:
                bottom, bx0, bx1 = s[3], s[10], s[11]
            else:
                s = _cardinals(win, "_NET_WM_STRUT", d, Xatom)
                if s is None or len(s) < 4:
                    continue
                bottom, bx0, bx1 = s[3], 0, 10 ** 9
            if bottom <= 0:
                continue
            found = True
            # el strut solo afecta a este monitor si su tramo horizontal lo cruza
            if bx0 < mon_x + mon_w and bx1 >= mon_x:
                gap = max(gap, bottom - below_mon)
        if not found:
            wa = _cardinals(root, "_NET_WORKAREA", d, Xatom)
            if wa is None or len(wa) < 4:
                return None
            wa_bottom = wa[1] + wa[3]
            if mon_y < wa_bottom <= mon_y + mon_h:
                gap = (mon_y + mon_h) - wa_bottom
            elif wa_bottom > mon_y + mon_h:
                gap = 0
            else:
                return None
        return gap if 0 <= gap <= MAX_GAP else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            d.close()
        except Exception:  # noqa: BLE001
            pass
