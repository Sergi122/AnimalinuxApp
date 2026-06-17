"""Rutas estandar (XDG) donde AnimaLinux guarda todo."""
import os
from pathlib import Path

APP_NAME = "animalinux"


def _xdg(env, default):
    return Path(os.environ.get(env, str(Path.home() / default)))


# ~/.local/share/animalinux  -> librería de animaciones (frames ya procesados)
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / APP_NAME
# ~/.config/animalinux        -> config + library.json
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / APP_NAME
# runtime (socket de IPC)
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / APP_NAME

ANIMATIONS_DIR = DATA_DIR / "animations"   # un subdir por animación con sus frames .png
LIBRARY_FILE = CONFIG_DIR / "library.json"  # metadatos + estado del escritorio
SOCKET_FILE = RUNTIME_DIR / "ipc.sock"      # IPC single-instance / tray


def ensure_dirs():
    for d in (DATA_DIR, CONFIG_DIR, RUNTIME_DIR, ANIMATIONS_DIR):
        d.mkdir(parents=True, exist_ok=True)
