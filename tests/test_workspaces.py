"""Escritorios: las mascotas con vida te siguen; las sin vida se quedan donde
las dejaste."""
import types

from animalinux.core import mascot_manager as mm


class FakeWin:
    def __init__(self, aid, mode, ws=None):
        self.anim = {"id": aid, "mode": mode}
        if ws:
            self.anim["workspace"] = ws
        self.mode = mode
        self.visible = True
        self.paused = False

    def get_visible(self):
        return self.visible

    def set_visible(self, v):
        self.visible = v

    def set_paused(self, p):
        self.paused = p


def _manager():
    m = mm.MascotManager.__new__(mm.MascotManager)
    m.library = types.SimpleNamespace(update=lambda *a, **k: None)
    m.mascots, m.toys, m.hidden, m._ws_cbs = {}, {}, False, []
    m.workspace = "hypr:1"
    return m


def test_gif_stays_life_follows():
    m = _manager()
    gif, life = FakeWin("g", "gif", "hypr:1"), FakeWin("l", "life")
    m.mascots = {"g": gif, "l": life}
    followed = []
    m.on_workspace_change(followed.append)
    m._on_workspace(1, "hypr:2")
    assert not gif.visible and gif.paused          # se queda en el 1
    assert life.visible and not life.paused        # te acompaña
    assert followed == [1]
    m._on_workspace(-1, "hypr:1")
    assert gif.visible and not gif.paused          # al volver, ahí está


def test_moving_a_gif_pins_it_to_the_current_desktop():
    m = _manager()
    gif = FakeWin("g", "gif", "hypr:1")
    m.mascots = {"g": gif}
    m.workspace = "hypr:3"
    m.on_moved("g", 10, 20)
    assert gif.anim["workspace"] == "hypr:3"


def test_unknown_desktop_at_start_pins_gif_on_first_event():
    m = _manager()
    m.workspace = None                    # KDE: el escritorio llega después
    gif = FakeWin("g", "gif")
    m.mascots = {"g": gif}
    m._on_workspace(0, "kde:1")
    assert gif.anim["workspace"] == "kde:1" and gif.visible
    m._on_workspace(1, "kde:2")
    assert not gif.visible
