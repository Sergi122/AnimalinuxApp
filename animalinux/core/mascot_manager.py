"""
Gestor de mascotas (CRUD del escritorio).

Extrae de app.py toda la lógica de crear / mostrar / ocultar / reescalar /
recargar mascotas y de generar sus poses. AnimaApp mantiene la API pública
(set_mascot_*, reload_mascot, register_pose…) delegando aquí, así el resto de
módulos no cambia.

El manager NO crea bucles GTK ni bandeja: solo gestiona las ventanas overlay
(MascotWindow) y los datos de la librería.
"""
from gi.repository import GLib

from ..backends import current as backend
from ..overlay import MascotWindow


class MascotManager:
    def __init__(self, app):
        self.app = app
        self.library = app.library
        self.mascots = {}          # anim_id -> MascotWindow
        self.toys = {}             # id -> MascotWindow en modo "toy"
        self._toy_n = 0
        self.hidden = False        # modo no molestar: todo oculto
        self.workspace = None      # escritorio activo ("hypr:3"...)
        self._ws_cbs = []
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
        # las plataformas solo las usa el modo Vida (andar/trepar por
        # bordes de ventana); sin ninguna mascota en ese modo, consultarlas
        # cada tick es gasto puro (wakeups constantes, malo para batería).
        if not self._platforms_busy and (self.toys or any(
                w.mode == "life" for w in self.mascots.values())):
            self._platforms_busy = True
            backend.platforms_async(self._on_platforms)
        return True   # seguir repitiendo

    def _on_platforms(self, plats):
        """Llamado por el backend en el hilo principal."""
        if plats is not None:
            self.platforms = plats
        self._platforms_busy = False
        return False

    # ---------- escritorios ----------
    # Las mascotas CON VIDA te acompañan a todos los escritorios. Las SIN VIDA
    # (GIF quietos) se quedan en el escritorio donde las pusiste: al cambiar
    # de escritorio se esconden y al volver reaparecen en su sitio.
    def start_floor_watch(self):
        """KDE Wayland: si cambia la barra de tareas, mover el suelo."""
        if backend.NAME != "linux":
            return
        from ..backends.linux import kwin
        if kwin.active():
            kwin.bridge().on_area(self._on_area)

    def _on_area(self):
        for win in list(self.mascots.values()) + list(self.toys.values()):
            if hasattr(win, "refresh_floor_gap"):
                win.refresh_floor_gap()

    def start_workspace_watch(self):
        try:
            self.workspace = backend.active_workspace()
        except Exception:  # noqa: BLE001
            self.workspace = None
        try:
            backend.workspace_watch(self._on_workspace)
        except Exception:  # noqa: BLE001
            pass

    def on_workspace_change(self, cb):
        """cb(dirección) — lo usa la compañía para que te «sigan»."""
        self._ws_cbs.append(cb)

    def _on_workspace(self, direction, key):
        first = self.workspace is None
        self.workspace = key
        if first:
            # ya conocemos el escritorio en que arrancaron: las sin vida que
            # aún no tenían uno quedan fijadas a este
            for win in self.mascots.values():
                if not win.anim.get("workspace"):
                    self._pin_here(win)
        for win in self.mascots.values():
            self._apply_workspace(win)
        if direction:
            for cb in self._ws_cbs:
                cb(direction)

    def _pin_here(self, win):
        """Una mascota sin vida queda fijada al escritorio actual."""
        if win.mode == "life" or self.workspace is None:
            return
        if win.anim.get("workspace") != self.workspace:
            win.anim["workspace"] = self.workspace
            self.library.update(win.anim["id"], workspace=self.workspace)

    def _apply_workspace(self, win):
        if self.hidden:
            return
        ws = win.anim.get("workspace")
        show = (win.mode == "life" or ws is None or self.workspace is None
                or ws == self.workspace)
        if show != win.get_visible():
            win.set_paused(not show)
            win.set_visible(show)

    # ---------- ciclo de vida de las ventanas ----------
    def spawn(self, anim):
        if anim["id"] in self.mascots:
            return
        frames_dir = self.library.frames_dir(anim["id"])
        win = MascotWindow(self.app, anim, frames_dir, on_moved=self.on_moved)
        self.mascots[anim["id"]] = win
        win.start()
        if win.mode != "life" and not anim.get("workspace"):
            self._pin_here(win)
        self._apply_workspace(win)
        comp = getattr(self.app, "companion", None)
        if comp is not None:
            win.set_mood(comp.mood_now())
        if self.hidden:
            win.set_paused(True)
            win.set_visible(False)
        # hay un partido: si no juega, no se ve hasta que termine
        from .. import sports
        m = sports.current()
        if m is not None and not m.over and all(p.win is not win for p in m.players):
            win.set_paused(True)
            win.set_visible(False)
            m.benched.append(win)

    # ---------- juguetes ----------
    def spawn_toy(self, kind="ball"):
        from pathlib import Path
        if kind not in ("ball", "yarn"):
            kind = "ball"
        frames = Path(__file__).resolve().parent.parent / "ui" / "assets" / "toys" / kind
        if not (frames / "frame_0000.png").exists():
            return None
        self._toy_n += 1
        tid = f"toy-{kind}-{self._toy_n}"
        # aparece arriba, cerca de una mascota (o en el centro)
        x = 400
        if self.mascots:
            w = next(iter(self.mascots.values()))
            x = int(w.center_x())
        anim = {"id": tid, "name": kind, "toy": kind, "mode": "toy",
                "width": 48, "height": 48, "scale": 1.0, "fps": 1,
                "x": x, "y": 60}
        win = MascotWindow(self.app, anim, frames, on_moved=None)
        self.toys[tid] = win
        win.start()
        if self.hidden:
            win.set_paused(True)
            win.set_visible(False)
        return win

    def remove_toy(self, tid):
        win = self.toys.pop(tid, None)
        if win is not None:
            win.destroy_window()
        return False

    def set_hidden_all(self, hidden):
        """No molestar: esconde (y duerme del todo) mascotas y juguetes."""
        self.hidden = hidden
        for win in list(self.mascots.values()) + list(self.toys.values()):
            win.set_paused(hidden)
            win.set_visible(not hidden)
        if not hidden:
            for win in self.mascots.values():
                self._apply_workspace(win)

    def on_moved(self, anim_id, x, y):
        self.library.update(anim_id, x=x, y=y)
        win = self.mascots.get(anim_id)
        if win is not None:
            self._pin_here(win)       # la arrastraste aquí: ahora vive aquí

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
            self._pin_here(win)
            self._apply_workspace(win)

    def reload(self, anim_id):
        """Recrea la ventana para que cargue las nuevas poses."""
        if anim_id in self.mascots:
            self.set_visible(anim_id, False)
            anim = self.library.animations.get(anim_id)
            if anim:
                self.spawn(anim)

    def pause_all(self, active):
        if self.hidden:
            return
        for win in list(self.mascots.values()) + list(self.toys.values()):
            if win.get_visible():          # las de otro escritorio siguen dormidas
                win.set_paused(active)

    def check_proximity(self):
        """Saludo entre mascotas que se cruzan (modo Vida). Idea 7: se miran,
        se saludan y luego se ALEJAN (meet) para no quedarse pegadas/trabadas."""
        life = [w for w in self.mascots.values() if w.mode == "life"]
        if len(life) < 2:
            return True
        for i in range(len(life)):
            for j in range(i + 1, len(life)):
                a, b = life[i], life[j]
                if abs(a.center_x() - b.center_x()) < 90:
                    a.meet(b.center_x())
                    b.meet(a.center_x())
        return True

    def destroy_all(self):
        for win in list(self.mascots.values()) + list(self.toys.values()):
            win.destroy_window()
        self.mascots.clear()
        self.toys.clear()

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
