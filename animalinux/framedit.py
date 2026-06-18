"""
Motor del editor FRAME POR FRAME.

Cada cuadro de la animación es independiente y puede ser:
  - una transformación de la imagen base (mover/rotar/escalar/voltear), o
  - una imagen DIBUJADA importada para ese cuadro (frames de un artista).

Así soporta las dos cosas que pediste: armar el movimiento posando la imagen,
o cargar frames dibujados a mano cuadro por cuadro para la máxima calidad.

El editor gráfico (lienzo + línea de tiempo + papel cebolla) va encima de esto.
Aquí está la lógica probable: modelo, render, validador y guardado como pose.
"""
import json
from pathlib import Path

from PIL import Image

from .core import image_processor as importer


def default_frame(source="base"):
    return {"source": source, "dx": 0.0, "dy": 0.0,
            "angle": 0.0, "sx": 1.0, "sy": 1.0, "flip": False}


class FrameModel:
    """Lista ordenada de cuadros (cada uno un dict de transformación)."""
    def __init__(self, base_path):
        self.base_path = str(base_path)
        self._base = Image.open(base_path).convert("RGBA")
        bbox = self._base.getbbox()
        if bbox:
            self._base = self._base.crop(bbox)
        self.frames = [default_frame()]
        self._cache = {self.base_path: self._base}

    # ---- edición de la lista de cuadros ----
    def add(self, source="base"):
        self.frames.append(default_frame(source))

    def duplicate(self, i):
        if 0 <= i < len(self.frames):
            self.frames.insert(i + 1, dict(self.frames[i]))

    def delete(self, i):
        if 0 <= i < len(self.frames) and len(self.frames) > 1:
            self.frames.pop(i)

    def move(self, i, j):
        if 0 <= i < len(self.frames) and 0 <= j < len(self.frames):
            self.frames.insert(j, self.frames.pop(i))

    def set(self, i, **kw):
        if 0 <= i < len(self.frames):
            self.frames[i].update(kw)

    def import_drawn(self, i, path):
        """Reemplaza el cuadro i por una imagen dibujada importada."""
        if 0 <= i < len(self.frames):
            self.frames[i]["source"] = str(path)

    # ---- render ----
    def _src(self, source):
        if source in self._cache:
            return self._cache[source]
        img = Image.open(source).convert("RGBA")
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        self._cache[source] = img
        return img

    def _metrics(self):
        # lienzo con holgura, basado en el cuadro más grande tras escalar
        maxw = maxh = 0
        for fr in self.frames:
            src = self._src(fr["source"]) if fr["source"] != "base" else self._base
            w, h = src.size
            maxw = max(maxw, int(w * fr["sx"]))
            maxh = max(maxh, int(h * fr["sy"]))
        mx = max(8, round(maxw * 0.4))
        top = max(12, round(maxh * 0.55))
        bot = max(4, round(maxh * 0.12))
        cw, ch = maxw + 2 * mx, maxh + top + bot
        return cw, ch, ch - bot, mx

    def render_frame(self, i, metrics=None):
        cw, ch, floor, mx = metrics or self._metrics()
        fr = self.frames[i]
        src = self._src(fr["source"]) if fr["source"] != "base" else self._base
        img = src
        if fr["flip"]:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if fr["sx"] != 1.0 or fr["sy"] != 1.0:
            img = img.resize((max(1, int(img.width * fr["sx"])),
                              max(1, int(img.height * fr["sy"]))), Image.LANCZOS)
        canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        px = int(cw / 2 - img.width / 2 + fr["dx"])
        py = int(floor - img.height + fr["dy"])
        canvas.alpha_composite(img, (px, py))
        if fr["angle"]:
            canvas = canvas.rotate(fr["angle"], resample=Image.BICUBIC,
                                   expand=False, center=(cw / 2, floor))
        return canvas

    def render_all(self):
        m = self._metrics()
        return [self.render_frame(i, m) for i in range(len(self.frames))]

    # ---- validador (la "IA que verifica") ----
    def validate(self):
        avisos = []
        frames = self.render_all()
        if len(frames) < 2:
            avisos.append("Tienes 1 cuadro: añade más para que se anime.")
        sizes = {f.size for f in frames}
        if len(sizes) > 1:
            avisos.append("Los cuadros tienen distinto tamaño (se uniformarán).")
        # alineación de los pies (parte inferior del contenido)
        bottoms = []
        for f in frames:
            bb = f.getbbox()
            if bb:
                bottoms.append(bb[3])
        if bottoms and (max(bottoms) - min(bottoms)) > max(4, frames[0].height * 0.06):
            avisos.append("Los pies se mueven mucho entre cuadros: revisa la "
                          "alineación para que no 'patine'.")
        # personaje cortado por el borde
        for idx, f in enumerate(frames):
            bb = f.getbbox()
            if bb and (bb[0] <= 0 or bb[1] <= 0 or bb[2] >= f.width or bb[3] >= f.height):
                avisos.append(f"El cuadro {idx + 1} toca el borde (puede recortarse).")
                break
        if not avisos:
            avisos.append("Todo correcto ✔ La animación se ve consistente.")
        return avisos

    # ---- guardar como pose ----
    def save_as_pose(self, frames_dir, pose):
        frames = self.render_all()
        w = max(f.width for f in frames)
        h = max(f.height for f in frames)
        out = (Path(frames_dir) if pose == "default"
               else Path(frames_dir) / pose)
        out.mkdir(parents=True, exist_ok=True)
        # limpiar frames previos de esa pose
        for old in out.glob("frame_*.png"):
            old.unlink()
        for old in out.glob("flip_*.png"):
            old.unlink()
        for i, f in enumerate(frames):
            if f.size != (w, h):
                c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                c.alpha_composite(f, ((w - f.width) // 2, h - f.height))
                f = c
            f.save(out / f"frame_{i:04d}.png")
        importer.ensure_flipped(out)
        return len(frames), w, h

    # ---- proyecto (guardar/cargar el trabajo del editor) ----
    def to_json(self):
        return json.dumps({"base": self.base_path, "frames": self.frames})

    @classmethod
    def from_json(cls, text):
        data = json.loads(text)
        m = cls(data["base"])
        m.frames = data["frames"]
        return m
