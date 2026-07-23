"""
Cerebro de AnimaLinux. Un único proceso GtkApplication que:
  - mantiene las mascotas (ventanas overlay) en el escritorio
  - abre la ventana de configuración cuando se lo piden
  - lanza el icono de bandeja (proceso aparte, ver tray.py)
  - usa instancia única: relanzar `animalinux --show` solo trae la ventana

Modos (argumentos):
  (sin args) / --daemon : arranca el servicio + mascotas (para el autostart)
  --show                : abre la ventana de configuración
  --quit                : cierra todo
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GLib  # noqa: E402

from .core.library import Library  # noqa: E402
from .core.mascot_manager import MascotManager  # noqa: E402
from .ui.control import ControlWindow  # noqa: E402
from .hypr import HyprMonitor  # noqa: E402
from .overlay import BACKEND  # noqa: E402
from . import pack as packmod  # noqa: E402

APP_ID = "dev.animalinux.App"


class AnimaApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.library = Library()
        self.manager = MascotManager(self)
        self.mascots = self.manager.mascots   # alias compartido (mismo dict)
        self.control = None
        self._started = False
        self._tray_proc = None
        self._hypr = None
        self._prox_id = None
        self._fs_watch_id = None
        self._fs_active = False

    # ------------------------------------------------------------------
    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if "--quit" in args:
            self.quit_all()
            return 0
        if not self._started:
            self._start_daemon()
        if "--show" in args:
            self.show_control()
        elif not args:
            # Steam-like: solo bandeja; abre control solo si es la primera vez
            if not self.library.animations:
                self.show_control()
        if "--daemon" in args:
            pass  # solo servicio, sin ventana
        return 0

    # ------------------------------------------------------------------
    def _start_daemon(self):
        self._started = True
        self.hold()
        from .ui import theme
        from . import i18n
        i18n.init()        # detecta / carga idioma
        theme.apply(None)  # tema oscuro global
        # restaurar mascotas que estaban en el escritorio: escalonadas (no
        # todas de golpe). Cada mascota es una ventana fullscreen ARGB
        # separada; crear varias en el mismo instante, justo al arrancar, se
        # ha visto que satura al compositor en equipos con render por
        # software (p.ej. xfwm4 sobre llvmpipe en una VM) — el resultado es
        # que una de las mascotas queda invisible varios segundos hasta que
        # el compositor se pone al día. Dar un respiro entre cada una evita
        # ese pico de carga simultánea.
        for i, anim in enumerate(self.library.active()):
            GLib.timeout_add(i * 400, self.manager.spawn, anim)
        # Pausa por pantalla completa: el comportamiento por defecto depende
        # del backend porque el efecto visual es distinto en cada uno.
        #   - Wayland/layer-shell (Hyprland/Sway): la mascota vive en la capa
        #     OVERLAY, así que se ve SIEMPRE encima, incluso sobre un juego o
        #     vídeo a pantalla completa. Pausarla ahí se notaría (se
        #     congelaría a la vista), así que sigue DESACTIVADO por defecto
        #     — opt-in con pause_on_fullscreen: true en library.json.
        #   - X11 (GNOME/KDE/Xfce/MATE/Cinnamon, o XWayland forzado): no hay
        #     capa "overlay" real, así que una ventana fullscreen ajena
        #     normalmente TAPA la mascota igual. Seguir animándola (frame
        #     clock continuo + timers) sin que se vea nada es puro gasto de
        #     batería/CPU, así que aquí queda ACTIVADO por defecto — se
        #     desactiva con pause_on_fullscreen: false.
        self._hypr = None
        pause_cfg = self.library.config.get("pause_on_fullscreen", None)
        if BACKEND == "wayland":
            if pause_cfg is True:
                self._hypr = HyprMonitor(self._on_fullscreen)
                self._hypr.start()
        elif pause_cfg is not False:
            self._fs_watch_id = GLib.timeout_add(2000, self._check_fullscreen_x11)
        # bandeja (proceso aparte para no mezclar GTK3 con GTK4)
        self._launch_tray()
        # saludo entre mascotas que se cruzan (modo Vida)
        self._prox_id = GLib.timeout_add(800, self.manager.check_proximity)
        # vigilar bordes de ventanas para que la mascota se suba/camine por ellos
        self.manager.start_platform_watch()

    def _launch_tray(self):
        try:
            import os
            # El tray es GTK3 y NO debe heredar el LD_PRELOAD de gtk4-layer-shell
            # (mezclar esa librería GTK4 en un proceso GTK3 rompe gtk_init).
            env = os.environ.copy()
            env.pop("LD_PRELOAD", None)
            env.pop("ANIMALINUX_PRELOADED", None)
            launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.NONE)
            launcher.set_environ([f"{k}={v}" for k, v in env.items()])
            self._tray_proc = launcher.spawnv(["python3", "-m", "animalinux.tray"])
        except GLib.Error:
            pass  # sin bandeja; se puede abrir con `animalinux --show`

    # ------------------------------------------------------------------
    def _on_fullscreen(self, active):
        self.manager.pause_all(active)
        return False

    def _check_fullscreen_x11(self):
        """Backend X11: sondeo liviano (sin subproceso) de si la ventana
        activa está a pantalla completa, vía Wnck/EWMH — ya es una
        dependencia blanda del proyecto (ver mascot_manager._fetch_platforms_wnck)."""
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
        if fs != self._fs_active:
            self._fs_active = fs
            self.manager.pause_all(fs)
        return True

    # ------------------------------------------------------------------
    # llamadas desde la ventana de configuración → delegan en MascotManager
    def set_mascot_visible(self, anim_id, visible):
        self.manager.set_visible(anim_id, visible)

    def set_mascot_fps(self, anim_id, fps):
        self.manager.set_fps(anim_id, fps)

    def set_mascot_scale(self, anim_id, scale):
        self.manager.set_scale(anim_id, scale)

    def set_mascot_mode(self, anim_id, mode):
        self.manager.set_mode(anim_id, mode)

    def reload_mascot(self, anim_id):
        self.manager.reload(anim_id)

    # ---------- packs (.alpack) ----------
    def import_pack(self, path):
        """Instala un pack. Devuelve el id de la nueva mascota."""
        return packmod.import_pack(self.library, path)

    def export_pack(self, anim_id, path):
        return packmod.export_pack(self.library, anim_id, path)

    def export_animation(self, anim_id, path):
        """Exporta una mascota 'sin vida' como GIF/MP4 (ver core/image_processor)."""
        from .core import image_processor as importer
        anim = self.library.animations.get(anim_id, {})
        return importer.export_animation(
            self.library.frames_dir(anim_id), path, fps=anim.get("fps", 12))

    def import_spritesheet(self, path, cols=0):
        from . import spritesheet
        return spritesheet.import_spritesheet(self.library, path, cols=cols)

    def import_life_folder(self, path):
        from . import folderimport
        return folderimport.import_folder(self.library, path)

    # ---------- partes / rig (mover brazos y piernas) ----------
    def show_rig_editor(self, anim_id):
        from .rigeditor import RigEditor
        RigEditor(self, anim_id).present()

    def generate_puppet_poses(self, anim_id, rig):
        return self.manager.generate_puppet_poses(anim_id, rig)

    # ---------- editores de dibujo ----------
    def show_pixel_editor(self, anim_id=None, guided=False):
        from .editors.pixel_editor import PixelEditor
        PixelEditor(self, anim_id=anim_id, guided=guided).present()

    def show_paint_editor(self, anim_id=None, guided=False):
        from .editors.paint_editor import PaintEditor
        PaintEditor(self, anim_id=anim_id, guided=guided).present()

    def show_paint_editor_project(self, project_path: str):
        """Abre el editor de pintura y carga un proyecto .alproj."""
        from .editors.paint_editor import PaintEditor
        ed = PaintEditor(self, anim_id=None)
        ed.present()
        GLib.idle_add(lambda: ed.canvas.load_project(project_path) and (
            ed._rebuild_strip(), ed.layer_panel.rebuild(),
            ed.canvas_size_lbl.set_text(f"{ed.canvas.cw}×{ed.canvas.ch}"),
            ed.save_status.set_text(
                f"Proyecto cargado: {__import__('pathlib').Path(project_path).name}")
        ) and False)

    # ---------- editor de sprites frame por frame ----------
    def show_frame_editor(self, anim_id, guided=False):
        fd = self.library.frames_dir(anim_id)
        if not (fd / "frame_0000.png").exists():
            return
        from .frameditor import FrameEditor
        FrameEditor(self, anim_id, guided=guided).present()

    def register_pose(self, anim_id, pose, fps=None):
        self.manager.register_pose(anim_id, pose, fps)

    def show_control(self):
        if self.control is None:
            self.control = ControlWindow(self)
            self.control.connect("close-request", self._on_control_closed)
        self.control.present()

    def _on_control_closed(self, _win):
        # cerrar la ventana NO cierra la app: sigue en segundo plano
        self.control = None
        return False

    def quit_all(self):
        self.manager.destroy_all()
        if self._prox_id:
            GLib.source_remove(self._prox_id)
            self._prox_id = None
        if self._hypr:
            self._hypr.stop()
        if self._fs_watch_id:
            GLib.source_remove(self._fs_watch_id)
            self._fs_watch_id = None
        if self._tray_proc:
            try:
                self._tray_proc.force_exit()
            except GLib.Error:
                pass
        if self._started:
            self.release()
        self.quit()


def _ensure_x11_backend_for_non_wlroots_wayland():
    """
    wlr-layer-shell (usado por overlay/normal_animation.py) solo existe en
    compositores wlroots (Hyprland, Sway...). En una sesión Wayland de
    GNOME/KDE no hay layer-shell, así que el overlay usaría el backend X11
    (overlay/x11_animation.py) pero GTK, por defecto, conectaría por Wayland
    puro (sin XWayland) y ese backend perdería los hints EWMH y el
    click-through basado en Gdk.Surface, pensados para una superficie X11.

    Solución: si detectamos Wayland SIN wlr-layer-shell, forzamos
    GDK_BACKEND=x11 y nos relanzamos, para que GTK conecte por XWayland (que
    trae cualquier compositor Wayland de escritorio) y el backend X11
    funcione exactamente igual que en una sesión X11 nativa (Cinnamon, MATE,
    Xfce). En Hyprland/Sway (Wayland CON layer-shell) esta función no hace
    nada: no toca el entorno ni relanza el proceso.
    """
    import os
    import sys

    if os.environ.get("ANIMALINUX_X11_FORCED"):
        return  # ya relanzado, no repetir

    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    is_wayland = session == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))
    if not is_wayland:
        return  # sesión X11 nativa: nada que forzar

    try:
        import gi
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell  # noqa: F401
    except Exception:  # noqa: BLE001
        pass
    else:
        return  # wlr-layer-shell disponible (Hyprland/Sway): no tocar nada

    if not os.environ.get("DISPLAY"):
        return  # no hay XWayland a mano; seguir en Wayland puro (degradado)

    os.environ["GDK_BACKEND"] = "x11"
    os.environ["ANIMALINUX_X11_FORCED"] = "1"
    os.execv(sys.executable, [sys.executable, "-m", "animalinux"] + sys.argv[1:])


def _ensure_layer_shell_preload():
    """
    gtk4-layer-shell DEBE precargarse antes que GTK, o init_for_window() no
    funciona y las mascotas salen como ventanas normales (con marco y fondo).
    Como LD_PRELOAD se lee al arrancar el proceso, nos relanzamos a nosotros
    mismos con la variable puesta. Así el usuario no tiene que tocar nada.
    """
    import glob
    import os
    import sys

    if os.environ.get("ANIMALINUX_PRELOADED"):
        return  # ya estamos relanzados, no repetir

    libs = []
    for base in ("/usr/lib", "/usr/lib64", "/lib", "/usr/lib/x86_64-linux-gnu"):
        libs += glob.glob(os.path.join(base, "libgtk4-layer-shell.so*"))
    if not libs:
        return  # no está instalada; seguimos (saldrá el warning)

    # preferir el symlink .so; si no, cualquiera sirve para LD_PRELOAD
    lib = next((p for p in libs if p.endswith(".so")), sorted(libs)[0])
    preload = os.environ.get("LD_PRELOAD", "")
    if lib not in preload:
        os.environ["LD_PRELOAD"] = (preload + ":" + lib).strip(":")
    os.environ["ANIMALINUX_PRELOADED"] = "1"
    # relanzar el proceso ya con la librería precargada
    os.execv(sys.executable, [sys.executable, "-m", "animalinux"] + sys.argv[1:])


def main():
    import sys
    _ensure_x11_backend_for_non_wlroots_wayland()
    _ensure_layer_shell_preload()
    app = AnimaApp()
    return app.run(sys.argv)
