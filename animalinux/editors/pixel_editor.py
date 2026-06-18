"""
Editor de píxeles — AnimaLinux  (v2 profesional, estilo Aseprite)
Lienzo pixel-art, paleta 48 colores, simetría H/V/HV, selección+mover,
outline, elipse, reemplazar color, dithering, varita mágica.

Atajos: B=lápiz  E=borrador  F=relleno  I=cuentagotas  O=outline
        C=elipse outline  V=elipse rellena  R=reemplazar  W=varita
        S=selección  M=mover  D=dithering  L=línea
        Z/Ctrl+Z=deshacer  Y/Ctrl+Y=rehacer
        +/−=zoom   [ ]=tamaño pincel   Ctrl+Scroll=zoom
"""
import math
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

import cairo
from PIL import Image

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False

from .icons import icon_image, icon_button  # noqa: E402

# ── constantes ───────────────────────────────────────────────────────────────
ZOOM_STEPS  = [1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 32]
MAX_UNDO    = 40
ONION_ALPHA = 0.30
THUMB       = 52
MAX_FRAMES  = 120

PALETTE = [
    # fila 1 — oscuros
    (0,   0,   0,   255), (30,  30,  30,  255), (70,  70,  70,  255),
    (120, 120, 120, 255), (180, 180, 180, 255), (255, 255, 255, 255),
    # fila 2 — rojos / naranjas / amarillos
    (180, 30,  30,  255), (220, 60,  40,  255), (230, 120, 40,  255),
    (240, 180, 40,  255), (220, 220, 50,  255), (160, 200, 50,  255),
    # fila 3 — verdes
    (60,  180, 60,  255), (30,  140, 80,  255), (20,  100, 70,  255),
    (40,  160, 140, 255), (50,  200, 180, 255), (80,  220, 210, 255),
    # fila 4 — azules / púrpuras
    (50,  100, 200, 255), (30,  60,  180, 255), (20,  20,  140, 255),
    (80,  40,  180, 255), (140, 60,  200, 255), (200, 80,  200, 255),
    # fila 5 — rosas / marrones / tierra
    (220, 120, 180, 255), (255, 160, 200, 255), (255, 200, 220, 255),
    (120, 70,  30,  255), (160, 100, 50,  255), (200, 150, 100, 255),
    # fila 6 — pasteles / especiales
    (255, 220, 180, 255), (220, 255, 200, 255), (200, 220, 255, 255),
    (255, 240, 150, 255), (150, 240, 255, 255), (240, 200, 255, 255),
    # fila 7 — colores oscuros saturados
    (80,  20,  20,  255), (20,  60,  20,  255), (20,  20,  80,  255),
    (60,  20,  80,  255), (80,  50,  10,  255), (10,  50,  60,  255),
    # fila 8 — índices especiales
    (255, 100, 100, 255), (100, 255, 100, 255), (100, 100, 255, 255),
    (255, 255, 100, 255), (100, 255, 255, 255), (255, 100, 255, 255),
    # transparente siempre al final
    (0,   0,   0,   0  ),
]


# ── helpers ──────────────────────────────────────────────────────────────────
from .editor_utils import premultiply_bgra as _to_cairo  # noqa: E402


def _interp(x0, y0, x1, y1):
    pts, dx, dy = [], abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x1 > x0 else -1
    sy = 1 if y1 > y0 else -1
    err = dx - dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1: break
        e2 = 2 * err
        if e2 > -dy: err -= dy; x0 += sx
        if e2 <  dx: err += dx; y0 += sy
    return pts


# ── PixelCanvas ───────────────────────────────────────────────────────────────
class PixelCanvas(Gtk.DrawingArea):
    def __init__(self, cw: int = 64, ch: int = 64):
        super().__init__()
        self.cw, self.ch = cw, ch
        self._zi   = 4
        self.tool   = "pencil"
        self.color  = (0, 0, 0, 255)
        self.color2 = (255, 255, 255, 255)
        self.brush  = 1
        self.onion  = False
        self.symmetry  = "none"
        self._wand_tol = 32

        self._frames: list[bytearray] = [bytearray(cw * ch * 4)]
        self._cur = 0
        self._clip_frame: bytearray | None = None

        self._surf_cache: dict[int, bytearray] = {}
        self._surf_dirty: set[int] = {0}

        self._undo: list[tuple] = []
        self._redo: list[tuple] = []

        self._drawing    = False
        self._drag_start = (0.0, 0.0)
        self._last_px    = (-1, -1)
        self._cursor_px  = (-1, -1)
        self._panning    = False
        self._pan_start  = (0.0, 0.0)
        self._pan_offset = [0.0, 0.0]
        self._pan_origin = [0.0, 0.0]

        # selección
        self._sel_rect  = None   # (x1,y1,x2,y2)
        self._sel_start = None
        self._sel_img   = None   # bytearray levantado
        self._sel_orig  = None   # (x1,y1) donde se levantó
        self._move_orig = None   # (cx,cy) inicio arrastre

        # outline / line
        self._shape_start = None

        self.on_pick          = None
        self.on_frame_changed = None
        self.on_cursor_moved  = None

        self.set_draw_func(self._draw)
        self.set_focusable(True)
        self.set_hexpand(True); self.set_vexpand(True)
        self._update_size_req()

        d1 = Gtk.GestureDrag(); d1.set_button(1)
        d1.connect("drag-begin",  self._drag_begin)
        d1.connect("drag-update", self._drag_update)
        d1.connect("drag-end",    self._drag_end)
        self.add_controller(d1)

        d2 = Gtk.GestureDrag(); d2.set_button(2)
        d2.connect("drag-begin",  self._pan_begin)
        d2.connect("drag-update", self._pan_update)
        d2.connect("drag-end",    self._pan_end)
        self.add_controller(d2)

        mo = Gtk.EventControllerMotion()
        mo.connect("motion", self._on_motion)
        mo.connect("leave", self._on_leave)
        self.add_controller(mo)

        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        sc.connect("scroll", self._on_scroll)
        self.add_controller(sc)

    # ── zoom ─────────────────────────────────────────────────────────────────
    @property
    def zoom(self): return ZOOM_STEPS[self._zi]

    def zoom_in(self):
        self._zi = min(self._zi + 1, len(ZOOM_STEPS) - 1)
        self._update_size_req()

    def zoom_out(self):
        self._zi = max(self._zi - 1, 0)
        self._update_size_req()

    def zoom_fit(self, view_w, view_h):
        best = 1
        for z in ZOOM_STEPS:
            if z * self.cw <= view_w and z * self.ch <= view_h: best = z
        self._zi = ZOOM_STEPS.index(best) if best in ZOOM_STEPS else 0
        self._pan_offset = [0.0, 0.0]
        self._update_size_req()

    def _update_size_req(self):
        z = self.zoom
        self.set_size_request(self.cw * z, self.ch * z)
        self.queue_draw()

    # ── píxeles ───────────────────────────────────────────────────────────────
    def _idx(self, x, y): return (y * self.cw + x) * 4

    def get_pixel(self, fi, x, y):
        if 0 <= x < self.cw and 0 <= y < self.ch:
            i = self._idx(x, y); d = self._frames[fi]
            return (d[i], d[i+1], d[i+2], d[i+3])
        return (0, 0, 0, 0)

    def set_pixel(self, fi, x, y, color):
        if 0 <= x < self.cw and 0 <= y < self.ch:
            i = self._idx(x, y)
            self._frames[fi][i:i+4] = color
            self._surf_dirty.add(fi)

    def paint_rect(self, fi, cx, cy, color, size):
        half = size // 2
        for dy in range(size):
            for dx in range(size):
                self.set_pixel(fi, cx - half + dx, cy - half + dy, color)

    def _sym_points(self, cx, cy):
        pts = [(cx, cy)]
        if self.symmetry in ("h", "hv"):  pts.append((self.cw - 1 - cx, cy))
        if self.symmetry in ("v", "hv"):  pts.append((cx, self.ch - 1 - cy))
        if self.symmetry == "hv":         pts.append((self.cw - 1 - cx, self.ch - 1 - cy))
        return pts

    def paint_sym(self, fi, cx, cy, color, size):
        for px, py in self._sym_points(cx, cy):
            self.paint_rect(fi, px, py, color, size)

    def flood_fill(self, fi, x, y, nc):
        if not (0 <= x < self.cw and 0 <= y < self.ch): return
        target = self.get_pixel(fi, x, y)
        nc = tuple(nc)
        if tuple(target) == nc: return
        if _NP:
            arr = np.frombuffer(bytes(self._frames[fi]),
                                dtype=np.uint8).reshape(self.ch, self.cw, 4).copy()
            tgt = np.array(target, dtype=np.uint8)
            vis = np.zeros((self.ch, self.cw), dtype=bool)
            stk = [(x, y)]
            while stk:
                px, py = stk.pop()
                if px<0 or px>=self.cw or py<0 or py>=self.ch: continue
                if vis[py,px]: continue
                if not np.array_equal(arr[py,px], tgt): continue
                vis[py,px] = True; arr[py,px] = nc
                stk += [(px+1,py),(px-1,py),(px,py+1),(px,py-1)]
            self._frames[fi] = bytearray(arr.tobytes())
        else:
            stk, vis = [(x,y)], set()
            while stk:
                px, py = stk.pop()
                if (px,py) in vis: continue
                if not (0<=px<self.cw and 0<=py<self.ch): continue
                if self.get_pixel(fi,px,py) != target: continue
                vis.add((px,py)); self.set_pixel(fi,px,py,nc)
                stk += [(px+1,py),(px-1,py),(px,py+1),(px,py-1)]
        self._surf_dirty.add(fi)

    def replace_color(self, fi, x, y, nc):
        """Reemplaza todos los píxeles del color en (x,y) por nc."""
        target = self.get_pixel(fi, x, y)
        nc = tuple(nc)
        if tuple(target) == nc: return
        if _NP:
            arr = np.frombuffer(bytes(self._frames[fi]),
                                dtype=np.uint8).reshape(self.ch, self.cw, 4).copy()
            tgt = np.array(target, dtype=np.uint8)
            mask = np.all(arr == tgt, axis=2)
            arr[mask] = np.array(nc, dtype=np.uint8)
            self._frames[fi] = bytearray(arr.tobytes())
        else:
            for yy in range(self.ch):
                for xx in range(self.cw):
                    if self.get_pixel(fi, xx, yy) == target:
                        self.set_pixel(fi, xx, yy, nc)
        self._surf_dirty.add(fi)

    def draw_outline(self, fi, x1, y1, x2, y2, color, size):
        """Rectángulo vacío (outline)."""
        x1, x2 = min(x1,x2), max(x1,x2)
        y1, y2 = min(y1,y2), max(y1,y2)
        for x in range(x1, x2+1):
            self.paint_sym(fi, x, y1, color, size)
            self.paint_sym(fi, x, y2, color, size)
        for y in range(y1+1, y2):
            self.paint_sym(fi, x1, y, color, size)
            self.paint_sym(fi, x2, y, color, size)

    def draw_line(self, fi, x0, y0, x1, y1, color, size):
        for px, py in _interp(x0, y0, x1, y1):
            self.paint_sym(fi, px, py, color, size)

    def draw_dither(self, fi, cx, cy, size):
        """Patrón de 2 colores intercalados en el área del pincel."""
        half = size // 2
        for dy in range(size):
            for dx in range(size):
                px, py = cx - half + dx, cy - half + dy
                c = self.color if (px + py) % 2 == 0 else self.color2
                self.set_pixel(fi, px, py, c)

    def draw_ellipse(self, fi, x1, y1, x2, y2, color, size, filled=False):
        """Dibuja una elipse (bresenham pixel-art)."""
        from PIL import ImageDraw
        x1, x2 = min(x1,x2), max(x1,x2)
        y1, y2 = min(y1,y2), max(y1,y2)
        im = Image.frombytes("RGBA", (self.cw, self.ch), bytes(self._frames[fi]))
        draw = ImageDraw.Draw(im)
        lw = max(1, size)
        if filled:
            draw.ellipse([x1,y1,x2,y2], fill=tuple(color), outline=None)
        else:
            draw.ellipse([x1,y1,x2,y2], fill=None, outline=tuple(color), width=lw)
        self._frames[fi] = bytearray(im.tobytes())
        self._surf_dirty.add(fi)

    def magic_wand(self, fi, x, y, tolerance=32):
        """Selecciona región contigua por tolerancia de color."""
        if not _NP: return
        arr = np.frombuffer(bytes(self._frames[fi]),
                            dtype=np.uint8).reshape(self.ch, self.cw, 4)
        target = arr[max(0,min(y,self.ch-1)), max(0,min(x,self.cw-1)), :3].astype(np.int32)
        vis    = np.zeros((self.ch, self.cw), dtype=bool)
        stk    = [(x, y)]
        while stk:
            px, py = stk.pop()
            if px<0 or px>=self.cw or py<0 or py>=self.ch: continue
            if vis[py, px]: continue
            diff = np.sqrt(np.sum((arr[py,px,:3].astype(np.int32)-target)**2))
            if diff > tolerance: continue
            vis[py, px] = True
            stk += [(px+1,py),(px-1,py),(px,py+1),(px,py-1)]
        rows = np.any(vis, axis=1); cols = np.any(vis, axis=0)
        if rows.any():
            r1,r2 = rows.argmax(), self.ch-1-rows[::-1].argmax()
            c1,c2 = cols.argmax(), self.cw-1-cols[::-1].argmax()
            self._sel_rect = (c1, r1, c2, r2)
            self._sel_img  = None

    # ── selección ─────────────────────────────────────────────────────────────
    def lift_selection(self):
        if not self._sel_rect: return
        x1,y1,x2,y2 = [int(v) for v in self._sel_rect]
        x1,x2 = max(0,min(x1,x2)), min(self.cw,max(x1,x2))
        y1,y2 = max(0,min(y1,y2)), min(self.ch,max(y1,y2))
        if x2<=x1 or y2<=y1: return
        fi  = self._cur
        arr = np.frombuffer(bytes(self._frames[fi]),
                            dtype=np.uint8).reshape(self.ch, self.cw, 4).copy() if _NP else None
        if arr is not None:
            self._sel_img  = bytearray(arr[y1:y2, x1:x2].tobytes())
            self._sel_orig = (x1, y1, x2-x1, y2-y1)
            arr[y1:y2, x1:x2] = 0
            self._frames[fi] = bytearray(arr.tobytes())
        self._surf_dirty.add(fi)

    def stamp_selection(self, nx1, ny1):
        if self._sel_img is None or self._sel_orig is None: return
        _, _, sw, sh = self._sel_orig
        fi  = self._cur
        arr = np.frombuffer(bytes(self._frames[fi]),
                            dtype=np.uint8).reshape(self.ch, self.cw, 4).copy() if _NP else None
        if arr is None: return
        sel = np.frombuffer(bytes(self._sel_img),
                            dtype=np.uint8).reshape(sh, sw, 4)
        x1i = max(0, int(nx1)); y1i = max(0, int(ny1))
        x2i = min(self.cw, x1i + sw); y2i = min(self.ch, y1i + sh)
        dw, dh = x2i - x1i, y2i - y1i
        if dw > 0 and dh > 0:
            arr[y1i:y2i, x1i:x2i] = sel[:dh, :dw]
        self._frames[fi] = bytearray(arr.tobytes())
        self._surf_dirty.add(fi)
        self._sel_img  = None
        self._sel_orig = None

    # ── undo/redo ─────────────────────────────────────────────────────────────
    def snap_undo(self):
        self._undo.append(tuple(bytes(f) for f in self._frames))
        if len(self._undo) > MAX_UNDO: self._undo.pop(0)
        self._redo.clear()

    def undo(self):
        if not self._undo: return
        self._redo.append(tuple(bytes(f) for f in self._frames))
        snap = self._undo.pop()
        self._frames = [bytearray(f) for f in snap]
        self._cur = min(self._cur, len(self._frames)-1)
        self._surf_dirty = set(range(len(self._frames)))
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()

    def redo(self):
        if not self._redo: return
        self._undo.append(tuple(bytes(f) for f in self._frames))
        snap = self._redo.pop()
        self._frames = [bytearray(f) for f in snap]
        self._cur = min(self._cur, len(self._frames)-1)
        self._surf_dirty = set(range(len(self._frames)))
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()

    # ── fotogramas ────────────────────────────────────────────────────────────
    @property
    def frame_count(self): return len(self._frames)

    def add_frame(self):
        self.snap_undo()
        self._frames.insert(self._cur+1, bytearray(self.cw*self.ch*4))
        self._cur += 1
        self._surf_dirty.add(self._cur)
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()

    def duplicate_frame(self):
        self.snap_undo()
        self._frames.insert(self._cur+1, bytearray(self._frames[self._cur]))
        self._cur += 1
        self._surf_dirty.add(self._cur)
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()

    def delete_frame(self):
        if len(self._frames) <= 1: return
        self.snap_undo()
        self._frames.pop(self._cur)
        self._cur = min(self._cur, len(self._frames)-1)
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()

    def go_to(self, idx: int):
        self._cur = max(0, min(idx, len(self._frames)-1))
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()

    def copy_frame(self):
        self._clip_frame = bytearray(self._frames[self._cur])

    def paste_frame(self):
        if self._clip_frame is None: return
        self.snap_undo()
        self._frames.insert(self._cur+1, bytearray(self._clip_frame))
        self._cur += 1
        self._surf_dirty.add(self._cur)
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()

    # ── importar ──────────────────────────────────────────────────────────────
    def import_image(self, path, pixelate=True):
        resample = Image.NEAREST if pixelate else Image.LANCZOS
        im = Image.open(path).convert("RGBA").resize((self.cw, self.ch), resample)
        self.snap_undo()
        self._frames[self._cur] = bytearray(im.tobytes())
        self._surf_dirty.add(self._cur)
        self.queue_draw()

    def load_from_dir(self, frames_dir: Path, max_dim=128):
        files = sorted(frames_dir.glob("frame_*.png"))[:MAX_FRAMES]
        if not files: return False
        first = Image.open(files[0]).convert("RGBA")
        w, h  = first.size
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            w, h  = max(1, int(w*ratio)), max(1, int(h*ratio))
        self.cw, self.ch = w, h
        self._frames = []
        for fp in files:
            im = Image.open(fp).convert("RGBA")
            if im.size != (w, h): im = im.resize((w, h), Image.NEAREST)
            self._frames.append(bytearray(im.tobytes()))
        self._cur = 0
        self._surf_cache.clear()
        self._surf_dirty = set(range(len(self._frames)))
        self._update_size_req()
        if self.on_frame_changed: self.on_frame_changed()
        return True

    # ── herramientas ──────────────────────────────────────────────────────────
    def _apply_tool(self, cx, cy):
        fi = self._cur
        if   self.tool == "pencil":  self.paint_sym(fi, cx, cy, self.color, self.brush)
        elif self.tool == "eraser":  self.paint_sym(fi, cx, cy, (0,0,0,0), self.brush)
        elif self.tool == "fill":    self.flood_fill(fi, cx, cy, self.color)
        elif self.tool == "replace": self.replace_color(fi, cx, cy, self.color)
        elif self.tool == "dither":  self.draw_dither(fi, cx, cy, self.brush)
        elif self.tool == "wand":    self.magic_wand(fi, cx, cy, self._wand_tol)
        elif self.tool == "pick":
            c = self.get_pixel(fi, cx, cy)
            if self.on_pick: self.on_pick(c)
        self.queue_draw()

    # ── coordenadas ───────────────────────────────────────────────────────────
    def _s2c(self, sx, sy):
        z = self.zoom
        return int(sx // z), int(sy // z)

    # ── entrada ───────────────────────────────────────────────────────────────
    def _drag_begin(self, g, sx, sy):
        self._drag_start = (sx, sy)
        self._drawing = True
        cx, cy = self._s2c(sx, sy)

        if self.tool == "select":
            self._sel_start = (cx, cy)
            self._sel_rect  = (cx, cy, cx, cy)
            self._sel_img   = None
            self.queue_draw(); return

        if self.tool == "move":
            if self._sel_rect and self._sel_img is None:
                self.snap_undo(); self.lift_selection()
            self._move_orig = (cx, cy)
            return

        if self.tool in ("outline", "line", "ellipse", "ellipse_fill", "rect_fill"):
            self._shape_start = (cx, cy)
            self.snap_undo(); return

        self.snap_undo()
        if self.tool not in ("pick", "wand"):
            self._apply_tool(cx, cy)
        self._last_px = (cx, cy)

    def _drag_update(self, g, dx, dy):
        if not self._drawing: return
        cx, cy = self._s2c(self._drag_start[0]+dx, self._drag_start[1]+dy)

        if self.tool == "select":
            sx, sy = self._sel_start
            self._sel_rect = (sx, sy, cx, cy)
            self.queue_draw(); return

        if self.tool == "move" and self._sel_img and self._move_orig:
            ox, oy = self._move_orig
            x1,y1,x2,y2 = self._sel_rect
            w, h = x2-x1, y2-y1
            nx1 = x1 + (cx - ox); ny1 = y1 + (cy - oy)
            self._sel_rect = (nx1, ny1, nx1+w, ny1+h)
            self._move_orig = (cx, cy)
            self.queue_draw(); return

        if self.tool in ("outline", "line", "ellipse", "ellipse_fill", "rect_fill"):
            self.queue_draw(); return

        if (cx, cy) == self._last_px: return
        if self.tool in ("pencil", "eraser", "dither"):
            for px, py in _interp(*self._last_px, cx, cy):
                self._apply_tool(px, py)
        else:
            self._apply_tool(cx, cy)
        self._last_px = (cx, cy)

    def _drag_end(self, g, dx, dy):
        cx, cy = self._s2c(self._drag_start[0]+dx, self._drag_start[1]+dy)

        if self.tool == "select":
            x0,y0 = self._sel_start
            self._sel_rect = (min(x0,cx), min(y0,cy), max(x0,cx), max(y0,cy))
            self._drawing = False; self.queue_draw(); return

        if self.tool == "move" and self._sel_img:
            x1,y1,_,_ = self._sel_rect
            self.stamp_selection(x1, y1)
            self._sel_rect  = None
            self._move_orig = None
            self._drawing   = False; self.queue_draw(); return

        if self.tool == "outline" and self._shape_start:
            sx, sy = self._shape_start
            self.draw_outline(self._cur, sx, sy, cx, cy, self.color, self.brush)
            self._shape_start = None

        elif self.tool == "line" and self._shape_start:
            sx, sy = self._shape_start
            self.draw_line(self._cur, sx, sy, cx, cy, self.color, self.brush)
            self._shape_start = None

        elif self.tool == "ellipse" and self._shape_start:
            sx, sy = self._shape_start
            self.draw_ellipse(self._cur, sx, sy, cx, cy, self.color, self.brush, filled=False)
            self._shape_start = None

        elif self.tool == "ellipse_fill" and self._shape_start:
            sx, sy = self._shape_start
            self.draw_ellipse(self._cur, sx, sy, cx, cy, self.color, self.brush, filled=True)
            self._shape_start = None

        elif self.tool == "rect_fill" and self._shape_start:
            sx, sy = self._shape_start
            from PIL import Image as _Img, ImageDraw as _ID
            x1,y1 = min(sx,cx), min(sy,cy)
            x2,y2 = max(sx,cx), max(sy,cy)
            im = _Img.frombytes("RGBA",(self.cw,self.ch),bytes(self._frames[self._cur]))
            _ID.Draw(im).rectangle([x1,y1,x2,y2], fill=tuple(self.color))
            self._frames[self._cur] = bytearray(im.tobytes())
            self._surf_dirty.add(self._cur)
            self._shape_start = None

        elif self.tool == "wand":
            self._apply_tool(cx, cy)

        elif self.tool == "pick":
            self._apply_tool(cx, cy)

        self._drawing = False
        self.queue_draw()

    def _pan_begin(self, g, sx, sy):
        self._panning = True
        self._pan_origin = [self._pan_offset[0], self._pan_offset[1]]
        self._pan_start  = (sx, sy)

    def _pan_update(self, g, dx, dy):
        if not self._panning: return
        self._pan_offset[0] = self._pan_origin[0] + dx
        self._pan_offset[1] = self._pan_origin[1] + dy
        self.queue_draw()

    def _pan_end(self, g, dx, dy):
        self._panning = False

    def _on_motion(self, ctrl, sx, sy):
        cx, cy = self._s2c(sx, sy)
        if (cx, cy) != self._cursor_px:
            self._cursor_px = (cx, cy)
            self.queue_draw()
            if self.on_cursor_moved and 0 <= cx < self.cw and 0 <= cy < self.ch:
                self.on_cursor_moved(cx, cy, self.get_pixel(self._cur, cx, cy))

    def _on_leave(self, ctrl):
        # ocultar el cursor de pincel al salir del lienzo (evita el recuadro
        # "fantasma" que queda dibujado encima)
        if self._cursor_px != (-1, -1):
            self._cursor_px = (-1, -1)
            self.queue_draw()

    def _on_scroll(self, ctrl, dx, dy):
        mods = ctrl.get_current_event_state()
        if mods & Gdk.ModifierType.CONTROL_MASK:
            self.zoom_out() if dy > 0 else self.zoom_in()
            return True
        return False

    # ── renderizado ───────────────────────────────────────────────────────────
    def _get_surf(self, fi) -> cairo.ImageSurface:
        if fi not in self._surf_dirty and fi in self._surf_cache:
            data = self._surf_cache[fi]
        else:
            data = _to_cairo(bytes(self._frames[fi]), self.cw, self.ch)
            self._surf_cache[fi] = data
            self._surf_dirty.discard(fi)
        return cairo.ImageSurface.create_for_data(
            data, cairo.Format.ARGB32, self.cw, self.ch, self.cw*4)

    def _paint_surf(self, cr, surf, alpha=1.0):
        z   = self.zoom
        pat = cairo.SurfacePattern(surf)
        pat.set_filter(cairo.Filter.NEAREST)
        m = cairo.Matrix(); m.scale(1/z, 1/z); pat.set_matrix(m)
        cr.set_source(pat)
        if alpha < 1.0: cr.paint_with_alpha(alpha)
        else:           cr.paint()

    def _draw_checker(self, cr, w, h):
        # checker sutil: dos grises muy próximos (menos ruido visual al dibujar)
        sq = 8
        for y in range(0, h, sq):
            for x in range(0, w, sq):
                v = 0.82 if (x//sq + y//sq) % 2 == 0 else 0.74
                cr.set_source_rgb(v, v, v)
                cr.rectangle(x, y, min(sq,w-x), min(sq,h-y)); cr.fill()

    def _draw_grid(self, cr, z):
        cr.set_source_rgba(0, 0, 0, 0.18); cr.set_line_width(0.5)
        for x in range(self.cw+1):
            cr.move_to(x*z, 0); cr.line_to(x*z, self.ch*z)
        for y in range(self.ch+1):
            cr.move_to(0, y*z); cr.line_to(self.cw*z, y*z)
        cr.stroke()

    def _draw_cursor(self, cr, z):
        cx, cy = self._cursor_px
        if not (0 <= cx < self.cw and 0 <= cy < self.ch): return
        half = self.brush // 2
        rx, ry = (cx-half)*z, (cy-half)*z
        rw, rh = self.brush*z, self.brush*z
        cr.set_source_rgba(0,0,0,0.6); cr.set_line_width(2.0)
        cr.rectangle(rx, ry, rw, rh); cr.stroke()
        cr.set_source_rgba(1,1,1,0.9); cr.set_line_width(1.0)
        cr.rectangle(rx+1, ry+1, rw-2, rh-2); cr.stroke()
        # espejos simetría
        blue = (0.2, 0.6, 1.0, 0.7)
        if self.symmetry in ("h","hv"):
            mx = (self.cw-1-cx-half)*z
            cr.set_source_rgba(*blue); cr.set_line_width(1.0)
            cr.rectangle(mx, ry, rw, rh); cr.stroke()
        if self.symmetry in ("v","hv"):
            my = (self.ch-1-cy-half)*z
            cr.set_source_rgba(*blue); cr.set_line_width(1.0)
            cr.rectangle(rx, my, rw, rh); cr.stroke()
        if self.symmetry == "hv":
            mx2 = (self.cw-1-cx-half)*z; my2 = (self.ch-1-cy-half)*z
            cr.set_source_rgba(*blue); cr.set_line_width(1.0)
            cr.rectangle(mx2, my2, rw, rh); cr.stroke()

    def _draw_sym_guides(self, cr, z):
        if self.symmetry == "none": return
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.5)
        cr.set_line_width(1.0); cr.set_dash([5.0, 3.0])
        if self.symmetry in ("h","hv"):
            mx = self.cw/2*z; cr.move_to(mx,0); cr.line_to(mx,self.ch*z); cr.stroke()
        if self.symmetry in ("v","hv"):
            my = self.ch/2*z; cr.move_to(0,my); cr.line_to(self.cw*z,my); cr.stroke()
        cr.set_dash([])

    def _draw_shape_preview(self, cr, z):
        if self._shape_start is None or not self._drawing: return
        cx, cy = self._cursor_px
        sx, sy = self._shape_start
        cr.set_source_rgba(*(c/255 for c in self.color))
        cr.set_line_width(1.0); cr.set_dash([3.0, 3.0])
        x1,y1 = min(sx,cx)*z, min(sy,cy)*z
        rw,rh  = abs(cx-sx)*z, abs(cy-sy)*z
        if self.tool in ("outline", "rect_fill"):
            cr.rectangle(x1, y1, rw, rh); cr.stroke()
        elif self.tool in ("ellipse", "ellipse_fill"):
            if rw > 0 and rh > 0:
                cr.save()
                cr.translate(x1+rw/2, y1+rh/2)
                cr.scale(rw/2, rh/2)
                cr.arc(0, 0, 1, 0, 2*math.pi)
                cr.restore(); cr.stroke()
        elif self.tool == "line":
            cr.move_to(sx*z, sy*z); cr.line_to(cx*z, cy*z); cr.stroke()
        cr.set_dash([])

    def _draw_sel_preview(self, cr, z):
        if not self._sel_rect: return
        x1,y1,x2,y2 = self._sel_rect
        rx,ry = min(x1,x2)*z, min(y1,y2)*z
        rw,rh = abs(x2-x1)*z, abs(y2-y1)*z
        cr.set_source_rgba(1,1,1,0.8); cr.set_line_width(1.0)
        cr.set_dash([3.0,3.0]); cr.rectangle(rx,ry,rw,rh); cr.stroke()
        cr.set_dash([])

    def _draw(self, area, cr, width, height):
        z  = self.zoom
        cw, ch = self.cw*z, self.ch*z

        cr.set_source_rgb(0.18,0.18,0.18); cr.paint()

        cr.save(); cr.rectangle(0,0,cw,ch); cr.clip()
        self._draw_checker(cr, cw, ch)
        cr.restore()

        if self.onion and self._cur > 0:
            self._paint_surf(cr, self._get_surf(self._cur-1), ONION_ALPHA)

        self._paint_surf(cr, self._get_surf(self._cur))

        if z >= 3:
            cr.save(); cr.rectangle(0,0,cw,ch); cr.clip()
            self._draw_grid(cr, z); cr.restore()

        self._draw_sym_guides(cr, z)
        self._draw_shape_preview(cr, z)
        self._draw_sel_preview(cr, z)
        self._draw_cursor(cr, z)

    # ── exportar ──────────────────────────────────────────────────────────────
    def to_pil(self, fi) -> Image.Image:
        return Image.frombytes("RGBA", (self.cw, self.ch), bytes(self._frames[fi]))

    def thumbnail(self, fi=None) -> Gdk.Texture:
        fi  = self._cur if fi is None else fi
        im  = self.to_pil(fi).resize((THUMB, THUMB), Image.NEAREST)
        raw = GLib.Bytes.new(im.tobytes())
        return Gdk.MemoryTexture.new(THUMB, THUMB, Gdk.MemoryFormat.R8G8B8A8,
                                     raw, THUMB * 4)


# ── PixelEditor (ventana) ─────────────────────────────────────────────────────
class PixelEditor(Gtk.Window):
    def __init__(self, app, anim_id=None, pose=None, guided=False):
        super().__init__(application=app, title="Editor de Píxeles — AnimaLinux")
        self.app      = app
        self.anim_id  = anim_id
        self._guided  = guided
        self._playing = False
        self._play_id = None

        self.canvas = PixelCanvas(64, 64)
        self.canvas.on_pick          = self._on_pick
        self.canvas.on_frame_changed = self._rebuild_strip
        self.canvas.on_cursor_moved  = self._on_cursor

        from ..ui import theme
        theme.apply(self)

        self.set_default_size(1100, 740)
        self._build_ui()

        if pose:
            self.pose_entry.set_text(pose)
        elif guided:
            self._suggest_next_pose()

        if anim_id is not None and pose in (None, "default"):
            fd = app.library.frames_dir(anim_id)
            if self.canvas.load_from_dir(fd):
                self._rebuild_strip()

        if anim_id is None:
            GLib.idle_add(self._ask_canvas_size)

        GLib.idle_add(self._show_tutorial)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)
        root.append(self._build_toolbar())

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True); root.append(body)
        body.append(self._build_left_panel())

        scroll = Gtk.ScrolledWindow()
        scroll.set_hexpand(True); scroll.set_vexpand(True)
        scroll.set_child(self.canvas); body.append(scroll)

        body.append(self._build_right_panel())
        root.append(self._build_status_bar())

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)

    def _build_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        bar.add_css_class("editor-toolbar")

        # zoom
        zm_out = icon_button("zoom_out", "Alejar (−)")
        zm_out.connect("clicked", lambda _: (self.canvas.zoom_out(), self._upd_zoom()))
        bar.append(zm_out)
        self.zoom_lbl = Gtk.Label(label=f"{self.canvas.zoom}×")
        self.zoom_lbl.set_size_request(40,-1)
        self.zoom_lbl.add_css_class("monospace"); bar.append(self.zoom_lbl)
        zm_in = icon_button("zoom_in", "Acercar (+)")
        zm_in.connect("clicked", lambda _: (self.canvas.zoom_in(), self._upd_zoom()))
        bar.append(zm_in)
        fit_b = icon_button("fit", "Ajustar a la vista")
        fit_b.connect("clicked", self._zoom_fit); bar.append(fit_b)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # FPS / play
        bar.append(Gtk.Label(label="FPS"))
        self.fps_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=12, lower=1, upper=60, step_increment=1))
        self.fps_spin.set_size_request(55,-1); bar.append(self.fps_spin)
        self.play_btn = icon_button("play", "Reproducir (Espacio)", toggle=True)
        self.play_btn.connect("toggled", self._on_play_toggle); bar.append(self.play_btn)

        onion = icon_button("onion", "Papel cebolla", toggle=True)
        onion.connect("toggled",
            lambda b: setattr(self.canvas,"onion",b.get_active())
            or self.canvas.queue_draw())
        bar.append(onion)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # simetría
        self._sym_btns = {}
        for ic, val, tip in [("sym_none","none","Sin simetría"),
                             ("sym_h","h","Simetría horizontal"),
                             ("sym_v","v","Simetría vertical"),
                             ("sym_hv","hv","Simetría H+V")]:
            b = icon_button(ic, tip, toggle=True)
            b.connect("toggled", self._on_sym_toggle, val)
            self._sym_btns[val] = b; bar.append(b)
        self._sym_btns["none"].set_active(True)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # importar / undo / redo
        imp = icon_button("import", "Importar imagen al lienzo")
        imp.connect("clicked", self._on_import); bar.append(imp)
        undo = icon_button("undo", "Deshacer (Z / Ctrl+Z)")
        undo.connect("clicked", lambda _: self.canvas.undo()); bar.append(undo)
        redo = icon_button("redo", "Rehacer (Y / Ctrl+Y)")
        redo.connect("clicked", lambda _: self.canvas.redo()); bar.append(redo)

        spacer = Gtk.Box(); spacer.set_hexpand(True); bar.append(spacer)
        help_btn = icon_button("help", "Guía rápida del editor")
        help_btn.connect("clicked", lambda _: self._show_tutorial(force=True))
        bar.append(help_btn)

        close_btn = icon_button("close", "Cerrar el editor (Ctrl+W)")
        close_btn.add_css_class("close-btn")
        close_btn.connect("clicked", lambda _: self._confirm_close())
        bar.append(close_btn)

        return bar

    def _build_left_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        panel.add_css_class("editor-panel")
        panel.set_margin_start(8); panel.set_margin_end(6); panel.set_margin_top(6)
        panel.set_size_request(104, -1)

        head = Gtk.Label(label="HERRAMIENTAS", xalign=0)
        head.add_css_class("panel-head"); panel.append(head)
        tools = [
            ("pencil",       "Lápiz (B)"),
            ("eraser",       "Borrador (E)"),
            ("fill",         "Relleno (F)"),
            ("replace",      "Reemplazar color (R)"),
            ("line",         "Línea (L)"),
            ("outline",      "Rectángulo contorno (O)"),
            ("rect_fill",    "Rectángulo relleno"),
            ("ellipse",      "Elipse contorno (C)"),
            ("ellipse_fill", "Elipse rellena (V)"),
            ("dither",       "Tramado (D)"),
            ("wand",         "Varita mágica (W)"),
            ("select",       "Selección (S)"),
            ("move",         "Mover (M)"),
            ("pick",         "Cuentagotas (I)"),
        ]
        self._tool_btns = {}
        tg = Gtk.Grid(); tg.set_row_spacing(3); tg.set_column_spacing(3)
        tg.set_halign(Gtk.Align.CENTER)
        for i, (tid, tip) in enumerate(tools):
            btn = icon_button(tid, tip, size=20, toggle=True)
            if tid == "pencil": btn.set_active(True)
            btn.connect("toggled", self._on_tool_toggle, tid)
            self._tool_btns[tid] = btn
            tg.attach(btn, i % 2, i // 2, 1, 1)
        panel.append(tg)

        panel.append(Gtk.Separator())
        ch = Gtk.Label(label="COLOR", xalign=0); ch.add_css_class("panel-head")
        panel.append(ch)

        self._color_preview = Gtk.DrawingArea()
        self._color_preview.set_size_request(100,24)
        self._color_preview.set_draw_func(self._draw_color_preview)
        panel.append(self._color_preview)

        self._color_btn = Gtk.ColorButton(); self._color_btn.set_use_alpha(True)
        rgba = Gdk.RGBA(); rgba.red=rgba.green=rgba.blue=0; rgba.alpha=1
        self._color_btn.set_rgba(rgba)
        self._color_btn.connect("color-set", self._on_color_set)
        panel.append(self._color_btn)

        panel.append(Gtk.Label(label="Color 2 (dither)"))
        self._color2_btn = Gtk.ColorButton(); self._color2_btn.set_use_alpha(True)
        rgba2 = Gdk.RGBA(); rgba2.red=rgba2.green=rgba2.blue=1; rgba2.alpha=1
        self._color2_btn.set_rgba(rgba2)
        self._color2_btn.connect("color-set", self._on_color2_set)
        panel.append(self._color2_btn)

        panel.append(Gtk.Separator())
        panel.append(Gtk.Label(label="Tamaño ([ ])"))
        self.brush_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=1, lower=1, upper=32, step_increment=1))
        self.brush_spin.connect("value-changed",
            lambda s: setattr(self.canvas, "brush", int(s.get_value())))
        panel.append(self.brush_spin)

        panel.append(Gtk.Separator())
        panel.append(Gtk.Label(label="Paleta"))

        cols = 6
        grid = Gtk.Grid()
        grid.set_row_spacing(2); grid.set_column_spacing(2)
        for i, c in enumerate(PALETTE):
            da = Gtk.DrawingArea(); da.set_size_request(17,17)
            da.set_draw_func(lambda a,cr,w,h,col=c:(
                self._draw_swatch_checker(cr,w,h),
                cr.set_source_rgba(col[0]/255,col[1]/255,col[2]/255,col[3]/255),
                cr.paint()))
            da.set_tooltip_text(f"R:{c[0]} G:{c[1]} B:{c[2]} A:{c[3]}")
            click = Gtk.GestureClick()
            click.connect("pressed", lambda g,n,x,y,col=c: self._set_color(col))
            da.add_controller(click)
            grid.attach(da, i % cols, i // cols, 1, 1)
        panel.append(grid)

        panel.append(Gtk.Separator())
        panel.append(Gtk.Label(label="Tolerancia varita"))
        self.wand_tol_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=32, lower=0, upper=255, step_increment=8))
        self.wand_tol_spin.connect("value-changed",
            lambda s: setattr(self.canvas, "_wand_tol", int(s.get_value())))
        panel.append(self.wand_tol_spin)

        return panel

    def _draw_swatch_checker(self, cr, w, h):
        sq = 4
        for y in range(0,h,sq):
            for x in range(0,w,sq):
                v = 0.8 if (x//sq+y//sq)%2==0 else 0.6
                cr.set_source_rgb(v,v,v)
                cr.rectangle(x,y,sq,sq); cr.fill()

    def _build_right_panel(self):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        panel.add_css_class("editor-panel"); panel.add_css_class("right")
        panel.set_margin_start(6); panel.set_margin_end(8); panel.set_margin_top(6)
        panel.set_size_request(96,-1)

        head = Gtk.Label(label="LÍNEA DE TIEMPO", xalign=0)
        head.add_css_class("panel-head"); panel.append(head)

        # fila de acciones sobre los fotogramas (con iconos)
        actions = Gtk.Box(spacing=2); actions.set_halign(Gtk.Align.CENTER)
        for ic, tip, cb, refresh in [
            ("add", "Nuevo fotograma (Ctrl+N)", self.canvas.add_frame, True),
            ("duplicate", "Duplicar (Ctrl+D)", self.canvas.duplicate_frame, True),
            ("copy", "Copiar (Ctrl+C)", self.canvas.copy_frame, False),
            ("paste", "Pegar (Ctrl+V)", self.canvas.paste_frame, True),
            ("trash", "Borrar (Supr)", self.canvas.delete_frame, True),
        ]:
            b = icon_button(ic, tip)
            b.connect("clicked",
                      lambda _, f=cb, r=refresh: (f(), self._rebuild_strip() if r else None))
            actions.append(b)
        panel.append(actions)

        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        sc.add_css_class("timeline")
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.strip_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.strip_box.set_margin_top(4); self.strip_box.set_margin_bottom(4)
        sc.set_child(self.strip_box); panel.append(sc)

        panel.append(Gtk.Separator())
        gif_b = Gtk.Button(); gif_b.add_css_class("suggested-action")
        gb = Gtk.Box(spacing=5); gb.set_halign(Gtk.Align.CENTER)
        gb.append(icon_image("gif", 16)); gb.append(Gtk.Label(label="Exportar GIF"))
        gif_b.set_child(gb)
        gif_b.set_tooltip_text("Exportar animación como GIF")
        gif_b.connect("clicked", lambda _: self._export_gif_dialog()); panel.append(gif_b)

        self._rebuild_strip()
        return panel

    def _build_status_bar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("editor-statusbar")
        bar.set_margin_start(8); bar.set_margin_end(8)
        bar.set_margin_top(3); bar.set_margin_bottom(3)

        self.cursor_lbl = Gtk.Label(label="X:— Y:—")
        self.cursor_lbl.set_size_request(100,-1)
        self.cursor_lbl.add_css_class("monospace"); bar.append(self.cursor_lbl)

        self.px_color_lbl = Gtk.Label(label="")
        self.px_color_lbl.add_css_class("monospace")
        self.px_color_lbl.set_hexpand(True); bar.append(self.px_color_lbl)

        if self.anim_id is None:
            bar.append(Gtk.Label(label="Nombre:"))
            self.name_entry = Gtk.Entry()
            self.name_entry.set_placeholder_text("Mi mascota")
            self.name_entry.set_size_request(110,-1); bar.append(self.name_entry)
        else:
            self.name_entry = None

        bar.append(Gtk.Label(label="Pose:"))
        self.pose_entry = Gtk.Entry(); self.pose_entry.set_text("default")
        self.pose_entry.set_size_request(84,-1); bar.append(self.pose_entry)

        self.save_status = Gtk.Label(label=""); self.save_status.add_css_class("dim-label")
        bar.append(self.save_status)

        save_btn = Gtk.Button(); save_btn.add_css_class("suggested-action")
        sb = Gtk.Box(spacing=5); sb.append(icon_image("save", 16))
        sb.append(Gtk.Label(label="Guardar pose")); save_btn.set_child(sb)
        save_btn.connect("clicked", lambda _: self._save_pose())
        bar.append(save_btn)
        return bar

    # ── tira ──────────────────────────────────────────────────────────────────
    def _rebuild_strip(self):
        child = self.strip_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.strip_box.remove(child); child = nxt
        for i in range(self.canvas.frame_count):
            vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            pic = Gtk.Picture(); pic.set_size_request(THUMB,THUMB)
            pic.set_content_fit(Gtk.ContentFit.CONTAIN)
            pic.set_paintable(self.canvas.thumbnail(i))
            lbl = Gtk.Label(label=str(i+1))
            vb.append(pic); vb.append(lbl)
            btn = Gtk.Button(); btn.set_child(vb)
            btn.add_css_class("frame-cell")
            if i == self.canvas._cur: btn.add_css_class("current")
            btn.connect("clicked", lambda _,idx=i: (self.canvas.go_to(idx),
                                                    self._rebuild_strip()))
            self.strip_box.append(btn)

    # ── zoom ──────────────────────────────────────────────────────────────────
    def _upd_zoom(self): self.zoom_lbl.set_text(f"{self.canvas.zoom}×")

    def _zoom_fit(self, _):
        sc = self.canvas.get_parent()
        if sc:
            self.canvas.zoom_fit(sc.get_allocated_width(), sc.get_allocated_height())
            self._upd_zoom()

    # ── simetría ──────────────────────────────────────────────────────────────
    def _on_sym_toggle(self, btn, val):
        if not btn.get_active(): return
        self.canvas.symmetry = val
        for k,b in self._sym_btns.items():
            if k != val and b.get_active(): b.set_active(False)
        self.canvas.queue_draw()

    # ── color ─────────────────────────────────────────────────────────────────
    def _set_color(self, color):
        self.canvas.color = color
        rgba = Gdk.RGBA()
        rgba.red,rgba.green,rgba.blue,rgba.alpha = (c/255 for c in color)
        self._color_btn.set_rgba(rgba)
        self._color_preview.queue_draw()

    def _on_color_set(self, btn):
        rgba = btn.get_rgba()
        self.canvas.color = (int(rgba.red*255),int(rgba.green*255),
                             int(rgba.blue*255),int(rgba.alpha*255))
        self._color_preview.queue_draw()

    def _on_color2_set(self, btn):
        rgba = btn.get_rgba()
        self.canvas.color2 = (int(rgba.red*255),int(rgba.green*255),
                              int(rgba.blue*255),int(rgba.alpha*255))

    def _on_pick(self, color):
        self._set_color(color)
        self._tool_btns["pencil"].set_active(True)

    def _draw_color_preview(self, area, cr, w, h):
        self._draw_swatch_checker(cr, w, h)
        r,g,b,a = (c/255 for c in self.canvas.color)
        cr.set_source_rgba(r,g,b,a); cr.paint()

    def _on_cursor(self, cx, cy, color):
        self.cursor_lbl.set_text(f"X:{cx:3d} Y:{cy:3d}")
        self.px_color_lbl.set_text(
            f"  R:{color[0]:3d} G:{color[1]:3d} B:{color[2]:3d} A:{color[3]:3d}")

    # ── herramientas ──────────────────────────────────────────────────────────
    def _on_tool_toggle(self, btn, tid):
        if not btn.get_active(): return
        if self.canvas.tool == "move" and tid != "move":
            if self.canvas._sel_img:
                x1,y1,_,_ = self.canvas._sel_rect
                self.canvas.stamp_selection(x1, y1)
                self.canvas._sel_rect = None
        self.canvas.tool = tid
        for k,b in self._tool_btns.items():
            if k != tid and b.get_active(): b.set_active(False)

    def _select_tool(self, tid):
        if tid in self._tool_btns:
            self._tool_btns[tid].set_active(True)

    # ── reproducir ────────────────────────────────────────────────────────────
    def _on_play_toggle(self, btn):
        self._playing = btn.get_active()
        if self._playing:
            fps = int(self.fps_spin.get_value())
            self._play_id = GLib.timeout_add(max(16,1000//fps), self._tick)
        elif self._play_id:
            GLib.source_remove(self._play_id); self._play_id = None

    def _tick(self):
        if not self._playing: return False
        self.canvas.go_to((self.canvas._cur+1) % self.canvas.frame_count)
        self._rebuild_strip()
        return True

    # ── atajos ────────────────────────────────────────────────────────────────
    def _on_key(self, ctrl, keyval, keycode, mods):
        ctrl_h = bool(mods & Gdk.ModifierType.CONTROL_MASK)
        key    = Gdk.keyval_name(keyval) or ""
        if ctrl_h:
            if key in ("z","Z"): self.canvas.undo(); return True
            if key in ("y","Y"): self.canvas.redo(); return True
            if key in ("s","S"): self._save_pose(); return True
            if key in ("d","D"): self.canvas.duplicate_frame(); self._rebuild_strip(); return True
            if key in ("n","N"): self.canvas.add_frame(); self._rebuild_strip(); return True
            if key in ("c","C"): self.canvas.copy_frame(); return True
            if key in ("v","V"): self.canvas.paste_frame(); self._rebuild_strip(); return True
            if key in ("w","W"): self._confirm_close(); return True
        else:
            if key in ("b","B"): self._select_tool("pencil");       return True
            if key in ("e","E"): self._select_tool("eraser");       return True
            if key in ("f","F"): self._select_tool("fill");         return True
            if key in ("r","R"): self._select_tool("replace");      return True
            if key in ("o","O"): self._select_tool("outline");      return True
            if key in ("c","C"): self._select_tool("ellipse");      return True
            if key in ("v","V"): self._select_tool("ellipse_fill"); return True
            if key in ("l","L"): self._select_tool("line");         return True
            if key in ("d","D"): self._select_tool("dither");       return True
            if key in ("w","W"): self._select_tool("wand");         return True
            if key in ("s","S"): self._select_tool("select");       return True
            if key in ("m","M"): self._select_tool("move");         return True
            if key in ("i","I"): self._select_tool("pick");         return True
            if key in ("z","Z"): self.canvas.undo(); return True
            if key in ("y","Y"): self.canvas.redo(); return True
            if key in ("plus","equal"): self.canvas.zoom_in(); self._upd_zoom(); return True
            if key == "minus":          self.canvas.zoom_out();self._upd_zoom(); return True
            if key == "bracketleft":
                v = max(1, self.canvas.brush-1)
                self.canvas.brush = v; self.brush_spin.set_value(v); return True
            if key == "bracketright":
                v = min(32, self.canvas.brush+1)
                self.canvas.brush = v; self.brush_spin.set_value(v); return True
            if key == "Delete": self.canvas.delete_frame(); self._rebuild_strip(); return True
            if key == "space":
                self.play_btn.set_active(not self.play_btn.get_active()); return True
            if key == "Escape":
                if self.canvas._sel_rect:
                    if self.canvas._sel_img:
                        x1,y1,_,_ = self.canvas._sel_rect
                        self.canvas.stamp_selection(x1,y1)
                    self.canvas._sel_rect = None
                    self.canvas.queue_draw(); return True
        return False

    # ── importar ──────────────────────────────────────────────────────────────
    def _on_import(self, _):
        dlg = Gtk.FileDialog(); dlg.set_title("Elige imagen base")
        dlg.open(self, None, self._on_file_chosen)

    def _on_file_chosen(self, dlg, result):
        try:
            gf = dlg.open_finish(result)
        except GLib.Error:
            return
        md = Gtk.AlertDialog()
        md.set_message("¿Cómo importar la imagen?")
        md.set_detail("«Pixelar» ajusta a resolución del lienzo.\n«Suavizado» usa interpolación bicúbica.")
        md.set_buttons(["Pixelar","Suavizado","Cancelar"])
        md.set_default_button(0); md.set_cancel_button(2)
        md.choose(self, None,
            lambda d,r,path=gf.get_path(): self._import_done(d,r,path))

    def _import_done(self, dialog, result, path):
        try:
            idx = dialog.choose_finish(result)
        except GLib.Error:
            return
        if idx == 2: return
        self.canvas.import_image(path, pixelate=(idx==0))
        self._rebuild_strip()

    # ── tutorial ──────────────────────────────────────────────────────────────
    def _show_tutorial(self, force=False):
        from .. import settings as _s
        if not force and _s.get("tutorial_pixel_shown", False):
            return
        dlg = Gtk.Dialog(title="Editor de Píxeles — Guía rápida",
                         transient_for=self, modal=True)
        dlg.set_default_size(500, 430)
        box = dlg.get_content_area()
        box.set_spacing(0)

        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        txt = Gtk.TextView(); txt.set_editable(False); txt.set_cursor_visible(False)
        txt.set_wrap_mode(Gtk.WrapMode.WORD)
        txt.set_margin_start(18); txt.set_margin_end(18)
        txt.set_margin_top(14); txt.set_margin_bottom(14)
        buf = txt.get_buffer()
        GUIDE = (
            "✏️  EDITOR DE PÍXELES — pixel art animado, estilo Aseprite.\n"
            "Dibuja punto a punto cada fotograma y guárdalo como pose para\n"
            "que tu mascota lo use.\n\n"
            "🚀  FLUJO RECOMENDADO\n"
            "────────────────────────────────────────\n"
            "  1. Elige el tamaño del lienzo (16², 32², 64²…).\n"
            "  2. Dibuja el primer fotograma con la paleta y el lápiz.\n"
            "  3. ➕ añade fotogramas; usa el 👁 papel cebolla como guía.\n"
            "  4. ▶ reproduce para revisar el movimiento.\n"
            "  5. Escribe el nombre de la pose y «Guardar pose».\n\n"
            "✏️  HERRAMIENTAS  (panel izquierdo)\n"
            "────────────────────────────────────────\n"
            "  B  Lápiz          E  Borrador\n"
            "  F  Relleno        R  Reemplazar color\n"
            "  O  Outline rect   L  Línea\n"
            "  C  Elipse ○       V  Elipse ●\n"
            "  D  Dithering      W  Varita mágica\n"
            "  S  Selección      M  Mover selección\n"
            "  I  Cuentagotas\n"
            "  [ ]  tamaño del lápiz\n\n"
            "🎨  PALETA DE COLORES  (panel izquierdo)\n"
            "────────────────────────────────────────\n"
            "  Clic izq. → color primario (FG)\n"
            "  El color 2 se usa en Dithering\n\n"
            "🔁  SIMETRÍA  (toolbar)\n"
            "────────────────────────────────────────\n"
            "  ↔ Horizontal  ↕ Vertical  ✦ Ambas\n"
            "  Ideal para cuerpos y caras simétricas.\n\n"
            "🎞️  FRAMES  (panel derecho)\n"
            "────────────────────────────────────────\n"
            "  ➕ Nuevo frame    ⎘ Duplicar\n"
            "  👁 Papel cebolla  Ctrl+C/V copiar/pegar\n"
            "  Clic en un frame para ir a él\n"
            "  ▶ reproducir animación  (Espacio)\n\n"
            "💾  GUARDAR  (¡no pierdas tu trabajo!)\n"
            "────────────────────────────────────────\n"
            "  Escribe el nombre de la pose abajo\n"
            "  (ej: default, walk, idle, greet, jump…)\n"
            "  → «💾 Guardar pose» o Ctrl+S.\n"
            "  Guarda cada pose antes de cerrar para poder seguir\n"
            "  ampliando la animación más tarde.\n\n"
            "🔍  ZOOM\n"
            "  +/-  o  Ctrl+Scroll  |  botón medio = pan\n\n"
            "❌  CERRAR\n"
            "  Botón ✕ (arriba a la derecha) o Ctrl+W.\n"
            "  Te preguntará si quieres guardar antes de salir.\n"
        )
        buf.set_text(GUIDE)
        sc.set_child(txt)
        box.append(sc)

        footer = Gtk.Box(spacing=10)
        footer.set_margin_start(14); footer.set_margin_end(14)
        footer.set_margin_top(8); footer.set_margin_bottom(10)
        no_show = Gtk.CheckButton(label="No mostrar al iniciar el editor")
        no_show.set_hexpand(True)
        footer.append(no_show)
        ok = Gtk.Button(label="✓  Entendido")
        ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: (
            _s.set_val("tutorial_pixel_shown", no_show.get_active()),
            dlg.destroy()))
        footer.append(ok)
        box.append(footer)
        dlg.present()

    # ── cerrar ────────────────────────────────────────────────────────────────
    def _confirm_close(self):
        """Confirma antes de cerrar para no perder el trabajo sin guardar."""
        dlg = Gtk.AlertDialog()
        dlg.set_message("¿Cerrar el editor de píxeles?")
        dlg.set_detail("Si no has guardado la pose (botón 💾 o Ctrl+S) se "
                       "perderán los cambios. Guarda primero si quieres "
                       "continuar el trabajo más tarde.")
        dlg.set_buttons(["Cancelar", "Guardar y cerrar", "Cerrar sin guardar"])
        dlg.set_cancel_button(0)
        dlg.set_default_button(1)
        dlg.choose(self, None, self._confirm_close_done)

    def _confirm_close_done(self, dlg, result):
        try:
            idx = dlg.choose_finish(result)
        except Exception:  # noqa: BLE001  (cancelado con Esc)
            return
        if idx == 1:
            self._save_pose(); self.close()
        elif idx == 2:
            self.close()

    # ── guardar pose ──────────────────────────────────────────────────────────
    def _save_pose(self):
        pose = self.pose_entry.get_text().strip() or "default"
        fps  = int(self.fps_spin.get_value())
        cw, ch = self.canvas.cw, self.canvas.ch
        from ..core import image_processor as importer

        if self.anim_id is None:
            name = (self.name_entry.get_text().strip() if self.name_entry
                    else "Sin nombre") or "Sin nombre"
            aid  = self.app.library.new_id()
            fd   = self.app.library.frames_dir(aid)
            pose_dir = fd if pose=="default" else fd/pose
            pose_dir.mkdir(parents=True, exist_ok=True)
            self._export_frames(pose_dir)
            self.app.library.add(aid, name, self.canvas.frame_count, cw, ch)
            self.app.library.update(aid, fps=fps)
            importer.ensure_flipped(pose_dir)
            if pose != "default":
                self.app.register_pose(aid, pose, fps)
            self.anim_id = aid
            self.save_status.set_text(f"Animación «{name}» creada.")
        else:
            fd = self.app.library.frames_dir(self.anim_id)
            pose_dir = fd if pose=="default" else fd/pose
            pose_dir.mkdir(parents=True, exist_ok=True)
            self._export_frames(pose_dir)
            importer.ensure_flipped(pose_dir)
            self.app.register_pose(self.anim_id, pose, fps)
            self.save_status.set_text(f"Pose «{pose}» guardada.")

        if self.app.control: self.app.control.refresh()
        if self._guided:     self._suggest_next_pose()

    def _export_frames(self, dest):
        for i in range(self.canvas.frame_count):
            self.canvas.to_pil(i).save(dest/f"frame_{i:04d}.png")

    def _suggest_next_pose(self):
        if not self.anim_id: return
        from .. import tips
        anim = self.app.library.animations.get(self.anim_id, {})
        nxt  = tips.next_missing(anim.get("poses",[]))
        if nxt:
            self.pose_entry.set_text(nxt); self._show_tip(nxt)
        else:
            self.save_status.set_text("¡Todas las poses creadas!")

    def _show_tip(self, pose):
        from .. import tips
        info = tips.tip_for(pose)
        md   = Gtk.AlertDialog()
        md.set_message(f"Siguiente: {info['titulo']}  (~{info['frames']} cuadros)")
        md.set_detail("\n".join(f"• {t}" for t in info["tips"]))
        md.set_buttons(["Entendido"]); md.show(self)

    # ── tamaño lienzo ─────────────────────────────────────────────────────────
    def _ask_canvas_size(self):
        dlg = Gtk.Dialog(title="Tamaño del lienzo", transient_for=self, modal=True)
        dlg.set_default_size(340,230)
        box = dlg.get_content_area()
        box.set_spacing(8); box.set_margin_start(16); box.set_margin_end(16)
        box.set_margin_top(14); box.set_margin_bottom(14)

        box.append(Gtk.Label(label="Ancho (px):"))
        w_sp = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=64,lower=8,upper=512,step_increment=8))
        box.append(w_sp)
        box.append(Gtk.Label(label="Alto (px):"))
        h_sp = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=64,lower=8,upper=512,step_increment=8))
        box.append(h_sp)

        presets = Gtk.Box(spacing=4)
        for lbl,w,h in [("16²",16,16),("32²",32,32),("64²",64,64),
                         ("128²",128,128),("64×96",64,96)]:
            b = Gtk.Button(label=lbl)
            b.connect("clicked", lambda _,ww=w,hh=h: (w_sp.set_value(ww),h_sp.set_value(hh)))
            presets.append(b)
        box.append(presets)

        ok = Gtk.Button(label="Crear lienzo"); ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: self._apply_canvas_size(
            dlg, int(w_sp.get_value()), int(h_sp.get_value())))
        box.append(ok); dlg.present()
        return False

    def _apply_canvas_size(self, dlg, w, h):
        self.canvas.cw, self.canvas.ch = w, h
        self.canvas._frames = [bytearray(w*h*4)]
        self.canvas._cur = 0
        self.canvas._undo.clear(); self.canvas._redo.clear()
        self.canvas._surf_cache.clear(); self.canvas._surf_dirty = {0}
        self.canvas._update_size_req()
        self._rebuild_strip(); dlg.destroy()

    # ── exportar GIF ──────────────────────────────────────────────────────────
    def _export_gif_dialog(self):
        dlg = Gtk.FileDialog()
        dlg.set_title("Guardar como GIF")
        dlg.set_initial_name("animacion.gif")
        dlg.save(self, None, self._gif_save_done)

    def _gif_save_done(self, dlg, result):
        try: gf = dlg.save_finish(result)
        except GLib.Error: return
        path = gf.get_path()
        fps  = int(self.fps_spin.get_value()) if hasattr(self, "fps_spin") else 8
        delay_ms = max(20, 1000 // fps)
        frames = [self.canvas.to_pil(i).convert("RGBA") for i in range(self.canvas.frame_count)]
        if not frames: return
        frames[0].save(
            path, format="GIF", save_all=True, append_images=frames[1:],
            loop=0, duration=delay_ms, disposal=2)
        self.save_status.set_text(f"GIF guardado: {Path(path).name}")

    def _draw_swatch_checker(self, cr, w, h):
        sq = 4
        for y in range(0,h,sq):
            for x in range(0,w,sq):
                v = 0.8 if (x//sq+y//sq)%2==0 else 0.6
                cr.set_source_rgb(v,v,v); cr.rectangle(x,y,sq,sq); cr.fill()
