"""
Juguetes: una pelota o un ovillo que se lanza con el mouse.

Un juguete es una MascotWindow más (misma ventana compacta, mismo arrastre por
backend) en modo "toy": en vez del modo Vida corre una física de pelota —
gravedad, rebote, rodar con rozamiento, chocar con los bordes y apoyarse en
las ventanas— y gira sobre su centro al rodar. Las mascotas en modo Vida lo
persiguen y lo patean (ver core/companion.py).

  - arrastrar y soltar rápido → lo lanzas
  - un clic → un toquecito
  - doble clic → guardarlo (desaparece)
"""
import math
import random

from gi.repository import GLib

from .clock import Clock

TOY_KINDS = {
    # nombre: (rebote, rozamiento al rodar, gravedad relativa)
    "ball": (0.62, 0.965, 1.0),
    "yarn": (0.30, 0.90, 0.9),
}
TOY_TICK = 33            # ms: la pelota se mueve más fino que las mascotas


class ToyMixin:
    _tvx = 0.0
    _tvy = 0.0
    _spin_deg = 0.0
    _toy_rest_since = 0
    toy_kind = "ball"

    def is_toy(self):
        return self.mode == "toy"

    def _enter_toy(self):
        self.toy_kind = self.anim.get("toy", "ball")
        self._floor_y = max(0, self._screen_h - self._floor_offset_y - self._cat_h)
        self._ground_y = self._floor_y
        self._toy_rest_since = GLib.get_monotonic_time()
        if self._behavior_id is None and not self._paused:
            self._behavior_id = Clock.get().every(TOY_TICK, self._toy_tick)

    def toy_moving(self):
        return abs(self._tvx) > 0.3 or abs(self._tvy) > 0.5 or self._dragging

    def toy_idle_s(self):
        """Segundos que lleva quieto (0 si se mueve)."""
        if self.toy_moving():
            return 0.0
        return (GLib.get_monotonic_time() - self._toy_rest_since) / 1e6

    def toy_throw(self, vx_px_s, vy_px_s):
        # px/s del arrastre → px/tick de la física (acotado, como el lanzamiento
        # de mascotas: creíble, nunca un teletransporte)
        k = TOY_TICK / 1000.0 * 0.9
        self._tvx = max(-40.0, min(40.0, vx_px_s * k))
        self._tvy = max(-45.0, min(10.0, vy_px_s * k))

    def kick(self, direction, power=1.0):
        """Una mascota (o un clic) lo patea."""
        self._tvx = direction * random.uniform(9, 14) * power
        self._tvy = -random.uniform(8, 13) * power
        self._paintable.set_squash(1.15, 0.85)

    def _toy_tick(self):
        if self._paused:
            return True
        if self._dragging:
            self._toy_rest_since = GLib.get_monotonic_time()
            return True
        bounce, friction, gk = TOY_KINDS.get(self.toy_kind, TOY_KINDS["ball"])
        self._tvy += 1.1 * gk
        nx = self._x + self._tvx
        ny = self._y + self._tvy
        right = max(0, self._screen_w - self._cat_w)
        if nx <= 0:
            nx, self._tvx = 0, abs(self._tvx) * 0.7
        elif nx >= right:
            nx, self._tvx = right, -abs(self._tvx) * 0.7
        if ny < 0:
            ny, self._tvy = 0, abs(self._tvy) * 0.5
        ground = self._ground_for_x(nx + self._cat_w / 2, self._y)
        on_ground = False
        if ny >= ground:
            ny = ground
            if self._tvy > 3.0:
                self._tvy = -self._tvy * bounce
                sq = min(0.25, abs(self._tvy) * 0.02)
                self._paintable.set_squash(1.0 + sq, 1.0 - sq)
            else:
                self._tvy = 0.0
                on_ground = True
            self._tvx *= friction
        else:
            self._paintable.set_squash(1.0, 1.0)
        if on_ground and abs(self._tvx) < 0.25:
            self._tvx = 0.0
        if self.toy_moving():
            self._toy_rest_since = GLib.get_monotonic_time()
        # girar al rodar: ángulo = distancia / radio
        r = max(4.0, self._cat_w / 2.0)
        self._spin_deg = (self._spin_deg + math.degrees(self._tvx / r)) % 360
        self._paintable.set_spin(round(self._spin_deg, 1))
        if (int(nx), int(ny)) != (self._x, self._y):
            self._set_position(nx, ny)
        return True
