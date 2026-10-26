"""
🏐 Vóley (estilo wallyball): la red en el medio, las paredes y el techo
rebotan y SOLO hay punto cuando el balón toca el piso. Tú (y tu mascota
ayudante) a la izquierda, hasta 4 mascotas a la derecha.

Juegas EMPUJANDO el balón con el mouse (rebota con fuerza al tocarlo). Tu
ayudante recibe, arma y remata sola. Máximo 3 toques por lado.

Saque: tiene que pasar la red y no puede tocar la pared del fondo; si no,
punto para el rival.

Dificultad de las mascotas = cuántas veces arman la jugada completa
(recepción → armado → remate): fácil ~3 de 10, medio ~6, difícil ~9.
"""
import math
import random

from ..i18n import N_, tr
from .base import TICK_MS, Match, ballistic, chance

DT = TICK_MS / 1000.0
WINDUP_S = 1.5          # lo que tarda el armado hasta el punto de remate
MAX_BALL = 36.0
PUSH_BOUNCE = 1.5       # cuánto rebota el balón al tocarlo con el mouse


class Volley(Match):
    SPORT = "volley"
    BALL = "volley"
    HOWTO = N_("Empuja el balón a su campo · tu saque debe pasar la red sin tocar el fondo")
    FOOT = 32

    def setup(self):
        s = self.S
        self.g = 0.42 * s
        self.net_x = self.W / 2
        self.net_w = max(5, 7 * s)         # red fina (también su choque)
        self.net_top = self.F - min(self.H * 0.42, max(1.7 * self.avg_h, self.H * 0.2))
        self.y_hit = self.F - max(1.1 * self.avg_h, self.H * 0.18)
        self.st = 0.0                   # reloj de la simulación (s)
        self.state = "serve_you"
        self.serving = None             # "you"/"pets" mientras el saque no cruza la red
        self.server_you = True
        self.plan = []                  # pasos pendientes de las mascotas
        self.last_spike = False         # el último toque de ellas fue un remate
        self.free_ball = False
        self.windup = None              # remate en preparación (1,5 s para decidir)
        self.touches = 0                # toques de tu equipo en esta posesión
        self._pushing = False
        self._last_contact = -1.0
        self.hard_hit = False
        self.spike_live = False
        self.actor = None
        self.serve_at = 0.0
        self.serve_after = 0.0
        n = len(self.rivals)
        for i, p in enumerate(self.rivals):
            p.x = self.net_x + (i + 0.6) * (self.W / 2) / (n + 0.6) - p.w / 2
        if self.helper:
            self.helper.x = self.W * 0.28
        self._serve()

    def cursor_limit(self):
        return self.net_x - self.net_w / 2 - 2

    # ── utilidades ────────────────────────────────────────────────────────
    def _t_to_y(self, y):
        """Segundos hasta que el balón (bajando) llegue a la altura y."""
        b = self.ball
        a, v, d = 0.5 * self.g, b.vy, y - b.y
        disc = v * v + 4 * a * d
        if disc < 0:
            return None
        t = (-v + math.sqrt(disc)) / (2 * a)
        return t * DT if t >= 0 else None

    def _land_x(self):
        """Dónde caerá el balón (sin contar la red)."""
        b = self.ball
        a, v, d = 0.5 * self.g, b.vy, (self.F - b.r) - b.y
        disc = v * v + 4 * a * d
        t = (-v + math.sqrt(max(0.0, disc))) / (2 * a)
        return b.x + b.vx * t

    def _send(self, x1, apex_y, y1=None):
        """Parábola a (x1, y1) con altura máxima apex_y. Si cruza la red, se
        sube el vértice hasta que pase por encima de la cinta."""
        b = self.ball
        y1 = y1 if y1 is not None else self.F - b.r
        crosses = (b.x - self.net_x) * (x1 - self.net_x) < 0
        for _ in range(10):
            vx, vy, _t = ballistic(b.x, b.y, x1, y1, apex_y, self.g)
            if not crosses or self._clears(b.x, b.y, vx, vy):
                break
            apex_y -= self.H * 0.05
        b.vx, b.vy = vx, vy

    def _clears(self, x, y, vx, vy):
        if abs(vx) < 1e-6:
            return False
        t = (self.net_x - x) / vx
        if t <= 0:
            return True
        return y + vy * t + 0.5 * self.g * t * t < self.net_top - self.ball.r * 1.3

    def _drive(self, tx, ticks):
        """Tiro fuerte y directo (remate) que cae en tx: si choca la red, se
        alarga el vuelo hasta que pase."""
        b = self.ball
        for _ in range(30):
            vx = (tx - b.x) / ticks
            vy = ((self.F - b.r) - b.y - 0.5 * self.g * ticks * ticks) / ticks
            if self._clears(b.x, b.y, vx, vy):
                break
            ticks += 1.5
        b.vx, b.vy = vx, vy

    # ── saques ────────────────────────────────────────────────────────────
    def _serve(self):
        b = self.ball
        self.touches = 0
        self.serving = None
        self.plan = []
        b.vx = b.vy = 0.0
        self.state = "serve_you" if self.server_you else "serve_pets"
        if self.server_you:
            # tu saque: el balón flota al fondo de tu campo hasta que lo empujas
            b.x, b.y = self.W * 0.12, self.F - self.H * 0.42
            self.serve_at = self.st + 1.0
            self.say(tr("Tu saque: empuja el balón con el mouse"), 2.0,
                     (0.7, 1, 0.55), y=self.H * 0.22, size=0.6)
        else:
            p = max(self.rivals, key=lambda r: r.x)
            p.x = self.W - p.w * 1.3
            self.actor = p
            b.x, b.y = p.cx, p.y - b.r * 1.2
            self.serve_at = self.st + 1.0

    # ── tick ──────────────────────────────────────────────────────────────
    def update(self, now):
        self.st += DT
        b, s = self.ball, self.S
        if self.state == "dead":
            if now >= self.serve_after:
                self._serve()
            return
        if self.windup is not None and b.x < self.net_x:
            self.windup = None              # el armado se fue a tu campo: no hubo remate
        if self.state == "serve_you":
            self._move_pets_idle()
            b.y += math.sin(self.st * 4) * 0.6         # flota esperando
            if self.st >= self.serve_at and self.mouse_push(b, MAX_BALL * s, k=PUSH_BOUNCE):
                self.last_spike = False
                self.state = "rally"
                self.serving = "you"
            elif self.st >= self.serve_at + 8:
                # 8 s sin sacar: saque flojo automático para no trabar el partido
                self._send(self.net_x + self.W * 0.2, self.net_top - self.H * 0.2)
                self.last_spike = False
                self.state = "rally"
                self.serving = "you"
            return
        if self.state == "serve_pets":
            p = self.actor
            b.x, b.y = p.cx, p.y - b.r * 1.2
            self._move_pets_idle(skip=p)
            if self.st >= self.serve_at:
                fault = {"easy": 0.25, "medium": 0.1, "hard": 0.04}[self._diff_name()]
                if chance(fault):
                    self._send(self.net_x + 4, self.net_top + 20 * s, self.net_top + 40 * s)
                else:
                    self._send(random.uniform(self.W * 0.08, self.net_x - self.W * 0.1),
                               self.net_top - self.H * random.uniform(0.18, 0.3))
                p.jump(-9 * p.k)
                self.state = "rally"
                self.plan = []
                self.last_spike = False
                self.serving = "pets"
            return

        # rally: física
        px, py = b.x, b.y
        b.vy += self.g
        b.x += b.vx
        b.y += b.vy
        if (px - self.net_x) * (b.x - self.net_x) < 0:
            # cruzó la línea de la red en este paso: ¿por debajo de la cinta?
            t = (self.net_x - px) / (b.x - px)
            yc = py + (b.y - py) * t
            if yc + b.r > self.net_top:
                side = -1 if px < self.net_x else 1
                b.x = self.net_x + side * (self.net_w / 2 + b.r)
                b.vx = -b.vx * 0.3
        b.spin = (b.spin + math.degrees(b.vx / b.r) * 0.6) % 360
        if self.serving and (px - self.net_x) * (b.x - self.net_x) < 0 \
                and b.y + b.r <= self.net_top + b.r:
            self.serving = None                     # el saque pasó la red: válido
        if b.x - b.r < 0 or b.x + b.r > self.W:
            back = "you" if b.x - b.r < 0 else "pets"
            if self.serving == back:
                # el saque tocó la pared del fondo: punto para el rival
                self._fault(tr("¡Saque al fondo!"), now)
                return
        if b.x - b.r < 0:
            b.x, b.vx = b.r, abs(b.vx) * 0.6
        if b.x + b.r > self.W:
            b.x, b.vx = self.W - b.r, -abs(b.vx) * 0.6
        if b.y - b.r < 0:
            b.y, b.vy = b.r, abs(b.vy) * 0.5
        self._net(b)
        if b.y + b.r >= self.F:
            b.y = self.F - b.r
            if b.x < self.net_x:
                self.point("pets", tr("Punto para las mascotas"))
                self.server_you = False
            else:
                self.point("you", tr("¡Punto!"))
                self.server_you = True
            self.state = "dead"
            self.serving = None
            self.serve_after = now + 1.7
            return

        if b.x < self.net_x:
            self.spike_live = False
            self._your_side(b)
            self._move_pets_idle()
            self._rival_block(b)
        else:
            self.touches = 0
            self._pushing = False
            self.block_tried = False
            self._pets_side(b)
        if self.helper:
            self._helper(b)

    def _diff_name(self):
        for k, v in (("easy", 0.3), ("medium", 0.6), ("hard", 0.9)):
            if abs(self.diff["skill"] - v) < 1e-6:
                return k
        return "medium"

    def _net(self, b):
        x0, x1 = self.net_x - self.net_w / 2, self.net_x + self.net_w / 2
        if b.y + b.r > self.net_top and x0 - b.r < b.x < x1 + b.r:
            if b.y < self.net_top + b.r * 0.6 and b.vy > 0:
                b.y, b.vy = self.net_top - b.r, -abs(b.vy) * 0.35     # cinta
                b.vx *= 0.6
                if abs(b.vy) < 3 * self.S and abs(b.vx) < 2 * self.S:
                    # se quedó encima de la cinta: cae hacia un lado
                    side = (1 if b.x >= self.net_x else -1) if abs(b.x - self.net_x) > 1 \
                        else random.choice((-1, 1))
                    b.vx = side * random.uniform(2.5, 4) * self.S
                    b.x = self.net_x + side * (self.net_w / 2 + b.r + 1)
            else:
                if b.x < self.net_x:
                    b.x, b.vx = x0 - b.r, -abs(b.vx) * 0.3
                else:
                    b.x, b.vx = x1 + b.r, abs(b.vx) * 0.3

    # ── tu lado: empujas el balón ─────────────────────────────────────────
    def _fault(self, label, now):
        """Falta de quien sacaba / tocaba: punto para el otro equipo."""
        who = "pets" if (self.serving == "you" or self.ball.x < self.net_x) else "you"
        self.point(who, label)
        self.server_you = who == "you"
        self.state = "dead"
        self.serving = None
        self.serve_after = now + 1.7

    def _touch(self):
        """Un toque de tu equipo. El cuarto es falta."""
        self.touches += 1
        if self.touches > 3:
            self.say(tr("¡Cuatro toques!"), 1.2, (1, 0.5, 0.5), y=self.H * 0.3)
            self.ball.vx = self.ball.vy = 0.0
            self.ball.y = self.F - self.ball.r
            return False
        return True

    def _your_side(self, b):
        if self.mouse_push(b, MAX_BALL * self.S, k=PUSH_BOUNCE):
            # un empujón continuo (aunque tiemble) cuenta como UN toque: el
            # siguiente necesita 0,3 s sin tocar el balón
            if not self._pushing and self.st - self._last_contact > 0.3:
                self._touch()
            self._pushing = True
            self._last_contact = self.st
        else:
            self._pushing = False

    def _open_spot(self):
        """Un hueco en el campo de las mascotas, lejos de ellas."""
        best, bx = -1, self.W * 0.75
        for _ in range(12):
            x = random.uniform(self.net_x + self.W * 0.06, self.W - self.W * 0.04)
            d = min(abs(x - p.cx) for p in self.rivals)
            if d > best:
                best, bx = d, x
        return bx

    # ── lado de las mascotas ──────────────────────────────────────────────
    def _pets_side(self, b):
        if not self.plan:
            if b.vy <= 0 and self.actor is None:
                return          # aún subiendo (rebote en pared): esperar a que baje
            skill = self.diff["skill"]
            if getattr(self, "free_ball", False):
                skill = min(1.0, skill + 0.2)
            elif getattr(self, "hard_hit", False):
                # un remate fuerte (de tu ayudante o un buen empujón) cuesta levantarlo
                self.hard_hit = False
                if not chance(skill * 0.6 + 0.15):
                    self.plan = ["error"]
                    self.actor = None
                    return
            r = random.random()
            if r < skill:
                self.plan = ["receive", "set", "spike"]
            elif r < skill + (1 - skill) * 0.55:
                self.plan = ["return"]
            else:
                self.plan = ["error"]
            self.actor = None
        step = self.plan[0]
        if step == "error":
            # se queda mirando: el balón cae
            self._move_pets_idle()
            return
        if self.actor is None or self.actor.cool > 0 and step != "spike":
            land = self._land_x()
            used = getattr(self, "_last_actor", None)
            cands = [p for p in self.rivals if p is not used] or self.rivals
            self.actor = min(cands, key=lambda p: abs(p.cx - land))
        p = self.actor
        sp = 7.0 * self.S * self.diff["speed"] * p.k
        bounds = (self.net_x + self.net_w, self.W)
        self.free_ball = False
        self.last_spike = False
        if step in ("receive", "return", "set"):
            p.run_to(self._land_x(), sp, bounds)
            p.face(b.x)
            for o in self.rivals:
                if o is not p:
                    o.speed_now = 0.0
            if b.vy > 0 and p.touches(b, b.r * 0.8):
                self._pet_touch(p, step)
        elif step == "spike":
            if self.windup is not None:
                p = self.windup["p"]
                self.actor = p
            tx, ty = self._spike_point()
            gp = 1.3 * self.S
            hand = ty + b.r * 0.5                        # dónde debe quedar su cabeza
            rise = max(4.0, p.floor_top - hand)
            t_rise = math.sqrt(2 * rise / gp) * DT       # s que tarda en subir
            if self.windup is not None:
                t_left = max(0.05, self.windup["until"] - self.st)
            else:
                t_left = self._t_to_y(ty) if b.vy > 0 else 0.3
                t_left = 0.3 if t_left is None else t_left
            # carrera de aproximación: llega al punto antes de saltar (esprinta
            # si hace falta, como una rematadora de verdad)
            run_t = max(0.05, t_left - t_rise)
            need = abs(tx - p.cx) / (run_t / DT)
            speed = max(sp, need * 1.15)
            p.run_to(tx, speed, bounds)
            p.face(self.net_x)
            close = abs(p.cx - tx) < p.w * 0.8
            if p.on_ground and t_left <= t_rise + 0.04 and (close or t_left < t_rise * 0.6):
                p.jump(-math.sqrt(2 * gp * rise))
            if p.touches(b, b.r * 1.2):
                self._pet_touch(p, "spike")

    def _pet_touch(self, p, step):
        b = self.ball
        self.plan.pop(0)
        self._last_actor = p
        p.cool = 6
        p.win._squash(1.1, 0.9)
        b.y = min(b.y, p.y - b.r * 0.4)
        if step == "receive":
            self._send(self.net_x + self.W * 0.12, self.net_top - self.H * 0.22)
        elif step == "set":
            self._set_for_spike(p)
        elif step == "return":
            self._send(random.uniform(self.W * 0.08, self.net_x - self.W * 0.1),
                       self.net_top - self.H * random.uniform(0.15, 0.28))
        elif step == "spike":
            self._do_spike(p)
        if not self.plan:
            self.actor = None

    def _spike_point(self):
        return self.net_x + self.W * 0.06, self.net_top - self.H * 0.06

    def _set_for_spike(self, setter):
        """El armado sube y cae en el punto de remate en ~1,5 s: ese es tu
        tiempo para decidir bloquear o recibir mientras la rematadora corre y
        salta."""
        b = self.ball
        tx, ty = self._spike_point()
        want = WINDUP_S / DT
        apex = min(ty, b.y) - self.H * 0.05
        for _ in range(40):
            vx, vy, t = ballistic(b.x, b.y, tx, ty, apex, self.g)
            if t >= want:
                break
            apex -= self.H * 0.02
        b.vx, b.vy = vx, vy
        others = [r for r in self.rivals if r is not setter] or self.rivals
        spiker = min(others, key=lambda r: abs(r.cx - tx))
        kind = "feint" if chance(0.1) else "power"     # casi siempre remate fuerte
        self.windup = {"until": self.st + t * DT, "p": spiker, "block_q": None, "kind": kind}
        self.actor = spiker

    def _do_spike(self, p):
        w = self.windup or {"kind": "power"}
        self.windup = None
        kind = w["kind"]
        b, s, d = self.ball, self.S, self.diff
        self.last_spike = True
        self.spike_live = True          # remate en el aire (hasta que cruce o lo bloqueen)
        p.win._lean_to(12 if p.win._facing_left else -12)
        p.win._squash(1.15, 0.85)
        if kind == "power":
            tx = random.uniform(self.W * 0.06, self.net_x - self.W * 0.1)
            self._drive(tx, random.uniform(16, 22) / d["power"])
            self.say(tr("¡Remate!"), 0.8, (1, 0.5, 0.5), x=b.x, y=b.y - 50 * s, size=0.7)
        else:
            # finta: toque suave por encima del bloqueo, cae cerca de la red
            self._send(self.net_x - self.W * random.uniform(0.04, 0.1), self.net_top - self.H * 0.07)
            self.say(tr("¡Finta!"), 0.9, (1, 0.8, 0.4), x=b.x, y=b.y - 50 * s, size=0.7)

    # ── bloqueos en la red ────────────────────────────────────────────────
    def _block_jump(self, p):
        """Salto alto de bloqueo: las manos por encima de la cinta."""
        gp = 1.3 * self.S
        # el cuerpo tapa la franja justo por encima de la cinta
        rise = max(6.0, p.floor_top - (self.net_top - p.h * 0.8))
        p.jump(-math.sqrt(2 * gp * rise))

    def _soft_touch(self, b, direction):
        """El bloqueo roza el balón: sigue hacia el campo de quien bloquea,
        frenado y subiendo un poco (fácil de levantar). No cuenta como toque."""
        b.vx = direction * max(1.5 * self.S, abs(b.vx) * 0.3)
        b.vy = -random.uniform(4, 7) * self.S
        b.x = self.net_x + direction * (self.net_w / 2 + b.r + 1)
        self.say(tr("¡Toque de bloqueo!"), 0.8, (0.9, 0.9, 0.6), x=self.net_x,
                 y=self.net_top - 60 * self.S, size=0.6)

    def _rival_block(self, b):
        """La rival más cerca de la red va al bloqueo: se planta en la red
        cuando el balón está alto cerca de ella en tu campo y salta a la vez
        que tu ayudante (o contra un empujón fuerte hacia su campo)."""
        if not self.rivals or getattr(self, "block_tried", False):
            return
        near_net = b.x > self.net_x - self.W * 0.2 and b.y < self.net_top
        fast = b.vx > 2 * self.S and b.x > self.net_x - self.W * 0.14 and b.y < self.net_top + b.r
        if not (near_net or fast):
            return
        p = min(self.rivals, key=lambda r: abs(r.cx - self.net_x))
        p.run_to(self.net_x + self.net_w + p.w * 0.5, 9 * self.S * p.k,
                 (self.net_x + self.net_w, self.W))
        p.face(self.net_x)
        gp = 1.3 * self.S
        rise = max(6.0, p.floor_top - (self.net_top - p.h * 0.8))
        t_p = math.sqrt(2 * rise / gp)                         # ticks hasta su punto alto
        h = self.helper
        if p.on_ground:
            if h is not None and not h.on_ground and abs(h.cx - self.net_x) < self.W * 0.15:
                if max(0.0, -h.vy / gp) <= t_p:                # salta a la vez que tu ayudante
                    self._block_jump(p)
            elif fast and (self.net_x - b.x) / max(1.0, b.vx) <= t_p:
                self._block_jump(p)
        reach = abs(p.cx - self.net_x) < p.w * 1.1 and p.y < self.net_top
        if not p.on_ground and reach and p.touches(b, b.r * 1.3) and b.vx > 0:
            self.block_tried = True
            r = random.random()
            full = 0.2 + 0.4 * self.diff["skill"]
            if r < full:
                b.x = self.net_x - self.net_w - b.r
                b.vx = -abs(b.vx) * 0.55 - 2 * self.S
                b.vy = abs(b.vy) * 0.3 + 3 * self.S
                p.win._squash(1.1, 0.9)
                self.say(tr("¡Bloqueo!"), 0.9, (1, 0.6, 0.5), x=self.net_x + 40 * self.S,
                         y=self.net_top - 60 * self.S, size=0.7)
            elif r < full + 0.35:
                self._soft_touch(b, +1)          # lo toca y pasa suave a su campo

    def _move_pets_idle(self, skip=None):
        """Sin balón en su campo: vuelven a su posición."""
        n = len(self.rivals)
        for i, p in enumerate(self.rivals):
            if p is skip:
                continue
            home = self.net_x + (i + 0.6) * (self.W / 2) / (n + 0.6)
            p.run_to(home, 4 * self.S * p.k, (self.net_x + self.net_w, self.W))
            p.face(self.ball.x)

    # ── tu ayudante: recibe, arma y remata ────────────────────────────────
    def _helper(self, b):
        h = self.helper
        sp = 7.0 * self.S * h.k
        bounds = (0, self.net_x - self.net_w)
        mine = b.x < self.net_x and self.state == "rally"
        tx, ty = self.net_x - self.W * 0.06, self.net_top - self.H * 0.06
        # ellas arman o rematan: tu ayudante salta a bloquear en la red
        attack = self.windup is not None or (self.spike_live and b.vx < 0 and not mine)
        if attack and self.state == "rally":
            spot = self.net_x - self.net_w - h.w * 0.5
            left = max(0.1, (self.windup["until"] - self.st) if self.windup else 0.1)
            need = abs(spot - h.cx) / (left / DT)
            h.run_to(spot, max(sp * 1.4, need * 1.3), bounds)
            h.face(self.net_x)
            # salta anticipando el golpe (como un bloqueador de verdad)
            w = self.windup
            # salta para llegar arriba a la vez que la rematadora
            gp = 1.3 * self.S
            rise = max(6.0, h.floor_top - (self.net_top - h.h * 0.8))
            t_h = math.sqrt(2 * rise / gp)                     # ticks hasta su punto más alto
            timing = False
            if w is not None and not w["p"].on_ground:
                t_sp = max(0.0, -w["p"].vy / gp)                # ticks hasta el de la rematadora
                timing = t_sp <= t_h
            near = abs(b.x - self.net_x) < self.W * 0.1 and b.y < self.net_top + b.r and b.vx < 0
            if h.on_ground and (timing or near) and abs(h.cx - spot) < h.w * 1.5:
                self._block_jump(h)
            reach = abs(h.cx - self.net_x) < h.w * 1.2 and h.y < self.net_top
            if not h.on_ground and reach and h.cool == 0 and h.touches(b, b.r * 1.3):
                h.cool = 20
                r = random.random()
                if r < 0.35:
                    self.spike_live = False
                    self._soft_touch(b, -1)      # lo toca y pasa suave a tu campo
                elif r < 0.85:
                    b.x = self.net_x + self.net_w + b.r
                    b.vx = abs(b.vx) * 0.55 + 2 * self.S
                    b.vy = abs(b.vy) * 0.3 + 3 * self.S
                    self.hard_hit = True
                    self.last_spike = False
                    self.spike_live = False
                    self.say(tr("¡Bloqueo de tu ayudante!"), 1.0, (0.6, 0.9, 1),
                             x=h.cx, y=h.y - 30 * self.S, size=0.6)
            return
        if not mine:
            # balón en su campo: espera adelantada, lista para ir al bloqueo
            h.run_to(self.net_x - self.W * 0.16, sp * 0.8, bounds)
            h.face(b.x)
            return
        # balón alto cerca de la red con toques disponibles: ¡remate!
        near_net = self.net_x - self.W * 0.2 < b.x < self.net_x - b.r
        if near_net and b.y < self.net_top and self.touches < 3:
            h.run_to(b.x + b.vx * 4, sp * 1.3, bounds)
            h.face(self.net_x)
            gp = 1.3 * self.S
            rise = max(4.0, h.floor_top - (b.y + b.r * 0.5))
            t = self._t_to_y(b.y + 1) if b.vy > 0 else None
            if h.on_ground and abs(b.x - h.cx) < h.w * 1.1 and b.vy > -2 \
                    and (t is None or t < math.sqrt(2 * rise / gp) * DT + 0.1):
                h.jump(-math.sqrt(2 * gp * rise))
            if h.cool == 0 and h.touches(b, b.r) and not h.on_ground:
                h.cool = 16
                if self._touch():
                    self.hard_hit = True
                    self._drive(self._open_spot(), 17)
                    self.say(tr("¡Remate de tu ayudante!"), 1.0, (0.6, 0.9, 1),
                             x=h.cx, y=h.y - 30 * self.S, size=0.6)
            return
        # balón que baja en tu campo: recibe (o arma si ya hubo un toque)
        if b.vy > 0 and abs(self._land_x() - h.cx) < self.W * 0.32:
            h.run_to(self._land_x(), sp, bounds)
            h.face(b.x)
            if h.cool == 0 and h.touches(b, b.r * 0.9):
                h.cool = 12
                h.win._squash(1.1, 0.9)
                if not self._touch():
                    return
                if self.touches >= 3:
                    self._send(self._open_spot(), self.net_top - self.H * 0.2)
                    self.say(tr("¡Al otro lado!"), 0.8, (0.6, 0.9, 1), x=h.cx, y=h.y - 30 * self.S, size=0.6)
                else:
                    # te lo deja alto junto a la red: remátalo tú o lo remata ella
                    self._send(tx, self.net_top - self.H * 0.3, ty)
                    self.say(tr("¡Te la armo!"), 0.8, (0.6, 0.9, 1), x=h.cx, y=h.y - 30 * self.S, size=0.6)
            return
        h.run_to(self.W * 0.25, sp * 0.6, bounds)
        h.face(b.x)

    # ── dibujo ────────────────────────────────────────────────────────────
    def draw_field(self, cr):
        s = self.S
        x, top = self.net_x, self.net_top
        mh = max(60 * s, (self.F - top) * 0.35)        # alto de la malla
        # poste fino del piso hasta la cinta
        cr.set_source_rgba(0.75, 0.77, 0.82, 0.95)
        cr.rectangle(x - 1.5 * s, top, 3 * s, self.F - top)
        cr.fill()
        # malla: una franja fina y oscura colgada de la cinta (sin cuadritos)
        cr.set_source_rgba(0.1, 0.11, 0.16, 0.8)
        cr.rectangle(x - 2.5 * s, top, 5 * s, mh)
        cr.fill()
        # cinta blanca arriba
        cr.set_source_rgba(1, 1, 1, 0.98)
        cr.rectangle(x - 3 * s, top - 2 * s, 6 * s, 5 * s)
        cr.fill()
        # campo rival: zona prohibida para tu cursor
        cr.set_source_rgba(1, 0.4, 0.5, 0.05)
        cr.rectangle(x + self.net_w / 2, 0, self.W - x, self.F)
        cr.fill()
        # mitades
        cr.set_source_rgba(0.45, 0.8, 1, 0.8)
        cr.rectangle(0, self.F - 4, x, 4)
        cr.fill()
        cr.set_source_rgba(1, 0.55, 0.7, 0.8)
        cr.rectangle(x, self.F - 4, self.W - x, 4)
        cr.fill()

    def draw_extra(self, cr):
        if self.serving == "you" or self.state == "serve_you":
            # pared del fondo: el saque no puede tocarla
            cr.set_source_rgba(1, 0.45, 0.5, 0.35)
            cr.rectangle(0, 0, 4 * self.S, self.F)
            cr.fill()
