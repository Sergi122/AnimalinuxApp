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
    assert pool("pets", "pets", 0, -1) == Match.CHEER
    assert pool("pets", "you", 0, 1) == Match.BOO


def test_remontada_empate_y_vuelta():
    assert pool("pets", "pets", 3, 2) == Match.COMEBACK      # iban perdiendo 0-3 → 1-3
    assert pool("pets", "pets", 1, 0) == Match.TIED
    assert pool("you", "you", -1, 0) == Match.TIED          # tu ayudante
    assert pool("pets", "pets", 1, -1) == Match.TURNED      # tenis: un punto puede valer 2


def test_las_alcanzan_y_paliza():
    assert pool("pets", "you", -2, -1) == Match.CAUGHT       # ganaban 2-0, ahora 2-1
    assert set(Match.CRUSHED) <= set(pool("pets", "you", 2, 3))
    assert set(Match.ROUT) <= set(pool("pets", "pets", -2, -3))


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
             Match.BOO, Match.CAUGHT, Match.CRUSHED]
    pools += [c.SPORT_CHEER for c in (Football, Basket, Volley, RacketMatch)]
    lines = [x for p in pools for x in p]
    assert len(lines) >= 70
    missing = [x for x in lines if x not in TR]
    assert not missing, missing
