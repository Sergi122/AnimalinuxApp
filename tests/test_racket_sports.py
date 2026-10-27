"""Ping-pong y tenis: reglas (saque, let, botes, tanteo) y simulación sin
ventanas con un mouse simulado."""
import random
import types

import pytest

pytest.importorskip("cairo")
from animalinux.sports import base  # noqa: E402
from animalinux.sports.pingpong import PingPong  # noqa: E402
from animalinux.sports.tennis import Tennis  # noqa: E402
from test_sports_sim import FakeWin  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_time():
    real = base.time.monotonic
    yield
    base.time.monotonic = real


def _match(cls, helper=False, rivals=1, **opts):
    random.seed(3)
    o = {"difficulty": "medium", "mode": "points", "points": 10}
    o.update(opts)
    pets = [FakeWin(1300 + 150 * i) for i in range(rivals)]
    m = cls(types.SimpleNamespace(), o, pets, FakeWin(300) if helper else None)
    m.setup()
    m.pitch = None
    m.points_log = []
    m.point = lambda who, label, pause=1.6: (m.points_log.append((who, label)), m.award(who))
    return m


def _rally(m, hitter):
    m.state = "rally"
    m.hitter = hitter
    m.bounces = 0
    m.serve_stage = None
    m.net_touch = m.net_hit = False


# ── ping-pong ────────────────────────────────────────────────────────────
def test_pingpong_serve_must_bounce_on_own_side_first():
    m = _match(PingPong)
    _rally(m, "you")
    m.serve_stage = "own"
    m._land(m.net_x + 50)                   # cayó directo en el lado rival
    assert m.points_log == [("pets", "¡El saque debe botar primero en tu lado!")]

    m = _match(PingPong)
    _rally(m, "you")
    m.serve_stage = "own"
    m._land(m.net_x - 80)                   # bien: primero en tu lado
    assert m.serve_stage == "box" and m.ball.vx > 0 and not m.points_log


def test_pingpong_let_replays_the_serve_without_points():
    m = _match(PingPong)
    _rally(m, "you")
    m.serve_stage = "box"
    m.net_touch = True                      # rozó la red y cae bien
    m._land(m.net_x + 100)
    assert m.state == "dead" and not m.points_log


def test_pingpong_double_bounce_and_bounce_on_own_side():
    m = _match(PingPong)
    _rally(m, "you")
    m._land(m.net_x + 100)
    assert m.bounces == 1 and not m.points_log
    m._land(m.net_x + 160)
    assert m.points_log == [("you", "¡Doble bote!")]

    m = _match(PingPong)
    _rally(m, "pets")
    m._land(m.net_x + 100)                  # la de ellas botó en su lado
    assert m.points_log == [("you", "¡Botó en tu propio lado!")]


def test_pingpong_no_hit_before_the_bounce_but_tennis_can_volley():
    m = _match(PingPong)
    _rally(m, "pets")
    m.ball.x = m.net_x - 100
    assert not m.ball_allowed("you")
    m.bounces = 1
    assert m.ball_allowed("you")
    t = _match(Tennis)
    _rally(t, "pets")
    t.ball.x = t.net_x - 100
    assert t.ball_allowed("you")            # volea
    t.serve_stage = "box"
    assert not t.ball_allowed("you")        # pero el saque hay que dejarlo botar


def test_pingpong_serve_changes_every_two_points_and_every_point_from_10_10():
    m = _match(PingPong)
    seq = []
    for who in ["you", "pets", "you", "pets"]:
        m.award(who)
        seq.append(m.server_team)
    assert seq == ["you", "pets", "pets", "you"]
    m.score = {"you": 10, "pets": 9}
    m.award("pets")                          # 10-10
    a = m.server_team
    m.award("you")                           # 11-10
    assert m.server_team != a


def test_pingpong_game_to_11_needs_two_points_of_difference():
    m = _match(PingPong)
    m.score = {"you": 10, "pets": 10}
    assert not m.award("you")                # 11-10: sigue
    assert m.award("you")                    # 12-10: gana


def test_pingpong_doubles_partners_alternate_hits():
    m = _match(PingPong, helper=True, rivals=2)
    _rally(m, "pets")
    m.turn["you"] = 1                        # le toca a la compañera
    assert not m.can_hit("you", "you")
    assert m.can_hit("you", m.helper)
    m._on_hit("you", m.helper)
    _rally(m, "pets")
    assert m.can_hit("you", "you")


# ── tenis ────────────────────────────────────────────────────────────────
def test_tennis_scoring_deuce_advantage_and_game():
    m = _match(Tennis)
    for who in ["you", "you", "you", "pets", "pets", "pets"]:
        m.award(who)
    assert m.call() == "Iguales (deuce)"
    m.award("you")
    assert m.call() == "Ventaja tú"
    m.award("pets")
    assert m.call() == "Iguales (deuce)"
    srv = m.server_team
    m.award("pets")
    m.award("pets")
    assert m.games == {"you": 0, "pets": 1}
    assert m.server_team != srv              # el saque pasa al otro en el juego siguiente


def test_tennis_set_to_6_with_tiebreak_at_6_6():
    m = _match(Tennis)
    m.games = {"you": 5, "pets": 6}
    for _ in range(4):
        won = m.award("you")
    assert m.games == {"you": 6, "pets": 6} and m.tiebreak and not won
    for _ in range(6):
        m.award("you")
    for _ in range(6):
        m.award("pets")
    assert m.tiebreak                        # 6-6 en el tie-break: hacen falta 2 de diferencia
    m.award("you")
    assert m.award("you")                    # 8-6: set
    assert m.games == {"you": 7, "pets": 6}


def test_tennis_serve_box_second_serve_and_double_fault():
    m = _match(Tennis)
    _rally(m, "you")
    m.serve_stage = "box"
    m._land(m.net_x + m.box + 40)            # pasó la línea de saque
    assert m.second and m.state == "dead" and not m.points_log
    _rally(m, "you")
    m.serve_stage = "box"
    m._land(m.net_x + m.box + 40)
    assert m.points_log == [("pets", "¡Doble falta!")]
    assert not m.second

    m = _match(Tennis)
    _rally(m, "you")
    m.serve_stage = "box"
    m._land(m.net_x + m.box * 0.5)           # dentro del cuadro
    assert m.serve_stage is None and m.bounces == 1


def test_tennis_out_beyond_the_baseline():
    m = _match(Tennis)
    _rally(m, "pets")
    m._land(m.x_lo - 20)
    assert m.points_log == [("you", "¡Fuera!")]


# ── simulación ───────────────────────────────────────────────────────────
def _bot(m):
    """Mouse simulado: tras el bote, va a la pelota y la golpea hacia la derecha."""
    b = m.ball
    if getattr(m, "_next", None):
        m.mouse, m._next = m._next, None
        return
    if m.state == "serve" and m.server == "you" and m.serve_phase == "toss" and b.vy > 0:
        m.mouse = (b.x - 14, b.y)
        m._next = (b.x + 2, b.y)
        return
    if m.state == "rally" and b.x < m.net_x and m.can_hit("you", "you") and m.ball_allowed("you"):
        m.mouse = (b.x - 30, b.y + 6)
        m._next = (b.x + 2, b.y)
        return
    m.mouse = (m.x_lo, m.limit_y + 10)


@pytest.mark.parametrize("cls", [PingPong, Tennis])
@pytest.mark.parametrize("helper", [False, True])
def test_racket_simulation_runs_scores_and_keeps_the_ball_on_screen(cls, helper):
    m = _match(cls, helper=helper, rivals=2 if helper else 1, mode="time", minutes=3)
    del m.point                               # el tanteo real
    clock = [0.0]
    base.time.monotonic = lambda: clock[0]
    m.t0 = 0.0
    hits = {"you": 0, "pets": 0}
    on_hit = m._on_hit

    def counted(team, who):
        hits[team] += 1
        on_hit(team, who)
    m._on_hit = counted
    for _ in range(4000):
        clock[0] += base.TICK_MS / 1000.0
        _bot(m)
        m._tick()
        b = m.ball
        assert -5 <= b.x <= m.W + 5 and -5 <= b.y <= m.F + 5
    points = (m.pts["you"] + m.pts["pets"] + 4 * sum(m.games.values())) if cls is Tennis \
        else sum(m.score.values())
    assert points >= 3
    assert hits["you"] > 3 and hits["pets"] > 3


@pytest.mark.parametrize("cls", [PingPong, Tennis])
def test_wheel_tilts_the_paddle_and_the_blade_angle_decides_the_shot(cls):
    m = _match(cls)
    assert m.you_tilt == 0.0                               # arranca recta
    m.on_scroll(-1)                                        # rueda hacia arriba
    assert m.you_tilt == m.TILT_STEP
    for _ in range(20):
        m.on_scroll(-1)
    assert m.you_tilt == m.TILT_MAX                        # con tope

    def out(tilt):
        m.you_tilt = tilt
        b = m.ball
        b.x, b.y, b.vx, b.vy = m.net_x - m.W * 0.2, m.net_top - 20, -6.0, 3.0
        m.mouse_prev = None
        m.mouse, m.mvx, m.mvy = (b.x - 4, b.y), 14.0, 0.0  # golpe hacia la red
        assert m._paddle_hit(b)
        return b.vx, b.vy
    vx0, vy0 = out(0.0)
    vxc, vyc = out(40.0)                                   # cara cerrada
    vxo, vyo = out(-40.0)                                  # cara abierta
    assert vx0 > 0 and vxc > 0 and vxo > 0                 # las tres van hacia la red
    assert vyc > vy0 > vyo                                 # cerrada baja, abierta sube


def test_blade_hitbox_is_the_straight_blade_not_a_circle():
    m = _match(PingPong)
    b = m.ball
    r = m.you_racket_r()
    m.mvx = m.mvy = 0.0
    b.vx, b.vy = -5.0, 0.0
    # junto a la punta de abajo de la lámina recta (vertical): la toca
    b.x, b.y = m.net_x - 200, m.net_top - 40
    m.mouse = (b.x - b.r - 1, b.y - r * 0.9)
    assert m._paddle_hit(b)
    # mismo sitio con la lámina inclinada a 75°: esa punta ya no está ahí
    b.x, b.y, b.vx = m.net_x - 200, m.net_top - 40, -5.0
    m.you_tilt = 75.0
    m.mouse = (b.x - b.r - 1, b.y - r * 0.9)
    assert not m._paddle_hit(b)
