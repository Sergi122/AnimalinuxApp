"""
Configuración persistente del usuario — settings.json en el directorio de configuración
"""
import json
from . import paths

_PATH = paths.CONFIG_DIR / "settings.json"

_DEFAULTS = {
    "tutorial_paint_shown":  False,
    "tutorial_pixel_shown":  False,
    "autosave_minutes":      5,
    "auto_update_check":     True,
    "last_update_check":     0,
    "update_available":      "",
}


def _load() -> dict:
    try:
        d = json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d if isinstance(d, dict) else {}


def _save(data: dict):
    """Escritura atómica: un corte de luz a mitad no deja el archivo roto."""
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PATH.with_name(_PATH.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_PATH)


def get(key: str, default=None):
    d = _load()
    return d.get(key, _DEFAULTS.get(key, default))


def set_val(key: str, value):
    d = _load()
    d[key] = value
    _save(d)
