"""Lo que gritan las mascotas cuando hay punto (06-nov)."""
import random

from animalinux.i18n_data import TR
from animalinux.sports.base import Match
from animalinux.sports.basket import Basket
from animalinux.sports.football import Football
from animalinux.sports.racket import RacketMatch
from animalinux.sports.volley import Volley


def pool(team, scorer, before, after, cls=Match):
    return cls.reaction_pool(team, scorer, before, after)


def test_rivales_celebran_o_se_quejan():
    # before/after = TU ventaja; las mascotas rivales son el equipo "pets"
    assert set(Match.CHEER) <= set(pool("pets", "pets", 0, -1))
    assert set(Match.BOO) <= set(pool("pets", "you", 0, 1))


def test_remontada_empate_y_vuelta():
    assert set(Match.COMEBACK) <= set(pool("pets", "pets", 3, 2))   # 0-3 → 1-3
    assert set(Match.TIED) <= set(pool("pets", "pets", 1, 0))
    assert set(Match.TIED) <= set(pool("you", "you", -1, 0))        # tu ayudante
    assert set(Match.TURNED) <= set(pool("pets", "pets", 1, -1))    # tenis: 2 de golpe


def test_las_alcanzan_y_paliza():
    assert set(Match.CAUGHT) <= set(pool("pets", "you", -2, -1))     # 2-0 → 2-1
    assert set(Match.CRUSHED) <= set(pool("pets", "you", 2, 3))
    assert set(Match.ROUT) <= set(pool("pets", "pets", -2, -3))


def test_sola_habla_en_singular():
    for args in [("pets", 0, -1), ("pets", 3, 2), ("pets", 1, 0), ("pets", 1, -1),
                 ("you", -2, -1), ("you", 2, 3), ("you", 0, 1), ("pets", -2, -3)]:
        p = Match.reaction_pool("pets", *args, solo=True)
        assert p
        assert not set(p) & Match.TEAM_ONLY, args
        assert not [x for x in p if "{name}" in x], args
    assert set(Match.SOLO["TIED"]) <= set(Match.reaction_pool("pets", "pets", 1, 0, solo=True))


def test_con_companeros_se_animan_por_nombre():
    assert set(Match.PRAISE) <= set(pool("pets", "pets", 0, -1))
    assert set(Match.CHEER_UP) <= set(pool("pets", "you", 0, 1))
    m = Match.__new__(Match)
    for _ in range(30):
        t = m.reaction("pets", "pets", 0, -1, random.Random(_), name="Panda")
        assert "{name}" not in t
    lines = {m.reaction("pets", "you", 0, 1, random.Random(i), name="Panda") for i in range(200)}
    assert any("Panda" in x for x in lines)


def test_ganando_por_mucho_se_burlan():
    for solo in (False, True):
        p = Match.reaction_pool("pets", "pets", -3, -Match.EASY_LEAD, solo=solo)
        assert set(Match.EASY) <= set(p)
        assert len(Match.EASY) >= 12
    assert not set(Match.EASY) & set(pool("pets", "pets", -1, -2))


def test_al_final_ganador_se_burla_perdedor_se_queja():
    m = Match.__new__(Match)
    from animalinux.i18n import tr
    assert m.final_line("pets", "lose", random.Random(1)) in {tr(x) for x in Match.WIN_TAUNT}
    assert m.final_line("pets", "win", random.Random(1)) in {tr(x) for x in Match.LOSE_SULK}
    assert m.final_line("you", "win", random.Random(1)) in {tr(x) for x in Match.WIN_TAUNT}
    assert m.final_line("pets", "draw") is None


def test_frases_propias_de_cada_deporte():
    for cls in (Football, Basket, Volley, RacketMatch):
        assert cls.SPORT_CHEER
        assert set(cls.SPORT_CHEER) <= set(pool("pets", "pets", 0, -1, cls))


def test_bastante_variedad_y_sin_repetir_seguido():
    m = Match.__new__(Match)
    rnd = random.Random(1)
    seen = [m.reaction("pets", "you", 0, 1, rnd) for _ in range(40)]
    assert len(set(seen)) >= 10
    for i in range(1, len(seen)):
        assert seen[i] not in seen[max(0, i - Match.RECENT):i]


def test_todas_traducidas():
    pools = [Match.CHEER, Match.ROUT, Match.COMEBACK, Match.TIED, Match.TURNED,
             Match.BOO, Match.CAUGHT, Match.CRUSHED, Match.PRAISE, Match.CHEER_UP,
             Match.EASY, Match.WIN_TAUNT, Match.WIN_TAUNT_SOLO, Match.LOSE_SULK,
             ("compa",), *Match.SOLO.values()]
    pools += [c.SPORT_CHEER for c in (Football, Basket, Volley, RacketMatch)]
    lines = [x for p in pools for x in p]
    assert len(lines) >= 70
    missing = [x for x in lines if x not in TR]
    assert not missing, missing
