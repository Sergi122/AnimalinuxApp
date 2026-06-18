"""
Librería de animaciones: guarda en library.json los metadatos de cada
animación importada y su estado en el escritorio (visible, posición, velocidad).

Estructura del JSON:
{
  "config": { "default_fps": 12 },
  "animations": {
     "<id>": {
        "id": "...",
        "name": "Theresa",
        "frame_count": 24,
        "width": 200, "height": 260,
        "fps": 12,                 # velocidad propia de esta animación
        "on_desktop": true,        # si se muestra ahora mismo
        "x": 100, "y": 400,        # posición en pantalla
        "scale": 1.0
     }, ...
  }
}
Los frames .png viven en  DATA_DIR/animations/<id>/frame_0000.png ...
"""
import json
import uuid
from .. import paths


class Library:
    def __init__(self):
        self.config = {"default_fps": 12}
        self.animations = {}
        self.load()

    # ---------- persistencia ----------
    def load(self):
        paths.ensure_dirs()
        if paths.LIBRARY_FILE.exists():
            try:
                data = json.loads(paths.LIBRARY_FILE.read_text())
                self.config = data.get("config", self.config)
                self.animations = data.get("animations", {})
            except (json.JSONDecodeError, OSError):
                # archivo corrupto: empezamos limpio sin romper la app
                self.animations = {}

    def save(self):
        paths.ensure_dirs()
        data = {"config": self.config, "animations": self.animations}
        tmp = paths.LIBRARY_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        tmp.replace(paths.LIBRARY_FILE)  # escritura atómica

    # ---------- operaciones ----------
    def new_id(self):
        return uuid.uuid4().hex[:12]

    def add(self, anim_id, name, frame_count, width, height):
        self.animations[anim_id] = {
            "id": anim_id,
            "name": name,
            "frame_count": frame_count,
            "width": width,
            "height": height,
            "fps": self.config.get("default_fps", 12),
            "mode": "gif",        # "gif" = quieta | "life" = camina/idle sola
            "author": "",
            "poses": ["default"],
            "on_desktop": False,
            "x": 100,
            "y": 100,
            "scale": 1.0,
        }
        self.save()

    def remove(self, anim_id):
        self.animations.pop(anim_id, None)
        # borrar los frames del disco
        d = paths.ANIMATIONS_DIR / anim_id
        if d.exists():
            for f in d.iterdir():
                f.unlink()
            d.rmdir()
        self.save()

    def update(self, anim_id, **kwargs):
        if anim_id in self.animations:
            self.animations[anim_id].update(kwargs)
            self.save()

    def frames_dir(self, anim_id):
        return paths.ANIMATIONS_DIR / anim_id

    def active(self):
        """Animaciones marcadas para mostrarse en el escritorio."""
        return [a for a in self.animations.values() if a.get("on_desktop")]
