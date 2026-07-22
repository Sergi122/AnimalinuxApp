"""
Gestor de mascotas (CRUD del escritorio).

Extrae de app.py toda la lógica de crear / mostrar / ocultar / reescalar /
recargar mascotas y de generar sus poses. AnimaApp mantiene la API pública
(set_mascot_*, reload_mascot, register_pose…) delegando aquí, así el resto de
módulos no cambia.

El manager NO crea bucles GTK ni bandeja: solo gestiona las ventanas overlay
(MascotWindow) y los datos de la librería.
"""
import json
import subprocess
import threading

from gi.repository import GLib

from ..overlay import MascotWindow


class MascotManager:
    def __init__(self, app):
        self.app = app
        self.library = app.library
        self.mascots = {}          # anim_id -> MascotWindow
        # Idea 5: plataformas = bordes superiores de las ventanas abiertas
        # (coords GLOBALES de Hyprland). Las mascotas se suben/caminan por ellas.
        # Se refresca en segundo plano para no bloquear el bucle GTK.
        self.platforms = []
        self._platforms_busy = False

    # ---------- plataformas (andar por ventanas) ----------
    def start_platform_watch(self, interval_ms=1500):
        GLib.timeout_add(interval_ms, self._refresh_platforms)
        self._refresh_platforms()

    def _refresh_platforms(self):
        if not self._platforms_busy:
            self._platforms_busy = True
            threading.Thread(target=self._fetch_platforms_bg, daemon=True).start()
        return True   # seguir repitiendo

    def _fetch_platforms_bg(self):
        """Hilo de fondo: SOLO hyprctl (subproceso aparte, no toca GDK/X11 —
        seguro fuera del hilo principal). El fallback a Wnck usa GDK/libwnck,
        que NO es thread-safe: llamarlo aquí (como se hacía antes) corrompía
        de forma intermitente el repintado en X11 (Xfce/Cinnamon) — carrera
        con el hilo de GTK que estaba dibujando la mascota a la vez, viéndose
        como un parpadeo/desaparición que se autocorregía sola en el
        siguiente frame. Por eso el fallback se reenvía al hilo principal."""
        plats = self._fetch_platforms_hyprctl()
        if plats is not None:
            self.platforms = plats
            self._platforms_busy = False
        else:
            GLib.idle_add(self._fetch_platforms_wnck_main)

    def _fetch_platforms_wnck_main(self):
        """Fallback Wnck: se ejecuta en el hilo principal (GLib.idle_add)."""
        plats = self._fetch_platforms_wnck()
        self.platforms = plats if plats is not None else self.platforms
        self._platforms_busy = False
        return False   # no repetir (es un idle_add de una sola vez)

    def _fetch_platforms_hyprctl(self):
        try:
            out = subprocess.run(
                ["hyprctl", "-j", "clients"],
                capture_output=True, text=True, timeout=2).stdout
            plats = []
            for c in json.loads(out):
                if c.get("hidden") or not c.get("mapped", True):
                    continue
                if c.get("workspace", {}).get("id", 1) < 0:
                    continue   # special/scratchpad
                at = c.get("at") or [0, 0]
                size = c.get("size") or [0, 0]
                if size[0] < 80 or size[1] < 40:
                    continue
                # borde SUPERIOR de la ventana = plataforma
                plats.append((at[0], at[0] + size[0], at[1]))
            return plats
        except Exception:  # noqa: BLE001
            return None

    def _fetch_platforms_wnck(self):
        """Lista de ventanas vía libwnck (EWMH), para X11 sin hyprctl. Cubre
        GNOME/Cinnamon/MATE/Xfce con una sola implementación. Las mascotas
        mismas quedan excluidas solas: llevan _NET_WM_STATE_SKIP_TASKBAR
        (ver overlay/_x11_hints.py) y is_skip_tasklist() lo detecta."""
        try:
            import gi
            gi.require_version("Wnck", "3.0")
            from gi.repository import Wnck
        except Exception:  # noqa: BLE001
            return None
        try:
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

    # ---------- ciclo de vida de las ventanas ----------
    def spawn(self, anim):
        if anim["id"] in self.mascots:
            return
        frames_dir = self.library.frames_dir(anim["id"])
        win = MascotWindow(self.app, anim, frames_dir, on_moved=self.on_moved)
        self.mascots[anim["id"]] = win
        win.start()

    def on_moved(self, anim_id, x, y):
        self.library.update(anim_id, x=x, y=y)

    def set_visible(self, anim_id, visible):
        if visible:
            anim = self.library.animations.get(anim_id)
            if anim:
                self.spawn(anim)
        else:
            win = self.mascots.pop(anim_id, None)
            if win:
                win.destroy_window()

    def set_fps(self, anim_id, fps):
        win = self.mascots.get(anim_id)
        if win:
            win.set_fps(fps)

    def set_scale(self, anim_id, scale):
        win = self.mascots.get(anim_id)
        if win:
            win.set_scale(scale)

    def set_mode(self, anim_id, mode):
        win = self.mascots.get(anim_id)
        if win:
            win.set_mode(mode)

    def reload(self, anim_id):
        """Recrea la ventana para que cargue las nuevas poses."""
        if anim_id in self.mascots:
            self.set_visible(anim_id, False)
            anim = self.library.animations.get(anim_id)
            if anim:
                self.spawn(anim)

    def pause_all(self, active):
        for win in self.mascots.values():
            win.set_paused(active)

    def check_proximity(self):
        """Saludo entre mascotas que se cruzan (modo Vida). Idea 7: se miran,
        se saludan y luego se ALEJAN (meet) para no quedarse pegadas/trabadas."""
        life = [w for w in self.mascots.values() if w.mode == "life"]
        for i in range(len(life)):
            for j in range(i + 1, len(life)):
                a, b = life[i], life[j]
                if abs(a.center_x() - b.center_x()) < 90:
                    a.meet(b.center_x())
                    b.meet(a.center_x())
        return True

    def destroy_all(self):
        for win in list(self.mascots.values()):
            win.destroy_window()
        self.mascots.clear()

    # ---------- generación de poses ----------
    def generate_puppet_poses(self, anim_id, rig):
        from .. import puppet
        from . import image_processor
        fd = self.library.frames_dir(anim_id)
        base = fd / "frame_0000.png"
        if not base.exists():
            return []
        made = puppet.generate_poses_from_rig(str(base), rig, fd)
        for pose in made:
            image_processor.ensure_flipped(fd / pose)
        self.library.update(anim_id, poses=["default"] + made, rig=rig)
        self.reload(anim_id)
        return made

    def register_pose(self, anim_id, pose, fps=None):
        anim = self.library.animations.get(anim_id, {})
        poses = anim.get("poses", ["default"])
        if pose not in poses:
            poses = poses + [pose]
        kw = {"poses": poses}
        if fps:
            kw["fps"] = fps
        self.library.update(anim_id, **kw)
        self.reload(anim_id)
