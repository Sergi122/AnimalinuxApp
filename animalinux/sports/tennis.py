"""
🎾 Tenis (reglas de la ITF), la cancha de lado sobre el suelo de la pantalla.
Tú a la izquierda (tu cursor es la raqueta), las mascotas a la derecha.

  - Saque: dos intentos. Tiene que caer en el CUADRO DE SAQUE del rival
    (entre la red y la línea de saque); si no, falta; dos faltas = doble falta
    y punto. Si roza la red y cae en el cuadro, «let»: se repite ese saque.
    Durante todo un juego saca el mismo; al siguiente juego, el otro equipo.
  - El saque hay que dejarlo botar; en el peloteo se puede volear (pegar sin
    bote). Bota una sola vez y tiene que caer dentro de la cancha rival.
  - Tanteo: 0, 15, 30, 40, juego; en 40-40 «deuce»: ventaja y juego (dos
    seguidos). Partido «a puntos» = un set a 6 juegos con 2 de diferencia y
    tie-break a 7 en 6-6 (el primer punto lo saca uno, luego de a 2).
    Partido por tiempo: gana quien lleve más juegos.
  - Dobles (con compañera): cualquiera de las dos puede pegarle.
"""
import math
import random

from ..i18n import N_, tr
from .racket import RacketMatch

LEVELS = {
    "easy":   {"skill": 0.86, "speed": 0.92, "power": 0.92, "err": 0.14, "smash": 0.4,
               "read": 0.45, "fault": 0.15, "lob": 0.1, "attack": 0.25},
    "medium": {"skill": 0.95, "speed": 1.15, "power": 1.08, "err": 0.07, "smash": 0.65,
               "read": 0.75, "fault": 0.08, "lob": 0.14, "attack": 0.45},
    "hard":   {"skill": 0.98, "speed": 1.28, "power": 1.22, "err": 0.035, "smash": 0.85,
               "read": 0.92, "fault": 0.04, "lob": 0.18, "attack": 0.6},
}
CALLS = ("0", "15", "30", "40")


class Tennis(RacketMatch):
    SPORT = "tennis"
    BALL = "tennis"
    HOWTO = N_("Tu cursor es la raqueta: devuélvela a su cancha (puedes volear)")
    VOLLEY_OK = True
    SECOND_SERVE = True
    TOSS_JUMP = True
    E = 0.78                 # sale con un ángulo parecido al de llegada
    FRIC = 0.9
    MAX_BALL = 26.0
    SMASH = (22.0, 28.0)
    RUN = 11.0
    SERVE_REF = 28.0
    LEVELS = LEVELS

    def setup(self):
        s = self.S
        self.ball.r = max(9, round(13 * s))
        self.g = 0.34 * s
        self.surf_y = self.F
        m = max(self.W * 0.12, 110 * s)                 # espacio detrás de la línea de fondo
        self.x_lo, self.x_hi = m, self.W - m
        self.net_x = self.W / 2
        half = self.net_x - self.x_lo
        self.box = half * 0.54                         # red → línea de saque (6,4 m de 11,9)
        self.net_top = self.F - max(0.55 * self.avg_h, 44 * s)
        self.net_w = max(3, 4 * s)
        self.pts = {"you": 0, "pets": 0}
        self.games = {"you": 0, "pets": 0}
        self.tiebreak = False
        self.tb_first = "you"
        self.setup_common()

    @property
    def limit_y(self):
        return max(self.H * 0.15, self.F - 3.0 * self.avg_h)

    def serve_box(self, side):
        if side == "you":
            return self.net_x - self.box, self.net_x
        return self.net_x, self.net_x + self.box

    def home_x(self, p, i):
        half = self.x_hi - self.net_x
        if i % 2 == 1:
            return self.net_x + half * 0.35               # en dobles, una a la red
        return min(self.W - p.w * 0.6, self.x_hi + (self.W - self.x_hi) * 0.2)

    def you_serve_x(self):
        return max(self.ball.r * 3, self.x_lo - self.ball.r * 2)

    def toss_base(self):
        return self.avg_h * 1.1

    def toss_h(self):
        return self.avg_h * 0.7

    def racket_r(self, p):
        return max(8 * self.S, 0.17 * p.h)

    def serve_kick(self, tx):
        b = self.ball
        self._drive(tx, max(14.0, abs(tx - b.x) / (17 * self.S)))

    def shot(self, p, tx, near, far):
        b = self.ball
        r = random.random()
        if r < self.lv["lob"]:
            # globo alto y profundo
            tx = near + (far - near) * random.uniform(0.75, 0.95)
            self._send(tx, max(self.H * 0.14, self.limit_y - self.H * 0.08))
            return
        if r < self.lv["lob"] + 0.08:
            # dejada: cortita tras la red
            tx = near + (far - near) * random.uniform(0.08, 0.22)
            self._send(tx, self.net_top - self.H * 0.04)
            return
        if p.team == "pets" and r < self.lv["lob"] + 0.08 + self.lv["attack"]:
            # golpe ganador: fuerte y pegado a la línea de fondo
            tx = near + (far - near) * random.uniform(0.82, 0.97)
            sp = random.uniform(20, 25) * self.S * self.lv["power"]
            self._drive(tx, max(14.0, abs(tx - b.x) / sp))
            return
        sp = random.uniform(15, 20) * self.S * self.lv["power"]
        self._drive(tx, max(16.0, abs(tx - b.x) / sp))

    # ── tanteo ────────────────────────────────────────────────────────────
    def award(self, who):
        o = self.other(who)
        won_set = False
        if self.tiebreak:
            self.pts[who] += 1
            a, b = self.pts[who], self.pts[o]
            n = a + b
            # primer punto lo saca uno; luego de a 2
            self.server_team = self.tb_first if ((n + 1) // 2) % 2 == 0 else self.other(self.tb_first)
            if a >= 7 and a - b >= 2:
                self.games[who] += 1
                self.say(tr("¡Tie-break y set!"), 1.6, (1, 0.9, 0.4), y=self.H * 0.38)
                self.pts = {"you": 0, "pets": 0}
                self.tiebreak = False
                won_set = True
                self._next_game_server(self.other(self.tb_first))
        else:
            self.pts[who] += 1
            a, b = self.pts[who], self.pts[o]
            if a >= 4 and a - b >= 2:
                self.games[who] += 1
                self.pts = {"you": 0, "pets": 0}
                g, h = self.games[who], self.games[o]
                self.say(tr("Juego") + f"  {self.games['you']} – {self.games['pets']}", 1.4,
                         (1, 1, 1), y=self.H * 0.38, size=0.8)
                if self.mode == "points" and g >= 6 and g - h >= 2:
                    won_set = True
                self._next_game_server()
                if self.mode == "points" and g == 6 and h == 6:
                    self.tiebreak = True
                    self.tb_first = self.server_team
                    self.say(tr("¡Tie-break! A 7 puntos"), 1.6, (1, 0.85, 0.4), y=self.H * 0.44)
        self.score = dict(self.games)
        return self.mode == "points" and won_set

    def _next_game_server(self, team=None):
        """Cambia el saque al otro equipo (en dobles, saca la otra del equipo)."""
        team = team or self.other(self.server_team)
        self.serve_idx[team] += 1
        self.server_team = team

    def call(self):
        y, p = self.pts["you"], self.pts["pets"]
        if self.tiebreak:
            return tr("Tie-break {a} – {b}", a=y, b=p)
        if y >= 3 and p >= 3:
            if y == p:
                return tr("Iguales (deuce)")
            return tr("Ventaja tú") if y > p else tr("Ventaja mascotas")
        return f"{CALLS[min(y, 3)]} – {CALLS[min(p, 3)]}"

    def board_sub(self):
        srv = tr("saque: tú") if self.server_team == "you" else tr("saque: mascotas")
        head = super().board_sub() if self.mode == "time" else tr("1 set a 6 juegos")
        return f"{self.call()}   ·   {head} · {srv}"

    # ── dibujo ────────────────────────────────────────────────────────────
    def draw_field(self, cr):
        s = self.S
        F = self.F
        # piso de la cancha (pista dura azul) con líneas blancas
        cr.set_source_rgba(0.16, 0.38, 0.62, 0.85)
        cr.rectangle(self.x_lo, F - 6 * s, self.x_hi - self.x_lo, 6 * s)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.95)
        for x in (self.x_lo, self.x_hi):                  # líneas de fondo
            cr.rectangle(x - 2 * s, F - 14 * s, 4 * s, 14 * s)
        for x in (self.net_x - self.box, self.net_x + self.box):   # líneas de saque
            cr.rectangle(x - 1.5 * s, F - 9 * s, 3 * s, 9 * s)
        cr.fill()
        # cuadros de saque (marca suave)
        cr.set_source_rgba(1, 1, 1, 0.12)
        cr.rectangle(self.net_x - self.box, F - 6 * s, 2 * self.box, 6 * s)
        cr.fill()
        # red: poste, malla oscura translúcida y cinta blanca
        nx, top = self.net_x, self.net_top
        cr.set_source_rgba(0.08, 0.09, 0.14, 0.55)
        cr.rectangle(nx - 3 * s, top, 6 * s, F - top)
        cr.fill()
        cr.set_source_rgba(0.75, 0.77, 0.82, 0.95)
        cr.rectangle(nx - 1.2 * s, top, 2.4 * s, F - top)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.97)
        cr.rectangle(nx - 3.5 * s, top - 2 * s, 7 * s, 4 * s)
        cr.fill()

    def blade_t(self, r):
        return max(4.5 * self.S, r * 0.36)

    def draw_racket(self, cr, x, y, r, tilt, rival, alpha=1.0):
        """Raqueta DE PERFIL (la cancha se ve de lado): el aro visto de canto
        es una barra larga y redondeada, luego el cuello fino y el mango."""
        cr.save()
        cr.translate(x, y)
        cr.rotate(math.radians(tilt))
        t = self.blade_t(r)                          # grosor del aro de canto
        col = (0.85, 0.25, 0.3) if rival else (0.25, 0.45, 0.9)
        # cuello (la «V» del aro vista de lado es una varilla)
        cr.set_source_rgba(*col, alpha)
        cr.rectangle(-t * 0.18, r * 1.05, t * 0.36, r * 0.5)
        cr.fill()
        # mango con grip oscuro y tope
        cr.set_source_rgba(0.15, 0.13, 0.18, alpha)
        cr.rectangle(-t * 0.32, r * 1.5, t * 0.64, r * 0.85)
        cr.fill()
        cr.rectangle(-t * 0.42, r * 2.32, t * 0.84, r * 0.12)
        cr.fill()
        # aro de canto: barra con puntas redondas y una línea de cuerdas
        h = r * 1.05
        cr.new_sub_path()
        cr.arc(0, -h + t / 2, t / 2, math.pi, 0)
        cr.arc(0, h - t / 2, t / 2, 0, math.pi)
        cr.close_path()
        cr.set_source_rgba(*col, alpha)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.6 * alpha)
        cr.set_line_width(1)
        cr.move_to(0, -h + t * 0.6)
        cr.line_to(0, h - t * 0.6)
        cr.stroke()
        cr.restore()
