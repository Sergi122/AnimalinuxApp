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

from .library import Library  # noqa: E402
from .overlay import MascotWindow  # noqa: E402
from .control import ControlWindow  # noqa: E402
from .hypr import HyprMonitor  # noqa: E402
from . import pack as packmod  # noqa: E402

APP_ID = "dev.animalinux.App"


class AnimaApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.library = Library()
        self.mascots = {}          # anim_id -> MascotWindow
        self.control = None
        self._started = False
        self._tray_proc = None
        self._hypr = None
        self._prox_id = None

    # ------------------------------------------------------------------
    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if "--quit" in args:
            self.quit_all()
            return 0
        if not self._started:
            self._start_daemon()
        if "--show" in args or not args:
            # arranque sin args también muestra config la primera vez
            self.show_control()
        if "--daemon" in args:
            pass  # solo servicio, sin ventana
        return 0

    # ------------------------------------------------------------------
    def _start_daemon(self):
        self._started = True
        self.hold()
        from . import theme, i18n
        i18n.init()        # detecta / carga idioma
        theme.apply(None)  # tema oscuro global
        # restaurar mascotas que estaban en el escritorio
        for anim in self.library.active():
            self._spawn_mascot(anim)
        # pausa por pantalla completa
        self._hypr = HyprMonitor(self._on_fullscreen)
        self._hypr.start()
        # bandeja (proceso aparte para no mezclar GTK3 con GTK4)
        self._launch_tray()
        # saludo entre mascotas que se cruzan (modo Vida)
        self._prox_id = GLib.timeout_add(800, self._check_proximity)

    def _check_proximity(self):
        life = [w for w in self.mascots.values() if w.mode == "life"]
        for i in range(len(life)):
            for j in range(i + 1, len(life)):
                if abs(life[i].center_x() - life[j].center_x()) < 90:
                    life[i].trigger_greet()
                    life[j].trigger_greet()
        return True

    def _launch_tray(self):
        try:
            self._tray_proc = Gio.Subprocess.new(
                ["python3", "-m", "animalinux.tray"],
                Gio.SubprocessFlags.NONE,
            )
        except GLib.Error:
            pass  # sin bandeja; se puede abrir con `animalinux --show`

    # ------------------------------------------------------------------
    def _spawn_mascot(self, anim):
        if anim["id"] in self.mascots:
            return
        frames_dir = self.library.frames_dir(anim["id"])
        win = MascotWindow(self, anim, frames_dir, on_moved=self._on_moved)
        self.mascots[anim["id"]] = win
        win.start()

    def _on_moved(self, anim_id, x, y):
        self.library.update(anim_id, x=x, y=y)

    def _on_fullscreen(self, active):
        for win in self.mascots.values():
            win.set_paused(active)
        return False

    # ------------------------------------------------------------------
    # llamadas desde la ventana de configuración
    def set_mascot_visible(self, anim_id, visible):
        if visible:
            anim = self.library.animations.get(anim_id)
            if anim:
                self._spawn_mascot(anim)
        else:
            win = self.mascots.pop(anim_id, None)
            if win:
                win.destroy_window()

    def set_mascot_fps(self, anim_id, fps):
        win = self.mascots.get(anim_id)
        if win:
            win.set_fps(fps)

    def set_mascot_scale(self, anim_id, scale):
        win = self.mascots.get(anim_id)
        if win:
            win.set_scale(scale)

    def set_mascot_mode(self, anim_id, mode):
        # al pasar a "Vida", si solo hay la pose default, generar las poses
        if mode == "life":
            anim = self.library.animations.get(anim_id, {})
            if anim.get("poses", ["default"]) == ["default"]:
                self.generate_life_poses(anim_id)
                win = self.mascots.get(anim_id)
                if win and win.mode != "life":
                    win.set_mode("life")
                return
        win = self.mascots.get(anim_id)
        if win:
            win.set_mode(mode)

    def generate_life_poses(self, anim_id):
        """Para el hilo principal: genera y recarga la mascota."""
        made = self._generate_pose_files(anim_id)
        self.reload_mascot(anim_id)
        return made

    def _generate_pose_files(self, anim_id):
        """Solo disco/datos (seguro en un hilo). NO toca ventanas GTK."""
        from . import procedural, importer
        fd = self.library.frames_dir(anim_id)
        base = fd / "frame_0000.png"
        if not base.exists():
            return []
        made = procedural.generate_poses(str(base), fd)
        for pose in made:
            importer.ensure_flipped(fd / pose)
        self.library.update(anim_id, poses=["default"] + made)
        return made

    def reload_mascot(self, anim_id):
        """Hilo principal: recrea la ventana para que cargue las nuevas poses."""
        if anim_id in self.mascots:
            self.set_mascot_visible(anim_id, False)
            anim = self.library.animations.get(anim_id)
            if anim:
                self._spawn_mascot(anim)

    # ---------- packs (.alpack) ----------
    def import_pack(self, path):
        """Instala un pack. Devuelve el id de la nueva mascota."""
        return packmod.import_pack(self.library, path)

    def export_pack(self, anim_id, path):
        return packmod.export_pack(self.library, anim_id, path)

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
        from . import puppet, importer
        fd = self.library.frames_dir(anim_id)
        base = fd / "frame_0000.png"
        if not base.exists():
            return []
        made = puppet.generate_poses_from_rig(str(base), rig, fd)
        for pose in made:
            importer.ensure_flipped(fd / pose)
        self.library.update(anim_id, poses=["default"] + made, rig=rig)
        self.reload_mascot(anim_id)
        return made

    # ---------- editores de dibujo ----------
    def show_pixel_editor(self, anim_id=None, guided=False):
        from .pixeleditor import PixelEditor
        PixelEditor(self, anim_id=anim_id, guided=guided).present()

    def show_paint_editor(self, anim_id=None, guided=False):
        from .painteditor import PaintEditor
        PaintEditor(self, anim_id=anim_id, guided=guided).present()

    def show_paint_editor_project(self, project_path: str):
        """Abre el editor de pintura y carga un proyecto .alproj."""
        from .painteditor import PaintEditor
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
        anim = self.library.animations.get(anim_id, {})
        poses = anim.get("poses", ["default"])
        if pose not in poses:
            poses = poses + [pose]
        kw = {"poses": poses}
        if fps:
            kw["fps"] = fps
        self.library.update(anim_id, **kw)
        self.reload_mascot(anim_id)

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
        for win in list(self.mascots.values()):
            win.destroy_window()
        self.mascots.clear()
        if self._prox_id:
            GLib.source_remove(self._prox_id)
            self._prox_id = None
        if self._hypr:
            self._hypr.stop()
        if self._tray_proc:
            try:
                self._tray_proc.force_exit()
            except GLib.Error:
                pass
        if self._started:
            self.release()
        self.quit()


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
    _ensure_layer_shell_preload()
    app = AnimaApp()
    return app.run(sys.argv)
