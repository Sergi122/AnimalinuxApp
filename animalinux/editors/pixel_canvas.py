"""
Lienzo del editor de píxeles — AnimaLinux (modelo y herramientas al estilo Aseprite).

  * Capas (visibilidad, bloqueo, opacidad) × fotogramas.
  * Herramientas: lápiz, borrador, bote, degradado, línea, rectángulo, elipse,
    contorno, marco, lazo, varita, mover, cuentagotas, mano, zoom.
  * Tintas (simple / composición alfa / bloquear alfa / tramado), opacidad,
    pincel cuadrado o redondo, modo pixel-perfect, simetría, modo mosaico.
  * Selección con máscara (Shift añade, Alt resta), copiar / cortar / pegar.
  * Vista fluida: zoom hacia el cursor, mover con Espacio / botón medio.

Todas las coordenadas de imagen son enteros; los píxeles se guardan RGBA
(orden Pillow) y se espejan en un búfer BGRA premultiplicado que se actualiza
píxel a píxel (sin reconvertir el fotograma en cada trazo).
"""
import functools
import math

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

import cairo
import numpy as np
from PIL import Image, ImageDraw

from .editor_utils import premultiply_bgra

ZOOM_STEPS = [1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64]
MAX_UNDO   = 100
MAX_FRAMES = 120
THUMB      = 44
ONION_ALPHA = 0.28
BG_VIEW    = (0.396, 0.333, 0.380)      # #655561 — gris violáceo de Aseprite

SHAPE_TOOLS = ("line", "rect", "ellipse", "contour", "gradient")
STROKE_TOOLS = ("pencil", "eraser")

BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
                  dtype=np.float32) / 16.0 + 1 / 32.0


# ── utilidades ───────────────────────────────────────────────────────────────
def _interp(x0, y0, x1, y1):
    """Bresenham inclusivo entre dos píxeles."""
    pts, dx, dy = [], abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x1 > x0 else -1
    sy = 1 if y1 > y0 else -1
    err = dx - dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy: err -= dy; x0 += sx
        if e2 <  dx: err += dx; y0 += sy
    return pts


@functools.lru_cache(maxsize=256)
def brush_offsets(size: int, shape: str):
    if size <= 1:
        return ((0, 0),)
    half = size // 2
    rng = range(-half, size - half)
    if shape == "square" or size <= 2:
        return tuple((dx, dy) for dy in rng for dx in rng)
    c, r = (size - 1) / 2, size / 2
    lim = r * r - r * 0.5
    return tuple((dx, dy) for dy in rng for dx in rng
                 if (dx + half - c) ** 2 + (dy + half - c) ** 2 <= lim)


def pixel_perfect(pts):
    """Quita los píxeles en 'L' de un trazo (modo pixel-perfect de Aseprite)."""
    if len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        p0, p1, p2 = out[-1], pts[k], pts[k + 1]
        diag = abs(p2[0] - p0[0]) == 1 and abs(p2[1] - p0[1]) == 1
        ortho = (abs(p1[0] - p0[0]) + abs(p1[1] - p0[1]) == 1 and
                 abs(p2[0] - p1[0]) + abs(p2[1] - p1[1]) == 1)
        if diag and ortho:
            continue
        out.append(p1)
    out.append(pts[-1])
    return out


class Layer:
    __slots__ = ("name", "visible", "locked", "opacity", "frames")

    def __init__(self, name, nframes, size_bytes):
        self.name = name
        self.visible = True
        self.locked = False
        self.opacity = 255
        self.frames = [bytearray(size_bytes) for _ in range(nframes)]


# ── Lienzo ───────────────────────────────────────────────────────────────────
class PixelCanvas(Gtk.DrawingArea):
    def __init__(self, cw: int = 64, ch: int = 64):
        super().__init__()
        self.cw, self.ch = cw, ch
        self.layers = [Layer("Capa 1", 1, cw * ch * 4)]
        self._layer = 0
        self._cur = 0
        self._zi = 5

        # opciones de herramienta
        self.tool = "pencil"
        self.color = (0, 0, 0, 255)
        self.color2 = (255, 255, 255, 255)
        self.brush = 1
        self.brush_shape = "square"
        self.ink = "simple"
        self.opacity = 255
        self.pixel_perfect = False
        self.shape_fill = False
        self.tol = 0
        self.contiguous = True
        self.conn8 = False
        self.grad_kind = "linear"
        self.grad_dither = False
        self.symmetry = "none"
        self.tiled = "none"
        self.show_grid = False
        self.grid_size = 0
        self.onion_prev = False
        self.onion_next = False

        # selección
        self.sel = None                 # np.ndarray bool (ch, cw) | None
        self._sel_path = None
        self._ants = 0.0
        self._clip = None

        # vista
        self._ox, self._oy = 0.0, 0.0
        self._auto_fit = True
        self._mouse = (0.0, 0.0)
        self._cursor_px = (-1, -1)
        self._space = False
        self._panning = False
        self._pan_origin = (0.0, 0.0)

        # caches de render
        self._surf_cache = {}
        self._dirty = set()
        self._checker = None

        # undo
        self._undo, self._redo = [], []

        # gesto en curso
        self._drawing = False
        self._tool_now = "pencil"
        self._btn = 1
        self._drag_start = (0, 0)
        self._last_px = None
        self._prev_end = None
        self._stroke_pts = []
        self._stroke_base = None
        self._stroke_done = set()
        self._shape_start = None
        self._shape_base = None
        self._shape_pts = []
        self._sc = self.color
        self._sc2 = self.color2
        self._mode = "replace"
        self._sel_base = None
        self._lasso = []
        self._mv = None

        # callbacks hacia la ventana
        self.on_pick = None
        self.on_frame_changed = None
        self.on_layers_changed = None
        self.on_cursor_moved = None
        self.on_zoom_changed = None
        self.on_status = None
        self.on_tool_request = None

        self.set_draw_func(self._draw)
        self.set_focusable(True)
        self.set_hexpand(True); self.set_vexpand(True)
        self.set_size_request(240, 200)
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self._set_cursor()

        d1 = Gtk.GestureDrag(); d1.set_button(0)
        d1.connect("drag-begin", self._drag_begin)
        d1.connect("drag-update", self._drag_update)
        d1.connect("drag-end", self._drag_end)
        self.add_controller(d1)
        self._g1 = d1

        d2 = Gtk.GestureDrag(); d2.set_button(2)
        d2.connect("drag-begin", lambda g, x, y: self._pan_begin(x, y))
        d2.connect("drag-update", lambda g, dx, dy: self._pan_update(dx, dy))
        d2.connect("drag-end", lambda g, dx, dy: self._pan_end())
        self.add_controller(d2)

        mo = Gtk.EventControllerMotion()
        mo.connect("motion", self._on_motion)
        mo.connect("leave", self._on_leave)
        self.add_controller(mo)

        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        sc.connect("scroll", self._on_scroll)
        self.add_controller(sc)

        self._ants_id = None
        self.connect("map", self._start_ants)
        self.connect("unmap", self._stop_ants)

    # ── propiedades ──────────────────────────────────────────────────────────
    @property
    def zoom(self): return ZOOM_STEPS[self._zi]

    @property
    def frame_count(self): return len(self.layers[0].frames)

    @property
    def layer(self): return self.layers[self._layer]

    def cel(self, li=None, fi=None):
        return self.layers[self._layer if li is None else li].frames[
            self._cur if fi is None else fi]

    def _status(self, msg):
        if self.on_status: self.on_status(msg)

    def _notify(self, layers=False):
        if self.on_frame_changed: self.on_frame_changed()
        if layers and self.on_layers_changed: self.on_layers_changed()

    def _set_cursor(self):
        t = self._tool_now if self._drawing else self.tool
        name = {"hand": "grab", "zoom": "zoom-in", "move": "move"}.get(t, "crosshair")
        if self._panning: name = "grabbing"
        elif self._space: name = "grab"
        self.set_cursor(Gdk.Cursor.new_from_name(name))

    def set_tool(self, tool):
        self.tool = tool
        self._set_cursor()
        self.queue_draw()

    # ── buffers y caché ──────────────────────────────────────────────────────
    def _mark_dirty(self, li=None, fi=None):
        self._dirty.add((self._layer if li is None else li,
                         self._cur if fi is None else fi))

    def _get_surf(self, li, fi):
        key = (li, fi)
        if key in self._dirty or key not in self._surf_cache:
            self._surf_cache[key] = premultiply_bgra(
                bytes(self.layers[li].frames[fi]), self.cw, self.ch)
            self._dirty.discard(key)
        return cairo.ImageSurface.create_for_data(
            self._surf_cache[key], cairo.Format.ARGB32, self.cw, self.ch, self.cw * 4)

    def _reset_caches(self):
        self._surf_cache.clear(); self._dirty.clear()

    def _arr(self, li=None, fi=None):
        return np.frombuffer(self.cel(li, fi), dtype=np.uint8).reshape(self.ch, self.cw, 4)

    def _set_arr(self, arr, li=None, fi=None):
        li = self._layer if li is None else li
        fi = self._cur if fi is None else fi
        self.layers[li].frames[fi][:] = np.ascontiguousarray(arr, dtype=np.uint8).tobytes()
        self._dirty.add((li, fi))

    # ── vista: zoom / pan ────────────────────────────────────────────────────
    def _set_zoom(self, zi, ax=None, ay=None):
        zi = max(0, min(zi, len(ZOOM_STEPS) - 1))
        if zi == self._zi: return
        if ax is None: ax, ay = self.get_width() / 2, self.get_height() / 2
        old = self.zoom
        ix, iy = (ax - self._ox) / old, (ay - self._oy) / old
        self._zi = zi
        self._ox, self._oy = ax - ix * self.zoom, ay - iy * self.zoom
        self._auto_fit = False
        self.queue_draw()
        if self.on_zoom_changed: self.on_zoom_changed()

    def zoom_in(self, ax=None, ay=None):  self._set_zoom(self._zi + 1, ax, ay)
    def zoom_out(self, ax=None, ay=None): self._set_zoom(self._zi - 1, ax, ay)

    def zoom_to(self, z):
        best = min(range(len(ZOOM_STEPS)), key=lambda k: abs(ZOOM_STEPS[k] - z))
        self._set_zoom(best)

    def zoom_fit(self, margin=36):
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0:
            self._auto_fit = True; self.queue_draw(); return
        best = 0
        for k, z in enumerate(ZOOM_STEPS):
            if z * self.cw <= w - margin and z * self.ch <= h - margin: best = k
        self._zi = best
        self._ox = (w - self.cw * self.zoom) / 2
        self._oy = (h - self.ch * self.zoom) / 2
        self._auto_fit = False
        self.queue_draw()
        if self.on_zoom_changed: self.on_zoom_changed()

    def request_fit(self):
        self._auto_fit = True; self.queue_draw()

    def set_space(self, on):
        if on == self._space: return
        self._space = on
        self._set_cursor()

    def _pan_begin(self, sx, sy):
        self._panning = True
        self._pan_origin = (self._ox, self._oy)
        self._set_cursor()

    def _pan_update(self, dx, dy):
        if not self._panning: return
        self._ox = self._pan_origin[0] + dx
        self._oy = self._pan_origin[1] + dy
        self._auto_fit = False
        self.queue_draw()

    def _pan_end(self):
        self._panning = False
        self._set_cursor()

    def _s2c(self, sx, sy):
        z = self.zoom
        return int((sx - self._ox) // z), int((sy - self._oy) // z)

    # ── undo / redo ──────────────────────────────────────────────────────────
    def _state(self):
        return ("full", self.cw, self.ch,
                [(l.name, l.visible, l.locked, l.opacity, [bytes(f) for f in l.frames])
                 for l in self.layers], self._layer, self._cur)

    def _apply_state(self, st):
        _, w, h, layers, li, fi = st
        size_changed = (w, h) != (self.cw, self.ch)
        self.cw, self.ch = w, h
        self.layers = []
        for name, vis, lock, op, frames in layers:
            l = Layer(name, 0, 0)
            l.visible, l.locked, l.opacity = vis, lock, op
            l.frames = [bytearray(f) for f in frames]
            self.layers.append(l)
        self._layer = min(li, len(self.layers) - 1)
        self._cur = min(fi, self.frame_count - 1)
        self._reset_caches()
        self.sel = None; self._sel_path = None
        if size_changed: self._auto_fit = True

    def snap_undo(self):
        """Guarda el fotograma activo (cel) para deshacer un trazo."""
        self._undo.append(("cel", self._layer, self._cur, bytes(self.cel())))
        if len(self._undo) > MAX_UNDO: self._undo.pop(0)
        self._redo.clear()

    def snap_full(self):
        self._undo.append(self._state())
        if len(self._undo) > MAX_UNDO: self._undo.pop(0)
        self._redo.clear()

    def _swap(self, stack_from, stack_to):
        if not stack_from: return
        item = stack_from.pop()
        if item[0] == "cel":
            _, li, fi, data = item
            if li < len(self.layers) and fi < self.frame_count:
                stack_to.append(("cel", li, fi, bytes(self.layers[li].frames[fi])))
                self.layers[li].frames[fi][:] = data
                self._dirty.add((li, fi))
                self._layer, self._cur = li, fi
        else:
            stack_to.append(self._state())
            self._apply_state(item)
        self.queue_draw()
        self._notify(layers=True)

    def undo(self): self._swap(self._undo, self._redo)
    def redo(self): self._swap(self._redo, self._undo)

    # ── capas ────────────────────────────────────────────────────────────────
    def _new_layer_obj(self, name):
        return Layer(name, self.frame_count, self.cw * self.ch * 4)

    def add_layer(self):
        self.snap_full()
        n = len(self.layers) + 1
        self.layers.insert(self._layer + 1, self._new_layer_obj(f"Capa {n}"))
        self._layer += 1
        self._notify(layers=True); self.queue_draw()

    def duplicate_layer(self):
        self.snap_full()
        src = self.layer
        l = Layer(src.name + " copia", 0, 0)
        l.visible, l.locked, l.opacity = src.visible, False, src.opacity
        l.frames = [bytearray(f) for f in src.frames]
        self.layers.insert(self._layer + 1, l)
        self._layer += 1
        self._reset_caches()
        self._notify(layers=True); self.queue_draw()

    def delete_layer(self):
        if len(self.layers) <= 1:
            self._status("No se puede borrar la única capa"); return
        self.snap_full()
        self.layers.pop(self._layer)
        self._layer = min(self._layer, len(self.layers) - 1)
        self._reset_caches()
        self._notify(layers=True); self.queue_draw()

    def move_layer(self, delta):
        j = self._layer + delta
        if not (0 <= j < len(self.layers)): return
        self.snap_full()
        self.layers[self._layer], self.layers[j] = self.layers[j], self.layers[self._layer]
        self._layer = j
        self._reset_caches()
        self._notify(layers=True); self.queue_draw()

    def merge_down(self):
        if self._layer == 0:
            self._status("No hay capa debajo"); return
        self.snap_full()
        top, bot = self.layers[self._layer], self.layers[self._layer - 1]
        for fi in range(self.frame_count):
            base = Image.frombytes("RGBA", (self.cw, self.ch), bytes(bot.frames[fi]))
            base = self._with_opacity(base, bot.opacity)
            over = self._with_opacity(
                Image.frombytes("RGBA", (self.cw, self.ch), bytes(top.frames[fi])), top.opacity)
            bot.frames[fi][:] = Image.alpha_composite(base, over).tobytes()
        bot.opacity = 255
        self.layers.pop(self._layer)
        self._layer -= 1
        self._reset_caches()
        self._notify(layers=True); self.queue_draw()

    def set_active_layer(self, i):
        self._layer = max(0, min(i, len(self.layers) - 1))
        self._notify(layers=True); self.queue_draw()

    def toggle_visible(self, i):
        self.layers[i].visible = not self.layers[i].visible
        self._notify(layers=True); self.queue_draw()

    def toggle_lock(self, i):
        self.layers[i].locked = not self.layers[i].locked
        self._notify(layers=True)

    def set_layer_opacity(self, i, v):
        self.layers[i].opacity = max(0, min(255, int(v)))
        self.queue_draw()

    def rename_layer(self, i, name):
        self.layers[i].name = name or self.layers[i].name
        self._notify(layers=True)

    @staticmethod
    def _with_opacity(im, opacity):
        if opacity >= 255: return im
        r, g, b, a = im.split()
        return Image.merge("RGBA", (r, g, b, a.point(lambda v: v * opacity // 255)))

    # ── fotogramas ───────────────────────────────────────────────────────────
    def go_to(self, idx):
        self._cur = max(0, min(idx, self.frame_count - 1))
        self.queue_draw(); self._notify()

    def _insert_frame(self, at, make):
        for l in self.layers:
            l.frames.insert(at, make(l))
        self._cur = at
        self._reset_caches()
        self.queue_draw(); self._notify(layers=True)

    def new_frame(self):
        """Nuevo fotograma vacío (todas las capas)."""
        if self.frame_count >= MAX_FRAMES: return
        self.snap_full()
        n = self.cw * self.ch * 4
        self._insert_frame(self._cur + 1, lambda l: bytearray(n))

    def duplicate_frame(self):
        if self.frame_count >= MAX_FRAMES: return
        self.snap_full()
        cur = self._cur
        self._insert_frame(cur + 1, lambda l: bytearray(l.frames[cur]))

    def delete_frame(self):
        if self.frame_count <= 1:
            self._status("No se puede borrar el único fotograma"); return
        self.snap_full()
        for l in self.layers: l.frames.pop(self._cur)
        self._cur = min(self._cur, self.frame_count - 1)
        self._reset_caches()
        self.queue_draw(); self._notify(layers=True)

    def move_frame(self, delta):
        j = self._cur + delta
        if not (0 <= j < self.frame_count): return
        self.snap_full()
        for l in self.layers:
            l.frames[self._cur], l.frames[j] = l.frames[j], l.frames[self._cur]
        self._cur = j
        self._reset_caches()
        self.queue_draw(); self._notify(layers=True)

    def copy_frame(self):
        self._frame_clip = [bytes(l.frames[self._cur]) for l in self.layers]

    def paste_frame(self):
        clip = getattr(self, "_frame_clip", None)
        if not clip or len(clip) != len(self.layers): return
        self.snap_full()
        cur = self._cur
        self._insert_frame(cur + 1, lambda l: bytearray(clip[self.layers.index(l)]))

    # ── compositing / export ─────────────────────────────────────────────────
    def flatten(self, fi):
        out = Image.new("RGBA", (self.cw, self.ch), (0, 0, 0, 0))
        for l in self.layers:
            if not l.visible: continue
            im = Image.frombytes("RGBA", (self.cw, self.ch), bytes(l.frames[fi]))
            out = Image.alpha_composite(out, self._with_opacity(im, l.opacity))
        return out

    def to_pil(self, fi): return self.flatten(fi)

    def thumbnail(self, fi=None, size=THUMB):
        from gi.repository import GLib as _GL
        fi = self._cur if fi is None else fi
        im = self.flatten(fi)
        s = min(size / self.cw, size / self.ch)
        w, h = max(1, int(self.cw * s)), max(1, int(self.ch * s))
        im = im.resize((w, h), Image.NEAREST)
        raw = _GL.Bytes.new(im.tobytes())
        return Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.R8G8B8A8, raw, w * 4)

    # ── carga / tamaño ───────────────────────────────────────────────────────
    def reset(self, w, h):
        self.cw, self.ch = w, h
        self.layers = [Layer("Capa 1", 1, w * h * 4)]
        self._layer = 0; self._cur = 0
        self._undo.clear(); self._redo.clear()
        self.sel = None; self._sel_path = None
        self._reset_caches()
        self._auto_fit = True
        self.queue_draw(); self._notify(layers=True)

    def load_from_dir(self, frames_dir, max_dim=128):
        files = sorted(frames_dir.glob("frame_*.png"))[:MAX_FRAMES]
        if not files: return False
        first = Image.open(files[0]).convert("RGBA")
        w, h = first.size
        if max(w, h) > max_dim:
            r = max_dim / max(w, h)
            w, h = max(1, int(w * r)), max(1, int(h * r))
        self.cw, self.ch = w, h
        lay = Layer("Capa 1", 0, 0)
        for fp in files:
            im = Image.open(fp).convert("RGBA")
            if im.size != (w, h): im = im.resize((w, h), Image.NEAREST)
            lay.frames.append(bytearray(im.tobytes()))
        self.layers = [lay]; self._layer = 0; self._cur = 0
        self._undo.clear(); self._redo.clear()
        self.sel = None; self._sel_path = None
        self._reset_caches(); self._auto_fit = True
        self.queue_draw(); self._notify(layers=True)
        return True

    def import_image(self, path, pixelate=True):
        resample = Image.NEAREST if pixelate else Image.LANCZOS
        im = Image.open(path).convert("RGBA").resize((self.cw, self.ch), resample)
        self.snap_undo()
        self.cel()[:] = im.tobytes()
        self._mark_dirty(); self.queue_draw()

    def _map_all(self, fn, new_size=None):
        """Aplica fn(arr)->arr a todos los cels (para transformaciones del sprite)."""
        self.snap_full()
        for l in self.layers:
            for k, f in enumerate(l.frames):
                arr = np.frombuffer(bytes(f), dtype=np.uint8).reshape(self.ch, self.cw, 4)
                l.frames[k] = bytearray(np.ascontiguousarray(fn(arr)).tobytes())
        if new_size: self.cw, self.ch = new_size
        self.sel = None; self._sel_path = None
        self._reset_caches(); self._auto_fit = True
        self.queue_draw(); self._notify(layers=True)

    def flip_sprite(self, horizontal):
        self._map_all(lambda a: a[:, ::-1] if horizontal else a[::-1])

    def rotate_sprite(self, deg):
        if deg == 180:
            self._map_all(lambda a: a[::-1, ::-1])
        elif deg == 90:
            self._map_all(lambda a: np.rot90(a, -1), (self.ch, self.cw))
        elif deg == -90:
            self._map_all(lambda a: np.rot90(a, 1), (self.ch, self.cw))

    def resize_sprite(self, w, h):
        w, h = max(1, min(512, w)), max(1, min(512, h))
        self._map_all(lambda a: np.asarray(
            Image.fromarray(np.array(a), "RGBA").resize((w, h), Image.NEAREST)), (w, h))

    def canvas_size(self, w, h, anchor="center"):
        """Cambia el tamaño del lienzo conservando el dibujo (sin escalar)."""
        w, h = max(1, min(512, w)), max(1, min(512, h))
        ow, oh = self.cw, self.ch
        if anchor == "center": ox, oy = (w - ow) // 2, (h - oh) // 2
        else:                  ox, oy = 0, 0

        def fn(a):
            out = np.zeros((h, w, 4), dtype=np.uint8)
            sx0, sy0 = max(0, -ox), max(0, -oy)
            dx0, dy0 = max(0, ox), max(0, oy)
            cw_, ch_ = min(ow - sx0, w - dx0), min(oh - sy0, h - dy0)
            if cw_ > 0 and ch_ > 0:
                out[dy0:dy0 + ch_, dx0:dx0 + cw_] = a[sy0:sy0 + ch_, sx0:sx0 + cw_]
            return out
        self._map_all(fn, (w, h))

    def crop_to_selection(self):
        bb = self._sel_bbox()
        if not bb:
            self._status("Selecciona una zona para recortar"); return
        x1, y1, x2, y2 = bb
        self._map_all(lambda a: a[y1:y2 + 1, x1:x2 + 1], (x2 - x1 + 1, y2 - y1 + 1))

    # ── selección ────────────────────────────────────────────────────────────
    def _sel_bbox(self):
        if self.sel is None or not self.sel.any(): return None
        ys, xs = np.nonzero(self.sel)
        return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

    def set_selection(self, mask):
        self.sel = mask if (mask is not None and mask.any()) else None
        self._sel_path = None
        self.queue_draw()

    def select_all(self):
        self.set_selection(np.ones((self.ch, self.cw), dtype=bool))

    def deselect(self): self.set_selection(None)

    def invert_selection(self):
        if self.sel is None: self.select_all()
        else: self.set_selection(~self.sel)

    def _combine(self, base, new):
        if self._mode == "add" and base is not None: return base | new
        if self._mode == "sub" and base is not None: return base & ~new
        return new

    def _sel_segments(self):
        if self._sel_path is not None: return self._sel_path
        segs = []
        if self.sel is not None:
            pad = np.pad(self.sel, 1)
            hz = pad[1:, 1:-1] != pad[:-1, 1:-1]     # (ch+1, cw)
            vt = pad[1:-1, 1:] != pad[1:-1, :-1]     # (ch, cw+1)
            for y in range(hz.shape[0]):
                xs = np.flatnonzero(hz[y])
                if xs.size:
                    start = prev = xs[0]
                    for x in xs[1:]:
                        if x != prev + 1:
                            segs.append((start, y, prev + 1, y)); start = x
                        prev = x
                    segs.append((start, y, prev + 1, y))
            for x in range(vt.shape[1]):
                ys = np.flatnonzero(vt[:, x])
                if ys.size:
                    start = prev = ys[0]
                    for y in ys[1:]:
                        if y != prev + 1:
                            segs.append((x, start, x, prev + 1)); start = y
                        prev = y
                    segs.append((x, start, x, prev + 1))
        self._sel_path = segs
        return segs

    def clear_selection_pixels(self):
        if self._locked(): return
        self.snap_undo()
        arr = self._arr().copy()
        if self.sel is None: arr[:] = 0
        else: arr[self.sel] = 0
        self._set_arr(arr); self.queue_draw(); self._notify()

    def copy_selection(self, cut=False):
        bb = self._sel_bbox()
        arr = self._arr()
        if bb is None:
            x1, y1, x2, y2 = 0, 0, self.cw - 1, self.ch - 1
            m = np.ones((self.ch, self.cw), dtype=bool)
        else:
            x1, y1, x2, y2 = bb; m = self.sel
        img = arr[y1:y2 + 1, x1:x2 + 1].copy()
        mm = m[y1:y2 + 1, x1:x2 + 1].copy()
        img[~mm] = 0
        self._clip = (img, mm, x1, y1)
        if cut: self.clear_selection_pixels()

    def paste_selection(self):
        if not self._clip: return
        if self._locked(): return
        img, mm, x1, y1 = self._clip
        h, w = mm.shape
        self.snap_undo()
        arr = self._arr().copy()
        y2, x2 = min(self.ch, y1 + h), min(self.cw, x1 + w)
        sub = img[:y2 - y1, :x2 - x1]; sm = mm[:y2 - y1, :x2 - x1]
        reg = arr[y1:y2, x1:x2]
        opaque = sm & (sub[..., 3] > 0)
        reg[opaque] = sub[opaque]
        self._set_arr(arr)
        m = np.zeros((self.ch, self.cw), dtype=bool)
        m[y1:y2, x1:x2] = sm
        self.set_selection(m)
        self.queue_draw(); self._notify()
        if self.on_tool_request: self.on_tool_request("move")

    def nudge(self, dx, dy):
        if self._locked(): return
        self.snap_undo()
        self._begin_move()
        self._move_by(dx, dy)
        self._mv = None
        self.queue_draw(); self._notify()

    # ── efectos sobre la selección / capa ────────────────────────────────────
    def flip_cel(self, horizontal):
        """Voltea la selección (si la hay) o toda la capa del fotograma actual."""
        if self._locked(): return
        self.snap_undo()
        arr = self._arr().copy()
        bb = self._sel_bbox()
        if bb is None:
            arr = arr[:, ::-1] if horizontal else arr[::-1]
        else:
            x1, y1, x2, y2 = bb
            m = self.sel[y1:y2 + 1, x1:x2 + 1]
            reg = arr[y1:y2 + 1, x1:x2 + 1].copy()
            flipped = reg[:, ::-1] if horizontal else reg[::-1]
            fm = m[:, ::-1] if horizontal else m[::-1]
            out = arr.copy()
            out[y1:y2 + 1, x1:x2 + 1][m] = 0
            sub = out[y1:y2 + 1, x1:x2 + 1]
            sub[fm] = flipped[fm]
            arr = out
            nm = np.zeros_like(self.sel); nm[y1:y2 + 1, x1:x2 + 1] = fm
            self.set_selection(nm)
        self._set_arr(arr); self.queue_draw(); self._notify()

    def outline_fx(self):
        """Dibuja un contorno de 1 px con el color principal alrededor de lo dibujado."""
        if self._locked(): return
        self.snap_undo()
        arr = self._arr().copy()
        solid = arr[..., 3] > 0
        pad = np.pad(solid, 1)
        grow = pad[:-2, 1:-1] | pad[2:, 1:-1] | pad[1:-1, :-2] | pad[1:-1, 2:]
        ring = grow & ~solid
        if self.sel is not None: ring &= self.sel
        arr[ring] = np.array(self.color, dtype=np.uint8)
        self._set_arr(arr); self.queue_draw(); self._notify()

    # ── mover (selección o cel completo) ─────────────────────────────────────
    def _begin_move(self):
        base = self._arr().copy()
        info = {"base": base, "sel": None, "img": None, "bb": None}
        if self.sel is not None and self.sel.any():
            x1, y1, x2, y2 = self._sel_bbox()
            m = self.sel[y1:y2 + 1, x1:x2 + 1].copy()
            img = base[y1:y2 + 1, x1:x2 + 1].copy()
            img[~m] = 0
            info.update(sel=self.sel.copy(), img=img, m=m, bb=(x1, y1, x2, y2))
        self._mv = info

    def _move_by(self, dx, dy):
        mv = self._mv
        base = mv["base"]
        new = np.zeros_like(base)
        if mv["bb"] is None:                        # cel completo
            sx0, sy0 = max(0, -dx), max(0, -dy)
            dx0, dy0 = max(0, dx), max(0, dy)
            w_, h_ = self.cw - abs(dx), self.ch - abs(dy)
            if w_ > 0 and h_ > 0:
                new[dy0:dy0 + h_, dx0:dx0 + w_] = base[sy0:sy0 + h_, sx0:sx0 + w_]
        else:
            new = base.copy()
            new[mv["sel"]] = 0
            x1, y1, x2, y2 = mv["bb"]
            img, m = mv["img"], mv["m"]
            h, w = m.shape
            tx1, ty1 = x1 + dx, y1 + dy
            cx1, cy1 = max(0, tx1), max(0, ty1)
            cx2, cy2 = min(self.cw, tx1 + w), min(self.ch, ty1 + h)
            if cx2 > cx1 and cy2 > cy1:
                sub = img[cy1 - ty1:cy2 - ty1, cx1 - tx1:cx2 - tx1]
                sm = m[cy1 - ty1:cy2 - ty1, cx1 - tx1:cx2 - tx1]
                reg = new[cy1:cy2, cx1:cx2]
                put = sm & (sub[..., 3] > 0)
                reg[put] = sub[put]
            nm = np.zeros((self.ch, self.cw), dtype=bool)
            if cx2 > cx1 and cy2 > cy1:
                nm[cy1:cy2, cx1:cx2] = m[cy1 - ty1:cy2 - ty1, cx1 - tx1:cx2 - tx1]
            self.sel = nm if nm.any() else None
            self._sel_path = None
        self._set_arr(new)

    # ── escritura de píxeles (tintas, simetría, mosaico) ─────────────────────
    def _locked(self):
        l = self.layer
        if l.locked:
            self._status("La capa está bloqueada"); return True
        if not l.visible:
            self._status("La capa está oculta"); return True
        return False

    def _sym(self, pts):
        s = self.symmetry
        if s == "none": return pts
        out = list(pts)
        cw1, ch1 = self.cw - 1, self.ch - 1
        if s in ("h", "hv"): out += [(cw1 - x, y) for x, y in pts]
        if s in ("v", "hv"): out += [(x, ch1 - y) for x, y in pts]
        if s == "hv":        out += [(cw1 - x, ch1 - y) for x, y in pts]
        return out

    def _stamp(self, x, y, size=None, shape=None):
        offs = brush_offsets(self.brush if size is None else size,
                             self.brush_shape if shape is None else shape)
        return [(x + dx, y + dy) for dx, dy in offs]

    def _ink_pixel(self, ink, dst, c, op, x, y, erase):
        if erase:
            a = 0 if op >= 255 else dst[3] * (255 - op) // 255
            return (0, 0, 0, 0) if a == 0 else (dst[0], dst[1], dst[2], a)
        if ink == "dither":
            c = c if (x + y) % 2 == 0 else self._sc2
            ink = "simple"
        sa = c[3] * op // 255
        if ink == "simple" and op >= 255:
            return tuple(c)
        if ink == "lock_alpha":
            if dst[3] == 0: return dst
            k = sa
            return ((c[0] * k + dst[0] * (255 - k)) // 255,
                    (c[1] * k + dst[1] * (255 - k)) // 255,
                    (c[2] * k + dst[2] * (255 - k)) // 255, dst[3])
        if sa <= 0: return dst
        if dst[3] == 0: return (c[0], c[1], c[2], sa)
        oa = sa + dst[3] * (255 - sa) // 255
        k = dst[3] * (255 - sa) // 255
        return ((c[0] * sa + dst[0] * k) // oa, (c[1] * sa + dst[1] * k) // oa,
                (c[2] * sa + dst[2] * k) // oa, oa)

    def _paint_points(self, pts, color, erase=False, done=None):
        li, fi = self._layer, self._cur
        cel = self.layers[li].frames[fi]
        cw, ch = self.cw, self.ch
        tx, ty = self.tiled in ("x", "xy"), self.tiled in ("y", "xy")
        sel, ink, op = self.sel, self.ink, self.opacity
        buf = self._surf_cache.get((li, fi))
        clean = buf is not None and (li, fi) not in self._dirty
        touched = False
        for x, y in pts:
            if tx: x %= cw
            elif not 0 <= x < cw: continue
            if ty: y %= ch
            elif not 0 <= y < ch: continue
            if sel is not None and not sel[y, x]: continue
            if done is not None:
                if (x, y) in done: continue
                done.add((x, y))
            i = (y * cw + x) * 4
            dst = (cel[i], cel[i + 1], cel[i + 2], cel[i + 3])
            new = self._ink_pixel(ink, dst, color, op, x, y, erase)
            if new == dst: continue
            cel[i:i + 4] = bytes(new)
            touched = True
            if clean:
                a = new[3]
                buf[i] = new[2] * a // 255; buf[i + 1] = new[1] * a // 255
                buf[i + 2] = new[0] * a // 255; buf[i + 3] = a
            else:
                self._dirty.add((li, fi))
        return touched

    def _paint_stamps(self, centers, color, erase=False, done=None):
        pts = []
        for x, y in centers:
            pts.extend(self._stamp(x, y))
        self._paint_points(self._sym(pts), color, erase, done)

    # ── formas ───────────────────────────────────────────────────────────────
    def _shape_points(self, tool, x0, y0, x1, y1):
        """Devuelve la lista de píxeles (sin pincel) de la forma."""
        if tool == "line":
            return _interp(x0, y0, x1, y1), True
        xa, xb = min(x0, x1), max(x0, x1)
        ya, yb = min(y0, y1), max(y0, y1)
        if tool == "rect":
            if self.shape_fill:
                return [(x, y) for y in range(ya, yb + 1) for x in range(xa, xb + 1)], False
            pts = []
            for x in range(xa, xb + 1): pts += [(x, ya), (x, yb)]
            for y in range(ya + 1, yb): pts += [(xa, y), (xb, y)]
            return pts, True
        if tool == "ellipse":
            w, h = xb - xa + 1, yb - ya + 1
            im = Image.new("L", (w, h), 0)
            d = ImageDraw.Draw(im)
            if self.shape_fill:
                d.ellipse([0, 0, w - 1, h - 1], fill=255)
            else:
                d.ellipse([0, 0, w - 1, h - 1], outline=255, width=1)
            ys, xs = np.nonzero(np.asarray(im))
            return [(int(x) + xa, int(y) + ya) for x, y in zip(xs, ys)], True
        return [], False

    def _draw_shape(self, x1, y1, constrain):
        x0, y0 = self._shape_start
        tool = self._tool_now
        if constrain:
            x1, y1 = self._constrain(x0, y0, x1, y1, tool)
        cel = self.cel()
        cel[:] = self._shape_base
        self._dirty.add((self._layer, self._cur))
        if tool == "gradient":
            self._gradient(x0, y0, x1, y1); return
        if tool == "contour":
            self._contour_paint(); return
        pts, stamped = self._shape_points(tool, x0, y0, x1, y1)
        if stamped:
            self._paint_stamps(pts, self._sc, done=set() if self.opacity < 255 else None)
        else:
            self._paint_points(self._sym(pts), self._sc, done=set())

    @staticmethod
    def _constrain(x0, y0, x1, y1, tool):
        dx, dy = x1 - x0, y1 - y0
        if tool == "line":
            ax, ay = abs(dx), abs(dy)
            if ax > 2 * ay: return x1, y0
            if ay > 2 * ax: return x0, y1
        m = max(abs(dx), abs(dy))
        return x0 + (m if dx >= 0 else -m), y0 + (m if dy >= 0 else -m)

    def _contour_paint(self):
        pts = self._shape_pts
        if not pts: return
        if self.shape_fill and len(pts) >= 3:
            im = Image.new("L", (self.cw, self.ch), 0)
            ImageDraw.Draw(im).polygon(pts, fill=255)
            ys, xs = np.nonzero(np.asarray(im))
            self._paint_points(self._sym([(int(x), int(y)) for x, y in zip(xs, ys)]),
                               self._sc, done=set())
        path = []
        for a, b in zip(pts, pts[1:]): path += _interp(a[0], a[1], b[0], b[1])
        if not self.shape_fill and len(pts) == 1: path = list(pts)
        self._paint_stamps(path, self._sc, done=set())

    def _gradient(self, x0, y0, x1, y1):
        ys, xs = np.mgrid[0:self.ch, 0:self.cw].astype(np.float32)
        if self.grad_kind == "radial":
            r = max(1.0, math.hypot(x1 - x0, y1 - y0))
            t = np.clip(np.hypot(xs - x0, ys - y0) / r, 0, 1)
        else:
            vx, vy = x1 - x0, y1 - y0
            n = vx * vx + vy * vy
            t = np.clip(((xs - x0) * vx + (ys - y0) * vy) / n, 0, 1) if n else np.zeros_like(xs)
        c1 = np.array(self._sc, dtype=np.float32)
        c2 = np.array(self._sc2, dtype=np.float32)
        if self.grad_dither:
            th = BAYER4[(ys.astype(int) % 4), (xs.astype(int) % 4)]
            out = np.where((t > th)[..., None], c2, c1)
        else:
            out = c1 + (c2 - c1) * t[..., None]
        out = out.astype(np.uint8)
        arr = self._arr().copy()
        mask = self.sel if self.sel is not None else np.ones((self.ch, self.cw), dtype=bool)
        op = self.opacity / 255.0
        if op >= 1:
            arr[mask] = out[mask]
        else:
            blend = (arr.astype(np.float32) * (1 - op) + out.astype(np.float32) * op)
            arr[mask] = blend[mask].astype(np.uint8)
        self._set_arr(arr)

    # ── bote / varita ────────────────────────────────────────────────────────
    def _region(self, x, y, tol, contiguous, conn8):
        arr = self._arr()
        if not (0 <= x < self.cw and 0 <= y < self.ch): return None
        target = arr[y, x].astype(np.int16)
        match = (np.abs(arr.astype(np.int16) - target).max(axis=2) <= tol)
        if not contiguous:
            return match
        vis = np.zeros((self.ch, self.cw), dtype=bool)
        stack = [(x, y)]
        nb = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if conn8: nb += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        while stack:
            px, py = stack.pop()
            if vis[py, px] or not match[py, px]: continue
            vis[py, px] = True
            for dx, dy in nb:
                qx, qy = px + dx, py + dy
                if 0 <= qx < self.cw and 0 <= qy < self.ch and not vis[qy, qx] and match[qy, qx]:
                    stack.append((qx, qy))
        return vis

    def _bucket(self, x, y):
        region = self._region(x, y, self.tol, self.contiguous, self.conn8)
        if region is None: return
        if self.sel is not None: region = region & self.sel
        ys, xs = np.nonzero(region)
        pts = [(int(a), int(b)) for a, b in zip(xs, ys)]
        c = self._sc
        saved = self.tiled; self.tiled = "none"
        self._paint_points(pts, c)
        self.tiled = saved

    def _wand(self, x, y, base):
        region = self._region(x, y, self.tol, self.contiguous, self.conn8)
        if region is None: return
        self.set_selection(self._combine(base, region))

    # ── entrada de ratón ─────────────────────────────────────────────────────
    def _drag_begin(self, g, sx, sy):
        btn = g.get_current_button()
        mods = g.get_current_event_state()
        self.grab_focus()
        alt = bool(mods & Gdk.ModifierType.ALT_MASK)
        shift = bool(mods & Gdk.ModifierType.SHIFT_MASK)
        if btn == 2 or self._space or self.tool == "hand":
            self._pan_begin(sx, sy); self._pan_hand = True; return
        self._pan_hand = False
        self._btn = btn
        self._drawing = True
        self._drag_start = (sx, sy)
        cx, cy = self._s2c(sx, sy)
        tool = "pick" if (alt and self.tool not in ("marquee", "lasso", "wand")) else self.tool
        self._tool_now = tool
        self._sc, self._sc2 = ((self.color2, self.color) if btn == 3
                               else (self.color, self.color2))
        self._mode = ("add" if shift else "sub" if alt else "replace")
        if tool in ("marquee", "lasso", "wand"):
            self._sel_base = self.sel.copy() if self.sel is not None else None

        if tool == "zoom":
            if btn == 3 or alt: self.zoom_out(sx, sy)
            else:               self.zoom_in(sx, sy)
            self._drawing = False; return

        if tool == "pick":
            self._pick(cx, cy, btn); self._drawing = False; return

        if tool == "marquee":
            self._drag_c0 = (cx, cy)
            if self._mode == "replace": self.set_selection(None)
            return
        if tool == "lasso":
            self._lasso = [(cx, cy)]
            if self._mode == "replace": self.set_selection(None)
            return
        if tool == "wand":
            self._wand(cx, cy, self._sel_base)
            self._drawing = False; return

        if tool == "move":
            if self._locked(): self._drawing = False; return
            self.snap_undo(); self._begin_move(); self._mv_start = (cx, cy); return

        if self._locked():
            self._drawing = False; return

        if tool == "fill":
            self.snap_undo(); self._bucket(cx, cy)
            self._drawing = False; self.queue_draw(); self._notify(); return

        if tool in SHAPE_TOOLS:
            self.snap_undo()
            self._shape_start = (cx, cy)
            self._shape_base = bytes(self.cel())
            self._shape_pts = [(cx, cy)]
            self._draw_shape(cx, cy, shift and tool != "contour")
            self.queue_draw(); return

        # lápiz / borrador
        self.snap_undo()
        self._stroke_base = bytes(self.cel())
        self._stroke_done = set() if (self.opacity < 255 or self.ink == "alpha") else None
        erase = tool == "eraser"
        if shift and self._prev_end is not None:
            pts = _interp(self._prev_end[0], self._prev_end[1], cx, cy)
        else:
            pts = [(cx, cy)]
        self._stroke_pts = list(pts)
        self._paint_stamps(pts, self._sc, erase, self._stroke_done)
        self._last_px = (cx, cy)
        self.queue_draw()

    def _drag_update(self, g, dx, dy):
        if self._panning:
            self._pan_update(dx, dy); return
        if not self._drawing: return
        cx, cy = self._s2c(self._drag_start[0] + dx, self._drag_start[1] + dy)
        tool = self._tool_now
        mods = g.get_current_event_state()
        shift = bool(mods & Gdk.ModifierType.SHIFT_MASK)

        if tool == "marquee":
            x0, y0 = self._drag_c0
            m = np.zeros((self.ch, self.cw), dtype=bool)
            xa, xb = max(0, min(x0, cx)), min(self.cw - 1, max(x0, cx))
            ya, yb = max(0, min(y0, cy)), min(self.ch - 1, max(y0, cy))
            if xb >= xa and yb >= ya: m[ya:yb + 1, xa:xb + 1] = True
            self.set_selection(self._combine(self._sel_base, m)); return
        if tool == "lasso":
            if (cx, cy) != self._lasso[-1]: self._lasso.append((cx, cy))
            self._lasso_mask(); return
        if tool == "move" and self._mv is not None:
            sx, sy = self._mv_start
            self._move_by(cx - sx, cy - sy); self.queue_draw(); return

        if tool in SHAPE_TOOLS and self._shape_start is not None:
            if tool == "contour" and (cx, cy) != self._shape_pts[-1]:
                self._shape_pts.append((cx, cy))
            self._draw_shape(cx, cy, shift and tool != "contour")
            self.queue_draw(); return

        if tool in STROKE_TOOLS and self._last_px is not None:
            if (cx, cy) == self._last_px: return
            new = _interp(self._last_px[0], self._last_px[1], cx, cy)[1:]
            self._stroke_pts += new
            erase = tool == "eraser"
            if self.pixel_perfect:
                self.cel()[:] = self._stroke_base
                self._dirty.add((self._layer, self._cur))
                done = set() if self._stroke_done is not None else None
                self._paint_stamps(pixel_perfect(self._stroke_pts), self._sc, erase, done)
                self._stroke_done = done
            else:
                self._paint_stamps(new, self._sc, erase, self._stroke_done)
            self._last_px = (cx, cy)
            self.queue_draw()

    def _lasso_mask(self):
        m = np.zeros((self.ch, self.cw), dtype=bool)
        if len(self._lasso) >= 3:
            im = Image.new("L", (self.cw, self.ch), 0)
            ImageDraw.Draw(im).polygon(self._lasso, fill=255, outline=255)
            m = np.asarray(im) > 0
        self.set_selection(self._combine(self._sel_base, m))

    def _drag_end(self, g, dx, dy):
        if self._panning:
            self._pan_end(); return
        if not self._drawing: return
        cx, cy = self._s2c(self._drag_start[0] + dx, self._drag_start[1] + dy)
        tool = self._tool_now
        try:
            if tool in STROKE_TOOLS:
                self._prev_end = (cx, cy)
                self._notify()
            elif tool in SHAPE_TOOLS:
                self._shape_start = None; self._shape_base = None
                self._notify()
            elif tool == "move":
                self._mv = None; self._notify()
            elif tool == "lasso":
                self._lasso_mask(); self._lasso = []
        finally:
            self._drawing = False
            self._set_cursor()
            self.queue_draw()

    def _pick(self, cx, cy, btn):
        if not (0 <= cx < self.cw and 0 <= cy < self.ch): return
        # muestrea la imagen visible (como Aseprite) salvo que solo haya una capa
        px = self.flatten(self._cur).getpixel((cx, cy))
        if self.on_pick: self.on_pick(tuple(px), btn == 3)

    def _on_motion(self, ctrl, sx, sy):
        self._mouse = (sx, sy)
        cx, cy = self._s2c(sx, sy)
        if (cx, cy) != self._cursor_px:
            self._cursor_px = (cx, cy)
            self.queue_draw()
            if self.on_cursor_moved:
                inside = 0 <= cx < self.cw and 0 <= cy < self.ch
                self.on_cursor_moved(cx, cy, self.cel()[(cy * self.cw + cx) * 4:(cy * self.cw + cx) * 4 + 4]
                                     if inside else None)

    def _on_leave(self, ctrl):
        if self._cursor_px != (-1, -1):
            self._cursor_px = (-1, -1)
            self.queue_draw()

    def _on_scroll(self, ctrl, dx, dy):
        mods = ctrl.get_current_event_state()
        touchpad = ctrl.get_unit() == Gdk.ScrollUnit.SURFACE
        if touchpad and not (mods & Gdk.ModifierType.CONTROL_MASK):
            self._ox -= dx; self._oy -= dy
            self._auto_fit = False; self.queue_draw(); return True
        if mods & Gdk.ModifierType.SHIFT_MASK:           # Shift+rueda: mover en horizontal
            self._ox -= dy * 30 if dy else dx * 30
            self._auto_fit = False; self.queue_draw(); return True
        mx, my = self._mouse
        if dy > 0:   self.zoom_out(mx, my)
        elif dy < 0: self.zoom_in(mx, my)
        return True

    # ── render ───────────────────────────────────────────────────────────────
    def _start_ants(self, *_):
        if self._ants_id is None:
            self._ants_id = GLib.timeout_add(140, self._tick_ants)

    def _stop_ants(self, *_):
        if self._ants_id is not None:
            GLib.source_remove(self._ants_id); self._ants_id = None

    def _tick_ants(self):
        if self.sel is not None:
            self._ants = (self._ants + 1) % 8
            self.queue_draw()
        return True

    def _checker_pattern(self):
        if self._checker is None:
            s = cairo.ImageSurface(cairo.FORMAT_RGB24, 16, 16)
            c = cairo.Context(s)
            c.set_source_rgb(0.80, 0.80, 0.80); c.paint()
            c.set_source_rgb(0.69, 0.69, 0.69)
            c.rectangle(0, 0, 8, 8); c.rectangle(8, 8, 8, 8); c.fill()
            self._checker = cairo.SurfacePattern(s)
            self._checker.set_extend(cairo.Extend.REPEAT)
            self._checker.set_filter(cairo.Filter.NEAREST)
        return self._checker

    def _paint_layers(self, cr, fi, alpha_mul=1.0):
        z = self.zoom
        for li, l in enumerate(self.layers):
            if not l.visible: continue
            surf = self._get_surf(li, fi)
            pat = cairo.SurfacePattern(surf)
            pat.set_filter(cairo.Filter.NEAREST)
            m = cairo.Matrix(); m.scale(1 / z, 1 / z); pat.set_matrix(m)
            cr.set_source(pat)
            cr.paint_with_alpha(alpha_mul * l.opacity / 255)

    def _draw(self, area, cr, width, height):
        if self._auto_fit and width > 8 and height > 8:
            self.zoom_fit()
        z = self.zoom
        iw, ih = self.cw * z, self.ch * z
        cr.set_source_rgb(*BG_VIEW); cr.paint()

        tx, ty = self.tiled in ("x", "xy"), self.tiled in ("y", "xy")
        nx0 = nx1 = ny0 = ny1 = 0
        if tx:
            nx0 = math.floor((0 - self._ox) / iw) - 0; nx1 = math.ceil((width - self._ox) / iw)
        if ty:
            ny0 = math.floor((0 - self._oy) / ih) - 0; ny1 = math.ceil((height - self._oy) / ih)
        tiles = [(i, j) for j in range(ny0, ny1 + 1) for i in range(nx0, nx1 + 1)] \
            if (tx or ty) else [(0, 0)]
        tiles = tiles[:400]

        for (i, j) in tiles:
            cr.save()
            cr.translate(self._ox + i * iw, self._oy + j * ih)
            main = (i == 0 and j == 0)
            cr.rectangle(0, 0, iw, ih); cr.clip()
            cr.set_source(self._checker_pattern()); cr.paint()
            if self.onion_prev and self._cur > 0:
                self._paint_layers(cr, self._cur - 1, ONION_ALPHA)
            if self.onion_next and self._cur < self.frame_count - 1:
                self._paint_layers(cr, self._cur + 1, ONION_ALPHA)
            self._paint_layers(cr, self._cur, 1.0 if main else 0.85)
            cr.restore()

        cr.save()
        cr.translate(self._ox, self._oy)
        # borde
        cr.set_source_rgba(0, 0, 0, 0.75); cr.set_line_width(1)
        cr.rectangle(-0.5, -0.5, iw + 1, ih + 1); cr.stroke()
        if self.show_grid and z >= 6:
            cr.save(); cr.rectangle(0, 0, iw, ih); cr.clip()
            cr.set_source_rgba(0, 0, 0, 0.22); cr.set_line_width(1)
            for x in range(1, self.cw): cr.move_to(x * z + .5, 0); cr.line_to(x * z + .5, ih)
            for y in range(1, self.ch): cr.move_to(0, y * z + .5); cr.line_to(iw, y * z + .5)
            cr.stroke(); cr.restore()
        if self.grid_size > 1:
            g = self.grid_size
            cr.save(); cr.rectangle(0, 0, iw, ih); cr.clip()
            cr.set_source_rgba(0.1, 0.3, 0.8, 0.5); cr.set_line_width(1)
            for x in range(g, self.cw, g): cr.move_to(x * z + .5, 0); cr.line_to(x * z + .5, ih)
            for y in range(g, self.ch, g): cr.move_to(0, y * z + .5); cr.line_to(iw, y * z + .5)
            cr.stroke(); cr.restore()
        self._draw_symmetry(cr, z)
        self._draw_selection(cr, z)
        self._draw_cursor(cr, z)
        cr.restore()

    def _draw_symmetry(self, cr, z):
        if self.symmetry == "none": return
        cr.set_source_rgba(0.2, 0.7, 1.0, 0.7)
        cr.set_line_width(1); cr.set_dash([5.0, 4.0])
        if self.symmetry in ("h", "hv"):
            x = self.cw / 2 * z; cr.move_to(x, 0); cr.line_to(x, self.ch * z); cr.stroke()
        if self.symmetry in ("v", "hv"):
            y = self.ch / 2 * z; cr.move_to(0, y); cr.line_to(self.cw * z, y); cr.stroke()
        cr.set_dash([])

    def _draw_selection(self, cr, z):
        if self.sel is None and not self._lasso: return
        segs = self._sel_segments() if self.sel is not None else []
        if not segs: return
        for color, off in (((0, 0, 0, 0.95), 0), ((1, 1, 1, 0.95), 4)):
            cr.set_source_rgba(*color)
            cr.set_line_width(1); cr.set_dash([4.0, 4.0], self._ants + off)
            for x1, y1, x2, y2 in segs:
                cr.move_to(x1 * z + (0.5 if x1 == x2 else 0), y1 * z + (0.5 if y1 == y2 else 0))
                cr.line_to(x2 * z + (0.5 if x1 == x2 else 0), y2 * z + (0.5 if y1 == y2 else 0))
            cr.stroke()
        cr.set_dash([])

    def _draw_cursor(self, cr, z):
        cx, cy = self._cursor_px
        if self._panning or self._space or self.tool in ("hand", "zoom", "move", "marquee",
                                                        "lasso", "wand", "pick"):
            return
        if not (-self.cw <= cx <= 2 * self.cw and -self.ch <= cy <= 2 * self.ch): return
        size = 1 if self.tool in ("fill", "gradient") else self.brush
        offs = brush_offsets(size, self.brush_shape)
        cr.new_path()
        if len(offs) > 500:
            half = size // 2
            cr.rectangle((cx - half) * z, (cy - half) * z, size * z, size * z)
        else:
            for dx, dy in offs:
                cr.rectangle((cx + dx) * z, (cy + dy) * z, z, z)
        cr.set_source_rgba(0, 0, 0, 0.75); cr.set_line_width(2); cr.stroke_preserve()
        cr.set_source_rgba(1, 1, 1, 0.9); cr.set_line_width(1); cr.stroke()
