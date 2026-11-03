"""
Compañía: lo que la mascota hace por lo que pasa en el equipo y con los demás.

Se mezcla en MascotWindow junto a LiveAnimationMixin. El cerebro (quién juega
con quién, qué suena, qué hora es) vive en core/companion.py; aquí solo están
las órdenes que cada mascota sabe cumplir y el tick de esos estados nuevos:

  set_mood(m)        "dance" (suena música) | "tired" (CPU alta) |
                     "worried" (batería baja) | "night" (de noche) | None
  startle()          llegó una notificación: «!», brinquito y mira arriba
  say(t) / set_sign  globo de texto temporal / cartel fijo (Pomodoro)
  stretch()          se estira (descanso del Pomodoro)
  chase(x, modo)     ir hacia un punto: cursor, juguete u otra mascota
  flee(x)            huir de otra mascota (jugando a pillarse)
  hide_at(x)         esconderse detrás de una ventana (escondidas)
  sleep_near(x)      ir a dormir al lado de otra mascota

Todo usa SOLO las poses que el usuario dibujó. Si el pack trae poses con
nombre propio (dance, tired, worried, surprised, stretch) se usan; si no, se
cae a idle/default y el movimiento del cuerpo hace el resto. La app no
inventa cuadros.
"""
import math
import random
import time

from gi.repository import GLib

from . import bubble as _bubble

Cloud_CPS = _bubble.Cloud.CPS

# poses opcionales nuevas (ver folderimport.KNOWN_POSES y la guía del panel)
EXTRA_POSES = ("dance", "tired", "worried", "surprised", "stretch")

# estados que maneja este módulo (no los toca el tick de LiveAnimationMixin)
STATES = frozenset({"dance", "chase", "flee", "look_up", "stretch",
                    "to_hide", "hidden", "seek_sleep", "count", "talk"})
TALK_MAX_TICKS = 600    # red de seguridad: ~36 s quieta hablando como mucho
CLOUD_STUCK_S = 25      # nube «escuchando/pensando» sin respuesta: se cierra

CHASE_TTL = 90          # ticks (~5 s) sin nuevas órdenes → abandona
SPEED_RUN = 6           # px/tick base al correr (se escala por tamaño)


_GAP_CACHE = {}


def _top_gap(tex):
    """Fracción de la altura de la textura que está vacía ARRIBA (la caja del
    sprite es la unión de todas las poses: en reposo suele sobrar espacio
    sobre la cabeza). Se calcula una vez por textura."""
    if tex is None:
        return 0.0
    key = id(tex)
    if key in _GAP_CACHE:
        return _GAP_CACHE[key]
    frac = 0.0
    try:
        import numpy as np
        from gi.repository import Gdk
        dl = Gdk.TextureDownloader.new(tex)
        dl.set_format(Gdk.MemoryFormat.R8G8B8A8)
        data, stride = dl.download_bytes()
        h, w = tex.get_height(), tex.get_width()
        a = np.frombuffer(data.get_data(), dtype=np.uint8)[: h * stride]
        alpha = a.reshape(h, stride)[:, 3:w * 4:4]
        rows = np.flatnonzero((alpha > 24).any(axis=1))
        if rows.size:
            frac = float(rows[0]) / h
    except Exception:  # noqa: BLE001
        frac = 0.0
    if len(_GAP_CACHE) > 256:
        _GAP_CACHE.clear()
    _GAP_CACHE[key] = frac
    return frac


class CompanionMixin:
    _mood = None
    _say_id = 0
    _say_bubble = None
    _sign_bubble = None
    _sign_text = None
    _deco_pad = 0
    _chase_x = None
    _chase_mode = None
    _chase_ttl = 0
    _hidden_layer = False
    _sleep_x = None
    _stretch_t = 0
    _cloud = None           # bubble.Cloud mientras hablas con ella
    _cloud_id = 0
    _cloud_last = 0.0
    _cloud_hold = 0.0       # instante en que la nube se cierra sola
    _cloud_size = None

    # ───────────────────────── utilidades ──────────────────────────────────
    def _pose_or(self, *names):
        for n in names:
            if n == "default" or self._has_pose(n):
                return n
        return "default"

    def _speed_k(self):
        return {"tired": 0.5, "worried": 0.7}.get(self._mood, 1.0)

    def is_busy(self):
        """Ocupada con algo que no conviene interrumpir (arrastre, agarre,
        en el aire, escondida...)."""
        return (self._dragging or self._grabbing or
                self._state in ("grab", "jump", "toss", "falling", "to_climb",
                                "to_hide", "hidden", "count"))

    def is_awake(self):
        return self._state != "sleep" and self._state != "seek_sleep"

    def _on_ground(self):
        return self._state not in ("jump", "toss", "falling", "grab")

    # ───────────────────────── globos / cartel ─────────────────────────────
    def _show_bubble(self, b):
        if self._cloud is not None and b is not self._cloud:
            return                       # la nube de la charla manda
        self._paintable.set_bubble(b)
        need = 0
        if b is not None:
            bw, bh, anchor = _bubble.bubble_size(b)
            need = int(max(bw / 2 - self._cat_w / 2, bh - anchor)) + 8
        if need != self._deco_pad:
            self._deco_pad = need
            self._deco_changed()

    def _deco_changed(self):
        """El backend agranda su superficie compacta para que quepa el globo."""
        self._set_position(self._x, self._y)

    def say(self, text, secs=8, kind="speech"):
        if self._say_id:
            GLib.source_remove(self._say_id)
            self._say_id = 0
        self._say_bubble = _bubble.render(text, kind)
        self._show_bubble(self._say_bubble)
        self._say_id = GLib.timeout_add(int(secs * 1000), self._end_say)

    def _end_say(self):
        self._say_id = 0
        self._say_bubble = None
        self._show_bubble(self._sign_bubble)
        return False

    def set_sign(self, text):
        """Cartel fijo (Pomodoro). None lo quita."""
        if text == self._sign_text:
            return
        self._sign_text = text
        self._sign_bubble = _bubble.render(text, "sign") if text else None
        if self._say_bubble is None:
            self._show_bubble(self._sign_bubble)

    # ───────────────────────── hablar: nube animada ────────────────────────
    def talk_listen(self):
        """Te oyó llamarla: levanta la cabeza y abre la nube con «…»."""
        self._cloud_open("listen")

    def talk_think(self):
        self._cloud_open("think")

    def talk_say(self, text, final=True):
        """Escribe `text` en la nube (crece si llega en trozos). final=True:
        se queda un rato proporcional al texto y se cierra sola."""
        self._cloud_open("say", text)
        if final:
            secs = 3.2 + len(text) / Cloud_CPS + len(text) * 0.045
            self._cloud_hold = time.monotonic() + min(14.0, secs)
            self._talk_hop()
        else:
            self._cloud_hold = 0.0

    def talk_close(self):
        if self._cloud is not None:
            self._cloud.close()

    def is_talking(self):
        return self._cloud is not None

    def _cloud_open(self, mode, text=""):
        if self._cloud is None or self._cloud.closing_at is not None:
            self._cloud = _bubble.Cloud(mode, text)
            self._cloud_size = None
            frac = _top_gap(getattr(self._paintable, "_tex", None))
            self._cloud.head_frac = frac
            self._cloud.head_px = frac * self._cat_h
        else:
            self._cloud.set(mode, text)
        self._cloud_hold = 0.0
        self._talk_pose(mode)
        self._cloud_relayout()
        if not self._cloud_id:
            self._cloud_last = time.monotonic()
            self._cloud_id = GLib.timeout_add(33, self._cloud_tick)

    def _talk_pose(self, mode):
        if self.mode != "life" or self.is_busy() and self._state != "talk":
            return
        if self._state == "sleep":
            self._wake_soft()
        if self._state != "talk":
            self._state = "talk"
            self._speed = 0
            self._chase_x = None
        self._state_ttl = TALK_MAX_TICKS
        self._set_pose(self._pose_or("greet", "idle") if mode == "listen"
                       else self._pose_or("idle"))

    def _talk_hop(self):
        if self.mode == "life" and self._state == "talk" and self._on_ground():
            self._squash(1.08, 0.9)

    def _cloud_relayout(self):
        c = self._cloud
        if c is None:
            return
        half = c.size()[0] / 2.0
        cx = self._x + self._cat_w / 2.0
        lo, hi = half + 4, self._screen_w - half - 4
        want = min(max(cx, lo), hi) if hi > lo else cx
        c.shift_x = want - cx
        size = c.size()
        if size != self._cloud_size:
            self._cloud_size = size
            self._show_bubble(c)

    def _cloud_tick(self):
        c = self._cloud
        if c is None:
            self._cloud_id = 0
            return False
        now = time.monotonic()
        dt, self._cloud_last = now - self._cloud_last, now
        c.step(dt)
        if c.closing_at is None and self._cloud_hold and now >= self._cloud_hold \
                and c.typing_done():
            c.close()
        # red de seguridad: escuchando/pensando sin respuesta (micrófono que
        # falló, IA colgada…) no se queda abierta para siempre
        if c.closing_at is None and c.mode in ("listen", "think") \
                and now - c.mode_t > CLOUD_STUCK_S:
            c.close()
        if c.finished():
            self._cloud = None
            self._cloud_id = 0
            self._cloud_hold = 0.0
            self._cloud_size = None
            self._show_bubble(self._say_bubble or self._sign_bubble)
            if self._state == "talk":
                self._state = "rest"
                self._rest_ttl = random.randint(6, 14)
                self._set_pose(self._pose_or("idle"))
            return False
        self._cloud_relayout()
        self._paintable.invalidate_contents()
        return True

    # ───────────────────────── reacciones al sistema ───────────────────────
    def set_mood(self, mood):
        if mood == self._mood:
            return
        self._mood = mood
        if self.mode != "life":
            return
        if mood is None and self._state == "dance":
            self._state_ttl = 0          # termina el baile en el próximo paso
        elif mood == "dance" and self._state in ("idle", "walk", "rest") \
                and not self.is_busy():
            self._start_dance()

    def startle(self):
        """Notificación: se sobresalta y mira hacia arriba."""
        if self.mode != "life" or self.is_busy():
            return
        if self._state == "sleep":
            self._wake_soft()
        self.say("!", 1.6, "alert")
        self.face_toward(self._x + self._cat_w / 2 + (1 if random.random() < .5 else -1))
        self._state = "jump"
        self._jump_vy = -7 * self._phys_k
        self._squash(0.9, 1.12)
        self._lean_to(-10 if not self._facing_left else 10)
        self._set_pose(self._pose_or("surprised", "jump"))

    def _wake_soft(self):
        self._idle_accum = 0
        self._state = "rest"
        self._rest_ttl = random.randint(6, 14)

    def stretch(self):
        """Descanso del Pomodoro: se estira despacio (~2 s)."""
        if self.mode != "life" or self.is_busy():
            return
        if self._state == "sleep":
            self._wake_soft()
        self._state = "stretch"
        self._stretch_t = 0
        self._speed = 0
        self._set_pose(self._pose_or("stretch", "idle"))

    def _start_dance(self):
        self._state = "dance"
        self._state_ttl = random.randint(50, 110)
        self._speed = 0
        self._idle_accum = 0
        self._set_pose(self._pose_or("dance", "idle"))

    # ───────────────────────── perseguir / huir ────────────────────────────
    def chase(self, tx, mode="cursor", run=True):
        """Ir hacia la X local `tx`. mode: "cursor" (se acerca y mira arriba),
        "laser" (lo persigue corriendo y salta), "toy", "pet"."""
        if self.mode != "life" or self.is_busy():
            return False
        if self._state == "sleep" and mode != "toy":
            return False
        self._chase_x = float(tx)
        self._chase_mode = mode
        self._chase_ttl = CHASE_TTL
        if self._state not in ("chase", "flee"):
            self._state = "chase"
            self._idle_accum = 0
        self._state = "chase"
        k = (SPEED_RUN if run else 3) * self._phys_k * self._speed_k()
        if mode == "laser":
            k *= 1.25
        self._speed = max(2, round(k))
        self._set_pose(self._pose_or("walk"))
        return True

    def flee(self, from_x):
        if self.mode != "life" or self.is_busy() or self._state == "sleep":
            return False
        away = -1 if from_x > self._x + self._cat_w / 2 else 1
        self._chase_x = self._x + away * 400
        self._chase_mode = "flee"
        self._chase_ttl = CHASE_TTL
        self._state = "flee"
        self._speed = max(2, round(SPEED_RUN * 0.9 * self._phys_k))
        self._set_pose(self._pose_or("walk"))
        return True

    def stop_chase(self):
        if self._state in ("chase", "flee"):
            self._state = "rest"
            self._rest_ttl = random.randint(6, 12)
            self._set_pose(self._pose_or("idle"))

    def _move_toward(self, tx):
        """Un paso hacia tx por el suelo/plataforma. True al llegar."""
        right = max(0, self._screen_w - self._cat_w)
        tx = min(max(0.0, tx), right)
        dx = tx - self._x
        if abs(dx) <= self._speed:
            nx = tx
        else:
            self._dir = 1 if dx > 0 else -1
            self._facing_left = self._dir < 0
            nx = self._x + self._dir * self._speed
        stride = max(8.0, self._cat_w * 0.45)
        self._walk_phase += abs(nx - self._x) / stride
        support = self._support_at(nx + self._cat_w / 2, self._y)
        if support is None:
            self._x = int(nx)
            self._toss_vx = self._toss_vy = 0.0
            self._state = "falling"
            self._set_pose(self._pose_or("fall", "jump"))
            return False
        self._ground_y = support
        self._set_position(nx, support)
        return abs(tx - self._x) < 1

    def _pounce(self, toward):
        self._dir = 1 if toward > self._x else -1
        self._state = "toss"
        self._toss_vx = self._dir * 4.5 * self._phys_k
        self._toss_vy = -10.0 * self._phys_k
        self._facing_left = self._dir < 0
        self._squash(0.86, 1.16)
        self._lean_to(-self._dir * 8)
        self._set_pose(self._pose_or("jump"))

    # ───────────────────────── escondidas / dormir juntas ──────────────────
    def can_hide(self):
        return hasattr(self, "_set_behind_windows")

    def hide_at(self, tx):
        if self.mode != "life" or self.is_busy() or not self.can_hide():
            return False
        if self._state == "sleep":
            return False
        self._chase_x = float(tx)
        self._state = "to_hide"
        self._chase_ttl = CHASE_TTL * 2
        self._speed = max(2, round(SPEED_RUN * self._phys_k))
        self._set_pose(self._pose_or("walk"))
        return True

    def unhide(self):
        if self._hidden_layer:
            self._set_behind_windows(False)
            self._hidden_layer = False
        if self._state in ("hidden", "to_hide"):
            self._state = "jump"                 # ¡aquí estoy!
            self._jump_vy = -13 * self._phys_k
            self._squash(0.85, 1.18)
            self._set_pose(self._pose_or("jump"))

    def is_hidden(self):
        return self._state == "hidden"

    def count(self, secs=3):
        """La que busca: se queda quieta de espaldas «contando»."""
        if self.mode != "life" or self.is_busy():
            return False
        self._state = "count"
        self._state_ttl = int(secs * 1000 / 60)
        self._speed = 0
        self._set_pose(self._pose_or("idle"))
        return True

    def sleep_near(self, tx):
        if self.mode != "life" or self.is_busy() or self._state == "sleep":
            return False
        self._sleep_x = float(tx)
        self._state = "seek_sleep"
        self._chase_ttl = CHASE_TTL * 2
        self._speed = max(1, round(3 * self._phys_k * self._speed_k()))
        self._set_pose(self._pose_or("walk"))
        return True

    def _fall_asleep(self):
        self._state = "sleep"
        self._speed = 0
        self._sleep_phase = 0
        self._set_pose(self._pose_or("sleep", "idle"))

    # ───────────────────────── tick ────────────────────────────────────────
    def _companion_pick(self):
        """Gancho de LiveAnimationMixin._pick_behavior. True si eligió algo."""
        mood = self._mood
        if mood == "dance" and random.random() < 0.75:
            self._start_dance()
            return True
        if mood in ("tired", "worried") and random.random() < 0.6:
            self._state = "idle"
            self._state_ttl = random.randint(30, 70)
            self._idle_accum += self._state_ttl
            self._speed = 0
            self._set_pose(self._pose_or(mood, "idle"))
            return True
        if mood == "night" and self._idle_accum >= 60 and random.random() < 0.5:
            self._fall_asleep()
            return True
        return False

    def _companion_tick(self):
        """Gancho de LiveAnimationMixin._behavior_tick. True si manejó el tick."""
        st = self._state
        if st not in STATES:
            # en reposo/quieta sin nada debajo (cambió la ventana o el
            # escritorio): a caer
            if st in ("idle", "rest") and self._y < self._floor_y:
                cx = self._x + self._cat_w / 2
                if self._support_at(cx, self._y) is None:
                    self._toss_vx = self._toss_vy = 0.0
                    self._state = "falling"
                    self._set_pose(self._pose_or("fall", "jump"))
                    return True
            return False

        if st == "dance":
            self._state_ttl -= 1
            if self._state_ttl <= 0 or self._mood != "dance":
                self._pick_behavior()
            return True

        if st == "stretch":
            self._stretch_t += 1
            if self._stretch_t > 36:
                self._state = "rest"
                self._rest_ttl = 10
                self._set_pose(self._pose_or("idle"))
            return True

        if st == "look_up":
            self._state_ttl -= 1
            self._lean_to(-7 if not self._facing_left else 7)
            if self._state_ttl <= 0:
                self._pick_behavior()
            return True

        if st == "count":
            self._state_ttl -= 1
            if self._state_ttl <= 0:
                self._state = "rest"
                self._rest_ttl = 4
            return True

        if st == "hidden":
            return True

        if st == "talk":
            self._state_ttl -= 1
            if self._state_ttl <= 0 or self._cloud is None:
                self._state = "rest"
                self._rest_ttl = 6
                self._set_pose(self._pose_or("idle"))
            return True

        self._chase_ttl -= 1
        if self._chase_ttl <= 0:
            if st == "to_hide":
                self._state = "rest"
                self._rest_ttl = 6
            else:
                self.stop_chase()
            if st == "seek_sleep":
                self._state = "rest"
                self._rest_ttl = 6
            return True

        if st == "to_hide":
            if self._move_toward(self._chase_x):
                self._state = "hidden"
                self._set_pose(self._pose_or("idle"))
                self._set_behind_windows(True)
                self._hidden_layer = True
            return True

        if st == "seek_sleep":
            if self._move_toward(self._sleep_x):
                self._fall_asleep()
            return True

        # chase / flee
        tx = self._chase_x
        if st == "flee":
            right = max(0, self._screen_w - self._cat_w)
            if self._x <= 0 or self._x >= right:
                # acorralada contra el borde: se escabulle hacia el otro lado
                self._chase_x = tx = (right if self._x <= 0 else 0)
                if random.random() < 0.3:
                    self._pounce(tx)
                    return True
        arrived = self._move_toward(tx)
        if self._state != st:
            return True                     # se cayó por un borde
        if arrived and st == "chase":
            mode = self._chase_mode
            if mode == "cursor":
                self._state = "look_up"
                self._state_ttl = random.randint(30, 60)
                self._speed = 0
                self._set_pose(self._pose_or("greet", "idle")
                               if random.random() < 0.4 else self._pose_or("idle"))
            elif mode == "laser":
                if random.random() < 0.35:
                    self._pounce(tx + random.choice((-1, 1)) * self._cat_w)
                else:
                    self._set_pose(self._pose_or("idle"))
            else:
                self._set_pose(self._pose_or("idle"))
        return True

    # ───────────────────────── cuerpo ──────────────────────────────────────
    def _companion_body(self, t):
        """Movimiento del cuerpo de los estados nuevos, o None."""
        st = self._state
        if st == "dance":
            beat = abs(math.sin(t * math.pi / 8))      # ~125 bpm a 60 ms/tick
            return (1.0 + 0.04 * beat, 1.0 - 0.07 * beat,
                    10.0 * math.sin(t * math.pi / 16), 0.06 * beat)
        if st == "stretch":
            p = math.sin(min(1.0, self._stretch_t / 36.0) * math.pi)
            return 1.0 - 0.06 * p, 1.0 + 0.14 * p, 2.0 * p, 0.0
        if st in ("chase", "flee", "to_hide", "seek_sleep"):
            p = self._walk_phase * math.pi
            air = abs(math.sin(p))
            sy = 0.95 + 0.07 * air
            return 1.0 + (1.0 - sy) * 0.8, sy, 7.0 * math.sin(p) + 4 * self._dir, 0.07 * air
        if st == "count":
            return 1.0, 1.0, 0.0, 0.0
        if st == "talk":
            c = self._cloud
            if c is not None and c.mode == "say" and not c.typing_done():
                b = abs(math.sin(t * 1.9))           # «habla»: rebotito
                return 1.0 + 0.025 * b, 1.0 - 0.04 * b, 0.0, 0.02 * b
            if c is not None and c.mode == "listen":
                return 1.0, 1.0, (-6.0 if not self._facing_left else 6.0), 0.0
            b = math.sin(t * 0.6)
            return 1.0 + 0.01 * b, 1.0 - 0.015 * b, 0.0, 0.0
        if st in ("idle", "rest"):
            if self._mood == "tired":                 # jadea, cabizbaja
                b = math.sin(t * 0.9)
                return 1.0 + 0.012 * b, 1.0 - 0.025 * b, 6.0, 0.0
            if self._mood == "worried":               # tiembla un poco
                return 1.0 + 0.01 * math.sin(t * 3.1), 1.0, 2.0 * math.sin(t * 2.7), 0.0
        return None
