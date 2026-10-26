"""
⚽ Fútbol en línea, sobre el suelo de la pantalla.

  - Tu arco a la izquierda, el de las mascotas a la derecha.
  - El mouse NO agarra el balón: solo lo empuja. Cuanto más rápido lo
    empujas, más rápido sale.
  - 1 mascota: ataca y defiende. 2 a 4: una es arquera y el resto juega.
  - Opcional: una mascota tuya de arquera.
"""
import math
import random

from ..i18n import N_, tr
from .base import Match, chance

MAX_BALL = 46.0          # px/tick (escalado por S)


class Football(Match):
    SPORT = "football"
    BALL = "soccer"
    HOWTO = N_("Empuja el balón con el mouse hacia el arco de la derecha")
    FOOT = 34

    def setup(self):
        s = self.S
        self.GW = max(52 * s, self.W * 0.04)             # fondo del arco
        self.GH = max(1.45 * self.avg_h, self.H * 0.16)  # alto del arco
        self.g = 0.95 * s
        # roles: con 2+ rivales, la del arco es la más cercana a su arco
        if len(self.rivals) >= 2:
            keeper = max(self.rivals, key=lambda p: p.x)
            keeper.role = "keeper"
        for i, p in enumerate(r for r in self.rivals if r.role != "keeper"):
            p.role = "striker" if i == 0 else "defender"
        # colocar: rivales en su mitad, ayudante en tu arco
        for p in self.rivals:
            if p.role == "keeper":
                p.x = self.W - self.GW - p.w * 1.1
            else:
                p.x = random.uniform(self.W * 0.55, self.W * 0.8)
            p.y = p.floor_top
        if self.helper:
            self.helper.role = "helper"
            self.helper.x = self.GW + self.helper.w * 0.1
        self.kickoff()

    def kickoff(self, conceded=None):
        """Saque del centro: lo hace el equipo que recibió el gol (las
        mascotas lo tocan hacia tu campo; si sacas tú, el balón te espera)."""
        b = self.ball
        b.x, b.y = self.W / 2, self.F - b.r
        b.vy = 0.0
        if conceded == "pets":
            b.vx = -4.0 * self.S
        elif conceded == "you":
            b.vx = 0.0
        else:
            b.y = self.F - self.H * 0.45
            b.vx = random.uniform(-2, 2) * self.S

    # ── física del balón ──────────────────────────────────────────────────
    def update(self, now):
        b, s = self.ball, self.S
        b.vy += self.g
        b.vx *= 0.996
        b.x += b.vx
        b.y += b.vy
        # suelo
        if b.y + b.r >= self.F:
            b.y = self.F - b.r
            if b.vy > 2.5 * s:
                b.vy = -b.vy * 0.55
            else:
                b.vy = 0.0
            b.vx *= 0.985
        # techo
        if b.y - b.r < 0:
            b.y, b.vy = b.r, abs(b.vy) * 0.6
        self._goal_frames(b)
        # paredes (detrás de los arcos)
        if b.x - b.r < 0:
            b.x, b.vx = b.r, abs(b.vx) * 0.5
        if b.x + b.r > self.W:
            b.x, b.vx = self.W - b.r, -abs(b.vx) * 0.5
        b.spin = (b.spin + math.degrees(b.vx / b.r)) % 360

        # ¿gol? (el balón entero pasa la línea por debajo del travesaño)
        top = self.F - self.GH
        if b.x + b.r * 0.2 < self.GW and b.y > top:
            self.point("pets", tr("¡Gol de las mascotas!"))
            self.kickoff(conceded="you")
            return
        if b.x - b.r * 0.2 > self.W - self.GW and b.y > top:
            self.point("you", tr("¡GOOOL!"))
            self.kickoff(conceded="pets")
            return

        self.mouse_push(b, MAX_BALL * self.S)
        self._ai(b)

    def _goal_frames(self, b):
        """Travesaños: el balón rebota en ellos."""
        top = self.F - self.GH
        for x0, x1 in ((0, self.GW), (self.W - self.GW, self.W)):
            if x0 - b.r < b.x < x1 + b.r and abs(b.y - top) < b.r:
                if b.vy > 0 and b.y < top:
                    b.y, b.vy = top - b.r, -abs(b.vy) * 0.6
                elif b.vy < 0 and b.y > top:
                    b.y, b.vy = top + b.r, abs(b.vy) * 0.6

    # ── IA ────────────────────────────────────────────────────────────────
    def _ai(self, b):
        d, s = self.diff, self.S
        run = 6.2 * s * d["speed"]
        bounds = (0, self.W)
        for p in self.rivals:
            sp = run * p.k
            if p.role == "keeper":
                gx = self.W - self.GW
                lo, hi = gx - p.w * 2.4, gx - p.w * 0.2
                p.run_to(min(hi, max(lo, b.x)), sp * 0.9, (lo - p.w, hi + p.w))
                p.face(b.x)
                self._keeper_jump(p, b, toward=+1)
                self._kick(p, b, direction=-1, clear=True)
                continue
            if p.role == "defender":
                # entre el balón y su arco, salvo que el balón esté cerca
                if abs(b.x - p.cx) < p.w * 2.5 or b.x > self.W * 0.6:
                    self._attack(p, b, sp, bounds)
                else:
                    p.run_to((b.x + self.W - self.GW) / 2, sp * 0.8, bounds)
                    p.face(b.x)
                self._kick(p, b, direction=-1)
                continue
            self._attack(p, b, sp, bounds)
            self._kick(p, b, direction=-1)
        if self.helper:
            h = self.helper
            lo, hi = self.GW * 0.2, self.GW + h.w * 2.4
            h.run_to(min(hi, max(lo, b.x)), run * h.k * 0.9, (0, hi + h.w))
            h.face(b.x)
            self._keeper_jump(h, b, toward=-1)
            self._kick(h, b, direction=+1, clear=True)

    def _attack(self, p, b, sp, bounds):
        """Ir a por el balón entrando por su derecha (para patear a la izquierda)."""
        behind = b.x + b.r + p.w * 0.35
        if p.cx < b.x - b.r and abs(p.cx - b.x) < p.w * 1.6 and b.y > self.F - b.r * 3:
            p.jump(-12 * p.k * self.S ** 0.5)      # lo salta para ponerse detrás
        p.run_to(behind, sp, bounds)
        p.face(b.x)
        # salta a por balones altos cerca
        if b.y < p.y and abs(b.x - p.cx) < p.w and b.vy > 0 and chance(0.08):
            p.jump(-17 * p.k)

    def _keeper_jump(self, p, b, toward):
        """Arquero: salta a por balones altos que van hacia su arco."""
        coming = b.vx * toward > 2 * self.S
        if coming and b.y < p.y + p.h * 0.2 and abs(b.x - p.cx) < p.w * 2.2 \
                and chance(0.25 * self.diff["skill"] + 0.1):
            p.jump(-18 * p.k)

    def _kick(self, p, b, direction, clear=False):
        if p.cool > 0 or not p.touches(b, 2):
            return
        d = self.diff
        if clear:
            # los arqueros no lo atajan todo: tu ayudante ~55 %, la de ellas
            # según la dificultad
            save = 0.55 if p.role == "helper" else 0.4 + 0.45 * d["skill"]
            if not chance(save):
                p.cool = 22                       # se le escapó
                return
        power = (random.uniform(9, 14) if not clear else random.uniform(13, 18)) * self.S * d["power"]
        good_side = (b.x - p.cx) * direction > -p.w * 0.15
        if good_side or clear:
            b.vx = direction * power
            b.vy = -random.uniform(3, 11) * self.S * (1.3 if clear else 1.0)
            near_goal = (b.x < self.W * 0.4) if direction < 0 else (b.x > self.W * 0.6)
            if not clear and near_goal:
                # cerca del arco: disparo al arco, a media altura
                b.vy = -random.uniform(6, 13) * self.S
            if not clear and chance(d["skill"] * 0.5):
                b.vy = -random.uniform(1, 4) * self.S       # tiro rasante
        else:
            # le pegó con el cuerpo «al revés»: rebote corto
            b.vx = -direction * random.uniform(3, 6) * self.S
            b.vy = -random.uniform(2, 5) * self.S
        p.cool = 8
        p.win._squash(1.12, 0.9)

    # ── dibujo ────────────────────────────────────────────────────────────
    def draw_field(self, cr):
        top = self.F - self.GH
        for x0, x1, mine in ((0, self.GW, True), (self.W - self.GW, self.W, False)):
            # red
            cr.set_source_rgba(1, 1, 1, 0.22)
            cr.set_line_width(1)
            step = 12 * self.S
            y = top
            while y < self.F:
                cr.move_to(x0, y); cr.line_to(x1, y)
                y += step
            x = x0
            while x <= x1:
                cr.move_to(x, top); cr.line_to(x, self.F)
                x += step
            cr.stroke()
            # palos
            post = x1 if mine else x0
            cr.set_source_rgba(1, 1, 1, 0.95)
            cr.set_line_width(max(4, 7 * self.S))
            cr.move_to(post, self.F); cr.line_to(post, top)
            cr.line_to(x0 if mine else x1, top)
            cr.stroke()
            # color del dueño
            col = (0.45, 0.8, 1, 0.85) if mine else (1, 0.55, 0.7, 0.85)
            cr.set_source_rgba(*col)
            cr.rectangle(min(x0, x1), self.F - 4, abs(x1 - x0), 4)
            cr.fill()
