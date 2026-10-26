"""
🏐 Vóley (estilo wallyball): la red en el medio, las paredes y el techo
rebotan y SOLO hay punto cuando el balón toca el piso. Tú (y tu mascota
ayudante) a la izquierda, hasta 4 mascotas a la derecha.

En tu lado juegas EMPUJANDO el balón con el mouse (sacar, recibir, armar).
Los anillos «estilo osu» aparecen solo en tres jugadas:

  - tu REMATE: el balón cae alto y cerca de la red → clic justo a tiempo;
  - BLOQUEAR su remate (anillo naranja en la red);
  - RECIBIR su remate si no lo bloqueaste (anillo azul).

Cuanto más preciso el clic, mejor sale. Dificultad de las mascotas = cuántas
veces arman la jugada completa (recepción → armado → remate): fácil ~3 de 10,
medio ~6, difícil ~9.
"""
import math
import random

from ..i18n import N_, tr
from .base import TICK_MS, Match, Ring, ballistic, chance, grade_label

DT = TICK_MS / 1000.0
WINDUP_S = 1.5          # lo que tarda el armado: tu tiempo para el anillo de bloqueo
MAX_BALL = 34.0


class Volley(Match):
    SPORT = "volley"
    BALL = "volley"
    HOWTO = N_("Empuja el balón a su campo · clic justo en los anillos para rematar, bloquear o recibir")

    def setup(self):
        s = self.S
        self.g = 0.42 * s
        self.net_x = self.W / 2
        self.net_w = max(5, 7 * s)
        self.net_top = self.F - min(self.H * 0.42, max(1.7 * self.avg_h, self.H * 0.2))
        self.y_hit = self.F - max(1.1 * self.avg_h, self.H * 0.18)
        self.st = 0.0                   # reloj de la simulación (s)
        self.ring = None
        self.state = "serve_you"
        self.server_you = True
        self.plan = []                  # pasos pendientes de las mascotas
        self.you_plan = []              # tus pasos: receive/set/spike, block/dig
        self.last_spike = False         # el último toque de ellas fue un remate
        self.free_ball = False
        self.spike_offered = False
        self.windup = None              # remate en preparación (1,5 s para decidir)
        self.touches = 0                # toques de tu equipo en esta posesión
        self._pushing = False
        self.rescue = None              # prob. de que tu ayudante salve el próximo
        self.helper_spike = False
        self.helper_whiff = False
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
        self.ring = None
        self.touches = 0
        self.rescue = None
        self.helper_spike = False
        self.helper_whiff = False
        self.plan = []
        self.you_plan = []
        self.spike_offered = False
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
            if self.st >= self.serve_at and self.mouse_push(b, MAX_BALL * s):
                self.last_spike = False
                self.state = "rally"
            elif self.st >= self.serve_at + 8:
                # 8 s sin sacar: saque flojo automático para no trabar el partido
                self._send(self.net_x + self.W * 0.2, self.net_top - self.H * 0.2)
                self.last_spike = False
                self.state = "rally"
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
            self.ring = None
            self.serve_after = now + 1.7
            return

        if b.x < self.net_x:
            self._your_side(b)
            self._move_pets_idle()
        else:
            self.spike_offered = False
            self.touches = 0
            self._pushing = False
            self.rescue = None
            self.helper_spike = False
            self.helper_whiff = False
            if not self.last_spike:
                self.you_plan = []
            r = self.ring
            if r is not None and r.kind != "block":
                self.ring = None
            elif r is not None and r.expired(self.st) and not r.done:
                self.ring = None               # no saltaste a bloquear: a recibir
                if self.windup is None:
                    self.you_plan = ["dig"]
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

    # ── tu lado ───────────────────────────────────────────────────────────
    NAMES = {"block": "Bloqueo", "spike": "Remate", "dig": "Recepción"}

    def _grade(self, kind, q, x=None, y=None):
        """Mensaje «Bloqueo/Remate/Recepción: perfecto / bien / regular / fallido»."""
        b = self.ball
        lbl, col = grade_label(q)
        name = {"block": tr("Bloqueo"), "spike": tr("Remate"), "dig": tr("Recepción")}.get(kind, "")
        self.say(tr("{jugada}: {nota}", jugada=name, nota=lbl) if name else lbl, 1.0, col,
                 x=b.x if x is None else x, y=(b.y - 46 * self.S) if y is None else y, size=0.7)

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
        r = self.ring
        if r is not None:
            if r.expired(self.st) and not r.done:
                self.ring = None
                if r.kind == "block":
                    self.you_plan = ["dig"]
                    return
                self._grade(r.kind, 0)
                self._ring_missed(r.kind, 0.0)
            return
        if self.you_plan[:1] == ["block"]:
            return                      # el anillo de bloqueo lo crea su remate
        if self.you_plan[:1] == ["dig"]:
            if b.vy > 0:
                t = self._t_to_y(self.F - b.r * 2.4)
                lead = 1.0 if getattr(self, "spike_kind", "power") == "feint" else 0.5
                if t is not None and t > 0.08:
                    self.ring = Ring(self.st + t, min(lead, t), "dig")
            return
        # ¿balón alto y cerca de la red, bajando? → tu remate (si quedan toques)
        near = self.net_x - self.W * 0.2 < b.x < self.net_x - b.r
        high = self.net_top - self.H * 0.4 < b.y < self.net_top - self.H * 0.03
        if near and high and b.vy > 0 and not self.spike_offered and self.touches < 3:
            t = self._t_to_y(self.net_top - self.H * 0.04)
            if t is not None and t > 0.15:
                self.spike_offered = True
                self.ring = Ring(self.st + t, min(0.85, t), "spike")
        # empujar con el mouse: cada contacto nuevo es un toque
        if self.mouse_push(b, MAX_BALL * self.S):
            if not self._pushing:
                self._pushing = True
                self._touch()
        else:
            self._pushing = False

    def _ring_missed(self, kind, q, tried=False):
        """Fallaste (o te quedó flojo) un bloqueo o una recepción: tu ayudante
        intenta salvarlo; cuanto peor fue lo tuyo, menos probable."""
        if kind == "block":
            if not tried:
                self.you_plan = ["dig"]       # no saltaste: queda la recepción
                return
            self.you_plan = []
            self._ask_rescue(0.25 + 0.5 * (q / 0.5 if q > 0 else 0.0))
        elif kind == "dig":
            self.you_plan = []
            self._ask_rescue(0.2)
        elif kind == "spike":
            # no remataste: tu ayudante puede rematar ella si está cerca
            self.helper_spike = True

    def _ask_rescue(self, p):
        if self.helper is not None:
            self.rescue = p

    def on_press(self, x, y):
        b = self.ball
        r = self.ring
        if r is None or r.done:
            return
        reach = b.r * (1 + 3.2 * r.progress(self.st)) + 46 * self.S
        if math.hypot(x - b.x, y - b.y) > reach:
            return
        q = r.grade(self.st)
        r.done = True
        self.ring = None
        self._grade(r.kind, q)
        if q <= 0:
            if r.kind == "block" and self.windup is not None:
                self.windup["block_q"] = 0.0   # saltaste a destiempo
                return
            self._ring_missed(r.kind, 0.0, tried=True)
            return
        if r.kind == "block":
            if self.windup is not None:
                self.windup["block_q"] = q     # se aplica en el golpe
            else:
                self.you_plan = []
                self._resolve_block(q)
        elif r.kind == "dig":
            self.you_plan = []
            self.spike_offered = False
            if self._touch():
                # una recepción floja queda corta y baja: le cuesta más a tu ayudante
                self._send(self.W * (0.2 + 0.12 * q), self.net_top - self.H * (0.06 + 0.18 * q))
                if q < 0.55:
                    self._ask_rescue(0.45 + 0.5 * q)
        elif r.kind == "spike":
            self.you_plan = []
            if self._touch():
                self._your_spike(q)

    def _your_spike(self, q):
        b = self.ball
        self.last_spike_q = q
        self.free_ball = False
        if q >= 0.55:
            self._drive(self._open_spot(), (14 if q >= 0.85 else 19) / max(0.7, 0.6 + 0.5 * q))
        elif chance(0.3):
            self._send(self.net_x - 3, self.net_top + 30 * self.S, self.net_top + 50 * self.S)
        else:
            self._send(self.net_x + random.uniform(0.04, 0.14) * self.W,
                       self.net_top - self.H * 0.12)
        b.y -= 2

    def _open_spot(self):
        """Un hueco en el campo de las mascotas, lejos de ellas."""
        best, bx = -1, self.W * 0.75
        for _ in range(12):
            x = random.uniform(self.net_x + self.W * 0.06, self.W - self.W * 0.04)
            d = min(abs(x - p.cx) for p in self.rivals)
            if d > best:
                best, bx = d, x
        return bx

    def _block(self, q):
        b, s = self.ball, self.S
        if q > 0.5:
            b.x = self.net_x - self.net_w - b.r
            b.vx = abs(b.vx) * 0.55 + 3 * s
            b.vy = 3 * s
            self.you_plan = []
            self.last_spike = False
            self.blocked = True
        else:
            # bloqueo flojo: amortigua y sube en tu lado; tu ayudante intenta
            # levantarlo (según lo bien que tocaste)
            b.vx *= 0.25
            b.vy = -7 * s
            self.you_plan = []
            self._ask_rescue(0.35 + q)

    # ── lado de las mascotas ──────────────────────────────────────────────
    def _pets_side(self, b):
        if not self.plan:
            if b.vy <= 0 and self.actor is None:
                return          # aún subiendo (rebote en pared): esperar a que baje
            skill = self.diff["skill"]
            if getattr(self, "free_ball", False):
                skill = min(1.0, skill + 0.2)
            elif getattr(self, "last_spike_q", None) is not None:
                # tu remate: cuanto mejor, más difícil que lo levanten
                q = self.last_spike_q
                self.last_spike_q = None
                if q >= 0.55 and not chance(skill * (1.0 - 0.6 * q) + 0.1):
                    self.plan = ["error"]
                    self.actor = None
                    return
            if getattr(self, "blocked", False):
                self.blocked = False
                if not chance(skill * 0.5):
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
        kind = "feint" if chance(0.3) else "power"
        self.windup = {"until": self.st + t * DT, "p": spiker, "block_q": None, "kind": kind}
        self.actor = spiker
        # anillo de BLOQUEO: se cierra justo cuando la rematadora le pega
        self.ring = Ring(self.st + t * DT, t * DT, "block")

    def _do_spike(self, p):
        w = self.windup or {"block_q": None, "kind": "power"}
        self.windup = None
        kind, bq = w["kind"], w["block_q"]
        b, s, d = self.ball, self.S, self.diff
        self.last_spike = True
        self.spike_kind = kind
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
        if bq is not None:
            self._resolve_block(bq)      # ya saltaste a bloquear antes del golpe
        else:
            self.you_plan = ["dig"]      # si el anillo de bloqueo vence sin clic: a recibir

    def _resolve_block(self, q):
        """Tu bloqueo contra su remate (q = precisión del clic)."""
        s = self.S
        if self.ring is not None and self.ring.kind == "block":
            self.ring = None
        if getattr(self, "spike_kind", "power") == "feint":
            # saltaste al bloqueo y era finta: te pasa por encima
            self.you_plan = []
            self.say(tr("¡Te pasó por encima del bloqueo!"), 1.2, (1, 0.6, 0.5),
                     y=self.net_top - 80 * s, x=self.net_x - self.W * 0.1, size=0.6)
            self._ask_rescue(0.5)
            return
        self._block(q)

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
        sp = 6.8 * self.S * h.k
        bounds = (0, self.net_x - self.net_w)
        mine = b.x < self.net_x and self.state == "rally" and self.windup is None
        busy_ring = self.ring is not None and self.ring.kind in ("block", "dig")
        # remate de tu ayudante: no remataste un balón bueno cerca de la red
        if mine and self.helper_spike and self.touches < 3:
            h.run_to(b.x - h.w * 0.2, sp * 1.2, bounds)
            h.face(self.net_x)
            if h.on_ground and abs(b.x - h.cx) < h.w * 1.3 and b.y < h.y and b.vy > -2:
                h.jump(-math.sqrt(2 * 1.3 * self.S * h.h * 1.1))
            if h.cool == 0 and h.touches(b, b.r):
                h.cool = 18
                self.helper_spike = False
                if self._touch():
                    self.last_spike_q = 0.7
                    self._drive(self._open_spot(), 18)
                    self.say(tr("¡Remate de tu ayudante!"), 1.0, (0.6, 0.9, 1),
                             x=h.cx, y=h.y - 30 * self.S, size=0.6)
            return
        going_down = mine and b.vy > 0 and not busy_ring and self.ring is None
        if going_down and self.rescue is not None:
            if not chance(self.rescue):
                self.rescue = None
                self.helper_whiff = True          # no llega: se queda mirando
            else:
                self.rescue = None
                self.helper_whiff = False
        land = self._land_x() if going_down else None
        reach = going_down and not getattr(self, "helper_whiff", False) \
            and abs(land - h.cx) < self.W * 0.3
        if reach:
            h.run_to(land, sp, bounds)
            if h.cool == 0 and h.touches(b, b.r * 0.8):
                h.cool = 14
                h.win._squash(1.1, 0.9)
                if not self._touch():
                    return
                self.spike_offered = False
                if self.touches >= 3:
                    # tercer toque: hay que pasarlo
                    self._send(self._open_spot(), self.net_top - self.H * 0.2)
                    self.say(tr("¡Al otro lado!"), 0.8, (0.6, 0.9, 1), x=h.cx, y=h.y - 30 * self.S, size=0.6)
                else:
                    # te lo arma alto junto a la red para que remates
                    self._send(self.net_x - self.W * 0.07, self.net_top - self.H * 0.3,
                               self.net_top - 10 * self.S)
                    self.say(tr("¡Te la armo!"), 0.8, (0.6, 0.9, 1), x=h.cx, y=h.y - 30 * self.S, size=0.6)
        else:
            h.run_to(self.W * 0.25, sp * 0.6, bounds)
        h.face(b.x)

    # ── dibujo ────────────────────────────────────────────────────────────
    def draw_field(self, cr):
        s = self.S
        x, top = self.net_x, self.net_top
        # palo
        cr.set_source_rgba(0.85, 0.85, 0.9, 0.95)
        cr.rectangle(x - self.net_w / 2, top, self.net_w, self.F - top)
        cr.fill()
        # malla (la parte de arriba, como una red de verdad)
        mh = max(60 * s, (self.F - top) * 0.35)
        cr.set_source_rgba(1, 1, 1, 0.3)
        cr.set_line_width(1)
        step = 9 * s
        yy = top
        while yy <= top + mh:
            cr.move_to(x - 22 * s, yy); cr.line_to(x + 22 * s, yy)
            yy += step
        xx = x - 22 * s
        while xx <= x + 22 * s:
            cr.move_to(xx, top); cr.line_to(xx, top + mh)
            xx += step
        cr.stroke()
        # cinta blanca y antena
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.rectangle(x - 24 * s, top - 3 * s, 48 * s, 6 * s)
        cr.fill()
        for k in range(6):
            cr.set_source_rgba(*((0.9, 0.2, 0.25, 1) if k % 2 == 0 else (1, 1, 1, 1)))
            cr.rectangle(x - 2 * s, top - (k + 1) * 10 * s, 4 * s, 10 * s)
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
        if self.ring is not None:
            self.draw_ring(cr, self.ring, self.st, self.ball.x, self.ball.y)
