"""
Editor de animación — AnimaLinux  (v3 profesional)
Pincel suave, múltiples tipos de pincel, capas con blend modes extendidos,
zoom continuo, simetría, smudge, gradiente, formas, varita mágica,
selección, colores recientes, HSV, HEX y papel cebolla rojo/azul.

Atajos: B=pincel  E=borrador  U=difuminar  F=relleno  G=gradiente
        L=línea  I=cuentagotas  S=selección  M=mover  W=varita
        X=cambiar FG/BG
        Z/Ctrl+Z=deshacer  Y/Ctrl+Y=rehacer
        [ ]=tamaño pincel   Ctrl+Scroll=zoom   Espacio+drag=pan
"""
import colorsys
import math
from collections import deque
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Gio

import cairo
from PIL import Image, ImageDraw, ImageFilter

try:
    import numpy as np
    _NP = True
except ImportError:
    _NP = False

# ── constantes ───────────────────────────────────────────────────────────────
ZOOM_MIN    = 0.05
ZOOM_MAX    = 32.0
MAX_UNDO    = 30
ONION_ALPHA = 0.25
THUMB       = 56
MAX_FRAMES  = 120
STAB_FACTOR = 0.55

BLEND_MODES = [
    "Normal", "Multiplicar", "Pantalla", "Superponer",
    "Añadir", "Diferencia", "Luz dura", "Luz suave",
    "Eludir color", "Quemar color",
]

BRUSH_TYPES  = ["round", "pencil", "airbrush", "texture",
                 "chalk", "watercolor", "marker", "crayon", "sponge", "pixel",
                 "fan", "ink"]
BRUSH_LABELS = ["Redondo suave", "Lápiz (duro)", "Aerógrafo", "Textura",
                 "Tiza", "Acuarela", "Marcador", "Crayón", "Esponja", "Píxel exacto",
                 "Abanico", "Tinta (pluma)"]

RANDOM_BRUSHES = {"texture", "watercolor", "sponge", "chalk"}


# ── helpers ──────────────────────────────────────────────────────────────────
from .editor_utils import pil_to_cairo as _pil_to_cairo  # noqa: E402
from .icons import icon_image, icon_button  # noqa: E402


def _make_stamp(radius: int, softness: float, color, opacity: int,
                brush_type: str = "round") -> Image.Image:
    size = max(3, radius * 2 + 2)
    if _NP:
        cx = cy = radius
        ys, xs = np.ogrid[:size, :size]
        d = np.sqrt((xs - cx)**2 + (ys - cy)**2)

        if brush_type == "pencil":
            t = (d <= radius).astype(np.float32)
        elif brush_type == "airbrush":
            sig = max(radius, 1)
            t = np.exp(-0.5 * (d / sig) ** 2) * 0.35
        elif brush_type == "texture":
            soft = np.clip(1.0 - d / max(radius, 1), 0, 1) ** (1.0 / max(softness, 0.05))
            noise = np.random.rand(size, size).astype(np.float32)
            t = soft * noise
        elif brush_type == "chalk":
            # bordes duros granulados como tiza
            soft  = np.clip(1.0 - d / max(radius, 1), 0, 1)
            grain = (np.random.rand(size, size) * 0.6 + 0.4).astype(np.float32)
            t = np.where(d < radius * 0.9, soft * grain * 0.85, 0)
        elif brush_type == "watercolor":
            # borde irregular, semi-transparente, efecto mojado
            warp = (np.sin(np.arctan2(ys - cy, xs - cx) * 7) * 0.15 +
                    np.random.rand(size, size).astype(np.float32) * 0.08)
            d2 = np.clip(d / max(radius, 1) + warp, 0, 2)
            t = np.clip(1.0 - d2, 0, 1) ** 0.4 * 0.55
        elif brush_type == "marker":
            # plano y sólido, borde ligeramente suave
            inner = radius * 0.82
            t = np.where(d <= inner, 0.9,
                np.clip(0.9 * (1.0 - (d - inner) / max(radius - inner, 1)), 0, 1))
        elif brush_type == "crayon":
            # rayas direccionales como crayón
            soft   = np.clip(1.0 - d / max(radius, 1), 0, 1) ** 1.5
            streak = (np.abs(np.sin((xs * 0.7 + ys * 0.25) * math.pi * 0.8))
                      * 0.5 + 0.5).astype(np.float32)
            noise  = np.random.rand(size, size).astype(np.float32) * 0.25
            t = soft * (streak * 0.75 + noise)
        elif brush_type == "sponge":
            # puntos dispersos superpuestos
            t  = np.zeros((size, size), dtype=np.float32)
            dr = max(2, radius // 4)
            rng = np.random.default_rng(radius * 7)
            ndots = max(6, radius * 4)
            offsets = rng.integers(-radius, radius + 1, (ndots, 2))
            for ddx, ddy in offsets:
                if ddx*ddx + ddy*ddy > radius*radius: continue
                d2 = np.sqrt((xs - (cx + ddx))**2 + (ys - (cy + ddy))**2)
                t  = np.maximum(t, np.clip(1.0 - d2 / max(dr, 1), 0, 1))
            t *= 0.72
        elif brush_type == "pixel":
            # círculo exacto, sin anti-aliasing
            t = (d <= radius + 0.5).astype(np.float32)
        elif brush_type == "fan":
            # abanico: semicírculo con rayas radiales
            angle = np.arctan2(ys - cy, xs - cx)
            mask  = (d <= radius).astype(np.float32)
            rays  = (np.cos(angle * 8) * 0.5 + 0.5)
            soft  = np.clip(1.0 - d / max(radius, 1), 0, 1) ** 0.5
            t = mask * rays * soft * 0.8
        elif brush_type == "ink":
            # pluma de tinta: punta elíptica, más opaca en centro
            d_ell = np.sqrt(((xs - cx) * 1.6)**2 + (ys - cy)**2)
            t = np.clip(1.0 - d_ell / max(radius, 1), 0, 1) ** 0.7
        else:  # round
            t = np.clip(1.0 - d / max(radius, 1), 0, 1) ** (1.0 / max(softness, 0.05))

        alpha = (t * opacity).clip(0, 255).astype(np.uint8)
        arr   = np.zeros((size, size, 4), dtype=np.uint8)
        arr[:, :, 0] = color[0]; arr[:, :, 1] = color[1]
        arr[:, :, 2] = color[2]; arr[:, :, 3] = alpha
        return Image.fromarray(arr, "RGBA")

    # fallback sin numpy
    im  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    cx = cy = radius
    for r in range(radius, -1, -1):
        t = (1.0 - r / max(radius, 1)) ** (1.0 / max(softness, 0.05))
        draw.ellipse([cx-r, cy-r, cx+r, cy+r],
                     fill=(*color[:3], int(opacity * t)))
    return im


def _chaikin(pts, iters=2):
    """Suavizado de trazo: algoritmo de Chaikin (curva de subdivisión)."""
    for _ in range(iters):
        new = []
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]; x1, y1 = pts[i + 1]
            new.append((0.75*x0 + 0.25*x1, 0.75*y0 + 0.25*y1))
            new.append((0.25*x0 + 0.75*x1, 0.25*y0 + 0.75*y1))
        pts = [pts[0]] + new + [pts[-1]]
    return pts


def _apply_camera(im: Image.Image, cam: dict) -> Image.Image:
    """Aplica transformación de cámara (translate, scale, rotate) a la imagen compuesta."""
    w, h = im.size
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cx, cy = w / 2, h / 2
    angle  = -cam.get("rot", 0.0)
    scale  = cam.get("scale", 1.0)
    tx, ty = cam.get("tx", 0.0), cam.get("ty", 0.0)
    if scale != 1.0:
        new_w, new_h = int(w * scale), int(h * scale)
        im = im.resize((new_w, new_h), Image.LANCZOS)
        paste_x = int(cx - new_w/2 + tx)
        paste_y = int(cy - new_h/2 + ty)
        out.paste(im, (paste_x, paste_y), im)
    else:
        out.paste(im, (int(tx), int(ty)), im)
    if angle != 0.0:
        out = out.rotate(angle, resample=Image.BICUBIC, center=(cx, cy), expand=False)
    return out


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


def _blend_images(base: Image.Image, top: Image.Image,
                  mode: str, opacity: int) -> Image.Image:
    if opacity == 0: return base.copy()
    if not _NP or mode == "Normal":
        if opacity < 255:
            r, g, b, a = top.split()
            a = a.point(lambda x: x * opacity // 255)
            top = Image.merge("RGBA", (r, g, b, a))
        result = base.copy()
        result.alpha_composite(top)
        return result

    b = np.array(base, dtype=np.float32) / 255.0
    t = np.array(top,  dtype=np.float32) / 255.0
    t[:, :, 3] *= opacity / 255.0

    br, bg, bb = b[:, :, 0], b[:, :, 1], b[:, :, 2]
    tr, tg, tb = t[:, :, 0], t[:, :, 1], t[:, :, 2]

    if mode == "Multiplicar":
        cr2, cg2, cb2 = br*tr, bg*tg, bb*tb
    elif mode == "Pantalla":
        cr2 = 1-(1-br)*(1-tr); cg2 = 1-(1-bg)*(1-tg); cb2 = 1-(1-bb)*(1-tb)
    elif mode == "Superponer":
        cr2 = np.where(br<0.5, 2*br*tr, 1-2*(1-br)*(1-tr))
        cg2 = np.where(bg<0.5, 2*bg*tg, 1-2*(1-bg)*(1-tg))
        cb2 = np.where(bb<0.5, 2*bb*tb, 1-2*(1-bb)*(1-tb))
    elif mode == "Añadir":
        cr2 = np.clip(br+tr, 0, 1); cg2 = np.clip(bg+tg, 0, 1); cb2 = np.clip(bb+tb, 0, 1)
    elif mode == "Diferencia":
        cr2, cg2, cb2 = np.abs(br-tr), np.abs(bg-tg), np.abs(bb-tb)
    elif mode == "Luz dura":
        cr2 = np.where(tr<0.5, 2*br*tr, 1-2*(1-br)*(1-tr))
        cg2 = np.where(tg<0.5, 2*bg*tg, 1-2*(1-bg)*(1-tg))
        cb2 = np.where(tb<0.5, 2*bb*tb, 1-2*(1-bb)*(1-tb))
    elif mode == "Luz suave":
        cr2 = (1-2*tr)*br**2 + 2*tr*br
        cg2 = (1-2*tg)*bg**2 + 2*tg*bg
        cb2 = (1-2*tb)*bb**2 + 2*tb*bb
    elif mode == "Eludir color":
        cr2 = np.clip(br/(1-tr+1e-7), 0, 1)
        cg2 = np.clip(bg/(1-tg+1e-7), 0, 1)
        cb2 = np.clip(bb/(1-tb+1e-7), 0, 1)
    elif mode == "Quemar color":
        cr2 = np.clip(1-(1-br)/(tr+1e-7), 0, 1)
        cg2 = np.clip(1-(1-bg)/(tg+1e-7), 0, 1)
        cb2 = np.clip(1-(1-bb)/(tb+1e-7), 0, 1)
    else:
        cr2, cg2, cb2 = tr, tg, tb

    ta = t[:, :, 3:4]; ba = b[:, :, 3:4]
    out_a = ta + ba*(1-ta)
    safe  = np.where(out_a > 0, out_a, 1)
    mixed = np.stack([cr2, cg2, cb2], axis=2)
    out_rgb = np.where(out_a > 0, (mixed*ta + b[:,:,:3]*ba*(1-ta))/safe, 0)
    out = np.clip(np.concatenate([out_rgb, out_a*255], axis=2), 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


# ── Layer ────────────────────────────────────────────────────────────────────
class Layer:
    def __init__(self, w: int, h: int, name: str = "Capa"):
        self.name         = name
        self.image        = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        self.visible      = True
        self.opacity      = 255
        self.blend_mode   = "Normal"
        self.locked       = False
        self.alpha_locked = False


# ── PaintCanvas ──────────────────────────────────────────────────────────────
class PaintCanvas(Gtk.DrawingArea):
    def __init__(self, cw: int = 512, ch: int = 512):
        super().__init__()
        self.cw, self.ch = cw, ch

        self.tool       = "brush"
        self.fg_color   = (0, 0, 0, 255)
        self.bg_color   = (255, 255, 255, 255)
        self.brush_r    = 12
        self.softness   = 0.5
        self.opacity    = 200
        self.onion      = False
        self.stabilizer = True
        self.symmetry   = "none"
        self.brush_type = "round"
        self.magic_wand_tolerance = 32
        self.smooth_strokes = False
        self._pressure  = 1.0
        self._stroke_pts: list[tuple] = []
        self._prestroke_snap = None

        self._frames: list[list[Layer]] = [[Layer(cw, ch, "Capa 1")]]
        self._frame_labels: list[str] = [""]
        self._frame_camera: list[dict] = [{"tx": 0.0, "ty": 0.0, "scale": 1.0, "rot": 0.0}]
        self._cur    = 0
        self._active = 0
        self._clip_frame: list[Layer] | None = None

        self._zoom = 1.0
        self._off  = [0.0, 0.0]

        self._comp_cache: dict[int, bytearray] = {}
        self._comp_dirty: set[int] = {0}
        self._stamp_cache: dict[tuple, Image.Image] = {}

        self._undo: list = []
        self._redo: list = []

        self._drawing    = False
        self._panning    = False
        self._space_held = False
        self._drag_sx = self._drag_sy = 0.0
        self._pan_ox  = self._pan_oy  = 0.0
        self._pan_sx  = self._pan_sy  = 0.0
        self._last_cx = self._last_cy = -1.0
        self._lazy_x: float | None = None
        self._lazy_y: float | None = None
        self._cursor_sx = self._cursor_sy = -1.0

        self._line_start    = None
        self._line_preview  = None
        self._grad_start    = None
        self._grad_preview  = None
        self._shape_start   = None
        self._shape_preview = None
        self._sel_rect      = None
        self._sel_origin    = None
        self._sel_img       = None
        self._sel_mask      = None

        self.recent_colors: deque = deque(maxlen=12)

        self.on_pick          = None
        self.on_frame_changed = None
        self.on_layer_changed = None
        self.on_cursor_moved  = None

        self.set_draw_func(self._draw)
        self.set_hexpand(True); self.set_vexpand(True); self.set_focusable(True)

        d1 = Gtk.GestureDrag(); d1.set_button(1)
        d1.connect("drag-begin",  self._db)
        d1.connect("drag-update", self._du)
        d1.connect("drag-end",    self._de)
        self.add_controller(d1)

        d2 = Gtk.GestureDrag(); d2.set_button(2)
        d2.connect("drag-begin",  self._pb)
        d2.connect("drag-update", self._pu)
        self.add_controller(d2)

        mo = Gtk.EventControllerMotion()
        mo.connect("motion", self._on_motion)
        mo.connect("leave", self._on_leave)
        self.add_controller(mo)

        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        sc.connect("scroll", self._on_scroll)
        self.add_controller(sc)

        ky = Gtk.EventControllerKey()
        ky.connect("key-pressed",  self._on_kp)
        ky.connect("key-released", self._on_kr)
        self.add_controller(ky)

        # presión de tableta / stylus via eventos legacy
        leg = Gtk.EventControllerLegacy()
        leg.connect("event", self._on_legacy_event)
        self.add_controller(leg)

    def _on_legacy_event(self, ctrl, event):
        """Captura presión de stylus/tableta."""
        if event is None:
            return False
        try:
            t = event.get_event_type()
            if t in (Gdk.EventType.MOTION_NOTIFY, Gdk.EventType.BUTTON_PRESS):
                ok, val = event.get_axis(Gdk.AxisUse.PRESSURE)
                if ok and val > 0:
                    self._pressure = float(val)
                else:
                    self._pressure = 1.0
        except Exception:
            pass
        return False

    # ── coordenadas ──────────────────────────────────────────────────────────
    def _origin(self):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        ox = self._off[0] + (w - self.cw * self._zoom) / 2
        oy = self._off[1] + (h - self.ch * self._zoom) / 2
        return ox, oy

    def _s2c(self, sx, sy):
        ox, oy = self._origin()
        return (sx - ox) / self._zoom, (sy - oy) / self._zoom

    # ── zoom ─────────────────────────────────────────────────────────────────
    def zoom_at(self, factor, sx, sy):
        old = self._zoom
        new = max(ZOOM_MIN, min(ZOOM_MAX, old * factor))
        if new == old: return
        cx, cy = self._s2c(sx, sy)
        self._zoom = new
        ox, oy = self._origin()
        self._off[0] += sx - (ox + cx * new)
        self._off[1] += sy - (oy + cy * new)
        self.queue_draw()

    def zoom_fit(self):
        w = self.get_allocated_width(); h = self.get_allocated_height()
        if w <= 0 or h <= 0: return
        self._zoom = min(w / self.cw, h / self.ch) * 0.92
        self._off  = [0.0, 0.0]; self.queue_draw()

    # ── estabilizador ─────────────────────────────────────────────────────────
    def _stabilize(self, cx, cy):
        if not self.stabilizer or self._lazy_x is None:
            self._lazy_x, self._lazy_y = float(cx), float(cy)
        else:
            f = STAB_FACTOR
            self._lazy_x += (cx - self._lazy_x) * (1 - f)
            self._lazy_y += (cy - self._lazy_y) * (1 - f)
        return self._lazy_x, self._lazy_y

    # ── capas ─────────────────────────────────────────────────────────────────
    @property
    def active_layer(self) -> Layer:
        layers = self._frames[self._cur]
        return layers[max(0, min(self._active, len(layers) - 1))]

    def _sym_points(self, cx: int, cy: int):
        pts = [(cx, cy)]
        if self.symmetry in ("h", "hv"):  pts.append((self.cw - 1 - cx, cy))
        if self.symmetry in ("v", "hv"):  pts.append((cx, self.ch - 1 - cy))
        if self.symmetry == "hv":         pts.append((self.cw - 1 - cx, self.ch - 1 - cy))
        return pts

    # ── stamp cache ───────────────────────────────────────────────────────────
    def _stamp(self, color=None) -> Image.Image:
        c = color or self.fg_color
        eff_opacity = max(1, int(self.opacity * self._pressure))
        if self.brush_type in RANDOM_BRUSHES:
            return _make_stamp(self.brush_r, self.softness, c, eff_opacity, self.brush_type)
        key = (self.brush_r, round(self.softness, 2), c, eff_opacity, self.brush_type)
        if key not in self._stamp_cache:
            if len(self._stamp_cache) > 64:
                self._stamp_cache.pop(next(iter(self._stamp_cache)))
            self._stamp_cache[key] = _make_stamp(
                self.brush_r, self.softness, c, eff_opacity, self.brush_type)
        return self._stamp_cache[key]

    # ── undo/redo ─────────────────────────────────────────────────────────────
    def _snapshot(self):
        snap = []
        for frame in self._frames:
            snap.append([(l.name, l.image.copy(), l.visible, l.opacity,
                          l.blend_mode, l.locked, l.alpha_locked)
                         for l in frame])
        return snap

    def snap_undo(self):
        self._undo.append(self._snapshot())
        if len(self._undo) > MAX_UNDO: self._undo.pop(0)
        self._redo.clear()

    def _restore(self, snap):
        self._frames = []
        for frame_snap in snap:
            layers = []
            for name, img, vis, opa, bm, lk, alk in frame_snap:
                l = Layer(self.cw, self.ch, name)
                l.image = img; l.visible = vis; l.opacity = opa
                l.blend_mode = bm; l.locked = lk; l.alpha_locked = alk
                layers.append(l)
            self._frames.append(layers)
        self._cur    = min(self._cur, len(self._frames) - 1)
        self._active = min(self._active, len(self._frames[self._cur]) - 1)
        self._comp_dirty = set(range(len(self._frames)))

    def _restore_snap(self, snap):
        """Restaura un snapshot dado sin toccar undo/redo (para smooth strokes)."""
        self._restore(snap)

    def undo(self):
        if not self._undo: return
        self._redo.append(self._snapshot()); self._restore(self._undo.pop())
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()
        if self.on_layer_changed: self.on_layer_changed()

    def redo(self):
        if not self._redo: return
        self._undo.append(self._snapshot()); self._restore(self._redo.pop())
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()
        if self.on_layer_changed: self.on_layer_changed()

    # ── composición ───────────────────────────────────────────────────────────
    def _composite(self, fi: int) -> Image.Image:
        result = Image.new("RGBA", (self.cw, self.ch), (0, 0, 0, 0))
        for layer in self._frames[fi]:
            if layer.visible:
                result = _blend_images(result, layer.image, layer.blend_mode, layer.opacity)
        # aplicar cámara si hay transformación
        cam = self._frame_camera[fi] if fi < len(self._frame_camera) else None
        if cam and (cam["tx"] != 0 or cam["ty"] != 0 or cam["scale"] != 1.0 or cam["rot"] != 0.0):
            result = _apply_camera(result, cam)
        return result

    def _get_surf(self, fi: int) -> cairo.ImageSurface:
        if fi in self._comp_dirty or fi not in self._comp_cache:
            data = _pil_to_cairo(self._composite(fi))
            self._comp_cache[fi] = data; self._comp_dirty.discard(fi)
        d = self._comp_cache[fi]
        return cairo.ImageSurface.create_for_data(
            d, cairo.Format.ARGB32, self.cw, self.ch, self.cw * 4)

    def _dirty(self): self._comp_dirty.add(self._cur)

    # ── herramientas de dibujo ────────────────────────────────────────────────
    def _do_brush(self, cx: float, cy: float):
        layer = self.active_layer
        if layer.locked: return
        img   = layer.image
        stamp = self._stamp()
        sw, sh = stamp.size

        if layer.alpha_locked and _NP:
            alpha_orig = np.array(img)[:, :, 3].copy()

        for px, py in self._sym_points(int(cx), int(cy)):
            tmp = Image.new("RGBA", img.size, (0, 0, 0, 0))
            try: tmp.paste(stamp, (px - sw//2, py - sh//2), stamp)
            except Exception: pass
            img.alpha_composite(tmp)

        if layer.alpha_locked and _NP:
            arr = np.array(img)
            arr[:, :, 3] = alpha_orig
            layer.image = Image.fromarray(arr, "RGBA")

        self._dirty()

    def _do_eraser(self, cx: float, cy: float):
        layer = self.active_layer
        if layer.locked: return
        img = layer.image
        if _NP:
            arr = np.array(img)
            for px, py in self._sym_points(int(cx), int(cy)):
                r = self.brush_r
                ys, xs = np.ogrid[:img.height, :img.width]
                mask = (xs-px)**2 + (ys-py)**2 <= r*r
                arr[mask, 3] = np.maximum(
                    0, arr[mask, 3].astype(int) - self.opacity).astype(np.uint8)
            layer.image = Image.fromarray(arr, "RGBA")
        else:
            draw = ImageDraw.Draw(img)
            for px, py in self._sym_points(int(cx), int(cy)):
                r = self.brush_r
                draw.ellipse([px-r, py-r, px+r, py+r], fill=(0, 0, 0, 0))
        self._dirty()

    def _do_smudge(self, cx: float, cy: float):
        layer = self.active_layer
        if layer.locked or not _NP: return
        arr = np.array(layer.image)
        r   = max(2, self.brush_r)
        for px, py in self._sym_points(int(cx), int(cy)):
            x1, y1 = max(0, px-r), max(0, py-r)
            x2, y2 = min(self.cw, px+r+1), min(self.ch, py+r+1)
            if x2 <= x1 or y2 <= y1: continue
            patch = arr[y1:y2, x1:x2, :3]
            blurred = np.array(
                Image.fromarray(patch, "RGB").filter(
                    ImageFilter.GaussianBlur(radius=max(1, r//3))))
            arr[y1:y2, x1:x2, :3] = blurred
        layer.image = Image.fromarray(arr, "RGBA")
        self._dirty()

    def _do_fill(self, cx: float, cy: float):
        layer = self.active_layer
        if layer.locked: return
        x, y = max(0, min(int(cx), self.cw-1)), max(0, min(int(cy), self.ch-1))
        img  = layer.image
        target = img.getpixel((x, y))
        nc = tuple(self.fg_color)
        if tuple(target) == nc: return
        if _NP:
            arr = np.array(img)
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
            layer.image = Image.fromarray(arr, "RGBA")
        else:
            ImageDraw.floodfill(img, (x, y), nc)
        self._dirty()

    def _do_gradient(self, x1: float, y1: float, x2: float, y2: float):
        layer = self.active_layer
        if layer.locked or not _NP: return
        dx, dy = x2-x1, y2-y1
        length = math.sqrt(dx*dx + dy*dy)
        if length < 1: return
        arr = np.array(layer.image, dtype=np.float32)
        h, w = arr.shape[:2]
        ys, xs = np.mgrid[:h, :w]
        t = np.clip(((xs-x1)*dx + (ys-y1)*dy) / (length*length), 0, 1)
        fg = np.array(self.fg_color, dtype=np.float32)
        bg = np.array(self.bg_color, dtype=np.float32)
        grad = fg[None,None,:] * (1-t[:,:,None]) + bg[None,None,:] * t[:,:,None]
        ga, aa = grad[:,:,3:4]/255.0, arr[:,:,3:4]/255.0
        out_a = ga + aa*(1-ga)
        safe  = np.where(out_a > 0, out_a, 1)
        rgb   = (grad[:,:,:3]*ga + arr[:,:,:3]*aa*(1-ga)) / safe
        out   = np.clip(np.concatenate([rgb, out_a*255], axis=2), 0, 255).astype(np.uint8)
        layer.image = Image.fromarray(out, "RGBA")
        self._dirty()

    def _do_pick(self, cx: float, cy: float):
        x, y = int(cx), int(cy)
        if 0 <= x < self.cw and 0 <= y < self.ch:
            c = self._composite(self._cur).getpixel((x, y))
            self._add_recent(c)
            if self.on_pick: self.on_pick(c)

    def _do_magic_wand(self, cx: float, cy: float):
        x, y = int(cx), int(cy)
        x, y = max(0, min(x, self.cw-1)), max(0, min(y, self.ch-1))
        tol = getattr(self, 'magic_wand_tolerance', 32)
        img = self.active_layer.image
        target = img.getpixel((x, y))
        if _NP:
            arr = np.array(img, dtype=np.int32)
            tgt = np.array(target[:3], dtype=np.int32)
            diff = np.sqrt(np.sum((arr[:,:,:3] - tgt[None,None,:])**2, axis=2))
            mask = (diff <= tol)
            rows = np.any(mask, axis=1); cols = np.any(mask, axis=0)
            if rows.any():
                self._sel_rect = (float(cols.argmax()), float(rows.argmax()),
                                  float(self.cw-1-cols[::-1].argmax()),
                                  float(self.ch-1-rows[::-1].argmax()))
                self._sel_mask = mask
        self._dirty(); self.queue_draw()

    def _do_shape(self, x1: float, y1: float, x2: float, y2: float):
        layer = self.active_layer
        if layer.locked: return
        img  = layer.image
        draw = ImageDraw.Draw(img)
        ix1, iy1 = int(min(x1,x2)), int(min(y1,y2))
        ix2, iy2 = int(max(x1,x2)), int(max(y1,y2))
        lw = max(1, self.brush_r * 2)
        fc = tuple(self.fg_color)
        if   self.tool == "rect_fill":
            draw.rectangle([ix1,iy1,ix2,iy2], fill=fc)
        elif self.tool == "rect_outline":
            draw.rectangle([ix1,iy1,ix2,iy2], fill=None, outline=fc, width=lw)
        elif self.tool == "ellipse_fill":
            draw.ellipse([ix1,iy1,ix2,iy2], fill=fc)
        elif self.tool == "ellipse_outline":
            draw.ellipse([ix1,iy1,ix2,iy2], fill=None, outline=fc, width=lw)
        self._dirty()

    def _add_recent(self, color):
        color = tuple(color)
        if color in self.recent_colors: self.recent_colors.remove(color)
        self.recent_colors.appendleft(color)

    # ── selección / mover ─────────────────────────────────────────────────────
    def _lift_selection(self):
        if not self._sel_rect: return
        x1,y1,x2,y2 = self._sel_rect
        x1i, y1i = max(0,int(x1)), max(0,int(y1))
        x2i, y2i = min(self.cw,int(x2)+1), min(self.ch,int(y2)+1)
        if x2i<=x1i or y2i<=y1i: return
        self.snap_undo()
        img = self.active_layer.image
        self._sel_img       = img.crop((x1i,y1i,x2i,y2i)).copy()
        self._sel_lift_orig = (x1i, y1i)
        draw = ImageDraw.Draw(img)
        draw.rectangle([x1i,y1i,x2i,y2i], fill=(0,0,0,0))
        self._dirty()

    def _move_selection(self, cx, cy):
        if self._sel_img is None or self._sel_origin is None: return
        ox, oy = self._sel_origin
        x1,y1,x2,y2 = self._sel_rect
        w = x2-x1; h = y2-y1
        nx1, ny1 = x1+(cx-ox), y1+(cy-oy)
        self._sel_rect  = (nx1, ny1, nx1+w, ny1+h)
        self._sel_origin = (cx, cy)
        self.queue_draw()

    def commit_selection(self):
        if self._sel_img is None or self._sel_rect is None: return
        x1,y1,_,_ = self._sel_rect
        img = self.active_layer.image
        img.alpha_composite(self._sel_img, dest=(int(x1), int(y1)))
        self._sel_img = None; self._sel_origin = None
        self._dirty(); self.queue_draw()

    # ── pan ──────────────────────────────────────────────────────────────────
    def _pan_begin_xy(self, sx, sy):
        self._panning = True
        self._pan_ox, self._pan_oy = self._off[0], self._off[1]
        self._pan_sx, self._pan_sy = sx, sy

    def _pb(self, g, sx, sy): self._pan_begin_xy(sx, sy)

    def _pu(self, g, dx, dy):
        if not self._panning: return
        self._off[0] = self._pan_ox + dx; self._off[1] = self._pan_oy + dy
        self.queue_draw()

    # ── entrada gestos ────────────────────────────────────────────────────────
    def _db(self, g, sx, sy):
        self._drag_sx, self._drag_sy = sx, sy
        self._lazy_x = self._lazy_y = None
        if self._space_held:
            self._pan_begin_xy(sx, sy); return
        self._drawing = True
        cx, cy = self._s2c(sx, sy)

        if self.tool in ("gradient", "line"):
            self.snap_undo()
            self._grad_start = (cx, cy); self._grad_preview = None; return

        if self.tool in ("rect_fill","rect_outline","ellipse_fill","ellipse_outline"):
            self.snap_undo()
            self._shape_start = (cx, cy); self._shape_preview = None; return

        if self.tool == "select":
            self._sel_rect   = (cx, cy, cx, cy)
            self._sel_origin = None; self._sel_img = None
            self.queue_draw(); return

        if self.tool == "move":
            if self._sel_rect and self._sel_img is None:
                self._lift_selection()
            self._sel_origin = (cx, cy); return

        if self.tool == "magic_wand":
            self._do_magic_wand(cx, cy); return

        if self.tool == "vec_pen":
            layer = self.active_layer
            if isinstance(layer, VectorLayer):
                self.snap_undo()
                layer.begin_path(int(cx), int(cy), self.fg_color, max(1, self.brush_r//2))
            return

        self.snap_undo()
        self._prestroke_snap = self._snapshot() if self.smooth_strokes else None
        self._stroke_pts = []
        lx, ly = self._stabilize(cx, cy)
        self._apply_point(int(lx), int(ly))
        self._last_cx, self._last_cy = lx, ly
        self._stroke_pts.append((lx, ly))
        self.queue_draw()

    def _du(self, g, dx, dy):
        if self._space_held and self._panning:
            self._pu(g, dx, dy); return
        if not self._drawing: return
        cx, cy = self._s2c(self._drag_sx+dx, self._drag_sy+dy)

        if self.tool in ("gradient","line"):
            self._grad_preview = (cx, cy); self.queue_draw(); return

        if self.tool in ("rect_fill","rect_outline","ellipse_fill","ellipse_outline"):
            self._shape_preview = (cx, cy); self.queue_draw(); return

        if self.tool == "select":
            x0,y0,_,_ = self._sel_rect
            self._sel_rect = (x0,y0,cx,cy); self.queue_draw(); return

        if self.tool == "move" and self._sel_rect and self._sel_origin:
            self._move_selection(cx, cy); return

        if self.tool == "vec_pen":
            layer = self.active_layer
            if isinstance(layer, VectorLayer):
                layer.add_point(int(cx), int(cy)); self.queue_draw()
            return

        lx, ly = self._stabilize(cx, cy)
        if self.tool in ("brush","eraser","smudge"):
            for px, py in _interp(int(self._last_cx), int(self._last_cy),
                                   int(lx), int(ly)):
                self._apply_point(px, py)
            self._last_cx, self._last_cy = lx, ly
            self._stroke_pts.append((lx, ly))
        elif self.tool == "fill":
            self._apply_point(int(lx), int(ly))
        self.queue_draw()

    def _de(self, g, dx, dy):
        if self._space_held: self._panning = False; return
        if not self._drawing: self._drawing = False; return
        cx, cy = self._s2c(self._drag_sx+dx, self._drag_sy+dy)

        if self.tool == "line" and self._grad_start:
            img  = self.active_layer.image
            draw = ImageDraw.Draw(img)
            lw   = max(1, self.brush_r * 2)
            draw.line([tuple(map(int, self._grad_start)), (int(cx), int(cy))],
                      fill=tuple(self.fg_color), width=lw)
            self._dirty()
            self._grad_start = self._grad_preview = None

        elif self.tool == "gradient" and self._grad_start:
            self._do_gradient(*self._grad_start, cx, cy)
            self._grad_start = self._grad_preview = None

        elif self.tool in ("rect_fill","rect_outline","ellipse_fill","ellipse_outline"):
            if self._shape_start:
                self._do_shape(*self._shape_start, cx, cy)
            self._shape_start = self._shape_preview = None

        elif self.tool == "select":
            x0,y0,_,_ = self._sel_rect
            self._sel_rect = (min(x0,cx), min(y0,cy), max(x0,cx), max(y0,cy))

        elif self.tool == "pick":
            self._do_pick(cx, cy)

        elif self.tool == "vec_pen":
            layer = self.active_layer
            if isinstance(layer, VectorLayer):
                layer.add_point(int(cx), int(cy))
                layer.end_path(closed=False)
                self._dirty(); self.queue_draw()
                if self.on_layer_changed: self.on_layer_changed()

        # suavizado de trazo post-stroke (Chaikin)
        if (self.smooth_strokes and self._prestroke_snap
                and self.tool in ("brush","eraser")
                and len(self._stroke_pts) > 4):
            self._restore_snap(self._prestroke_snap)
            smoothed = _chaikin(self._stroke_pts, iters=3)
            for i in range(len(smoothed) - 1):
                for px, py in _interp(int(smoothed[i][0]),   int(smoothed[i][1]),
                                       int(smoothed[i+1][0]), int(smoothed[i+1][1])):
                    self._apply_point(px, py)
            self._dirty()

        self._stroke_pts = []; self._prestroke_snap = None
        self._drawing = False; self.queue_draw()

    def _apply_point(self, cx: int, cy: int):
        if   self.tool == "brush":  self._do_brush(cx, cy)
        elif self.tool == "eraser": self._do_eraser(cx, cy)
        elif self.tool == "smudge": self._do_smudge(cx, cy)
        elif self.tool == "fill":   self._do_fill(cx, cy)
        elif self.tool == "pick":   self._do_pick(cx, cy)

    # ── motion / scroll / teclado ─────────────────────────────────────────────
    def _on_motion(self, ctrl, sx, sy):
        self._cursor_sx, self._cursor_sy = sx, sy
        cx, cy = self._s2c(sx, sy)
        if self.on_cursor_moved and 0 <= int(cx) < self.cw and 0 <= int(cy) < self.ch:
            comp  = self._composite(self._cur)
            color = comp.getpixel((int(cx), int(cy)))
            self.on_cursor_moved(cx, cy, color)
        self.queue_draw()

    def _on_leave(self, ctrl):
        # al salir del canvas, oculta el cursor de pincel para que no quede
        # un círculo "fantasma" dibujado encima del lienzo
        self._cursor_sx = self._cursor_sy = -1.0
        self.queue_draw()

    def _on_scroll(self, ctrl, dx, dy):
        mods = ctrl.get_current_event_state()
        if mods & Gdk.ModifierType.CONTROL_MASK:
            factor = 0.8 if dy > 0 else 1.25
            self.zoom_at(factor, self._cursor_sx, self._cursor_sy)
            return True
        return False

    def _on_kp(self, ctrl, kv, kc, mods):
        if Gdk.keyval_name(kv) == "space":
            self._space_held = True
            if not self._panning and not self._drawing:
                self._pan_begin_xy(self._cursor_sx, self._cursor_sy)
            return True
        return False

    def _on_kr(self, ctrl, kv, kc, mods):
        if Gdk.keyval_name(kv) == "space":
            self._space_held = False; self._panning = False; return True
        return False

    # ── cairo render ──────────────────────────────────────────────────────────
    def _draw_checker(self, cr, ox, oy):
        sq, z = 16, self._zoom
        for y in range(0, self.ch, sq):
            for x in range(0, self.cw, sq):
                v = 0.22 if (x//sq + y//sq) % 2 == 0 else 0.16
                cr.set_source_rgb(v, v, v)
                cr.rectangle(ox+x*z, oy+y*z, min(sq,self.cw-x)*z, min(sq,self.ch-y)*z)
                cr.fill()

    def _draw(self, area, cr, width, height):
        ox, oy = self._origin()
        z = self._zoom

        cr.set_source_rgb(0.118, 0.118, 0.180); cr.paint()

        cr.save()
        cr.rectangle(ox, oy, self.cw*z, self.ch*z); cr.clip()
        self._draw_checker(cr, ox, oy)
        cr.restore()

        # onion skin rojo/azul multi-frame
        if self.onion:
            for delta, tint, am in [(-2,(1,.3,.3),.12),(-1,(1,.55,.55),.22),
                                     (1,(.55,.55,1),.18),(2,(.4,.6,1),.10)]:
                fi = self._cur + delta
                if 0 <= fi < len(self._frames):
                    surf = self._get_surf(fi)
                    cr.save(); cr.translate(ox, oy); cr.scale(z, z)
                    pat = cairo.SurfacePattern(surf)
                    pat.set_filter(cairo.Filter.BILINEAR)
                    cr.set_source(pat)
                    cr.paint_with_alpha(am * 3.0)
                    cr.set_source_rgba(*tint, am)
                    cr.paint(); cr.restore()

        # composición actual
        surf = self._get_surf(self._cur)
        cr.save(); cr.translate(ox, oy); cr.scale(z, z)
        pat = cairo.SurfacePattern(surf)
        pat.set_filter(cairo.Filter.BILINEAR)
        cr.set_source(pat); cr.paint()

        # preview gradiente/línea
        gp = self._grad_preview
        if self.tool in ("gradient","line") and gp and self._grad_start and self._drawing:
            cr.set_source_rgba(*(c/255 for c in self.fg_color))
            cr.set_line_width(max(1, self.brush_r))
            cr.move_to(*self._grad_start); cr.line_to(*gp); cr.stroke()
        cr.restore()

        # shape preview
        sp = self._shape_preview
        if self.tool in ("rect_fill","rect_outline","ellipse_fill","ellipse_outline"):
            if self._drawing and self._shape_start and sp:
                x1,y1 = self._shape_start; x2,y2 = sp
                rx1,ry1 = ox+min(x1,x2)*z, oy+min(y1,y2)*z
                rw,rh = abs(x2-x1)*z, abs(y2-y1)*z
                cr.set_source_rgba(*(c/255 for c in self.fg_color[:3]), 0.75)
                cr.set_line_width(1.5); cr.set_dash([4.0,4.0])
                if "rect" in self.tool:
                    cr.rectangle(rx1,ry1,rw,rh)
                else:
                    if rw > 0 and rh > 0:
                        cr.save()
                        cr.translate(rx1+rw/2, ry1+rh/2)
                        cr.scale(rw/2, rh/2)
                        cr.arc(0, 0, 1, 0, 2*math.pi)
                        cr.restore()
                cr.stroke(); cr.set_dash([])

        # borde lienzo
        cr.set_source_rgba(0.4, 0.4, 0.5, 0.5)
        cr.set_line_width(1.0)
        cr.rectangle(ox, oy, self.cw*z, self.ch*z); cr.stroke()

        self._draw_sym_guides(cr, ox, oy, z)
        self._draw_sel(cr, ox, oy, z)
        self._draw_cursor(cr, ox, oy, z)

    def _draw_sym_guides(self, cr, ox, oy, z):
        if self.symmetry == "none": return
        cr.set_source_rgba(0.8, 0.4, 1.0, 0.55)
        cr.set_line_width(1.0); cr.set_dash([6.0, 4.0])
        if self.symmetry in ("h","hv"):
            mx = ox + self.cw/2*z
            cr.move_to(mx, oy); cr.line_to(mx, oy+self.ch*z); cr.stroke()
        if self.symmetry in ("v","hv"):
            my = oy + self.ch/2*z
            cr.move_to(ox, my); cr.line_to(ox+self.cw*z, my); cr.stroke()
        cr.set_dash([])

    def _draw_sel(self, cr, ox, oy, z):
        if not self._sel_rect: return
        x1,y1,x2,y2 = self._sel_rect
        cr.set_source_rgba(0.8, 0.65, 1.0, 0.9)
        cr.set_line_width(1.0); cr.set_dash([4.0, 4.0])
        cr.rectangle(ox+x1*z, oy+y1*z, (x2-x1)*z, (y2-y1)*z); cr.stroke()
        cr.set_dash([])

    def _draw_cursor(self, cr, ox, oy, z):
        sx, sy = self._cursor_sx, self._cursor_sy
        if sx < 0: return
        cx, cy = self._s2c(sx, sy)
        if not (0 <= cx < self.cw and 0 <= cy < self.ch): return

        if self.tool in ("brush","eraser","smudge"):
            r = self.brush_r * z
            cr.set_source_rgba(1, 1, 1, 0.85); cr.set_line_width(2.0)
            cr.arc(sx, sy, max(2, r), 0, 2*math.pi); cr.stroke()
            cr.set_source_rgba(0, 0, 0, 0.45); cr.set_line_width(1.0)
            cr.arc(sx, sy, max(1, r-1.5), 0, 2*math.pi); cr.stroke()
            blue = (0.8, 0.4, 1.0, 0.7)
            if self.symmetry in ("h","hv"):
                mx = ox + (self.cw-1-cx)*z
                cr.set_source_rgba(*blue); cr.set_line_width(1.5)
                cr.arc(mx, sy, max(2, r), 0, 2*math.pi); cr.stroke()
            if self.symmetry in ("v","hv"):
                my = oy + (self.ch-1-cy)*z
                cr.set_source_rgba(*blue); cr.set_line_width(1.5)
                cr.arc(sx, my, max(2, r), 0, 2*math.pi); cr.stroke()
            if self.symmetry == "hv":
                mx2 = ox + (self.cw-1-cx)*z; my2 = oy + (self.ch-1-cy)*z
                cr.set_source_rgba(*blue); cr.set_line_width(1.5)
                cr.arc(mx2, my2, max(2, r), 0, 2*math.pi); cr.stroke()
        else:
            cr.set_source_rgba(1, 1, 1, 0.9); cr.set_line_width(1.5); sz = 8
            cr.move_to(sx-sz, sy); cr.line_to(sx+sz, sy)
            cr.move_to(sx, sy-sz); cr.line_to(sx, sy+sz); cr.stroke()

    # ── frames ────────────────────────────────────────────────────────────────
    @property
    def frame_count(self): return len(self._frames)

    def _cam_default(self):
        return {"tx": 0.0, "ty": 0.0, "scale": 1.0, "rot": 0.0}

    def _sync_meta(self):
        """Asegura que _frame_labels y _frame_camera tengan misma longitud que _frames."""
        n = len(self._frames)
        while len(self._frame_labels) < n:  self._frame_labels.append("")
        while len(self._frame_camera) < n:  self._frame_camera.append(self._cam_default())
        self._frame_labels = self._frame_labels[:n]
        self._frame_camera  = self._frame_camera[:n]

    def add_frame(self):
        self.snap_undo()
        self._frames.insert(self._cur+1, [Layer(self.cw, self.ch, "Capa 1")])
        self._frame_labels.insert(self._cur+1, "")
        self._frame_camera.insert(self._cur+1, self._cam_default())
        self._cur += 1; self._comp_dirty.add(self._cur)
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()
        if self.on_layer_changed: self.on_layer_changed()

    def duplicate_frame(self):
        self.snap_undo()
        new_layers = []
        for l in self._frames[self._cur]:
            nl = Layer(self.cw, self.ch, l.name)
            nl.image = l.image.copy(); nl.visible = l.visible
            nl.opacity = l.opacity; nl.blend_mode = l.blend_mode
            nl.locked = l.locked; nl.alpha_locked = l.alpha_locked
            new_layers.append(nl)
        self._frames.insert(self._cur+1, new_layers)
        self._frame_labels.insert(self._cur+1, self._frame_labels[self._cur])
        self._frame_camera.insert(self._cur+1, dict(self._frame_camera[self._cur]))
        self._cur += 1; self._comp_dirty.add(self._cur)
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()
        if self.on_layer_changed: self.on_layer_changed()

    def delete_frame(self):
        if len(self._frames) <= 1: return
        self.snap_undo()
        self._frames.pop(self._cur)
        if self._cur < len(self._frame_labels): self._frame_labels.pop(self._cur)
        if self._cur < len(self._frame_camera):  self._frame_camera.pop(self._cur)
        self._cur = min(self._cur, len(self._frames)-1)
        self._comp_dirty = set(range(len(self._frames)))
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()

    def go_to(self, idx: int):
        self._cur = max(0, min(idx, len(self._frames)-1))
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()
        if self.on_layer_changed: self.on_layer_changed()

    def copy_frame(self):
        src = self._frames[self._cur]
        clip = []
        for l in src:
            nl = Layer(self.cw, self.ch, l.name)
            nl.image = l.image.copy(); nl.visible = l.visible
            nl.opacity = l.opacity; nl.blend_mode = l.blend_mode
            nl.locked = l.locked; nl.alpha_locked = l.alpha_locked
            clip.append(nl)
        self._clip_frame = clip

    def paste_frame(self):
        if self._clip_frame is None: return
        self.snap_undo()
        new_layers = []
        for l in self._clip_frame:
            nl = Layer(self.cw, self.ch, l.name)
            nl.image = l.image.copy(); nl.visible = l.visible
            nl.opacity = l.opacity; nl.blend_mode = l.blend_mode
            nl.locked = l.locked; nl.alpha_locked = l.alpha_locked
            new_layers.append(nl)
        self._frames.insert(self._cur+1, new_layers)
        self._cur += 1; self._comp_dirty.add(self._cur)
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()
        if self.on_layer_changed: self.on_layer_changed()

    # ── operaciones de capa ───────────────────────────────────────────────────
    def add_layer(self):
        self.snap_undo()
        layers = self._frames[self._cur]
        layers.append(Layer(self.cw, self.ch, f"Capa {len(layers)+1}"))
        self._active = len(layers)-1
        self._dirty(); self.queue_draw()
        if self.on_layer_changed: self.on_layer_changed()

    def delete_layer(self):
        layers = self._frames[self._cur]
        if len(layers) <= 1: return
        self.snap_undo()
        layers.pop(self._active)
        self._active = max(0, self._active-1)
        self._dirty(); self.queue_draw()
        if self.on_layer_changed: self.on_layer_changed()

    def duplicate_layer(self):
        self.snap_undo()
        layers = self._frames[self._cur]
        src = layers[self._active]
        nl = Layer(self.cw, self.ch, src.name+" copia")
        nl.image = src.image.copy(); nl.visible = src.visible
        nl.opacity = src.opacity; nl.blend_mode = src.blend_mode
        nl.locked = src.locked; nl.alpha_locked = src.alpha_locked
        layers.insert(self._active+1, nl)
        self._active += 1
        self._dirty(); self.queue_draw()
        if self.on_layer_changed: self.on_layer_changed()

    def merge_down(self):
        layers = self._frames[self._cur]
        if self._active == 0: return
        self.snap_undo()
        top = layers[self._active]; bot = layers[self._active-1]
        bot.image = _blend_images(bot.image, top.image, top.blend_mode, top.opacity)
        layers.pop(self._active); self._active -= 1
        self._dirty(); self.queue_draw()
        if self.on_layer_changed: self.on_layer_changed()

    def flatten(self):
        self.snap_undo()
        comp = self._composite(self._cur)
        nl = Layer(self.cw, self.ch, "Fondo"); nl.image = comp
        self._frames[self._cur] = [nl]; self._active = 0
        self._dirty(); self.queue_draw()
        if self.on_layer_changed: self.on_layer_changed()

    def move_layer(self, delta: int):
        layers = self._frames[self._cur]
        i, j = self._active, self._active+delta
        if not (0 <= j < len(layers)): return
        self.snap_undo()
        layers[i], layers[j] = layers[j], layers[i]
        self._active = j
        self._dirty(); self.queue_draw()
        if self.on_layer_changed: self.on_layer_changed()

    def set_layer_prop(self, idx, **kw):
        layers = self._frames[self._cur]
        if not (0 <= idx < len(layers)): return
        l = layers[idx]
        for k, v in kw.items(): setattr(l, k, v)
        self._dirty(); self.queue_draw()

    # ── importar / cargar ─────────────────────────────────────────────────────
    def import_image(self, path):
        im = Image.open(path).convert("RGBA").resize((self.cw,self.ch), Image.LANCZOS)
        self.snap_undo()
        self.active_layer.image = im
        self._dirty(); self.queue_draw()

    def load_from_dir(self, frames_dir: Path):
        files = sorted(frames_dir.glob("frame_*.png"))[:MAX_FRAMES]
        if not files: return False
        first = Image.open(files[0]).convert("RGBA")
        w, h  = first.size; self.cw, self.ch = w, h
        self._frames = []
        for fp in files:
            im = Image.open(fp).convert("RGBA")
            if im.size != (w,h): im = im.resize((w,h), Image.LANCZOS)
            nl = Layer(w, h, "Fondo"); nl.image = im
            self._frames.append([nl])
        self._cur = 0; self._active = 0
        self._comp_cache.clear()
        self._comp_dirty = set(range(len(self._frames)))
        self.queue_draw()
        if self.on_frame_changed: self.on_frame_changed()
        if self.on_layer_changed: self.on_layer_changed()
        return True

    # ── exportar ──────────────────────────────────────────────────────────────
    def thumbnail(self, fi=None) -> Gdk.Texture:
        fi  = self._cur if fi is None else fi
        im  = self._composite(fi).resize((THUMB, THUMB), Image.LANCZOS)
        raw = GLib.Bytes.new(im.tobytes())
        return Gdk.MemoryTexture.new(THUMB, THUMB, Gdk.MemoryFormat.R8G8B8A8, raw, THUMB*4)

    def to_pil(self, fi: int) -> Image.Image:
        return self._composite(fi)

    def add_vector_layer(self):
        """Añade una capa vectorial al frame actual."""
        self.snap_undo()
        layers = self._frames[self._cur]
        vl = VectorLayer(self.cw, self.ch, f"Vector {len(layers)+1}")
        layers.append(vl)
        self._active = len(layers) - 1
        self._dirty(); self.queue_draw()
        if self.on_layer_changed: self.on_layer_changed()

    # ── proyecto (.alproj) ────────────────────────────────────────────────────
    def save_project(self, path: str):
        """Guarda el proyecto completo: capas, blend modes, frames, cámara, etiquetas."""
        import zipfile, json, io
        self._sync_meta()
        meta = {
            "version": 1,
            "canvas":  {"w": self.cw, "h": self.ch},
            "cur":     self._cur,
            "frame_labels":  self._frame_labels,
            "frame_camera":  self._frame_camera,
            "frames": []
        }
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fi, layers in enumerate(self._frames):
                frame_info = {"layers": []}
                for li, layer in enumerate(layers):
                    lmeta = {
                        "name":         layer.name,
                        "visible":      layer.visible,
                        "opacity":      layer.opacity,
                        "blend_mode":   layer.blend_mode,
                        "locked":       layer.locked,
                        "alpha_locked": layer.alpha_locked,
                        "img":          f"f{fi}/l{li}.png",
                    }
                    frame_info["layers"].append(lmeta)
                    buf = io.BytesIO()
                    layer.image.save(buf, "PNG")
                    zf.writestr(f"f{fi}/l{li}.png", buf.getvalue())
                meta["frames"].append(frame_info)
            zf.writestr("project.json", json.dumps(meta, indent=2))

    def load_project(self, path: str) -> bool:
        """Carga un proyecto .alproj y restaura todo el estado del editor."""
        import zipfile, json, io
        try:
            with zipfile.ZipFile(path, "r") as zf:
                meta = json.loads(zf.read("project.json"))
                if meta.get("version", 0) != 1:
                    return False
                cw = meta["canvas"]["w"]
                ch = meta["canvas"]["h"]
                self.cw, self.ch = cw, ch
                self._frames = []
                for fi, finfo in enumerate(meta["frames"]):
                    layers = []
                    for li, lm in enumerate(finfo["layers"]):
                        layer = Layer(cw, ch, lm["name"])
                        layer.visible      = lm.get("visible", True)
                        layer.opacity      = lm.get("opacity", 255)
                        layer.blend_mode   = lm.get("blend_mode", "Normal")
                        layer.locked       = lm.get("locked", False)
                        layer.alpha_locked = lm.get("alpha_locked", False)
                        img_bytes = zf.read(lm["img"])
                        layer.image = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
                        layers.append(layer)
                    self._frames.append(layers)
                self._frame_labels = meta.get("frame_labels", [""] * len(self._frames))
                self._frame_camera = meta.get("frame_camera",
                    [{"tx":0,"ty":0,"scale":1.0,"rot":0.0}] * len(self._frames))
                self._cur    = min(meta.get("cur", 0), len(self._frames) - 1)
                self._active = 0
                self._undo.clear(); self._redo.clear()
                self._comp_cache.clear()
                self._comp_dirty = set(range(len(self._frames)))
                self.queue_draw()
                if self.on_frame_changed: self.on_frame_changed()
                if self.on_layer_changed: self.on_layer_changed()
                return True
        except Exception:
            return False


# ── VectorLayer ───────────────────────────────────────────────────────────────
class VectorLayer(Layer):
    """Capa vectorial: almacena trayectorias cairo, rasteriza on-demand."""
    def __init__(self, w: int, h: int, name: str = "Vector"):
        super().__init__(w, h, name)
        self.paths: list[dict] = []   # [{points, color, width, closed}]
        self._cur_path: list[tuple] | None = None

    def begin_path(self, x: int, y: int, color, width: int):
        self._cur_path = [(x, y)]
        self._path_color = tuple(color)
        self._path_width = width

    def add_point(self, x: int, y: int):
        if self._cur_path is not None:
            self._cur_path.append((x, y))

    def end_path(self, closed: bool = False):
        if self._cur_path and len(self._cur_path) >= 2:
            self.paths.append({
                "points": list(self._cur_path),
                "color":  self._path_color,
                "width":  self._path_width,
                "closed": closed,
            })
        self._cur_path = None
        self._rasterize()

    def _rasterize(self):
        """Rasteriza todos los paths vectoriales a self.image."""
        w, h = self.image.size
        self.image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if not self.paths:
            return
        surf = cairo.ImageSurface(cairo.Format.ARGB32, w, h)
        cr   = cairo.Context(surf)
        cr.set_line_cap(cairo.LineCap.ROUND)
        cr.set_line_join(cairo.LineJoin.ROUND)
        for path in self.paths:
            pts = path["points"]
            if len(pts) < 2: continue
            r, g, b, a = (c/255 for c in path["color"])
            cr.set_source_rgba(r, g, b, a)
            cr.set_line_width(path["width"])
            # Catmull-Rom spline via bezier approximation
            cr.move_to(*pts[0])
            if len(pts) == 2:
                cr.line_to(*pts[1])
            else:
                for i in range(1, len(pts)-1):
                    xc = (pts[i][0] + pts[i+1][0]) / 2
                    yc = (pts[i][1] + pts[i+1][1]) / 2
                    cr.curve_to(pts[i][0], pts[i][1], pts[i][0], pts[i][1], xc, yc)
                cr.line_to(*pts[-1])
            if path["closed"]: cr.close_path()
            cr.stroke()
        # ARGB32 cairo → RGBA PIL
        data = surf.get_data()
        arr  = (np.frombuffer(data, np.uint8).reshape(h, w, 4)
                if _NP else None)
        if arr is not None:
            rgba = np.empty_like(arr)
            a_ch = arr[:, :, 3:4].astype(np.float32) / 255.0
            a_ch = np.where(a_ch > 0, a_ch, 1.0)
            rgba[:, :, 0] = np.clip(arr[:, :, 2].astype(np.float32) / a_ch[:, :, 0], 0, 255)
            rgba[:, :, 1] = np.clip(arr[:, :, 1].astype(np.float32) / a_ch[:, :, 0], 0, 255)
            rgba[:, :, 2] = np.clip(arr[:, :, 0].astype(np.float32) / a_ch[:, :, 0], 0, 255)
            rgba[:, :, 3] = arr[:, :, 3]
            self.image = Image.fromarray(rgba.astype(np.uint8), "RGBA")


# ── LayerPanel ───────────────────────────────────────────────────────────────
class LayerPanel(Gtk.Box):
    def __init__(self, canvas: PaintCanvas):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self._c = canvas
        canvas.on_layer_changed = self.rebuild
        self.set_size_request(210, -1)
        self.set_margin_start(4); self.set_margin_end(8); self.set_margin_top(6)

        head = Gtk.Label(label="CAPAS", xalign=0)
        head.add_css_class("panel-head"); head.set_hexpand(True)
        hdr = Gtk.Box(spacing=2); hdr.append(head)
        for ic, tip, fn in [
            ("add", "Nueva capa", canvas.add_layer),
            ("duplicate", "Duplicar capa", canvas.duplicate_layer),
            ("merge", "Fusionar con la de abajo", canvas.merge_down),
            ("flatten", "Aplanar todas", canvas.flatten),
        ]:
            b = icon_button(ic, tip)
            b.connect("clicked", lambda _, f=fn: f()); hdr.append(b)
        db = icon_button("trash", "Eliminar capa")
        db.connect("clicked", lambda _: canvas.delete_layer()); hdr.append(db)
        self.append(hdr)

        mv = Gtk.Box(spacing=2); mv.set_halign(Gtk.Align.START)
        up_b = icon_button("up", "Subir capa")
        up_b.connect("clicked", lambda _: canvas.move_layer(-1))
        dn_b = icon_button("down", "Bajar capa")
        dn_b.connect("clicked", lambda _: canvas.move_layer(1))
        vec_b = icon_button("vec_pen", "Añadir capa vectorial")
        vec_b.connect("clicked", lambda _: canvas.add_vector_layer())
        mv.append(up_b); mv.append(dn_b); mv.append(vec_b); self.append(mv)

        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        sc.set_child(self._list); self.append(sc)
        self.rebuild()

    def _layer_thumb(self, layer) -> Gdk.Texture:
        im  = layer.image.resize((44, 44), Image.LANCZOS)
        raw = GLib.Bytes.new(im.tobytes())
        return Gdk.MemoryTexture.new(44, 44, Gdk.MemoryFormat.R8G8B8A8, raw, 44*4)

    def rebuild(self):
        child = self._list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._list.remove(child); child = nxt

        canvas = self._c
        layers = canvas._frames[canvas._cur]
        active = canvas._active

        for i in range(len(layers)-1, -1, -1):
            l = layers[i]
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)

            row = Gtk.Box(spacing=2)
            row.set_margin_start(2); row.set_margin_end(2)
            if i == active: row.add_css_class("card")

            # thumbnail
            thumb_pic = Gtk.Picture()
            thumb_pic.set_size_request(44, 44)
            thumb_pic.set_content_fit(Gtk.ContentFit.CONTAIN)
            try: thumb_pic.set_paintable(self._layer_thumb(l))
            except Exception: pass
            row.append(thumb_pic)

            # ojo (visibilidad)
            eye = Gtk.ToggleButton(); eye.add_css_class("tool-btn")
            eye.set_child(icon_image("eye" if l.visible else "eye_off", 16))
            eye.set_active(l.visible); eye.set_tooltip_text("Visibilidad")
            eye.connect("toggled", lambda b,idx=i: (
                canvas.set_layer_prop(idx, visible=b.get_active()),
                b.set_child(icon_image("eye" if b.get_active() else "eye_off", 16))))
            row.append(eye)

            # lock
            lk = icon_button("lock", "Bloquear capa", size=16, toggle=True)
            lk.set_active(l.locked)
            lk.connect("toggled", lambda b,idx=i:
                canvas.set_layer_prop(idx, locked=b.get_active()))
            row.append(lk)

            # alpha lock
            alk = Gtk.ToggleButton(label="α"); alk.add_css_class("tool-btn")
            alk.set_active(l.alpha_locked)
            alk.set_tooltip_text("Bloquear alpha (pintar solo píxeles existentes)")
            alk.connect("toggled", lambda b,idx=i:
                canvas.set_layer_prop(idx, alpha_locked=b.get_active()))
            row.append(alk)

            # nombre
            nb = Gtk.Button(label=(l.name[:10] if len(l.name)<=10 else l.name[:9]+"…"))
            nb.set_hexpand(True)
            nb.connect("clicked", lambda _,idx=i: self._select(idx))
            row.append(nb)
            outer.append(row)

            # blend + opacidad
            sub = Gtk.Box(spacing=2); sub.set_margin_start(6)
            dd = Gtk.DropDown.new_from_strings(BLEND_MODES)
            dd.set_size_request(120,-1)
            try:  dd.set_selected(BLEND_MODES.index(l.blend_mode))
            except ValueError: dd.set_selected(0)
            dd.connect("notify::selected", lambda d,_,idx=i:
                canvas.set_layer_prop(idx, blend_mode=BLEND_MODES[d.get_selected()]))
            sub.append(dd)

            opa = Gtk.SpinButton(adjustment=Gtk.Adjustment(
                value=l.opacity, lower=0, upper=255, step_increment=5))
            opa.set_size_request(58,-1)
            opa.connect("value-changed", lambda s,idx=i:
                canvas.set_layer_prop(idx, opacity=int(s.get_value())))
            sub.append(opa)
            outer.append(sub)

            self._list.append(outer)

    def _select(self, idx: int):
        self._c._active = idx; self.rebuild()


def _apply_theme(window: Gtk.Window):
    from ..ui import theme as _theme
    _theme.apply(window)


# ── PaintEditor (ventana) ─────────────────────────────────────────────────────
class PaintEditor(Gtk.Window):
    def __init__(self, app, anim_id=None, pose=None, guided=False):
        super().__init__(application=app, title="Editor de Pintura — AnimaLinux")
        self.app         = app
        self.anim_id     = anim_id
        self._guided     = guided
        self._playing    = False
        self._play_id    = None
        self._audio_path = None
        self._audio_proc = None

        self.canvas      = PaintCanvas(512, 512)
        self.canvas.on_pick          = self._on_pick
        self.canvas.on_frame_changed = self._rebuild_strip
        self.canvas.on_cursor_moved  = self._on_cursor

        self.layer_panel = LayerPanel(self.canvas)

        self.set_default_size(1360, 860)
        self._build_ui()
        _apply_theme(self)

        if pose:
            self.pose_entry.set_text(pose)
        elif guided:
            self._suggest_next_pose()

        if anim_id is not None and pose in (None, "default"):
            fd = app.library.frames_dir(anim_id)
            if self.canvas.load_from_dir(fd):
                self._rebuild_strip(); self.layer_panel.rebuild()

        if anim_id is None:
            GLib.idle_add(self._ask_canvas_size)

        GLib.idle_add(self._show_tutorial)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)
        root.append(self._build_toolbar())
        root.append(self._build_tool_options_bar())   # barra de opciones de herramienta

        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True)

        # status bar primero para que canvas_size_lbl exista antes de _rebuild_strip
        status_bar = self._build_status_bar()
        body.append(self._build_left_panel())
        body.append(self.canvas)
        body.append(self._build_right_panel())        # solo capas
        root.append(body)
        root.append(self._build_timeline())           # timeline horizontal al fondo
        root.append(status_bar)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)

    def _build_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        bar.add_css_class("editor-toolbar")
        sepv = lambda: bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # zoom
        zm_out = icon_button("zoom_out", "Alejar")
        zm_out.connect("clicked", lambda _: (
            self.canvas.zoom_at(0.8, self.canvas.get_allocated_width()/2,
                                self.canvas.get_allocated_height()/2), self._upd_zoom()))
        self.zoom_lbl = Gtk.Label(label="100%"); self.zoom_lbl.set_size_request(48,-1)
        self.zoom_lbl.add_css_class("monospace")
        zm_in = icon_button("zoom_in", "Acercar")
        zm_in.connect("clicked", lambda _: (
            self.canvas.zoom_at(1.25, self.canvas.get_allocated_width()/2,
                                self.canvas.get_allocated_height()/2), self._upd_zoom()))
        fit_b = icon_button("fit", "Ajustar zoom (Ctrl+0)")
        fit_b.connect("clicked", lambda _: (self.canvas.zoom_fit(), self._upd_zoom()))
        bar.append(zm_out); bar.append(self.zoom_lbl); bar.append(zm_in); bar.append(fit_b)
        sepv()

        bar.append(Gtk.Label(label="FPS"))
        self.fps_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=12, lower=1, upper=60, step_increment=1))
        self.fps_spin.set_size_request(55,-1); bar.append(self.fps_spin)
        self.play_btn = icon_button("play", "Reproducir (Espacio)", toggle=True)
        self.play_btn.connect("toggled", self._on_play_toggle); bar.append(self.play_btn)

        onion = icon_button("onion", "Papel cebolla rojo/azul multi-frame", toggle=True)
        onion.connect("toggled", lambda b: setattr(self.canvas,"onion",b.get_active())
                      or self.canvas.queue_draw())
        bar.append(onion)

        stab = icon_button("stabilizer", "Estabilizador de trazo", toggle=True)
        stab.set_active(True)
        stab.connect("toggled", lambda b: setattr(self.canvas,"stabilizer",b.get_active()))
        bar.append(stab)

        smooth = icon_button("smooth", "Suavizado de trazo (Chaikin)", toggle=True)
        smooth.connect("toggled", lambda b: setattr(self.canvas,"smooth_strokes",b.get_active()))
        bar.append(smooth)
        sepv()

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
        sepv()

        # cámara / audio
        cam_reset = icon_button("reset", "Resetear cámara de este frame")
        cam_reset.connect("clicked", lambda _: self._cam_reset()); bar.append(cam_reset)
        cam_b = icon_button("camera", "Editar cámara del frame actual")
        cam_b.connect("clicked", lambda _: self._cam_dialog()); bar.append(cam_b)
        self._audio_btn = icon_button("audio", "Importar audio para sincronizar")
        self._audio_btn.connect("clicked", lambda _: self._import_audio()); bar.append(self._audio_btn)
        sepv()

        imp = icon_button("import", "Importar imagen")
        imp.connect("clicked", self._on_import); bar.append(imp)
        undo = icon_button("undo", "Deshacer (Z/Ctrl+Z)")
        undo.connect("clicked", lambda _: self.canvas.undo()); bar.append(undo)
        redo = icon_button("redo", "Rehacer (Y/Ctrl+Y)")
        redo.connect("clicked", lambda _: self.canvas.redo()); bar.append(redo)
        sepv()

        save_proj = icon_button("save", "Guardar proyecto .alproj con capas (Ctrl+Shift+S)")
        save_proj.connect("clicked", lambda _: self._save_project_dialog()); bar.append(save_proj)
        open_proj = icon_button("folder_open", "Abrir proyecto .alproj")
        open_proj.connect("clicked", lambda _: self._load_project_dialog()); bar.append(open_proj)

        spacer = Gtk.Box(); spacer.set_hexpand(True); bar.append(spacer)
        help_btn = icon_button("help", "Guía rápida del editor")
        help_btn.connect("clicked", lambda _: self._show_tutorial(force=True))
        bar.append(help_btn)

        return bar

    def _build_tool_options_bar(self):
        """Barra de opciones de herramienta — siempre visible debajo del toolbar."""
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_margin_start(8); bar.set_margin_end(8)
        bar.set_margin_top(3); bar.set_margin_bottom(3)

        sep = lambda: Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)

        bar.append(Gtk.Label(label="Pincel:"))
        bt_dd = Gtk.DropDown.new_from_strings(BRUSH_LABELS)
        bt_dd.set_size_request(148, -1)
        bt_dd.connect("notify::selected", lambda d, _: (
            setattr(self.canvas, "brush_type", BRUSH_TYPES[d.get_selected()]),
            self.canvas._stamp_cache.clear()))
        self._brush_dd = bt_dd
        bar.append(bt_dd)

        bar.append(sep())
        bar.append(Gtk.Label(label="Radio:"))
        self.size_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=12, lower=1, upper=200, step_increment=2))
        self.size_spin.set_size_request(72, -1)
        self.size_spin.set_tooltip_text("Tamaño del pincel ( [ ] )")
        self.size_spin.connect("value-changed",
            lambda s: setattr(self.canvas, "brush_r", int(s.get_value())))
        bar.append(self.size_spin)

        bar.append(sep())
        bar.append(Gtk.Label(label="Suavidad:"))
        self.soft_spin = Gtk.SpinButton(digits=2,
            adjustment=Gtk.Adjustment(value=0.5, lower=0.05, upper=1.0, step_increment=0.05))
        self.soft_spin.set_size_request(72, -1)
        self.soft_spin.connect("value-changed",
            lambda s: (setattr(self.canvas, "softness", s.get_value()),
                       self.canvas._stamp_cache.clear()))
        bar.append(self.soft_spin)

        bar.append(sep())
        bar.append(Gtk.Label(label="Opacidad:"))
        self.opac_spin = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=200, lower=1, upper=255, step_increment=10))
        self.opac_spin.set_size_request(72, -1)
        self.opac_spin.connect("value-changed",
            lambda s: (setattr(self.canvas, "opacity", int(s.get_value())),
                       self.canvas._stamp_cache.clear()))
        bar.append(self.opac_spin)

        bar.append(sep())
        bar.append(Gtk.Label(label="Varita tol.:"))
        self.wand_tol = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=32, lower=0, upper=255, step_increment=8))
        self.wand_tol.set_size_request(72, -1)
        self.wand_tol.connect("value-changed",
            lambda s: setattr(self.canvas, "magic_wand_tolerance", int(s.get_value())))
        bar.append(self.wand_tol)

        return bar

    def _build_left_panel(self):
        """Panel izquierdo: herramientas + colores. Controles de pincel en la barra superior."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("editor-panel")
        outer.set_size_request(126, -1)

        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_vexpand(True)

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        panel.set_margin_start(6); panel.set_margin_end(6); panel.set_margin_top(6)

        # ── herramientas ──
        tools_lbl = Gtk.Label(label="HERRAMIENTAS", xalign=0)
        tools_lbl.add_css_class("panel-head")
        panel.append(tools_lbl)
        tools = [
            ("brush",          "Pincel (B)"),
            ("eraser",         "Borrador (E)"),
            ("smudge",         "Difuminar"),
            ("fill",           "Relleno (G)"),
            ("gradient",       "Gradiente"),
            ("line",           "Línea"),
            ("pick",           "Cuentagotas (I)"),
            ("select",         "Selección (S)"),
            ("move",           "Mover (M)"),
            ("magic_wand",     "Varita mágica (W)"),
            ("rect_fill",      "Rectángulo relleno"),
            ("rect_outline",   "Rectángulo contorno"),
            ("ellipse_fill",   "Elipse rellena"),
            ("ellipse_outline","Elipse contorno"),
            ("vec_pen",        "Pluma vectorial"),
        ]
        # nombre de tool -> nombre de icono (cuando difieren)
        icon_for = {"magic_wand": "wand", "rect_outline": "outline",
                    "ellipse_outline": "ellipse"}
        self._tool_btns = {}
        grid = Gtk.Grid()
        grid.set_row_spacing(3); grid.set_column_spacing(3)
        grid.set_halign(Gtk.Align.CENTER)
        for i, (tid, tip) in enumerate(tools):
            btn = icon_button(icon_for.get(tid, tid), tip, size=20, toggle=True)
            if tid == "brush": btn.set_active(True)
            btn.connect("toggled", self._on_tool_toggle, tid)
            self._tool_btns[tid] = btn
            grid.attach(btn, i % 2, i // 2, 1, 1)
        panel.append(grid)

        panel.append(Gtk.Separator())

        # ── colores FG / BG ──
        color_lbl = Gtk.Label(label="COLORES", xalign=0)
        color_lbl.add_css_class("panel-head")
        panel.append(color_lbl)

        colors_row = Gtk.Box(spacing=4)
        fg_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        fg_col.append(Gtk.Label(label="FG"))
        self._fg_btn = Gtk.ColorButton(); self._fg_btn.set_use_alpha(True)
        rgba = Gdk.RGBA(); rgba.red=rgba.green=rgba.blue=0; rgba.alpha=1
        self._fg_btn.set_rgba(rgba)
        self._fg_btn.connect("color-set", self._on_fg_set)
        fg_col.append(self._fg_btn)
        colors_row.append(fg_col)

        bg_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        bg_col.append(Gtk.Label(label="BG"))
        self._bg_btn = Gtk.ColorButton(); self._bg_btn.set_use_alpha(True)
        rgba2 = Gdk.RGBA(); rgba2.red=rgba2.green=rgba2.blue=1; rgba2.alpha=1
        self._bg_btn.set_rgba(rgba2)
        self._bg_btn.connect("color-set", self._on_bg_set)
        bg_col.append(self._bg_btn)
        colors_row.append(bg_col)
        panel.append(colors_row)

        swap_btn = Gtk.Button(label="⇌ FG ↔ BG  (X)")
        swap_btn.set_tooltip_text("Intercambiar colores FG/BG (X)")
        swap_btn.connect("clicked", lambda _: self._swap_colors())
        panel.append(swap_btn)

        hex_row = Gtk.Box(spacing=2)
        hex_row.append(Gtk.Label(label="#"))
        self._hex_entry = Gtk.Entry()
        self._hex_entry.set_max_length(8); self._hex_entry.set_size_request(90, -1)
        self._hex_entry.set_text("000000ff")
        self._hex_entry.set_placeholder_text("RRGGBBAA")
        self._hex_entry.connect("activate", self._on_hex_activate)
        hex_row.append(self._hex_entry)
        panel.append(hex_row)

        for lbl2, attr, upper in [("H", "_hsv_h", 360), ("S", "_hsv_s", 100), ("V", "_hsv_v", 100)]:
            row = Gtk.Box(spacing=2)
            lbl_w = Gtk.Label(label=lbl2); lbl_w.set_size_request(14, -1)
            row.append(lbl_w)
            sp = Gtk.SpinButton(adjustment=Gtk.Adjustment(
                value=0, lower=0, upper=upper, step_increment=1))
            sp.set_size_request(80, -1)
            sp.connect("value-changed", self._on_hsv_changed)
            setattr(self, attr + "_spin", sp)
            row.append(sp)
            panel.append(row)

        panel.append(Gtk.Separator())

        # ── colores recientes ──
        rec_lbl = Gtk.Label(label="Recientes")
        rec_lbl.add_css_class("caption")
        panel.append(rec_lbl)
        self._recent_grid = Gtk.Grid()
        self._recent_grid.set_row_spacing(2); self._recent_grid.set_column_spacing(2)
        panel.append(self._recent_grid)
        self._rebuild_recent()

        sc.set_child(panel)
        outer.append(sc)
        return outer

    def _rebuild_recent(self):
        child = self._recent_grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._recent_grid.remove(child); child = nxt
        recent = list(self.canvas.recent_colors)
        for i in range(12):
            da = Gtk.DrawingArea(); da.set_size_request(20,20)
            if i < len(recent):
                c = recent[i]
                da.set_draw_func(lambda a,cr,w,h,col=c:(
                    cr.set_source_rgba(col[0]/255,col[1]/255,col[2]/255,col[3]/255),
                    cr.paint()))
                da.set_tooltip_text(f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}")
                click = Gtk.GestureClick()
                click.connect("pressed", lambda g,n,x,y,col=c: self._set_fg(col))
                da.add_controller(click)
            else:
                da.set_draw_func(lambda a,cr,w,h:(cr.set_source_rgb(0.2,0.2,0.3),cr.paint()))
            self._recent_grid.attach(da, i%6, i//6, 1, 1)

    def _build_right_panel(self):
        """Panel derecho: solo capas (el timeline va al fondo)."""
        return self.layer_panel

    def _build_timeline(self):
        """Timeline horizontal estilo CSP — frames en fila al fondo de la ventana."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.add_css_class("timeline")

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.set_margin_start(6); bar.set_margin_end(6)
        bar.set_margin_top(4); bar.set_margin_bottom(4)

        # controles de frame (izquierda) — con iconos
        ctrl = Gtk.Box(spacing=2)
        ctrl.set_margin_end(4)

        for ic, tip, fn in [
            ("add",       "Añadir frame (Ctrl+N)",   self.canvas.add_frame),
            ("duplicate", "Duplicar frame (Ctrl+D)", self.canvas.duplicate_frame),
            ("copy",      "Copiar frame (Ctrl+C)",   self.canvas.copy_frame),
            ("paste",     "Pegar frame (Ctrl+V)",    self.canvas.paste_frame),
            ("trash",     "Borrar frame (Supr)",     self.canvas.delete_frame),
        ]:
            b = icon_button(ic, tip)
            b.connect("clicked", lambda _, f=fn: (
                f(), self._rebuild_strip(), self.layer_panel.rebuild()))
            ctrl.append(b)

        ctrl.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        gif_b = Gtk.Button(); gb = Gtk.Box(spacing=4)
        gb.append(icon_image("gif", 16)); gb.append(Gtk.Label(label="GIF")); gif_b.set_child(gb)
        gif_b.set_tooltip_text("Exportar como GIF animado")
        gif_b.connect("clicked", lambda _: self._export_gif_dialog())
        ctrl.append(gif_b)

        mp4_b = Gtk.Button(); mb = Gtk.Box(spacing=4)
        mb.append(icon_image("gif", 16)); mb.append(Gtk.Label(label="MP4")); mp4_b.set_child(mb)
        mp4_b.set_tooltip_text("Exportar como MP4 (requiere ffmpeg)")
        mp4_b.connect("clicked", lambda _: self._export_mp4_dialog())
        ctrl.append(mp4_b)

        bar.append(ctrl)

        # tira de frames desplazable (horizontal)
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        sc.set_hexpand(True)
        sc.set_size_request(-1, THUMB + 46)
        self.strip_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.strip_box.set_margin_start(4); self.strip_box.set_margin_end(4)
        self.strip_box.set_margin_top(2); self.strip_box.set_margin_bottom(2)
        sc.set_child(self.strip_box)
        bar.append(sc)

        outer.append(bar)
        self._rebuild_strip()
        return outer

    def _build_status_bar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("editor-statusbar")
        bar.set_margin_start(8); bar.set_margin_end(8)
        bar.set_margin_top(3); bar.set_margin_bottom(3)

        self.cursor_lbl = Gtk.Label(label="X:— Y:—")
        self.cursor_lbl.set_size_request(90,-1)
        self.cursor_lbl.add_css_class("monospace"); bar.append(self.cursor_lbl)

        self.px_lbl = Gtk.Label(label="")
        self.px_lbl.add_css_class("monospace"); self.px_lbl.set_hexpand(True)
        bar.append(self.px_lbl)

        self.zoom_status = Gtk.Label(label="100%")
        self.zoom_status.add_css_class("dim-label"); bar.append(self.zoom_status)

        self.canvas_size_lbl = Gtk.Label(label="512×512")
        self.canvas_size_lbl.add_css_class("dim-label"); bar.append(self.canvas_size_lbl)

        if self.anim_id is None:
            bar.append(Gtk.Label(label="Nombre:"))
            self.name_entry = Gtk.Entry()
            self.name_entry.set_placeholder_text("Mi animación")
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

    # ── tira de frames (timeline) ─────────────────────────────────────────────
    def _rebuild_strip(self):
        child = self.strip_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.strip_box.remove(child); child = nxt
        self.canvas._sync_meta()

        for i in range(self.canvas.frame_count):
            # contenedor por frame: botón + entry de etiqueta (fuera del botón)
            outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            outer.set_margin_bottom(2)

            # thumbnail del frame dentro del botón
            pic = Gtk.Picture()
            pic.set_size_request(THUMB, THUMB)
            pic.set_content_fit(Gtk.ContentFit.CONTAIN)
            pic.set_paintable(self.canvas.thumbnail(i))

            # número de frame + icono de cámara si tiene transform
            cam = self.canvas._frame_camera[i]
            cam_icon = " 🎥" if (cam["tx"] or cam["ty"] or cam["scale"] != 1.0 or cam["rot"]) else ""
            num_lbl = Gtk.Label(label=f"{i+1}{cam_icon}")
            num_lbl.add_css_class("caption")

            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            inner.append(num_lbl)
            inner.append(pic)

            btn = Gtk.Button()
            btn.set_child(inner)
            btn.add_css_class("frame-cell")
            if i == self.canvas._cur:
                btn.add_css_class("current")
            btn.connect("clicked", lambda _,idx=i: (
                self.canvas.go_to(idx), self._rebuild_strip(), self.layer_panel.rebuild()))
            outer.append(btn)

            # entry de etiqueta FUERA del botón (interactivo independiente)
            tag_entry = Gtk.Entry()
            tag_entry.set_placeholder_text("etiqueta…")
            tag_entry.set_text(self.canvas._frame_labels[i])
            tag_entry.set_size_request(THUMB, 22)
            tag_entry.set_max_length(16)
            tag_entry.connect("changed", lambda e, idx=i:
                self._set_frame_label(idx, e.get_text()))
            outer.append(tag_entry)

            self.strip_box.append(outer)

        self._rebuild_recent()
        self.canvas_size_lbl.set_text(f"{self.canvas.cw}×{self.canvas.ch}")

    # ── zoom ──────────────────────────────────────────────────────────────────
    def _upd_zoom(self):
        pct = f"{self.canvas._zoom*100:.0f}%"
        self.zoom_lbl.set_text(pct); self.zoom_status.set_text(pct)

    # ── simetría ──────────────────────────────────────────────────────────────
    def _on_sym_toggle(self, btn, val):
        if not btn.get_active(): return
        self.canvas.symmetry = val
        for k,b in self._sym_btns.items():
            if k != val and b.get_active(): b.set_active(False)
        self.canvas.queue_draw()

    # ── color FG/BG ───────────────────────────────────────────────────────────
    def _sync_color_ui(self, color):
        """Sincroniza hex entry, HSV spins y fg_btn con el color dado."""
        r,g,b,a = color
        h,s,v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
        self._hex_entry.set_text(f"{r:02x}{g:02x}{b:02x}{a:02x}")
        self._hsv_h_spin.set_value(round(h*360))
        self._hsv_s_spin.set_value(round(s*100))
        self._hsv_v_spin.set_value(round(v*100))
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = r/255, g/255, b/255, a/255
        self._fg_btn.set_rgba(rgba)

    def _on_fg_set(self, btn):
        rgba = btn.get_rgba()
        c = (int(rgba.red*255),int(rgba.green*255),int(rgba.blue*255),int(rgba.alpha*255))
        self.canvas.fg_color = c
        self.canvas._stamp_cache.clear()
        self.canvas._add_recent(c)
        self._sync_color_ui(c)
        self._rebuild_recent()

    def _on_bg_set(self, btn):
        rgba = btn.get_rgba()
        self.canvas.bg_color = (int(rgba.red*255),int(rgba.green*255),
                                int(rgba.blue*255),int(rgba.alpha*255))

    def _set_fg(self, color):
        self.canvas.fg_color = tuple(color)
        self.canvas._stamp_cache.clear()
        self._sync_color_ui(color)

    def _on_pick(self, color):
        self._set_fg(color)
        self._tool_btns["brush"].set_active(True)
        self._rebuild_recent()

    def _on_hex_activate(self, entry):
        txt = entry.get_text().strip().lstrip("#")
        try:
            if len(txt) == 6:
                r,g,b = int(txt[0:2],16),int(txt[2:4],16),int(txt[4:6],16)
                a = 255
            elif len(txt) == 8:
                r,g,b,a = int(txt[0:2],16),int(txt[2:4],16),int(txt[4:6],16),int(txt[6:8],16)
            else: return
            c = (r,g,b,a)
            self.canvas.fg_color = c; self.canvas._stamp_cache.clear()
            self._sync_color_ui(c)
        except ValueError: pass

    def _on_hsv_changed(self, spin):
        h = self._hsv_h_spin.get_value() / 360
        s = self._hsv_s_spin.get_value() / 100
        v = self._hsv_v_spin.get_value() / 100
        r,g,b = colorsys.hsv_to_rgb(h, s, v)
        a = self.canvas.fg_color[3] if self.canvas.fg_color else 255
        c = (int(r*255), int(g*255), int(b*255), a)
        self.canvas.fg_color = c; self.canvas._stamp_cache.clear()
        self._hex_entry.set_text(f"{c[0]:02x}{c[1]:02x}{c[2]:02x}{c[3]:02x}")
        rgba = Gdk.RGBA(); rgba.red,rgba.green,rgba.blue,rgba.alpha = r,g,b,a/255
        self._fg_btn.set_rgba(rgba)

    def _swap_colors(self):
        self.canvas.fg_color, self.canvas.bg_color = (
            self.canvas.bg_color, self.canvas.fg_color)
        self.canvas._stamp_cache.clear()
        self._sync_color_ui(self.canvas.fg_color)
        rgba2 = Gdk.RGBA()
        bg = self.canvas.bg_color
        rgba2.red,rgba2.green,rgba2.blue,rgba2.alpha = (c/255 for c in bg)
        self._bg_btn.set_rgba(rgba2)

    def _on_cursor(self, cx, cy, color):
        self.cursor_lbl.set_text(f"X:{int(cx):4d} Y:{int(cy):4d}")
        self.px_lbl.set_text(
            f"  R:{color[0]:3d} G:{color[1]:3d} B:{color[2]:3d} A:{color[3]:3d}")
        self._upd_zoom()

    # ── herramientas ──────────────────────────────────────────────────────────
    def _on_tool_toggle(self, btn, tid):
        if not btn.get_active(): return
        if self.canvas.tool == "move" and tid != "move":
            self.canvas.commit_selection()
        self.canvas.tool = tid
        for k,b in self._tool_btns.items():
            if k != tid and b.get_active(): b.set_active(False)

    def _select_tool(self, tid):
        if tid in self._tool_btns:
            self._tool_btns[tid].set_active(True)

    # ── reproducir ────────────────────────────────────────────────────────────
    def _tick(self):
        if not self._playing: return False
        self.canvas.go_to((self.canvas._cur+1) % self.canvas.frame_count)
        self._rebuild_strip(); return True

    # ── teclado ───────────────────────────────────────────────────────────────
    def _on_key(self, ctrl, keyval, keycode, mods):
        ctrl_h = bool(mods & Gdk.ModifierType.CONTROL_MASK)
        key    = Gdk.keyval_name(keyval) or ""
        shift_h = bool(mods & Gdk.ModifierType.SHIFT_MASK)
        if ctrl_h:
            if key in ("z","Z"): self.canvas.undo(); return True
            if key in ("y","Y"): self.canvas.redo(); return True
            if key in ("s","S"):
                if shift_h: self._save_project_dialog()
                else:       self._save_pose()
                return True
            if key in ("d","D"): self.canvas.duplicate_frame(); self._rebuild_strip(); return True
            if key in ("n","N"): self.canvas.add_frame(); self._rebuild_strip(); return True
            if key in ("c","C"): self.canvas.copy_frame(); return True
            if key in ("v","V"): self.canvas.paste_frame(); self._rebuild_strip(); self.layer_panel.rebuild(); return True
        else:
            if key in ("b","B"): self._select_tool("brush");         return True
            if key in ("e","E"): self._select_tool("eraser");        return True
            if key in ("u","U"): self._select_tool("smudge");        return True
            if key in ("f","F"): self._select_tool("fill");          return True
            if key in ("g","G"): self._select_tool("gradient");      return True
            if key in ("l","L"): self._select_tool("line");          return True
            if key in ("i","I"): self._select_tool("pick");          return True
            if key in ("s","S"): self._select_tool("select");        return True
            if key in ("m","M"): self._select_tool("move");          return True
            if key in ("w","W"): self._select_tool("magic_wand");    return True
            if key in ("v","V"): self._select_tool("vec_pen");       return True
            if key in ("x","X"): self._swap_colors();                return True
            if key in ("z","Z"): self.canvas.undo();                 return True
            if key in ("y","Y"): self.canvas.redo();                 return True
            if key == "bracketleft":
                v = max(1, self.canvas.brush_r-2)
                self.canvas.brush_r = v; self.size_spin.set_value(v); return True
            if key == "bracketright":
                v = min(200, self.canvas.brush_r+2)
                self.canvas.brush_r = v; self.size_spin.set_value(v); return True
            if key == "Delete": self.canvas.delete_frame(); self._rebuild_strip(); return True
            if key == "space":
                self.play_btn.set_active(not self.play_btn.get_active()); return True
            if key == "Escape":
                if self.canvas._sel_rect:
                    self.canvas.commit_selection()
                    self.canvas._sel_rect = None; self.canvas.queue_draw(); return True
        return False

    # ── importar ──────────────────────────────────────────────────────────────
    def _on_import(self, _):
        dlg = Gtk.FileDialog(); dlg.set_title("Elige imagen base")
        dlg.open(self, None, self._on_file_chosen)

    def _on_file_chosen(self, dlg, result):
        try: gf = dlg.open_finish(result)
        except GLib.Error: return
        self.canvas.import_image(gf.get_path()); self._rebuild_strip()

    # ── guardar / abrir proyecto (.alproj) ───────────────────────────────────
    def _save_project_dialog(self):
        from .. import projects as _proj
        dlg = Gtk.FileDialog()
        dlg.set_title("Guardar proyecto (.alproj)")
        f = Gtk.FileFilter(); f.set_name("Proyecto AnimaLinux (*.alproj)")
        f.add_pattern("*.alproj")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        dlg.set_filters(store)
        pose = self.pose_entry.get_text().strip() or "proyecto"
        dlg.set_initial_name(f"{pose}.alproj")
        proj_dir = _proj.ensure_dir()
        dlg.set_initial_folder(Gio.File.new_for_path(str(proj_dir)))
        dlg.save(self, None, self._on_save_proj_done)

    def _on_save_proj_done(self, dlg, result):
        try:
            gf = dlg.save_finish(result)
        except GLib.Error:
            return
        path = gf.get_path()
        if not path.endswith(".alproj"):
            path += ".alproj"
        try:
            self.canvas.save_project(path)
            self.save_status.set_text(f"Proyecto guardado: {Path(path).name}")
        except Exception as e:
            self.save_status.set_text(f"Error al guardar: {e}")

    def _load_project_dialog(self):
        dlg = Gtk.FileDialog()
        dlg.set_title("Abrir proyecto (.alproj)")
        f = Gtk.FileFilter(); f.set_name("Proyecto AnimaLinux (*.alproj)")
        f.add_pattern("*.alproj")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        dlg.set_filters(store)
        dlg.open(self, None, self._on_load_proj_done)

    def _on_load_proj_done(self, dlg, result):
        try:
            gf = dlg.open_finish(result)
        except GLib.Error:
            return
        path = gf.get_path()
        ok = self.canvas.load_project(path)
        if ok:
            self._rebuild_strip()
            self.layer_panel.rebuild()
            self.canvas_size_lbl.set_text(f"{self.canvas.cw}×{self.canvas.ch}")
            self.save_status.set_text(f"Proyecto cargado: {Path(path).name}")
        else:
            self.save_status.set_text("Error: archivo no válido o versión incompatible")

    # ── tutorial ──────────────────────────────────────────────────────────────
    def _show_tutorial(self, force=False):
        from .. import settings as _s
        if not force and _s.get("tutorial_paint_shown", False):
            return
        dlg = Gtk.Dialog(title="Editor de Pintura — Guía rápida",
                         transient_for=self, modal=True)
        dlg.set_default_size(520, 460)
        box = dlg.get_content_area()
        box.set_spacing(0)

        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        txt = Gtk.TextView(); txt.set_editable(False); txt.set_cursor_visible(False)
        txt.set_wrap_mode(Gtk.WrapMode.WORD)
        txt.set_margin_start(18); txt.set_margin_end(18)
        txt.set_margin_top(14); txt.set_margin_bottom(14)
        buf = txt.get_buffer()
        GUIDE = (
            "🖌️  HERRAMIENTAS  (panel izquierdo)\n"
            "────────────────────────────────────────\n"
            "  B  Pincel         E  Borrador\n"
            "  F  Relleno        G  Gradiente\n"
            "  L  Línea          I  Cuentagotas\n"
            "  S  Selección      M  Mover\n"
            "  W  Varita mágica  V  Pluma vectorial\n"
            "  X  Cambiar FG ↔ BG\n\n"
            "🔧  OPCIONES DE PINCEL  (barra superior)\n"
            "────────────────────────────────────────\n"
            "  Tipo de pincel — Radio — Suavidad — Opacidad\n"
            "  [ ]  reducir / aumentar radio del pincel\n\n"
            "🎞️  TIMELINE  (parte inferior)\n"
            "────────────────────────────────────────\n"
            "  ➕ Frame   → añade un nuevo fotograma\n"
            "  ⎘ Dupl.   → duplica el frame actual\n"
            "  ⎘ Copiar / Pegar → Ctrl+C / Ctrl+V\n"
            "  Haz clic en un frame para ir a él\n"
            "  ▶ (arriba) reproduce la animación\n\n"
            "🗂️  CAPAS  (panel derecho)\n"
            "────────────────────────────────────────\n"
            "  +  nueva capa      ⎘  duplicar\n"
            "  👁  ocultar/mostrar    🔒  bloquear\n"
            "  α  bloquear alpha (pinta solo píxeles existentes)\n"
            "  Arrastra ▲▼ para reordenar\n\n"
            "💾  GUARDAR\n"
            "────────────────────────────────────────\n"
            "  Escribe el nombre de la pose en el campo\n"
            "  inferior (ej: default, walk, idle…)\n"
            "  → botón \"💾 Guardar pose\"  o  Ctrl+S\n\n"
            "↩️  DESHACER / REHACER\n"
            "  Ctrl+Z   Ctrl+Y   (hasta 30 niveles)\n\n"
            "🔍  ZOOM Y NAVEGACIÓN\n"
            "  Ctrl+Scroll → zoom  |  Espacio+arrastrar → pan\n"
            "  Ctrl+0 → ajustar zoom al lienzo\n"
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
            _s.set_val("tutorial_paint_shown", no_show.get_active()),
            dlg.destroy()))
        footer.append(ok)
        box.append(footer)
        dlg.present()

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
            pose_dir = fd if pose == "default" else fd/pose
            pose_dir.mkdir(parents=True, exist_ok=True)
            self._export_frames(pose_dir)
            self.app.library.add(aid, name, self.canvas.frame_count, cw, ch)
            self.app.library.update(aid, fps=fps)
            importer.ensure_flipped(pose_dir)
            if pose != "default": self.app.register_pose(aid, pose, fps)
            self.anim_id = aid
            self.save_status.set_text(f"Animación «{name}» creada.")
        else:
            fd = self.app.library.frames_dir(self.anim_id)
            pose_dir = fd if pose == "default" else fd/pose
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
        if nxt: self.pose_entry.set_text(nxt); self._show_tip(nxt)
        else:   self.save_status.set_text("¡Todas las poses creadas!")

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
        dlg.set_default_size(380, 280)
        box = dlg.get_content_area()
        box.set_spacing(8); box.set_margin_start(16); box.set_margin_end(16)
        box.set_margin_top(14); box.set_margin_bottom(14)

        box.append(Gtk.Label(label="Ancho (px):"))
        w_sp = Gtk.SpinButton(adjustment=Gtk.Adjustment(
            value=512, lower=64, upper=8192, step_increment=64))
        box.append(w_sp)
        box.append(Gtk.Label(label="Alto (px):"))
        h_sp = Gtk.SpinButton(adjustment=Gtk.Adjustment(
            value=512, lower=64, upper=8192, step_increment=64))
        box.append(h_sp)

        presets = Gtk.Box(spacing=3)
        for lbl2,w,h in [("512²",512,512),("800×600",800,600),
                          ("1024²",1024,1024),("1280×720",1280,720),
                          ("1920×1080",1920,1080)]:
            b = Gtk.Button(label=lbl2)
            b.connect("clicked", lambda _,ww=w,hh=h: (w_sp.set_value(ww),h_sp.set_value(hh)))
            presets.append(b)
        box.append(presets)

        ok = Gtk.Button(label="Crear lienzo"); ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: self._apply_size(
            dlg, int(w_sp.get_value()), int(h_sp.get_value())))
        box.append(ok); dlg.present()
        return False

    def _apply_size(self, dlg, w, h):
        self.canvas.cw, self.canvas.ch = w, h
        self.canvas._frames  = [[Layer(w, h, "Capa 1")]]
        self.canvas._cur     = 0; self.canvas._active = 0
        self.canvas._undo.clear(); self.canvas._redo.clear()
        self.canvas._comp_cache.clear(); self.canvas._comp_dirty = {0}
        self.canvas.queue_draw()
        self._rebuild_strip(); self.layer_panel.rebuild()
        self.canvas_size_lbl.set_text(f"{w}×{h}")
        dlg.destroy()

    # ── exportar GIF ──────────────────────────────────────────────────────────
    def _export_gif_dialog(self):
        dlg = Gtk.FileDialog()
        dlg.set_title("Guardar como GIF animado")
        dlg.set_initial_name("animacion.gif")
        dlg.save(self, None, self._gif_save_done)

    def _gif_save_done(self, dlg, result):
        try: gf = dlg.save_finish(result)
        except GLib.Error: return
        path = gf.get_path()
        fps  = int(self.fps_spin.get_value())
        delay_ms = max(20, 1000 // fps)
        frames = [self.canvas.to_pil(i).convert("RGBA")
                  for i in range(self.canvas.frame_count)]
        if not frames: return
        frames[0].save(
            path, format="GIF", save_all=True, append_images=frames[1:],
            loop=0, duration=delay_ms, disposal=2)
        self.save_status.set_text(f"GIF guardado: {Path(path).name}")

    # ── exportar MP4 ──────────────────────────────────────────────────────────
    def _export_mp4_dialog(self):
        dlg = Gtk.FileDialog()
        dlg.set_title("Exportar como MP4")
        dlg.set_initial_name("animacion.mp4")
        dlg.save(self, None, self._mp4_save_done)

    def _mp4_save_done(self, dlg, result):
        import subprocess, tempfile, shutil
        try: gf = dlg.save_finish(result)
        except GLib.Error: return
        out_path = gf.get_path()
        fps = int(self.fps_spin.get_value())
        tmp = tempfile.mkdtemp(prefix="animalinux_mp4_")
        try:
            for i in range(self.canvas.frame_count):
                self.canvas.to_pil(i).save(f"{tmp}/frame_{i:04d}.png")
            ret = subprocess.run(
                ["ffmpeg", "-y", "-framerate", str(fps),
                 "-i", f"{tmp}/frame_%04d.png",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-preset", "medium", out_path],
                capture_output=True)
            if ret.returncode == 0:
                self.save_status.set_text(f"MP4 guardado: {Path(out_path).name}")
            else:
                self.save_status.set_text("Error: ffmpeg no encontrado o falló.")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ── cámara por frame ──────────────────────────────────────────────────────
    def _cam_reset(self):
        self.canvas._sync_meta()
        i = self.canvas._cur
        self.canvas._frame_camera[i] = self.canvas._cam_default()
        self.canvas._dirty(); self.canvas.queue_draw()

    def _cam_dialog(self):
        self.canvas._sync_meta()
        i   = self.canvas._cur
        cam = self.canvas._frame_camera[i]
        dlg = Gtk.Dialog(title=f"Cámara — Frame {i+1}", transient_for=self, modal=True)
        dlg.set_default_size(300, 260)
        box = dlg.get_content_area()
        box.set_spacing(6); box.set_margin_start(14); box.set_margin_end(14)
        box.set_margin_top(12); box.set_margin_bottom(12)

        spins = {}
        for lbl, key, lo, hi, step, val in [
            ("Trasl. X (px)", "tx", -2000, 2000, 1, cam["tx"]),
            ("Trasl. Y (px)", "ty", -2000, 2000, 1, cam["ty"]),
            ("Escala",        "scale", 0.1, 8.0, 0.05, cam["scale"]),
            ("Rotación (°)",  "rot",  -180, 180, 1, cam["rot"]),
        ]:
            row = Gtk.Box(spacing=6)
            row.append(Gtk.Label(label=lbl))
            sp = Gtk.SpinButton(
                adjustment=Gtk.Adjustment(value=val, lower=lo, upper=hi, step_increment=step),
                digits=2 if key=="scale" else 0)
            sp.set_hexpand(True)
            sp.connect("value-changed", lambda s, k=key:
                self.canvas._frame_camera[self.canvas._cur].__setitem__(k, s.get_value())
                or self.canvas._dirty() or self.canvas.queue_draw())
            spins[key] = sp; row.append(sp); box.append(row)

        ok = Gtk.Button(label="Cerrar"); ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: dlg.destroy())
        box.append(ok); dlg.present()

    # ── audio ─────────────────────────────────────────────────────────────────
    def _import_audio(self):
        dlg = Gtk.FileDialog(); dlg.set_title("Seleccionar archivo de audio")
        dlg.open(self, None, self._audio_chosen)

    def _audio_chosen(self, dlg, result):
        try: gf = dlg.open_finish(result)
        except GLib.Error: return
        self._audio_path = gf.get_path()
        self._audio_btn.set_label(f"🎵 {Path(self._audio_path).name[:14]}")
        self.save_status.set_text("Audio cargado. Se reproduce al presionar ▶.")

    def _on_play_toggle(self, btn):
        self._playing = btn.get_active()
        if self._playing:
            fps = int(self.fps_spin.get_value())
            self._play_id = GLib.timeout_add(max(16, 1000//fps), self._tick)
            if getattr(self, "_audio_path", None):
                import subprocess
                self._audio_proc = subprocess.Popen(
                    ["mpv", "--no-video", "--loop=inf", self._audio_path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            if self._play_id:
                GLib.source_remove(self._play_id); self._play_id = None
            proc = getattr(self, "_audio_proc", None)
            if proc:
                proc.terminate(); self._audio_proc = None

    # ── etiquetas de frame (para timeline) ────────────────────────────────────
    def _set_frame_label(self, idx: int, text: str):
        self.canvas._sync_meta()
        self.canvas._frame_labels[idx] = text
