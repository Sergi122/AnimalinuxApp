"""
Motor del editor de animación — AnimaLinux (modelo estilo Toon Boom Harmony).

Sin dependencias de ventanas: se puede probar sin pantalla.

  Escena ─┬─ capas (dibujo raster o vectorial), de abajo hacia arriba
          │    └─ dibujos + exposición: qué dibujo se ve en cada fotograma
          │       (un dibujo puede mantenerse varios fotogramas, como en la hoja
          │        de exposición de Harmony)
          ├─ cámara con claves animadas (traslación, escala, rotación)
          ├─ rango de reproducción (inicio / fin), FPS, audio
          └─ deshacer por regiones (solo se guarda el área modificada)

Los dibujos raster guardan RGBA recto (numpy) y un búfer BGRA premultiplicado
que se actualiza por regiones, así que pintar no reconvierte el lienzo entero.
"""
import copy
import io
import json
import math
import zipfile

import numpy as np
import cairo
from PIL import Image, ImageDraw

MAX_UNDO = 80

BLEND_OPS = {
    "Normal": "OVER", "Multiplicar": "MULTIPLY", "Pantalla": "SCREEN",
    "Superponer": "OVERLAY", "Oscurecer": "DARKEN", "Aclarar": "LIGHTEN",
    "Añadir": "ADD", "Diferencia": "DIFFERENCE", "Luz dura": "HARD_LIGHT",
    "Luz suave": "SOFT_LIGHT", "Eludir color": "COLOR_DODGE",
    "Quemar color": "COLOR_BURN",
}
BLEND_MODES = list(BLEND_OPS)

BRUSH_TYPES = ["round", "pencil", "airbrush", "texture", "chalk", "watercolor",
               "marker", "crayon", "sponge", "pixel", "fan", "ink"]
BRUSH_LABELS = ["Redondo suave", "Lápiz (duro)", "Aerógrafo", "Textura", "Tiza",
                "Acuarela", "Marcador", "Crayón", "Esponja", "Píxel exacto",
                "Abanico", "Tinta (pluma)"]
GRAIN_BRUSHES = {"texture", "chalk", "watercolor", "crayon", "sponge"}

_NOISE = np.random.default_rng(7).random((256, 256)).astype(np.float32)


def _op(name):
    return getattr(cairo.Operator, BLEND_OPS.get(name, "OVER"))


# ── conversiones cairo <-> numpy ─────────────────────────────────────────────
def premul_region(bufarr, arr, x0, y0, x1, y1):
    """RGBA recto -> BGRA premultiplicado (solo el rectángulo dado)."""
    reg = arr[y0:y1, x0:x1]
    a = reg[..., 3].astype(np.uint16)
    out = bufarr[y0:y1, x0:x1]
    out[..., 0] = (reg[..., 2].astype(np.uint16) * a + 127) // 255
    out[..., 1] = (reg[..., 1].astype(np.uint16) * a + 127) // 255
    out[..., 2] = (reg[..., 0].astype(np.uint16) * a + 127) // 255
    out[..., 3] = reg[..., 3]


def surface_to_rgba(surf):
    """cairo.ImageSurface ARGB32 (premultiplicado) -> ndarray RGBA recto."""
    surf.flush()
    w, h = surf.get_width(), surf.get_height()
    raw = np.frombuffer(surf.get_data(), dtype=np.uint8).reshape(h, surf.get_stride() // 4, 4)[:, :w]
    a = raw[..., 3].astype(np.float32)
    safe = np.where(a > 0, a, 1)
    rgb = np.clip(raw[..., :3].astype(np.float32) * 255.0 / safe[..., None], 0, 255)
    out = np.empty((h, w, 4), dtype=np.uint8)
    out[..., 0] = rgb[..., 2]; out[..., 1] = rgb[..., 1]; out[..., 2] = rgb[..., 0]
    out[..., 3] = raw[..., 3]
    out[a == 0, :3] = 0
    return out


# ── trazos vectoriales ───────────────────────────────────────────────────────
def _smooth_path(cr, pts, closed=False):
    """Catmull-Rom -> curvas de Bézier a través de los puntos."""
    n = len(pts)
    if n == 0: return
    cr.move_to(*pts[0][:2])
    if n == 1:
        cr.line_to(pts[0][0] + 0.01, pts[0][1]); return
    if n == 2 and not closed:
        cr.line_to(*pts[1][:2]); return
    P = [p[:2] for p in pts]
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = P[(i - 1) % n] if (closed or i > 0) else P[0]
        p1 = P[i]; p2 = P[(i + 1) % n]
        p3 = P[(i + 2) % n] if (closed or i + 2 < n) else P[-1]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        cr.curve_to(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
    if closed: cr.close_path()


def draw_stroke(cr, st):
    col = st["color"]
    cr.set_line_cap(cairo.LineCap.ROUND); cr.set_line_join(cairo.LineJoin.ROUND)
    pts = st["pts"]
    if st.get("closed") and st.get("fill"):
        f = st["fill"]
        _smooth_path(cr, pts, True)
        cr.set_source_rgba(f[0] / 255, f[1] / 255, f[2] / 255, f[3] / 255); cr.fill()
    if st["width"] <= 0: return
    cr.set_source_rgba(col[0] / 255, col[1] / 255, col[2] / 255, col[3] / 255)
    pr = [p[2] if len(p) > 2 else 1.0 for p in pts]
    if len(pts) > 2 and max(pr) - min(pr) > 0.08 and not st.get("closed"):
        for i in range(len(pts) - 1):            # ancho variable con la presión
            cr.set_line_width(max(0.4, st["width"] * (pr[i] + pr[i + 1]) / 2))
            cr.move_to(*pts[i][:2]); cr.line_to(*pts[i + 1][:2]); cr.stroke()
    else:
        cr.set_line_width(max(0.4, st["width"]))
        _smooth_path(cr, pts, st.get("closed", False)); cr.stroke()


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def stroke_hit(st, x, y, r=4.0):
    pts = st["pts"]; tol = r + st["width"] / 2
    if len(pts) == 1: return math.hypot(x - pts[0][0], y - pts[0][1]) <= tol
    segs = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if st.get("closed") else [])
    return any(seg_dist(x, y, a[0], a[1], b[0], b[1]) <= tol for a, b in segs)


def point_in_poly(pts, x, y):
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i][:2]; x2, y2 = pts[(i + 1) % n][:2]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
            inside = not inside
    return inside


# ── dibujo ───────────────────────────────────────────────────────────────────
class Drawing:
    """Un dibujo (raster o vectorial). Varias exposiciones pueden compartirlo."""

    def __init__(self, w, h, kind="raster", arr=None):
        self.w, self.h, self.kind = w, h, kind
        if kind == "raster":
            self.arr = np.zeros((h, w, 4), np.uint8) if arr is None else arr
            self.buf = bytearray(w * h * 4)
            self.bufarr = np.frombuffer(self.buf, np.uint8).reshape(h, w, 4)
            self.refresh(0, 0, w, h)
        else:
            self.strokes = []
            self._vsurf = None
            self._vdirty = True

    # raster ------------------------------------------------------------------
    def refresh(self, x0, y0, x1, y1):
        x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(self.w, x1), min(self.h, y1)
        if x1 <= x0 or y1 <= y0: return
        premul_region(self.bufarr, self.arr, x0, y0, x1, y1)
        # No se llama a mark_dirty: cairo aborta el proceso si la superficie sigue
        # referenciada por el dibujo grabado de GTK. Se usa una superficie nueva en
        # cada uso (ver surface()), sin estado interno que invalidar.

    # vectorial ---------------------------------------------------------------
    def touch(self):
        if self.kind == "vector": self._vdirty = True

    def surface(self):
        if self.kind == "raster":
            return cairo.ImageSurface.create_for_data(
                self.buf, cairo.Format.ARGB32, self.w, self.h, self.w * 4)
        if self._vdirty or self._vsurf is None:
            s = cairo.ImageSurface(cairo.Format.ARGB32, self.w, self.h)
            cr = cairo.Context(s)
            for st in self.strokes: draw_stroke(cr, st)
            self._vsurf = s; self._vdirty = False
        return self._vsurf

    def rgba(self):
        return self.arr if self.kind == "raster" else surface_to_rgba(self.surface())

    def is_empty(self):
        if self.kind == "vector": return not self.strokes
        return not self.arr[..., 3].any()

    def copy(self):
        if self.kind == "raster":
            return Drawing(self.w, self.h, "raster", self.arr.copy())
        d = Drawing(self.w, self.h, "vector")
        d.strokes = copy.deepcopy(self.strokes)
        return d


class Layer:
    def __init__(self, name, kind="raster", frames=1):
        self.name = name
        self.kind = kind
        self.visible = True
        self.locked = False
        self.alpha_locked = False
        self.opacity = 255
        self.blend = "Normal"
        self.onion = True
        self.drawings = []
        self.exposure = [-1] * frames

    def meta(self):
        return dict(name=self.name, kind=self.kind, visible=self.visible, locked=self.locked,
                    alpha_locked=self.alpha_locked, opacity=self.opacity, blend=self.blend,
                    onion=self.onion)

    def apply_meta(self, m):
        for k, v in m.items(): setattr(self, k, v)

    def at(self, f):
        if 0 <= f < len(self.exposure):
            i = self.exposure[f]
            if 0 <= i < len(self.drawings): return self.drawings[i]
        return None

    def drawing_index_at(self, f):
        return self.exposure[f] if 0 <= f < len(self.exposure) else -1


CAM_DEFAULT = {"tx": 0.0, "ty": 0.0, "scale": 1.0, "rot": 0.0}


# ── escena ───────────────────────────────────────────────────────────────────
class Scene:
    def __init__(self, w=512, h=512, fps=12):
        self.w, self.h, self.fps = w, h, fps
        self.frame_count = 1
        self.layers = []
        self.cam_keys = {}
        self.start, self.stop = 0, 0
        self.audio = None
        self._undo, self._redo = [], []
        self._pre = None
        self.add_layer("raster", "Dibujo 1", record=False)

    # ── deshacer ─────────────────────────────────────────────────────────────
    def _struct(self):
        return ("struct", self.frame_count, self.start, self.stop,
                copy.deepcopy(self.cam_keys),
                [(l.meta(), list(l.drawings), list(l.exposure)) for l in self.layers])

    def _apply_struct(self, st):
        _, fc, s, e, cam, layers = st
        self.frame_count, self.start, self.stop = fc, s, e
        self.cam_keys = copy.deepcopy(cam)
        self.layers = []
        for meta, drawings, expo in layers:
            l = Layer(meta["name"], meta["kind"], 0)
            l.apply_meta(meta); l.drawings = list(drawings); l.exposure = list(expo)
            self.layers.append(l)

    def snap(self):
        self._undo.append(self._struct())
        if len(self._undo) > MAX_UNDO: self._undo.pop(0)
        self._redo.clear()

    def begin_edit(self, drawing):
        """Llamar antes de modificar un dibujo (pixeles o trazos)."""
        if drawing.kind == "raster": self._pre = (drawing, drawing.arr.copy())
        else: self._pre = (drawing, copy.deepcopy(drawing.strokes))

    def end_edit(self, record=True):
        """Registra el cambio: solo el rectángulo modificado (raster) o los trazos.
        `record=False` descarta la copia (p. ej. si el dibujo se acaba de crear y
        deshacer la creación ya lo elimina)."""
        if self._pre is None: return False
        d, before = self._pre
        self._pre = None
        if not record: return True
        if d.kind == "raster":
            diff = np.any(d.arr != before, axis=2)
            if not diff.any(): return False
            ys, xs = np.nonzero(diff)
            x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
            item = ("region", d, (x0, y0, x1, y1), before[y0:y1, x0:x1].copy())
        else:
            if before == d.strokes: return False
            item = ("vec", d, before)
        self._undo.append(item)
        if len(self._undo) > MAX_UNDO: self._undo.pop(0)
        self._redo.clear()
        return True

    def _swap(self, src, dst):
        if not src: return False
        item = src.pop()
        if item[0] == "region":
            _, d, (x0, y0, x1, y1), crop = item
            cur = d.arr[y0:y1, x0:x1].copy()
            d.arr[y0:y1, x0:x1] = crop
            d.refresh(x0, y0, x1, y1)
            dst.append(("region", d, (x0, y0, x1, y1), cur))
        elif item[0] == "vec":
            _, d, strokes = item
            dst.append(("vec", d, copy.deepcopy(d.strokes)))
            d.strokes = strokes; d.touch()
        else:
            dst.append(self._struct()); self._apply_struct(item)
        return True

    def undo(self): return self._swap(self._undo, self._redo)
    def redo(self): return self._swap(self._redo, self._undo)

    # ── capas ────────────────────────────────────────────────────────────────
    def add_layer(self, kind="raster", name=None, above=None, record=True):
        if record: self.snap()
        n = len(self.layers) + 1
        l = Layer(name or (f"Dibujo {n}" if kind == "raster" else f"Vector {n}"), kind, self.frame_count)
        at = len(self.layers) if above is None else above + 1
        self.layers.insert(at, l)
        return at

    def remove_layer(self, i):
        if len(self.layers) <= 1 or not 0 <= i < len(self.layers): return False
        self.snap(); self.layers.pop(i); return True

    def duplicate_layer(self, i):
        self.snap()
        src = self.layers[i]
        l = Layer(src.name + " copia", src.kind, 0)
        l.apply_meta({**src.meta(), "name": src.name + " copia", "locked": False})
        l.drawings = [d.copy() for d in src.drawings]
        l.exposure = list(src.exposure)
        self.layers.insert(i + 1, l)
        return i + 1

    def move_layer(self, i, delta):
        j = i + delta
        if not (0 <= i < len(self.layers) and 0 <= j < len(self.layers)): return i
        self.snap()
        self.layers[i], self.layers[j] = self.layers[j], self.layers[i]
        return j

    def merge_down(self, i):
        if i <= 0 or self.layers[i].kind != "raster" or self.layers[i - 1].kind != "raster":
            return False
        self.snap()
        top, bot = self.layers[i], self.layers[i - 1]
        new_draw, new_expo, cache = [], [], {}
        for f in range(self.frame_count):
            key = (bot.drawing_index_at(f), top.drawing_index_at(f))
            if key == (-1, -1):
                new_expo.append(-1); continue
            if key not in cache:
                s = cairo.ImageSurface(cairo.Format.ARGB32, self.w, self.h)
                cr = cairo.Context(s)
                for lay in (bot, top):
                    d = lay.at(f)
                    if d is None: continue
                    cr.set_source_surface(d.surface(), 0, 0)
                    cr.set_operator(_op(lay.blend)); cr.paint_with_alpha(lay.opacity / 255)
                nd = Drawing(self.w, self.h, "raster", surface_to_rgba(s))
                new_draw.append(nd); cache[key] = len(new_draw) - 1
            new_expo.append(cache[key])
        bot.drawings, bot.exposure = new_draw, new_expo
        bot.opacity, bot.blend = 255, "Normal"
        self.layers.pop(i)
        return True

    # ── fotogramas y exposición ──────────────────────────────────────────────
    def ensure_frames(self, n):
        if n > self.frame_count:
            if self.stop == self.frame_count - 1: self.stop = n - 1      # el rango sigue el final
            for l in self.layers: l.exposure += [-1] * (n - self.frame_count)
            self.frame_count = n

    def set_length(self, n):
        n = max(1, min(2000, n))
        self.snap()
        if n > self.frame_count: self.ensure_frames(n)
        else:
            for l in self.layers: l.exposure = l.exposure[:n]
            self.frame_count = n
        self.start = min(self.start, n - 1); self.stop = min(max(self.stop, self.start), n - 1)

    def insert_frames(self, at, n=1):
        self.snap()
        for l in self.layers: l.exposure[at:at] = [-1] * n
        self.frame_count += n
        self.cam_keys = {(f + n if f >= at else f): v for f, v in self.cam_keys.items()}
        if self.stop >= at: self.stop = min(self.stop + n, self.frame_count - 1)
        if self.start >= at: self.start += n

    def delete_frames(self, at, n=1):
        if self.frame_count - n < 1: return False
        self.snap()
        for l in self.layers: del l.exposure[at:at + n]
        self.frame_count -= n
        self.cam_keys = {(f - n if f >= at + n else f): v for f, v in self.cam_keys.items()
                         if not at <= f < at + n}
        self.start = min(self.start, self.frame_count - 1)
        self.stop = min(self.stop, self.frame_count - 1)
        return True

    def new_drawing(self, li, f, copy_from=None, record=True):
        """Crea un dibujo nuevo en la celda (li, f); lo devuelve."""
        if record: self.snap()
        self.ensure_frames(f + 1)
        l = self.layers[li]
        d = copy_from.copy() if copy_from is not None else Drawing(self.w, self.h, l.kind)
        l.drawings.append(d)
        l.exposure[f] = len(l.drawings) - 1
        return d

    def drawing_for_edit(self, li, f):
        """Dibujo a modificar en (li, f); crea uno si la celda está vacía."""
        l = self.layers[li]
        d = l.at(f)
        if d is not None: return d
        return self.new_drawing(li, f)

    def extend_exposure(self, li, f, to):
        """Mantiene el dibujo de (li, f) hasta el fotograma `to`."""
        l = self.layers[li]
        i = l.drawing_index_at(f)
        if i < 0: return False
        self.snap(); self.ensure_frames(to + 1)
        for k in range(f, to + 1): l.exposure[k] = i
        return True

    def clear_cell(self, li, f, to=None):
        self.snap()
        l = self.layers[li]
        for k in range(f, (to if to is not None else f) + 1):
            if 0 <= k < len(l.exposure): l.exposure[k] = -1

    def duplicate_drawing(self, li, f):
        l = self.layers[li]
        d = l.at(f)
        if d is None: return None
        return self.new_drawing(li, f, copy_from=d)

    def reverse_frames(self, a, b):
        self.snap()
        for l in self.layers: l.exposure[a:b + 1] = l.exposure[a:b + 1][::-1]

    def pingpong(self, a, b):
        """Duplica el rango a..b en sentido inverso justo después."""
        self.snap()
        n = b - a
        for l in self.layers:
            seg = l.exposure[a:b + 1]
            l.exposure[b + 1:b + 1] = seg[-2::-1] if n > 0 else []
        self.frame_count += max(0, n)
        for l in self.layers:
            if len(l.exposure) < self.frame_count: l.exposure += [-1] * (self.frame_count - len(l.exposure))

    # ── cámara ───────────────────────────────────────────────────────────────
    def camera_at(self, f):
        if not self.cam_keys: return dict(CAM_DEFAULT)
        keys = sorted(self.cam_keys)
        if f <= keys[0]: return dict(self.cam_keys[keys[0]])
        if f >= keys[-1]: return dict(self.cam_keys[keys[-1]])
        for a, b in zip(keys, keys[1:]):
            if a <= f <= b:
                t = (f - a) / (b - a)
                ka, kb = self.cam_keys[a], self.cam_keys[b]
                return {k: ka[k] + (kb[k] - ka[k]) * t for k in CAM_DEFAULT}
        return dict(CAM_DEFAULT)

    def set_camera_key(self, f, cam):
        self.snap()
        self.cam_keys[f] = {k: float(cam.get(k, CAM_DEFAULT[k])) for k in CAM_DEFAULT}

    def remove_camera_key(self, f):
        if f in self.cam_keys:
            self.snap(); del self.cam_keys[f]

    def camera_matrix(self, cam):
        cx, cy = self.w / 2, self.h / 2
        m = cairo.Matrix()
        m.translate(cx + cam["tx"], cy + cam["ty"])
        m.rotate(math.radians(cam["rot"]))
        m.scale(cam["scale"], cam["scale"])
        m.translate(-cx, -cy)
        return m

    # ── composición ──────────────────────────────────────────────────────────
    def composite(self, f, camera=True, skip=None):
        """Superficie cairo con la escena en el fotograma f."""
        s = cairo.ImageSurface(cairo.Format.ARGB32, self.w, self.h)
        cr = cairo.Context(s)
        cam = self.camera_at(f) if camera else None
        moved = cam is not None and cam != CAM_DEFAULT
        if moved: cr.transform(self.camera_matrix(cam))
        for li, l in enumerate(self.layers):
            if not l.visible or (skip and li in skip): continue
            d = l.at(f)
            if d is None: continue
            cr.set_source_surface(d.surface(), 0, 0)
            if moved: cr.get_source().set_filter(cairo.Filter.BILINEAR)
            cr.set_operator(_op(l.blend))
            cr.paint_with_alpha(l.opacity / 255)
        return s

    def to_pil(self, f, camera=True):
        return Image.fromarray(surface_to_rgba(self.composite(f, camera)), "RGBA")

    def flatten_frame(self, f):
        return surface_to_rgba(self.composite(f, camera=False))

    # ── proyecto (.alproj v2, con lectura de v1) ─────────────────────────────
    def save(self, path):
        meta = {"version": 2, "w": self.w, "h": self.h, "fps": self.fps,
                "frames": self.frame_count, "start": self.start, "stop": self.stop,
                "cam_keys": {str(k): v for k, v in self.cam_keys.items()},
                "audio": self.audio, "layers": []}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for li, l in enumerate(self.layers):
                lm = l.meta(); lm["exposure"] = l.exposure; lm["drawings"] = []
                for di, d in enumerate(l.drawings):
                    if d.kind == "raster":
                        buf = io.BytesIO()
                        Image.fromarray(d.arr, "RGBA").save(buf, "PNG")
                        name = f"l{li}/d{di}.png"
                        zf.writestr(name, buf.getvalue())
                        lm["drawings"].append({"img": name})
                    else:
                        lm["drawings"].append({"strokes": [
                            {**s, "pts": [list(p) for p in s["pts"]], "color": list(s["color"]),
                             "fill": list(s["fill"]) if s.get("fill") else None} for s in d.strokes]})
                meta["layers"].append(lm)
            zf.writestr("project.json", json.dumps(meta))

    @classmethod
    def load(cls, path):
        with zipfile.ZipFile(path) as zf:
            meta = json.loads(zf.read("project.json"))
            v = meta.get("version", 0)
            if v == 2: return cls._load_v2(zf, meta)
            if v == 1: return cls._load_v1(zf, meta)
        raise ValueError("Versión de proyecto no soportada")

    @classmethod
    def _load_v2(cls, zf, meta):
        sc = cls(meta["w"], meta["h"], meta.get("fps", 12))
        sc.layers = []
        sc.frame_count = meta["frames"]
        sc.start, sc.stop = meta.get("start", 0), meta.get("stop", meta["frames"] - 1)
        sc.cam_keys = {int(k): v for k, v in meta.get("cam_keys", {}).items()}
        sc.audio = meta.get("audio")
        for lm in meta["layers"]:
            l = Layer(lm["name"], lm["kind"], 0)
            l.apply_meta({k: lm[k] for k in ("visible", "locked", "alpha_locked", "opacity", "blend", "onion") if k in lm})
            l.exposure = list(lm["exposure"])
            for dm in lm["drawings"]:
                if "img" in dm:
                    arr = np.array(Image.open(io.BytesIO(zf.read(dm["img"]))).convert("RGBA"))
                    l.drawings.append(Drawing(sc.w, sc.h, "raster", arr))
                else:
                    d = Drawing(sc.w, sc.h, "vector")
                    d.strokes = [{**s, "pts": [tuple(p) for p in s["pts"]], "color": tuple(s["color"]),
                                  "fill": tuple(s["fill"]) if s.get("fill") else None}
                                 for s in dm["strokes"]]
                    l.drawings.append(d)
            sc.layers.append(l)
        sc._undo.clear(); sc._redo.clear()
        return sc

    @classmethod
    def _load_v1(cls, zf, meta):
        """Formato antiguo: cada fotograma tenía su propia lista de capas."""
        w, h = meta["canvas"]["w"], meta["canvas"]["h"]
        sc = cls(w, h)
        frames = meta["frames"]
        sc.frame_count = len(frames)
        sc.layers = []
        nl = max(len(fr["layers"]) for fr in frames)
        for li in range(nl):
            first = next((fr["layers"][li] for fr in frames if li < len(fr["layers"])), None)
            l = Layer(first["name"] if first else f"Dibujo {li + 1}", "raster", len(frames))
            if first:
                l.apply_meta({"visible": first.get("visible", True), "locked": first.get("locked", False),
                              "alpha_locked": first.get("alpha_locked", False),
                              "opacity": first.get("opacity", 255), "blend": first.get("blend_mode", "Normal")})
            for fi, fr in enumerate(frames):
                if li >= len(fr["layers"]): continue
                arr = np.array(Image.open(io.BytesIO(zf.read(fr["layers"][li]["img"]))).convert("RGBA"))
                if not arr[..., 3].any(): continue
                l.drawings.append(Drawing(w, h, "raster", arr))
                l.exposure[fi] = len(l.drawings) - 1
            sc.layers.append(l)
        cams = meta.get("frame_camera", [])
        for fi, c in enumerate(cams):
            if c and any(abs(c.get(k, 0) - CAM_DEFAULT[k]) > 1e-9 for k in CAM_DEFAULT):
                sc.cam_keys[fi] = {k: float(c.get(k, CAM_DEFAULT[k])) for k in CAM_DEFAULT}
        sc.stop = sc.frame_count - 1
        return sc

    @classmethod
    def from_frames(cls, files, max_dim=2048):
        """Crea una escena con un dibujo por fotograma a partir de PNG."""
        first = Image.open(files[0]).convert("RGBA")
        w, h = first.size
        sc = cls(w, h)
        l = sc.layers[0]
        l.exposure = [-1] * len(files); sc.frame_count = len(files)
        for i, fp in enumerate(files):
            im = Image.open(fp).convert("RGBA")
            if im.size != (w, h): im = im.resize((w, h), Image.LANCZOS)
            l.drawings.append(Drawing(w, h, "raster", np.array(im)))
            l.exposure[i] = i
        sc.stop = sc.frame_count - 1
        l.name = "Fondo"
        return sc


# ═════════════════════════ pinceles ══════════════════════════════════════════
def brush_tip(kind, radius, hardness):
    """Forma del pincel: ndarray float32 (s, s) con cobertura 0..1."""
    radius = max(0.5, float(radius))
    r = int(math.ceil(radius)) + 1
    size = r * 2 + 1
    ys, xs = np.mgrid[:size, :size].astype(np.float32)
    dx, dy = xs - r, ys - r
    d = np.sqrt(dx * dx + dy * dy)
    rr = max(radius, 0.5)
    soft = max(0.05, 1.0 - hardness)              # 0 = duro, 1 = muy suave
    if kind == "pencil" or kind == "pixel":
        t = np.clip(rr + 0.5 - d, 0, 1)
    elif kind == "airbrush":
        t = np.exp(-0.5 * (d / max(rr * 0.55, 0.5)) ** 2) * 0.55
    elif kind == "marker":
        inner = rr * 0.86
        t = np.clip((rr + 0.5 - d), 0, 1) * np.where(d <= inner, 0.92, 0.92 * np.clip(1 - (d - inner) / max(rr - inner, 1), 0, 1) + 0.0)
        t = np.clip(t, 0, 1)
    elif kind == "chalk":
        t = np.where(d < rr, np.clip(1.0 - d / rr, 0, 1) ** 0.5, 0) * 0.9
    elif kind == "watercolor":
        ang = np.arctan2(dy, dx)
        warp = np.sin(ang * 7) * 0.12
        t = np.clip(1.0 - (d / rr + warp), 0, 1) ** 0.5 * 0.6
    elif kind == "crayon":
        t = np.clip(1.0 - d / rr, 0, 1) ** 0.8
    elif kind == "sponge":
        t = np.clip(1.0 - d / rr, 0, 1) ** 0.6 * 0.8
    elif kind == "texture":
        t = np.clip(1.0 - d / rr, 0, 1) ** (1.0 / soft)
    elif kind == "fan":
        ang = np.arctan2(dy, dx)
        t = (d <= rr) * (np.cos(ang * 8) * 0.5 + 0.5) * np.clip(1.0 - d / rr, 0, 1) ** 0.5 * 0.85
    elif kind == "ink":
        de = np.sqrt((dx * 1.5) ** 2 + dy * dy)
        t = np.clip(1.0 - de / rr, 0, 1) ** 0.6
    else:  # round
        edge = np.clip((rr - d) / max(rr * soft, 0.75) + (0 if soft > 0.08 else 0.5), 0, 1)
        t = edge
    return t.astype(np.float32)


def apply_dab(arr, cx, cy, tip, color, opacity, erase=False, alpha_lock=False, grain=False, smudge=None):
    """Estampa el pincel en (cx, cy). Devuelve el rectángulo modificado o None."""
    s = tip.shape[0]; r = s // 2
    ix, iy = int(round(cx)), int(round(cy))
    x0, y0 = ix - r, iy - r
    H, W = arr.shape[:2]
    sx0, sy0 = max(0, -x0), max(0, -y0)
    ex0, ey0 = max(0, x0), max(0, y0)
    ex1, ey1 = min(W, x0 + s), min(H, y0 + s)
    if ex1 <= ex0 or ey1 <= ey0: return None
    cov = tip[sy0:sy0 + (ey1 - ey0), sx0:sx0 + (ex1 - ex0)] * (opacity / 255.0)
    if grain:
        ny = (np.arange(ey0, ey1) % 256)[:, None]; nx = (np.arange(ex0, ex1) % 256)[None, :]
        cov = cov * (0.35 + 0.65 * _NOISE[ny, nx])
    reg = arr[ey0:ey1, ex0:ex1]
    ra = reg[..., 3].astype(np.float32) / 255.0
    if smudge is not None:                              # dedo: arrastra color
        carried = smudge["px"]
        if carried is None or carried.shape != reg.shape:
            smudge["px"] = reg.astype(np.float32).copy(); return (ex0, ey0, ex1, ey1)
        k = (cov * smudge.get("k", 0.6))[..., None]
        cur = reg.astype(np.float32)
        out = cur * (1 - k) + carried * k
        smudge["px"] = carried * 0.65 + cur * 0.35
        reg[:] = np.clip(out + 0.5, 0, 255).astype(np.uint8)
        return (ex0, ey0, ex1, ey1)
    if erase:
        na = ra * (1 - cov)
        reg[..., 3] = (na * 255 + 0.5).astype(np.uint8)
        reg[na <= 0.002, :3] = 0
        return (ex0, ey0, ex1, ey1)
    cov = cov * (color[3] / 255.0)
    c = np.array(color[:3], np.float32)
    if alpha_lock:
        w = (cov * (ra > 0))[..., None]
        reg[..., :3] = np.clip(reg[..., :3].astype(np.float32) * (1 - w) + c * w + 0.5, 0, 255).astype(np.uint8)
        return (ex0, ey0, ex1, ey1)
    oa = cov + ra * (1 - cov)
    safe = np.maximum(oa, 1e-6)[..., None]
    rgb = (c * cov[..., None] + reg[..., :3].astype(np.float32) * (ra * (1 - cov))[..., None]) / safe
    reg[..., :3] = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
    reg[..., 3] = np.clip(oa * 255 + 0.5, 0, 255).astype(np.uint8)
    return (ex0, ey0, ex1, ey1)


class StrokePainter:
    """Traza un trazo de pincel sobre un dibujo raster (suavizado, espaciado, presión)."""

    def __init__(self, drawing, kind="round", size=12.0, hardness=0.5, opacity=255, color=(0, 0, 0, 255),
                 erase=False, alpha_lock=False, smudge=False, smoothing=0.0, spacing=0.14,
                 pressure_size=True, pressure_opacity=False, min_size=0.25):
        self.d = drawing; self.kind = kind; self.size = max(0.5, size); self.hardness = hardness
        self.opacity = opacity; self.color = tuple(color); self.erase = erase
        self.alpha_lock = alpha_lock; self.spacing = spacing
        self.pressure_size = pressure_size; self.pressure_opacity = pressure_opacity
        self.min_size = min_size
        self.smoothing = max(0.0, min(0.95, smoothing))
        self.sm = {"px": None, "k": 0.6} if smudge else None
        self.grain = kind in GRAIN_BRUSHES
        self._tips = {}
        self.last = None        # última posición de dab
        self.lazy = None
        self._acc = 0.0
        self.dirty = None

    def _tip(self, radius):
        key = round(radius * 2) / 2
        t = self._tips.get(key)
        if t is None:
            t = self._tips[key] = brush_tip(self.kind, key, self.hardness)
        return t

    def _union(self, r):
        if r is None: return
        if self.dirty is None: self.dirty = list(r)
        else:
            self.dirty = [min(self.dirty[0], r[0]), min(self.dirty[1], r[1]),
                          max(self.dirty[2], r[2]), max(self.dirty[3], r[3])]

    def _dab(self, x, y, pressure):
        p = max(0.0, min(1.0, pressure))
        rad = self.size / 2 * (self.min_size + (1 - self.min_size) * p if self.pressure_size else 1.0)
        op = self.opacity * ((0.25 + 0.75 * p) if self.pressure_opacity else 1.0)
        r = apply_dab(self.d.arr, x, y, self._tip(rad), self.color, op, self.erase,
                      self.alpha_lock, self.grain, self.sm)
        self._union(r)

    def _smooth(self, x, y):
        if self.smoothing <= 0 or self.lazy is None:
            self.lazy = (x, y)
        else:
            k = self.smoothing
            self.lazy = (self.lazy[0] + (x - self.lazy[0]) * (1 - k), self.lazy[1] + (y - self.lazy[1]) * (1 - k))
        return self.lazy

    def add(self, x, y, pressure=1.0, final=False):
        x, y = self._smooth(x, y)
        if self.last is None:
            self.last = (x, y, pressure)
            self._dab(x, y, pressure)
        else:
            lx, ly, lp = self.last
            dist = math.hypot(x - lx, y - ly)
            step = max(0.6, self.size * self.spacing)
            if dist > 1e-6:
                pos = step - self._acc
                while pos <= dist:
                    t = pos / dist
                    self._dab(lx + (x - lx) * t, ly + (y - ly) * t, lp + (pressure - lp) * t)
                    pos += step
                self._acc = dist - (pos - step)
                self.last = (x, y, pressure)
        return self.flush()

    def finish(self, tx, ty, pressure=1.0):
        """Al soltar: alcanza el punto final para que el trazo llegue al cursor."""
        if self.smoothing > 0 and self.lazy is not None:
            for _ in range(24):
                if math.hypot(tx - self.lazy[0], ty - self.lazy[1]) < 0.7: break
                self.add(tx, ty, pressure)
        return self.flush()

    def flush(self):
        r, self.dirty = self.dirty, None
        if r is not None:
            self.d.refresh(*[int(v) for v in r])
        return r


# ═════════════════════════ relleno, formas, degradado ════════════════════════
def dilate(mask, n):
    for _ in range(n):
        p = np.pad(mask, 1)
        mask = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return mask


def flood_region(sample, x, y, tol=32, contiguous=True, gap=0):
    """Región (bool) que rellenaría el bote en (x, y).

    `gap` cierra huecos de hasta ~gap px en los contornos: se rellena sobre una
    imagen donde las líneas se han engrosado y luego se recupera el borde."""
    H, W = sample.shape[:2]
    if not (0 <= x < W and 0 <= y < H): return None
    tgt = sample[y, x].astype(np.int16)
    match = np.abs(sample.astype(np.int16) - tgt).max(axis=2) <= tol
    if not contiguous:
        return match
    barrier = ~match
    free = ~dilate(barrier, gap) if gap else match
    if not free[y, x]: free = match
    vis = np.zeros((H, W), bool)
    stack = [(x, y)]
    while stack:
        px, py = stack.pop()
        if vis[py, px] or not free[py, px]: continue
        # avanza por la fila (scanline) para ser rápido
        x0 = px
        while x0 > 0 and free[py, x0 - 1] and not vis[py, x0 - 1]: x0 -= 1
        x1 = px
        while x1 < W - 1 and free[py, x1 + 1] and not vis[py, x1 + 1]: x1 += 1
        vis[py, x0:x1 + 1] = True
        for ny in (py - 1, py + 1):
            if 0 <= ny < H:
                row = free[ny, x0:x1 + 1] & ~vis[ny, x0:x1 + 1]
                if row.any():
                    idx = np.flatnonzero(row)
                    starts = idx[np.r_[True, np.diff(idx) > 1]]
                    for s in starts: stack.append((x0 + int(s), ny))
    if gap: vis = dilate(vis, gap) & match
    return vis


def fill_behind(arr, mask, color, opacity=255, grow=1):
    """Pinta `mask` con `color` DETRÁS de lo que ya hay (el relleno no tapa las líneas)."""
    if grow: mask = dilate(mask, grow)
    ys, xs = np.nonzero(mask)
    if ys.size == 0: return None
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    m = mask[y0:y1, x0:x1]
    reg = arr[y0:y1, x0:x1]
    fa = (color[3] / 255.0) * (opacity / 255.0)
    ra = reg[..., 3].astype(np.float32) / 255.0
    oa = ra + fa * (1 - ra)
    safe = np.maximum(oa, 1e-6)[..., None]
    c = np.array(color[:3], np.float32)
    rgb = (reg[..., :3].astype(np.float32) * ra[..., None] + c * (fa * (1 - ra))[..., None]) / safe
    out = reg.copy()
    out[..., :3] = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(oa * 255 + 0.5, 0, 255).astype(np.uint8)
    reg[m] = out[m]
    return (x0, y0, x1, y1)


def paint_mask(arr, cov, color, opacity=255, erase=False):
    """Compone una cobertura float (H, W) con un color sobre arr. Devuelve bbox."""
    ys, xs = np.nonzero(cov > 0.002)
    if ys.size == 0: return None
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    cv = cov[y0:y1, x0:x1] * (opacity / 255.0)
    reg = arr[y0:y1, x0:x1]
    ra = reg[..., 3].astype(np.float32) / 255.0
    if erase:
        na = ra * (1 - cv)
        reg[..., 3] = (na * 255 + 0.5).astype(np.uint8); reg[na <= 0.002, :3] = 0
        return (x0, y0, x1, y1)
    cv = cv * (color[3] / 255.0)
    c = np.array(color[:3], np.float32)
    oa = cv + ra * (1 - cv)
    safe = np.maximum(oa, 1e-6)[..., None]
    rgb = (c * cv[..., None] + reg[..., :3].astype(np.float32) * (ra * (1 - cv))[..., None]) / safe
    reg[..., :3] = np.clip(rgb + 0.5, 0, 255).astype(np.uint8)
    reg[..., 3] = np.clip(oa * 255 + 0.5, 0, 255).astype(np.uint8)
    return (x0, y0, x1, y1)


def shape_coverage(w, h, kind, pts, width=2.0, fill=False, closed=False, ss=3):
    """Cobertura antialias (H, W) de línea / rectángulo / elipse / polilínea."""
    big = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(big)
    P = [(x * ss, y * ss) for x, y in pts]
    lw = max(1, int(round(width * ss)))
    if kind == "line":
        d.line(P, fill=255, width=lw)
        r = lw / 2
        for x, y in (P[0], P[-1]): d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    elif kind == "rect":
        (x0, y0), (x1, y1) = P[0], P[-1]
        box = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
        if fill: d.rectangle(box, fill=255)
        else: d.rectangle(box, outline=255, width=lw)
    elif kind == "ellipse":
        (x0, y0), (x1, y1) = P[0], P[-1]
        box = [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]
        if fill: d.ellipse(box, fill=255)
        else: d.ellipse(box, outline=255, width=lw)
    elif kind == "poly":
        if fill and len(P) >= 3: d.polygon(P, fill=255)
        pp = P + ([P[0]] if closed and len(P) > 2 else [])
        d.line(pp, fill=255, width=lw, joint="curve")
    small = big.resize((w, h), Image.BOX)
    return np.asarray(small, dtype=np.float32) / 255.0


def gradient_array(w, h, p0, p1, c0, c1, radial=False):
    ys, xs = np.mgrid[:h, :w].astype(np.float32)
    if radial:
        r = max(1.0, math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
        t = np.clip(np.hypot(xs - p0[0], ys - p0[1]) / r, 0, 1)
    else:
        vx, vy = p1[0] - p0[0], p1[1] - p0[1]
        n = vx * vx + vy * vy
        t = np.clip(((xs - p0[0]) * vx + (ys - p0[1]) * vy) / n, 0, 1) if n else np.zeros_like(xs)
    a, b = np.array(c0, np.float32), np.array(c1, np.float32)
    return (a + (b - a) * t[..., None]).astype(np.uint8)
