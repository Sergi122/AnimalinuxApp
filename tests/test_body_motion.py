"""Movimiento procedural del cuerpo (modo Vida) sin cuadros propios."""
import types

from animalinux.overlay.live_animation import LiveAnimationMixin


def _stub(state, pose="default", has=False, **kw):
    attrs = dict(
        _state=state, _pose=pose, _has_pose=lambda n: has, _walk_phase=0.5,
        _greet_ttl=0, _react_ttl=0, _jump_vy=-18.0, _toss_vy=0.0, _body_t=0,
        _mood=None, _dir=1, _stretch_t=0)
    attrs.update(kw)
    o = types.SimpleNamespace(**attrs)
    o._companion_body = types.MethodType(LiveAnimationMixin._companion_body, o)
    o._body_motion = types.MethodType(LiveAnimationMixin._body_motion, o)
    o._body_raw = types.MethodType(LiveAnimationMixin._body_raw, o)
    return o


def test_walk_bobs_and_waddles():
    o = _stub("walk")
    sx, sy, lean, bob = o._body_motion()
    assert bob > 0.04 and abs(lean) > 4          # en el aire a mitad de paso
    o._walk_phase = 1.0                            # pie apoyado
    sx, sy, lean, bob = o._body_motion()
    assert bob < 0.01 and sy < 1.0                 # se aplasta al apoyar


def test_idle_breathes():
    o = _stub("idle")
    vals = set()
    for _ in range(40):
        vals.add(o._body_motion()[1])
    assert len(vals) > 5


def test_jump_stretches():
    sx, sy, _, _ = _stub("jump")._body_motion()
    assert sy > 1.0 and sx < 1.0


def test_own_frames_half_intensity():
    full = _stub("walk")._body_motion()
    half = _stub("walk", pose="walk", has=True)._body_motion()
    assert abs(half[2] - full[2] / 2) < 1e-9 and abs(half[3] - full[3] / 2) < 1e-9


def test_dance_bounces_to_the_beat():
    o = _stub("dance")
    bobs = [o._body_motion()[3] for _ in range(16)]
    assert max(bobs) > 0.05 and min(bobs) < 0.01      # sube y baja con el ritmo


def test_tired_droops_and_worried_shivers():
    tired = _stub("idle", _mood="tired")
    assert tired._body_motion()[2] == 6.0              # cabizbaja
    worried = _stub("idle", _mood="worried")
    leans = {round(worried._body_motion()[2], 3) for _ in range(10)}
    assert len(leans) > 3
