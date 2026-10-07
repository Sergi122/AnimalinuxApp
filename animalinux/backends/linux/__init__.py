"""Backend Linux: Wayland (wlr-layer-shell, Hyprland/Sway) y X11 (EWMH)."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

NAME = "linux"
APP_NAME = "AnimaLinux"   # nombre visible del producto en este sistema
LOGO = "logo.png"         # archivo de ui/assets
SUBPROCESS_KW = {}                       # sin flags especiales
PIP_EXTRA = ("--break-system-packages",)  # pip --user en distros con PEP 668


# ── rutas (XDG) ─────────────────────────────────────────────────────────────
def _xdg(env, default):
    return Path(os.environ.get(env, str(Path.home() / default)))


def dirs():
    data = _xdg("XDG_DATA_HOME", ".local/share") / "animalinux"
    config = _xdg("XDG_CONFIG_HOME", ".config") / "animalinux"
    rt = os.environ.get("XDG_RUNTIME_DIR")
    if rt:
        runtime = Path(rt) / "animalinux"
    else:   # sin XDG_RUNTIME_DIR: nada de una ruta fija y compartida en /tmp
        import tempfile
        runtime = Path(tempfile.gettempdir()) / f"animalinux-{os.getuid()}"
    return data, config, runtime


# ── arranque: relanzados previos a GTK ──────────────────────────────────────
def _is_wayland():
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    return session == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


def _has_layer_shell():
    try:
        import gi
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _ensure_x11_backend_for_non_wlroots_wayland():
    """
    wlr-layer-shell solo existe en compositores wlroots (Hyprland, Sway...).
    En una sesión Wayland de GNOME/KDE el overlay usa el backend X11, pero GTK
    conectaría por Wayland puro y ese backend perdería los hints EWMH y el
    click-through. Si hay Wayland SIN layer-shell, se fuerza GDK_BACKEND=x11 y
    nos relanzamos para conectar por XWayland. En Hyprland/Sway no hace nada.
    """
    if os.environ.get("ANIMALINUX_X11_FORCED"):
        return
    if not _is_wayland():
        return
    if _has_layer_shell():
        return
    if not os.environ.get("DISPLAY"):
        return  # sin XWayland: Wayland puro (degradado)
    os.environ["GDK_BACKEND"] = "x11"
    os.environ["ANIMALINUX_X11_FORCED"] = "1"
    os.execv(sys.executable, [sys.executable, "-m", "animalinux"] + sys.argv[1:])


def _ensure_layer_shell_preload():
    """
    gtk4-layer-shell DEBE precargarse antes que GTK, o init_for_window() no
    funciona y las mascotas salen como ventanas normales. LD_PRELOAD se lee al
    arrancar, así que nos relanzamos con la variable puesta.
    """
    import glob

    if os.environ.get("ANIMALINUX_PRELOADED"):
        return
    libs = []
    for base in ("/usr/lib", "/usr/lib64", "/lib", "/usr/lib/x86_64-linux-gnu"):
        libs += glob.glob(os.path.join(base, "libgtk4-layer-shell.so*"))
    if not libs:
        return
    lib = next((p for p in libs if p.endswith(".so")), sorted(libs)[0])
    preload = os.environ.get("LD_PRELOAD", "")
    if lib not in preload:
        os.environ["LD_PRELOAD"] = (preload + ":" + lib).strip(":")
    os.environ["ANIMALINUX_PRELOADED"] = "1"
    os.execv(sys.executable, [sys.executable, "-m", "animalinux"] + sys.argv[1:])


def prepare_process():
    _ensure_x11_backend_for_non_wlroots_wayland()
    _ensure_layer_shell_preload()


# ── overlay ─────────────────────────────────────────────────────────────────
def overlay():
    if os.environ.get("ANIMALINUX_X11_FORCED"):
        from ...overlay.x11_animation import MascotWindow
        return MascotWindow, "x11"
    if _is_wayland() and _has_layer_shell():
        from ...overlay.normal_animation import MascotWindow
        return MascotWindow, "wayland"
    from ...overlay.x11_animation import MascotWindow
    return MascotWindow, "x11"


# ── plataformas (bordes de ventanas) ────────────────────────────────────────
def _platforms_hyprctl():
    from .hyprcursor import clients as hypr_clients
    try:
        clients = hypr_clients()   # socket IPC, sin fork/exec
        if clients is None:
            out = subprocess.run(
                ["hyprctl", "-j", "clients"],
                capture_output=True, text=True, timeout=2).stdout
            clients = json.loads(out)
        plats = []
        for c in clients:
            if c.get("hidden") or not c.get("mapped", True):
                continue
            if c.get("workspace", {}).get("id", 1) < 0:
                continue   # special/scratchpad
            at = c.get("at") or [0, 0]
            size = c.get("size") or [0, 0]
            if size[0] < 80 or size[1] < 40:
                continue
            plats.append((at[0], at[0] + size[0], at[1]))
        return plats
    except Exception:  # noqa: BLE001
        return None


def _platforms_wnck():
    """libwnck (EWMH): GNOME/Cinnamon/MATE/Xfce. Las mascotas quedan fuera
    solas (llevan SKIP_TASKBAR). libwnck NO es thread-safe: solo hilo principal."""
    try:
        import gi
        gi.require_version("Wnck", "3.0")
        from gi.repository import Wnck
        screen = Wnck.Screen.get_default()
        screen.force_update()
        plats = []
        for w in screen.get_windows():
            if w.is_minimized() or w.is_skip_tasklist():
                continue
            if w.get_window_type() not in (
                    Wnck.WindowType.NORMAL, Wnck.WindowType.DIALOG):
                continue
            x, y, width, height = w.get_geometry()
            if width < 80 or height < 40:
                continue
            plats.append((x, x + width, y))
        return plats
    except Exception:  # noqa: BLE001
        return None


def platforms_async(callback):
    """hyprctl en un hilo (subproceso, no toca GDK); si no hay Hyprland, Wnck
    en el hilo principal."""
    from gi.repository import GLib

    def work():
        plats = _platforms_hyprctl()
        if plats is not None:
            GLib.idle_add(lambda: callback(plats) and False)
        else:
            GLib.idle_add(lambda: callback(_platforms_wnck()) and False)

    threading.Thread(target=work, daemon=True).start()


# ── pantalla completa ───────────────────────────────────────────────────────
class _Wnck2s:
    """Sondeo liviano (sin subproceso) de si la ventana activa está a
    pantalla completa, vía Wnck/EWMH."""

    def __init__(self, pause):
        from gi.repository import GLib
        self._glib = GLib
        self._pause = pause
        self._active = False
        self._id = GLib.timeout_add(2000, self._tick)

    def _tick(self):
        try:
            import gi
            gi.require_version("Wnck", "3.0")
            from gi.repository import Wnck
            screen = Wnck.Screen.get_default()
            screen.force_update()
            active = screen.get_active_window()
            fs = bool(active and active.is_fullscreen())
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
    """Wayland/layer-shell: la mascota vive en la capa OVERLAY y se ve siempre,
    así que pausar sería visible: opt-in (cfg is True). X11: una ventana
    fullscreen ajena tapa la mascota, así que animar sin verse es gasto puro:
    activo salvo cfg is False."""
    from ... import overlay as _ov
    if _ov.BACKEND == "wayland":
        if cfg is True:
            from .hypr import HyprMonitor
            mon = HyprMonitor(pause)
            mon.start()
            return mon
        return None
    if cfg is not False:
        return _Wnck2s(pause)
    return None


def forward_to_running(args):
    """La instancia única la resuelve GApplication por D-Bus."""
    return False


# ── bandeja (proceso GTK3 aparte: no se puede mezclar con GTK4) ─────────────
_tray_proc = None


def start_tray(app=None):
    global _tray_proc
    try:
        from gi.repository import Gio, GLib
        env = os.environ.copy()
        # el tray es GTK3: no debe heredar el LD_PRELOAD de gtk4-layer-shell
        env.pop("LD_PRELOAD", None)
        env.pop("ANIMALINUX_PRELOADED", None)
        launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.NONE)
        launcher.set_environ([f"{k}={v}" for k, v in env.items()])
        _tray_proc = launcher.spawnv(
            ["python3", "-m", "animalinux.backends.linux.tray"])
    except GLib.Error:
        pass  # sin bandeja; se puede abrir con `animalinux --show`


def stop_tray():
    global _tray_proc
    if _tray_proc:
        try:
            _tray_proc.force_exit()
        except Exception:  # noqa: BLE001
            pass
        _tray_proc = None


from . import autostart  # noqa: E402,F401


# ── utilidades del sistema ──────────────────────────────────────────────────
def _clean_env():
    """Entorno sin el LD_PRELOAD de gtk4-layer-shell: los programas GTK3
    (Firefox, el tray) abortan al mezclarlo con GTK4."""
    env = os.environ.copy()
    env.pop("LD_PRELOAD", None)
    env.pop("ANIMALINUX_PRELOADED", None)
    return env


def open_url(url):
    try:
        subprocess.Popen(["xdg-open", url], env=_clean_env(), start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        import webbrowser
        webbrowser.open(url)


def open_folder(path):
    for cmd in ("xdg-open", "dolphin", "nautilus", "thunar", "pcmanfm"):
        try:
            subprocess.Popen([cmd, str(path)], env=_clean_env())
            return
        except FileNotFoundError:
            continue


def system_language():
    """Código de idioma de 2 letras del sistema ('es', 'en'...) o ''."""
    import locale
    return (locale.getlocale()[0] or "")[:2].lower()


def ffmpeg_hint():
    return None   # el comando depende del gestor de paquetes (ver image_processor)


def restart_app():
    subprocess.Popen(
        ["sh", "-c", "animalinux --quit; sleep 2; exec animalinux --show"],
        env=_clean_env(), start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
