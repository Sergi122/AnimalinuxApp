"""
Deportes contra las mascotas: ⚽ fútbol, 🏐 vóley, 🏀 básquet, 🏓 ping-pong y
🎾 tenis.

start(app, sport, opts) elige las mascotas (con vida, hasta 4 rivales y una
ayudante opcional), abre la cancha y arranca el partido. opts:
    difficulty  "easy" | "medium" | "hard"
    mode        "time" | "points"
    minutes     5 | 10        (modo tiempo)
    points      10            (modo puntos)
    rivals      1..4
    helper      bool          (una mascota de tu lado)
"""
from ..i18n import tr

SPORTS = {
    "football": ("⚽", "Fútbol"),
    "volley": ("🏐", "Vóley"),
    "basket": ("🏀", "Básquet"),
    "pingpong": ("🏓", "Ping-pong"),
    "tennis": ("🎾", "Tenis"),
}
MAX_RIVALS = 4

_current = None


def current():
    return _current


def supported():
    from .pitch import supported as _s
    return _s()


def start(app, sport, opts):
    """Devuelve (Match | None, motivo si no se pudo)."""
    global _current
    if _current is not None:
        _current.finish(abandon=True)
    if not supported():
        return None, tr("Los deportes aún no están disponibles en este sistema.")
    mascots = app.manager.mascots
    pets = [w for w in mascots.values() if w.mode == "life" and w.get_visible()]
    if not pets:
        return None, tr("Hace falta al menos una mascota en modo Vida en el escritorio.")
    # equipos elegidos en el menú (cada mascota en UN solo equipo)
    ids = [i for i in opts.get("rival_ids") or [] if i in mascots]
    hid = opts.get("helper_id") or ""
    if ids:
        rivals = [mascots[i] for i in ids if mascots[i] in pets and i != hid][:MAX_RIVALS]
        helper = mascots[hid] if hid in mascots and mascots[hid] in pets else None
        if not rivals:
            return None, tr("Elige al menos una mascota rival.")
    else:
        # todas en el mismo monitor que la primera
        pets = [w for w in pets if (w._mon_x, w._mon_y) == (pets[0]._mon_x, pets[0]._mon_y)]
        want_helper = bool(opts.get("helper")) and len(pets) >= 2
        n = max(1, min(MAX_RIVALS, int(opts.get("rivals", 2)), len(pets) - (1 if want_helper else 0)))
        rivals, helper = pets[:n], (pets[n] if want_helper else None)
    if sport == "volley":
        from .volley import Volley as M
    elif sport == "basket":
        from .basket import Basket as M
    elif sport == "pingpong":
        from .pingpong import PingPong as M
    elif sport == "tennis":
        from .tennis import Tennis as M
    else:
        from .football import Football as M
    match = M(app, opts, rivals, helper)
    monitor = None
    try:
        surf = pets[0].get_surface()
        monitor = pets[0].get_display().get_monitor_at_surface(surf)
    except Exception:  # noqa: BLE001
        monitor = None

    def ended(m):
        global _current
        if _current is m:
            _current = None
        comp = getattr(app, "companion", None)
        if comp is not None:
            comp.match_over(m)
    match.on_end = ended
    _current = match
    comp = getattr(app, "companion", None)
    if comp is not None:
        comp.match_started(match)
    match.start(monitor)
    return match, None
