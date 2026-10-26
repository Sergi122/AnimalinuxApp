"""Simulación sin ventanas de los tres deportes: miles de ticks con un mouse
simulado. Comprueba que no revientan, que el balón no se escapa de la
pantalla y que hay goles / puntos / canastas."""
import random
import types

import pytest

pytest.importorskip("cairo")
from animalinux.sports import base  # noqa: E402
from animalinux.sports.basket import Basket  # noqa: E402
from animalinux.sports.football import Football  # noqa: E402
from animalinux.sports.volley import Volley  # noqa: E402


class FakeWin:
    def __init__(self, x, w=96, h=96):
        self._cat_w, self._cat_h = w, h
        self._x, self._y = x, 900
        self._screen_w, self._screen_h = 1920, 1080
        self._mon_x = self._mon_y = 0
        self._floor_offset_y = 40
        self._floor_y = 1080 - 40 - h
        self._facing_left = False
        self._hidden_layer = False
        self._paused = False
        self.mode = "life"
        self._state = "idle"
        self.pose = "default"

    def _pose_or(self, *n):
        return n[0]

    def _set_pose(self, p):
        self.pose = p

    def _squash(self, *a):
        pass

    def _lean_to(self, *a):
        pass

    def _apply_juice(self):
        pass

    def _set_position(self, x, y):
        self._x, self._y = x, y

    def _stop_behavior_clock(self):
        pass

    def _start_behavior_clock(self):
        pass

    def get_visible(self):
        return True


def _run(cls, opts, ticks, mouse_fn, rivals=2, helper=True, seed=1):
    random.seed(seed)
    pets = [FakeWin(1200 + 150 * i) for i in range(rivals)]
    h = FakeWin(300) if helper else None
    m = cls(types.SimpleNamespace(), dict(opts), pets, h)
    m.setup()
    m.pitch = None
    clock = [0.0]
    base.time.monotonic = lambda: clock[0]      # reloj simulado
    m.t0 = 0.0
    for t in range(ticks):
        clock[0] += base.TICK_MS / 1000.0
        mouse_fn(m, t)
        m._tick()
        b = m.ball
        assert -5 <= b.x <= m.W + 5 and -5 <= b.y <= m.F + 5, (cls.__name__, t, b.x, b.y)
        if m.over:
            break
    return m


@pytest.fixture(autouse=True)
def _restore_time():
    import time
    real = time.monotonic
    yield
    base.time.monotonic = real


def test_football_pets_score_without_you_and_you_can_score_pushing():
    m = _run(Football, {"difficulty": "hard", "mode": "time", "minutes": 99}, 4000,
             lambda m, t: None)
    assert m.score["pets"] >= 1

    def push(m, t):                 # empuja el balón hacia la derecha con fuerza
        b = m.ball
        m.mouse = (b.x - b.r - 20 + (t % 6) * 8, b.y)
    m = _run(Football, {"difficulty": "easy", "mode": "time", "minutes": 99}, 4000, push,
             rivals=1, helper=False)
    assert m.score["you"] >= 1


def test_volley_rally_points_and_serve_rules():
    def player(m, t):
        b = m.ball
        if m.state == "serve_you" or (b.x < m.net_x and b.vy > 0 and b.y > m.F - 260):
            # el cursor sube desde debajo del balón hacia arriba-derecha
            k = t % 4
            m.mouse = (b.x - b.r - 10 + 6 * k, b.y + b.r + 40 - 22 * k)
        else:
            m.mouse = (60, 60)
    m = _run(Volley, {"difficulty": "hard", "mode": "time", "minutes": 99}, 9000, player)
    assert m.score["you"] + m.score["pets"] >= 3
    # saque que toca la pared del fondo: punto para el rival
    m = _run(Volley, {"difficulty": "medium", "mode": "time", "minutes": 99}, 2,
             lambda m, t: None, rivals=1, helper=False)
    m.state, m.serving = "rally", "you"
    m.ball.x, m.ball.y, m.ball.vx, m.ball.vy = m.ball.r + 2, m.F - 300, -10.0, 0.0
    before = m.score["pets"]
    m.update(0)
    assert m.score["pets"] == before + 1


def test_basket_shots_and_fouls():
    m = _run(Basket, {"difficulty": "hard", "mode": "time", "minutes": 99}, 6000,
             lambda m, t: None)
    assert m.score["pets"] >= 2
    # agarrar y quedarse más de 3 s → falta
    m = _run(Basket, {"difficulty": "medium", "mode": "time", "minutes": 99}, 5,
             lambda m, t: None, rivals=1, helper=False)
    m.mouse = (m.ball.x, m.ball.y)
    m.on_press(*m.mouse)
    assert m.owner == "you"
    for _ in range(int(3.3 / (base.TICK_MS / 1000.0))):
        m.mvx = m.mvy = 0
        m.update(0)
    assert m.owner != "you"
