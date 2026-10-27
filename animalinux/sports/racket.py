"""
Motor común de los deportes de raqueta (🏓 ping-pong y 🎾 tenis), vistos de
lado: tú (y tu mascota compañera) a la izquierda, las mascotas a la derecha.

Tu cursor es la raqueta/paleta: empuja la pelota (cuanto más rápido, más
fuerte). El saque se apunta solo y la FUERZA de tu empujón decide lo largo:
suave se queda en la red, fuerte se va fuera.

Reglas comunes (cada deporte las ajusta):
  - Un golpe por equipo: nadie devuelve dos veces seguidas.
  - La pelota tiene que pasar la red y botar en el lado rival. Si bota en tu
    propio lado, choca la red o cae fuera sin botar en el rival, punto para él.
  - Bota una sola vez: al segundo bote, punto para quien la pegó.
  - Si roza la red en el saque y cae bien, es «let»: se repite el saque.
  - Paredes y techo de la pantalla cuentan como fuera.

Cada deporte pone la geometría (superficie de bote, red, zonas buenas), su
tanteo (award) y quién saca.
"""
import math
import random

from ..i18n import N_, tr
from .base import TICK_MS, Match, ballistic, chance

DT = TICK_MS / 1000.0


class RacketMatch(Match):
    REACH_ABOVE_LIMIT = False
    FOOT = 18                # zona de golpe del saque (el resto lo golpea la lámina)
    TILT_MAX = 75.0          # inclinación máxima de la paleta (grados)
    TILT_STEP = 10.0         # grados por paso de la rueda del mouse
    PADDLE_E = 0.3           # rebote de la pelota en la cara de la paleta
    SWING_K = 0.5            # cuánto de la velocidad del mouse pasa a la pelota
    LIFT = 0.3               # elevación al golpear (como al cepillar la pelota)
    YOU_CAP = 0.75           # tope de tu golpe (fracción de MAX_BALL)
    PUSH_K = 0.9             # cuánto sale la pelota respecto a la velocidad del mouse
    VOLLEY_OK = False        # ¿se puede pegar antes del bote? (tenis sí, salvo el saque)
    SERVE_OWN_BOUNCE = False  # ping-pong: el saque bota primero en tu lado
    ALTERNATE = False        # ping-pong en dobles: los compañeros pegan por turnos
    E = 0.8                  # rebote vertical en la superficie
    FRIC = 0.9               # lo que conserva de velocidad horizontal al botar
    MAX_BALL = 30.0
    SERVE_REF = 26.0         # empujón «a fondo» del saque (px/tick a 1080p)
    LEVELS = {}
    HOWTO2 = N_("Rueda del mouse: inclina la paleta (arriba = pelota baja, abajo = pelota alta)")
    RUN = 8.0                # carrera de las mascotas (px/tick a 1080p)
    SMASH = (17.0, 22.0)     # velocidad del remate (px/tick a 1080p)

    # ── geometría (la pone cada deporte en setup) ─────────────────────────
    # self.surf_y, self.x_lo, self.x_hi, self.net_x, self.net_top, self.net_w, self.g
    def on_surface(self, x):
        return True

    def in_bounds(self, x, side):
        """¿Un bote en x (del lado side) es bueno?"""
        if side == "you":
            return self.x_lo <= x < self.net_x
        return self.net_x < x <= self.x_hi

    def serve_box(self, side):
        """(desde, hasta) donde tiene que caer el saque en el lado side."""
        if side == "you":
            return self.x_lo, self.net_x
        return self.net_x, self.x_hi

    def home_x(self, p, i):
        return self.x_hi - p.w

    def hand_y(self, p):
        return p.y + p.h * 0.42

    def racket_r(self, p):
        return max(7 * self.S, 0.13 * p.h)

    def tilt_to(self, ang, target, k=0.3):
        """La paleta se inclina hacia target como la aguja de un
        transportador (suave, sin saltos)."""
        target = max(-self.TILT_MAX, min(self.TILT_MAX, target))
        return ang + (target - ang) * k

    # ── preparación ───────────────────────────────────────────────────────
    def setup_common(self):
        self.lv = self.LEVELS[self._diff_name()]
        self.st = 0.0
        self.state = "dead"
        self.serve_at = 0.6
        self.you_tilt = 0.0                         # inclinación de tu paleta
        self.server_team = "you"
        self.serve_idx = {"you": 0, "pets": 0}    # en dobles, quién del equipo saca
        self.server = None                         # "you" o Player
        self.serve_phase = "hold"
        self.serve_f = 0.0
        self.second = False                        # tenis: segundo saque
        self.hitter = None                         # equipo del último golpe
        self.last_by = None
        self.bounces = 0                           # botes del lado del receptor
        self.serve_stage = None                    # "own" | "box" | None
        self.net_touch = False
        self.net_hit = False
        self.turn = {"you": 0, "pets": 0}
        self.shot_id = 0
        self._let_go = {}
        self._path_key = None
        self._told_serve = False
        self.mouse_racket = None
        for i, p in enumerate(self.rivals):
            p.x = self.home_x(p, i) - p.w / 2
            p.y = p.floor_top
        if self.helper:
            self.helper.x = self.net_x - (self.home_x(self.helper, 0) - self.net_x) - self.helper.w / 2
        self.ball.x, self.ball.y = self.W * 0.2, self.surf_y - self.H * 0.2

    def cursor_limit(self):
        return self.net_x - self.net_w / 2 - 2

    # ── equipos ───────────────────────────────────────────────────────────
    @staticmethod
    def other(team):
        return "pets" if team == "you" else "you"

    def members(self, team):
        if team == "you":
            return ["you"] + ([self.helper] if self.helper else [])
        return list(self.rivals)

    def next_hitter(self, team):
        m = self.members(team)
        return m[self.turn[team] % len(m)]

    def side_of(self, x):
        return "you" if x < self.net_x else "pets"

    def can_hit(self, team, who):
        if self.state != "rally" or self.hitter == team:
            return False
        if self.ALTERNATE and self.next_hitter(team) is not who:
            return False
        return True

    def ball_allowed(self, team):
        """¿Ya se le puede pegar (ha botado, o se permite volear)?"""
        if self.bounces >= 1:
            return True
        return self.VOLLEY_OK and self.serve_stage is None and self.side_of(self.ball.x) == team

    # ── física ────────────────────────────────────────────────────────────
    def _step(self, x, y, vx, vy):
        """Un tick de vuelo. Devuelve (x, y, vx, vy, evento): None, "tape"
        (rozó la cinta y pasó), "net", ("land", x) o "dead" (suelo fuera de la
        mesa, paredes o techo)."""
        r = self.ball.r
        px, py = x, y
        vy += self.g
        x += vx
        y += vy
        ev = None
        if (px - self.net_x) * (x - self.net_x) < 0:
            t = (self.net_x - px) / (x - px)
            yc = py + (y - py) * t
            if yc + r > self.net_top and yc - r < self.surf_y:
                if yc + r < self.net_top + r * 0.9:
                    vx *= 0.55                     # roza la cinta y pasa, frenada
                    vy = -abs(vy) * 0.3
                    y = min(y, self.net_top - r)
                    ev = "tape"
                else:
                    side = -1 if px < self.net_x else 1
                    x = self.net_x + side * (self.net_w / 2 + r)
                    vx = -vx * 0.2
                    ev = "net"
        if vy > 0 and y + r >= self.surf_y and py + r <= self.surf_y + 1 and self.on_surface(x) \
                and r <= x <= self.W - r:
            y = self.surf_y - r
            vy = -vy * self.E
            vx *= self.FRIC
            return x, y, vx, vy, ("land", x)
        if (y + r >= self.F or (y - r > self.surf_y and self.on_surface(x))
                or x - r < 0 or x + r > self.W or y - r < 0):
            x = min(max(x, r), self.W - r)
            y = min(max(y, r), self.F - r)
            return x, y, vx, vy, "dead"
        return x, y, vx, vy, ev

    def _clears(self, x, y, vx, vy):
        if abs(vx) < 1e-6:
            return False
        t = (self.net_x - x) / vx
        if t <= 0:
            return True
        return y + vy * t + 0.5 * self.g * t * t < self.net_top - self.ball.r * 1.3

    def _send(self, x1, apex_y):
        """Parábola hasta botar en x1 con altura máxima apex_y; si cruza la
        red, sube el vértice hasta pasar por encima de la cinta."""
        b = self.ball
        y1 = self.surf_y - b.r
        crosses = (b.x - self.net_x) * (x1 - self.net_x) < 0
        apex_y = max(b.r * 3, apex_y)
        vx = vy = 0.0
        for _ in range(12):
            vx, vy, _t = ballistic(b.x, b.y, x1, y1, apex_y, self.g)
            if not crosses or self._clears(b.x, b.y, vx, vy):
                break
            apex_y = max(b.r * 3, apex_y - self.H * 0.04)
        b.vx, b.vy = vx, vy

    def _drive(self, tx, ticks):
        """Golpe directo y fuerte que bota en tx: si choca la red, alarga el
        vuelo hasta que pase."""
        b = self.ball
        y1 = self.surf_y - b.r
        for _ in range(30):
            vx = (tx - b.x) / ticks
            vy = (y1 - b.y - 0.5 * self.g * ticks * ticks) / ticks
            if self._clears(b.x, b.y, vx, vy):
                b.vx, b.vy = vx, vy
                return
            ticks += 1.5
        self._send(tx, min(b.y, self.net_top) - self.H * 0.08)

    def _path(self, n=170):
        """Vuelo previsto: [(tick, x, y, vy, botes en el lado receptor, evento)]."""
        b = self.ball
        key = (self.st, b.x, b.y, b.vx, b.vy)
        if self._path_key == key:
            return self._path_val
        x, y, vx, vy = b.x, b.y, b.vx, b.vy
        rec = self.other(self.hitter) if self.hitter else None
        nb = self.bounces
        out = []
        for i in range(1, n):
            x, y, vx, vy, ev = self._step(x, y, vx, vy)
            if isinstance(ev, tuple) and self.side_of(ev[1]) == rec:
                nb += 1
            out.append((i, x, y, vy, nb, ev))
            if ev == "dead" or nb >= 2:
                break
        self._path_key, self._path_val = key, out
        return out

    # ── reglas ────────────────────────────────────────────────────────────
    def _lose(self, team, label):
        """Punto para el otro equipo."""
        if self.state != "rally":
            return
        self.state = "dead"
        self.second = False
        self.serve_at = self.st + 0.5
        self.point(self.other(team), label)

    def _serve_fault(self, label):
        """Saque malo: en tenis hay segundo saque; en ping-pong es punto."""
        if self.state != "rally":
            return
        if self.SECOND_SERVE and not self.second:
            self.second = True
            self.state = "dead"
            self.serve_at = self.st + 1.0
            self.say(label + " · " + tr("segundo saque"), 1.2, (1, 0.8, 0.5), y=self.H * 0.3)
            return
        if self.SECOND_SERVE:
            label = tr("¡Doble falta!")
        self.second = False
        self._lose(self.hitter, label)

    SECOND_SERVE = False

    def _let(self):
        self.state = "dead"
        self.serve_at = self.st + 1.0
        self.say(tr("¡Let! Se repite el saque"), 1.2, (0.8, 0.9, 1), y=self.H * 0.3)

    def _land(self, x):
        side = self.side_of(x)
        h = self.hitter
        if self.serve_stage == "own":
            if side == h:
                self.serve_stage = "box"
                self._serve_second_leg()
                return
            self._serve_fault(tr("¡El saque debe botar primero en tu lado!"))
            return
        if self.bounces == 0:
            if side == h:
                if self.serve_stage:
                    self._serve_fault(tr("¡A la red!"))
                else:
                    self._lose(h, tr("¡A la red!") if self.net_hit else tr("¡Botó en tu propio lado!"))
                return
            if self.serve_stage == "box":
                lo, hi = self.serve_box(side)
                if not lo <= x <= hi:
                    self._serve_fault(tr("¡Saque fuera!"))
                    return
                if self.net_touch:
                    self._let()
                    return
                self.serve_stage = None
            elif not self.in_bounds(x, side):
                self._lose(h, tr("¡Fuera!"))
                return
            self.bounces = 1
            return
        self._lose(self.other(h), tr("¡Doble bote!"))

    def _dead(self):
        h = self.hitter
        if self.serve_stage:
            self._serve_fault(tr("¡A la red!") if self.net_hit else tr("¡Saque fuera!"))
        elif self.bounces >= 1:
            self._lose(self.other(h), tr("¡No la devolvió!"))
        else:
            self._lose(h, tr("¡A la red!") if self.net_hit else tr("¡Fuera!"))

    def _on_hit(self, team, who):
        self.hitter = team
        self.last_by = who
        self.bounces = 0
        self.serve_stage = None
        self.net_touch = self.net_hit = False
        self.turn[team] += 1
        self.shot_id += 1

    # ── saque ─────────────────────────────────────────────────────────────
    def _new_serve(self):
        team = self.server_team
        m = self.members(team)
        who = m[self.serve_idx[team] % len(m)]
        self.server = who
        self.state = "serve"
        self.serve_phase = "hold"
        self.serve_at = self.st + 0.8
        self.serve_t0 = self.st
        self.hitter = None
        self.bounces = 0
        self.serve_stage = None
        self.net_touch = self.net_hit = False
        self.turn[team] = m.index(who)
        o = self.other(team)
        self.turn[o] = (self.score["you"] + self.score["pets"]) % len(self.members(o))
        b = self.ball
        b.vx = b.vy = 0.0
        b.x, b.y = self._serve_hand(who)
        if who == "you":
            if not self._told_serve:
                self._told_serve = True
                self.say(tr("Tu saque: empuja la pelota hacia la derecha cuando la lances (suave = corto, fuerte = largo)"),
                         3.0, (0.7, 1, 0.55), y=self.H * 0.22, size=0.55)
            else:
                self.say(tr("Sacas tú") + (" · " + tr("segundo saque") if self.second else ""),
                         1.2, (0.7, 1, 0.55), y=self.H * 0.22, size=0.55)
        elif team == "you":
            self.say(tr("Saca tu compañera"), 1.2, (0.6, 0.9, 1), y=self.H * 0.22, size=0.55)

    def _serve_hand(self, who):
        if who == "you":
            return self.you_serve_x(), self.surf_y - self.toss_base()
        p = who
        d = -1 if p.team == "pets" else 1
        return p.cx + d * p.w * 0.3, p.y - self.ball.r

    def you_serve_x(self):
        return self.x_lo - self.ball.r * 2

    def toss_base(self):
        return self.avg_h * 0.5

    def toss_h(self):
        return self.avg_h * 0.5

    def _serving(self, b):
        who = self.server
        if self.serve_phase == "hold":
            hx, hy = self._serve_hand(who)
            b.x, b.y = hx, hy
            if who != "you":
                who.face(self.net_x)
            if self.st >= self.serve_at:
                # lanzamiento hacia arriba (en ping-pong, al menos «16 cm»)
                b.vy = -math.sqrt(2 * self.g * self.toss_h())
                self.serve_phase = "toss"
                self.toss_y = hy
                if who != "you" and self.TOSS_JUMP:
                    who.jump(-9 * who.k)
            return
        b.vy += self.g
        b.y += b.vy
        if who == "you":
            if self._you_serve_contact(b):
                return
            if self.st > self.serve_t0 + 9:
                self._serve_shot("you", 0.55)         # 8 s sin sacar: saque flojo automático
                return
        elif b.vy > 0 and b.y >= self.toss_y - self.toss_h() * 0.35:
            # la mascota le pega al caer
            if chance(self.lv["fault"] * (1.5 if self.second else 1.0) if who.team == "pets" else 0.06):
                q = random.choice((random.uniform(0.05, 0.2), random.uniform(0.9, 1.0)))
            else:
                q = random.uniform(0.35, 0.8) if not self.second else random.uniform(0.35, 0.6)
            who.win._squash(1.12, 0.9)
            self._serve_shot(who.team, q)
            return
        if b.vy > 0 and b.y > self.toss_y + 2:
            # nadie le pegó: vuelve a la mano y se lanza otra vez
            self.serve_phase = "hold"
            self.serve_at = self.st + 0.4

    def _you_serve_contact(self, b):
        if self.mouse is None or self.mvx < 2 * self.S:
            return False
        reach = b.r + self.FOOT * self.S
        if math.hypot(b.x - self.mouse[0], b.y - self.mouse[1]) > reach + abs(self.mvx) * 0.5:
            return False
        q = min(1.0, self.mvx / (self.SERVE_REF * self.S))
        self._serve_shot("you", q)
        return True

    TOSS_JUMP = False

    def _serve_depth(self, q):
        """q (fuerza del saque, 0-1) → profundidad f: <0 red, 0-1 buena, >1 fuera."""
        if q < 0.25:
            return -1.0
        if q > 0.86:
            return 1.0 + (q - 0.86) * 2 + 0.06
        return 0.06 + (q - 0.25) / 0.61 * 0.9

    def _serve_shot(self, team, q):
        b = self.ball
        d = 1 if team == "you" else -1
        f = self._serve_depth(q)
        self.serve_f = f
        server = self.server
        self._on_hit(team, server)
        self.state = "rally"
        if self.SERVE_OWN_BOUNCE:
            self.serve_stage = "own"
            lo, hi = self.serve_box(team)
            own_x = (lo + hi) / 2 + d * (hi - lo) * 0.15
            vx, vy, _t = ballistic(b.x, b.y, own_x, self.surf_y - b.r, b.y - 2, self.g)
            b.vx, b.vy = vx, vy
        else:
            self.serve_stage = "box"
            self._serve_leg(team, f)

    def _serve_second_leg(self):
        self._serve_leg(self.hitter, self.serve_f)

    def _serve_leg(self, team, f):
        """Tramo del saque que pasa (o no) la red hacia el lado rival."""
        b = self.ball
        d = 1 if team == "you" else -1
        lo, hi = self.serve_box(self.other(team))
        near, far = (lo, hi) if d > 0 else (hi, lo)
        if f < 0:
            # a la red: vuelo bajo que la choca
            tx = self.net_x + d * abs(far - near) * 0.3
            vx, vy, _t = ballistic(b.x, b.y, tx, self.surf_y - b.r,
                                   self.net_top + (self.surf_y - self.net_top) * 0.3, self.g)
            b.vx, b.vy = vx, vy
            return
        tx = near + (far - near) * f
        self.serve_kick(tx)

    def serve_kick(self, tx):
        self._send(tx, self.net_top - self.H * random.uniform(0.03, 0.09))

    # ── tick ──────────────────────────────────────────────────────────────
    def update(self, now):
        self.st += DT
        b = self.ball
        if self.state == "dead":
            self._idle(None)
            if self.st >= self.serve_at:
                self._new_serve()
            return
        if self.state == "serve":
            self._idle(self.server if self.server != "you" else None)
            self._serving(b)
            return
        b.x, b.y, b.vx, b.vy, ev = self._step(b.x, b.y, b.vx, b.vy)
        b.spin = (b.spin + math.degrees(b.vx / max(1.0, b.r)) * 0.5) % 360
        if ev == "tape":
            self.net_touch = True
        elif ev == "net":
            self.net_touch = self.net_hit = True
        if isinstance(ev, tuple):
            self._land(ev[1])
        elif ev == "dead":
            self._dead()
        if self.state != "rally":
            return
        self._you(b)
        if self.state == "rally":
            self._ai("pets")
        if self.state == "rally" and self.helper:
            self._ai("you")

    # ── tú ────────────────────────────────────────────────────────────────
    def _you(self, b):
        if b.x >= self.net_x or not self.can_hit("you", "you") or not self.ball_allowed("you"):
            return
        if self._paddle_hit(b):
            if self.on_surface(b.x) and b.y > self.surf_y - b.r:
                b.y = self.surf_y - b.r                    # nunca dentro de la mesa
            self._on_hit("you", "you")

    # ── tu paleta ─────────────────────────────────────────────────────────
    def on_scroll(self, dy):
        """La rueda inclina tu paleta: hacia arriba, la cabeza a la derecha
        (cara cerrada: la pelota sale baja); hacia abajo, a la izquierda (cara
        abierta: sale alta)."""
        step = -1 if dy > 0 else 1
        self.you_tilt = max(-self.TILT_MAX, min(self.TILT_MAX, self.you_tilt + step * self.TILT_STEP))

    def you_racket_r(self):
        return max(7 * self.S, 0.13 * self.avg_h)

    def blade_t(self, r):
        """Grosor de la lámina vista de perfil (cada deporte la dibuja)."""
        return max(4 * self.S, r * 0.34)

    def _paddle_hit(self, b):
        """La zona de golpe es la LÁMINA recta de tu paleta (un segmento
        girado según la inclinación). La pelota rebota en su cara: el ángulo
        de la paleta decide hacia dónde sale y tu movimiento le da la fuerza.
        El choque barre el camino del cursor en el tick (un golpe rápido no
        la atraviesa)."""
        if self.mouse is None or not self.ball_reachable(b):
            return False
        if math.hypot(self.mvx, self.mvy) > 4 * self.SWING_REF * self.S:
            return False        # el cursor SALTÓ (lo reubicó el sistema): no es un golpe
        r = self.you_racket_r()
        half_l, reach = r, b.r + self.blade_t(r) / 2
        th = math.radians(self.you_tilt)
        ax, ay = math.sin(th), -math.cos(th)            # a lo largo de la lámina
        nx, ny = math.cos(th), math.sin(th)              # la cara (hacia la red)
        ex, ey = self.mouse
        sx, sy = ex - self.mvx, ey - self.mvy
        n = max(1, min(10, int(math.hypot(self.mvx, self.mvy) / max(1.0, b.r)) + 1))
        for i in range(n + 1):
            k = i / n
            cx, cy = sx + (ex - sx) * k, sy + (ey - sy) * k
            dx, dy = b.x - cx, b.y - cy
            along = max(-half_l, min(half_l, dx * ax + dy * ay))
            px, py = cx + ax * along, cy + ay * along     # punto de la lámina más cercano
            if math.hypot(b.x - px, b.y - py) < reach:
                break
        else:
            return False
        # golpe en movimiento: sale hacia donde avanza la cara (aunque en este
        # tick la lámina ya haya pasado el centro); quieta, según el lado
        mv_n = self.mvx * nx + self.mvy * ny
        if abs(mv_n) > 1.0 * self.S:
            side = 1.0 if mv_n > 0 else -1.0
        else:
            side = 1.0 if (b.x - px) * nx + (b.y - py) * ny >= 0 else -1.0
        fx, fy = nx * side, ny * side
        b.x, b.y = px + fx * reach, py + fy * reach
        # rebote en la cara: la pelota devuelve parte de su velocidad y suma
        # la del golpe (solo la componente hacia donde mira la cara)
        vin = b.vx * fx + b.vy * fy
        swing = max(0.0, self.mvx * fx + self.mvy * fy)
        if vin >= 0 and swing <= 0:
            return False                                # se alejan: no hay golpe
        out = max(0.0, -vin) * self.PADDLE_E + swing * self.SWING_K
        tx_, ty_ = b.vx - vin * fx, b.vy - vin * fy     # lo que no va contra la cara
        b.vx = tx_ * 0.5 + fx * out
        b.vy = ty_ * 0.5 + fy * out - swing * self.LIFT
        cap = self.MAX_BALL * self.S * self.YOU_CAP
        sp = math.hypot(b.vx, b.vy)
        if sp > cap:
            b.vx, b.vy = b.vx * cap / sp, b.vy * cap / sp
        if b.vx > 0.5 * self.S:
            self._depth_by_swing(b, swing)
        b.x = min(max(b.x, b.r), self.W - b.r)
        return True

    SWING_REF = 36.0         # golpe «a fondo» (px/tick a 1080p): cae junto a la línea

    def _depth_by_swing(self, b, swing):
        """El ángulo de salida lo da la cara de la paleta; la FUERZA del golpe
        decide lo largo: suave cae cerca de la red, normal a media mesa y a
        tope junto a la línea de fondo (más que eso se va larga). Si con ese
        ángulo no pasa la red, va a la red (eso no se corrige)."""
        q = swing / (self.SWING_REF * self.S)
        half = self.x_hi - self.net_x
        depth = 0.2 + 0.75 * min(q, 1.0) + max(0.0, q - 1.0) * 0.4
        tx = self.net_x + half * (depth + random.gauss(0, 0.05))   # nadie es perfecto
        ux, uy = b.vx, b.vy
        n = math.hypot(ux, uy)
        ux, uy = ux / n, uy / n
        y1 = self.surf_y - b.r

        def land_x(v):
            # vuelo sin la red: dónde vuelve a la altura de la superficie
            x, y, vx, vy = b.x, b.y, ux * v, uy * v
            for _ in range(400):
                vy += self.g
                x += vx
                y += vy
                if vy > 0 and y >= y1:
                    return x
            return x
        lo, hi = 1.0 * self.S, self.MAX_BALL * self.S
        if land_x(hi) < tx:
            v = hi                                      # ni a tope llega: lo más fuerte
        else:
            for _ in range(24):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if land_x(mid) < tx else (lo, mid)
            v = (lo + hi) / 2
        b.vx, b.vy = ux * v, uy * v

    # ── IA (mascotas rivales y tu compañera) ──────────────────────────────
    def _racket_pos(self, p):
        d = -1 if p.team == "pets" else 1
        rr = self.racket_r(p)
        return p.cx + d * (p.w * 0.38 + rr * 0.6), self.hand_y(p) - rr * 0.4

    def _chasers(self, team, path):
        ais = [m for m in self.members(team) if m != "you"]
        if not ais:
            return []
        if self.ALTERNATE:
            nh = self.next_hitter(team)
            return [nh] if nh != "you" else []
        if team == "you" and self.mouse is not None:
            # tu compañera solo va a por las que te quedan lejos
            tgt = self._first_hit_x(team, path)
            if tgt is not None and abs(tgt - self.mouse[0]) < (self.net_x - self.x_lo) * 0.35:
                return []
            return ais
        tgt = self._first_hit_x(team, path)
        if tgt is None:
            return []
        return [min(ais, key=lambda p: abs(p.cx - tgt))]

    def _first_hit_x(self, team, path):
        for (_i, x, _y, _vy, nb, _ev) in path:
            if self.side_of(x) == team and nb >= 1:
                return x
        return None

    def _ai(self, team):
        if self.hitter == team:
            self._idle_team(team)
            return
        b = self.ball
        path = self._path()
        # ¿se va fuera? las listas la dejan pasar
        first = next((ev for (_i, _x, _y, _vy, _nb, ev) in path
                      if isinstance(ev, tuple) or ev == "dead"), None)
        out = first is None or first == "dead" or not self.in_bounds(first[1], team) \
            or (self.serve_stage == "box" and not
                self.serve_box(team)[0] <= first[1] <= self.serve_box(team)[1])
        if self.serve_stage == "own":
            out = False
        if out and self.bounces == 0:
            key = (team, self.shot_id)
            if key not in self._let_go:
                self._let_go[key] = chance(self.lv["read"])
            if self._let_go[key]:
                self._idle_team(team)
                return
        chasers = self._chasers(team, path)
        for m in self.members(team):
            if m != "you" and m not in chasers:
                self._go_home(m)
        for p in chasers:
            self._chase(p, team, path, b)
            if self.state != "rally" or self.hitter == team:
                break

    def _chase(self, p, team, path, b):
        d = -1 if p.team == "pets" else 1
        sp = self.RUN * self.S * self.lv["speed"] * max(0.9, min(1.3, p.k))
        bounds = (self.net_x + self.net_w, self.W) if p.team == "pets" else (0, self.net_x - self.net_w)
        rr = self.racket_r(p)
        off = p.w * 0.38 + rr * 0.6
        ry0 = p.floor_top + (self.hand_y(p) - p.y) - rr * 0.4     # paleta, de pie
        band = rr * 2.0 + b.r
        jump_top = ry0 - p.h * 0.9
        pick, best = None, -1e9
        volley_zone = (self.x_hi - self.net_x) * 0.4
        for (i, x, y, vy, nb, ev) in path:
            if self.side_of(x) != team:
                continue
            ok = nb >= 1 or (self.VOLLEY_OK and self.serve_stage is None and nb == 0
                             and abs(x - self.net_x) < volley_zone)
            if not ok:
                continue
            # a la altura de la paleta, o más alta (saltando)
            if not (abs(y - ry0) <= band or jump_top <= y < ry0):
                continue
            slack = sp * i + rr - abs((x - d * off) - p.cx)
            if slack >= sp * 4:                     # llega con tiempo y la espera
                pick = (x, y)
                break
            if slack > best:
                pick, best = (x, y), slack          # no llega a ninguna: la que menos le falte
        if pick is not None:
            p.run_to(pick[0] - d * off, sp, bounds)
        p.face(self.net_x)
        # golpe
        rx, ry = self._racket_pos(p)
        if p.cool > 0 or not self.can_hit(team, p) or not self.ball_allowed(team):
            return
        if p.on_ground and abs(b.x - rx) < rr * 3 + abs(b.vx) * 5:
            # salta solo si el vuelo previsto pasa POR ENCIMA de la raqueta
            yx = next((y for (_i, x, y, _vy, _nb, _ev) in path if (x - rx) * (b.x - rx) <= 0), None)
            if yx is not None and yx < ry - band:
                need = (ry - yx) + rr
                p.jump(-math.sqrt(2 * 1.3 * self.S * min(need, p.h * 1.1)))
        ex, ey = rr + b.r + 6 * self.S, band
        if ((b.x - rx) / ex) ** 2 + ((b.y - ry) / ey) ** 2 > 1.0:
            return
        if not chance(self._hit_p(p)):
            p.cool = 20
            p.win._squash(1.1, 0.92)
            return
        self._ai_shot(p, team)

    def _hit_p(self, p):
        sp = math.hypot(self.ball.vx, self.ball.vy) / max(1e-6, self.S)
        hard = min(0.12, max(0.0, (sp - 18) / 70))
        return self.lv["skill"] - hard if p.team == "pets" else 0.86 - hard

    def _weak_spot(self, lo, hi, defenders, sharp):
        """Un sitio entre lo y hi lejos de quien defiende (más listas = más lejos)."""
        best, best_d = None, -1.0
        for _ in range(6):
            x = random.uniform(lo, hi)
            dd = min((abs(x - dx) for dx in defenders), default=hi - lo)
            dd += random.uniform(0, (hi - lo) * (1 - sharp) * 0.6)
            if dd > best_d:
                best, best_d = x, dd
        return best

    def _ai_shot(self, p, team):
        """La mascota devuelve: elige golpe y sitio."""
        b = self.ball
        o = self.other(team)
        lo, hi = (self.x_lo, self.net_x) if o == "you" else (self.net_x, self.x_hi)
        half = hi - lo
        near, far = (hi, lo) if o == "you" else (lo, hi)
        defenders = []
        if o == "you":
            if self.mouse is not None:
                defenders.append(self.mouse[0])
            if self.helper:
                defenders.append(self.helper.cx)
        else:
            defenders = [r.cx for r in self.rivals]
        a, z = sorted((near + (far - near) * 0.15, near + (far - near) * 0.95))
        tx = self._weak_spot(a, z, defenders, self.lv["skill"] if p.team == "pets" else 0.6)
        err = self.lv["err"] if p.team == "pets" else 0.1
        bad = chance(err)
        s = 1 if far > near else -1
        if bad and chance(0.5):
            tx = far + s * half * random.uniform(0.05, 0.25)       # se va larga
            bad = "long"
        self._on_hit(team, p)
        p.win._squash(1.14, 0.88)
        p.tilt = self.TILT_MAX * 0.8 * s      # la paleta barre hacia donde la manda
        high = b.y < self.net_top - self.avg_h * 0.4
        if bad is True:
            # a la red
            vx, vy, _t = ballistic(b.x, b.y, self.net_x + s * half * 0.2, self.surf_y - b.r,
                                   self.net_top + (self.surf_y - self.net_top) * 0.4, self.g)
            b.vx, b.vy = vx, vy
            return
        if high and chance(self.lv["smash"]):
            sp = random.uniform(*self.SMASH) * self.S * self.lv["power"]
            self._drive(tx, max(10.0, abs(tx - b.x) / sp))
            self.say(tr("¡Remate!"), 0.8, (1, 0.6, 0.45) if p.team == "pets" else (0.6, 0.9, 1),
                     x=p.cx, y=p.y - 30 * self.S, size=0.55)
            return
        self.shot(p, tx, near, far)

    def shot(self, p, tx, near, far):
        self._send(tx, self.net_top - self.H * random.uniform(0.05, 0.18))

    # ── posiciones de espera ──────────────────────────────────────────────
    def _go_home(self, p):
        i = self.rivals.index(p) if p in self.rivals else 0
        hx = self.home_x(p, i)
        if p.team == "you":
            hx = self.net_x - (hx - self.net_x)
        bounds = (self.net_x + self.net_w, self.W) if p.team == "pets" else (0, self.net_x - self.net_w)
        p.run_to(hx, self.RUN * 0.75 * self.S * self.lv["speed"] * max(0.9, min(1.3, p.k)), bounds)
        p.face(self.net_x)

    def _idle_team(self, team):
        for m in self.members(team):
            if m != "you":
                self._go_home(m)

    def _idle(self, skip):
        for m in self.rivals + ([self.helper] if self.helper else []):
            if m is not skip:
                self._go_home(m)
            else:
                m.face(self.net_x)

    # ── dibujo ────────────────────────────────────────────────────────────
    def draw_extra(self, cr):
        for p in self.players:
            rx, ry = self._racket_pos(p)
            # recta en reposo; tras golpear vuelve poco a poco a vertical
            p.tilt = self.tilt_to(getattr(p, "tilt", 0.0), 0.0, 0.12)
            self.draw_racket(cr, rx, ry, self.racket_r(p), p.tilt, p.team == "pets")
        if self.mouse is not None and self.mouse[0] < self.net_x:
            # inclinada con la rueda del mouse (como la aguja de un transportador)
            self.draw_racket(cr, self.mouse[0], self.mouse[1], self.you_racket_r(),
                             self.you_tilt, False, alpha=0.8)

    def draw_racket(self, cr, x, y, r, tilt, rival, alpha=1.0):
        """Dibuja la paleta con la cara en (x, y), inclinada tilt grados
        (positivo = la cabeza hacia la derecha)."""
        pass
