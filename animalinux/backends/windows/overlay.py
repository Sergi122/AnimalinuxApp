"""
MascotWindow de Windows: la MISMA clase que X11 (poses, modo Vida, arrastre,
física, berrinches) con las piezas del sistema cambiadas por Win32:

  - siempre la ventana compacta (del tamaño del sprite + holgura), movida con
    SetWindowPos: nada de una superficie transparente del tamaño del monitor
    por mascota, que es lo que más cuesta en CPU/RAM;
  - estilo TOOLWINDOW|NOACTIVATE|TOPMOST (sin barra de tareas ni foco robado);
  - región de la ventana recortada a la caja del sprite (clic-through fuera);
  - puntero global con GetCursorPos; suelo = área de trabajo (sobre la barra).
"""
import os
import sys

from gi.repository import GLib

from ...overlay import x11_animation as _base
from . import win32

_DEBUG = bool(os.environ.get("ANIMALINUX_DEBUG"))


class MascotWindow(_base.MascotWindow):
    FORCE_COMPACT = True
    # la clase base llama a _set_position/_move_x11 dentro de su __init__:
    # estos valores deben existir ANTES de que corra
    _hwnd = None
    _k = win32.system_scale()      # lógico (GDK) -> físico (Win32)

    def __init__(self, app, anim, frames_dir, on_moved):
        super().__init__(app, anim, frames_dir, on_moved)
        self.connect("map", lambda *_: GLib.idle_add(self._init_native))

    # ---- posición: nunca fuera de la pantalla ----
    def _set_position(self, x, y):
        """Las posiciones guardadas pueden venir de otra resolución o monitor
        (p.ej. x=1466 en una pantalla de 1024): la mascota quedaría invisible
        y sin forma de recuperarla. Se recorta a la pantalla visible."""
        x = min(int(x), max(0, self._screen_w - self._cat_w))
        y = min(int(y), max(0, self._screen_h - self._floor_offset_y - self._cat_h))
        if _DEBUG:
            print(f"[win32] {self.anim.get('name')}: pos=({x},{y}) "
                  f"screen=({self._screen_w}x{self._screen_h}) "
                  f"cat=({self._cat_w}x{self._cat_h})", file=sys.stderr, flush=True)
        super()._set_position(x, y)

    # ---- ventana nativa ----
    def _init_native(self):
        h = win32.hwnd_from_gtk(self)
        if h is None:
            return False
        self._hwnd = h
        win32.make_overlay_window(h)
        self._xpos = None
        self._move_x11()
        self._update_input_region()
        return False

    def _move_x11(self):          # mismo nombre: la clase base lo llama
        if self._hwnd is None:
            return
        pos = (int((self._mon_x + self._x - self._pad) * self._k),
               int((self._mon_y + self._y - self._pad) * self._k))
        if pos == self._xpos:
            return                 # sin cambio: ni una llamada al sistema
        self._xpos = pos
        win32.move_window(self._hwnd, pos[0], pos[1])

    def _update_input_region(self):
        if self._hwnd is None:
            return
        k = self._k
        win32.set_window_shape(self._hwnd, self._pad * k, self._pad * k,
                               self._cat_w * k, self._cat_h * k)

    # ---- puntero global ----
    def _global_pointer(self):
        p = win32.cursor_pos()
        if p is None:
            return None
        return int(p[0] / self._k), int(p[1] / self._k)

    def _poll_grab_cursor(self):
        p = self._global_pointer()
        if p is not None:
            self._on_grab_motion(None, p[0] - self._mon_x, p[1] - self._mon_y)

    # ---- suelo: encima de la barra de tareas ----
    def _refresh_floor_offset(self):
        try:
            _x, y, _w, h = win32.work_area()
            gap = int(self._screen_h - (y + h) / self._k)
        except Exception:  # noqa: BLE001
            return
        if not 0 <= gap <= 120:
            return
        if gap != self._floor_offset_y:
            self._floor_offset_y = gap
            if self.mode == "life" and self._floor_y:
                hgt = int(self.anim.get("height", 100) * self.anim.get("scale", 1.0))
                self._floor_y = max(0, self._screen_h - gap - hgt)
                self._ground_y = self._floor_y
