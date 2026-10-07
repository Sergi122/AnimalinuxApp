"""
Cerebro de AnimaLinux. Un único proceso GtkApplication que:
  - mantiene las mascotas (ventanas overlay) en el escritorio
  - abre la ventana de configuración cuando se lo piden
  - lanza el icono de bandeja (proceso aparte, ver backends)
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
from .backends import current as backend  # noqa: E402
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
        self._fs_watch = None
        self._prox_id = None

    # ------------------------------------------------------------------
    def do_command_line(self, command_line):
        self.handle_args(command_line.get_arguments()[1:])
        return 0

    def handle_args(self, args):
        """Ejecuta una orden (--show/--quit/--daemon). Llega por D-Bus en
        Linux (do_command_line) o por el reenvío de instancia única en Windows."""
        if "--quit" in args:
            self.quit_all()
            return
        if not self._started:
            self._start_daemon()
        if "--show" in args:
            self.show_control()
        elif not args:
            # Steam-like: solo bandeja; abre control solo si es la primera vez
            if not self.library.animations:
                self.show_control()

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
        # Pausa por pantalla completa: la política (opt-in o por defecto) la
        # decide cada backend porque el efecto visual es distinto en cada uno.
        self._fs_watch = backend.fullscreen_watch(
            self._on_fullscreen,
            self.library.config.get("pause_on_fullscreen", None))
        # bandeja
        backend.start_tray(self)
        # saludo entre mascotas que se cruzan (modo Vida)
        self._prox_id = GLib.timeout_add(800, self.manager.check_proximity)
        # vigilar bordes de ventanas para que la mascota se suba/camine por ellos
        self.manager.start_platform_watch()
        # buscar versiones nuevas cada vez que se abre la app
        GLib.timeout_add_seconds(3, lambda: self._check_updates() and False)

    def _check_updates(self):
        import threading
        from .core import updater
        if not updater.should_check():
            return False

        def work():
            new = updater.check_and_store()
            if new:
                GLib.idle_add(self._notify_update, new)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _notify_update(self, version):
        from .i18n import t
        n = Gio.Notification.new(t("upd_notify_title"))
        n.set_body(t("upd_available", v=version))
        self.send_notification("update", n)
        if self.control:
            self.control.refresh_update_banner()
        return False

    # ------------------------------------------------------------------
    def _on_fullscreen(self, active):
        self.manager.pause_all(active)
        return False

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

    # ---------- editores de dibujo ----------
    def show_pixel_editor(self, anim_id=None, guided=False):
        from .editors.pixel_editor import PixelEditor
        PixelEditor(self, anim_id=anim_id, guided=guided).present()

    def show_paint_editor(self, anim_id=None, guided=False):
        from .editors.paint_editor import PaintEditor
        PaintEditor(self, anim_id=anim_id, guided=guided).present()

    def show_paint_editor_project(self, project_path: str):
        """Abre el editor de animación y carga un proyecto .alproj."""
        from .editors.paint_editor import PaintEditor
        PaintEditor(self, anim_id=None, project=project_path).present()

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
        self._check_updates()   # también al abrir la ventana

    def _on_control_closed(self, _win):
        # cerrar la ventana NO cierra la app: sigue en segundo plano
        self.control = None
        return False

    def quit_all(self):
        self.manager.destroy_all()
        if self._prox_id:
            GLib.source_remove(self._prox_id)
            self._prox_id = None
        if self._fs_watch:
            self._fs_watch.stop()
            self._fs_watch = None
        backend.stop_tray()
        if self._started:
            self.release()
        self.quit()


def main():
    import sys
    backend.prepare_process()
    if backend.forward_to_running(sys.argv[1:]):
        return 0   # ya hay una instancia: se le pasó la orden
    app = AnimaApp()
    return app.run(sys.argv)
