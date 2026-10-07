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
from gi.repository import GLib

from ...overlay import x11_animation as _base
from . import win32


class MascotWindow(_base.MascotWindow):
    FORCE_COMPACT = True

    def __init__(self, app, anim, frames_dir, on_moved):
        super().__init__(app, anim, frames_dir, on_moved)
        self._hwnd = None
        self._k = win32.system_scale()      # lógico (GDK) -> físico (Win32)
        self.connect("map", lambda *_: GLib.idle_add(self._init_native))

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
