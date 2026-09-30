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

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Graphene  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

from .live_animation import LiveAnimationMixin  # noqa: E402
from .poses import PoseLoaderMixin  # noqa: E402
from .clock import Clock  # noqa: E402
from .hyprcursor import cursor_pos  # noqa: E402
from .. import settings

_CSS_APPLIED = False


class ScaledPaintable(GObject.GObject, Gdk.Paintable):
    """Envuelve una textura y reporta su tamaño intrínseco MULTIPLICADO por un
    factor de escala. Así GtkPicture toma como tamaño natural el escalado y el
    sprite puede agrandarse Y EMPEQUEÑECERSE (un size_request menor que el
    intrínseco no encoge un GtkPicture; esto sí). GTK escala al dibujar, sin
    re-rasterizar píxeles."""
    def __init__(self):
        super().__init__()
        self._tex = None
        self._scale = 1.0
        self._bw = 1
        self._bh = 1
        # deformación dinámica (squash&stretch + inclinación) ANCLADA en los
        # pies. No cambia el tamaño intrínseco (no thrashea el layout): solo
        # transforma el dibujo en do_snapshot.
        self._sx = 1.0
        self._sy = 1.0
        self._lean = 0.0   # grados
        self._bob = 0.0    # desplazamiento vertical, fracción de la altura (+ = arriba)
        self._mirror = False   # espejo horizontal (mirar a la izquierda)

    def set_mirror(self, on):
        on = bool(on)
        if on != self._mirror:
            self._mirror = on
            self.invalidate_contents()

    def set_texture(self, tex):
        self._tex = tex
        if tex is not None:
            self._bw = tex.get_intrinsic_width()
            self._bh = tex.get_intrinsic_height()
        self.invalidate_contents()

    def set_scale_factor(self, s):
        self._scale = max(0.05, float(s))
        self.invalidate_size()

    def set_squash(self, sx, sy):
        if (sx, sy) != (self._sx, self._sy):
            self._sx, self._sy = sx, sy
            self.invalidate_contents()

    def set_bob(self, frac):
        if frac != self._bob:
            self._bob = frac
            self.invalidate_contents()

    def set_lean(self, deg):
        if deg != self._lean:
            self._lean = deg
            self.invalidate_contents()

    def do_get_intrinsic_width(self):
        return max(1, int(self._bw * self._scale))

    def do_get_intrinsic_height(self):
        return max(1, int(self._bh * self._scale))

    def do_snapshot(self, snapshot, width, height):
        if self._tex is None:
            return
        sx, sy, lean, bob = self._sx, self._sy, self._lean, self._bob
        deform = (sx != 1.0 or sy != 1.0 or lean != 0.0 or bob != 0.0)
        if deform:
            snapshot.save()
            # anclar la transformación en los pies (centro-abajo)
            snapshot.translate(Graphene.Point().init(width / 2.0, height - bob * height))
            if lean:
                snapshot.rotate(lean)
            if sx != 1.0 or sy != 1.0:
                snapshot.scale(sx, sy)
            snapshot.translate(Graphene.Point().init(-width / 2.0, -height))
        if self._mirror:
            snapshot.save()
            snapshot.translate(Graphene.Point().init(width / 2.0, 0))
            snapshot.scale(-1.0, 1.0)
            snapshot.translate(Graphene.Point().init(-width / 2.0, 0))
            self._tex.snapshot(snapshot, width, height)
            snapshot.restore()
        else:
            self._tex.snapshot(snapshot, width, height)
        if deform:
            snapshot.restore()


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


class MascotWindow(PoseLoaderMixin, LiveAnimationMixin, Gtk.Window):
    # Hacia dónde mira. Se espeja al dibujar (no hay texturas "flip" duplicadas
    # en memoria): el setter avisa al paintable.
    @property
    def _facing_left(self):
        return self._face_left_v

    @_facing_left.setter
    def _facing_left(self, v):
        v = bool(v)
        self._face_left_v = v
        pt = getattr(self, "_paintable", None)
        if pt is not None:
            pt.set_mirror(v)

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
        self._face_left_v = False
        self._index = 0
        self._anim_id = None
        self._behavior_id = None
        self._tick_id = None
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
        # px libres bajo el área de trabajo (_NET_WORKAREA) que install.sh
        # midió una vez: el hueco que deja la barra de tareas u otro panel
        # anclado abajo. El suelo se calcula por encima de esto para que la
        # mascota no camine tapada por la barra.
        # saneado: valores >120px no pueden ser una barra de tareas real (ver
        # install.sh) — si settings.json quedó con un valor disparatado de una
        # detección multi-monitor defectuosa, se ignora en vez de clavar la
        # mascota en el borde superior de la pantalla.
        floor_offset = settings.get("floor_offset_px", 0)
        self._floor_offset_y = floor_offset if 0 <= floor_offset <= 120 else 0

        # física del tiro (parabólica)
        self._toss_vx = 0.0
        self._toss_vy = 0.0    # velocidad vertical durante el tiro

        self.add_css_class("animalinux-mascot")
        self.set_decorated(False)
        self.set_resizable(False)

        LayerShell.init_for_window(self)
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_namespace(self, "animalinux-mascot")
        # La superficie es COMPACTA: solo el tamaño del sprite más un margen para
        # el squash/inclinación, anclada arriba-izquierda y movida por márgenes
        # de layer-shell. Una ventana fullscreen por mascota costaba ~40 MB de
        # GPU y un repintado enorme cada vez. Solo pasa a pantalla completa
        # mientras se arrastra o "agarra" el cursor (hace falta seguir al puntero
        # por todo el escritorio) y vuelve a compacta al soltar.
        self._full = False
        # con Hyprland el cursor se lee por su socket → nunca hace falta pantalla completa
        self._poll_ok = cursor_pos() is not None
        self._cursor_task = None
        self._surf_w = self._surf_h = 0
        self._ox = self._oy = 0
        self._pad = 0
        self._win_pos = None
        self._drag_grab = (0, 0)
        for edge in (LayerShell.Edge.LEFT, LayerShell.Edge.TOP):
            LayerShell.set_anchor(self, edge, True)
            LayerShell.set_margin(self, edge, 0)
        for edge in (LayerShell.Edge.RIGHT, LayerShell.Edge.BOTTOM):
            LayerShell.set_anchor(self, edge, False)
            LayerShell.set_margin(self, edge, 0)
        # zona exclusiva -1 → los márgenes se miden desde el borde real del
        # monitor (ignora las áreas reservadas por barras)
        LayerShell.set_exclusive_zone(self, -1)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.NONE)

        self._load_poses()
        scale = anim.get("scale", 1.0)
        w = int(anim.get("width", 100) * scale)
        h = int(anim.get("height", 100) * scale)
        self._cat_w = w
        self._cat_h = h

        # El sprite se muestra a través de un ScaledPaintable: una sola vez se
        # asigna al picture y luego sólo cambiamos su textura (cada frame) y su
        # factor de escala (al hacer zoom). Esto permite empequeñecer el sprite,
        # cosa que size_request por sí solo NO logra en un GtkPicture.
        self._paintable = ScaledPaintable()
        self._paintable.set_scale_factor(scale / self._bake)
        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        self.picture.set_content_fit(Gtk.ContentFit.FILL)
        self.picture.set_halign(Gtk.Align.START)
        self.picture.set_valign(Gtk.Align.START)
        # overflow visible: el squash&stretch/lean puede dibujar fuera de la
        # caja del sprite (estirado o inclinado) sin que se recorte.
        self.picture.set_overflow(Gtk.Overflow.VISIBLE)
        self.picture.set_paintable(self._paintable)
        first = self._frames_for("default")
        if first:
            self._paintable.set_texture(first[0])

        # contenedor que se mueve dentro de la ventana fullscreen vía márgenes
        # (la ventana nunca se mueve ni se redimensiona). NO se ponen botones ni
        # opciones encima del sprite: la gestión se hace desde la ventana de
        # control / bandeja, no sobre la mascota.
        self._overlay = Gtk.Box()
        # SIN halign/valign=START aquí: ver el mismo comentario en
        # overlay/x11_animation.py — es un bug real de GTK4 que deja el Box
        # con alto=0 al asignar, aunque el tamaño natural medido sea
        # correcto, y el sprite nunca llega a dibujarse. El Box se queda con
        # su FILL por defecto; el posicionamiento ya lo dan los márgenes
        # (_set_position) y el propio picture (start/start) dentro de él.
        self._overlay.set_overflow(Gtk.Overflow.VISIBLE)
        self._overlay.append(self.picture)
        self.set_child(self._overlay)

        # posición inicial del sprite (márgenes de la picture)
        self._set_position(anim.get("x", 100), anim.get("y", 100))
        # refrescar la región de input al mapear/redibujar (evita bloquear clics)
        self.connect("map", self._on_map)

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
        self._grab_anchor = None # ancla (mx,my,x,y) para seguir el cursor relativo
        self._rest_ttl  = 0      # ticks de reposo tras aterrizar
        self._greet_cd  = 0      # cooldown anti-bucle de saludos

        # ── mejoras modo Vida ───────────────────────────────────────────────
        self._walk_phase = 0.0   # fase de caminado ligada a la DISTANCIA (idea 2)
        self._sq_sx = 1.0        # squash & stretch dinámico (idea 1)
        self._sq_sy = 1.0
        self._lean = 0.0         # inclinación al lanzarse/caer (idea 10)
        self._lean_target = 0.0
        self._last_cursor_x = None  # última X del cursor sobre la mascota (idea 6)
        self._phys_k = 1.0       # factor de física según tamaño (idea 3)
        self._gravity = 2.0      # = live_animation.GRAVITY; se recalcula en _enter_life
        self._idle_accum = 0     # acumulador para dormirse (idea 4)
        self._sleep_phase = 0
        self._mon_x = 0          # offset del monitor (idea 5/8)
        self._mon_y = 0
        self._ground_y = 0       # y-tope del sprite cuando está apoyado (idea 5)
        self._climb_target = None  # (x, y_tope, altura) al trepar a una ventana
        self._retreat_from = None  # X de la otra mascota tras saludarse (idea 7)
        # berrinche por aburrimiento (idea 11)
        self._last_interaction = GLib.get_monotonic_time()
        self._bored_phase = 0    # 0=normal 1=ya agarró 2=desactivada
        self._bored_grab = False
        self._orig_scale = anim.get("scale", 1.0)


    # ---------- posición ----------
    def _set_position(self, x, y):
        # coordenadas del sprite en el monitor. En modo compacto se mueve la
        # superficie entera con márgenes de layer-shell; en modo pantalla
        # completa (arrastre/agarre) se mueve el contenedor dentro de la ventana.
        self._x = max(0, int(x))
        self._y = max(0, int(y))
        self._place()
        self._update_input_region()

    def _on_map(self, *_):
        surf = self.get_surface()
        if surf is not None:
            surf.connect("layout", self._on_surface_layout)
        self._update_input_region()

    def _on_surface_layout(self, surf, w, h):
        self._surf_w, self._surf_h = w, h
        self._apply_input_region()

    def _full_ready(self):
        """True cuando la superficie ya mide el monitor entero (tras pasar a
        modo pantalla completa): solo entonces las coordenadas del puntero
        son coordenadas de monitor."""
        return (self._full and self._surf_w >= self._screen_w - 4
                and self._surf_h >= self._screen_h - 4)

    def _place(self):
        if self._full:
            self._overlay.set_margin_start(self._x)
            self._overlay.set_margin_top(self._y)
            return
        pad = int(0.45 * max(self._cat_w, self._cat_h)) + 6
        ox = min(pad, self._x)
        oy = min(pad, self._y)
        self._ox, self._oy = ox, oy
        if pad != self._pad:
            self._pad = pad
            self._overlay.set_margin_end(pad)
            self._overlay.set_margin_bottom(pad)
        self._overlay.set_margin_start(ox)
        self._overlay.set_margin_top(oy)
        # tamaño explícito: sin él el compositor puede darle a la superficie el
        # tamaño de todo el monitor en la primera configuración
        size = (ox + self._cat_w + pad, oy + self._cat_h + pad)
        if size != getattr(self, "_win_size", None):
            self._win_size = size
            self.set_size_request(*size)
            self.set_default_size(*size)
        pos = (self._x - ox, self._y - oy)
        if pos != self._win_pos:
            self._win_pos = pos
            LayerShell.set_margin(self, LayerShell.Edge.LEFT, pos[0])
            LayerShell.set_margin(self, LayerShell.Edge.TOP, pos[1])

    def _sync_surface(self):
        """Compacta ↔ pantalla completa según haga falta (arrastrando o
        agarrando el cursor hace falta la pantalla entera)."""
        want_full = bool((self._dragging or self._grabbing) and not self._poll_ok)
        if want_full == self._full:
            return
        self._full = want_full
        E = LayerShell.Edge
        if want_full:
            for e in (E.RIGHT, E.BOTTOM):
                LayerShell.set_anchor(self, e, True)
            for e in (E.LEFT, E.TOP, E.RIGHT, E.BOTTOM):
                LayerShell.set_margin(self, e, 0)
            self._overlay.set_margin_end(0)
            self._overlay.set_margin_bottom(0)
            self.set_size_request(self._screen_w, self._screen_h)
            self.set_default_size(self._screen_w, self._screen_h)
        else:
            for e in (E.RIGHT, E.BOTTOM):
                LayerShell.set_anchor(self, e, False)
            self._pad = 0
            self._win_pos = None
            self._win_size = None
        self._place()

    def _update_input_region(self):
        self._sync_surface()
        self._apply_input_region()

    def _apply_input_region(self):
        """Limita lo clicable a la caja del sprite (o a toda la pantalla en grab,
        para capturar el cursor en cualquier sitio). Sin esto, la ventana
        fullscreen bloquearía todo el escritorio."""
        surf = self.get_surface()
        if surf is None:
            return
        try:
            import cairo
            if self._full and self._grabbing:
                reg = cairo.Region(cairo.RectangleInt(
                    0, 0, self._screen_w, self._screen_h))
            elif self._full:
                reg = cairo.Region(cairo.RectangleInt(
                    self._x, self._y, self._cat_w, self._cat_h))
            else:
                reg = cairo.Region(cairo.RectangleInt(
                    self._ox, self._oy, self._cat_w, self._cat_h))
            surf.set_input_region(reg)
        except Exception:  # noqa: BLE001
            pass

    def _on_drag_begin(self, gesture, sx, sy):
        if self._state == "grab":
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        if self.mode == "life":
            self._wake()          # idea 4: arrastrarla la despierta
        # dónde agarraste el sprite (el gesto llega en coords de la superficie
        # compacta; el sprite arranca en (_ox,_oy) dentro de ella)
        self._drag_grab = (sx - self._ox, sy - self._oy) if not self._full \
            else (sx - self._x, sy - self._y)
        self._dragging = True
        self._drag_origin = (self._x, self._y)
        self._toss_vx = 0.0
        self._toss_vy = 0.0
        # cancela un temblor/saludo pendiente para que no actúe al soltar
        self._react_ttl = 0
        self._greet_ttl = 0
        self._last_drag = (GLib.get_monotonic_time(), float(self._x), float(self._y))
        if self._poll_ok:
            self._cursor_task = Clock.get().every(16, self._drag_poll)
        self._sync_surface()      # (sin Hyprland) pantalla completa para seguir al puntero
        self._apply_input_region()

    def _on_drag_update(self, gesture, ox, oy):
        # la posición se calcula con el puntero absoluto en _on_grab_motion
        # (los offsets del gesto se falsean al cambiar la superficie de tamaño)
        pass

    def _drag_poll(self):
        if not self._dragging:
            self._cursor_task = None
            return False
        p = cursor_pos()
        if p is not None:
            self._drag_follow(p[0] - self._mon_x, p[1] - self._mon_y)
        return True

    def _start_grab(self):
        LiveAnimationMixin._start_grab(self)
        if self._grabbing and self._poll_ok and self._cursor_task is None:
            self._cursor_task = Clock.get().every(16, self._grab_poll)

    def _grab_poll(self):
        if not self._grabbing:
            self._cursor_task = None
            return False
        p = cursor_pos()
        if p is not None:
            LiveAnimationMixin._on_grab_motion(
                self, None, p[0] - self._mon_x, p[1] - self._mon_y)
        return True

    def _end_grab_restore(self):
        if self._cursor_task is not None:
            Clock.get().cancel(self._cursor_task)
            self._cursor_task = None
        LiveAnimationMixin._end_grab_restore(self)

    def _drag_follow(self, gx, gy):
        nx = gx - self._drag_grab[0]
        ny = gy - self._drag_grab[1]
        self._set_position(nx, ny)
        now = GLib.get_monotonic_time()
        if self._last_drag:
            t0, x0, y0 = self._last_drag
            dt = (now - t0) / 1_000_000.0
            if dt > 0.01:
                self._drag_vx = (self._x - x0) / dt
                self._drag_vy = (self._y - y0) / dt
                self._last_drag = (now, float(self._x), float(self._y))

    def _on_drag_end(self, gesture, ox, oy):
        self._dragging = False
        if self._cursor_task is not None and not self._grabbing:
            Clock.get().cancel(self._cursor_task)
            self._cursor_task = None
        self._sync_surface()
        self._apply_input_region()
        if self.mode == "life" and self._state != "grab":
            vx = getattr(self, "_drag_vx", 0.0)   # px/seg (medido en drag-update)
            vy = getattr(self, "_drag_vy", 0.0)
            # si el último movimiento fue hace rato, soltaste PARADO → sin impulso
            last = getattr(self, "_last_drag", None)
            if last is not None:
                age = (GLib.get_monotonic_time() - last[0]) / 1_000_000.0
                if age > 0.08:
                    vx = vy = 0.0
            speed = (vx * vx + vy * vy) ** 0.5
            if speed > 250:
                # LANZAR: impulso horizontal → arco parabólico. px/seg → px/tick
                # con factor pequeño y ACOTADO (máx 14 px/tick) para que sea un
                # lanzamiento creíble y NUNCA un salto/teletransporte.
                self._toss_vx = max(-14.0, min(14.0, vx * 0.012))
                self._toss_vy = max(-18.0, min(2.0,  vy * 0.012))
                self._state = "toss"
            else:
                # soltar parado → cae recto al suelo, X no cambia
                self._toss_vx = 0.0
                self._toss_vy = 0.0
                self._state = "falling"
            self._pose = "jump" if self._has_pose("jump") else "default"
        if self.on_moved:
            self.on_moved(self.anim["id"], self._x, self._y)
        self._drag_vx = 0.0
        self._drag_vy = 0.0

    def _on_grab_motion(self, ctrl, mx, my):
        if self._dragging:
            if self._full_ready():
                self._drag_follow(mx, my)
            return
        if not self._full:
            # superficie compacta: el puntero llega en coords de la superficie
            self._last_cursor_x = mx + self._x - self._ox
            return
        if not self._full_ready():
            return
        LiveAnimationMixin._on_grab_motion(self, ctrl, mx, my)

    def _on_cursor_enter(self, controller, x, y):
        if self.mode == "life" and self._state != "grab":
            self._wake()              # pasar el cursor por encima = atención
            self.trigger_greet()

    def _grab_keyboard(self, on):
        """Berrinche: bloquear/soltar el teclado (capa exclusiva)."""
        try:
            mode = (LayerShell.KeyboardMode.EXCLUSIVE if on
                    else LayerShell.KeyboardMode.NONE)
            LayerShell.set_keyboard_mode(self, mode)
        except Exception:  # noqa: BLE001
            pass

    def _on_click(self, gesture, n_press, x, y):
        if self.mode == "life":
            self._react_to_touch()

    # ---------- poses / texturas ----------
    # ---------- arranque ----------
    def start(self):
        self.present()
        self._update_screen_size()
        if self.mode == "life":
            self._enter_life()
        else:
            # gif estático: reubica el sprite ahora que conocemos el tamaño real
            self._set_position(self._x, self._y)
        self._schedule_anim()
        GLib.idle_add(self._update_input_region)
        # Sin tick callback permanente: el repintado se pide solo cuando cambia
        # la textura/posición (ver Clock). Un tick callback por mascota
        # despertaba al proceso en cada vsync (~60 Hz × nº de mascotas).

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
                # offset del monitor: las ventanas de hyprctl vienen en coords
                # GLOBALES; restando esto se pasan a coords locales del monitor.
                self._mon_x, self._mon_y = geo.x, geo.y
        except Exception:  # noqa: BLE001
            pass

    # ---------- animación de frames ----------
    def _schedule_anim(self):
        if self._anim_id:
            Clock.get().cancel(self._anim_id)
            self._anim_id = None
        if self._paused:
            return
        fps = max(1, int(self.anim.get("fps", 12)))
        self._anim_id = Clock.get().every(1000.0 / fps, self._anim_tick)

    def _anim_tick(self):
        frames = self._frames_for(self._pose)
        if self._paused or len(frames) == 0:
            return True
        # Idea 2: el caminado avanza con la DISTANCIA recorrida (no con un fps
        # fijo), así los pies no "patinan". _walk_phase lo alimenta el behavior
        # tick (px/zancada). Para el resto de poses, avance normal por tiempo.
        if self.mode == "life" and self._pose == "walk" and self._state == "walk":
            self._index = int(self._walk_phase) % len(frames)
        else:
            self._index = (self._index + 1) % len(frames)
        self._paintable.set_texture(frames[self._index])
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
        # escala vía el paintable (encoge y agranda); el tamaño natural del
        # picture pasa a ser el escalado, así halign START lo respeta en ambos
        # sentidos. queue_resize fuerza el re-layout inmediato.
        if scale > self._bake * 1.001:
            self._schedule_rebake()
        self._paintable.set_scale_factor(scale / self._bake)
        self.picture.queue_resize()
        self._overlay.queue_resize()
        self.queue_resize()
        if self.mode == "life":
            self._floor_y = max(0, self._screen_h - self._floor_offset_y - h)
            self._set_position(self._x, self._floor_y)
        else:
            self._set_position(self._x, self._y)   # actualiza también la región

    def _schedule_rebake(self):
        """Agrandaste la mascota por encima de la resolución de sus texturas:
        se recargan a la nueva resolución (con un pequeño retardo para no
        recargar en cada paso del deslizador)."""
        if getattr(self, "_rebake_id", 0):
            GLib.source_remove(self._rebake_id)
        self._rebake_id = GLib.timeout_add(250, self._rebake)

    def _rebake(self):
        self._rebake_id = 0
        self._poses = {}
        self._load_poses()
        scale = self.anim.get("scale", 1.0)
        self._paintable.set_scale_factor(scale / self._bake)
        frames = self._frames_for(self._pose)
        if frames:
            self._index %= len(frames)
            self._paintable.set_texture(frames[self._index])
        return False

    def set_mode(self, mode):
        self.mode = mode
        self.anim["mode"] = mode
        if mode == "life":
            self._update_screen_size()
            self._enter_life()
        else:
            self._exit_life()

    def set_paused(self, paused):
        if paused == self._paused:
            return
        self._paused = paused
        # en pausa no queda ningún temporizador vivo (el proceso duerme del todo)
        if paused:
            if self._anim_id:
                Clock.get().cancel(self._anim_id)
                self._anim_id = None
            self._stop_behavior_clock()
        else:
            self._schedule_anim()
            if self.mode == "life":
                self._start_behavior_clock()

    def center_x(self):
        scale = self.anim.get("scale", 1.0)
        return self._x + int(self.anim.get("width", 100) * scale) / 2

    def destroy_window(self):
        if self._anim_id:
            Clock.get().cancel(self._anim_id)
            self._anim_id = None
        self._stop_behavior_clock()
        self.destroy()
