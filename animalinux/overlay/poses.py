"""Carga de poses compartida por los backends (Wayland/layer-shell y X11).

- Carga PEREZOSA: al arrancar solo se decodifica la pose «default»; las demás se cargan al
  usarlas por primera vez (las más habituales —idle, walk, jump— se precargan en ratos
  libres, un paso por vez, sin bloquear la interfaz). Una mascota que nunca se enoja o
  duerme nunca paga la memoria de esas poses.
- Una sola textura por cuadro: mirar a la izquierda se dibuja espejando (ScaledPaintable.set_mirror).
- Las poses de otro tamaño se ajustan CONSERVANDO la proporción (antes se estiraban con NEAREST,
  deformando el personaje) y se anclan abajo al centro.
- Con BAKE=True las texturas se reducen a la resolución a la que se muestran (menos RAM/GPU).
"""
from pathlib import Path

from gi.repository import Gdk, GLib

from .live_animation import MANDATORY_POSES

PRELOAD = ("idle", "walk", "jump")     # se cargan en segundo plano tras arrancar


class PoseLoaderMixin:
    BAKE = True

    # ---------- carga ----------
    def _load_poses(self):
        base = Path(self._frames_dir)
        self._poses = {}
        self._pose_dirs = {}
        self._base_size = None
        # resolución de las texturas: si la mascota se muestra a menos del 100 % no tiene sentido
        # guardar los píxeles originales; se reducen una vez (LANCZOS) y el paintable compensa.
        sc = float(self.anim.get("scale", 1.0))
        self._bake = min(1.0, max(0.05, sc)) if self.BAKE else 1.0
        # auto-recorte: caja real del dibujo (unión de todas las poses)
        self._orig_size = None
        self._crop_box = None
        self._compute_crop_box(base)
        subs = sorted(p for p in base.iterdir() if p.is_dir())
        if list(base.glob("frame_*.png")):
            self._load_one_pose("default", base)
        for sub in subs:
            if "default" in self._poses:
                self._pose_dirs[sub.name] = sub          # perezosa
            else:
                self._load_one_pose(sub.name, sub)       # sin capa plana: la primera hace de default
                if sub.name in self._poses:
                    self._poses["default"] = self._poses[sub.name]
        self._preload_ids = [n for n in PRELOAD if n in self._pose_dirs]
        if self._preload_ids:
            GLib.idle_add(self._preload_step)

    def _preload_step(self):
        while self._preload_ids:
            name = self._preload_ids.pop(0)
            if name in self._pose_dirs:
                self._ensure_pose(name)
                return True                             # una pose por ciclo libre
        return False

    def _ensure_pose(self, name):
        folder = self._pose_dirs.pop(name, None)
        if folder is not None:
            self._load_one_pose(name, folder)

    def _load_one_pose(self, name, folder):
        folder = Path(folder)
        normals = sorted(folder.glob("frame_*.png"))
        if not normals:
            return
        # la primera pose cargada (default) fija el tamaño base de referencia
        if self._base_size is None:
            try:
                from PIL import Image
                self._base_size = Image.open(str(normals[0])).size
            except Exception:  # noqa: BLE001
                self._base_size = None
        normal = [t for t in (self._load_texture(p) for p in normals) if t]
        if normal:
            self._poses[name] = {"normal": normal}

    def _frames_for(self, pose):
        if pose in self._pose_dirs:
            self._ensure_pose(pose)
        data = self._poses.get(pose) or self._poses.get("default")
        if not data:
            return []
        return data["normal"]

    def _has_pose(self, pose):
        if pose not in MANDATORY_POSES and pose in self.anim.get("disabled_poses", ()):
            return False
        return pose in self._poses or pose in self._pose_dirs

    def _compute_crop_box(self, base):
        """Caja real (unión de bboxes de TODAS las poses) para recortar el margen transparente.
        Solo afecta a las texturas en memoria y a anim width/height, no a los PNG."""
        try:
            from PIL import Image
        except Exception:  # noqa: BLE001
            return
        base = Path(base)
        normals = sorted(base.glob("frame_*.png"))
        for sub in sorted(p for p in base.iterdir() if p.is_dir()):
            normals += sorted(sub.glob("frame_*.png"))
        if not normals:
            return
        box = None
        orig = None
        for p in normals:
            try:
                im = Image.open(str(p))
            except Exception:  # noqa: BLE001
                continue
            if orig is None:
                orig = im.size
            if im.size != orig:
                continue           # solo el lienzo dominante
            b = im.convert("RGBA").getbbox()
            if b:
                box = b if box is None else (
                    min(box[0], b[0]), min(box[1], b[1]),
                    max(box[2], b[2]), max(box[3], b[3]))
        if not orig or not box:
            return
        ow, oh = orig
        pad = 2
        x0 = max(0, box[0] - pad)
        y0 = max(0, box[1] - pad)
        x1 = min(ow, box[2] + pad)
        y1 = min(oh, box[3] + pad)
        cw, ch = x1 - x0, y1 - y0
        if cw >= ow * 0.96 and ch >= oh * 0.96:
            return                 # ya está ajustado
        self._orig_size = orig
        self._crop_box = (x0, y0, x1, y1)
        self._base_size = (cw, ch)
        self.anim["width"] = cw
        self.anim["height"] = ch

    def _load_texture(self, path):
        """PNG -> textura: recortada al margen real, ajustada al tamaño base sin deformar y
        reducida a la resolución de pantalla."""
        target = self._base_size
        try:
            from PIL import Image
            im = Image.open(str(path))
            changed = False
            box = self._crop_box
            if box and im.size == self._orig_size:
                im = im.crop(box)
                changed = True
            if target is not None and im.size != tuple(target):
                im = self._fit(im.convert("RGBA"), tuple(target))
                changed = True
            if self._bake < 0.999:
                w = max(1, int(round(im.width * self._bake)))
                h = max(1, int(round(im.height * self._bake)))
                im = im.convert("RGBA").resize((w, h), Image.LANCZOS)
                changed = True
            if not changed:
                return Gdk.Texture.new_from_filename(str(path))
            im = im.convert("RGBA")
            gbytes = GLib.Bytes.new(im.tobytes())
            return Gdk.MemoryTexture.new(
                im.width, im.height, Gdk.MemoryFormat.R8G8B8A8, gbytes, im.width * 4)
        except Exception:  # noqa: BLE001
            try:
                return Gdk.Texture.new_from_filename(str(path))
            except Exception:  # noqa: BLE001
                return None

    @staticmethod
    def _fit(im, target):
        """Encaja im en target conservando la proporción, anclado abajo al centro."""
        from PIL import Image
        tw, th = target
        k = min(tw / im.width, th / im.height)
        nw, nh = max(1, round(im.width * k)), max(1, round(im.height * k))
        pixel_art = max(tw, th) <= 96
        im = im.resize((nw, nh), Image.NEAREST if pixel_art else Image.LANCZOS)
        out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        out.alpha_composite(im, ((tw - nw) // 2, th - nh))
        return out
