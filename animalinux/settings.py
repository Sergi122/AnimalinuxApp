"""
Configuración persistente del usuario — ~/.config/animalinux/settings.json
"""
import json
from pathlib import Path

_PATH = Path.home() / ".config" / "animalinux" / "settings.json"

_DEFAULTS = {
    "tutorial_paint_shown":  False,
    "tutorial_pixel_shown":  False,
    "autosave_minutes":      5,
}


def _load() -> dict:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict):
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get(key: str, default=None):
    d = _load()
    return d.get(key, _DEFAULTS.get(key, default))


def set_val(key: str, value):
    d = _load()
    d[key] = value
    _save(d)
