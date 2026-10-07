"""Backend Windows: Win32 nativo.

Reutiliza la MascotWindow de GTK (poses, modo Vida, arrastre, editores) y solo
cambia lo que es del sistema: ventana siempre-encima de tamaño sprite movida
con SetWindowPos, bandeja con Shell_NotifyIcon, rutas %APPDATA%, autostart en
el registro y lista de ventanas con EnumWindows. Cero subprocesos.
"""
import os
from pathlib import Path

NAME = "windows"
# Sin ventana de consola negra al lanzar ffmpeg/mpv desde la app gráfica
SUBPROCESS_KW = {"creationflags": 0x08000000}   # CREATE_NO_WINDOW
PIP_EXTRA = ()


def dirs():
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return (local / "AnimaLinux" / "data", roaming / "AnimaLinux",
            local / "AnimaLinux" / "run")


def prepare_process():
    # Una GL por ventana cuesta decenas de MB y la transparencia por píxel
    # con GL en Win32 es poco fiable: ventanas pequeñas + render por CPU es lo
    # más ligero y estable. Se puede anular con GSK_RENDERER.
    os.environ.setdefault("GSK_RENDERER", "cairo")


def overlay():
    from .overlay import MascotWindow
    return MascotWindow, "win32"


# ── plataformas (bordes de ventanas) ────────────────────────────────────────
def platforms_async(callback):
    """EnumWindows tarda <1 ms: se resuelve en el acto, en el hilo principal."""
    from . import win32
    try:
        k = 1.0 / win32.system_scale()   # px físicos -> lógicos de GDK
        plats = [(int(l * k), int(r * k), int(t * k))
                 for (l, t, r, _b) in win32.top_level_rects()]
    except Exception:  # noqa: BLE001
        plats = None
    callback(plats)


# ── pantalla completa ───────────────────────────────────────────────────────
class _FullscreenPoll:
    def __init__(self, pause):
        from gi.repository import GLib
        self._glib, self._pause, self._active = GLib, pause, False
        self._id = GLib.timeout_add(2000, self._tick)

    def _tick(self):
        from . import win32
        try:
            fs = win32.fullscreen_app_active()
        except Exception:  # noqa: BLE001
            fs = False
        if fs != self._active:
            self._active = fs
            self._pause(fs)
        return True

    def stop(self):
        if self._id:
            self._glib.source_remove(self._id)
            self._id = None


def fullscreen_watch(pause, cfg):
    # Como en X11: una app a pantalla completa tapa a la mascota, así que
    # seguir animándola sería gasto puro. Activo salvo cfg is False.
    return _FullscreenPoll(pause) if cfg is not False else None


# ── bandeja + instancia única ───────────────────────────────────────────────
_tray = None


def start_tray(app):
    global _tray
    from .tray import Tray
    _tray = Tray(app)


def stop_tray():
    global _tray
    if _tray:
        _tray.destroy()
        _tray = None


def forward_to_running(args):
    from .tray import forward
    return forward(args)


from . import autostart  # noqa: E402,F401


# ── utilidades del sistema ──────────────────────────────────────────────────
def open_url(url):
    import webbrowser
    webbrowser.open(url)


def open_folder(path):
    os.startfile(str(path))   # noqa: S606  (Explorador de Windows)


def system_language():
    """Idioma de la interfaz de Windows ('es-BO' -> 'es')."""
    import ctypes
    buf = ctypes.create_unicode_buffer(85)
    if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85):
        return buf.value[:2].lower()
    return ""


def ffmpeg_hint():
    return "winget install ffmpeg"


def restart_app():
    import subprocess
    import sys
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    cmd = [exe] if getattr(sys, "frozen", False) else [exe, "-m", "animalinux"]
    # cmd /c: espera 2 s a que la instancia vieja salga y arranca la nueva
    subprocess.Popen(
        ["cmd", "/c", "ping -n 3 127.0.0.1 >nul & " + subprocess.list2cmdline(cmd + ["--show"])],
        creationflags=0x00000008 | 0x08000000,   # DETACHED_PROCESS | CREATE_NO_WINDOW
        close_fds=True)
    subprocess.Popen(cmd + ["--quit"], creationflags=0x08000000)
