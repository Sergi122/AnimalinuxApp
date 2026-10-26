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


def _is_gnome():
    """GNOME (Mutter) no implementa wlr-layer-shell: ahí va por XWayland."""
    desk = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    return any(k in desk for k in ("GNOME", "PANTHEON", "UNITY"))


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
    if _has_layer_shell() and not _is_gnome():
        return    # Hyprland, Sway, KDE Plasma (KWin), niri, labwc…
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
    if _is_wayland() and _has_layer_shell() and not _is_gnome():
        from ...overlay.normal_animation import MascotWindow
        return MascotWindow, "wayland"
    from ...overlay.x11_animation import MascotWindow
    return MascotWindow, "x11"


# ── plataformas (bordes de ventanas) ────────────────────────────────────────
_LAST_RECTS = []      # (x0, y0, x1, y1) globales de las ventanas visibles


def window_rects():
    """Rectángulos de las ventanas visibles (de la última consulta de
    plataformas): para esconderse detrás de una en las escondidas."""
    return list(_LAST_RECTS)


def _platforms_hyprctl():
    global _LAST_RECTS
    from .hyprcursor import clients as hypr_clients, monitors as hypr_monitors
    try:
        clients = hypr_clients()   # socket IPC, sin fork/exec
        if clients is None:
            out = subprocess.run(
                ["hyprctl", "-j", "clients"],
                capture_output=True, text=True, timeout=2).stdout
            clients = json.loads(out)
        # solo las ventanas de los escritorios que se VEN: antes la mascota
        # podía subirse a una ventana de otro escritorio (flotaba en el aire)
        active = None
        mons = hypr_monitors()
        if mons:
            active = {m.get("activeWorkspace", {}).get("id") for m in mons}
            active |= {m.get("specialWorkspace", {}).get("id") for m in mons}
            active.discard(None)
            active.discard(0)
        plats, rects = [], []
        for c in clients:
            if c.get("hidden") or not c.get("mapped", True):
                continue
            ws = c.get("workspace", {}).get("id", 1)
            if ws < 0:
                continue   # special/scratchpad
            if active is not None and ws not in active:
                continue
            at = c.get("at") or [0, 0]
            size = c.get("size") or [0, 0]
            if size[0] < 80 or size[1] < 40:
                continue
            plats.append((at[0], at[0] + size[0], at[1]))
            rects.append((at[0], at[1], at[0] + size[0], at[1] + size[1]))
        _LAST_RECTS = rects
        return plats
    except Exception:  # noqa: BLE001
        return None


def _platforms_wnck():
    """libwnck (EWMH): GNOME/Cinnamon/MATE/Xfce. Las mascotas quedan fuera
    solas (llevan SKIP_TASKBAR). libwnck NO es thread-safe: solo hilo principal."""
    global _LAST_RECTS
    try:
        import gi
        gi.require_version("Wnck", "3.0")
        from gi.repository import Wnck
        screen = Wnck.Screen.get_default()
        screen.force_update()
        ws = screen.get_active_workspace()
        plats, rects = [], []
        for w in screen.get_windows():
            if w.is_minimized() or w.is_skip_tasklist():
                continue
            if ws is not None and not w.is_visible_on_workspace(ws):
                continue
            if w.get_window_type() not in (
                    Wnck.WindowType.NORMAL, Wnck.WindowType.DIALOG):
                continue
            x, y, width, height = w.get_geometry()
            if width < 80 or height < 40:
                continue
            plats.append((x, x + width, y))
            rects.append((x, y, x + width, y + height))
        _LAST_RECTS = rects
        return plats
    except Exception:  # noqa: BLE001
        return None


def active_workspace():
    """Clave del escritorio activo ("hypr:3", "kde:2", "x11:0") o None."""
    from . import kwin
    from .hyprcursor import _json_request
    ws = _json_request(b"j/activeworkspace")
    if isinstance(ws, dict) and "id" in ws:
        return f"hypr:{ws['id']}"
    if kwin.active():
        d = kwin.bridge().desktop
        return f"kde:{d}" if d is not None else None
    try:
        import gi
        gi.require_version("Wnck", "3.0")
        from gi.repository import Wnck
        scr = Wnck.Screen.get_default()
        scr.force_update()
        w = scr.get_active_workspace()
        return f"x11:{w.get_number()}" if w is not None else None
    except Exception:  # noqa: BLE001
        return None


def workspace_watch(callback):
    """callback(dirección, clave) al cambiar de escritorio: dirección = ±1
    (hacia el siguiente/anterior), clave como en active_workspace().
    Hyprland por su socket de eventos; KDE Wayland por el puente de KWin; X11
    por Wnck. Devuelve True si se puede seguir."""
    from gi.repository import GLib
    from . import hypr
    last = {"id": None}

    def on_hypr(data):
        try:
            wid = int(data.split(",", 1)[0])
        except ValueError:
            return False
        prev, last["id"] = last["id"], wid
        if wid != prev and wid > 0:
            d = 0 if prev is None or prev <= 0 else (1 if wid > prev else -1)
            callback(d, f"hypr:{wid}")
        return False
    if hypr.events().on("workspacev2", on_hypr):
        return True
    from . import kwin
    if kwin.active():
        kwin.bridge().on_desktop(lambda d, n: callback(d, f"kde:{n}"))
        return True
    try:
        import gi
        gi.require_version("Wnck", "3.0")
        from gi.repository import Wnck
        screen = Wnck.Screen.get_default()

        def on_wnck(scr, prev_ws):
            cur = scr.get_active_workspace()
            if cur is None:
                return
            n = cur.get_number()
            d = 0 if prev_ws is None else n - prev_ws.get_number()
            d = (d > 0) - (d < 0)
            GLib.idle_add(lambda: callback(d, f"x11:{n}") and False)
        screen.connect("active-workspace-changed", on_wnck)
        return True
    except Exception:  # noqa: BLE001
        return False


def warp_cursor(x, y):
    """Lleva el cursor a (x, y) globales. Hyprland por su socket; X11 con
    XWarpPointer. KDE/GNOME en Wayland no lo permiten: False."""
    from .hyprcursor import move_cursor
    if move_cursor(x, y):
        return True
    if os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("ANIMALINUX_X11_FORCED"):
        return False
    try:
        from Xlib import display as xd
        d = xd.Display()
        d.screen().root.warp_pointer(int(x), int(y))
        d.sync()
        d.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def start_bridges(app):
    """KDE Plasma en Wayland: carga el script-puente de KWin (ventanas,
    cursor, escritorios, pantalla completa). En el resto no hace nada."""
    from . import kwin
    try:
        if kwin.start(app):
            kwin.bridge().want_cursor("play", 200)
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def stop_bridges():
    from . import kwin
    if kwin.active():
        kwin.bridge().stop()


def platforms_async(callback):
    """hyprctl en un hilo (subproceso, no toca GDK); KDE Wayland: lo que
    mandó el puente de KWin; si no, Wnck en el hilo principal."""
    from gi.repository import GLib
    from . import kwin
    if kwin.active():
        global _LAST_RECTS
        rects = kwin.bridge().rects
        if rects is not None:
            _LAST_RECTS = list(rects)
            plats = [(x0, x1, y0) for (x0, y0, x1, y1) in rects
                     if x1 - x0 >= 80 and y1 - y0 >= 40]
            GLib.idle_add(lambda: callback(plats) and False)
            return

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
    from . import kwin
    if _ov.BACKEND == "wayland" and kwin.active():
        if cfg is True:
            kwin.bridge().on_fullscreen(pause)
        return None
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
