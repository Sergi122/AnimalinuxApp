"""Del estado del sistema al humor de las mascotas: música > batería baja >
CPU al rojo > noche, y el aviso de batería baja sale UNA vez."""
from animalinux.core import companion as comp


class Pet:
    def __init__(self):
        self.mood, self.said = None, []

    def set_mood(self, m):
        self.mood = m

    def say(self, text, secs=0):
        self.said.append(text)


def _companion(monkeypatch, pets):
    monkeypatch.setattr(comp, "cfg", lambda k: comp.DEFAULTS.get(k))
    c = comp.Companion.__new__(comp.Companion)
    c.sys_state, c.dnd, c.dnd_manual, c._low_bat_said = {}, False, False, False
    c.pets = lambda life=True: pets
    c._update_dnd = lambda: None
    return c


def test_mood_priority(monkeypatch):
    c = _companion(monkeypatch, [])
    for st, mood in (({}, None), ({"night": True}, "night"),
                     ({"night": True, "hot": True}, "tired"),
                     ({"hot": True, "low_battery": True}, "worried"),
                     ({"low_battery": True, "music": True}, "dance")):
        c.sys_state = st
        assert c.mood_now() == mood, st


def test_state_reaches_pets_and_battery_warning_once(monkeypatch):
    pets = [Pet(), Pet()]
    c = _companion(monkeypatch, pets)
    c._on_sys_state({"low_battery": True})
    c._on_sys_state({"low_battery": True})
    assert all(p.mood == "worried" for p in pets)
    assert sum(len(p.said) for p in pets) == 1          # una sola vez
    c._on_sys_state({"night": True})
    assert all(p.mood == "night" for p in pets)
    c._on_sys_state({"low_battery": True})               # vuelve a bajar: avisa otra vez
    assert sum(len(p.said) for p in pets) == 2


def test_a_screenshot_is_not_screen_sharing(monkeypatch):
    """Hyprland avisa «screencast» por cada captura (dura <0,5 s): no debe
    esconder las mascotas; si sigue activo SHARE_MIN_S, sí."""
    from animalinux.core import sysmon
    states, timers = [], []
    monkeypatch.setattr(sysmon, "_sharing_now", lambda: False)
    monkeypatch.setattr(sysmon.GLib, "timeout_add", lambda ms, fn: timers.append(fn) or len(timers))
    monkeypatch.setattr(sysmon.GLib, "source_remove", lambda sid: timers.__setitem__(sid - 1, None))
    m = sysmon.SystemMonitor(lambda st: states.append(st["sharing"]), lambda e: None, dict)
    m._on_hypr_screencast("1,monitor")
    m._on_hypr_screencast("0,monitor")             # captura: se acabó enseguida
    assert True not in states and timers == [None]
    m._on_hypr_screencast("1,monitor")             # compartir de verdad
    timers[-1]()                                    # pasaron SHARE_MIN_S
    assert states[-1] is True
