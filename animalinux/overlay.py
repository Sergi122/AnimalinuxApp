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
GREET_COOLDOWN = 80        # ticks (~5 s) entre saludos por proximidad


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
        # barra de control sobre el sprite (gana en especificidad a la regla *)
        "window.animalinux-mascot .animalinux-ctrlbar {"
        "  background-color: rgba(26,26,46,0.85);"
        "  border-radius: 8px;"
        "  padding: 2px;"
        "  margin: 2px;"
        "}"
        "window.animalinux-mascot .animalinux-ctrlbtn {"
        "  background-color: rgba(123,97,255,0.85);"
        "  color: #ffffff;"
        "  border-radius: 6px;"
        "  min-width: 20px;"
        "  min-height: 20px;"
        "  padding: 2px;"
        "}"
        "window.animalinux-mascot .animalinux-ctrlbtn:hover {"
        "  background-color: rgba(123,97,255,1.0);"
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
        self._app = app
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
        self._grabbing = False   # True mientras sigue el cursor (modo grab)

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
        # La ventana está SIEMPRE a pantalla completa (anclada a los 4 bordes →
        # superficie real fullscreen). El sprite se mueve DENTRO por márgenes de
        # la Picture, así la superficie nunca se redimensiona (sin parpadeos ni
        # "líneas") y en grab basta ampliar la región de input para seguir el
        # cursor por todo el escritorio. La región de input (lo clicable) se
        # limita a la caja del sprite para no bloquear el resto del escritorio.
        for edge in (LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT,
                     LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM):
            LayerShell.set_anchor(self, edge, True)
            LayerShell.set_margin(self, edge, 0)
        # zona exclusiva -1 → la superficie cubre TODO el monitor (ignora las
        # áreas reservadas por barras), imprescindible para que sea fullscreen
        LayerShell.set_exclusive_zone(self, -1)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)

        self._load_poses()
        scale = anim.get("scale", 1.0)
        w = int(anim.get("width", 100) * scale)
        h = int(anim.get("height", 100) * scale)
        self._cat_w = w
        self._cat_h = h

        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.picture.set_content_fit(Gtk.ContentFit.FILL)
        self.picture.set_size_request(w, h)
        first = self._frames_for("default")
        if first:
            self.picture.set_paintable(first[0])

        # ── barra de control (Administrar / Cerrar) sobre el sprite ──────────
        # Va dentro de un Gtk.Overlay POR ENCIMA del picture: así los botones
        # tienen su propio manejo de eventos y el gesto de arrastre del sprite
        # NO se los traga (antes los clics se perdían al mover la mascota).
        # Se revelan al pasar el cursor por encima de la mascota.
        self._overlay = Gtk.Overlay()
        self._overlay.set_halign(Gtk.Align.START)
        self._overlay.set_valign(Gtk.Align.START)
        self._overlay.set_child(self.picture)
        self._overlay.add_overlay(self._build_ctrl_bar())

        # el overlay (sprite + barra) se mueve dentro de la ventana fullscreen
        # vía sus márgenes (la ventana nunca se mueve ni se redimensiona)
        self.set_child(self._overlay)

        # posición inicial del sprite (márgenes de la picture)
        self._set_position(anim.get("x", 100), anim.get("y", 100))
        # refrescar la región de input al mapear/redibujar (evita bloquear clics)
        self.connect("map", lambda *_: self._update_input_region())

        _apply_transparency(self.get_display() or Gdk.Display.get_default())

        # arrastrar (botón izquierdo Y derecho).
        # IMPORTANTE: los gestos van en la VENTANA (fullscreen, estática), no en
        # el picture: el sprite se mueve cambiando los márgenes, así que medir el
        # offset sobre el propio picture (que se desplaza bajo el cursor) creaba
        # un bucle de realimentación → la mascota "saltaba". En coordenadas de la
        # ventana el offset es estable y el arrastre sigue al cursor 1:1.
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        drag_right = Gtk.GestureDrag()
        drag_right.set_button(3)
        drag_right.connect("drag-begin", self._on_drag_begin)
        drag_right.connect("drag-update", self._on_drag_update)
        drag_right.connect("drag-end", self._on_drag_end)
        self.add_controller(drag_right)

        # cursor encima -> saludar (en la picture, solo pixels opacos)
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._on_cursor_enter)
        self.picture.add_controller(motion)

        # cursor encima -> revelar la barra de control (Administrar / Cerrar)
        if getattr(self, "_overlay_hover", None) is not None:
            self.picture.add_controller(self._overlay_hover)

        # tocarla (click) -> reaccionar / enojarse
        click = Gtk.GestureClick()
        click.connect("pressed", self._on_click)
        self.picture.add_controller(click)

        # motion en la VENTANA fullscreen: en modo grab el sprite sigue el cursor
        # por todo el escritorio (la región de input cubre toda la pantalla).
        win_motion = Gtk.EventControllerMotion()
        win_motion.connect("motion", self._on_grab_motion)
        self.add_controller(win_motion)

        # estado de interacción
        self._anger = 0          # sube al tocarla repetido
        self._react_ttl = 0      # ticks de reacción (jitter)
        self._jitter_base = 0    # x base mientras tiembla
        self._last_drag = None   # (t, ox, oy) para medir velocidad de arrastre
        self._grab_ttl  = 0      # ticks en estado "agarra el ratón"
        self._rest_ttl  = 0      # ticks de reposo tras aterrizar
        self._greet_cd  = 0      # cooldown anti-bucle de saludos


    # ---------- barra de control sobre el sprite ----------
    def _build_ctrl_bar(self):
        """Pequeña barra con «Administrar» y «Cerrar», anclada arriba-derecha
        del sprite. Oculta por defecto; se revela al pasar el cursor encima."""
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        bar.add_css_class("animalinux-ctrlbar")

        manage = Gtk.Button(label="⚙")
        manage.set_tooltip_text("Administrar mascotas")
        manage.add_css_class("animalinux-ctrlbtn")
        manage.connect("clicked", self._on_manage_clicked)
        bar.append(manage)

        close = Gtk.Button(label="✕")
        close.set_tooltip_text("Quitar del escritorio")
        close.add_css_class("animalinux-ctrlbtn")
        close.connect("clicked", self._on_close_clicked)
        bar.append(close)

        # Revealer para mostrar/ocultar suavemente al hacer hover
        self._ctrl_revealer = Gtk.Revealer()
        self._ctrl_revealer.set_transition_type(
            Gtk.RevealerTransitionType.CROSSFADE)
        self._ctrl_revealer.set_transition_duration(120)
        self._ctrl_revealer.set_reveal_child(False)
        self._ctrl_revealer.set_child(bar)
        self._ctrl_revealer.set_halign(Gtk.Align.END)
        self._ctrl_revealer.set_valign(Gtk.Align.START)

        # hover sobre el área del sprite revela/oculta la barra
        hover = Gtk.EventControllerMotion()
        hover.connect("enter", lambda *_: self._ctrl_revealer.set_reveal_child(True))
        hover.connect("leave", lambda *_: self._ctrl_revealer.set_reveal_child(False))
        self._overlay_hover = hover  # se añade al picture en __init__ tardío
        return self._ctrl_revealer

    def _on_manage_clicked(self, _btn):
        # abre (o trae al frente) la ventana de configuración
        try:
            self._app.show_control()
        except Exception:  # noqa: BLE001
            pass

    def _on_close_clicked(self, _btn):
        # quita la mascota del escritorio y lo persiste para que no reaparezca
        aid = self.anim["id"]
        try:
            self._app.library.update(aid, on_desktop=False)
            if self._app.control is not None:
                self._app.control.refresh()
        except Exception:  # noqa: BLE001
            pass
        self._app.set_mascot_visible(aid, False)

    # ---------- posición ----------
    def _set_position(self, x, y):
        # el sprite se mueve dentro de la ventana fullscreen vía márgenes de la
        # picture (la ventana en sí nunca se mueve ni se redimensiona)
        self._x = max(0, int(x))
        self._y = max(0, int(y))
        self._overlay.set_margin_start(self._x)
        self._overlay.set_margin_top(self._y)
        self._update_input_region()

    def _update_input_region(self):
        """Limita lo clicable a la caja del sprite (o a toda la pantalla en grab,
        para capturar el cursor en cualquier sitio). Sin esto, la ventana
        fullscreen bloquearía todo el escritorio."""
        surf = self.get_surface()
        if surf is None:
            return
        try:
            import cairo
            if self._grabbing:
                reg = cairo.Region(cairo.RectangleInt(
                    0, 0, self._screen_w, self._screen_h))
            else:
                reg = cairo.Region(cairo.RectangleInt(
                    self._x, self._y, self._cat_w, self._cat_h))
            surf.set_input_region(reg)
        except Exception:  # noqa: BLE001
            pass

    def _on_drag_begin(self, gesture, sx, sy):
        if self._state == "grab":
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        self._dragging = True
        self._drag_origin = (self._x, self._y)
        self._toss_vx = 0.0
        self._toss_vy = 0.0
        self._last_drag = (GLib.get_monotonic_time(), 0.0, 0.0)

    def _on_drag_update(self, gesture, ox, oy):
        if self._state == "grab":
            return
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
        """La mascota agarra el cursor: amplía la región de input a toda la
        pantalla (la ventana YA es fullscreen) y el sprite sigue el puntero por
        todo el escritorio hasta soltarlo. NO redimensiona nada → sin artefactos."""
        self._grab_ttl = 80   # ~5 s a 60 ms/tick
        self._state = "grab"
        self._grabbing = True
        self._toss_vx = 0.0
        self._toss_vy = 0.0
        if self._has_pose("grab"):
            self._pose = "grab"
        elif self._has_pose("angry"):
            self._pose = "angry"
        self._update_input_region()   # ahora captura el cursor en toda la pantalla

    def _on_grab_motion(self, ctrl, mx, my):
        """En grab: la ventana cubre la pantalla, así que (mx,my) son coordenadas
        de pantalla → centra el sprite en el cursor (lo 'sujeta')."""
        if not self._grabbing or self._dragging:
            return
        w, h = self._cat_w, self._cat_h
        nx = max(0, min(self._screen_w - w, int(mx - w / 2)))
        ny = max(0, min(self._screen_h - h, int(my - h / 2)))
        self._set_position(nx, ny)

    def _end_grab_restore(self):
        """Suelta el cursor: la región de input vuelve a la caja del sprite.
        El sprite se queda DONDE estaba el cursor (self._x/_y), sin teleport."""
        self._grabbing = False
        self._update_input_region()

    def _cool_down(self):
        self._anger = max(0, self._anger - 1)
        return False

    # ---------- poses / texturas ----------
    def _load_poses(self):
        base = Path(self._frames_dir)
        # tamaño base = el de la pose 'default'. Todas las demás poses se
        # normalizan a este tamaño para que la mascota NO cambie de tamaño al
        # cambiar de animación (algunas poses se generan con otro lienzo).
        self._base_size = None
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
        normals = sorted(folder.glob("frame_*.png"))
        flips = sorted(folder.glob("flip_*.png"))
        if not normals:
            return
        # la primera pose cargada (default) fija el tamaño base de referencia
        if self._base_size is None:
            try:
                from PIL import Image
                self._base_size = Image.open(str(normals[0])).size
            except Exception:  # noqa: BLE001
                self._base_size = None
        normal = [t for t in (self._load_texture(p) for p in normals) if t]
        flip = [t for t in (self._load_texture(p) for p in flips) if t]
        if not flip:
            flip = normal
        if normal:
            self._poses[name] = {"normal": normal, "flip": flip}

    def _load_texture(self, path):
        """Carga un PNG como textura, redimensionado al tamaño base si difiere
        (así todas las poses ocupan exactamente el mismo lienzo)."""
        target = self._base_size
        try:
            from PIL import Image
            im = Image.open(str(path))
            if target is None or im.size == tuple(target):
                return Gdk.Texture.new_from_filename(str(path))
            im = im.convert("RGBA").resize(tuple(target), Image.NEAREST)
            data = im.tobytes()
            gbytes = GLib.Bytes.new(data)
            return Gdk.MemoryTexture.new(
                im.width, im.height,
                Gdk.MemoryFormat.R8G8B8A8, gbytes, im.width * 4)
        except Exception:  # noqa: BLE001
            try:
                return Gdk.Texture.new_from_filename(str(path))
            except Exception:  # noqa: BLE001
                return None

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
        # forzar la ventana al tamaño del monitor → superficie REALMENTE fullscreen
        # (sin esto la superficie queda del tamaño del contenido y el sprite se
        # teletransporta al recortarse los márgenes)
        self.set_size_request(self._screen_w, self._screen_h)
        self.set_default_size(self._screen_w, self._screen_h)
        self.queue_resize()
        if self.mode == "life":
            self._enter_life()
        else:
            # gif estático: reubica el sprite ahora que conocemos el tamaño real
            self._set_position(self._x, self._y)
        self._schedule_anim()
        GLib.idle_add(self._update_input_region)

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
        if r < 0.22:
            # pausa breve; a veces se gira para "mirar alrededor"
            self._state = "idle"
            self._state_ttl = random.randint(15, 45)
            self._speed = 0
            if random.random() < 0.35:
                self._facing_left = not self._facing_left
                self._dir = -1 if self._facing_left else 1
            self._pose = "idle" if self._has_pose("idle") else "default"
        elif r < 0.72:
            # caminar: tramos largos y mantiene el rumbo casi siempre
            # (cambiar de dirección sólo el 25% de las veces = menos nervioso)
            self._state = "walk"
            self._state_ttl = random.randint(45, 120)
            if random.random() < 0.25 or self._dir == 0:
                self._dir = random.choice([-1, 1])
            self._speed = random.randint(2, 4)
            self._facing_left = self._dir < 0
            self._pose = "walk" if self._has_pose("walk") else "default"
        elif r < 0.88:
            # brinco hacia adelante: avanza mientras salta
            self._start_hop()
        else:
            # salto vertical en el sitio
            self._start_jump()

    def _start_jump(self):
        self._state = "jump"
        self._jump_vy = -random.randint(14, 22)   # impulso hacia arriba
        self._pose = "jump" if self._has_pose("jump") else "default"

    def _start_hop(self):
        """Brinco con avance horizontal (reusa la física de 'toss')."""
        if self._dir == 0:
            self._dir = random.choice([-1, 1])
        self._state = "toss"
        self._toss_vx = self._dir * random.uniform(2.5, 4.5)
        self._toss_vy = -float(random.randint(9, 14))
        self._facing_left = self._toss_vx < 0
        self._pose = "jump" if self._has_pose("jump") else "default"
        self._index = 0

    def trigger_greet(self):
        """Saludar: usa la pose 'greet' si existe; si no, da un saltito."""
        if self._greet_ttl > 0 or self._greet_cd > 0:
            return
        if self._has_pose("greet"):
            self._greet_ttl = GREET_TICKS
            self._pose = "greet"
        elif self._state != "jump":
            self._start_jump()

    def _behavior_tick(self):
        if self._paused or self._dragging:
            return True

        # cooldown de saludo: decrementa siempre
        if self._greet_cd > 0:
            self._greet_cd -= 1

        # ── modo agarre del ratón (sigue el cursor; al soltar se lanza) ──
        if self._state == "grab":
            self._grab_ttl -= 1
            # el sprite ya sigue al cursor vía _on_grab_motion; aquí sólo cuenta
            if self._grab_ttl <= 0:
                self._grab_ttl = 0
                self._anger = 0
                # restaura la ventana en la posición ACTUAL (donde el cursor lo
                # dejó) y lanza desde ahí → sin teletransporte
                self._end_grab_restore()
                vx = random.choice([-1, 1]) * random.randint(20, 38)
                self._toss_vx = vx
                self._toss_vy = random.randint(-20, -10)
                self._facing_left = vx < 0
                self._state = "toss"
                self._pose = "jump" if self._has_pose("jump") else "default"
                self._index = 0
            return True

        # ── caída libre (soltar suave en el aire) ──────────────────────────
        if self._state == "falling":
            if self._y < self._floor_y:
                self._toss_vy += GRAVITY
                ny = min(self._floor_y, self._y + int(self._toss_vy))
                self._set_position(self._x, ny)
            if self._y >= self._floor_y:
                self._toss_vy = 0.0
                self._rest_ttl = random.randint(12, 28)
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
                self._rest_ttl = random.randint(12, 30)
                self._state = "rest"
                self._pose = "idle" if self._has_pose("idle") else "default"
                self._index = 0
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
                self._greet_cd = GREET_COOLDOWN   # bloquea re-saludo ~5 s
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
        self.picture.queue_resize()
        self._overlay.queue_resize()
        self.queue_resize()
        if self.mode == "life":
            self._floor_y = max(0, self._screen_h - h)
            self._set_position(self._x, self._floor_y)
        else:
            self._set_position(self._x, self._y)   # actualiza también la región

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

    def destroy_window(self):
        if self._anim_id:
            GLib.source_remove(self._anim_id)
        if self._behavior_id:
            GLib.source_remove(self._behavior_id)
        self.destroy()
