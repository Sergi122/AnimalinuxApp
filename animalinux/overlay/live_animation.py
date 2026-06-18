"""
Modo Vida del overlay: comportamiento autónomo de la mascota.

Contiene LiveAnimationMixin, que se mezcla en MascotWindow (ver
normal_animation.py). Toda la lógica de caminar / idle / saltar / rebotar /
saludar / enojarse / agarrar el ratón / tiro parabólico vive aquí.

Estos métodos asumen que el host (MascotWindow) aporta: self.anim,
self._set_position, self._has_pose, self._update_input_region, self.picture,
self._screen_w/_screen_h, self._floor_y, self._x/_y, self._cat_w/_cat_h y el
resto del estado de comportamiento inicializado en MascotWindow.__init__.
"""
import random

from gi.repository import GLib  # noqa: E402

BEHAVIOR_INTERVAL = 60      # ms entre pasos (modo Vida)
GRAVITY = 2                 # px/tick^2 para el salto
GREET_TICKS = 25            # cuánto dura el saludo
GREET_COOLDOWN = 80         # ticks (~5 s) entre saludos por proximidad


class LiveAnimationMixin:
    """Comportamiento 'con vida'. Se mezcla en MascotWindow."""

    def _react_to_touch(self):
        """Tocarla la sobresalta; si insistes (4 clicks), agarra el ratón."""
        if self._grab_ttl > 0:
            return   # ya está en modo agarre
        self._anger = min(4, self._anger + 1)
        self._react_ttl = 14
        self._jitter_base = self._x
        if self._has_pose("angry"):
            self._pose = "angry"
        elif self._has_pose("greet"):
            self._pose = "greet"

        if self._anger >= 4:
            # ¡Harta! → agarra el ratón
            self._start_grab()
        elif self._anger >= 2:
            # enojada: se voltea y sale corriendo
            self._facing_left = not self._facing_left
            self._state = "walk"
            self._dir = 1 if not self._facing_left else -1
            self._speed = 5
            self._state_ttl = 50
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
            self._pose = "grab"
        elif self._has_pose("angry"):
            self._pose = "angry"
        self._update_input_region()   # ahora captura el cursor en toda la pantalla

    def _on_grab_motion(self, ctrl, mx, my):
        """En grab el sprite sigue el cursor de forma RELATIVA (igual que el
        arrastre): se ancla en el primer movimiento y luego se desplaza por el
        mismo delta que el cursor. Así NO salta a la posición del puntero al
        empezar (eso se veía como un teletransporte) y es inmune a cualquier
        desfase entre coordenadas de ventana y del sprite."""
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

    def _enter_life(self):
        scale = self.anim.get("scale", 1.0)
        h = int(self.anim.get("height", 100) * scale)
        self._floor_y = max(0, self._screen_h - h)
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
        self._pose = "default"
        self._index = 0

    def _pick_behavior(self):
        r = random.random()
        if r < 0.22:
            # pausa breve; a veces se gira para "mirar alrededor"
            self._state = "idle"
            self._state_ttl = random.randint(15, 45)
            self._speed = 0
            if random.random() < 0.35:
                self._facing_left = not self._facing_left
                self._dir = -1 if self._facing_left else 1
            self._pose = "idle" if self._has_pose("idle") else "default"
        elif r < 0.72:
            # caminar: tramos largos y mantiene el rumbo casi siempre
            # (cambiar de dirección sólo el 25% de las veces = menos nervioso)
            self._state = "walk"
            self._state_ttl = random.randint(45, 120)
            if random.random() < 0.25 or self._dir == 0:
                self._dir = random.choice([-1, 1])
            self._speed = random.randint(2, 4)
            self._facing_left = self._dir < 0
            self._pose = "walk" if self._has_pose("walk") else "default"
        elif r < 0.88:
            # brinco hacia adelante: avanza mientras salta
            self._start_hop()
        else:
            # salto vertical en el sitio
            self._start_jump()

    def _start_jump(self):
        self._state = "jump"
        self._jump_vy = -random.randint(14, 22)   # impulso hacia arriba
        self._pose = "jump" if self._has_pose("jump") else "default"

    def _start_hop(self):
        """Brinco con avance horizontal (reusa la física de 'toss')."""
        if self._dir == 0:
            self._dir = random.choice([-1, 1])
        self._state = "toss"
        self._toss_vx = self._dir * random.uniform(2.5, 4.5)
        self._toss_vy = -float(random.randint(9, 14))
        self._facing_left = self._toss_vx < 0
        self._pose = "jump" if self._has_pose("jump") else "default"
        self._index = 0

    def trigger_greet(self):
        """Saludar: usa la pose 'greet' si existe; si no, da un saltito."""
        if self._greet_ttl > 0 or self._greet_cd > 0:
            return
        if self._has_pose("greet"):
            self._greet_ttl = GREET_TICKS
            self._pose = "greet"
        elif self._state != "jump":
            self._start_jump()

    def _behavior_tick(self):
        if self._paused or self._dragging:
            return True

        # cooldown de saludo: decrementa siempre
        if self._greet_cd > 0:
            self._greet_cd -= 1

        # ── modo agarre del ratón (sigue el cursor; al soltar cae suave) ──
        if self._state == "grab":
            self._grab_ttl -= 1
            # el sprite ya sigue al cursor vía _on_grab_motion; aquí sólo cuenta
            if self._grab_ttl <= 0:
                self._grab_ttl = 0
                self._anger = 0
                # suelta el cursor y CAE SUAVE desde donde quedó (sin lanzarla
                # lejos → sin teletransporte). X no cambia.
                self._end_grab_restore()
                self._toss_vx = 0.0
                self._toss_vy = 0.0
                self._state = "falling"
                self._pose = "jump" if self._has_pose("jump") else "default"
                self._index = 0
            return True

        # ── caída libre (soltar suave en el aire) ──────────────────────────
        if self._state == "falling":
            if self._y < self._floor_y:
                self._toss_vy += GRAVITY
                ny = min(self._floor_y, self._y + int(self._toss_vy))
                self._set_position(self._x, ny)
            if self._y >= self._floor_y:
                self._toss_vy = 0.0
                self._rest_ttl = random.randint(12, 28)
                self._state = "rest"
            return True

        # ── tiro parabólico ────────────────────────────────────────────────
        if self._state == "toss":
            scale = self.anim.get("scale", 1.0)
            w = int(self.anim.get("width", 100) * scale)
            right = max(0, self._screen_w - w)
            # mover X con fricción; rebote en bordes SIN snap (la mascota puede
            # estar pasada el borde si la lanzaste desde ahí → solo invierte vx)
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
            self._toss_vx *= 0.88
            # mover Y con gravedad
            self._toss_vy += GRAVITY
            ny = self._y + int(self._toss_vy)
            # aterrizó en el suelo → descansa donde cayó
            if ny >= self._floor_y:
                ny = self._floor_y
                self._toss_vx = 0.0
                self._toss_vy = 0.0
                self._rest_ttl = random.randint(12, 30)
                self._state = "rest"
                self._pose = "idle" if self._has_pose("idle") else "default"
                self._index = 0
            self._set_position(int(nx), int(ny))
            return True

        # ── reposo tras aterrizar ──────────────────────────────────────────
        if self._state == "rest":
            if self._rest_ttl > 0:
                self._rest_ttl -= 1
                self._pose = "idle" if self._has_pose("idle") else "default"
            else:
                self._pick_behavior()
            return True

        # ── reacción al tocarla: tiembla unos ticks ────────────────────────
        # El temblor es RELATIVO a la posición actual (±2 px). Antes usaba un
        # _jitter_base ABSOLUTO fijado al tocarla: si la mascota se movía después
        # (arrastre/caminar), el temblor la teletransportaba a la X vieja.
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

        if self._state == "jump":
            self._y += self._jump_vy
            self._jump_vy += GRAVITY
            if self._y >= self._floor_y:        # aterrizó
                self._y = self._floor_y
                self._pick_behavior()
            self._set_position(self._x, self._y)
            return True

        self._state_ttl -= 1
        if self._state_ttl <= 0:
            self._pick_behavior()
        if self._state == "walk":
            scale = self.anim.get("scale", 1.0)
            w = int(self.anim.get("width", 100) * scale)
            right = max(0, self._screen_w - w)
            if self._x > right:
                # quedó pasada el borde derecho (p.ej. la arrastraste ahí):
                # vuelve ANDANDO paso a paso, sin saltar al borde (teleport)
                self._dir, self._facing_left = -1, True
                nx = self._x - self._speed
            else:
                nx = self._x + self._dir * self._speed
                if nx <= 0:
                    nx, self._dir, self._facing_left = 0, 1, False
                elif nx >= right:
                    nx, self._dir, self._facing_left = right, -1, True
            self._set_position(max(0, nx), self._floor_y)
        return True
