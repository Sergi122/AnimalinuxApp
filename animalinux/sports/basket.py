"""
🏀 Básquet: un aro en cada extremo. Tú (y tu ayudante) encestan en el de la
DERECHA, las mascotas en el de la izquierda. Paredes y techo rebotan.

  - Mantén pulsado sobre el balón para AGARRARLO (máx. 3 s). Mientras lo
    llevas no puedes mover el mouse muy rápido: si corres con él → falta.
    Al soltar, se lanza con el último movimiento (un tirón corto vale).
  - Sin agarrarlo, el cursor lo EMPUJA como en los otros deportes.
  - Por encima del límite de altura de tu cursor (la línea punteada) no se
    puede agarrar ni empujar el balón.
  - Canasta = 2 puntos; desde lejos (más allá de la línea), 3.
  - Tu ayudante juega de verdad: se desmarca, ataca botando hacia el aro,
    tira, y te PASA el balón (te llega ya agarrado). Para pasárselo a ella,
    lánzaselo. En defensa marca a la que lleva el balón, roba y tapona.
  - Las mascotas botan, se pasan el balón (puedes interceptar el pase), una
    te marca y otra cuida tu aro; SALTAN a taponar tus tiros calculando por
    dónde pasa el balón. La dificultad cambia cuánto taponan, la velocidad de
    sus tiros y pases y lo fácil que es quitarles el balón.
"""
import math
import random
import time

from ..i18n import N_, tr
from .base import TICK_MS, Match, Player, ballistic, chance

DT = TICK_MS / 1000.0
HOLD_MAX_S = 3.0
SHOT_CLOCK_S = 24.0      # reloj de posesión: hay que tirar antes de 24 s
MAX_BALL = 46.0

# por dificultad: prob. de taponar al tocar el tiro, de saltar a taponar,
# radio extra para agarrar/interceptar, altura de sus tiros y pases (más
# bajos = más rápidos), prob. por tick de robarte el balón, y lo que roba y
# tapona tu ayudante (contra mascotas más difíciles, menos)
LEVELS = {
    "easy":   {"block": 0.5,  "jump": 0.8,  "grab": 50, "shot": (0.12, 0.2),
               "pass": (0.5, 0.8),   "steal": 0.05, "ally_steal": 0.03, "ally_block": 0.5},
    "medium": {"block": 0.6,  "jump": 0.9, "grab": 30, "shot": (0.07, 0.13),
               "pass": (0.25, 0.5),  "steal": 0.09, "ally_steal": 0.016, "ally_block": 0.4},
    "hard":   {"block": 0.75, "jump": 1.0, "grab": 18, "shot": (0.04, 0.09),
               "pass": (0.12, 0.3),  "steal": 0.13, "ally_steal": 0.008, "ally_block": 0.3},
}


class Basket(Match):
    SPORT = "basket"
    BALL = "basket"
    HOWTO = N_("Mantén pulsado para agarrar el balón (3 s, sin correr) y suelta con un tirón para tirar al aro de la derecha")
    FOOT = 30

    def setup(self):
        s = self.S
        self.g = 0.9 * s
        self.lv = LEVELS[self._diff_name()]
        self.rim_y = self.F - min(self.H * 0.62, max(2.7 * self.avg_h, self.H * 0.42))
        self.rim_w = self.ball.r * 3.3
        self.board_w = max(6, 10 * s)
        self.three = self.W * 0.42           # distancia de triple
        self.st = 0.0
        self.owner = None                    # Player con el balón, o "you"
        self.hold_t0 = 0.0
        self.fast_ticks = 0
        self.vel_hist = []
        self.shot = None                     # (equipo, x desde donde tiró)
        self.shot_id = 0                     # cada tiro, para saltar UNA vez a taponarlo
        self._jumped = set()
        self._tried = set()
        self.shooter_target = None
        self.pass_to = None                  # Player (rival o ayudante) o "you"
        self.poss = None                     # equipo con la posesión ("you"/"pets")
        self.poss_t0 = 0.0
        self.helper_spot = self.W * 0.7
        self.helper_spot_t = 0.0
        self.helper_t0 = 0.0
        for i, p in enumerate(self.rivals):
            p.x = self.W * (0.55 + 0.1 * i)
        if self.helper:
            self.helper.x = self.W * 0.12
        self._give("you")

    # geometría de los aros: lado -1 = izquierda (mascotas tiran), +1 = derecha (tú)
    def _hoop(self, side):
        if side > 0:
            board = self.W - self.board_w
            return board, board - self.rim_w, board      # tablero, aro frente, aro fondo
        board = self.board_w
        return board, board + self.rim_w, board

    def _rim_center(self, side):
        _b, front, back = self._hoop(side)
        return (front + back) / 2

    # ── posesión ──────────────────────────────────────────────────────────
    def _possess(self, team):
        if team != self.poss:
            self.poss = team
            self.poss_t0 = self.st

    def _give(self, who):
        self._possess(who)
        b = self.ball
        b.held = False
        self.owner = None
        self.shot = None
        self.pass_to = None
        if who == "you":
            b.x, b.y = self.W * 0.25, self.F - self.H * 0.3
            b.vx, b.vy = 0.0, 0.0
        else:
            p = min(self.rivals, key=lambda r: abs(r.cx - self.W * 0.75))
            self._pet_takes(p)

    def _pet_takes(self, p):
        self._possess("pets")
        self.owner = p
        self.pass_to = None
        self.shot = None
        self.ball.held = True
        self.shooter_target = self._rim_center(-1) + random.uniform(0.12, 0.38) * self.W

    def _helper_takes(self, h):
        self._possess("you")
        self.owner = h
        self.pass_to = None
        self.shot = None
        self.ball.held = True
        self.helper_t0 = self.st
        self.shooter_target = self._rim_center(1) - random.uniform(0.12, 0.38) * self.W

    def _you_take(self):
        b = self.ball
        self.owner = "you"
        self._possess("you")
        self.pass_to = None
        self.shot = None
        b.held = True
        b.vx = b.vy = 0.0
        self.hold_t0 = self.st
        self.fast_ticks = 0
        self.vel_hist = []

    def _new_shot(self, team, x):
        self.shot = (team, x)
        self.shot_id += 1

    # ── entrada ───────────────────────────────────────────────────────────
    def on_press(self, x, y):
        b = self.ball
        if self.owner is not None:
            return
        if not self.ball_reachable(b):
            return          # por encima del límite de tu cursor no se agarra
        stealing = isinstance(self.pass_to, Player) and self.pass_to.team == "pets"
        pad = self.lv["grab"] if stealing else 50
        if math.hypot(x - b.x, y - b.y) <= b.r + pad * self.S:
            if stealing:
                self.say(tr("¡Interceptado!"), 1.0, (1, 0.9, 0.3), y=self.H * 0.3)
            self._you_take()

    def on_release(self, x, y):
        if self.owner != "you":
            return
        b = self.ball
        b.held = False
        self.owner = None
        hist = self.vel_hist[-4:] or [(0.0, 0.0)]
        vx = sum(v[0] for v in hist) / len(hist)
        vy = sum(v[1] for v in hist) / len(hist)
        sp = math.hypot(vx, vy)
        cap = MAX_BALL * self.S
        if sp > cap:
            vx, vy = vx * cap / sp, vy * cap / sp
        b.vx, b.vy = vx * 1.3, vy * 1.3
        self._new_shot("you", b.x)
        # tu cursor no empuja el balón recién lanzado (si no, chocaría contigo)
        self.no_push_until = time.monotonic() + 0.35
        # la que te marca salta al instante a taponar (como en un partido de verdad)
        gp = 1.3 * self.S
        for p in self.rivals:
            if abs(p.cx - b.x) < p.w * 2.2 and p.on_ground and p.cool == 0:
                self._jumped.add((self.shot_id, id(p)))
                if chance(self.lv["jump"]):
                    top = min(self.H * 0.32, p.h * 1.8)
                    rise = max(p.h * 0.5, min(top, p.floor_top - (b.y - b.r)))
                    p.jump(-math.sqrt(2 * gp * rise))
                    p.face(b.x)
        # ¿una mascota te estorba al lanzar? (además de saltar a taponar)
        near = min(self.rivals, key=lambda p: abs(p.cx - b.x))
        dist = abs(near.cx - b.x)
        if dist < near.w * 2.0 and b.y > near.y - near.h:
            near.face(b.x)
            k = 1.0 - dist / (near.w * 2.0)
            if chance(0.1 + 0.4 * self.diff["skill"] * k):
                b.vx *= random.uniform(0.75, 1.25)
                b.vy *= random.uniform(0.8, 1.2)
                self.say(tr("¡Te estorbó!"), 0.9, (1, 0.6, 0.5), x=near.cx,
                         y=near.y - 30 * self.S, size=0.7)

    def _foul(self, why):
        self.say(why, 1.4, (1, 0.5, 0.45), y=self.H * 0.3)
        self.ball.held = False
        self.owner = None
        self._give("pets")

    # ── tick ──────────────────────────────────────────────────────────────
    def update(self, now):
        self.st += DT
        b, s = self.ball, self.S
        prev_y = b.y
        if self.poss is not None and self.st - self.poss_t0 > SHOT_CLOCK_S:
            team = self.poss
            self.say(tr("¡24 segundos! Pierde la posesión"), 1.5, (1, 0.6, 0.45), y=self.H * 0.3)
            self.owner = None
            b.held = False
            self._give("pets" if team == "you" else "you")
            return

        if self.owner == "you":
            if self.mouse is not None:
                b.x, b.y = self.mouse
            sp = math.hypot(self.mvx, self.mvy)
            self.vel_hist.append((self.mvx, self.mvy))
            # un tirón corto para lanzar vale; correr con el balón, no
            self.fast_ticks = self.fast_ticks + 1 if sp > 32 * s else 0
            if self.fast_ticks > 10:
                self._foul(tr("¡Falta! Corriste con el balón"))
            elif self.st - self.hold_t0 > HOLD_MAX_S:
                self._foul(tr("¡Falta! 3 segundos"))
            self._defense_vs_you(b)
            self._steal(b)
            self._helper_ai(b)
            return
        if isinstance(self.owner, Player):
            if self.owner.team == "pets":
                self._pet_with_ball(self.owner, b)
            else:
                self._helper_with_ball(self.owner, b)
                self._defense_vs_you(b)
                self._steal(b)
            self._helper_ai(b)
            return

        # balón suelto: física
        b.vy += self.g
        b.vx *= 0.997
        b.x += b.vx
        b.y += b.vy
        b.spin = (b.spin + math.degrees(b.vx / b.r)) % 360
        if b.y + b.r >= self.F:
            b.y = self.F - b.r
            b.vy = -abs(b.vy) * 0.72 if abs(b.vy) > 2 * s else 0.0
            b.vx *= 0.96
            if self.pass_to is not None:
                self.pass_to = None            # el pase se perdió
        if b.y - b.r < 0:
            b.y, b.vy = b.r, abs(b.vy) * 0.6
        if b.x - b.r < 0:
            b.x, b.vx = b.r, abs(b.vx) * 0.7
        if b.x + b.r > self.W:
            b.x, b.vx = self.W - b.r, -abs(b.vx) * 0.7
        for side in (-1, 1):
            self._hoop_collide(b, side)
            if self._through(b, prev_y, side):
                return
        # pase de tu ayudante: te llega YA agarrado
        if self.pass_to == "you" and self.mouse is not None and self.ball_reachable(b):
            mx, my = self.mouse
            if math.hypot(b.x - mx, b.y - my) <= b.r + (self.FOOT + 14) * s:
                self._you_take()
                return
        if self.mouse_push(b, MAX_BALL * s) and isinstance(self.pass_to, Player) \
                and self.pass_to.team == "pets":
            self.pass_to = None
            self.say(tr("¡Interceptado!"), 1.0, (1, 0.9, 0.3), y=self.H * 0.3)
        for p in self.rivals:
            self._contest(p, b)
        self._loose_ball(b)
        if self.owner is None:
            self._defend_hoop(b)
            self._helper_ai(b)

    def _hoop_collide(self, b, side):
        board, front, back = self._hoop(side)
        # tablero
        top = self.rim_y - 95 * self.S
        if top < b.y < self.rim_y + 12 * self.S:
            if side > 0 and b.x + b.r > board:
                b.x, b.vx = board - b.r, -abs(b.vx) * 0.6
            if side < 0 and b.x - b.r < board:
                b.x, b.vx = board + b.r, abs(b.vx) * 0.6
        # los dos extremos del aro
        for px in (front, back):
            dx, dy = b.x - px, b.y - self.rim_y
            d = math.hypot(dx, dy)
            if 0 < d < b.r + 3:
                nx, ny = dx / d, dy / d
                vn = b.vx * nx + b.vy * ny
                if vn < 0:
                    b.vx -= 1.55 * vn * nx
                    b.vy -= 1.55 * vn * ny
                b.x, b.y = px + nx * (b.r + 3), self.rim_y + ny * (b.r + 3)

    def _through(self, b, prev_y, side):
        _board, front, back = self._hoop(side)
        lo, hi = min(front, back), max(front, back)
        if prev_y < self.rim_y <= b.y and b.vy > 0 and lo + b.r * 0.3 < b.x < hi - b.r * 0.3:
            who = "you" if side > 0 else "pets"
            pts = 2
            if self.shot and self.shot[0] == who and abs(self.shot[1] - self._rim_center(side)) > self.three:
                pts = 3
            self.last_pts = pts
            self.point(who, tr("¡Triple!") if pts == 3 else tr("¡Canasta!"))
            self._give("pets" if who == "you" else "you")
            return True
        return False

    def points_for(self, who):
        return getattr(self, "last_pts", 2)

    # ── IA ────────────────────────────────────────────────────────────────
    def _contest(self, d, b):
        """d salta a TAPONAR un tiro del otro equipo: calcula por dónde pasará
        el balón por encima de ella y salta para llegar justo a esa altura."""
        if self.owner is not None or self.shot is None or self.shot[0] == d.team \
                or d.cool > 0 or abs(b.vx) < 0.5:
            return
        key = (self.shot_id, id(d))
        t = (d.cx - b.x) / b.vx                       # ticks hasta pasar por ella
        if d.on_ground and 0 < t < 40 and key not in self._jumped:
            y_at = b.y + b.vy * t + 0.5 * self.g * t * t
            gp = 1.3 * self.S
            rise = d.floor_top - (y_at - b.r * 0.3)       # su cabeza a la altura del balón
            if 0 < rise <= min(self.H * 0.32, d.h * 1.8):
                if t <= math.sqrt(2 * rise / gp) + 1:
                    self._jumped.add(key)
                    rate = self.lv["jump"] if d.team == "pets" else 0.8
                    if chance(rate):
                        d.jump(-math.sqrt(2 * gp * rise * 1.05))
        if key not in self._tried and d.touches(b, 4):
            # también de pie, con las manos arriba (pero cuesta más)
            self._tried.add(key)
            rate = self.lv["block"] if d.team == "pets" else self.lv["ally_block"]
            if d.on_ground:
                rate *= 0.5
            if chance(rate):
                away = -1 if b.vx > 0 else 1
                b.vx = away * (abs(b.vx) * 0.4 + 4 * self.S)
                b.vy = -5 * self.S
                self.shot = None
                d.cool = 12
                col = (1, 0.6, 0.5) if d.team == "pets" else (0.6, 0.9, 1)
                self.say(tr("¡Tapón!"), 0.9, col, x=d.cx, y=d.y - 30 * self.S, size=0.7)

    def _loose_ball(self, b):
        """Balón suelto: las dos mascotas más cerca van a por él (o la que
        recibe un pase espera la pelota)."""
        sp = 6.5 * self.S * self.diff["speed"]
        o = self.pass_to
        if isinstance(o, Player) and o.team == "pets":
            if o.touches(b, 8):
                self._pet_takes(o)
                return
            if abs(b.vx) < 0.5:
                self.pass_to = None            # el pase se perdió
            else:
                o.run_to(b.x + b.vx * 6, sp * o.k, (0, self.W))
                o.face(b.x)
                return
        # un tiro tuyo en el aire solo se para TAPONANDO (_contest); el balón
        # se agarra cuando ya baja (rebote)
        live = self.shot is not None and self.shot[0] == "you" \
            and not (b.vy > 0 and b.y > self.rim_y + self.H * 0.08)
        near = sorted(self.rivals, key=lambda p: abs(p.cx - b.x))[:2]
        for p in near:
            if live:
                p.run_to(b.x + b.vx * 8, sp * p.k, (0, self.W))   # va al rebote
                p.face(b.x)
                continue
            p.run_to(b.x, sp * p.k, (0, self.W))
            p.face(b.x)
            if b.y < p.y and abs(b.x - p.cx) < p.w and b.vy > 0 and chance(0.06):
                p.jump(-17 * p.k)
            if p.cool == 0 and p.touches(b, 4):
                if b.y > self.F - p.h * 1.6 or chance(0.4):
                    self._pet_takes(p)
                    return
                b.vx, b.vy = -abs(b.vx) * 0.5 - 3 * self.S, -6 * self.S   # la palmea
                p.cool = 10

    def _pass_target(self, p):
        """¿A quién pasarla? A una compañera más cerca del aro y libre."""
        rim = self._rim_center(-1)
        best = None
        for o in self.rivals:
            if o is p or o.cool > 0:
                continue
            if abs(o.cx - rim) < abs(p.cx - rim) - p.w:
                if best is None or abs(o.cx - rim) < abs(best.cx - rim):
                    best = o
        return best

    def _pass(self, p, o, b):
        b.held = False
        self.owner = None
        b.x, b.y = p.cx, p.y + p.h * 0.3
        lo, hi = self.lv["pass"]
        apex = min(p.y, o.y) - p.h * random.uniform(lo, hi)
        vx, vy, _t = ballistic(b.x, b.y, o.cx, o.y + o.h * 0.35, apex, self.g)
        b.vx, b.vy = vx, vy
        self.pass_to = o
        p.cool = 12
        self.say(tr("¡Pase!"), 0.6, (1, 0.8, 0.6), x=p.cx, y=p.y - 30 * self.S, size=0.55)

    def _carry(self, p, b, side, acc):
        """Bota hacia su sitio de tiro, salta y tira al aro `side`."""
        sp = 5.5 * self.S * self.diff["speed"] * p.k
        arrived = p.run_to(self.shooter_target, sp, (0, self.W))
        p.face(self._rim_center(side))
        if p.on_ground and not arrived:
            ph = (self.st * 6.0) % 2.0                      # bote
            hand = p.y + p.h * 0.55
            ground = self.F - b.r
            b.x = p.cx + (-1 if p.win._facing_left else 1) * p.w * 0.35
            b.y = hand + (ground - hand) * (1 - abs(ph - 1.0))
            b.spin = (b.spin + 12) % 360
            return
        if p.on_ground:
            p.jump(-12 * p.k)                                # salta para tirar
            return
        if p.vy >= -1:                                       # arriba del salto: tira
            b.held = False
            self.owner = None
            b.x, b.y = p.cx, p.y - b.r
            rx = self._rim_center(side)
            if not chance(acc):
                rx += random.choice((-1, 1)) * self.rim_w * random.uniform(0.55, 1.1)
            lo, hi = self.lv["shot"] if p.team == "pets" else (0.1, 0.18)
            apex = min(self.rim_y, b.y) - self.H * random.uniform(lo, hi)
            vx, vy, _t = ballistic(b.x, b.y, rx, self.rim_y, apex, self.g)
            b.vx, b.vy = vx, vy
            self._new_shot(p.team, b.x)
            self.poss = None
            p.cool = 15
        else:
            b.x, b.y = p.cx, p.y - b.r * 0.6

    def _pet_with_ball(self, p, b):
        """Bota hacia su sitio de tiro, pasa si una compañera está mejor, y lanza."""
        if p.on_ground and len(self.rivals) > 1 and chance(0.012 + 0.02 * self.diff["skill"]):
            o = self._pass_target(p)
            if o is not None:
                self._pass(p, o, b)
                return
        self._carry(p, b, -1, self.diff["skill"])

    def _helper_with_ball(self, h, b):
        """Tu ayudante con el balón: ataca hacia el aro de la derecha y te lo
        pasa (más si la marcan); si no, tira ella."""
        guarded = any(abs(p.cx - h.cx) < h.w * 1.3 for p in self.rivals)
        if h.on_ground and self.mouse is not None and self.st - self.helper_t0 > 0.6 \
                and chance(0.05 if guarded else 0.015):
            self._pass_you(h, b)
            return
        self._carry(h, b, 1, 0.55)

    def _pass_you(self, h, b):
        b.held = False
        self.owner = None
        mx, my = self.mouse
        my = max(my, self.limit_y + b.r)
        b.x, b.y = h.cx, h.y + h.h * 0.3
        apex = min(b.y, my) - h.h * random.uniform(0.3, 0.6)
        vx, vy, _t = ballistic(b.x, b.y, mx, my, apex, self.g)
        b.vx, b.vy = vx, vy
        self.pass_to = "you"
        h.cool = 12
        self.say(tr("¡Tuya!"), 0.7, (0.6, 0.9, 1), x=h.cx, y=h.y - 30 * self.S, size=0.6)

    def _defense_vs_you(self, b):
        """Tu equipo ataca: una mascota cuida tu aro y otra marca al balón."""
        self._defend_hoop(b)
        if not self.rivals:
            return
        keeper = self._hoop_keeper()
        others = [p for p in self.rivals if p is not keeper] or self.rivals
        guard = min(others, key=lambda p: abs(p.cx - b.x))
        if guard is keeper and len(self.rivals) > 1:
            return
        sp = 6 * self.S * self.diff["speed"] * guard.k
        # se pone delante del balón, entre él y tu aro
        guard.run_to(b.x + guard.w * 1.1, sp, (0, self.W))
        guard.face(b.x)

    def _hoop_keeper(self):
        hoop_x = self._rim_center(1)
        return min(self.rivals, key=lambda p: abs(p.cx - hoop_x))

    def _defend_hoop(self, b):
        """Una mascota se planta bajo TU aro (el de la derecha) y tapona."""
        if not self.rivals:
            return
        d = self._hoop_keeper()
        if d is self.owner or (len(self.rivals) == 1 and self.owner is not None):
            return
        sp = 6 * self.S * self.diff["speed"] * d.k
        d.run_to(self._rim_center(1) - self.W * 0.1, sp, (0, self.W))
        d.face(b.x)
        self._contest(d, b)

    def _helper_ai(self, b):
        """Tu ayudante sin balón: se desmarca en ataque, marca y roba en
        defensa, va a por los rebotes y tapona."""
        h = self.helper
        if h is None or self.owner is h:
            return
        sp = 6.5 * self.S * h.k
        bounds = (0, self.W)
        owner = self.owner
        if isinstance(owner, Player) and owner.team == "pets":
            # defensa: delante de la que bota, entre ella y su aro (el de la izquierda)
            h.run_to(owner.cx - owner.w * 1.1, sp, bounds)
            h.face(owner.cx)
            if h.cool == 0 and h.touches(b, 6) and chance(self.lv["ally_steal"]):
                self.say(tr("¡Robo de tu ayudante!"), 1.0, (0.6, 0.9, 1),
                         x=h.cx, y=h.y - 30 * self.S, size=0.6)
                owner.cool = 20
                self._helper_takes(h)
            return
        if owner == "you" or self.pass_to == "you":
            # ataque: se desmarca entre tu cursor y el aro, lejos de las rivales
            if self.st - self.helper_spot_t > 1.5:
                self.helper_spot_t = self.st
                best, bx = -1, self.W * 0.7
                for _ in range(10):
                    x = random.uniform(self.W * 0.5, self.W * 0.88)
                    dd = min(abs(x - p.cx) for p in self.rivals)
                    if dd > best:
                        best, bx = dd, x
                self.helper_spot = bx
            h.run_to(self.helper_spot, sp, bounds)
            h.face(b.x)
            return
        # balón suelto
        self._contest(h, b)
        if self.shot is not None and self.shot[0] == "pets":
            h.run_to(self._rim_center(-1) + self.W * 0.08, sp, bounds)    # al rebote
            h.face(b.x)
            return
        h.run_to(b.x, sp, bounds)
        h.face(b.x)
        # tu tiro no lo «roba» en el aire: solo recoge balones que ya bajan
        # (el rebote, o tu pase cuando le llega)
        low = b.y > self.rim_y + self.H * 0.08 and b.vy > 0
        mine = self.shot is None or (self.shot[0] == "you" and low)
        if mine and h.cool == 0 and h.touches(b, 6):
            self._helper_takes(h)               # recoge el rebote o tu pase

    def _steal(self, b):
        """Si llevas el balón (tú o tu ayudante) cerca de una mascota, puede robarlo."""
        for p in self.rivals:
            if p.cool == 0 and p.touches(b, 6) and chance(self.lv["steal"]):
                self.say(tr("¡Robo!"), 1.0, (1, 0.5, 0.5), x=p.cx, y=p.y - 30 * self.S, size=0.7)
                if isinstance(self.owner, Player):
                    self.owner.cool = 20
                self.owner = None
                b.held = False
                self._pet_takes(p)
                return

    # ── dibujo ────────────────────────────────────────────────────────────
    def draw_field(self, cr):
        s = self.S
        for side, col in ((-1, (1, 0.55, 0.7)), (1, (0.45, 0.8, 1))):
            board, front, back = self._hoop(side)
            # poste
            px = board + side * 4 * s
            cr.set_source_rgba(0.75, 0.75, 0.8, 0.9)
            cr.rectangle(px - 3 * s, self.rim_y - 40 * s, 6 * s, self.F - self.rim_y + 40 * s)
            cr.fill()
            # tablero
            bx = board if side > 0 else board - self.board_w
            cr.set_source_rgba(1, 1, 1, 0.9)
            cr.rectangle(bx, self.rim_y - 95 * s, self.board_w, 107 * s)
            cr.fill()
            # red
            lo, hi = min(front, back), max(front, back)
            cr.set_source_rgba(1, 1, 1, 0.7)
            cr.set_line_width(1.5)
            depth = self.rim_w * 0.8
            for k in range(6):
                t = k / 5
                x = lo + (hi - lo) * t
                cr.move_to(x, self.rim_y)
                cr.line_to(lo + (hi - lo) * (0.2 + 0.6 * t), self.rim_y + depth)
            cr.stroke()
            # aro
            cr.set_source_rgba(0.95, 0.35, 0.15, 1)
            cr.set_line_width(max(3, 5 * s))
            cr.move_to(lo, self.rim_y)
            cr.line_to(hi, self.rim_y)
            cr.stroke()
            # línea de triple
            tx = self._rim_center(side) - side * self.three
            cr.set_source_rgba(col[0], col[1], col[2], 0.7)
            cr.rectangle(tx - 2, self.F - 10 * s, 4, 10 * s)
            cr.fill()
            cr.rectangle(min(tx, self._rim_center(side)), self.F - 4, abs(self._rim_center(side) - tx), 4)
            cr.fill()

    def draw_extra(self, cr):
        if self.poss is not None:
            left = max(0, int(SHOT_CLOCK_S - (self.st - self.poss_t0)) + 1)
            col = (1, 0.45, 0.4) if left <= 5 else (1, 0.85, 0.4)
            # reloj de posesión, en un recuadro junto al marcador
            x0, y0 = self.W / 2 + 222 * self.S, 22 * self.S
            self._round_rect(cr, x0, y0, 54 * self.S, 46 * self.S, 10 * self.S)
            cr.set_source_rgba(0.09, 0.08, 0.15, 0.86)
            cr.fill()
            self._text(cr, f"{min(24, left)}", x0 + 27 * self.S, y0 + 33 * self.S, 24 * self.S, col,
                       outline=False)
            cr.new_path()
        if self.owner == "you":
            # cuánto te queda de los 3 segundos
            left = max(0.0, 1 - (self.st - self.hold_t0) / HOLD_MAX_S)
            b, s = self.ball, self.S
            cr.set_source_rgba(1, 1, 1, 0.85)
            cr.set_line_width(4 * s)
            cr.new_path()
            cr.arc(b.x, b.y, b.r + 10 * s, -math.pi / 2, -math.pi / 2 + 2 * math.pi * left)
            cr.stroke()
