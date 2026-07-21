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
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Graphene  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

from .live_animation import LiveAnimationMixin  # noqa: E402
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
        sx, sy, lean = self._sx, self._sy, self._lean
        deform = (sx != 1.0 or sy != 1.0 or lean != 0.0)
        if deform:
            snapshot.save()
            # anclar la transformación en los pies (centro-abajo)
            snapshot.translate(Graphene.Point().init(width / 2.0, height))
            if lean:
                snapshot.rotate(lean)
            if sx != 1.0 or sy != 1.0:
                snapshot.scale(sx, sy)
            snapshot.translate(Graphene.Point().init(-width / 2.0, -height))
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


class MascotWindow(LiveAnimationMixin, Gtk.Window):
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
        self._floor_offset_y = settings.get("floor_offset_px", 0)

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

        # El sprite se muestra a través de un ScaledPaintable: una sola vez se
        # asigna al picture y luego sólo cambiamos su textura (cada frame) y su
        # factor de escala (al hacer zoom). Esto permite empequeñecer el sprite,
        # cosa que size_request por sí solo NO logra en un GtkPicture.
        self._paintable = ScaledPaintable()
        self._paintable.set_scale_factor(scale)
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
        # el sprite se mueve dentro de la ventana fullscreen vía márgenes del
        # contenedor (la ventana en sí nunca se mueve ni se redimensiona)
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
        if self.mode == "life":
            self._wake()          # idea 4: arrastrarla la despierta
        self._dragging = True
        self._drag_origin = (self._x, self._y)
        self._toss_vx = 0.0
        self._toss_vy = 0.0
        # cancela un temblor/saludo pendiente para que no actúe al soltar
        self._react_ttl = 0
        self._greet_ttl = 0
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
    def _load_poses(self):
        base = Path(self._frames_dir)
        # tamaño base = el de la pose 'default'. Todas las demás poses se
        # normalizan a este tamaño para que la mascota NO cambie de tamaño al
        # cambiar de animación (algunas poses se generan con otro lienzo).
        self._base_size = None
        # auto-recorte: calcula la caja real del dibujo de la pose default y
        # ajusta anim width/height (lo usan input region, colisiones y bordes)
        self._orig_size = None
        self._crop_box = None
        self._compute_crop_box(base)
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
                from ..core import image_processor as importer
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

    def _compute_crop_box(self, base):
        """Calcula la caja real (unión de bboxes de TODAS las poses) para
        recortar el margen transparente. Muchas mascotas se importan con un
        lienzo enorme de margen vacío (medido: hasta 60-67% del área): eso
        hacía la caja de input gigante y los bordes de caminado raros.
        Recortando al contenido real mejora input region, colisiones y bordes
        — sin tocar los PNG en disco (solo afecta a las texturas en memoria y
        a anim width/height). Se usa UNA sola caja, unión de todas las poses,
        para que todas queden alineadas y del mismo tamaño (las poses se
        normalizan a este lienzo)."""
        try:
            from PIL import Image
        except Exception:  # noqa: BLE001
            return
        base = Path(base)
        # frames de la pose default (en la raíz) + todas las subcarpetas
        normals = sorted(base.glob("frame_*.png"))
        for sub in sorted(p for p in base.iterdir() if p.is_dir()):
            normals += sorted(sub.glob("frame_*.png"))
        if not normals:
            return
        box = None
        orig = None
        for p in normals:
            try:
                im = Image.open(str(p))
            except Exception:  # noqa: BLE001
                continue
            if orig is None:
                orig = im.size
            # solo cuentan los frames del lienzo dominante (mismo tamaño que
            # el primero); las poses generadas con otro lienzo se omiten aquí.
            if im.size != orig:
                continue
            b = im.convert("RGBA").getbbox()
            if b:
                box = b if box is None else (
                    min(box[0], b[0]), min(box[1], b[1]),
                    max(box[2], b[2]), max(box[3], b[3]))
        if not orig or not box:
            return
        ow, oh = orig
        pad = 2   # margen de seguridad para no comer el borde del dibujo
        x0 = max(0, box[0] - pad)
        y0 = max(0, box[1] - pad)
        x1 = min(ow, box[2] + pad)
        y1 = min(oh, box[3] + pad)
        cw, ch = x1 - x0, y1 - y0
        # solo recortar si el margen es apreciable (>4% en algún eje); si el
        # sprite ya está ajustado, no merece la pena el coste de re-rasterizar.
        if cw >= ow * 0.96 and ch >= oh * 0.96:
            return
        self._orig_size = orig
        self._crop_box = (x0, y0, x1, y1)
        self._base_size = (cw, ch)
        # propaga el tamaño real al resto de la lógica (input/colisión/bordes)
        self.anim["width"] = cw
        self.anim["height"] = ch

    def _load_texture(self, path):
        """Carga un PNG como textura, recortado al margen real (auto-recorte)
        y redimensionado al tamaño base si difiere (así todas las poses ocupan
        exactamente el mismo lienzo)."""
        target = self._base_size
        try:
            from PIL import Image
            im = Image.open(str(path))
            changed = False
            # recorte: a todo frame del lienzo dominante (raíz o subpose). Los
            # flip_*.png usan la caja espejada para alinearse con su normal.
            box = self._crop_box
            if box and im.size == self._orig_size:
                if Path(path).name.startswith("flip_"):
                    ow = self._orig_size[0]
                    box = (ow - box[2], box[1], ow - box[0], box[3])
                im = im.crop(box)
                changed = True
            if target is not None and im.size != tuple(target):
                im = im.convert("RGBA").resize(tuple(target), Image.NEAREST)
                changed = True
            if not changed:
                return Gdk.Texture.new_from_filename(str(path))
            im = im.convert("RGBA")
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
        # Mantener vivo el frame clock en modo CONTINUO. Sin esto, GTK solo
        # pide frames al compositor "bajo demanda" (tras un queue_draw); cuando
        # otra ventana pasa a pantalla completa, esa petición perezosa deja de
        # atenderse y la mascota se queda congelada aunque siga visible y la
        # lógica (timers) siga avanzando. Un tick callback persistente fuerza a
        # GTK a pedir un frame cada vsync, así la animación nunca se para.
        if self._tick_id is None:
            self._tick_id = self.add_tick_callback(self._keep_clock_alive)

    def _keep_clock_alive(self, widget, clock):
        # No hace falta lógica aquí: basta con existir para que el frame clock
        # siga en modo continuo y repinte las invalidaciones pendientes
        # (texturas nuevas y reposicionamientos) en el acto.
        return GLib.SOURCE_CONTINUE

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
            GLib.source_remove(self._anim_id)
            self._anim_id = None
        fps = max(1, int(self.anim.get("fps", 12)))
        interval = int(1000 / fps)
        self._anim_id = GLib.timeout_add(interval, self._anim_tick)

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
        self._paintable.set_scale_factor(scale)
        self.picture.queue_resize()
        self._overlay.queue_resize()
        self.queue_resize()
        if self.mode == "life":
            self._floor_y = max(0, self._screen_h - self._floor_offset_y - h)
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
        if self._tick_id is not None:
            self.remove_tick_callback(self._tick_id)
            self._tick_id = None
        self.destroy()
