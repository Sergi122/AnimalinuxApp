"""
Modo Vida del overlay: comportamiento autónomo de la mascota.

Contiene LiveAnimationMixin, que se mezcla en MascotWindow (ver
normal_animation.py). Toda la lógica de caminar / idle / saltar / rebotar /
saludar / enojarse / agarrar el ratón / tiro parabólico vive aquí.

Mejoras (modo Vida):
  1. Squash & stretch dinámico al saltar/aterrizar (vía ScaledPaintable).
  2. Caminado sincronizado a la distancia (no patina).
  3. Física escalada al tamaño de la mascota.
  4. Se duerme tras mucho rato quieta; despierta al interactuar.
  5. Anda por los bordes de las ventanas / se sienta encima (usa hyprctl).
  7. Las mascotas se giran a mirarse al cruzarse.
  9. Transiciones de pose limpias (_set_pose).
 10. Inclinación (lean) al lanzarse/caer.

Estos métodos asumen que el host (MascotWindow) aporta: self.anim,
self._set_position, self._has_pose, self._update_input_region, self.picture,
self._paintable, self._screen_w/_screen_h, self._floor_y, self._x/_y,
self._cat_w/_cat_h, los offsets self._mon_x/_mon_y y el resto del estado de
comportamiento inicializado en MascotWindow.__init__.
"""
import math
import random

from gi.repository import GLib  # noqa: E402

BEHAVIOR_INTERVAL = 60      # ms entre pasos (modo Vida)
GRAVITY = 2                 # px/tick^2 base (se escala por tamaño)
GREET_TICKS = 25            # cuánto dura el saludo
GREET_COOLDOWN = 80         # ticks (~5 s) entre saludos por proximidad
REF_HEIGHT = 150            # altura de referencia para escalar la física
SLEEP_AFTER = 360           # ticks de quietud acumulada antes de dormirse (~22s)


class LiveAnimationMixin:
    """Comportamiento 'con vida'. Se mezcla en MascotWindow."""

    # ───────────────────────── utilidades ──────────────────────────────────
    def _set_pose(self, name):
        """Idea 9: cambiar de pose reseteando el frame para que no salte a
        mitad de ciclo. Si ya estamos en esa pose, no hace nada."""
        if name != self._pose:
            self._pose = name
            self._index = 0

    def face_toward(self, target_cx):
        """Idea 7: girarse hacia un punto X (otra mascota, etc.)."""
        my = self._x + self._cat_w / 2
        self._facing_left = target_cx < my
        self._dir = -1 if self._facing_left else 1

    # ── squash & stretch + lean (idea 1 y 10) ──────────────────────────────
    def _squash(self, sx, sy):
        self._sq_sx, self._sq_sy = sx, sy

    def _lean_to(self, deg):
        self._lean_target = deg

    def _apply_juice(self):
        """Suaviza el squash&stretch y el lean hacia el reposo cada tick y los
        empuja al paintable. Los eventos (saltar/aterrizar/lanzar) fijan un
        impulso y esto lo va relajando → efecto elástico."""
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
        """Y-tope del sprite (mascota) de la superficie sobre la que aterrizaría
        al caer desde cur_top en la columna cx: la plataforma más ALTA que esté
        por debajo de la posición actual; si no hay, el suelo."""
        best = self._floor_y
        for (x0, x1, top) in self._platforms():
            if x0 - 4 <= cx <= x1 + 4:
                gt = (top - self._mon_y) - self._cat_h
                if cur_top - 6 <= gt < best:
                    best = gt
        return best

    def _support_at(self, cx, level, tol=12):
        """Si en la columna cx hay una superficie (plataforma o suelo) a la
        altura 'level' (±tol), devuelve su y-tope; si no, None (→ caer)."""
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

    # ───────────────────────── interacción ─────────────────────────────────
    def _react_to_touch(self):
        """Tocarla la sobresalta; si insistes (4 clicks), agarra el ratón."""
        self._wake()
        if self._grab_ttl > 0:
            return   # ya está en modo agarre
        self._anger = min(4, self._anger + 1)
        self._react_ttl = 14
        self._jitter_base = self._x
        if self._has_pose("angry"):
            self._set_pose("angry")
        elif self._has_pose("greet"):
            self._set_pose("greet")

        if self._anger >= 4:
            # ¡Harta! → agarra el ratón
            self._start_grab()
        elif self._anger >= 2:
            # enojada: se voltea y sale corriendo
            self._facing_left = not self._facing_left
            self._state = "walk"
            self._dir = 1 if not self._facing_left else -1
            self._speed = max(1, round(5 * self._phys_k))
            self._state_ttl = 50
            self._set_pose("walk" if self._has_pose("walk") else "default")
        GLib.timeout_add_seconds(3, self._cool_down)

    def _start_grab(self):
        """La mascota agarra el cursor: amplía la región de input a toda la
        pantalla (la ventana YA es fullscreen) y el sprite sigue el puntero por
        todo el escritorio hasta soltarlo. NO redimensiona nada → sin artefactos."""
        self._grab_ttl = 80   # ~5 s a 60 ms/tick
        self._state = "grab"
        self._grabbing = True
        self._grab_anchor = None   # se fija en el primer movimiento (sin salto)
        self._toss_vx = 0.0
        self._toss_vy = 0.0
        if self._has_pose("grab"):
            self._set_pose("grab")
        elif self._has_pose("angry"):
            self._set_pose("angry")
        self._update_input_region()   # ahora captura el cursor en toda la pantalla

    def _on_grab_motion(self, ctrl, mx, my):
        """En grab el sprite sigue el cursor de forma RELATIVA (igual que el
        arrastre): se ancla en el primer movimiento y luego se desplaza por el
        mismo delta que el cursor. Así NO salta a la posición del puntero al
        empezar (eso se veía como un teletransporte) y es inmune a cualquier
        desfase entre coordenadas de ventana y del sprite."""
        # Idea 6 (versión segura): aunque no estemos en grab, recordar la última
        # X del cursor SOBRE la mascota para mirar hacia él en idle.
        self._last_cursor_x = self._x + mx
        if not self._grabbing or self._dragging:
            return
        if self._grab_anchor is None:
            self._grab_anchor = (mx, my, self._x, self._y)
            return
        mx0, my0, x0, y0 = self._grab_anchor
        self._set_position(x0 + (mx - mx0), y0 + (my - my0))

    def _end_grab_restore(self):
        """Suelta el cursor: la región de input vuelve a la caja del sprite.
        El sprite se queda DONDE estaba el cursor (self._x/_y), sin teleport."""
        self._grabbing = False
        self._update_input_region()

    def _cool_down(self):
        self._anger = max(0, self._anger - 1)
        return False

    def _wake(self):
        """Idea 4: despertar de un toque/arrastre/saludo."""
        self._idle_accum = 0
        if self._state == "sleep":
            self._state = "rest"
            self._rest_ttl = random.randint(6, 14)

    # ───────────────────────── ciclo de vida ───────────────────────────────
    def _enter_life(self):
        scale = self.anim.get("scale", 1.0)
        h = int(self.anim.get("height", 100) * scale)
        # Idea 3: física proporcional al tamaño (una mascota grande "pesa" más)
        self._phys_k = max(0.6, min(1.8, h / float(REF_HEIGHT)))
        self._gravity = GRAVITY * self._phys_k
        self._floor_y = max(0, self._screen_h - h)
        self._ground_y = self._floor_y
        self._set_position(self._x, self._floor_y)
        self._pick_behavior()
        if self._behavior_id is None:
            self._behavior_id = GLib.timeout_add(
                BEHAVIOR_INTERVAL, self._behavior_tick)

    def _exit_life(self):
        if self._behavior_id:
            GLib.source_remove(self._behavior_id)
            self._behavior_id = None
        self._facing_left = False
        self._set_pose("default")
        # devolver el sprite a su forma neutra
        self._squash(1.0, 1.0)
        self._lean = self._lean_target = 0.0
        self._paintable.set_squash(1.0, 1.0)
        self._paintable.set_lean(0.0)

    def _pick_behavior(self):
        # Idea 4: si lleva mucho rato quieta, dormirse
        if self._idle_accum >= SLEEP_AFTER:
            self._state = "sleep"
            self._speed = 0
            self._set_pose("sleep" if self._has_pose("sleep")
                           else ("idle" if self._has_pose("idle") else "default"))
            return
        r = random.random()
        if r < 0.22:
            # pausa breve; a veces se gira para "mirar alrededor"
            self._state = "idle"
            self._state_ttl = random.randint(15, 45)
            self._idle_accum += self._state_ttl
            self._speed = 0
            if random.random() < 0.35:
                self._facing_left = not self._facing_left
                self._dir = -1 if self._facing_left else 1
            elif getattr(self, "_last_cursor_x", None) is not None \
                    and random.random() < 0.4:
                # Idea 6: a veces mirar hacia donde estuvo el cursor
                self.face_toward(self._last_cursor_x)
            self._set_pose("idle" if self._has_pose("idle") else "default")
        elif r < 0.72:
            # caminar: tramos largos y mantiene el rumbo casi siempre
            self._idle_accum = 0
            self._state = "walk"
            self._state_ttl = random.randint(45, 120)
            if random.random() < 0.25 or self._dir == 0:
                self._dir = random.choice([-1, 1])
            self._speed = max(1, round(random.randint(2, 4) * self._phys_k))
            self._facing_left = self._dir < 0
            self._set_pose("walk" if self._has_pose("walk") else "default")
        elif r < 0.88:
            # brinco hacia adelante: avanza mientras salta
            self._idle_accum = 0
            self._start_hop()
        else:
            # salto vertical en el sitio
            self._idle_accum = 0
            self._start_jump()

    def _start_jump(self):
        self._state = "jump"
        self._jump_vy = -random.randint(14, 22) * self._phys_k   # impulso arriba
        self._squash(0.86, 1.16)                                 # stretch despegue
        self._set_pose("jump" if self._has_pose("jump") else "default")

    def _start_hop(self):
        """Brinco con avance horizontal (reusa la física de 'toss')."""
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
        """Saludar: usa la pose 'greet' si existe; si no, da un saltito."""
        self._wake()
        if self._greet_ttl > 0 or self._greet_cd > 0:
            return
        if self._has_pose("greet"):
            self._greet_ttl = GREET_TICKS
            self._set_pose("greet")
        elif self._state != "jump":
            self._start_jump()

    def _land(self, ny):
        """Aterrizaje: squash de impacto proporcional a la caída."""
        self._squash(1.0 + 0.22, 1.0 - 0.18)
        self._lean_to(0)
        self._rest_ttl = random.randint(12, 28)
        self._state = "rest"
        self._set_pose("idle" if self._has_pose("idle") else "default")
        self._index = 0
        return ny

    # ───────────────────────── tick principal ──────────────────────────────
    def _behavior_tick(self):
        if self._paused or self._dragging:
            return True

        self._apply_juice()   # squash&stretch + lean elásticos (ideas 1/10)

        # cooldown de saludo: decrementa siempre
        if self._greet_cd > 0:
            self._greet_cd -= 1

        # ── dormida (idea 4): respiración lenta hasta que la despierten ──────
        if self._state == "sleep":
            self._sleep_phase = getattr(self, "_sleep_phase", 0) + 1
            s = math.sin(self._sleep_phase * 0.12)
            self._paintable.set_squash(1.0 - 0.02 * s, 1.0 + 0.05 * s)
            return True

        # ── modo agarre del ratón (sigue el cursor; al soltar cae suave) ──
        if self._state == "grab":
            self._grab_ttl -= 1
            if self._grab_ttl <= 0:
                self._grab_ttl = 0
                self._anger = 0
                self._end_grab_restore()
                self._toss_vx = 0.0
                self._toss_vy = 0.0
                self._state = "falling"
                self._set_pose("jump" if self._has_pose("jump") else "default")
            return True

        # ── caída libre (soltar suave en el aire) ──────────────────────────
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

        # ── tiro parabólico ────────────────────────────────────────────────
        if self._state == "toss":
            scale = self.anim.get("scale", 1.0)
            w = int(self.anim.get("width", 100) * scale)
            right = max(0, self._screen_w - w)
            nx = self._x + self._toss_vx
            if nx <= 0:
                nx = 0
                self._toss_vx = abs(self._toss_vx) * 0.55
            elif nx >= right:
                nx = min(nx, self._x)          # nunca saltar a la derecha
                if self._x <= right:
                    nx = right
                self._toss_vx = -abs(self._toss_vx) * 0.55
            self._facing_left = self._toss_vx < 0
            self._lean_to(-self._toss_vx * 1.8)   # inclina según el avance
            self._toss_vx *= 0.88
            # mover Y con gravedad
            self._toss_vy += self._gravity
            ny = self._y + int(self._toss_vy)
            center = nx + self._cat_w / 2
            ground = self._ground_for_x(center, self._y)
            if ny >= ground:                       # aterrizó
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

        # ── reacción al tocarla: tiembla unos ticks (RELATIVO) ─────────────
        if self._react_ttl > 0:
            self._react_ttl -= 1
            self._set_position(self._x + random.randint(-2, 2), self._y)
            if self._react_ttl == 0 and self._pose in ("angry", "greet"):
                self._pick_behavior()
            return True

        if self._greet_ttl > 0:
            self._greet_ttl -= 1
            if self._greet_ttl == 0:
                self._greet_cd = GREET_COOLDOWN   # bloquea re-saludo ~5 s
                self._pick_behavior()
            return True

        # ── salto vertical en el sitio ─────────────────────────────────────
        if self._state == "jump":
            self._y += int(self._jump_vy)
            self._jump_vy += self._gravity
            center = self._x + self._cat_w / 2
            ground = self._ground_for_x(center, self._y)
            if self._y >= ground:               # aterrizó
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
                # quedó pasada el borde derecho: vuelve ANDANDO (sin teleport)
                self._dir, self._facing_left = -1, True
                nx = self._x - self._speed
            else:
                nx = self._x + self._dir * self._speed
                if nx <= 0:
                    nx, self._dir, self._facing_left = 0, 1, False
                elif nx >= right:
                    nx, self._dir, self._facing_left = right, -1, True
            nx = max(0, nx)
            # Idea 2: avanzar el frame de caminado con la distancia recorrida
            stride = max(8.0, self._cat_w * 0.45)
            self._walk_phase += abs(self._dir * self._speed) / stride
            # Idea 5: ¿sigue habiendo suelo bajo los pies a la nueva X?
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
