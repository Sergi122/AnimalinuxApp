"""
🏓 Ping-pong (reglas de la ITTF), con la mesa vista de lado en el centro de
la pantalla. Tú a la izquierda (tu cursor es la paleta), las mascotas a la
derecha.

  - Saque: la pelota se lanza hacia arriba (como los 16 cm de la regla) y,
    al golpearla, bota PRIMERO en tu lado y luego en el del rival. Si roza la
    red y cae bien es «let»: se repite, sin límite.
  - Peloteo: tiene que pasar la red y botar UNA vez en el lado rival. No se
    puede pegar antes de que bote (tu paleta la atraviesa hasta el bote).
  - Partido «a puntos» = un juego a 11 con 2 de diferencia. Cada uno saca 2
    veces seguidas; desde 10-10, de a 1.
  - Dobles (con compañera): los del mismo equipo pegan POR TURNOS.
"""
import math
import random

from ..i18n import N_, tr
from .racket import RacketMatch

LEVELS = {
    # skill: prob. de devolverla al alcanzarla · err: golpe malo (red/larga)
    # read: dejar pasar una que se va fuera · fault: saque malo
    "easy":   {"skill": 0.72, "speed": 0.88, "power": 0.92, "err": 0.16, "smash": 0.35,
               "read": 0.45, "fault": 0.1, "attack": 0.3},
    "medium": {"skill": 0.85, "speed": 1.02, "power": 1.08, "err": 0.08, "smash": 0.6,
               "read": 0.75, "fault": 0.05, "attack": 0.55},
    "hard":   {"skill": 0.94, "speed": 1.22, "power": 1.22, "err": 0.05, "smash": 0.85,
               "read": 0.92, "fault": 0.02, "attack": 0.8},
}


class PingPong(RacketMatch):
    SPORT = "pingpong"
    BALL = "pingpong"
    HOWTO = N_("Tu cursor es la paleta: devuélvela a su lado después del bote")
    SERVE_OWN_BOUNCE = True
    ALTERNATE = True
    E = 0.9                  # mesa dura: rebota casi con el mismo ángulo
    FRIC = 0.97
    MAX_BALL = 22.0
    SERVE_REF = 24.0
    LEVELS = LEVELS

    def setup(self):
        s = self.S
        self.ball.r = max(7, round(10 * s))
        self.g = 0.3 * s
        tw = min(self.W * 0.56, max(self.W * 0.4, self.avg_h * 7))
        self.net_x = self.W / 2
        self.x_lo, self.x_hi = self.net_x - tw / 2, self.net_x + tw / 2
        self.surf_y = self.F - max(0.55 * self.avg_h, 40 * s)      # tablero
        self.net_top = self.surf_y - max(0.22 * self.avg_h, 18 * s)
        self.net_w = max(3, 4 * s)
        self.setup_common()

    def on_surface(self, x):
        return self.x_lo <= x <= self.x_hi

    @property
    def limit_y(self):
        return max(self.H * 0.12, self.surf_y - 2.6 * self.avg_h)

    def home_x(self, p, i):
        # esperan algo separadas de la mesa (la pelota sale larga tras el bote)
        return min(self.W - p.w * 0.6, self.x_hi + p.w * 0.6 + self.W * 0.05 + p.w * 0.9 * i)

    def you_serve_x(self):
        return self.x_lo - self.ball.r * 3

    def toss_base(self):
        return self.avg_h * 0.25

    def toss_h(self):
        return max(self.avg_h * 0.45, 30 * self.S)

    def racket_r(self, p):
        return max(6 * self.S, 0.11 * p.h)

    def shot(self, p, tx, near, far):
        b = self.ball
        if p.team == "pets" and random.random() < self.lv["attack"]:
            # golpe de ataque: rápido y plano
            sp = random.uniform(11, 16) * self.S * self.lv["power"]
            self._drive(tx, max(12.0, abs(tx - b.x) / sp))
            return
        if random.random() < 0.18:
            # corta, cerca de la red
            tx = near + (far - near) * random.uniform(0.12, 0.3)
            self._send(tx, self.net_top - self.H * random.uniform(0.02, 0.05))
            return
        self._send(tx, self.net_top - self.H * random.uniform(0.04, 0.14))

    # ── tanteo ────────────────────────────────────────────────────────────
    def award(self, who):
        self.score[who] += 1
        y, p = self.score["you"], self.score["pets"]
        total = y + p
        k = total // 2 if not (y >= 10 and p >= 10) else 10 + (total - 20)
        new = "you" if k % 2 == 0 else "pets"
        if new != self.server_team:
            self.serve_idx[new] += 1 if total > 0 else 0
        self.server_team = new
        return self.mode == "points" and max(y, p) >= 11 and abs(y - p) >= 2

    def board_sub(self):
        srv = tr("saque: tú") if self.server_team == "you" else tr("saque: mascotas")
        if self.mode == "time":
            return super().board_sub() + " · " + srv
        return tr("juego a 11") + " · " + srv

    # ── dibujo ────────────────────────────────────────────────────────────
    def draw_field(self, cr):
        s = self.S
        x0, x1, y = self.x_lo, self.x_hi, self.surf_y
        th = max(5, 9 * s)
        # patas
        cr.set_source_rgba(0.16, 0.17, 0.22, 0.9)
        for lx in (x0 + (x1 - x0) * 0.08, x1 - (x1 - x0) * 0.08):
            cr.rectangle(lx - 4 * s, y + th, 8 * s, self.F - y - th)
        cr.fill()
        # tablero azul con borde blanco arriba
        cr.set_source_rgba(0.1, 0.3, 0.62, 0.97)
        cr.rectangle(x0, y, x1 - x0, th)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.rectangle(x0, y - 1.5 * s, x1 - x0, 2.5 * s)
        cr.fill()
        # red: postes, malla y cinta
        nx, top = self.net_x, self.net_top
        cr.set_source_rgba(0.08, 0.09, 0.14, 0.75)
        cr.rectangle(nx - 2 * s, top, 4 * s, y - top)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.rectangle(nx - 2.5 * s, top - 2 * s, 5 * s, 3.5 * s)
        cr.fill()
        # tu mitad / la suya
        cr.set_source_rgba(0.45, 0.8, 1, 0.8)
        cr.rectangle(0, self.F - 4, nx, 4)
        cr.fill()
        cr.set_source_rgba(1, 0.55, 0.7, 0.8)
        cr.rectangle(nx, self.F - 4, self.W - nx, 4)
        cr.fill()

    def draw_racket(self, cr, x, y, r, tilt, rival, alpha=1.0):
        """Paleta DE PERFIL (la mesa se ve de lado): una lámina delgada con
        goma roja de un lado y negra del otro, y el mango en línea debajo."""
        cr.save()
        cr.translate(x, y)
        cr.rotate(math.radians(tilt))
        t = self.blade_t(r)                          # grosor de la lámina
        # mango (madera) y su tope
        cr.set_source_rgba(0.62, 0.42, 0.22, alpha)
        cr.rectangle(-t * 0.42, r * 0.95, t * 0.84, r * 0.8)
        cr.fill()
        cr.set_source_rgba(0.45, 0.3, 0.16, alpha)
        cr.rectangle(-t * 0.5, r * 1.75, t, r * 0.14)
        cr.fill()
        # lámina: madera al centro, goma a cada lado
        cr.set_source_rgba(0.85, 0.7, 0.5, alpha)
        cr.rectangle(-t * 0.18, -r, t * 0.36, r * 1.95)
        cr.fill()
        front, back = ((0.78, 0.12, 0.16), (0.1, 0.1, 0.12)) if rival else ((0.1, 0.1, 0.12), (0.78, 0.12, 0.16))
        cr.set_source_rgba(*back, alpha)
        cr.rectangle(-t * 0.5, -r, t * 0.32, r * 1.95)
        cr.fill()
        cr.set_source_rgba(*front, alpha)
        cr.rectangle(t * 0.18, -r, t * 0.32, r * 1.95)
        cr.fill()
        cr.restore()
