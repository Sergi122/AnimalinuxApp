"""
⚽ Fútbol en línea, sobre el suelo de la pantalla.

  - Tu arco a la izquierda, el de las mascotas a la derecha.
  - El mouse NO agarra el balón: solo lo empuja. Cuanto más rápido lo
    empujas, más rápido sale.
  - Como en el básquet, tu cursor tiene un límite de altura (la línea
    punteada): por encima de él no se puede tocar el balón.
  - 1 mascota: ataca y defiende. 2 a 4: una es arquera y el resto juega.
  - Opcional: una mascota tuya de arquera.
"""
import math
import random

from ..i18n import N_, tr
from .base import Match, chance

MAX_BALL = 46.0          # px/tick (escalado por S)


class Football(Match):
    SPORT_CHEER = (N_("¡Golazo!"), N_("¡Al fondo de la red!"), N_("¡Qué golazo!"))
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
    def _predict(self, b, ticks):
        """Dónde estará el balón dentro de `ticks` (misma física que update,
        sin travesaños): para anticipar en vez de correr detrás."""
        x, y, vx, vy = b.x, b.y, b.vx, b.vy
        for _ in range(int(ticks)):
            vy += self.g
            vx *= 0.996
            x += vx
            y += vy
            if y + b.r >= self.F:
                y = self.F - b.r
                vy = -vy * 0.55 if vy > 2.5 * self.S else 0.0
                vx *= 0.985
            if x - b.r < 0 or x + b.r > self.W:
                vx = -vx * 0.5
                x = min(max(x, b.r), self.W - b.r)
        return x, y

    def _ai(self, b):
        d, s = self.diff, self.S
        run = 8.8 * s * d["speed"]
        bounds = (0, self.W)
        lead = 4 + 12 * d["skill"]            # ticks que anticipan el balón
        field = [p for p in self.rivals if p.role != "keeper"]
        # la más cercana va a por el balón; las demás cubren
        chaser = min(field, key=lambda p: abs(p.cx - b.x)) if field else None
        danger = b.x > self.W * 0.7               # balón cerca de su arco
        for p in self.rivals:
            self._body_block(p, b)
        for p in self.rivals:
            sp = run * p.k
            if p.role == "keeper":
                gx = self.W - self.GW
                area = (gx - p.w * 3.6, self.W)
                if not self._aerial(p, b, sp, area):
                    self._keeper(p, b, sp)
                self._kick(p, b, direction=-1, clear=True)
                continue
            if self._aerial(p, b, sp, bounds):
                self._kick(p, b, direction=-1, clear_zone=danger)
                continue
            if p is chaser or danger or abs(b.x - p.cx) < p.w * 2.0:
                self._attack(p, b, sp, bounds, lead)
            elif b.x < self.W * 0.45:
                # apoyo: espera el rebote cerca de tu arco
                p.run_to(self.GW + self.W * 0.12 + p.w, sp * 0.9, bounds)
                p.face(b.x)
            else:
                self._cover(p, b, sp, bounds)
            self._kick(p, b, direction=-1, clear_zone=danger)
        if self.helper:
            h = self.helper
            lo, hi = self.GW * 0.2, self.GW + h.w * 2.4
            h.run_to(min(hi, max(lo, b.x)), run * h.k * 0.9, (0, hi + h.w))
            h.face(b.x)
            self._keeper_jump(h, b, toward=-1)
            self._kick(h, b, direction=+1, clear=True)

    JUMP = 18.0          # impulso de salto de las mascotas (× p.k)
    PG = 1.3             # gravedad de las mascotas (base: p.physics(1.3 * S))

    def _aerial(self, p, b, sp, bounds):
        """Balón alto que viene hacia su arco: calcula dónde y cuándo saltar
        para llegarle con la cabeza (o el cuerpo) y corre a ese punto."""
        s, d = self.S, self.diff
        if p.diving or b.vx <= 1.0 * s or b.y > p.y + p.h * 0.2:
            return False
        if not p.on_ground:
            return True                   # ya saltó: que siga su vuelo
        g = self.PG * s
        vj = -self.JUMP * p.k
        react = int(7 * (1 - d["skill"]))     # fácil: reacciona tarde
        x, y, vx, vy = b.x, b.y, b.vx, b.vy
        for t in range(1, 40):
            vy += self.g
            vx *= 0.996
            x += vx
            y += vy
            if y + b.r >= self.F or x > self.W:
                return False              # cae antes: lo resuelve el juego normal
            if t < react:
                continue
            if abs(x - p.cx) > sp * t + p.w * 0.5:
                continue                  # no llega corriendo
            # ¿a qué altura llega su cabeza tau ticks después de saltar?
            rise = p.y - (y + b.r * 0.5)      # cuánto debe subir la cabeza
            if rise <= 0:
                tau = 0.0
            else:
                disc = vj * vj - 2 * g * rise
                if disc < 0:
                    continue              # demasiado alto
                tau = (-vj - disc ** 0.5) / g
            tj = t - tau                  # tick en que hay que saltar
            if tj < -1:
                continue
            p.run_to(x, sp, bounds)
            p.face(b.x)
            if tj <= 1 and rise > 0:
                p.jump(vj)
            return True
        return False

    def _body_block(self, p, b):
        """El cuerpo tapa: un balón que va hacia su arco rebota en ella aunque
        no pueda patearlo (recién pateó o falló la atajada)."""
        if getattr(p, "leak", 0) > 0:
            p.leak -= 1                   # se le escapó: esta vez pasa
            return
        if p.cool <= 0 or b.vx <= 1.0 * self.S or not p.touches(b, 0):
            return
        if not chance(0.4 + 0.6 * self.diff["skill"]):
            p.leak = 6                    # no llegó a cerrarse: pasa
            return
        b.x = min(b.x, p.x + p.w * 0.12 - b.r)
        b.vx = -abs(b.vx) * random.uniform(0.3, 0.5)
        b.vy = min(b.vy, 0.0) - random.uniform(2, 5) * self.S

    def _cover(self, p, b, sp, bounds):
        """Cubrir: entre el balón y su arco (del lado del arco), lista para
        cortar un tiro o un pase largo."""
        goal = self.W - self.GW
        gap = max(p.w * 1.6, (goal - b.x) * 0.35)
        p.run_to(min(goal - p.w, b.x + gap), sp * 0.95, bounds)
        p.face(b.x)
        # corta balones altos que pasan por encima
        if b.vx > 2 * self.S and b.y < p.y and abs(b.x - p.cx) < p.w * 1.5 and chance(0.25):
            p.jump(-17 * p.k)

    def _keeper(self, p, b, sp):
        """Arquera: se para donde VA a llegar el balón y, si no lo alcanza
        corriendo, se lanza en plancha (según la dificultad)."""
        d = self.diff
        gx = self.W - self.GW
        lo, hi = gx - p.w * 2.6, gx - p.w * 0.1
        area = (lo - p.w, hi + p.w)
        target = b.x
        if b.vx > 1.5 * self.S:
            # cuántos ticks hasta su zona y a qué altura llega
            t = max(1.0, (lo - b.x) / b.vx) if b.x < lo else 1.0
            px, py = self._predict(b, min(60, t))
            target = px
            if py < p.y and abs(px - p.cx) < p.w * 2.4 and chance(0.12 + 0.3 * d["skill"]):
                p.jump(-18 * p.k)
            elif (not p.on_ground or abs(px - p.cx) > sp * t + p.w * 0.4) \
                    and t < 22 and chance(0.08 + 0.25 * d["skill"]):
                p.dive(px, t, area)
        p.run_to(min(hi, max(lo, target)), sp * 1.05, area)
        p.face(b.x)
        self._keeper_jump(p, b, toward=+1)

    def _attack(self, p, b, sp, bounds, lead=0):
        """Ir a por el balón entrando por su derecha (para patear a la izquierda)."""
        if lead and abs(b.vx) > 1.0 * self.S:
            fx, _fy = self._predict(b, lead)
        else:
            fx = b.x
        behind = fx + b.r + p.w * 0.35
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

    def _kick(self, p, b, direction, clear=False, clear_zone=False):
        # la arquera en el aire estira los brazos
        reach = 2 + (14 * self.diff["skill"] * self.S if clear and not p.on_ground else 0)
        if p.cool > 0 or not p.touches(b, reach):
            return
        d = self.diff
        if not p.on_ground and not clear and direction < 0:
            if b.x < self.W * 0.5:
                # volea / cabezazo en ataque: al arco
                self._aimed_shot(b, direction, random.uniform(14, 19) * self.S * d["power"])
            else:
                # cabezazo defensivo: lejos y arriba
                b.vx = direction * random.uniform(13, 19) * self.S * d["power"]
                b.vy = -random.uniform(7, 12) * self.S
            p.cool = 8
            p.win._squash(1.12, 0.9)
            return
        if clear_zone and not clear and chance(0.45 + 0.5 * d["skill"]):
            # balón muy cerca de su arco: despeje largo y alto, sin pensarlo
            b.vx = direction * random.uniform(16, 22) * self.S * d["power"]
            b.vy = -random.uniform(12, 18) * self.S
            p.cool = 8
            p.win._squash(1.12, 0.9)
            return
        if clear:
            # los arqueros no lo atajan todo: tu ayudante ~55 %, la de ellas
            # según la dificultad
            save = 0.55 if p.role == "helper" else 0.35 + 0.6 * d["skill"]
            if not chance(save):
                p.cool = 22
                if p.role != "helper" and chance(0.2 + 0.7 * d["skill"]):
                    # no la atrapa, pero la desvía hacia afuera
                    b.vx = direction * max(abs(b.vx) * 0.45, 4 * self.S)
                    b.vy = -random.uniform(6, 11) * self.S
                else:
                    p.leak = 12                   # se le escapó de verdad
                return
        power = (random.uniform(9, 14) if not clear else random.uniform(13, 18)) * self.S * d["power"]
        good_side = (b.x - p.cx) * direction > -p.w * 0.15
        if good_side or clear:
            b.vx = direction * power
            b.vy = -random.uniform(3, 11) * self.S * (1.3 if clear else 1.0)
            near_goal = (b.x < self.W * 0.4) if direction < 0 else (b.x > self.W * 0.6)
            shoot_zone = (b.x < self.W * 0.7) if direction < 0 else (b.x > self.W * 0.3)
            close = (b.x < self.W * 0.3) if direction < 0 else (b.x > self.W * 0.7)
            blocker = self._cursor_ahead(b, direction)
            if not clear and direction < 0 and blocker and chance(0.35 + 0.55 * d["skill"]):
                # tu pie está delante: se la pica por encima
                b.vx = direction * random.uniform(9, 13) * self.S * d["power"]
                b.vy = -random.uniform(15, 19) * self.S
            elif not clear and (close or (shoot_zone and chance(0.5 + 0.5 * d["skill"]))):
                self._aimed_shot(b, direction, power * random.uniform(1.2, 1.5))
            elif not clear and direction < 0 and not blocker and chance(0.3 + 0.6 * d["skill"]):
                # campo libre: la lleva con toques cortos
                b.vx = direction * random.uniform(6, 9) * self.S * d["speed"]
                b.vy = -random.uniform(0, 2) * self.S
            elif not clear and near_goal:
                # cerca del arco: disparo al arco, a media altura
                b.vy = -random.uniform(6, 13) * self.S
            elif not clear and chance(d["skill"] * 0.5):
                b.vy = -random.uniform(1, 4) * self.S       # tiro rasante
        else:
            # le pegó con el cuerpo «al revés»: rebote corto
            b.vx = -direction * random.uniform(3, 6) * self.S
            b.vy = -random.uniform(2, 5) * self.S
        p.cool = 8
        p.win._squash(1.12, 0.9)

    def _cursor_ahead(self, b, direction):
        """¿Tu pie está entre el balón y el arco, a poca distancia?"""
        if self.mouse is None:
            return False
        mx, my = self.mouse
        dx = (mx - b.x) * direction
        return 0 < dx < self.W * 0.22 and my > self.F - self.GH * 1.8

    def _aimed_shot(self, b, direction, power):
        """Tiro al arco: calcula la parábola para que entre bajo el travesaño,
        lejos de quien lo defiende."""
        s = self.S
        if direction < 0:
            tx = self.GW * random.uniform(0.2, 0.7)
            guard = self.helper
        else:
            tx = self.W - self.GW * random.uniform(0.2, 0.7)
            guard = next((p for p in self.rivals if p.role == "keeper"), None)
        # alto o rasante según dónde esté la arquera
        if guard is not None and guard.on_ground and not chance(0.35):
            ty = self.F - self.GH * random.uniform(0.6, 0.85)    # por encima
        else:
            ty = self.F - b.r - self.GH * random.uniform(0.0, 0.3)  # rasante
        dist = max(1.0, abs(tx - b.x))
        t = min(22.0, max(6.0, dist / max(power, 14 * s)))   # de lejos, más fuerte
        vx = direction * min(dist / t, 40 * s)
        t = dist / abs(vx)
        vy = (ty - b.y - 0.5 * self.g * t * t) / t
        b.vx = vx
        b.vy = max(-26 * s, min(4 * s, vy))

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
