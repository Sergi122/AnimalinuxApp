"""Posición global del cursor en Hyprland vía su socket IPC (sin lanzar procesos).

Wayland no deja leer el puntero fuera de la superficie, pero Hyprland lo expone
con el comando `cursorpos`. Sirve para arrastrar o hacer que la mascota agarre
el cursor SIN ampliar su ventana a pantalla completa."""
import os
import socket


def _path():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    rt = os.environ.get("XDG_RUNTIME_DIR")
    if not sig or not rt:
        return None
    p = f"{rt}/hypr/{sig}/.socket.sock"
    return p if os.path.exists(p) else None


_PATH = _path()


def cursor_pos():
    """(x, y) globales del cursor, o None si no hay Hyprland / falla.
    En KDE Wayland, lo último que mandó el puente de KWin."""
    if _PATH is None:
        from . import kwin
        return kwin.bridge().cursor_pos() if kwin.active() else None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.05)
        s.connect(_PATH)
        s.sendall(b"cursorpos")
        data = s.recv(64).decode()
        s.close()
        x, y = data.replace(",", " ").split()[:2]
        return int(float(x)), int(float(y))
    except Exception:  # noqa: BLE001
        return None


def move_cursor(x, y):
    """Mueve el cursor (coords globales). True si se pudo."""
    if _PATH is None:
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.05)
        s.connect(_PATH)
        s.sendall(f"dispatch movecursor {int(x)} {int(y)}".encode())
        s.recv(64)
        s.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def clients():
    """Lista `j/clients` de Hyprland por el socket IPC (sin lanzar hyprctl).
    Devuelve None si no hay Hyprland o falla (el llamador usa su fallback)."""
    return _json_request(b"j/clients")


def monitors():
    """`j/monitors` (escritorio activo de cada monitor) o None."""
    return _json_request(b"j/monitors")


def _json_request(cmd):
    if _PATH is None:
        return None
    import json
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(_PATH)
        s.sendall(cmd)
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        return json.loads(buf.decode())
    except Exception:  # noqa: BLE001
        return None
