"""
Modo Vida del overlay: comportamiento autónomo de la mascota.

Contiene LiveAnimationMixin, que se mezcla en MascotWindow (ver
normal_animation.py).

Mejoras (modo Vida):
  1. Squash & stretch dinámico al saltar/aterrizar (vía ScaledPaintable).
  2. Caminado sincronizado a la distancia (no patina).
  3. Física escalada al tamaño de la mascota.
  4. Se duerme tras un rato quieta (con inclinación visible); despierta al
     interactuar.
  5. Anda por los bordes de las ventanas / se sienta encima (usa hyprctl) y
     ADEMÁS trepa proactivamente a una ventana cercana.
  7. Las mascotas se saludan al cruzarse y luego se ALEJAN (no se quedan pegadas).
  9. Transiciones de pose limpias (_set_pose).
 10. Inclinación (lean) al lanzarse/caer.
 11. Berrinche por aburrimiento: tras mucho rato SIN interacción del usuario, se
     hace grande y "agarra" el ratón unos segundos; si la siguen ignorando, se
     desactiva sola del panel.
"""
import math
import random

from gi.repository import GLib  # noqa: E402

BEHAVIOR_INTERVAL = 60      # ms entre pasos (modo Vida)
GRAVITY = 2                 # px/tick^2 base (se escala por tamaño)
GREET_TICKS = 25            # cuánto dura el saludo
GREET_COOLDOWN = 80         # ticks (~5 s) entre saludos por proximidad
REF_HEIGHT = 150            # altura de referencia para escalar la física
SLEEP_AFTER = 320           # ticks de quietud acumulada antes de dormirse (~19s)

# Berrinche por aburrimiento (idea 11). Segundos REALES sin interacción del
# usuario. Se pueden anular desde library.json (bored_grab_s / bored_grab_dur_s
# / bored_disable_s) — útil para probar con valores cortos.
BORED_GRAB_S = 15 * 60      # 15 min sin atención → agarra el ratón
BORED_GRAB_DUR_S = 10       # el agarre dura 10 s
BORED_DISABLE_S = 5 * 60    # 5 min más ignorada → se desactiva del panel


class LiveAnimationMixin:
    """Comportamiento 'con vida'. Se mezcla en MascotWindow."""

    # ───────────────────────── utilidades ──────────────────────────────────
    def _set_pose(self, name):
        """Idea 9: cambiar de pose reseteando el frame (sin saltos a mitad)."""
        if name != self._pose:
            self._pose = name
            self._index = 0

    def face_toward(self, target_cx):
        """Idea 7: girarse hacia un punto X."""
        my = self._x + self._cat_w / 2
        self._facing_left = target_cx < my
        self._dir = -1 if self._facing_left else 1

    # ── squash & stretch + lean (idea 1 y 10) ──────────────────────────────
    def _squash(self, sx, sy):
        self._sq_sx, self._sq_sy = sx, sy

    def _lean_to(self, deg):
        self._lean_target = deg

    def _apply_juice(self):
        self._sq_sx += (1.0 - self._sq_sx) * 0.35
        self._sq_sy += (1.0 - self._sq_sy) * 0.35
        self._lean += (self._lean_target - self._lean) * 0.4
        self._lean_target *= 0.7
        self._paintable.set_squash(round(self._sq_sx, 3), round(self._sq_sy, 3))
        self._paintable.set_lean(round(self._lean, 2))

    # ── plataformas = bordes de ventanas (idea 5) ───────────────────────────
    def _platforms(self):
        try:
            return self._app.manager.platforms
        except Exception:  # noqa: BLE001
            return []

    def _ground_for_x(self, cx, cur_top):
        best = self._floor_y
        for (x0, x1, top) in self._platforms():
            if x0 - 4 <= cx <= x1 + 4:
                gt = (top - self._mon_y) - self._cat_h
                if cur_top - 6 <= gt < best:
                    best = gt
        return best

    def _support_at(self, cx, level, tol=12):
        best = None

        def consider(gt):
            nonlocal best
            if abs(gt - level) <= tol and (best is None or
                                           abs(gt - level) < abs(best - level)):
                best = gt

        for (x0, x1, top) in self._platforms():
            if x0 <= cx <= x1:
                consider((top - self._mon_y) - self._cat_h)
        consider(self._floor_y)
        return best

    def _pick_climb_target(self):
        """Idea 5 (proactiva): elige una ventana cercana y alcanzable a la que
        trepar. Devuelve (x_donde_pararse, y_tope_sprite, altura_a_subir)."""
        max_h = 60 + 110 * self._phys_k     # cuánto puede subir de un salto
        best = None
        for (x0, x1, top) in self._platforms():
            lx0, lx1 = x0 - self._mon_x, x1 - self._mon_x
            gt = (top - self._mon_y) - self._cat_h
            climb_h = self._floor_y - gt
            if 40 <= climb_h <= max_h and (lx1 - lx0) >= self._cat_w + 10:
                sx = min(max(self._x, lx0 + 5), lx1 - self._cat_w - 5)
                if 0 <= sx <= self._screen_w - self._cat_w:
                    d = abs(sx - self._x)
                    if best is None or d < best[0]:
                        best = (d, sx, gt, climb_h)
        if best:
            return (best[1], best[2], best[3])
        return None

    # ───────────────────────── interacción usuario ─────────────────────────
    def _interaction_now(self):
        """Marca atención del USUARIO (resetea el reloj de aburrimiento)."""
        self._last_interaction = GLib.get_monotonic_time()
        self._bored_phase = 0
        if self._bored_grab:
            self._end_bored_grab()

    def _wake(self):
        """El usuario la toca/arrastra/pasa por encima: cuenta como atención y
        la despierta si dormía."""
        self._interaction_now()
        self._idle_accum = 0
        if self._state == "sleep":
            self._state = "rest"
            self._rest_ttl = random.randint(6, 14)

    def _react_to_touch(self):
        """Tocarla la sobresalta; si insistes (4 clicks), agarra el ratón."""
        self._wake()
        if self._grab_ttl > 0:
            return
        self._anger = min(4, self._anger + 1)
        self._react_ttl = 14
        self._jitter_base = self._x
        if self._has_pose("angry"):
            self._set_pose("angry")
        elif self._has_pose("greet"):
            self._set_pose("greet")

        if self._anger >= 4:
            self._start_grab()
        elif self._anger >= 2:
            self._facing_left = not self._facing_left
            self._state = "walk"
            self._dir = 1 if not self._facing_left else -1
            self._speed = max(1, round(5 * self._phys_k))
            self._state_ttl = 50
            self._set_pose("walk" if self._has_pose("walk") else "default")
        GLib.timeout_add_seconds(3, self._cool_down)

    def _start_grab(self):
        """La mascota agarra el cursor: la región de input cubre TODA la pantalla
        y el sprite sigue al puntero hasta soltarlo."""
        self._grab_ttl = 80
        self._state = "grab"
        self._grabbing = True
        self._grab_anchor = None
        self._toss_vx = 0.0
        self._toss_vy = 0.0
        if self._has_pose("grab"):
            self._set_pose("grab")
        elif self._has_pose("angry"):
            self._set_pose("angry")
        self._update_input_region()

    def _on_grab_motion(self, ctrl, mx, my):
        self._last_cursor_x = self._x + mx     # idea 6 (versión segura)
        if not self._grabbing or self._dragging:
            return
        if self._grab_anchor is None:
            self._grab_anchor = (mx, my, self._x, self._y)
            return
        mx0, my0, x0, y0 = self._grab_anchor
        self._set_position(x0 + (mx - mx0), y0 + (my - my0))

    def _end_grab_restore(self):
        self._grabbing = False
        self._update_input_region()

    def _cool_down(self):
        self._anger = max(0, self._anger - 1)
        return False

    # ───────────────────── berrinche por aburrimiento (idea 11) ────────────
    def _bored_cfg(self):
        try:
            c = self._app.library.config
            return (c.get("bored_grab_s", BORED_GRAB_S),
                    c.get("bored_grab_dur_s", BORED_GRAB_DUR_S),
                    c.get("bored_disable_s", BORED_DISABLE_S))
        except Exception:  # noqa: BLE001
            return (BORED_GRAB_S, BORED_GRAB_DUR_S, BORED_DISABLE_S)

    def _check_boredom(self):
        if self._dragging or self._grabbing or self._bored_grab:
            return
        grab_s, _dur, disable_s = self._bored_cfg()
        idle = (GLib.get_monotonic_time() - self._last_interaction) / 1_000_000.0
        if self._bored_phase == 0 and idle >= grab_s:
            self._bored_phase = 1
            self._start_bored_grab()
        elif self._bored_phase == 1 and idle >= grab_s + disable_s:
            self._bored_phase = 2
            self._disable_self()

    def _start_bored_grab(self):
        _g, dur, _d = self._bored_cfg()
        self._bored_grab = True
        self._orig_scale = self.anim.get("scale", 1.0)
        # se hace GRANDE
        self.set_scale(min(3.0, self._orig_scale * 2.5))
        self._start_grab()
        self._grab_ttl = max(1, int(dur * 1000 / BEHAVIOR_INTERVAL))   # ~10 s
        self._grab_keyboard(True)      # además bloquea el teclado

    def _end_bored_grab(self):
        self._bored_grab = False
        self._grab_ttl = 0
        self._grabbing = False
        self._grab_keyboard(False)
        try:
            self.set_scale(self._orig_scale)
        except Exception:  # noqa: BLE001
            pass
        self._update_input_region()
        self._state = "falling"
        self._set_pose("jump" if self._has_pose("jump") else "default")

    def _disable_self(self):
        """Se rinde: se quita del escritorio y se desmarca en el panel."""
        aid = self.anim.get("id")
        app = self._app

        def go():
            try:
                app.library.update(aid, on_desktop=False)
                app.manager.set_visible(aid, False)
            except Exception:  # noqa: BLE001
                pass
            return False
        GLib.timeout_add(30, go)

    # ───────────────────────── ciclo de vida ───────────────────────────────
    def _enter_life(self):
        scale = self.anim.get("scale", 1.0)
        h = int(self.anim.get("height", 100) * scale)
        self._phys_k = max(0.6, min(1.8, h / float(REF_HEIGHT)))
        self._gravity = GRAVITY * self._phys_k
        self._floor_y = max(0, self._screen_h - h)
        self._ground_y = self._floor_y
        self._last_interaction = GLib.get_monotonic_time()
        self._set_position(self._x, self._floor_y)
        self._pick_behavior()
        if self._behavior_id is None:
            self._behavior_id = GLib.timeout_add(
                BEHAVIOR_INTERVAL, self._behavior_tick)

    def _exit_life(self):
        if self._behavior_id:
            GLib.source_remove(self._behavior_id)
            self._behavior_id = None
        if self._bored_grab:
            self._end_bored_grab()
        self._facing_left = False
        self._set_pose("default")
        self._squash(1.0, 1.0)
        self._lean = self._lean_target = 0.0
        self._paintable.set_squash(1.0, 1.0)
        self._paintable.set_lean(0.0)

    def _pick_behavior(self):
        # retirarse tras saludar a otra mascota (idea 7: no quedarse pegadas)
        if self._retreat_from is not None:
            away = self._retreat_from
            self._retreat_from = None
            self._idle_accum = 0
            self._state = "walk"
            self._state_ttl = random.randint(40, 80)
            self._dir = -1 if away > (self._x + self._cat_w / 2) else 1
            self._facing_left = self._dir < 0
            self._speed = max(1, round(random.randint(3, 4) * self._phys_k))
            self._set_pose("walk" if self._has_pose("walk") else "default")
            return

        # dormirse tras mucha quietud (idea 4)
        if self._idle_accum >= SLEEP_AFTER:
            self._state = "sleep"
            self._speed = 0
            self._sleep_phase = 0
            self._set_pose("sleep" if self._has_pose("sleep")
                           else ("idle" if self._has_pose("idle") else "default"))
            return

        r = random.random()
        if r < 0.18:
            self._state = "idle"
            self._state_ttl = random.randint(15, 45)
            self._idle_accum += self._state_ttl
            self._speed = 0
            if random.random() < 0.35:
                self._facing_left = not self._facing_left
                self._dir = -1 if self._facing_left else 1
            elif getattr(self, "_last_cursor_x", None) is not None \
                    and random.random() < 0.4:
                self.face_toward(self._last_cursor_x)
            self._set_pose("idle" if self._has_pose("idle") else "default")
        elif r < 0.30 and self._try_climb():
            self._idle_accum = 0          # idea 5: trepar a una ventana
        elif r < 0.74:
            self._idle_accum = 0
            self._state = "walk"
            self._state_ttl = random.randint(45, 120)
            if random.random() < 0.25 or self._dir == 0:
                self._dir = random.choice([-1, 1])
            self._speed = max(1, round(random.randint(2, 4) * self._phys_k))
            self._facing_left = self._dir < 0
            self._set_pose("walk" if self._has_pose("walk") else "default")
        elif r < 0.88:
            self._idle_accum = 0
            self._start_hop()
        else:
            self._idle_accum = 0
            self._start_jump()

    def _try_climb(self):
        target = self._pick_climb_target()
        if not target:
            return False
        self._climb_target = target
        self._state = "to_climb"
        self._speed = max(2, round(3 * self._phys_k))
        self._set_pose("walk" if self._has_pose("walk") else "default")
        return True

    def _start_jump(self):
        self._state = "jump"
        self._jump_vy = -random.randint(14, 22) * self._phys_k
        self._squash(0.86, 1.16)
        self._set_pose("jump" if self._has_pose("jump") else "default")

    def _start_hop(self):
        if self._dir == 0:
            self._dir = random.choice([-1, 1])
        self._state = "toss"
        self._toss_vx = self._dir * random.uniform(2.5, 4.5) * self._phys_k
        self._toss_vy = -float(random.randint(9, 14)) * self._phys_k
        self._facing_left = self._toss_vx < 0
        self._squash(0.88, 1.14)
        self._lean_to(-self._dir * 8)
        self._set_pose("jump" if self._has_pose("jump") else "default")

    def trigger_greet(self):
        """Saludar. NO cuenta como atención del usuario (puede venir de otra
        mascota), pero sí saca del sueño."""
        if self._state == "sleep":
            self._state = "rest"
            self._rest_ttl = random.randint(6, 14)
        if self._greet_ttl > 0 or self._greet_cd > 0:
            return
        if self._has_pose("greet"):
            self._greet_ttl = GREET_TICKS
            self._set_pose("greet")
        elif self._state != "jump":
            self._start_jump()

    def meet(self, other_cx):
        """Idea 7: encuentro con otra mascota → mirarse, saludar y retirarse
        (para no quedarse pegadas / 'trabadas')."""
        if (self._greet_cd > 0 or self._greet_ttl > 0 or self._bored_grab or
                self._state in ("grab", "toss", "jump", "falling", "to_climb")):
            return
        self.face_toward(other_cx)
        self._retreat_from = other_cx
        self.trigger_greet()

    def _land(self, ny):
        self._squash(1.22, 0.82)
        self._lean_to(0)
        self._rest_ttl = random.randint(12, 28)
        self._state = "rest"
        self._set_pose("idle" if self._has_pose("idle") else "default")
        return ny

    # ───────────────────────── tick principal ──────────────────────────────
    def _behavior_tick(self):
        if self._paused or self._dragging:
            return True

        self._apply_juice()
        self._check_boredom()

        if self._greet_cd > 0:
            self._greet_cd -= 1

        # ── dormida (idea 4): respiración lenta + cabeza ladeada (visible) ──
        if self._state == "sleep":
            self._sleep_phase = getattr(self, "_sleep_phase", 0) + 1
            s = math.sin(self._sleep_phase * 0.10)
            self._paintable.set_squash(1.05 - 0.03 * s, 0.90 + 0.05 * s)
            self._paintable.set_lean(7.0)        # dormita inclinada
            return True

        # ── agarre del ratón (manual o por berrinche) ──────────────────────
        if self._state == "grab":
            self._grab_ttl -= 1
            if self._grab_ttl <= 0:
                self._grab_ttl = 0
                self._anger = 0
                if self._bored_grab:
                    self._end_bored_grab()
                else:
                    self._end_grab_restore()
                    self._toss_vx = 0.0
                    self._toss_vy = 0.0
                    self._state = "falling"
                    self._set_pose("jump" if self._has_pose("jump") else "default")
            return True

        # ── ir a trepar a una ventana (idea 5 proactiva) ───────────────────
        if self._state == "to_climb":
            tx, gt, climb_h = self._climb_target
            if abs(self._x - tx) <= self._speed + 1:
                self._x = tx
                vy = math.sqrt(2 * self._gravity * (climb_h + 24))
                self._state = "jump"
                self._jump_vy = -vy
                self._squash(0.85, 1.18)
                self._set_pose("jump" if self._has_pose("jump") else "default")
            else:
                self._dir = 1 if tx > self._x else -1
                self._facing_left = self._dir < 0
                nx = self._x + self._dir * self._speed
                stride = max(8.0, self._cat_w * 0.45)
                self._walk_phase += abs(self._speed) / stride
                self._set_position(max(0, nx), self._floor_y)
            return True

        # ── caída libre ────────────────────────────────────────────────────
        if self._state == "falling":
            center = self._x + self._cat_w / 2
            ground = self._ground_for_x(center, self._y)
            if self._y < ground:
                self._toss_vy += self._gravity
                ny = min(ground, self._y + int(self._toss_vy))
                self._set_position(self._x, ny)
            if self._y >= ground:
                self._toss_vy = 0.0
                self._ground_y = ground
                self._land(ground)
            return True

        # ── tiro parabólico / brinco ───────────────────────────────────────
        if self._state == "toss":
            scale = self.anim.get("scale", 1.0)
            w = int(self.anim.get("width", 100) * scale)
            right = max(0, self._screen_w - w)
            nx = self._x + self._toss_vx
            if nx <= 0:
                nx = 0
                self._toss_vx = abs(self._toss_vx) * 0.55
            elif nx >= right:
                nx = min(nx, self._x)
                if self._x <= right:
                    nx = right
                self._toss_vx = -abs(self._toss_vx) * 0.55
            self._facing_left = self._toss_vx < 0
            self._lean_to(-self._toss_vx * 1.8)
            self._toss_vx *= 0.88
            self._toss_vy += self._gravity
            ny = self._y + int(self._toss_vy)
            center = nx + self._cat_w / 2
            ground = self._ground_for_x(center, self._y)
            if ny >= ground:
                ny = ground
                self._toss_vx = 0.0
                self._toss_vy = 0.0
                self._ground_y = ground
                self._set_position(int(nx), int(ny))
                self._land(ny)
                return True
            self._set_position(int(nx), int(ny))
            return True

        # ── reposo tras aterrizar ──────────────────────────────────────────
        if self._state == "rest":
            if self._rest_ttl > 0:
                self._rest_ttl -= 1
                self._set_pose("idle" if self._has_pose("idle") else "default")
            else:
                self._pick_behavior()
            return True

        # ── reacción al tocarla ────────────────────────────────────────────
        if self._react_ttl > 0:
            self._react_ttl -= 1
            self._set_position(self._x + random.randint(-2, 2), self._y)
            if self._react_ttl == 0 and self._pose in ("angry", "greet"):
                self._pick_behavior()
            return True

        if self._greet_ttl > 0:
            self._greet_ttl -= 1
            if self._greet_ttl == 0:
                self._greet_cd = GREET_COOLDOWN
                self._pick_behavior()
            return True

        # ── salto vertical ─────────────────────────────────────────────────
        if self._state == "jump":
            self._y += int(self._jump_vy)
            self._jump_vy += self._gravity
            center = self._x + self._cat_w / 2
            ground = self._ground_for_x(center, self._y)
            if self._y >= ground:
                self._y = ground
                self._ground_y = ground
                self._set_position(self._x, self._y)
                self._land(ground)
            else:
                self._set_position(self._x, self._y)
            return True

        # ── idle / walk ────────────────────────────────────────────────────
        self._state_ttl -= 1
        if self._state_ttl <= 0:
            self._pick_behavior()
        if self._state == "walk":
            scale = self.anim.get("scale", 1.0)
            w = int(self.anim.get("width", 100) * scale)
            right = max(0, self._screen_w - w)
            if self._x > right:
                self._dir, self._facing_left = -1, True
                nx = self._x - self._speed
            else:
                nx = self._x + self._dir * self._speed
                if nx <= 0:
                    nx, self._dir, self._facing_left = 0, 1, False
                elif nx >= right:
                    nx, self._dir, self._facing_left = right, -1, True
            nx = max(0, nx)
            stride = max(8.0, self._cat_w * 0.45)
            self._walk_phase += abs(self._dir * self._speed) / stride
            center = nx + self._cat_w / 2
            support = self._support_at(center, self._y)
            if support is not None:
                self._ground_y = support
                self._set_position(nx, support)
            else:
                # se acabó la plataforma → caer por el borde
                self._x = nx
                self._toss_vx = 0.0
                self._toss_vy = 0.0
                self._state = "falling"
                self._set_pose("jump" if self._has_pose("jump") else "default")
        return True
