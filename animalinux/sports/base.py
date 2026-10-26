"""
Piezas comunes de los deportes: el balón, las mascotas jugadoras, el reloj
del partido, el marcador, los avisos grandes y los anillos «estilo osu».

Unidades: píxeles del monitor y «ticks» de TICK_MS. Toda la física se escala
con la altura de la pantalla (S = alto/1080) para que se juegue igual en una
pantalla chica y en una grande.
"""
import math
import random
import time
from pathlib import Path

import cairo
from gi.repository import GLib

from ..i18n import tr
from ..overlay.clock import Clock

TICK_MS = 33
ASSETS = Path(__file__).resolve().parent.parent / "ui" / "assets" / "toys"

DIFFICULTY = {
    # velocidad, fuerza, acierto (prob. de que la IA haga la jugada buena)
    "easy":   {"speed": 0.72, "power": 0.8, "skill": 0.3},
    "medium": {"speed": 0.9,  "power": 0.95, "skill": 0.6},
    "hard":   {"speed": 1.12, "power": 1.1, "skill": 0.9},
}


def ballistic(x0, y0, x1, y1, apex_y, g):
    """Velocidad inicial (vx, vy) para ir de (x0,y0) a (x1,y1) pasando por
    una altura máxima apex_y (y crece hacia abajo) con gravedad g."""
    apex_y = min(apex_y, y0 - 1, y1 - 1)
    up = max(1.0, y0 - apex_y)
    vy = -math.sqrt(2 * g * up)
    t_up = -vy / g
    down = max(1.0, y1 - apex_y)
    t_down = math.sqrt(2 * down / g)
    t = t_up + t_down
    return (x1 - x0) / t, vy, t


class Ball:
    def __init__(self, kind, r):
        self.kind = kind
        self.r = r
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.spin = 0.0
        self.held = False
        try:
            self.img = cairo.ImageSurface.create_from_png(str(ASSETS / kind / "frame_0000.png"))
        except Exception:  # noqa: BLE001
            self.img = None

    def draw(self, cr):
        if self.img is None:
            cr.set_source_rgb(1, 1, 1)
            cr.arc(self.x, self.y, self.r, 0, 2 * math.pi)
            cr.fill()
            return
        iw = self.img.get_width()
        k = 2 * self.r / iw
        cr.save()
        cr.translate(self.x, self.y)
        cr.rotate(math.radians(self.spin))
        cr.scale(k, k)
        cr.translate(-iw / 2, -iw / 2)
        cr.set_source_surface(self.img, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.restore()


class Player:
    """Una mascota en el partido. x, y = esquina superior izquierda (como las
    ventanas de mascota); la física del salto la lleva el partido."""

    def __init__(self, win, team, role, floor):
        self.win = win
        self.team = team          # "pets" | "you"
        self.role = role          # "keeper" | "field" | "helper"…
        self.w = win._cat_w
        self.h = win._cat_h
        self.floor_top = floor - self.h
        self.x = float(win._x)
        self.y = float(self.floor_top)
        self.vy = 0.0
        self.k = max(0.6, min(1.8, self.h / 150.0))
        self.cool = 0             # ticks hasta poder volver a tocar
        self.mood_ttl = 0
        self.speed_now = 0.0

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def on_ground(self):
        return self.y >= self.floor_top - 0.5

    def run_to(self, tx, speed, bounds):
        lo, hi = bounds
        tx = max(lo, min(hi - self.w, tx - self.w / 2))
        d = tx - self.x
        step = max(-speed, min(speed, d))
        self.x += step
        self.speed_now = abs(step)
        if abs(step) > 0.3:
            self.win._facing_left = step < 0
        return abs(d) <= speed

    def jump(self, vy):
        if self.on_ground:
            self.vy = vy

    def face(self, x):
        self.win._facing_left = x < self.cx

    hang = False      # suspendida en el aire (preparando un remate)

    def physics(self, g):
        if self.hang:
            return
        if not self.on_ground or self.vy < 0:
            self.vy += g
            self.y += self.vy
            if self.y >= self.floor_top:
                self.y = self.floor_top
                self.vy = 0.0
                self.win._squash(1.15, 0.86)
        if self.cool > 0:
            self.cool -= 1
        if self.mood_ttl > 0:
            self.mood_ttl -= 1

    def touches(self, ball, pad=0.0):
        """¿El balón toca el cuerpo (caja algo encogida + radio)?"""
        x0, x1 = self.x + self.w * 0.12, self.x + self.w * 0.88
        y0, y1 = self.y + self.h * 0.05, self.y + self.h
        nx = min(max(ball.x, x0), x1)
        ny = min(max(ball.y, y0), y1)
        return (ball.x - nx) ** 2 + (ball.y - ny) ** 2 <= (ball.r + pad) ** 2

    def apply(self):
        """Pasa posición y pose a la ventana de la mascota."""
        w = self.win
        if self.mood_ttl > 0:
            pass
        elif not self.on_ground:
            w._set_pose(w._pose_or("jump"))
        elif self.speed_now > 0.5:
            w._set_pose(w._pose_or("walk"))
        else:
            w._set_pose(w._pose_or("idle"))
        w._apply_juice()
        w._set_position(self.x, self.y)

    def celebrate(self, ticks=45):
        self.mood_ttl = ticks
        self.win._set_pose(self.win._pose_or("greet", "jump"))
        self.jump(-11 * self.k)

    def sulk(self, ticks=45):
        self.mood_ttl = ticks
        self.win._set_pose(self.win._pose_or("angry", "worried", "idle"))


class Ring:
    """Anillo que se cierra sobre el balón: hay que hacer clic justo cuando
    toca el borde del balón. precisión 1.0 = perfecto."""
    WINDOW = 0.28        # s de tolerancia a cada lado

    def __init__(self, t_hit, lead, kind="hit"):
        self.t_hit = t_hit
        self.lead = lead
        self.kind = kind          # "hit" | "block" | "serve"
        self.done = False

    def progress(self, now):
        return max(0.0, (self.t_hit - now) / self.lead)

    def grade(self, now):
        return max(0.0, 1.0 - abs(now - self.t_hit) / self.WINDOW)

    def expired(self, now):
        return now > self.t_hit + self.WINDOW


class Match:
    """Base de los tres deportes."""
    SPORT = ""
    BALL = "soccer"
    HOWTO = ""
    FOOT = 14            # radio de tu «pie» (el cursor), en px a 1080p

    def __init__(self, app, opts, pets, helper_win):
        self.app = app
        self.opts = opts
        self.diff = DIFFICULTY.get(opts.get("difficulty", "medium"), DIFFICULTY["medium"])
        self.mode = opts.get("mode", "points")       # "points" | "time"
        self.target = int(opts.get("points", 10))
        self.minutes = float(opts.get("minutes", 5))
        w0 = pets[0]
        self.W, self.H = w0._screen_w, w0._screen_h
        self.mon = (w0._mon_x, w0._mon_y)
        self.F = self.H - w0._floor_offset_y            # línea del suelo
        self.S = self.H / 1080.0
        self.score = {"you": 0, "pets": 0}
        self.rivals = [Player(w, "pets", "field", self.F) for w in pets]
        self.helper = Player(helper_win, "you", "helper", self.F) if helper_win else None
        self.players = self.rivals + ([self.helper] if self.helper else [])
        self.max_h = max(p.h for p in self.players)
        # para la red y el aro: la altura media (con la más alta, las
        # pequeñas tendrían que saltar media pantalla)
        self.avg_h = sum(p.h for p in self.players) / len(self.players)
        self.ball = Ball(self.BALL, max(14, round(22 * self.S)))
        self.mouse = None              # (x, y)
        self.mouse_prev = None
        self.mvx = self.mvy = 0.0      # velocidad del mouse (px/tick)
        self.pressed = False
        self.msgs = []                 # (texto, hasta, color, x, y, tamaño)
        self.t0 = time.monotonic()
        self.over = False
        self.result = None
        self.pause_until = 0.0
        self.tick_id = None
        self.pitch = None
        self.on_end = None

    # ── ciclo de vida ─────────────────────────────────────────────────────
    def start(self, monitor):
        from .pitch import PitchWindow
        # las mascotas que no juegan esperan escondidas hasta el final
        playing = {id(p.win) for p in self.players}
        self.benched = [w for w in self.app.manager.mascots.values()
                        if id(w) not in playing and w.get_visible()]
        for w in self.benched:
            w.set_paused(True)
            w.set_visible(False)
        for p in self.players:
            w = p.win
            w._stop_behavior_clock()
            w._state = "sport"
            w._hidden_layer and w._set_behind_windows(False)
            w._squash(1.0, 1.0)
        self.setup()
        self.pitch = PitchWindow(self.app, monitor,
                                 (self.mon[0], self.mon[1], self.W, self.H), {
                                     "draw": self.draw, "motion": self._motion,
                                     "press": self._press, "release": self._release,
                                     "key": self._key})
        self.pitch.present()
        # cómo se juega (4 s, sin pausar el partido)
        if self.HOWTO:
            self.say(tr(self.HOWTO), 4.5, (1, 1, 1), y=self.H * 0.42, size=0.62)
            self.say(tr("Mientras dura el partido el mouse es tuyo para jugar · Esc para salir"),
                     4.5, (0.8, 0.85, 1), y=self.H * 0.42 + 40 * self.S, size=0.5)
        self.tick_id = Clock.get().every(TICK_MS, self._tick)

    def stop(self):
        if self.tick_id:
            Clock.get().cancel(self.tick_id)
            self.tick_id = None
        if self.pitch is not None:
            self.pitch.destroy()
            self.pitch = None
        for p in self.players:
            w = p.win
            w._state = "rest"
            w._rest_ttl = 10
            w._y = w._floor_y
            w._set_position(p.x, w._floor_y)
            if w.mode == "life" and not w._paused:
                w._start_behavior_clock()
        for w in getattr(self, "benched", []):
            w.set_visible(True)
            w.set_paused(False)
        self.benched = []
        if self.on_end:
            self.on_end(self)

    # ── entrada ───────────────────────────────────────────────────────────
    # zona donde puede andar tu cursor (None = toda la pantalla)
    CURSOR_MAX_X = None

    def _motion(self, x, y):
        lim = self.cursor_limit()
        if lim is not None and x > lim:
            # tu cursor no pasa al campo rival: se le devuelve a tu lado
            x = lim
            if not getattr(self, "_warping", False):
                self._warping = True
                from ..backends import current as backend
                try:
                    backend.warp_cursor(self.mon[0] + lim - 4, self.mon[1] + y)
                except Exception:  # noqa: BLE001
                    pass
                GLib.timeout_add(30, self._unwarp)
        self.mouse = (x, y)

    def _unwarp(self):
        self._warping = False
        return False

    def cursor_limit(self):
        return None

    def _press(self, x, y, button):
        self.mouse = (x, y)
        if self._exit_hit(x, y):
            self.finish(abandon=True)
            return
        self.pressed = True
        self.on_press(x, y)

    def _release(self, x, y, button):
        self.mouse = (x, y)
        self.pressed = False
        self.on_release(x, y)

    def _key(self, name):
        if name == "Escape":
            self.finish(abandon=True)
            return True
        return False

    def _exit_rect(self):
        """Botón «Terminar partido»: arriba al centro, bajo el marcador."""
        s = self.S
        w, h = 200 * s, 34 * s
        return (self.W / 2 - w / 2, 14 * s + 64 * s + 34 * s, w, h)

    def _exit_hit(self, x, y):
        ex, ey, ew, eh = self._exit_rect()
        return ex <= x <= ex + ew and ey <= y <= ey + eh

    # ── tick ──────────────────────────────────────────────────────────────
    def _tick(self):
        if self.over:
            return False
        now = time.monotonic()
        if self.mouse is not None:
            if self.mouse_prev is not None:
                self.mvx = self.mouse[0] - self.mouse_prev[0]
                self.mvy = self.mouse[1] - self.mouse_prev[1]
            self.mouse_prev = self.mouse
        try:
            if now >= self.pause_until:
                self.update(now)
            for p in self.players:
                p.physics(1.3 * self.S)
                p.apply()
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()
        self.msgs = [m for m in self.msgs if m[1] > now]
        if self.mode == "time" and self.remaining() <= 0:
            self.finish()
        if self.pitch is not None:
            self.pitch.redraw()
        return True

    def remaining(self):
        return self.minutes * 60 - (time.monotonic() - self.t0)

    def point(self, who, label, pause=1.6):
        self.score[who] += self.points_for(who)
        self.say(label, pause, (1, .85, .3) if who == "you" else (1, .45, .5))
        for p in self.rivals:
            (p.celebrate if who == "pets" else p.sulk)()
        if self.helper:
            (self.helper.celebrate if who == "you" else self.helper.sulk)()
        self.pause_until = time.monotonic() + pause
        if self.mode == "points" and self.score[who] >= self.target:
            GLib.timeout_add(int(pause * 1000), lambda: (self.finish(), False)[1])

    def points_for(self, who):
        return 1

    def finish(self, abandon=False):
        if self.over:
            return
        self.over = True
        y, p = self.score["you"], self.score["pets"]
        self.result = "abandon" if abandon else ("win" if y > p else "lose" if p > y else "draw")
        if not abandon:
            text = {"win": tr("¡Ganaste! {a} – {b}", a=y, b=p),
                    "lose": tr("Ganaron las mascotas {b} – {a}", a=y, b=p),
                    "draw": tr("Empate {a} – {b}", a=y, b=p)}[self.result]
            self.say(text, 3.5, (1, 1, 1), size=1.4)
            for pl in self.rivals:
                (pl.celebrate if self.result == "lose" else pl.sulk)(90)
            if self.pitch is not None:
                self.pitch.redraw()
            GLib.timeout_add(3200, lambda: (self.stop(), False)[1])
        else:
            self.stop()

    def say(self, text, secs=1.5, color=(1, 1, 1), x=None, y=None, size=1.0):
        self.msgs.append((text, time.monotonic() + secs, color, x, y, size))

    def mouse_push(self, b, cap, k=1.15):
        """El cursor es un «pie» redondo: empuja el balón, nunca lo agarra.
        Cuanto más rápido lo empujas, más rápido sale."""
        if self.mouse is None or b.held or time.monotonic() < getattr(self, "no_push_until", 0):
            return False
        mx, my = self.mouse
        foot = self.FOOT * self.S
        dx, dy = b.x - mx, b.y - my
        d = math.hypot(dx, dy)
        if d >= b.r + foot or d == 0:
            return False
        nx, ny = dx / d, dy / d
        b.x, b.y = mx + nx * (b.r + foot), my + ny * (b.r + foot)
        rel = (self.mvx * nx + self.mvy * ny) - (b.vx * nx + b.vy * ny)
        if rel > 0:
            b.vx += nx * rel * k
            b.vy += ny * rel * k
        else:
            vn = b.vx * nx + b.vy * ny          # cursor quieto: rebota
            if vn < 0:
                b.vx -= (0.45 + k) * vn * nx
                b.vy -= (0.45 + k) * vn * ny
        sp = math.hypot(b.vx, b.vy)
        if sp > cap:
            b.vx, b.vy = b.vx * cap / sp, b.vy * cap / sp
        # el pie nunca saca el balón de la cancha
        b.x = min(max(b.x, b.r), self.W - b.r)
        b.y = min(max(b.y, b.r), self.F - b.r)
        return True

    # ── a implementar por cada deporte ────────────────────────────────────
    def setup(self):
        pass

    def update(self, now):
        pass

    def on_press(self, x, y):
        pass

    def on_release(self, x, y):
        pass

    def draw_field(self, cr):
        pass

    # ── dibujo común ──────────────────────────────────────────────────────
    def draw(self, cr, w, h):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        # una sombra muy suave sobre el suelo marca la cancha
        cr.set_source_rgba(1, 1, 1, 0.10)
        cr.rectangle(0, self.F - 3, self.W, 3)
        cr.fill()
        self.draw_field(cr)
        self.ball.draw(cr)
        self.draw_extra(cr)
        self._draw_board(cr)
        self._draw_exit(cr)
        now = time.monotonic()
        for i, (text, until, color, x, y, size) in enumerate(self.msgs):
            alpha = min(1.0, (until - now) / 0.4)
            self._text(cr, text, x if x is not None else self.W / 2,
                       y if y is not None else self.H * 0.32 + i * 46 * self.S,
                       34 * self.S * size, color, alpha)

    def draw_extra(self, cr):
        pass

    def _text(self, cr, text, x, y, px, color=(1, 1, 1), alpha=1.0, outline=True):
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(px)
        ext = cr.text_extents(text)
        tx, ty = x - ext.width / 2 - ext.x_bearing, y
        if outline:
            cr.move_to(tx, ty)
            cr.text_path(text)
            cr.set_source_rgba(0.08, 0.06, 0.12, 0.85 * alpha)
            cr.set_line_width(max(3, px / 7))
            cr.stroke()
        cr.move_to(tx, ty)
        cr.set_source_rgba(color[0], color[1], color[2], alpha)
        cr.show_text(text)
        cr.new_path()          # que el siguiente trazo no arranque desde el texto

    def _round_rect(self, cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()

    def _draw_board(self, cr):
        s = self.S
        bw, bh = 420 * s, 64 * s
        x, y = self.W / 2 - bw / 2, 14 * s
        self._round_rect(cr, x, y, bw, bh, 12 * s)
        cr.set_source_rgba(0.09, 0.08, 0.15, 0.86)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.25)
        cr.set_line_width(2)
        cr.stroke()
        self._text(cr, tr("TÚ"), x + 62 * s, y + 41 * s, 22 * s, (0.6, 0.85, 1), outline=False)
        self._text(cr, tr("MASCOTAS"), x + bw - 82 * s, y + 41 * s, 20 * s, (1, 0.7, 0.8), outline=False)
        self._text(cr, f"{self.score['you']}  –  {self.score['pets']}",
                   self.W / 2, y + 40 * s, 30 * s, (1, 1, 1), outline=False)
        if self.mode == "time":
            r = max(0, int(self.remaining()))
            sub = f"{r // 60:02d}:{r % 60:02d}"
        else:
            sub = tr("a {n} puntos", n=self.target)
        self._text(cr, sub, self.W / 2, y + bh + 24 * s, 17 * s, (1, 1, 1), 0.9)

    def _draw_exit(self, cr):
        x, y, w, h = self._exit_rect()
        self._round_rect(cr, x, y, w, h, 10 * self.S)
        cr.set_source_rgba(0.09, 0.08, 0.15, 0.8)
        cr.fill()
        cr.set_source_rgba(1, 0.45, 0.5, 0.9)
        cr.set_line_width(2)
        self._round_rect(cr, x, y, w, h, 10 * self.S)
        cr.stroke()
        self._text(cr, tr("Terminar partido (Esc)"), x + w / 2, y + h * 0.66, 15 * self.S,
                   (1, 1, 1), outline=False)

    def draw_ring(self, cr, ring, now, x, y):
        """Anillo osu: se cierra hasta el borde del balón en el instante justo."""
        p = ring.progress(now)
        r = self.ball.r * (1.0 + 3.2 * p) + 2
        col = {"spike": (1, 0.85, 0.3), "block": (1, 0.55, 0.35),
               "dig": (0.45, 0.85, 1)}.get(ring.kind, (1, 1, 1))
        cr.set_source_rgba(col[0], col[1], col[2], 0.95)
        cr.set_line_width(max(3, 5 * self.S))
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgba(1, 1, 1, 0.55)
        cr.set_line_width(2)
        cr.arc(x, y, self.ball.r + 2, 0, 2 * math.pi)
        cr.stroke()


def grade_label(q):
    if q >= 0.85:
        return tr("¡Perfecto!"), (1, 0.9, 0.3)
    if q >= 0.55:
        return tr("¡Bien!"), (0.6, 1, 0.6)
    if q > 0.0:
        return tr("Regular"), (0.8, 0.85, 1)
    return tr("Fallaste"), (1, 0.5, 0.5)


def chance(p):
    return random.random() < p
