"""
La capa visible: una ventana wlr-layer-shell por mascota.

MODOS:
  - "gif"  : reproduce la animación tal cual, quieta.
  - "life" : la mascota vive -> camina, idle, SALTA, rebota en los bordes,
             saluda cuando el cursor se le pone encima o se cruza con otra
             mascota, y mira hacia donde avanza.

POSES (si el pack las trae): default (obligatoria), walk, idle, greet, jump.
Con un solo gif, 'default' se usa para todo. Si hay poses extra, se reproducen
según lo que la mascota esté haciendo. La app NO inventa fotogramas: reproduce
los que existen y controla el comportamiento (igual que Shimeji / AnimaEngine).

Nota Wayland: se puede detectar el cursor SOBRE la mascota (entra/sale de su
superficie), pero no seguir el cursor por toda la pantalla (Wayland no deja leer
la posición global del puntero).
"""
import random
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

_CSS_APPLIED = False
BEHAVIOR_INTERVAL = 60      # ms entre pasos (modo Vida)
GRAVITY = 2                 # px/tick^2 para el salto
GREET_TICKS = 25           # cuánto dura el saludo
GRAB_SIZE = 350             # px del cuadrado invisible que retiene el cursor en grab


def _apply_transparency(display):
    global _CSS_APPLIED
    if _CSS_APPLIED:
        return
    provider = Gtk.CssProvider()
    css = (
        "window.animalinux-mascot {"
        "  background: transparent;"
        "  background-color: transparent;"
        "  background-image: none;"
        "  box-shadow: none;"
        "}"
        "window.animalinux-mascot * {"
        "  background: transparent;"
        "  background-color: transparent;"
        "  background-image: none;"
        "}"
    )
    if hasattr(provider, "load_from_string"):
        provider.load_from_string(css)
    else:
        provider.load_from_data(css.encode())
    # PRIORITY_USER + 1 garantiza que gana sobre cualquier tema
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
    )
    _CSS_APPLIED = True


class MascotWindow(Gtk.Window):
    def __init__(self, app, anim, frames_dir, on_moved):
        super().__init__(application=app)
        self.anim = anim
        self.on_moved = on_moved
        self._frames_dir = str(frames_dir)
        self.mode = anim.get("mode", "gif")

        # poses: nombre -> {"normal":[tex], "flip":[tex]}
        self._poses = {}
        self._pose = "default"
        self._facing_left = False
        self._index = 0
        self._anim_id = None
        self._behavior_id = None
        self._paused = False
        self._dragging = False

        # estado de comportamiento
        self._state = "idle"
        self._state_ttl = 0
        self._dir = 1
        self._speed = 0
        self._floor_y = 0      # borde inferior fijo (nunca cambia salvo al reescalar)
        self._jump_vy = 0
        self._greet_ttl = 0
        self._screen_w, self._screen_h = 1920, 1080

        # física del tiro (parabólica)
        self._toss_vx = 0.0
        self._toss_vy = 0.0    # velocidad vertical durante el tiro

        self.add_css_class("animalinux-mascot")
        self.set_decorated(False)
        self.set_resizable(False)

        LayerShell.init_for_window(self)
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_namespace(self, "animalinux-mascot")
        LayerShell.set_anchor(self, LayerShell.Edge.LEFT, True)
        LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)
        self._set_position(anim.get("x", 100), anim.get("y", 100))

        self._load_poses()
        scale = anim.get("scale", 1.0)
        w = int(anim.get("width", 100) * scale)
        h = int(anim.get("height", 100) * scale)

        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(False)
        self.picture.set_content_fit(Gtk.ContentFit.FILL)
        self.picture.set_size_request(w, h)
        first = self._frames_for("default")
        if first:
            self.picture.set_paintable(first[0])
        # Fixed como contenedor: permite mover la picture dentro del área grab
        self.fixed = Gtk.Fixed()
        self.fixed.put(self.picture, 0, 0)
        self.set_child(self.fixed)
        self.set_default_size(w, h)
        self._cat_w = w
        self._cat_h = h
        self._grab_size = 0   # 0 = sin modo grab; >0 = ventana expandida

        _apply_transparency(self.get_display() or Gdk.Display.get_default())

        # arrastrar
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.picture.add_controller(drag)

        # cursor encima -> saludar (en la picture, solo pixels opacos)
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_cursor_enter)
        self.picture.add_controller(motion)

        # tocarla (click) -> reaccionar / enojarse
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.picture.add_controller(click)

        # estado de interacción
        self._anger = 0          # sube al tocarla repetido
        self._react_ttl = 0      # ticks de reacción (jitter)
        self._jitter_base = 0    # x base mientras tiembla
        self._last_drag = None   # (t, ox, oy) para medir velocidad de arrastre
        self._grab_ttl  = 0      # ticks en estado "agarra el ratón"
        self._rest_ttl  = 0      # ticks de reposo tras aterrizar

        # motion en la VENTANA completa para modo grab (cubre toda la zona expandida)
        self._motion = Gtk.EventControllerMotion()
        self._motion.connect("motion", self._on_motion_grab)
        self._motion.connect("enter", lambda c, x, y: self._on_motion_grab(c, x, y))
        self.add_controller(self._motion)

    # ---------- posición ----------
    def _set_position(self, x, y):
        self._x = max(0, int(x))
        self._y = max(0, int(y))
        LayerShell.set_margin(self, LayerShell.Edge.LEFT, self._x)
        LayerShell.set_margin(self, LayerShell.Edge.TOP, self._y)

    def _on_drag_begin(self, gesture, sx, sy):
        self._dragging = True
        self._drag_origin = (self._x, self._y)
        self._toss_vx = 0.0
        self._toss_vy = 0.0
        self._last_drag = (GLib.get_monotonic_time(), 0.0, 0.0)

    def _on_drag_update(self, gesture, ox, oy):
        x0, y0 = self._drag_origin
        self._set_position(x0 + ox, y0 + oy)
        now = GLib.get_monotonic_time()
        if self._last_drag:
            t0, ox0, oy0 = self._last_drag
            dt = (now - t0) / 1_000_000.0
            if dt > 0.01:
                self._drag_vx = (ox - ox0) / dt
                self._drag_vy = (oy - oy0) / dt
                self._last_drag = (now, ox, oy)

    def _on_drag_end(self, gesture, ox, oy):
        self._dragging = False
        vx = getattr(self, "_drag_vx", 0.0)
        vy = getattr(self, "_drag_vy", 0.0)
        if self.mode == "life" and self._state != "grab":
            spd = (vx**2 + vy**2) ** 0.5
            if spd > 700:
                # tiro fuerte → trayectoria parabólica
                self._toss_vx = max(-40, min(40, vx / 60.0))
                self._toss_vy = max(-30, min(10,  vy / 60.0))
                self._state = "toss"
                self._pose = "jump" if self._has_pose("jump") else "default"
            else:
                # soltar suave → cae al suelo con gravedad, X no cambia
                self._toss_vx = 0.0
                self._toss_vy = 0.0
                self._state = "falling"
                self._pose = "jump" if self._has_pose("jump") else "default"
        if self.on_moved:
            self.on_moved(self.anim["id"], self._x, self._y)
        self._drag_vx = 0.0
        self._drag_vy = 0.0

    def _on_cursor_enter(self, controller, x, y):
        if self.mode == "life" and self._state != "grab":
            self.trigger_greet()

    def _on_motion_grab(self, ctrl, mx, my):
        """En modo grab: cursor relativo a la ventana → seguir cursor."""
        if self._state != "grab" or self._dragging:
            return
        self._grab_cx = mx
        self._grab_cy = my
        self._grab_follow(mx, my)

    def _grab_follow(self, mx, my):
        """Mueve el sprite para que el cursor quede en su centro."""
        if self._grab_size <= 0:
            return
        w, h = self._cat_w, self._cat_h
        # mx/my son coordenadas dentro de la ventana (0..w, 0..h)
        # Queremos que el sprite se mueva para centrar el cursor en él
        nx = self._x + int(mx - w / 2)
        ny = self._y + int(my - h / 2)
        nx = max(0, min(self._screen_w - w, nx))
        ny = max(0, min(self._screen_h - h, ny))
        self._set_position(nx, ny)

    def _on_click(self, gesture, n_press, x, y):
        if self.mode == "life":
            self._react_to_touch()

    def _react_to_touch(self):
        """Tocarla la sobresalta; si insistes (4 clicks), agarra el ratón."""
        if self._grab_ttl > 0:
            return   # ya está en modo agarre
        self._anger = min(4, self._anger + 1)
        self._react_ttl = 14
        self._jitter_base = self._x
        if self._has_pose("angry"):
            self._pose = "angry"
        elif self._has_pose("greet"):
            self._pose = "greet"

        if self._anger >= 4:
            # ¡Harta! → agarra el ratón
            self._start_grab()
        elif self._anger >= 2:
            # enojada: se voltea y sale corriendo
            self._facing_left = not self._facing_left
            self._state = "walk"
            self._dir = 1 if not self._facing_left else -1
            self._speed = 5
            self._state_ttl = 50
        GLib.timeout_add_seconds(3, self._cool_down)

    def _start_grab(self):
        """La mascota 'agarra' el cursor: expande la ventana y sigue el ratón."""
        self._grab_ttl = 80   # ~5 s a 60 ms/tick
        self._state = "grab"
        self._toss_vx = 0.0
        self._toss_vy = 0.0
        if self._has_pose("grab"):
            self._pose = "grab"
        elif self._has_pose("angry"):
            self._pose = "angry"
        # Ventana permanece del mismo tamaño — solo abrimos la región de input
        # al área completa del sprite (no se intenta redimensionar la ventana
        # porque set_default_size no funciona fiable en LayerShell ya mapeado)
        self._grab_size = 1   # >0 activa _grab_follow
        GLib.idle_add(self._set_input_region_full)

    def _set_input_region_full(self):
        """Abre la región de eventos al área completa del sprite (modo grab)."""
        try:
            import cairo
            surf = self.get_surface()
            if surf:
                w, h = self._cat_w, self._cat_h
                region = cairo.Region(cairo.RectangleInt(0, 0, w, h))
                surf.set_input_region(region)
        except Exception:
            pass
        return False

    def _end_grab_restore(self):
        """Restaura la región de input tras salir de grab."""
        self._grab_size = 0
        GLib.idle_add(self._apply_input_region)
        return False

    def _cool_down(self):
        self._anger = max(0, self._anger - 1)
        return False

    # ---------- poses / texturas ----------
    def _load_poses(self):
        base = Path(self._frames_dir)
        # 'default' = capa plana
        self._load_one_pose("default", base)
        # poses extra = subcarpetas
        for sub in sorted(p for p in base.iterdir() if p.is_dir()):
            self._load_one_pose(sub.name, sub)
        if "default" not in self._poses and self._poses:
            # si no hubo capa plana, usar la primera pose como default
            self._poses["default"] = next(iter(self._poses.values()))

    def _load_one_pose(self, name, folder):
        folder = Path(folder)
        if not list(folder.glob("flip_*.png")):
            try:
                from . import importer
                importer.ensure_flipped(folder)
            except Exception:  # noqa: BLE001
                pass
        normal, flip = [], []
        for p in sorted(folder.glob("frame_*.png")):
            try:
                normal.append(Gdk.Texture.new_from_filename(str(p)))
            except GLib.Error:
                pass
        for p in sorted(folder.glob("flip_*.png")):
            try:
                flip.append(Gdk.Texture.new_from_filename(str(p)))
            except GLib.Error:
                pass
        if not flip:
            flip = normal
        if normal:
            self._poses[name] = {"normal": normal, "flip": flip}

    def _frames_for(self, pose):
        data = self._poses.get(pose) or self._poses.get("default")
        if not data:
            return []
        return data["flip"] if self._facing_left else data["normal"]

    def _has_pose(self, pose):
        return pose in self._poses

    # ---------- arranque ----------
    def start(self):
        self.present()
        self._update_screen_size()
        if self.mode == "life":
            self._enter_life()
        self._schedule_anim()
        GLib.idle_add(self._apply_input_region)

    def _update_screen_size(self):
        try:
            display = self.get_display() or Gdk.Display.get_default()
            mon = None
            surf = self.get_surface()
            if surf is not None and hasattr(display, "get_monitor_at_surface"):
                mon = display.get_monitor_at_surface(surf)
            mons = display.get_monitors()
            if mon is None and mons.get_n_items() > 0:
                mon = mons.get_item(0)
            if mon is not None:
                geo = mon.get_geometry()
                self._screen_w, self._screen_h = geo.width, geo.height
        except Exception:  # noqa: BLE001
            pass

    # ---------- animación de frames ----------
    def _schedule_anim(self):
        if self._anim_id:
            GLib.source_remove(self._anim_id)
            self._anim_id = None
        fps = max(1, int(self.anim.get("fps", 12)))
        interval = int(1000 / fps)
        self._anim_id = GLib.timeout_add(interval, self._anim_tick)

    def _anim_tick(self):
        frames = self._frames_for(self._pose)
        if self._paused or len(frames) == 0:
            return True
        self._index = (self._index + 1) % len(frames)
        self.picture.set_paintable(frames[self._index])
        return True

    # ---------- modo Vida ----------
    def _enter_life(self):
        scale = self.anim.get("scale", 1.0)
        h = int(self.anim.get("height", 100) * scale)
        self._floor_y = max(0, self._screen_h - h)
        self._set_position(self._x, self._floor_y)
        self._pick_behavior()
        if self._behavior_id is None:
            self._behavior_id = GLib.timeout_add(
                BEHAVIOR_INTERVAL, self._behavior_tick)

    def _exit_life(self):
        if self._behavior_id:
            GLib.source_remove(self._behavior_id)
            self._behavior_id = None
        self._facing_left = False
        self._pose = "default"
        self._index = 0

    def _pick_behavior(self):
        r = random.random()
        if r < 0.45:
            self._state = "idle"
            self._state_ttl = random.randint(20, 60)
            self._speed = 0
            self._pose = "idle" if self._has_pose("idle") else "default"
        elif r < 0.85:
            self._state = "walk"
            self._state_ttl = random.randint(25, 70)
            self._dir = random.choice([-1, 1])
            self._speed = random.randint(1, 3)
            self._facing_left = self._dir < 0
            self._pose = "walk" if self._has_pose("walk") else "default"
        else:
            self._start_jump()

    def _start_jump(self):
        self._state = "jump"
        self._jump_vy = -random.randint(14, 22)   # impulso hacia arriba
        self._pose = "jump" if self._has_pose("jump") else "default"

    def trigger_greet(self):
        """Saludar: usa la pose 'greet' si existe; si no, da un saltito."""
        if self._greet_ttl > 0:
            return
        if self._has_pose("greet"):
            self._greet_ttl = GREET_TICKS
            self._pose = "greet"
        elif self._state != "jump":
            self._start_jump()

    def _behavior_tick(self):
        if self._paused or self._dragging:
            return True

        # ── modo agarre del ratón (sigue cursor, tiembla) ─────────────────
        if self._state == "grab":
            self._grab_ttl -= 1
            if self._grab_ttl <= 0:
                # suelta: restaura ventana y sale disparada
                self._grab_ttl = 0
                self._anger = 0
                GLib.idle_add(self._end_grab_restore)
                vx = random.choice([-1, 1]) * random.randint(20, 38)
                self._toss_vx = vx
                self._toss_vy = random.randint(-20, -10)
                self._facing_left = vx < 0
                self._state = "toss"
                self._pose = "jump" if self._has_pose("jump") else "default"
            return True

        # ── caída libre (soltar suave en el aire) ──────────────────────────
        if self._state == "falling":
            if self._y < self._floor_y:
                self._toss_vy += GRAVITY
                ny = min(self._floor_y, self._y + int(self._toss_vy))
                self._set_position(self._x, ny)
            if self._y >= self._floor_y:
                self._toss_vy = 0.0
                self._rest_ttl = random.randint(25, 50)
                self._state = "rest"
            return True

        # ── tiro parabólico ────────────────────────────────────────────────
        if self._state == "toss":
            scale = self.anim.get("scale", 1.0)
            w = int(self.anim.get("width", 100) * scale)
            # mover X con fricción
            nx = self._x + self._toss_vx
            if nx <= 0:
                nx = 0;                 self._toss_vx = -self._toss_vx * 0.55
            elif nx >= self._screen_w - w:
                nx = self._screen_w - w; self._toss_vx = -self._toss_vx * 0.55
            self._facing_left = self._toss_vx < 0
            self._toss_vx *= 0.88
            # mover Y con gravedad
            self._toss_vy += GRAVITY
            ny = self._y + int(self._toss_vy)
            # aterrizó en el suelo → descansa donde cayó
            if ny >= self._floor_y:
                ny = self._floor_y
                self._toss_vx = 0.0
                self._toss_vy = 0.0
                self._rest_ttl = random.randint(30, 60)
                self._state = "rest"
                self._pose = "idle" if self._has_pose("idle") else "default"
            self._set_position(int(nx), int(ny))
            return True

        # ── reposo tras aterrizar ──────────────────────────────────────────
        if self._state == "rest":
            if self._rest_ttl > 0:
                self._rest_ttl -= 1
                self._pose = "idle" if self._has_pose("idle") else "default"
            else:
                self._pick_behavior()
            return True

        # ── reacción al tocarla: tiembla unos ticks ────────────────────────
        if self._react_ttl > 0:
            self._react_ttl -= 1
            jx = self._jitter_base + random.randint(-3, 3)
            self._set_position(jx, self._y)
            if self._react_ttl == 0:
                self._set_position(self._jitter_base, self._y)
                if self._pose in ("angry", "greet"):
                    self._pick_behavior()
            return True

        if self._greet_ttl > 0:
            self._greet_ttl -= 1
            if self._greet_ttl == 0:
                self._pick_behavior()
            return True

        if self._state == "jump":
            self._y += self._jump_vy
            self._jump_vy += GRAVITY
            if self._y >= self._floor_y:        # aterrizó
                self._y = self._floor_y
                self._pick_behavior()
            self._set_position(self._x, self._y)
            return True

        self._state_ttl -= 1
        if self._state_ttl <= 0:
            self._pick_behavior()
        if self._state == "walk":
            scale = self.anim.get("scale", 1.0)
            w = int(self.anim.get("width", 100) * scale)
            nx = self._x + self._dir * self._speed
            if nx <= 0:
                nx, self._dir, self._facing_left = 0, 1, False
            elif nx >= self._screen_w - w:
                nx, self._dir, self._facing_left = self._screen_w - w, -1, True
            self._set_position(nx, self._floor_y)
        return True

    # ---------- ajustes en vivo ----------
    def set_fps(self, fps):
        self.anim["fps"] = fps
        self._schedule_anim()

    def set_scale(self, scale):
        self.anim["scale"] = scale
        w = int(self.anim.get("width", 100) * scale)
        h = int(self.anim.get("height", 100) * scale)
        self._cat_w = w
        self._cat_h = h
        self.picture.set_size_request(w, h)
        self.set_default_size(w, h)
        if self.mode == "life":
            self._floor_y = max(0, self._screen_h - h)
            self._set_position(self._x, self._floor_y)
        GLib.idle_add(self._apply_input_region)

    def set_mode(self, mode):
        self.mode = mode
        self.anim["mode"] = mode
        if mode == "life":
            self._update_screen_size()
            self._enter_life()
        else:
            self._exit_life()

    def set_paused(self, paused):
        self._paused = paused

    def center_x(self):
        scale = self.anim.get("scale", 1.0)
        return self._x + int(self.anim.get("width", 100) * scale) / 2

    # ---------- arrastre por píxeles visibles ----------
    def _apply_input_region(self):
        try:
            import cairo
            from PIL import Image
            surf = self.get_surface()
            if surf is None:
                return False
            base = sorted(Path(self._frames_dir).glob("frame_*.png"))
            if not base:
                return False
            im = Image.open(base[0]).convert("RGBA")
            bw, bh = im.size
            scale = self.anim.get("scale", 1.0)
            w = max(1, int(bw * scale))
            h = max(1, int(bh * scale))
            alpha = im.getchannel("A")
            region = cairo.Region()
            block = 6
            sx, sy = bw / w, bh / h
            y = 0
            while y < h:
                x = 0
                while x < w:
                    bx = min(bw - 1, int(x * sx))
                    by = min(bh - 1, int(y * sy))
                    if alpha.getpixel((bx, by)) > 30:
                        region.union(cairo.RectangleInt(x, y, block, block))
                    x += block
                y += block
            surf.set_input_region(region)
        except Exception:  # noqa: BLE001
            pass
        return False

    def destroy_window(self):
        if self._anim_id:
            GLib.source_remove(self._anim_id)
        if self._behavior_id:
            GLib.source_remove(self._behavior_id)
        self.destroy()
