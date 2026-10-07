"""Rutas donde AnimaLinux guarda todo (las decide el backend de la plataforma:
XDG en Linux, %APPDATA%/%LOCALAPPDATA% en Windows)."""
from .backends import current as _backend

APP_NAME = "animalinux"

# librería de animaciones (frames ya procesados) / config + library.json /
# runtime (IPC)
DATA_DIR, CONFIG_DIR, RUNTIME_DIR = _backend.dirs()

ANIMATIONS_DIR = DATA_DIR / "animations"   # un subdir por animación con sus frames .png
LIBRARY_FILE = CONFIG_DIR / "library.json"  # metadatos + estado del escritorio
SOCKET_FILE = RUNTIME_DIR / "ipc.sock"      # IPC single-instance / tray


def ensure_dirs():
    for d in (DATA_DIR, CONFIG_DIR, RUNTIME_DIR, ANIMATIONS_DIR):
        d.mkdir(parents=True, exist_ok=True)
