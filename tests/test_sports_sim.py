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


def test_volley_serve_is_a_single_touch():
    """Mientras tu saque va en el aire, tu cursor no lo toca (ni falta sin querer)."""
    m = _run(Volley, {"difficulty": "medium", "mode": "time", "minutes": 99}, 2,
             lambda m, t: None, rivals=1, helper=False)
    m._now = 0.0
    m.state, m.serving, m._pushing = "rally", "you", False
    b = m.ball
    b.x, b.y, b.vx, b.vy = m.W * 0.2, m.F - 300, 6.0, -4.0
    m.mouse = (b.x - b.r - 5, b.y)            # el cursor sigue pegado al balón
    m._your_side(b)
    assert (b.vx, b.vy) == (6.0, -4.0) and m.score == {"you": 0, "pets": 0}


def test_volley_no_double_touch_by_pets():
    """Ninguna mascota (rival o ayudante) toca dos veces seguidas."""
    touches = []
    orig_pet = Volley._pet_touch
    orig_touch = Volley._touch
    orig_point = Volley.point

    def point(self, who, label, pause=1.6):
        touches.append(("punto", len(touches)))      # cada punto separa jugadas
        return orig_point(self, who, label, pause)
    Volley.point = point

    def pet_touch(self, p, step):
        touches.append(("pets", id(p)))
        return orig_pet(self, p, step)

    def touch(self, who="you"):
        touches.append(("you", who))
        return orig_touch(self, who)
    Volley._pet_touch = pet_touch
    Volley._touch = touch
    try:
        def player(m, t):
            b = m.ball
            if m.state == "serve_you" or (b.x < m.net_x and b.vy > 0 and b.y > m.F - 260):
                k = t % 4
                m.mouse = (b.x - b.r - 10 + 6 * k, b.y + b.r + 40 - 22 * k)
            else:
                m.mouse = (60, 60)
        _run(Volley, {"difficulty": "hard", "mode": "time", "minutes": 99}, 6000, player, rivals=2)
    finally:
        Volley._pet_touch = orig_pet
        Volley._touch = orig_touch
        Volley.point = orig_point
    pairs = list(zip(touches, touches[1:]))
    doubles = [a for a, b in pairs if a == b and a != ("you", "you")]
    assert len(touches) > 20 and not doubles, doubles[:5]


def _volley(**kw):
    m = _run(Volley, {"difficulty": "medium", "mode": "time", "minutes": 99}, 2,
             lambda m, t: None, **kw)
    m._now = 0.0
    return m


def test_cursor_foot_is_swept_so_fast_moves_dont_skip_the_ball():
    """Un movimiento rápido que cruza el balón en un solo tick lo toca igual."""
    m = _volley(rivals=1, helper=False)
    b = m.ball
    b.x, b.y, b.vx, b.vy = 500.0, 800.0, 0.0, 0.0
    m.mouse = (b.x + 200, b.y)            # antes estaba a la izquierda, ahora a la derecha
    m.mvx, m.mvy = 400.0, 0.0
    assert m.mouse_push(b, 50)
    assert b.vx > 0


def test_volley_one_push_is_one_touch_and_no_double_touch():
    """Un empujón (aunque el cursor siga pegado) es UN toque; luego tu cursor
    atraviesa el balón hasta que toque otra."""
    m = _volley(rivals=1, helper=True)
    m.state, m.serving, m.serve_air = "rally", None, None
    b = m.ball
    b.x, b.y, b.vx, b.vy = m.W * 0.25, m.F - 300, 0.0, 2.0
    for i in range(30):                    # el cursor persigue al balón un segundo
        m.mouse = (b.x, b.y + b.r + 10)
        m.mvx, m.mvy = 0.0, -12.0
        m.st += base.TICK_MS / 1000.0
        m._your_side(b)
        b.x += b.vx
        b.y += b.vy
    assert m.touches == 1 and m.you_locked
    m._touch("helper")
    assert not m.you_locked                # tocó tu ayudante: ya puedes volver


def test_volley_serve_cannot_touch_walls_or_ceiling_but_rally_can():
    m = _volley(rivals=1, helper=False)
    m.state, m.serving, m.serve_air = "rally", None, "pets"
    b = m.ball
    b.x, b.y, b.vx, b.vy = m.W * 0.3, b.r + 1, 3.0, -8.0        # saque rival al techo
    m.update(0)
    assert m.score == {"you": 1, "pets": 0}
    m = _volley(rivals=1, helper=False)
    m.state, m.serving, m.serve_air = "rally", None, "pets"
    b = m.ball
    b.x, b.y, b.vx, b.vy = b.r + 1, m.F - 400, -9.0, 0.0       # saque rival a TU pared
    m.update(0)
    assert m.score == {"you": 1, "pets": 0}
    m = _volley(rivals=1, helper=False)
    m.state, m.serving, m.serve_air = "rally", None, None        # jugada normal: rebota
    b = m.ball
    b.x, b.y, b.vx, b.vy = m.W * 0.3, b.r + 1, 3.0, -8.0
    m.update(0)
    assert m.score == {"you": 0, "pets": 0} and b.vy > 0


def test_volley_team_serve_alternates_you_and_helper():
    m = _volley(rivals=2, helper=True)
    seen = []
    for _ in range(4):
        m.server_you = True
        m._serve()
        seen.append("you" if m.state == "serve_you" else
                    "helper" if m.server is m.helper else "?")
    assert seen in (["helper", "you", "helper", "you"], ["you", "helper", "you", "helper"])


def test_volley_pet_serves_normal_and_jump_and_clean():
    """Las mascotas sacan normal y medio saque mate; sus saques (y los de tu
    ayudante) nunca tocan paredes ni techo."""
    kinds, wall = set(), []
    orig_hit, orig_fault = Volley._serve_hit, Volley._fault

    def hit(self, p):
        kinds.add(self.serve_kind)
        self._srv_pet = True
        return orig_hit(self, p)

    def fault(self, label, now, loser=None):
        if getattr(self, "_srv_pet", False):
            wall.append(label)
        return orig_fault(self, label, now, loser)
    Volley._serve_hit, Volley._fault = hit, fault
    try:
        def player(m, t):
            if m.state == "serve_you":
                m._srv_pet = False
                b = m.ball
                m.mouse = (b.x - b.r - 10 + 6 * (t % 4), b.y + b.r + 30 - 14 * (t % 4))
            else:
                m.mouse = (60, 600)
        _run(Volley, {"difficulty": "hard", "mode": "time", "minutes": 99}, 12000, player,
             rivals=2, seed=4)
    finally:
        Volley._serve_hit, Volley._fault = orig_hit, orig_fault
    assert kinds == {"normal", "jump"} and not wall, (kinds, wall)


def test_volley_helper_spikes_only_on_third_touch():
    spikes = []
    orig_say = Volley.say

    def say(self, text, *a, **k):
        if text == "¡Remate de tu ayudante!":
            spikes.append(self.touches)
        return orig_say(self, text, *a, **k)
    Volley.say = say
    try:
        def player(m, t):
            # tú solo juegas DESPUÉS de que reciba tu ayudante: la levantas
            # hacia la red (2º toque) para que ella remate
            b = m.ball
            if m.state == "serve_you":
                m.mouse = (b.x - b.r - 10 + 6 * (t % 4), b.y + b.r + 40 - 22 * (t % 4))
                m.mvx, m.mvy = 0.0, 0.0
            elif m.touches == 1 and m.last_toucher == "helper" and b.x < m.net_x \
                    and b.vy > 0 and b.y > m.F - 340:
                m.mouse = (b.x - b.r * 0.6, b.y + b.r + 8)
            else:
                m.mouse = (60, m.F - 20)
        for seed in range(4):
            _run(Volley, {"difficulty": "easy", "mode": "time", "minutes": 99}, 9000, player,
                 rivals=2, seed=seed)
    finally:
        Volley.say = orig_say
    assert spikes and all(n == 3 for n in spikes), spikes


def _basket(**kw):
    return _run(Basket, {"difficulty": "medium", "mode": "time", "minutes": 99}, 1,
                lambda m, t: None, **kw)


def test_basket_ball_above_cursor_limit_cannot_be_grabbed_or_pushed():
    m = _basket(rivals=1, helper=False)
    b = m.ball
    b.x, b.y, b.vx, b.vy = m.W * 0.3, m.limit_y - 60, 0.0, 0.0
    m.mouse = (b.x, m.limit_y + 4)
    m.on_press(*m.mouse)
    assert m.owner is None
    m.mvx, m.mvy = 0.0, -30.0
    assert not m.mouse_push(b, 50)
    b.y = m.limit_y + 40                   # bajo el límite sí
    m.on_press(b.x, b.y)
    assert m.owner == "you"


def test_basket_helper_passes_to_you_already_held():
    m = _basket(rivals=1, helper=True)
    h = m.helper
    m._helper_takes(h)
    m.mouse = (m.W * 0.3, m.F - 200)
    m._pass_you(h, m.ball)
    for _ in range(200):
        m.mvx = m.mvy = 0
        m.update(0)
        if m.owner == "you":
            break
    assert m.owner == "you"


def test_basket_you_can_pass_to_the_helper():
    m = _basket(rivals=1, helper=True)
    h = m.helper
    h.x = m.W * 0.5
    m.rivals[0].x = m.W * 0.9
    b = m.ball
    b.x, b.y = h.cx - 300, h.y + h.h * 0.3
    m.mouse = (b.x, b.y)
    m._you_take()
    vx, vy, _t = base.ballistic(b.x, b.y, h.cx, h.y + h.h * 0.4, h.y - 80, m.g)
    m.vel_hist = [(vx / 1.3, vy / 1.3)] * 4
    m.on_release(*m.mouse)
    m.mouse = (60, m.F - 60)
    for _ in range(120):
        m.mvx = m.mvy = 0
        m.update(0)
        for p in m.players:
            p.physics(1.3 * m.S)
        if m.owner is not None:
            break
    assert m.owner is h
