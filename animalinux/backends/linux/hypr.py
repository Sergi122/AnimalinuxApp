"""
Escucha los eventos de Hyprland (socket2) para pausar las animaciones cuando
hay una ventana en pantalla completa, y reanudarlas al salir. Ahorra GPU/batería.
Todo va envuelto en try/except: si algo del socket falla, la app sigue igual.
"""
import os
import socket
import threading
from pathlib import Path

from gi.repository import GLib


def _socket_path():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not sig:
        return None
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime:
        return None   # nada de buscar sockets en /tmp (cualquiera podría crear uno)
    p = Path(runtime) / "hypr" / sig / ".socket2.sock"
    return p if p.exists() else None


class HyprMonitor:
    def __init__(self, on_fullscreen):
        self.on_fullscreen = on_fullscreen  # callback(bool)
        self._stop = False

    def start(self):
        path = _socket_path()
        if not path:
            return  # no estamos en Hyprland (o no se pudo localizar el socket)
        threading.Thread(target=self._run, args=(path,), daemon=True).start()

    def _run(self, path):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(str(path))
            buf = b""
            while not self._stop:
                data = sock.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._handle(line.decode("utf-8", "ignore"))
        except OSError:
            pass

    def _handle(self, line):
        # eventos tipo "fullscreen>>1" / "fullscreen>>0"
        if line.startswith("fullscreen>>"):
            active = line.split(">>", 1)[1].strip() == "1"
            GLib.idle_add(self.on_fullscreen, active)

    def stop(self):
        self._stop = True


class _HyprEvents:
    """Un único lector del socket de eventos de Hyprland para todo el que
    quiera escuchar algo (compartir pantalla, cambio de escritorio...).
    on(nombre, fn): fn(datos) se llama en el hilo principal."""

    def __init__(self):
        self._subs = {}
        self._started = False

    def on(self, name, fn):
        self._subs.setdefault(name, []).append(fn)
        if not self._started:
            path = _socket_path()
            if path is None:
                return False
            self._started = True
            threading.Thread(target=self._run, args=(path,), daemon=True).start()
        return True

    def _run(self, path):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(str(path))
            buf = b""
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    name, _, rest = line.decode("utf-8", "ignore").partition(">>")
                    for fn in self._subs.get(name, ()):
                        GLib.idle_add(fn, rest)
        except OSError:
            pass


_EVENTS = None


def events():
    global _EVENTS
    if _EVENTS is None:
        _EVENTS = _HyprEvents()
    return _EVENTS
