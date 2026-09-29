"""
Vista de trabajo del editor de animación (estilo Toon Boom Harmony).

  * Vista «Dibujo» (editable) y vista «Cámara» (con la cámara animada).
  * Papel cebolla rojo/azul, mesa de luz, cuadrícula, guías de simetría, vista espejo.
  * Herramientas: seleccionar, editor de contorno, pincel, lápiz, borrador, dedo,
    pintar (bote con cierre de huecos), degradado, cuentagotas, línea, rectángulo,
    elipse, polilínea, lazo, mano, zoom y cámara.
  * Capas raster (píxeles) y vectoriales (trazos editables).
"""
import math

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

import cairo
import numpy as np
from PIL import Image

from . import anim_engine as ae

ZOOM_MIN, ZOOM_MAX = 0.05, 32.0
VIEW_BG = (0.50, 0.50, 0.50)

RASTER_PAINT = ("brush", "pencil", "smudge")
SHAPES = ("line", "rect", "ellipse", "polyline")


def rdp(pts, eps):
    """Ramer–Douglas–Peucker: simplifica un trazo conservando su forma."""
    if len(pts) < 3: return list(pts)
    a, b = pts[0], pts[-1]
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = ae.seg_dist(pts[i][0], pts[i][1], a[0], a[1], b[0], b[1])
        if d > dmax: dmax, idx = d, i
    if dmax > eps:
        left = rdp(pts[:idx + 1], eps); right = rdp(pts[idx:], eps)
        return left[:-1] + right
    return [a, b]


def ellipse_pts(x0, y0, x1, y1, n=36):
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0) / 2, abs(y1 - y0) / 2
    return [(cx + rx * math.cos(2 * math.pi * k / n), cy + ry * math.sin(2 * math.pi * k / n), 1.0)
            for k in range(n)]


def sel_segments(mask):
    segs = []
    pad = np.pad(mask, 1)
    hz = pad[1:, 1:-1] != pad[:-1, 1:-1]
    vt = pad[1:-1, 1:] != pad[1:-1, :-1]
    for y in range(hz.shape[0]):
        xs = np.flatnonzero(hz[y])
        if xs.size:
            start = prev = xs[0]
            for x in xs[1:]:
                if x != prev + 1: segs.append((start, y, prev + 1, y)); start = x
                prev = x
            segs.append((start, y, prev + 1, y))
    for x in range(vt.shape[1]):
        ys = np.flatnonzero(vt[:, x])
        if ys.size:
            start = prev = ys[0]
            for y in ys[1:]:
                if y != prev + 1: segs.append((x, start, x, prev + 1)); start = y
                prev = y
            segs.append((x, start, x, prev + 1))
    return segs


class AnimCanvas(Gtk.DrawingArea):
    def __init__(self, scene=None):
        super().__init__()
        self.scene = scene or ae.Scene(512, 512)
        self.cur = 0
        self.li = 0                      # capa activa
        self.tool = "brush"
        self.fg = (0, 0, 0, 255)
        self.bg = (255, 255, 255, 255)
        self.props = dict(
            brush_kind="round", brush_size=14.0, hardness=0.6, opacity=255, spacing=0.14,
            smoothing=0.35, pressure_size=True, pressure_opacity=False,
            pencil_size=3.0, eraser_size=24.0, smudge_size=28.0,
            fill_tol=32, fill_gap=3, fill_all=False, fill_contig=True,
            shape_fill=False, shape_width=3.0, grad_radial=False, dropper_all=True,
        )
        # vista
        self.mode = "draw"               # draw | camera
        self.onion = False
        self.onion_prev, self.onion_next = 2, 2
        self.light_table = False
        self.show_grid = False
        self.grid_size = 32
        self.symmetry = "none"
        self.mirror_view = False
        self.paper = False
        self.safe_area = False
        self._z, self._ox, self._oy = 1.0, 0.0, 0.0
        self._fit_pending = True
        self._sticky_fit = False       # tras ajustar, se reajusta al cambiar el tamaño de la ventana
        self._fit_size = (0, 0)
        self._mouse = (0.0, 0.0)
        self._cursor_c = None
        self._space = False
        self._panning = False
        self._pan_origin = (0, 0)
        self._pressure = 1.0
        self._stylus = False

        # selección raster / vector
        self.sel = None
        self._sel_segs = None
        self._ants = 0.0
        self._clip = None
        self.vsel = set()
        self._vpoint = None

        # gesto
        self._drawing = False
        self._tool_now = "brush"
        self._btn = 1
        self._start = (0.0, 0.0)
        self._painters = []
        self._created = False
        self._base = None
        self._poly = []
        self._lasso = []
        self._shape_end = (0, 0)
        self._mv = None
        self._cam_start = None

        # callbacks
        self.on_pick = None
        self.on_frame = None
        self.on_layers = None
        self.on_cursor = None
        self.on_zoom = None
        self.on_status = None
        self.on_tool = None
        self.on_edit = None              # se llama al terminar cualquier cambio

        self.set_draw_func(self._draw)
        self.set_focusable(True)
        self.set_hexpand(True); self.set_vexpand(True)
        self.set_size_request(320, 240)
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self._cursor()

        d = Gtk.GestureDrag(); d.set_button(0)
        d.connect("drag-begin", self._drag_begin)
        d.connect("drag-update", self._drag_update)
        d.connect("drag-end", self._drag_end)
        self.add_controller(d); self._g = d
        d2 = Gtk.GestureDrag(); d2.set_button(2)
        d2.connect("drag-begin", lambda g, x, y: self._pan_begin())
        d2.connect("drag-update", lambda g, dx, dy: self._pan_update(dx, dy))
        d2.connect("drag-end", lambda g, dx, dy: self._pan_end())
        self.add_controller(d2)
        mo = Gtk.EventControllerMotion()
        mo.connect("motion", self._motion); mo.connect("leave", self._leave)
        self.add_controller(mo)
        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        sc.connect("scroll", self._scroll)
        self.add_controller(sc)
        leg = Gtk.EventControllerLegacy(); leg.connect("event", self._legacy)
        self.add_controller(leg)
        self._ants_id = None
        self.connect("map", self._start_ants); self.connect("unmap", self._stop_ants)

    # ══ utilidades ════════════════════════════════════════════════════════════
    @property
    def layer(self):
        return self.scene.layers[max(0, min(self.li, len(self.scene.layers) - 1))]

    def _status(self, m):
        if self.on_status: self.on_status(m)

    def _changed(self, layers=False):
        if self.on_frame: self.on_frame()
        if layers and self.on_layers: self.on_layers()
        if self.on_edit: self.on_edit()
        self.queue_draw()

    def _cursor(self):
        t = self._tool_now if self._drawing else self.tool
        name = {"hand": "grab", "zoom": "zoom-in", "select": "default", "contour": "default",
                "camera": "move"}.get(t, "crosshair")
        if self._panning: name = "grabbing"
        elif self._space: name = "grab"
        self.set_cursor(Gdk.Cursor.new_from_name(name))

    def set_tool(self, tool):
        if self._poly and tool != "polyline": self._finish_poly()
        self.tool = tool; self._cursor(); self.queue_draw()

    def set_space(self, on):
        if on != self._space:
            self._space = on; self._cursor()

    def _legacy(self, ctrl, event):
        try:
            if event is None: return False
            t = event.get_event_type()
            if t in (Gdk.EventType.MOTION_NOTIFY, Gdk.EventType.BUTTON_PRESS):
                ok, val = event.get_axis(Gdk.AxisUse.PRESSURE)
                self._stylus = bool(ok)
                self._pressure = float(val) if ok and val > 0 else 1.0
        except Exception:  # noqa: BLE001
            pass
        return False

    # ══ vista ═════════════════════════════════════════════════════════════════
    def _s2c(self, sx, sy):
        x = (sx - self._ox) / self._z
        if self.mirror_view: x = self.scene.w - x
        return x, (sy - self._oy) / self._z

    def _c2s(self, x, y):
        if self.mirror_view: x = self.scene.w - x
        return self._ox + x * self._z, self._oy + y * self._z

    def zoom_at(self, factor, sx=None, sy=None):
        if sx is None: sx, sy = self.get_width() / 2, self.get_height() / 2
        cx, cy = self._s2c(sx, sy)
        z = max(ZOOM_MIN, min(ZOOM_MAX, self._z * factor))
        if z == self._z: return
        self._z = z
        x = (self.scene.w - cx) if self.mirror_view else cx
        self._ox, self._oy = sx - x * z, sy - cy * z
        self._fit_pending = False; self._sticky_fit = False
        self.queue_draw()
        if self.on_zoom: self.on_zoom()

    def zoom_to(self, z):
        self.zoom_at(z / self._z)

    def zoom_fit(self):
        w, h = self.get_width(), self.get_height()
        if w <= 0 or h <= 0:
            self._fit_pending = True; return
        s = self.scene
        self._z = min((w - 40) / s.w, (h - 40) / s.h)
        self._z = max(ZOOM_MIN, min(ZOOM_MAX, self._z))
        self._ox, self._oy = (w - s.w * self._z) / 2, (h - s.h * self._z) / 2
        self._fit_pending = False; self._sticky_fit = True; self._fit_size = (w, h)
        self.queue_draw()
        if self.on_zoom: self.on_zoom()

    def _pan_begin(self):
        self._panning = True; self._pan_origin = (self._ox, self._oy); self._cursor()

    def _pan_update(self, dx, dy):
        if self._panning:
            self._ox, self._oy = self._pan_origin[0] + dx, self._pan_origin[1] + dy
            self._fit_pending = False; self._sticky_fit = False; self.queue_draw()

    def _pan_end(self):
        self._panning = False; self._cursor()

    def _scroll(self, ctrl, dx, dy):
        mods = ctrl.get_current_event_state()
        touchpad = ctrl.get_unit() == Gdk.ScrollUnit.SURFACE
        if touchpad and not (mods & Gdk.ModifierType.CONTROL_MASK):
            self._ox -= dx; self._oy -= dy; self._fit_pending = False; self._sticky_fit = False; self.queue_draw(); return True
        if self.tool == "camera" and self.mode == "camera":
            self._cam_edit(scale_mul=1.05 if dy < 0 else 1 / 1.05); return True
        f = 1 / 1.15 if dy > 0 else 1.15
        self.zoom_at(f, *self._mouse)
        return True

    # ══ navegación / capas / fotogramas ═══════════════════════════════════════
    def go_to(self, f):
        f = max(0, min(f, 1999))
        if f >= self.scene.frame_count:            # avanzar más allá del final amplía la escena
            self.scene.ensure_frames(f + 1)
        if f != self.cur:
            self._commit_move()
        self.cur = f
        self.queue_draw()
        if self.on_frame: self.on_frame()

    def set_layer(self, i):
        self.li = max(0, min(i, len(self.scene.layers) - 1))
        self.vsel.clear(); self._vpoint = None
        self.queue_draw()
        if self.on_layers: self.on_layers()

    def _after_struct(self, layers=True):
        self.li = max(0, min(self.li, len(self.scene.layers) - 1))
        self.cur = max(0, min(self.cur, self.scene.frame_count - 1))
        self.vsel.clear(); self._vpoint = None
        self._changed(layers)

    def _step_history(self, fn):
        size = (self.scene.w, self.scene.h)
        if fn():
            if (self.scene.w, self.scene.h) != size:
                self.sel = None; self._sel_segs = None; self._fit_pending = True
            self._after_struct()

    def undo(self): self._step_history(self.scene.undo)
    def redo(self): self._step_history(self.scene.redo)

    def load_scene(self, scene):
        self.scene = scene; self.cur = 0; self.li = 0
        self.sel = None; self._sel_segs = None; self.vsel.clear()
        self._fit_pending = True
        self._changed(True)

    def new_scene(self, w, h, fps=12):
        self.load_scene(ae.Scene(w, h, fps))

    # capas
    def add_layer(self, kind="raster"):
        self.li = self.scene.add_layer(kind, above=self.li); self._after_struct()

    def remove_layer(self):
        if self.scene.remove_layer(self.li): self._after_struct()
        else: self._status("No se puede borrar la única capa")

    def duplicate_layer(self):
        self.li = self.scene.duplicate_layer(self.li); self._after_struct()

    def move_layer(self, d):
        self.li = self.scene.move_layer(self.li, d); self._after_struct()

    def merge_down(self):
        if self.scene.merge_down(self.li):
            self.li -= 1; self._after_struct()
        else: self._status("Solo se pueden unir dos capas de dibujo")

    # fotogramas / exposición
    def new_drawing_here(self):
        self.scene.new_drawing(self.li, self.cur); self._after_struct(False)

    def duplicate_drawing_here(self):
        if self.scene.duplicate_drawing(self.li, self.cur) is None:
            self._status("La celda está vacía")
        self._after_struct(False)

    def extend_exposure(self, n=1):
        f = self.cur
        if self.layer.drawing_index_at(f) < 0:
            self._status("Dibuja algo en la celda antes de extenderla"); return
        self.scene.extend_exposure(self.li, f, f + n)
        self.cur = min(self.cur + n, self.scene.frame_count - 1)
        self._after_struct(False)

    def clear_cell(self):
        self.scene.clear_cell(self.li, self.cur); self._after_struct(False)

    def insert_frame(self):
        self.scene.insert_frames(self.cur + 1, 1); self.cur += 1; self._after_struct(False)

    def delete_frame(self):
        if self.scene.delete_frames(self.cur, 1): self._after_struct(False)
        else: self._status("La escena necesita al menos un fotograma")

    def _cur_drawing(self, create=False):
        d = self.layer.at(self.cur)
        if d is None and create:
            d = self.scene.new_drawing(self.li, self.cur); self._created = True
        return d

    def _blocked(self):
        l = self.layer
        if l.locked: self._status("La capa está bloqueada"); return True
        if not l.visible: self._status("La capa está oculta"); return True
        return False

    # ══ entrada ═══════════════════════════════════════════════════════════════
    def _drag_begin(self, g, sx, sy):
        btn = g.get_current_button()
        mods = g.get_current_event_state()
        self.grab_focus()
        alt = bool(mods & Gdk.ModifierType.ALT_MASK)
        shift = bool(mods & Gdk.ModifierType.SHIFT_MASK)
        ctrl = bool(mods & Gdk.ModifierType.CONTROL_MASK)
        if btn == 2 or self._space or self.tool == "hand":
            self._pan_begin(); return
        self._btn = btn; self._start = (sx, sy)
        cx, cy = self._s2c(sx, sy)
        self._shift, self._alt, self._ctrl = shift, alt, ctrl
        tool = self.tool
        if alt and tool not in ("select", "contour", "lasso", "camera"): tool = "dropper"
        self._tool_now = tool
        self._drawing = True
        self._created = False
        if tool == "zoom":
            self.zoom_at(1 / 1.5 if (btn == 3 or alt) else 1.5, sx, sy); self._drawing = False; return
        if tool == "dropper":
            self._dropper(cx, cy, btn == 3); self._drawing = False; return
        if tool == "camera":
            self._cam_begin(cx, cy); return
        if self.mode == "camera":
            self._status("Cambia a la vista «Dibujo» para dibujar"); self._drawing = False; return
        if tool == "polyline":
            self._poly_click(cx, cy, g); return
        if tool in ("select", "contour", "lasso"):
            self._select_begin(cx, cy, tool); return
        if self._blocked():
            self._drawing = False; return
        fg = self.bg if btn == 3 else self.fg
        self._col = fg
        if tool == "eraser":
            self._eraser_begin(cx, cy); return
        if tool in ("brush", "pencil", "smudge"):
            self._stroke_begin(cx, cy, tool); return
        if tool == "paint":
            self._paint_bucket(cx, cy); self._drawing = False; return
        if tool in ("line", "rect", "ellipse", "gradient"):
            self._shape_begin(cx, cy, tool); return

    def _drag_update(self, g, dx, dy):
        if self._panning:
            self._pan_update(dx, dy); return
        if not self._drawing: return
        sx, sy = self._start[0] + dx, self._start[1] + dy
        cx, cy = self._s2c(sx, sy)
        tool = self._tool_now
        if tool in ("brush", "pencil", "smudge") and self._painters:
            self._stroke_move(cx, cy)
        elif tool == "eraser":
            self._eraser_move(cx, cy)
        elif tool in ("line", "rect", "ellipse", "gradient"):
            self._shape_move(cx, cy)
        elif tool in ("select", "contour", "lasso"):
            self._select_move(cx, cy, tool)
        elif tool == "camera":
            self._cam_move(cx, cy)
        elif tool == "polyline":
            self._shape_end = (cx, cy); self.queue_draw()

    def _drag_end(self, g, dx, dy):
        if self._panning:
            self._pan_end(); return
        if not self._drawing: return
        sx, sy = self._start[0] + dx, self._start[1] + dy
        cx, cy = self._s2c(sx, sy)
        tool = self._tool_now
        try:
            if tool in ("brush", "pencil", "smudge") and self._painters:
                self._stroke_end(cx, cy)
            elif tool == "eraser":
                self._eraser_end()
            elif tool in ("line", "rect", "ellipse", "gradient"):
                self._shape_end_(cx, cy)
            elif tool in ("select", "contour", "lasso"):
                self._select_end(cx, cy, tool)
            elif tool == "camera":
                self._cam_end()
        finally:
            self._drawing = False; self._cursor(); self.queue_draw()

    def _motion(self, ctrl, sx, sy):
        self._mouse = (sx, sy)
        c = self._s2c(sx, sy)
        self._cursor_c = c
        if self.tool == "polyline" and self._poly:
            self._shape_end = c
        self.queue_draw()
        if self.on_cursor: self.on_cursor(c[0], c[1])

    def _leave(self, ctrl):
        self._cursor_c = None; self.queue_draw()

    # ══ raster: pincel / lápiz / dedo ═════════════════════════════════════════
    def _tool_params(self, tool):
        p = self.props
        if tool == "pencil": return "pencil", p["pencil_size"], 1.0
        if tool == "smudge": return "round", p["smudge_size"], p["hardness"]
        return p["brush_kind"], p["brush_size"], p["hardness"]

    def _sym_maps(self):
        W, H = self.scene.w - 1, self.scene.h - 1
        maps = [lambda x, y: (x, y)]
        if self.symmetry in ("h", "hv"): maps.append(lambda x, y: (W - x, y))
        if self.symmetry in ("v", "hv"): maps.append(lambda x, y: (x, H - y))
        if self.symmetry == "hv": maps.append(lambda x, y: (W - x, H - y))
        return maps

    def _stroke_begin(self, cx, cy, tool, erase=False, kind=None, size=None):
        layer = self.layer
        if layer.kind == "vector":
            self._vstroke_begin(cx, cy, tool); return
        d = self._cur_drawing(create=True)
        self.scene.begin_edit(d)
        self._drawing_ref = d
        k, sz, hard = self._tool_params(tool)
        if kind: k = kind
        if size: sz = size
        p = self.props
        self._painters = []
        self._maps = self._sym_maps()
        pr = self._pressure if self._stylus else 1.0
        for m in self._maps:
            sp = ae.StrokePainter(
                d, k, sz, hard, p["opacity"], self._col, erase=erase, alpha_lock=layer.alpha_locked,
                smudge=(tool == "smudge"), smoothing=p["smoothing"] if tool != "smudge" else 0.0,
                spacing=p["spacing"], pressure_size=p["pressure_size"] and self._stylus,
                pressure_opacity=p["pressure_opacity"] and self._stylus)
            self._painters.append(sp)
        self._dab_all(cx, cy, pr)

    def _dab_all(self, cx, cy, pr, final=False):
        for m, sp in zip(self._maps, self._painters):
            x, y = m(cx, cy)
            sp.add(x, y, pr)
        self.queue_draw()

    def _stroke_move(self, cx, cy):
        if self.layer.kind == "vector": self._vstroke_move(cx, cy); return
        self._dab_all(cx, cy, self._pressure if self._stylus else 1.0)

    def _stroke_end(self, cx, cy):
        if self.layer.kind == "vector": self._vstroke_end(cx, cy); return
        pr = self._pressure if self._stylus else 1.0
        for m, sp in zip(self._maps, self._painters):
            x, y = m(cx, cy)
            sp.finish(x, y, pr)
        self._painters = []
        self.scene.end_edit(record=not self._created)
        self._changed(self._created)

    # ── borrador ─────────────────────────────────────────────────────────────
    def _eraser_begin(self, cx, cy):
        if self.layer.kind == "vector":
            d = self._cur_drawing()
            if d is None: self._drawing = False; return
            self.scene.begin_edit(d); self._drawing_ref = d
            self._vec_erase(cx, cy); return
        if self.layer.at(self.cur) is None:
            self._drawing = False; return
        self._stroke_begin(cx, cy, "brush", erase=True, kind="round", size=self.props["eraser_size"])

    def _eraser_move(self, cx, cy):
        if self.layer.kind == "vector":
            if getattr(self, "_drawing_ref", None) is not None: self._vec_erase(cx, cy)
        elif self._painters:
            self._dab_all(cx, cy, 1.0)

    def _eraser_end(self):
        if self.layer.kind == "vector":
            if getattr(self, "_drawing_ref", None) is not None:
                self.scene.end_edit(); self._drawing_ref = None; self._changed()
        elif self._painters:
            x, y = self._s2c(*self._mouse)
            for m, sp in zip(self._maps, self._painters): sp.finish(*m(x, y))
            self._painters = []; self.scene.end_edit(record=not self._created); self._changed()

    def _vec_erase(self, cx, cy):
        d = self._drawing_ref
        r = self.props["eraser_size"] / 2
        keep = [s for s in d.strokes if not ae.stroke_hit(s, cx, cy, r)]
        if len(keep) != len(d.strokes):
            d.strokes[:] = keep; d.touch(); self.queue_draw()

    # ══ vectorial ═════════════════════════════════════════════════════════════
    def _vstroke_begin(self, cx, cy, tool):
        d = self._cur_drawing(create=True)
        self.scene.begin_edit(d); self._drawing_ref = d
        p = self.props
        w = p["pencil_size"] if tool == "pencil" else p["brush_size"]
        col = tuple(self._col)
        pr = self._pressure if self._stylus else 1.0
        self._vst = {"pts": [(cx, cy, pr)], "color": col, "width": float(w), "closed": False, "fill": None,
                     "_raw": [(cx, cy, pr)]}
        d.strokes.append(self._vst); d.touch()
        self._lazy = (cx, cy)
        self._painters = [None]          # marca que hay trazo en curso
        self.queue_draw()

    def _vstroke_move(self, cx, cy):
        s = self.props["smoothing"]
        lx, ly = self._lazy
        self._lazy = (lx + (cx - lx) * (1 - s * 0.85), ly + (cy - ly) * (1 - s * 0.85))
        x, y = self._lazy
        pr = self._pressure if self._stylus else 1.0
        last = self._vst["_raw"][-1]
        if math.hypot(x - last[0], y - last[1]) >= 1.5:
            self._vst["_raw"].append((x, y, pr)); self._vst["pts"] = list(self._vst["_raw"])
            self._drawing_ref.touch(); self.queue_draw()

    def _vstroke_end(self, cx, cy):
        st = self._vst
        raw = st.pop("_raw")
        raw.append((cx, cy, self._pressure if self._stylus else 1.0))
        eps = 0.6 + self.props["smoothing"] * 2.2
        st["pts"] = rdp(raw, eps) if len(raw) > 2 else raw
        if len(st["pts"]) == 2 and math.hypot(st["pts"][0][0] - st["pts"][1][0],
                                             st["pts"][0][1] - st["pts"][1][1]) < 1.2:
            st["pts"] = st["pts"][:1]
        self._drawing_ref.touch()
        self._painters = []
        self.scene.end_edit(record=not self._created)
        self._changed(self._created)

    def _vec_drawing(self):
        d = self.layer.at(self.cur)
        return d if (d is not None and d.kind == "vector") else None

    # ══ pintar (bote) ═════════════════════════════════════════════════════════
    def _sample_array(self):
        if self.props["fill_all"]:
            return self.scene.flatten_frame(self.cur)
        d = self.layer.at(self.cur)
        return d.rgba() if d is not None else np.zeros((self.scene.h, self.scene.w, 4), np.uint8)

    def _paint_bucket(self, cx, cy):
        col = self._col
        if self.layer.kind == "vector":
            d = self._vec_drawing()
            if d is None: return
            for s in reversed(d.strokes):
                if s.get("closed") and ae.point_in_poly(s["pts"], cx, cy):
                    self.scene.begin_edit(d); s["fill"] = tuple(col); d.touch()
                    self.scene.end_edit(); self._changed(); return
            self._status("Haz clic dentro de una forma cerrada"); return
        x, y = int(cx), int(cy)
        p = self.props
        region = ae.flood_region(self._sample_array(), x, y, p["fill_tol"], p["fill_contig"], p["fill_gap"])
        if region is None: return
        if self.sel is not None: region &= self.sel
        d = self._cur_drawing(create=True)
        self.scene.begin_edit(d)
        bbox = ae.fill_behind(d.arr, region, col, p["opacity"], grow=1)
        if bbox: d.refresh(*bbox)
        self.scene.end_edit(record=not self._created)
        self._changed(self._created)

    def _dropper(self, cx, cy, right):
        x, y = int(cx), int(cy)
        if not (0 <= x < self.scene.w and 0 <= y < self.scene.h): return
        arr = self.scene.flatten_frame(self.cur) if self.props["dropper_all"] else self._sample_array()
        c = tuple(int(v) for v in arr[y, x])
        if self.on_pick: self.on_pick(c, right)

    # ══ formas / degradado ════════════════════════════════════════════════════
    def _shape_begin(self, cx, cy, tool):
        self._sh0 = (cx, cy); self._shape_end = (cx, cy)
        if self.layer.kind == "vector" and tool == "gradient":
            self._status("El degradado solo funciona en capas de dibujo"); self._drawing = False; return
        if self.layer.kind == "raster":
            d = self._cur_drawing(create=True)
            self.scene.begin_edit(d); self._drawing_ref = d
            self._base = d.arr.copy()
        else:
            d = self._cur_drawing(create=True)
            self.scene.begin_edit(d); self._drawing_ref = d
        self.queue_draw()

    def _shape_pts(self, tool, x0, y0, x1, y1, shift):
        if shift:
            dx, dy = x1 - x0, y1 - y0
            if tool == "line":
                ax, ay = abs(dx), abs(dy)
                if ax > 2 * ay: y1 = y0
                elif ay > 2 * ax: x1 = x0
                else:
                    m = max(ax, ay); x1 = x0 + math.copysign(m, dx); y1 = y0 + math.copysign(m, dy)
            else:
                m = max(abs(dx), abs(dy)); x1 = x0 + math.copysign(m, dx); y1 = y0 + math.copysign(m, dy)
        return x1, y1

    def _shape_move(self, cx, cy):
        d = self._drawing_ref
        x0, y0 = self._sh0; tool = self._tool_now
        x1, y1 = self._shape_pts(tool, x0, y0, cx, cy, self._shift_now())
        self._shape_end = (x1, y1)
        if d.kind == "raster":
            d.arr[:] = self._base
            self._raster_shape(d, tool, x0, y0, x1, y1)
            d.refresh(0, 0, d.w, d.h)
        self.queue_draw()

    def _shift_now(self):
        return bool(self._g.get_current_event_state() & Gdk.ModifierType.SHIFT_MASK)

    def _raster_shape(self, d, tool, x0, y0, x1, y1):
        p = self.props; col = self._col
        if tool == "gradient":
            g = ae.gradient_array(d.w, d.h, (x0, y0), (x1, y1), self.fg, self.bg, p["grad_radial"])
            mask = self.sel if self.sel is not None else np.ones((d.h, d.w), bool)
            op = p["opacity"] / 255.0
            cur = d.arr.astype(np.float32)
            new = cur * (1 - op) + g.astype(np.float32) * op
            d.arr[mask] = np.clip(new[mask] + 0.5, 0, 255).astype(np.uint8)
            return None
        cov = ae.shape_coverage(d.w, d.h, tool, [(x0, y0), (x1, y1)], p["shape_width"], p["shape_fill"])
        if self.sel is not None: cov = cov * self.sel
        for m in self._sym_maps():
            if m(1, 1) == (1, 1): c = cov
            else:
                c = ae.shape_coverage(d.w, d.h, tool, [m(x0, y0), m(x1, y1)], p["shape_width"], p["shape_fill"])
            ae.paint_mask(d.arr, c, col, p["opacity"])
        return None

    def _shape_end_(self, cx, cy):
        d = self._drawing_ref
        x0, y0 = self._sh0; tool = self._tool_now
        x1, y1 = self._shape_pts(tool, x0, y0, cx, cy, self._shift_now())
        p = self.props
        if d.kind == "raster":
            d.arr[:] = self._base
            self._raster_shape(d, tool, x0, y0, x1, y1)
            d.refresh(0, 0, d.w, d.h)
            self._base = None
        else:
            col = tuple(self._col)
            fill = tuple(col) if p["shape_fill"] else None
            if tool == "line":
                st = {"pts": [(x0, y0, 1.0), (x1, y1, 1.0)], "closed": False, "fill": None}
            elif tool == "rect":
                st = {"pts": [(x0, y0, 1.0), (x1, y0, 1.0), (x1, y1, 1.0), (x0, y1, 1.0)], "closed": True, "fill": fill}
            else:
                st = {"pts": ellipse_pts(x0, y0, x1, y1), "closed": True, "fill": fill}
            st.update(color=col, width=float(p["shape_width"]))
            d.strokes.append(st); d.touch()
        self.scene.end_edit(record=not self._created)
        self._drawing_ref = None
        self._changed(self._created)

    # polilínea ---------------------------------------------------------------
    def _poly_click(self, cx, cy, g):
        if self.layer.kind == "raster" and self._blocked(): self._drawing = False; return
        self._poly.append((cx, cy)); self._shape_end = (cx, cy)
        self._drawing = False
        self.queue_draw()

    def _finish_poly(self, close=False):
        pts = self._poly; self._poly = []
        if len(pts) < 2: self.queue_draw(); return
        if self._blocked(): return
        p = self.props; col = tuple(self.fg)
        d = self._cur_drawing(create=True); created = self._created
        self.scene.begin_edit(d)
        if d.kind == "vector":
            d.strokes.append({"pts": [(x, y, 1.0) for x, y in pts], "color": col, "width": float(p["shape_width"]),
                              "closed": close, "fill": col if (close and p["shape_fill"]) else None})
            d.touch()
        else:
            self._col = self.fg
            cov = ae.shape_coverage(d.w, d.h, "poly", pts, p["shape_width"], p["shape_fill"] and close, close)
            ae.paint_mask(d.arr, cov, col, p["opacity"])
            d.refresh(0, 0, d.w, d.h)
        self.scene.end_edit(record=not created)
        self._changed(created)

    def finish_polyline(self, close=False):
        if self._poly: self._finish_poly(close)

    # ══ selección / contorno ══════════════════════════════════════════════════
    def _select_begin(self, cx, cy, tool):
        self._sx0, self._sy0 = cx, cy
        if self.layer.kind == "vector":
            self._vselect_begin(cx, cy, tool); return
        if tool == "lasso":
            self._lasso = [(cx, cy)]; self._set_sel(None); return
        if self.sel is not None and 0 <= int(cy) < self.scene.h and 0 <= int(cx) < self.scene.w \
                and self.sel[int(cy), int(cx)] and not self._blocked():
            d = self._cur_drawing()
            if d is not None:
                self.scene.begin_edit(d); self._drawing_ref = d
                self._begin_move(d); self._mvstart = (cx, cy); self._mode = "move"; return
        self._mode = "marquee"; self._set_sel(None)

    def _select_move(self, cx, cy, tool):
        if self.layer.kind == "vector":
            self._vselect_move(cx, cy, tool); return
        if tool == "lasso":
            self._lasso.append((cx, cy)); self._lasso_mask(); return
        if getattr(self, "_mode", "") == "move":
            self._move_by(int(round(cx - self._mvstart[0])), int(round(cy - self._mvstart[1]))); return
        x0, y0 = self._sx0, self._sy0
        m = np.zeros((self.scene.h, self.scene.w), bool)
        xa, xb = max(0, int(min(x0, cx))), min(self.scene.w - 1, int(max(x0, cx)))
        ya, yb = max(0, int(min(y0, cy))), min(self.scene.h - 1, int(max(y0, cy)))
        if xb >= xa and yb >= ya: m[ya:yb + 1, xa:xb + 1] = True
        self._set_sel(m)

    def _select_end(self, cx, cy, tool):
        if self.layer.kind == "vector":
            self._vselect_end(cx, cy, tool); return
        if tool == "lasso": self._lasso_mask(); self._lasso = []
        elif getattr(self, "_mode", "") == "move":
            self._mv = None
            self.scene.end_edit(); self._drawing_ref = None; self._changed()

    def _lasso_mask(self):
        m = np.zeros((self.scene.h, self.scene.w), bool)
        if len(self._lasso) >= 3:
            im = Image.new("L", (self.scene.w, self.scene.h), 0)
            from PIL import ImageDraw
            ImageDraw.Draw(im).polygon([(x, y) for x, y in self._lasso], fill=255)
            m = np.asarray(im) > 0
        self._set_sel(m)

    def _set_sel(self, mask):
        self.sel = mask if (mask is not None and mask.any()) else None
        self._sel_segs = None; self.queue_draw()

    def select_all(self):
        if self.layer.kind == "vector":
            d = self._vec_drawing()
            self.vsel = set(range(len(d.strokes))) if d else set(); self.queue_draw(); return
        self._set_sel(np.ones((self.scene.h, self.scene.w), bool))

    def deselect(self):
        self._commit_move(); self.vsel.clear(); self._vpoint = None; self._set_sel(None)

    def invert_selection(self):
        if self.layer.kind != "raster": return
        self._set_sel(~self.sel if self.sel is not None else np.ones((self.scene.h, self.scene.w), bool))

    def _commit_move(self):
        self._mv = None

    def _sel_bbox(self):
        if self.sel is None: return None
        ys, xs = np.nonzero(self.sel)
        return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

    def _begin_move(self, d):
        base = d.arr.copy()
        x0, y0, x1, y1 = self._sel_bbox()
        m = self.sel[y0:y1 + 1, x0:x1 + 1].copy()
        img = base[y0:y1 + 1, x0:x1 + 1].copy(); img[~m] = 0
        self._mv = dict(d=d, base=base, sel=self.sel.copy(), img=img, m=m, bb=(x0, y0, x1, y1))

    def _move_by(self, dx, dy):
        mv = self._mv
        if not mv: return
        d, base = mv["d"], mv["base"]
        new = base.copy(); new[mv["sel"]] = 0
        x0, y0, x1, y1 = mv["bb"]; img, m = mv["img"], mv["m"]
        h, w = m.shape
        tx, ty = x0 + dx, y0 + dy
        cx1, cy1, cx2, cy2 = max(0, tx), max(0, ty), min(d.w, tx + w), min(d.h, ty + h)
        nm = np.zeros((d.h, d.w), bool)
        if cx2 > cx1 and cy2 > cy1:
            sub = img[cy1 - ty:cy2 - ty, cx1 - tx:cx2 - tx]; sm = m[cy1 - ty:cy2 - ty, cx1 - tx:cx2 - tx]
            reg = new[cy1:cy2, cx1:cx2]
            put = sm & (sub[..., 3] > 0)
            reg[put] = sub[put]
            nm[cy1:cy2, cx1:cx2] = sm
        d.arr[:] = new; d.refresh(0, 0, d.w, d.h)
        self._set_sel(nm)

    def clear_selection(self):
        if self.layer.kind == "vector":
            d = self._vec_drawing()
            if d and self.vsel:
                self.scene.begin_edit(d)
                d.strokes[:] = [s for i, s in enumerate(d.strokes) if i not in self.vsel]
                d.touch(); self.vsel.clear(); self.scene.end_edit(); self._changed()
            return
        d = self._cur_drawing()
        if d is None or self._blocked(): return
        self.scene.begin_edit(d)
        if self.sel is None: d.arr[:] = 0
        else: d.arr[self.sel] = 0
        d.refresh(0, 0, d.w, d.h); self.scene.end_edit(); self._changed()

    def copy_selection(self, cut=False):
        d = self._cur_drawing()
        if d is None or self.layer.kind != "raster": return
        bb = self._sel_bbox() or (0, 0, d.w - 1, d.h - 1)
        m = self.sel if self.sel is not None else np.ones((d.h, d.w), bool)
        x0, y0, x1, y1 = bb
        img = d.arr[y0:y1 + 1, x0:x1 + 1].copy(); mm = m[y0:y1 + 1, x0:x1 + 1].copy(); img[~mm] = 0
        self._clip = (img, mm, x0, y0)
        if cut: self.clear_selection()

    def paste_selection(self):
        if not self._clip or self.layer.kind != "raster" or self._blocked(): return
        img, mm, x0, y0 = self._clip
        if x0 >= self.scene.w or y0 >= self.scene.h:
            self._status("Lo copiado ya no cabe en la escena"); return
        d = self._cur_drawing(create=True); created = self._created
        self.scene.begin_edit(d)
        h, w = mm.shape
        y1, x1 = min(d.h, y0 + h), min(d.w, x0 + w)
        if y1 <= y0 or x1 <= x0:
            self._status("Lo copiado ya no cabe en la escena"); return
        sub, sm = img[:y1 - y0, :x1 - x0], mm[:y1 - y0, :x1 - x0]
        reg = d.arr[y0:y1, x0:x1]; put = sm & (sub[..., 3] > 0); reg[put] = sub[put]
        d.refresh(0, 0, d.w, d.h)
        self.scene.end_edit(record=not created)
        m = np.zeros((d.h, d.w), bool); m[y0:y1, x0:x1] = sm; self._set_sel(m)
        self._changed(created)
        if self.on_tool: self.on_tool("select")

    def flip_drawing(self, horizontal):
        d = self._cur_drawing()
        if d is None or self._blocked(): return
        self.scene.begin_edit(d)
        if d.kind == "raster":
            d.arr[:] = d.arr[:, ::-1] if horizontal else d.arr[::-1]; d.refresh(0, 0, d.w, d.h)
        else:
            W, H = self.scene.w, self.scene.h
            for s in d.strokes:
                s["pts"] = [((W - p[0]) if horizontal else p[0], p[1] if horizontal else (H - p[1]), *p[2:])
                            for p in s["pts"]]
            d.touch()
        self.scene.end_edit(); self._changed()

    def rotate_drawing(self, deg):
        """Gira el dibujo 90/180° (solo raster cuadrado o 180°)."""
        d = self._cur_drawing()
        if d is None or self._blocked(): return
        if d.kind != "raster": self._status("Solo para capas de dibujo"); return
        if deg != 180 and d.w != d.h: self._status("Girar 90° necesita una escena cuadrada"); return
        self.scene.begin_edit(d)
        d.arr[:] = np.rot90(d.arr, {90: -1, -90: 1, 180: 2}[deg]).copy()
        d.refresh(0, 0, d.w, d.h); self.scene.end_edit(); self._changed()

    def nudge(self, dx, dy):
        if self.layer.kind == "vector":
            d = self._vec_drawing()
            if d and self.vsel:
                self.scene.begin_edit(d)
                for i in self.vsel:
                    d.strokes[i]["pts"] = [(p[0] + dx, p[1] + dy, *p[2:]) for p in d.strokes[i]["pts"]]
                d.touch(); self.scene.end_edit(); self._changed()
            return
        d = self._cur_drawing()
        if d is None or self._blocked(): return
        self.scene.begin_edit(d)
        if self.sel is None:
            self.sel = np.ones((d.h, d.w), bool); self._begin_move(d); self._move_by(dx, dy); self._set_sel(None)
        else:
            self._begin_move(d); self._move_by(dx, dy)
        self._mv = None
        self.scene.end_edit(); self._changed()

    # vectorial: seleccionar / contorno ----------------------------------------
    def _vselect_begin(self, cx, cy, tool):
        d = self._vec_drawing()
        self._vmode = "rubber"; self._vpoint = None
        if d is None: return
        if tool == "contour":
            if self.vsel:
                for si in self.vsel:
                    for pi, p in enumerate(d.strokes[si]["pts"]):
                        if math.hypot(p[0] - cx, p[1] - cy) <= 8 / self._z:
                            self.scene.begin_edit(d); self._drawing_ref = d
                            self._vpoint = (si, pi); self._vmode = "point"; return
                # clic sobre un segmento: añade un punto
                for si in self.vsel:
                    pts = d.strokes[si]["pts"]
                    for i in range(len(pts) - 1):
                        if ae.seg_dist(cx, cy, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) <= 6 / self._z:
                            self.scene.begin_edit(d); self._drawing_ref = d
                            pts.insert(i + 1, (cx, cy, 1.0)); d.touch()
                            self._vpoint = (si, i + 1); self._vmode = "point"; return
        hit = None
        for i in range(len(d.strokes) - 1, -1, -1):
            if ae.stroke_hit(d.strokes[i], cx, cy, 5 / self._z): hit = i; break
        if hit is not None:
            if self._shift: self.vsel ^= {hit}
            elif hit not in self.vsel: self.vsel = {hit}
            self.scene.begin_edit(d); self._drawing_ref = d
            self._vmode = "move" if tool == "select" else "rubber"
            self._vlast = (cx, cy)
            if tool == "contour": self._vmode = "rubber"
        else:
            if not self._shift: self.vsel = set()
            self._vmode = "rubber"
        self.queue_draw()

    def _vselect_move(self, cx, cy, tool):
        d = self._vec_drawing()
        if d is None: return
        if self._vmode == "point" and self._vpoint:
            si, pi = self._vpoint; p = d.strokes[si]["pts"][pi]
            d.strokes[si]["pts"][pi] = (cx, cy, *p[2:]); d.touch()
        elif self._vmode == "move":
            dx, dy = cx - self._vlast[0], cy - self._vlast[1]; self._vlast = (cx, cy)
            for i in self.vsel:
                d.strokes[i]["pts"] = [(p[0] + dx, p[1] + dy, *p[2:]) for p in d.strokes[i]["pts"]]
            d.touch()
        self._rubber = (self._sx0, self._sy0, cx, cy)
        self.queue_draw()

    def _vselect_end(self, cx, cy, tool):
        d = self._vec_drawing()
        if self._vmode in ("move", "point") and getattr(self, "_drawing_ref", None) is not None:
            self.scene.end_edit(); self._drawing_ref = None; self._changed()
        elif self._vmode == "rubber" and d is not None:
            x0, x1 = sorted((self._sx0, cx)); y0, y1 = sorted((self._sy0, cy))
            if abs(x1 - x0) > 3 or abs(y1 - y0) > 3:
                found = {i for i, s in enumerate(d.strokes)
                         if any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in s["pts"])}
                self.vsel = (self.vsel | found) if self._shift else found
            if getattr(self, "_drawing_ref", None) is not None:
                self.scene.end_edit(record=False); self._drawing_ref = None
        self._rubber = None; self.queue_draw()

    def delete_point(self):
        d = self._vec_drawing()
        if not (d and self._vpoint): return
        si, pi = self._vpoint
        pts = d.strokes[si]["pts"]
        if len(pts) <= 2: return
        self.scene.begin_edit(d); pts.pop(pi); d.touch(); self._vpoint = None
        self.scene.end_edit(); self._changed()

    # ══ cámara ════════════════════════════════════════════════════════════════
    def _cam_current(self):
        return self.scene.camera_at(self.cur)

    def _cam_begin(self, cx, cy):
        self.scene.snap()
        self._cam_start = (cx, cy, dict(self._cam_current()))
        self._cam_alt = self._alt

    def _cam_apply(self, cam):
        self.scene.cam_keys[self.cur] = {k: float(cam[k]) for k in ae.CAM_DEFAULT}
        self._changed()

    def _cam_move(self, cx, cy):
        x0, y0, cam = self._cam_start
        new = dict(cam)
        if self._cam_alt:
            cxm, cym = self.scene.w / 2, self.scene.h / 2
            a0 = math.atan2(y0 - cym, x0 - cxm); a1 = math.atan2(cy - cym, cx - cxm)
            new["rot"] = cam["rot"] + math.degrees(a1 - a0)
        else:
            new["tx"] = cam["tx"] + (cx - x0); new["ty"] = cam["ty"] + (cy - y0)
        self._cam_apply(new)

    def _cam_end(self):
        self._cam_start = None

    def _cam_edit(self, scale_mul=1.0):
        self.scene.snap()
        cam = dict(self._cam_current()); cam["scale"] = max(0.05, cam["scale"] * scale_mul)
        self._cam_apply(cam)

    def camera_key(self):
        self.scene.set_camera_key(self.cur, self._cam_current()); self._changed()

    def camera_remove_key(self):
        self.scene.remove_camera_key(self.cur); self._changed()

    def camera_reset(self):
        self.scene.set_camera_key(self.cur, dict(ae.CAM_DEFAULT)); self._changed()

    # ══ importar / exportar ═══════════════════════════════════════════════════
    def import_image(self, path):
        im = Image.open(path).convert("RGBA")
        W, H = self.scene.w, self.scene.h
        s = min(W / im.width, H / im.height)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        canvas.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
        if self.layer.kind != "raster":
            self.li = self.scene.add_layer("raster", above=self.li)
        d = self.layer.at(self.cur)
        if d is None: d = self.scene.new_drawing(self.li, self.cur)
        else: self.scene.snap()
        d.arr[:] = np.asarray(canvas); d.refresh(0, 0, W, H)
        self._after_struct()

    def import_sequence(self, files):
        """Cada imagen ocupa un fotograma nuevo en una capa nueva."""
        if not files: return
        self.scene.snap()
        li = self.scene.add_layer("raster", "Secuencia", above=self.li, record=False)
        W, H = self.scene.w, self.scene.h
        self.scene.ensure_frames(self.cur + len(files))
        l = self.scene.layers[li]
        for k, fp in enumerate(files):
            im = Image.open(fp).convert("RGBA")
            s = min(W / im.width, H / im.height)
            im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
            cv = Image.new("RGBA", (W, H), (0, 0, 0, 0)); cv.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
            l.drawings.append(ae.Drawing(W, H, "raster", np.asarray(cv).copy()))
            l.exposure[self.cur + k] = len(l.drawings) - 1
        self.li = li
        self._after_struct()

    def to_pil(self, f, camera=True):
        return self.scene.to_pil(f, camera)

    def save_project(self, path):
        self.scene.save(path)

    def load_project(self, path):
        try:
            self.load_scene(ae.Scene.load(path)); return True
        except Exception:  # noqa: BLE001
            return False

    def load_from_dir(self, frames_dir):
        files = sorted(frames_dir.glob("frame_*.png"))[:600]
        if not files: return False
        self.load_scene(ae.Scene.from_frames(files)); return True

    # ══ render ════════════════════════════════════════════════════════════════
    def _start_ants(self, *_):
        if self._ants_id is None: self._ants_id = GLib.timeout_add(150, self._tick_ants)

    def _stop_ants(self, *_):
        if self._ants_id is not None: GLib.source_remove(self._ants_id); self._ants_id = None

    def _tick_ants(self):
        if self.sel is not None:
            self._ants = (self._ants + 1) % 8; self.queue_draw()
        return True

    def _view_filter(self):
        # GOOD al reducir cuesta ~30 ms por capa en 1080p; BILINEAR ~1,5 ms
        if self._z >= 3: return cairo.Filter.NEAREST
        return cairo.Filter.GOOD if self._z >= 1 else cairo.Filter.BILINEAR

    def _layer_paint(self, cr, l, d, alpha=1.0, op=None):
        cr.set_source_surface(d.surface(), 0, 0)
        cr.get_source().set_filter(self._view_filter())
        cr.set_operator(op if op is not None else ae._op(l.blend))
        cr.paint_with_alpha(alpha * l.opacity / 255)
        cr.set_operator(cairo.Operator.OVER)

    def _onion(self, cr, f):
        for k in range(1, self.onion_prev + 1):
            g = f - k
            if g < 0: break
            self._tint(cr, g, (0.95, 0.25, 0.25), 0.34 * (1 - (k - 1) / (self.onion_prev + 0.5)))
        for k in range(1, self.onion_next + 1):
            g = f + k
            if g >= self.scene.frame_count: break
            self._tint(cr, g, (0.2, 0.55, 0.95), 0.34 * (1 - (k - 1) / (self.onion_next + 0.5)))

    def _tint(self, cr, f, rgb, a):
        for l in self.scene.layers:
            if not l.visible or not l.onion: continue
            d = l.at(f)
            if d is None or d is l.at(self.cur): continue
            cr.set_source_rgba(rgb[0], rgb[1], rgb[2], a * l.opacity / 255)
            pat = cairo.SurfacePattern(d.surface()); pat.set_filter(self._view_filter())
            cr.mask(pat)

    def _paint_scene(self, cr, f, camera=False):
        s = self.scene
        moved = False
        if camera:
            cam = s.camera_at(f)
            if cam != ae.CAM_DEFAULT:
                cr.save(); cr.transform(s.camera_matrix(cam)); moved = True
        for i, l in enumerate(s.layers):
            if not l.visible: continue
            d = l.at(f)
            if d is None: continue
            dim = 1.0
            if self.light_table and self.mode == "draw" and i != self.li: dim = 0.35
            self._layer_paint(cr, l, d, dim)
        if moved: cr.restore()

    def _draw(self, area, cr, width, height):
        if width > 20 and height > 20 and (self._fit_pending or (self._sticky_fit and (width, height) != self._fit_size)):
            self.zoom_fit()
        s = self.scene; z = self._z
        cr.set_source_rgb(*VIEW_BG); cr.paint()
        cr.save()
        cr.translate(self._ox, self._oy); cr.scale(z, z)
        if self.mirror_view:
            cr.translate(s.w, 0); cr.scale(-1, 1)
        if self.mode == "draw":
            if self.paper:
                cr.set_source_rgb(0.96, 0.96, 0.94); cr.rectangle(0, 0, s.w, s.h); cr.fill()
            else:
                cr.set_source_rgba(0, 0, 0, 0.10); cr.rectangle(0, 0, s.w, s.h); cr.fill()
            if self.onion: self._onion(cr, self.cur)
            self._paint_scene(cr, self.cur, camera=False)
            self._overlay_draw(cr)
        else:
            cr.set_source_rgba(0, 0, 0, 0.10); cr.rectangle(-2000, -2000, 5000, 5000); cr.fill()
            self._paint_scene(cr, self.cur, camera=True)
            cr.set_source_rgba(0, 0, 0, 0.45)
            cr.rectangle(-4000, -4000, 9000, 9000); cr.rectangle(0, 0, s.w, s.h)
            cr.set_fill_rule(cairo.FillRule.EVEN_ODD); cr.fill(); cr.set_fill_rule(cairo.FillRule.WINDING)
        # marco de escena / cámara
        cr.set_source_rgba(1, 1, 1, 0.55 if self.mode == "camera" else 0.25)
        cr.set_line_width(1.5 / z); cr.rectangle(0, 0, s.w, s.h); cr.stroke()
        if self.safe_area:
            cr.set_source_rgba(1, 0.8, 0.2, 0.6); cr.set_line_width(1 / z)
            m = 0.05
            cr.rectangle(s.w * m, s.h * m, s.w * (1 - 2 * m), s.h * (1 - 2 * m)); cr.stroke()
        if self.show_grid:
            g = self.grid_size
            cr.set_source_rgba(1, 1, 1, 0.22); cr.set_line_width(1 / z)
            for x in range(g, s.w, g): cr.move_to(x, 0); cr.line_to(x, s.h)
            for y in range(g, s.h, g): cr.move_to(0, y); cr.line_to(s.w, y)
            cr.stroke()
        cr.restore()
        self._draw_cursor(cr)

    def _overlay_draw(self, cr):
        s = self.scene; z = self._z
        if self.symmetry != "none":
            cr.set_source_rgba(0.3, 0.8, 1, 0.75); cr.set_line_width(1 / z); cr.set_dash([6 / z, 4 / z])
            if self.symmetry in ("h", "hv"): cr.move_to(s.w / 2, 0); cr.line_to(s.w / 2, s.h)
            if self.symmetry in ("v", "hv"): cr.move_to(0, s.h / 2); cr.line_to(s.w, s.h / 2)
            cr.stroke(); cr.set_dash([])
        # selección raster
        if self.sel is not None:
            if self._sel_segs is None: self._sel_segs = sel_segments(self.sel)
            for color, off in (((0, 0, 0, 1), 0), ((1, 1, 1, 1), 4)):
                cr.set_source_rgba(*color); cr.set_line_width(1 / z); cr.set_dash([4 / z, 4 / z], (self._ants + off) / z)
                for x1, y1, x2, y2 in self._sel_segs: cr.move_to(x1, y1); cr.line_to(x2, y2)
                cr.stroke()
            cr.set_dash([])
        # vectores seleccionados + puntos de control
        d = self._vec_drawing() if self.layer.kind == "vector" else None
        if d is not None and self.vsel:
            for si in self.vsel:
                if si >= len(d.strokes): continue
                st = d.strokes[si]
                xs = [p[0] for p in st["pts"]]; ys = [p[1] for p in st["pts"]]
                pad = st["width"] / 2 + 4 / z
                cr.set_source_rgba(0.2, 0.7, 1, 0.9); cr.set_line_width(1 / z); cr.set_dash([4 / z, 3 / z])
                cr.rectangle(min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)
                cr.stroke(); cr.set_dash([])
                if self.tool == "contour":
                    for p in st["pts"]:
                        cr.rectangle(p[0] - 3.5 / z, p[1] - 3.5 / z, 7 / z, 7 / z)
                        cr.set_source_rgb(1, 1, 1); cr.fill_preserve()
                        cr.set_source_rgb(0.1, 0.4, 0.9); cr.set_line_width(1 / z); cr.stroke()
        if getattr(self, "_rubber", None) and self._drawing and self._tool_now in ("select", "contour"):
            x0, y0, x1, y1 = self._rubber
            cr.set_source_rgba(0.3, 0.7, 1, 0.15); cr.rectangle(x0, y0, x1 - x0, y1 - y0); cr.fill()
            cr.set_source_rgba(0.3, 0.7, 1, 0.9); cr.set_line_width(1 / z); cr.rectangle(x0, y0, x1 - x0, y1 - y0); cr.stroke()
        if self._lasso and self._drawing:
            cr.set_source_rgba(1, 1, 1, 0.9); cr.set_line_width(1 / z); cr.set_dash([4 / z, 3 / z])
            cr.move_to(*self._lasso[0])
            for p in self._lasso[1:]: cr.line_to(*p)
            cr.stroke(); cr.set_dash([])
        # polilínea en curso
        if self._poly:
            cr.set_source_rgba(*(c / 255 for c in self.fg)); cr.set_line_width(max(1, self.props["shape_width"]))
            cr.move_to(*self._poly[0])
            for p in self._poly[1:]: cr.line_to(*p)
            cr.line_to(*self._shape_end); cr.stroke()
        # vista previa de formas vectoriales
        if self._drawing and self._tool_now in ("line", "rect", "ellipse") and self.layer.kind == "vector":
            x0, y0 = self._sh0; x1, y1 = self._shape_end
            cr.set_source_rgba(*(c / 255 for c in self.fg)); cr.set_line_width(max(1, self.props["shape_width"]))
            if self._tool_now == "line": cr.move_to(x0, y0); cr.line_to(x1, y1)
            elif self._tool_now == "rect": cr.rectangle(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
            else:
                cr.save(); cr.translate((x0 + x1) / 2, (y0 + y1) / 2)
                cr.scale(max(0.1, abs(x1 - x0) / 2), max(0.1, abs(y1 - y0) / 2)); cr.arc(0, 0, 1, 0, 2 * math.pi); cr.restore()
            cr.stroke()

    def _draw_cursor(self, cr):
        if self._cursor_c is None or self._panning or self._space or self.mode == "camera":
            return
        t = self.tool
        if t in ("brush", "pencil", "eraser", "smudge"):
            p = self.props
            size = {"brush": p["brush_size"], "pencil": p["pencil_size"], "eraser": p["eraser_size"],
                    "smudge": p["smudge_size"]}[t]
            sx, sy = self._mouse
            r = max(2.0, size * self._z / 2)
            cr.set_line_width(1)
            cr.arc(sx, sy, r, 0, 2 * math.pi); cr.set_source_rgba(0, 0, 0, 0.7); cr.stroke()
            cr.arc(sx, sy, max(0.5, r - 1), 0, 2 * math.pi); cr.set_source_rgba(1, 1, 1, 0.7); cr.stroke()
