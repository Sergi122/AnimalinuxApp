"""
Editor de píxeles — AnimaLinux (v3, disposición y atajos de Aseprite)

  ┌ menús ─────────────────────────────────────────────────────────────┐
  │ barra de contexto (opciones de la herramienta activa)              │
  ├─ paleta ──┬──────── lienzo (zoom hacia el cursor) ───────┬─ herram. ┤
  │ FG / BG   │                                              │          │
  │ selector  │                                              │          │
  ├───────────┴── línea de tiempo: capas × fotogramas ───────┴──────────┤
  └ estado ────────────────────────────────────────────────────────────┘

Atajos (como Aseprite):
  B lápiz · E borrador · G bote · Shift+G degradado · L línea · U rectángulo
  Shift+U elipse · D contorno · M marco · Q lazo · W varita · V mover
  I cuentagotas · H mano · Z zoom · X intercambiar colores
  Rueda = zoom · Espacio+arrastrar = mover vista · Clic derecho = color de fondo
  Alt+clic = cuentagotas · Shift+clic = línea recta · Enter = reproducir
"""
import re
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Gio

import cairo

from ..i18n import tr, N_
from .icons import icon_image
from .menubar import build_menubar
from .teardown import release_signals
from .pixel_canvas import PixelCanvas, MAX_FRAMES
from .pixel_widgets import ColorPicker, FgBg, PaletteGrid, Timeline
from ..ui import guide_widgets as gw

INK = "#1e1e1e"

PALETTE = [
    (0, 0, 0, 255), (30, 30, 30, 255), (70, 70, 70, 255), (120, 120, 120, 255),
    (180, 180, 180, 255), (255, 255, 255, 255), (180, 30, 30, 255), (220, 60, 40, 255),
    (230, 120, 40, 255), (240, 180, 40, 255), (220, 220, 50, 255), (160, 200, 50, 255),
    (60, 180, 60, 255), (30, 140, 80, 255), (20, 100, 70, 255), (40, 160, 140, 255),
    (50, 200, 180, 255), (80, 220, 210, 255), (50, 100, 200, 255), (30, 60, 180, 255),
    (20, 20, 140, 255), (80, 40, 180, 255), (140, 60, 200, 255), (200, 80, 200, 255),
    (220, 120, 180, 255), (255, 160, 200, 255), (255, 200, 220, 255), (120, 70, 30, 255),
    (160, 100, 50, 255), (200, 150, 100, 255), (255, 220, 180, 255), (220, 255, 200, 255),
    (200, 220, 255, 255), (255, 240, 150, 255), (150, 240, 255, 255), (240, 200, 255, 255),
    (80, 20, 20, 255), (20, 60, 20, 255), (20, 20, 80, 255), (60, 20, 80, 255),
    (80, 50, 10, 255), (10, 50, 60, 255), (255, 100, 100, 255), (100, 255, 100, 255),
    (100, 100, 255, 255), (255, 255, 100, 255), (100, 255, 255, 255), (255, 100, 255, 255),
    (0, 0, 0, 0),
]

# (id, icono, nombre, tecla)
TOOLS = [
    ("marquee",  "select",   N_("Marco rectangular (M)"), "M"),
    ("lasso",    "lasso",    N_("Lazo (Q)"), "Q"),
    ("wand",     "wand",     N_("Varita mágica (W)"), "W"),
    ("move",     "move",     N_("Mover selección o capa (V)"), "V"),
    ("pencil",   "pencil",   N_("Lápiz (B)"), "B"),
    ("eraser",   "eraser",   N_("Borrador (E)"), "E"),
    ("pick",     "pick",     N_("Cuentagotas (I) — Alt+clic con otra herramienta"), "I"),
    ("hand",     "hand",     N_("Mano (H) — o mantén Espacio"), "H"),
    ("zoom",     "zoom_in",  N_("Zoom (Z) — clic acerca, clic derecho aleja"), "Z"),
    ("fill",     "fill",     N_("Bote de pintura (G)"), "G"),
    ("gradient", "gradient", N_("Degradado (Shift+G)"), "Shift+G"),
    ("line",     "line",     N_("Línea (L) — Shift = ángulos de 45°"), "L"),
    ("rect",     "outline",  N_("Rectángulo (U) — Shift = cuadrado"), "U"),
    ("ellipse",  "ellipse",  N_("Elipse (Shift+U) — Shift = círculo"), "Shift+U"),
    ("contour",  "contour",  N_("Contorno libre (D)"), "D"),
]

KEY_TOOLS = {"m": "marquee", "q": "lasso", "w": "wand", "v": "move", "b": "pencil",
             "e": "eraser", "i": "pick", "h": "hand", "z": "zoom", "g": "fill",
             "l": "line", "u": "rect", "d": "contour"}
SHIFT_KEY_TOOLS = {"g": "gradient", "u": "ellipse"}

CTX = {
    "pencil":   ("brush", "ink", "opacity", "pp"),
    "eraser":   ("brush", "opacity", "pp"),
    "line":     ("brush", "ink", "opacity"),
    "rect":     ("brush", "ink", "opacity", "fill"),
    "ellipse":  ("brush", "ink", "opacity", "fill"),
    "contour":  ("brush", "ink", "opacity", "fill"),
    "fill":     ("opacity", "bucket"),
    "gradient": ("opacity", "grad"),
    "wand":     ("bucket", "selhint"),
    "marquee":  ("selhint",),
    "lasso":    ("selhint",),
    "move":     ("movehint",),
    "pick":     ("pickhint",),
    "hand":     (),
    "zoom":     ("zoomhint",),
}

INKS = [("simple", N_("Simple")), ("alpha", N_("Composición alfa")),
        ("lock_alpha", N_("Bloquear alfa")), ("dither", N_("Tramado"))]

CSS = """
window.ase, window.ase box { background-color: #7d929e; }
window.ase, window.ase label { color: #1e1e1e; }
window.ase .ase-menubar { background-color: #c6c6c6; border-bottom: 1px solid #3a4a52; padding: 0 2px; }
window.ase .ase-menubtn, window.ase .ase-menubtn > button { padding: 0; border: none; border-radius: 0; background: transparent; box-shadow: none; }
window.ase .ase-menubtn > button { padding: 3px 10px; min-height: 20px; }
window.ase .ase-menubtn > button label { color: #1e1e1e; }
window.ase .ase-menubtn > button:hover, window.ase .ase-menubtn > button:checked { background-color: #e8e8e8; border: none; }
popover.ase-pop, popover.ase-pop > arrow { background: transparent; box-shadow: none; border: none; }
popover.ase-pop > contents { background-color: #c6c6c6; color: #1e1e1e; border: 1px solid #3a4a52; border-radius: 2px; padding: 3px; }
popover.ase-pop modelbutton { color: #1e1e1e; padding: 4px 12px; min-height: 22px; border-radius: 0; }
popover.ase-pop modelbutton:hover { background-color: #7d929e; color: #ffffff; }
popover.ase-pop modelbutton label, popover.ase-pop modelbutton accelerator { color: inherit; }
popover.ase-pop separator { background-color: #9aa5aa; min-height: 1px; margin: 3px 0; }
window.ase .ase-ctx { background-color: #7d929e; border-bottom: 1px solid #3a4a52; padding: 3px 6px; min-height: 30px; }
window.ase .ase-left { background-color: #655561; padding: 6px; }
window.ase .ase-left label { color: #e8e2ea; }
window.ase .ase-right { background-color: #7d929e; padding: 3px; border-left: 1px solid #3a4a52; }
window.ase .ase-center { background-color: #655561; }
window.ase .ase-tl { background-color: #c6c6c6; border-top: 1px solid #3a4a52; }
window.ase .ase-tl box { background-color: #c6c6c6; }
window.ase .ase-status { background-color: #7d929e; border-top: 1px solid #3a4a52; padding: 2px 6px; }
window.ase button { background-image: none; background-color: #c6cfd3; border: 1px solid #3a4a52;
   border-radius: 2px; color: #1e1e1e; padding: 2px 6px; min-height: 20px; box-shadow: none; }
window.ase button:hover { background-color: #e4ecef; }
window.ase button:checked, window.ase button:active { background-color: #ffffff; border-color: #101820; }
window.ase button.ase-tool { padding: 3px; min-width: 26px; min-height: 26px; }
window.ase button.suggested-action { background-color: #4f7d9a; color: #fff; }
window.ase entry, window.ase spinbutton, window.ase spinbutton text {
   background-color: #f2f2f2; color: #1e1e1e; border-radius: 2px; min-height: 20px; }
window.ase entry text, window.ase text { color: #1e1e1e; background-color: transparent; }
window.ase entry text selection, window.ase text selection { background-color: #4f7d9a; color: #ffffff; }
window.ase entry placeholder, window.ase text placeholder { color: #6a7a82; }
window.ase .ase-hscroll, window.ase .ase-hscroll > viewport { background-color: transparent; }
window.ase spinbutton button { min-height: 18px; padding: 0 3px; }
window.ase dropdown button { min-height: 20px; }
window.ase separator { background-color: #3a4a52; min-width: 1px; }
window.ase checkbutton { color: #1e1e1e; }
window.ase scale trough { background-color: #3a4a52; min-height: 4px; }
window.ase scale slider { background-color: #f2f2f2; border: 1px solid #101820; min-width: 12px; min-height: 12px; }
window.ase scrolledwindow { background-color: #c6c6c6; }
window.ase .dim { color: #33434b; }
"""

_css_loaded = False


def _load_css():
    global _css_loaded
    if _css_loaded: return
    prov = Gtk.CssProvider()
    try:
        prov.load_from_string(CSS)
    except AttributeError:
        prov.load_from_data(CSS.encode())
    display = Gdk.Display.get_default()
    if display:
        Gtk.StyleContext.add_provider_for_display(
            display, prov, Gtk.STYLE_PROVIDER_PRIORITY_USER + 5)
        _css_loaded = True


def _hex(c):
    return "#%02x%02x%02x" % tuple(c[:3]) + ("" if c[3] == 255 else "%02x" % c[3])


def _parse_hex(t):
    t = t.strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", t): t += "ff"
    if not re.fullmatch(r"[0-9a-fA-F]{8}", t): return None
    return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4, 6))


class PixelEditor(Gtk.Window):
    def __init__(self, app, anim_id=None, pose=None, guided=False):
        super().__init__(application=app, title=tr("Editor de Píxeles — AnimaLinux"))
        self.app = app
        self.anim_id = anim_id
        self._guided = guided
        self._playing = False
        self._play_id = None
        self._prev_id = None
        self._prev_i = 0
        self._syncing = False
        self._status_id = None

        from ..ui import theme
        theme.apply(self)
        _load_css()
        self.add_css_class("ase")
        self.set_default_size(1180, 780)

        from .. import settings as _s
        saved = _s.get("pixel_palette", None)
        self.palette = [tuple(c) for c in saved] if saved else list(PALETTE)

        self.canvas = PixelCanvas(64, 64)
        cv = self.canvas
        cv.on_pick = self._on_pick
        cv.on_frame_changed = self._sync
        cv.on_layers_changed = self._sync
        cv.on_cursor_moved = self._on_cursor
        cv.on_zoom_changed = self._on_zoom
        cv.on_status = self._flash
        cv.on_tool_request = self._select_tool

        self._build_actions()
        self._build_ui()
        self.connect("close-request", self._on_close_request)

        if pose:
            self.pose_entry.set_text(pose)
        elif guided:
            self._suggest_next_pose()

        if anim_id is not None and pose in (None, "default"):
            fd = app.library.frames_dir(anim_id)
            if cv.load_from_dir(fd):
                self._sync()

        if anim_id is None:
            GLib.idle_add(self._ask_canvas_size)
        else:
            GLib.idle_add(self._show_tutorial)

    # ══ acciones y menús ══════════════════════════════════════════════════════
    def _build_actions(self):
        self._grp = Gio.SimpleActionGroup()
        self.insert_action_group("ed", self._grp)
        c = self.canvas

        def act(name, cb, state=None, ptype=None):
            if state is None:
                a = Gio.SimpleAction.new(name, None)
                a.connect("activate", lambda *_: cb())
            elif ptype is None:
                a = Gio.SimpleAction.new_stateful(name, None, GLib.Variant.new_boolean(state))
                a.connect("change-state", lambda act_, v: (act_.set_state(v), cb(v.get_boolean())))
            else:
                a = Gio.SimpleAction.new_stateful(
                    name, GLib.VariantType.new("s"), GLib.Variant.new_string(state))
                a.connect("change-state", lambda act_, v: (act_.set_state(v), cb(v.get_string())))
            self._grp.add_action(a)
            return a

        # archivo
        act("save", self._save_pose)
        act("import", lambda: self._on_import(None))
        act("gif", self._export_gif_dialog)
        act("close", self._confirm_close)
        # editar
        act("undo", c.undo); act("redo", c.redo)
        act("cut", lambda: c.copy_selection(cut=True))
        act("copy", c.copy_selection); act("paste", c.paste_selection)
        act("clear", c.clear_selection_pixels)
        act("select_all", c.select_all); act("deselect", c.deselect)
        act("invert_sel", c.invert_selection)
        act("flip_cel_h", lambda: c.flip_cel(True)); act("flip_cel_v", lambda: c.flip_cel(False))
        act("outline", c.outline_fx)
        # sprite
        act("canvas_size", self._dlg_canvas_size); act("resize", self._dlg_resize)
        act("crop", c.crop_to_selection)
        act("flip_h", lambda: c.flip_sprite(True)); act("flip_v", lambda: c.flip_sprite(False))
        act("rot_cw", lambda: c.rotate_sprite(90)); act("rot_ccw", lambda: c.rotate_sprite(-90))
        act("rot_180", lambda: c.rotate_sprite(180))
        # capa
        act("layer_new", c.add_layer); act("layer_dup", c.duplicate_layer)
        act("layer_del", c.delete_layer); act("layer_up", lambda: c.move_layer(1))
        act("layer_down", lambda: c.move_layer(-1)); act("layer_merge", c.merge_down)
        act("layer_props", lambda: self._dlg_layer(c._layer))
        # fotograma
        act("frame_new", c.duplicate_frame); act("frame_empty", c.new_frame)
        act("frame_del", c.delete_frame)
        act("frame_left", lambda: c.move_frame(-1)); act("frame_right", lambda: c.move_frame(1))
        act("frame_copy", c.copy_frame); act("frame_paste", c.paste_frame)
        act("play", lambda: self.play_btn.set_active(not self.play_btn.get_active()))
        # vista
        act("zoom_in", c.zoom_in); act("zoom_out", c.zoom_out); act("fit", c.zoom_fit)
        act("zoom_100", lambda: c.zoom_to(1))
        self._a_grid = act("grid", self._set_grid, state=False)
        self._a_grid_n = act("grid_n", self._set_grid_n, state="0", ptype="s")
        self._a_sym = act("sym", self._set_sym, state="none", ptype="s")
        self._a_tile = act("tile", self._set_tile, state="none", ptype="s")
        self._a_onion_p = act("onion_prev", lambda v: self._set_onion("prev", v), state=False)
        self._a_onion_n = act("onion_next", lambda v: self._set_onion("next", v), state=False)
        self._a_preview = act("preview", self._set_preview, state=False)
        # ayuda
        act("help", lambda: self._show_tutorial(force=True))

    @staticmethod
    def _item(label, action, accel=None, target=None):
        it = Gio.MenuItem.new(label, None)
        if target is None: it.set_detailed_action(action)
        else: it.set_action_and_target_value(action, GLib.Variant.new_string(target))
        if accel: it.set_attribute_value("accel", GLib.Variant.new_string(accel))
        return it

    def _build_menu(self):
        I = self._item

        def sect(*items):
            m = Gio.Menu()
            for it in items: m.append_item(it)
            return m

        def menu(*sections):
            m = Gio.Menu()
            for s in sections: m.append_section(None, s)
            return m

        archivo = menu(
            sect(I(tr("Guardar pose"), "ed.save", "<Control>s"), I(tr("Importar imagen…"), "ed.import"),
                 I(tr("Exportar como GIF…"), "ed.gif")),
            sect(I(tr("Cerrar el editor"), "ed.close", "<Control>w")))
        editar = menu(
            sect(I(tr("Deshacer"), "ed.undo", "<Control>z"), I(tr("Rehacer"), "ed.redo", "<Control>y")),
            sect(I(tr("Cortar"), "ed.cut", "<Control>x"), I(tr("Copiar"), "ed.copy", "<Control>c"),
                 I(tr("Pegar"), "ed.paste", "<Control>v"), I(tr("Borrar"), "ed.clear", "Delete")),
            sect(I(tr("Seleccionar todo"), "ed.select_all", "<Control>a"),
                 I(tr("Deseleccionar"), "ed.deselect", "<Control>d"),
                 I(tr("Invertir selección"), "ed.invert_sel", "<Control><Shift>i")),
            sect(I(tr("Voltear horizontal (selección/capa)"), "ed.flip_cel_h"),
                 I(tr("Voltear vertical (selección/capa)"), "ed.flip_cel_v"),
                 I(tr("Contorno con el color principal"), "ed.outline")))
        sprite = menu(
            sect(I(tr("Tamaño del lienzo…"), "ed.canvas_size"), I(tr("Redimensionar sprite…"), "ed.resize"),
                 I(tr("Recortar a la selección"), "ed.crop")),
            sect(I(tr("Voltear lienzo horizontal"), "ed.flip_h"), I(tr("Voltear lienzo vertical"), "ed.flip_v")),
            sect(I(tr("Rotar 90° horario"), "ed.rot_cw"), I(tr("Rotar 90° antihorario"), "ed.rot_ccw"),
                 I(tr("Rotar 180°"), "ed.rot_180")))
        capa = menu(
            sect(I(tr("Nueva capa"), "ed.layer_new", "<Shift>n"), I(tr("Duplicar capa"), "ed.layer_dup"),
                 I(tr("Borrar capa"), "ed.layer_del")),
            sect(I(tr("Subir capa"), "ed.layer_up"), I(tr("Bajar capa"), "ed.layer_down"),
                 I(tr("Unir con la de abajo"), "ed.layer_merge")),
            sect(I(tr("Propiedades de la capa…"), "ed.layer_props")))
        frame = menu(
            sect(I(tr("Nuevo fotograma (copia el actual)"), "ed.frame_new", "<Alt>n"),
                 I(tr("Nuevo fotograma vacío"), "ed.frame_empty"),
                 I(tr("Borrar fotograma"), "ed.frame_del")),
            sect(I(tr("Mover a la izquierda"), "ed.frame_left"), I(tr("Mover a la derecha"), "ed.frame_right")),
            sect(I(tr("Copiar fotograma"), "ed.frame_copy"), I(tr("Pegar fotograma"), "ed.frame_paste")),
            sect(I(tr("Reproducir / pausar"), "ed.play", "Return")))

        sym = sect(I(tr("Sin simetría"), "ed.sym", target="none"),
                   I(tr("Simetría horizontal"), "ed.sym", target="h"),
                   I(tr("Simetría vertical"), "ed.sym", target="v"),
                   I(tr("Simetría H + V"), "ed.sym", target="hv"))
        tile = sect(I(tr("Sin mosaico"), "ed.tile", target="none"), I(tr("Mosaico en X"), "ed.tile", target="x"),
                    I(tr("Mosaico en Y"), "ed.tile", target="y"), I(tr("Mosaico X + Y"), "ed.tile", target="xy"))
        gridn = sect(I(tr("Sin cuadrícula"), "ed.grid_n", target="0"), I(tr("Cuadrícula 8×8"), "ed.grid_n", target="8"),
                     I(tr("Cuadrícula 16×16"), "ed.grid_n", target="16"),
                     I(tr("Cuadrícula 32×32"), "ed.grid_n", target="32"))
        vista = menu(
            sect(I(tr("Acercar"), "ed.zoom_in", "plus"), I(tr("Alejar"), "ed.zoom_out", "minus"),
                 I(tr("Ajustar a la ventana"), "ed.fit", "<Control>0"), I(tr("Tamaño real (100%)"), "ed.zoom_100", "1")),
            sect(I(tr("Cuadrícula de píxeles"), "ed.grid", "<Control>apostrophe")),
            gridn, sym, tile,
            sect(I(tr("Papel cebolla: anterior"), "ed.onion_prev"), I(tr("Papel cebolla: siguiente"), "ed.onion_next"),
                 I(tr("Ventana de vista previa"), "ed.preview")))
        ayuda = menu(sect(I(tr("Guía rápida y atajos"), "ed.help", "F1")))

        top = Gio.Menu()
        for name, m in ((tr("Archivo"), archivo), (tr("Editar"), editar), (tr("Sprite"), sprite),
                        (tr("Capa"), capa), (tr("Fotograma"), frame), (tr("Vista"), vista), (tr("Ayuda"), ayuda)):
            top.append_submenu(name, m)
        return build_menubar(top, "ase-menubtn", "ase-pop")

    # ══ interfaz ══════════════════════════════════════════════════════════════
    @staticmethod
    def _hscroll(widget):
        """Barra que se desplaza en horizontal si la ventana es estrecha (así la
        caja de herramientas nunca queda fuera de pantalla)."""
        sc = Gtk.ScrolledWindow()
        sc.add_css_class("ase-hscroll")
        sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        sc.set_propagate_natural_height(True)
        sc.set_min_content_width(50)
        sc.set_child(widget)
        return sc

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(root)

        top = Gtk.Box(); top.add_css_class("ase-menubar")
        top.append(self._build_menu())
        self.title_lbl = Gtk.Label(label=tr("Sin título")); self.title_lbl.set_hexpand(True)
        self.title_lbl.add_css_class("dim")
        top.append(self.title_lbl)
        help_b = Gtk.Button(label="?"); help_b.set_tooltip_text(tr("Guía rápida (F1)"))
        help_b.connect("clicked", lambda _: self._show_tutorial(force=True))
        close_b = Gtk.Button(); close_b.set_child(icon_image("close", 14, INK))
        close_b.set_tooltip_text(tr("Cerrar el editor (Ctrl+W)"))
        close_b.connect("clicked", lambda _: self._confirm_close())
        top.append(help_b); top.append(close_b)
        root.append(top)

        root.append(self._hscroll(self._build_context_bar()))

        body = Gtk.Box(); body.set_vexpand(True); root.append(body)
        body.append(self._build_left())

        overlay = Gtk.Overlay(); overlay.set_hexpand(True); overlay.set_vexpand(True)
        overlay.add_css_class("ase-center")
        overlay.set_child(self.canvas)
        self.preview = Gtk.DrawingArea()
        self.preview.set_content_width(112); self.preview.set_content_height(112)
        self.preview.set_halign(Gtk.Align.END); self.preview.set_valign(Gtk.Align.END)
        self.preview.set_margin_end(14); self.preview.set_margin_bottom(14)
        self.preview.set_draw_func(self._draw_preview)
        self.preview.set_visible(False)
        overlay.add_overlay(self.preview)
        body.append(overlay)
        body.append(self._build_toolbar())

        root.append(self._build_timeline())
        root.append(self._hscroll(self._build_status()))

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        key.connect("key-released", self._on_key_up)
        self.add_controller(key)
        self._select_tool("pencil")
        self._set_fg(self.canvas.color); self._set_bg(self.canvas.color2)

    # ── barra de contexto ────────────────────────────────────────────────────
    def _build_context_bar(self):
        c = self.canvas
        bar = Gtk.Box(spacing=8); bar.add_css_class("ase-ctx")
        self._ctx = {}

        def section(name):
            b = Gtk.Box(spacing=6); self._ctx[name] = b; bar.append(b); return b

        def lbl(t): return Gtk.Label(label=t)

        s = section("brush")
        s.append(lbl(tr("Tamaño")))
        size = Gtk.SpinButton.new_with_range(1, 64, 1); size.set_value(1)
        size.connect("value-changed", lambda w: (setattr(c, "brush", int(w.get_value())), c.queue_draw()))
        self.brush_spin = size; s.append(size)
        sq = Gtk.ToggleButton(); sq.set_child(icon_image("outline", 14, INK)); sq.set_tooltip_text(tr("Pincel cuadrado"))
        ci = Gtk.ToggleButton(); ci.set_child(icon_image("ellipse", 14, INK)); ci.set_tooltip_text(tr("Pincel redondo"))
        ci.set_group(sq); sq.set_active(True)
        sq.connect("toggled", lambda b: b.get_active() and (setattr(c, "brush_shape", "square"), c.queue_draw()))
        ci.connect("toggled", lambda b: b.get_active() and (setattr(c, "brush_shape", "circle"), c.queue_draw()))
        s.append(sq); s.append(ci)

        s = section("pp")
        pp = Gtk.CheckButton(label=tr("Pixel-perfect"))
        pp.set_tooltip_text(tr("Quita los píxeles en 'L' de los trazos a mano alzada"))
        pp.connect("toggled", lambda w: setattr(c, "pixel_perfect", w.get_active()))
        s.append(pp)

        s = section("ink")
        s.append(lbl(tr("Tinta")))
        dd = Gtk.DropDown.new_from_strings([tr(n) for _, n in INKS])
        dd.connect("notify::selected", lambda w, _p: setattr(c, "ink", INKS[w.get_selected()][0]))
        s.append(dd)

        s = section("opacity")
        s.append(lbl(tr("Opacidad")))
        op = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 255, 1)
        op.set_value(255); op.set_size_request(110, -1); op.set_draw_value(True)
        op.set_value_pos(Gtk.PositionType.RIGHT)
        op.connect("value-changed", lambda w: setattr(c, "opacity", int(w.get_value())))
        s.append(op)

        s = section("fill")
        f = Gtk.CheckButton(label=tr("Rellenar")); f.connect("toggled", lambda w: setattr(c, "shape_fill", w.get_active()))
        s.append(f)

        s = section("bucket")
        s.append(lbl(tr("Tolerancia")))
        tol = Gtk.SpinButton.new_with_range(0, 255, 4); tol.set_value(0)
        tol.connect("value-changed", lambda w: setattr(c, "tol", int(w.get_value())))
        s.append(tol)
        cont = Gtk.CheckButton(label=tr("Contiguo")); cont.set_active(True)
        cont.connect("toggled", lambda w: setattr(c, "contiguous", w.get_active()))
        c8 = Gtk.CheckButton(label=tr("8 vecinos"))
        c8.connect("toggled", lambda w: setattr(c, "conn8", w.get_active()))
        s.append(cont); s.append(c8)

        s = section("grad")
        kd = Gtk.DropDown.new_from_strings([tr("Lineal"), tr("Radial")])
        kd.connect("notify::selected", lambda w, _p: setattr(c, "grad_kind", ("linear", "radial")[w.get_selected()]))
        gd = Gtk.CheckButton(label=tr("Tramado Bayer"))
        gd.connect("toggled", lambda w: setattr(c, "grad_dither", w.get_active()))
        s.append(kd); s.append(gd)

        for name, text in (("selhint", tr("Shift: añadir a la selección · Alt: restar")),
                           ("movehint", tr("Arrastra para mover · Ctrl+flechas: 1 px")),
                           ("pickhint", tr("Clic izq.: color principal · Clic der.: fondo")),
                           ("zoomhint", tr("Clic: acercar · Clic derecho/Alt: alejar"))):
            s = section(name); l = Gtk.Label(label=text); l.add_css_class("dim"); s.append(l)

        spacer = Gtk.Box(); spacer.set_hexpand(True); bar.append(spacer)

        sym_box = Gtk.Box(spacing=2)
        self._sym_btns = {}
        first = None
        for val, ic, tip in (("none", "sym_none", tr("Sin simetría")), ("h", "sym_h", tr("Simetría horizontal")),
                             ("v", "sym_v", tr("Simetría vertical")), ("hv", "sym_hv", tr("Simetría H+V"))):
            b = Gtk.ToggleButton(); b.set_child(icon_image(ic, 14, INK)); b.set_tooltip_text(tip)
            if first is None: first = b
            else: b.set_group(first)
            b.connect("toggled", lambda w, v=val: w.get_active() and self._a_sym.change_state(GLib.Variant.new_string(v)))
            self._sym_btns[val] = b; sym_box.append(b)
        self._sym_btns["none"].set_active(True)
        bar.append(sym_box)
        for ic, tip, cb in (("grid", tr("Cuadrícula de píxeles"),
                             lambda w: self._a_grid.change_state(GLib.Variant.new_boolean(w.get_active()))),
                            ("preview", tr("Ventana de vista previa"),
                             lambda w: self._a_preview.change_state(GLib.Variant.new_boolean(w.get_active())))):
            b = Gtk.ToggleButton(); b.set_child(icon_image(ic, 14, INK)); b.set_tooltip_text(tip)
            b.connect("toggled", cb); bar.append(b)
            setattr(self, f"_gb_{ic}", b)
        return bar

    def _ctx_update(self):
        show = CTX.get(self.canvas.tool, ())
        for name, box in self._ctx.items():
            box.set_visible(name in show)

    # ── paleta / color ───────────────────────────────────────────────────────
    def _build_left(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("ase-left")
        box.set_size_request(150 + 16, -1)

        self.pal = PaletteGrid(self.palette, self._on_palette_pick)
        box.append(self.pal)

        row = Gtk.Box(spacing=3)
        add = Gtk.Button(label="+"); add.set_tooltip_text(tr("Añadir el color principal a la paleta"))
        add.connect("clicked", lambda _: self._pal_add())
        rem = Gtk.Button(label="−"); rem.set_tooltip_text(tr("Quitar de la paleta el color seleccionado"))
        rem.connect("clicked", lambda _: self._pal_remove())
        rst = Gtk.Button(); rst.set_child(icon_image("reset", 12, INK)); rst.set_tooltip_text(tr("Restaurar paleta por defecto"))
        rst.connect("clicked", lambda _: self._pal_reset())
        for b in (add, rem, rst): row.append(b)
        box.append(row)

        box.append(Gtk.Separator())
        sw = Gtk.Box(spacing=6)
        self.fgbg = FgBg(on_swap=self._swap_colors)
        sw.append(self.fgbg)
        ent = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.fg_entry = Gtk.Entry(); self.fg_entry.set_width_chars(9); self.fg_entry.set_max_width_chars(9)
        self.bg_entry = Gtk.Entry(); self.bg_entry.set_width_chars(9); self.bg_entry.set_max_width_chars(9)
        self.fg_entry.connect("activate", lambda e: self._entry_color(e, False))
        self.bg_entry.connect("activate", lambda e: self._entry_color(e, True))
        self.fg_entry.set_tooltip_text(tr("Color principal (#rrggbb o #rrggbbaa)"))
        self.bg_entry.set_tooltip_text(tr("Color de fondo"))
        ent.append(self.fg_entry); ent.append(self.bg_entry); sw.append(ent)
        box.append(sw)

        self.picker = ColorPicker(self._on_picker)
        box.append(self.picker)
        spacer = Gtk.Box(); spacer.set_vexpand(True); box.append(spacer)
        return box

    def _on_palette_pick(self, color, right):
        (self._set_bg if right else self._set_fg)(color)

    def _pal_add(self):
        c = self.canvas.color
        if c not in self.palette: self.palette.append(c)
        self._pal_changed()

    def _pal_remove(self):
        i = self.pal.sel
        if 0 <= i < len(self.palette) and len(self.palette) > 1:
            self.palette.pop(i); self.pal.sel = -1
            self._pal_changed()

    def _pal_reset(self):
        self.palette[:] = PALETTE; self.pal.sel = -1; self._pal_changed()

    def _pal_changed(self):
        self.pal.set_colors(self.palette)
        from .. import settings as _s
        _s.set_val("pixel_palette", [list(c) for c in self.palette])

    def _entry_color(self, entry, bg):
        c = _parse_hex(entry.get_text())
        if c: (self._set_bg if bg else self._set_fg)(c)

    def _set_fg(self, c):
        c = tuple(c); self.canvas.color = c
        self.fg_entry.set_text(_hex(c)); self.fgbg.set_colors(c, self.canvas.color2)
        self.picker.set_rgba(c)

    def _set_bg(self, c):
        c = tuple(c); self.canvas.color2 = c
        self.bg_entry.set_text(_hex(c)); self.fgbg.set_colors(self.canvas.color, c)

    def _on_picker(self, c):
        self.canvas.color = tuple(c)
        self.fg_entry.set_text(_hex(c)); self.fgbg.set_colors(tuple(c), self.canvas.color2)

    def _swap_colors(self):
        a, b = self.canvas.color, self.canvas.color2
        self._set_fg(b); self._set_bg(a)

    def _on_pick(self, color, right):
        (self._set_bg if right else self._set_fg)(color)

    # ── caja de herramientas ─────────────────────────────────────────────────
    def _build_toolbar(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.add_css_class("ase-right")
        self._tool_btns = {}
        first = None
        for tid, ic, tip, _k in TOOLS:
            b = Gtk.ToggleButton(); b.add_css_class("ase-tool")
            b.set_child(icon_image(ic, 18, INK)); b.set_tooltip_text(tr(tip))
            b.set_focus_on_click(False)
            if first is None: first = b
            else: b.set_group(first)
            b.connect("toggled", lambda w, t=tid: w.get_active() and self._on_tool(t))
            self._tool_btns[tid] = b; col.append(b)
        return col

    def _on_tool(self, tid):
        self.canvas.set_tool(tid); self._ctx_update()

    def _select_tool(self, tid):
        b = self._tool_btns.get(tid)
        if b is not None: b.set_active(True)
        self._on_tool(tid)

    # ── línea de tiempo ──────────────────────────────────────────────────────
    def _build_timeline(self):
        c = self.canvas
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); box.add_css_class("ase-tl")
        bar = Gtk.Box(spacing=3)
        bar.set_margin_start(6); bar.set_margin_end(6); bar.set_margin_top(4); bar.set_margin_bottom(3)

        def btn(icon, tip, cb, toggle=False):
            b = Gtk.ToggleButton() if toggle else Gtk.Button()
            b.set_child(icon_image(icon, 14, INK)); b.set_tooltip_text(tip); b.set_focus_on_click(False)
            if toggle: b.connect("toggled", lambda w: cb(w))
            else: b.connect("clicked", lambda w: cb())
            bar.append(b); return b

        btn("first", tr("Primer fotograma (Inicio)"), lambda: c.go_to(0))
        btn("prev", tr("Fotograma anterior (←)"), lambda: c.go_to(c._cur - 1))
        self.play_btn = btn("play", tr("Reproducir (Enter)"), self._on_play_toggle, toggle=True)
        btn("next", tr("Fotograma siguiente (→)"), lambda: c.go_to(c._cur + 1))
        btn("last", tr("Último fotograma (Fin)"), lambda: c.go_to(c.frame_count - 1))
        bar.append(Gtk.Separator())
        bar.append(Gtk.Label(label="FPS"))
        self.fps_spin = Gtk.SpinButton.new_with_range(1, 60, 1); self.fps_spin.set_value(12)
        self.fps_spin.connect("activate", lambda w: self.canvas.grab_focus())
        bar.append(self.fps_spin)
        bar.append(Gtk.Separator())
        btn("add", tr("Nueva capa (Shift+N)"), c.add_layer)
        btn("duplicate", tr("Duplicar capa"), c.duplicate_layer)
        btn("up", tr("Subir capa"), lambda: c.move_layer(1))
        btn("down", tr("Bajar capa"), lambda: c.move_layer(-1))
        btn("merge", tr("Unir con la de abajo"), c.merge_down)
        btn("trash", tr("Borrar capa"), c.delete_layer)
        bar.append(Gtk.Separator())
        btn("layers", tr("Nuevo fotograma (Alt+N, copia el actual)"), c.duplicate_frame)
        btn("trash", tr("Borrar fotograma"), c.delete_frame)
        bar.append(Gtk.Separator())
        self.onion_p = btn("onion", tr("Papel cebolla: anterior"),
                           lambda w: self._a_onion_p.change_state(GLib.Variant.new_boolean(w.get_active())), toggle=True)
        self.onion_n = btn("next", tr("Papel cebolla: siguiente"),
                           lambda w: self._a_onion_n.change_state(GLib.Variant.new_boolean(w.get_active())), toggle=True)
        gif = Gtk.Button(); gif.set_child(icon_image("gif", 14, INK)); gif.set_tooltip_text(tr("Exportar GIF"))
        gif.set_hexpand(True); gif.set_halign(Gtk.Align.END)
        gif.connect("clicked", lambda _: self._export_gif_dialog())
        bar.append(gif)
        box.append(self._hscroll(bar))

        self.timeline = Timeline(c, on_rename=self._dlg_layer)
        sc = Gtk.ScrolledWindow(); sc.set_child(self.timeline)
        sc.set_min_content_height(112); sc.set_max_content_height(190)
        sc.set_propagate_natural_height(True)
        box.append(sc)
        return box

    # ── barra de estado ──────────────────────────────────────────────────────
    def _build_status(self):
        bar = Gtk.Box(spacing=8); bar.add_css_class("ase-status")
        self.cursor_lbl = Gtk.Label(label="X:—  Y:—"); self.cursor_lbl.set_size_request(92, -1)
        self.cursor_lbl.set_xalign(0); bar.append(self.cursor_lbl)
        self.px_color_lbl = Gtk.Label(label=""); self.px_color_lbl.set_xalign(0)
        self.px_color_lbl.set_hexpand(True); bar.append(self.px_color_lbl)
        self.save_status = Gtk.Label(label=""); self.save_status.add_css_class("dim"); bar.append(self.save_status)
        self.size_lbl = Gtk.Label(label="64 × 64"); bar.append(self.size_lbl)
        bar.append(Gtk.Separator())

        if self.anim_id is None:
            bar.append(Gtk.Label(label=tr("Nombre")))
            self.name_entry = Gtk.Entry(); self.name_entry.set_placeholder_text(tr("Mi mascota"))
            self.name_entry.set_width_chars(12); bar.append(self.name_entry)
        else:
            self.name_entry = None
        bar.append(Gtk.Label(label=tr("Pose")))
        self.pose_entry = Gtk.Entry(); self.pose_entry.set_text("default"); self.pose_entry.set_width_chars(8)
        self.pose_entry.connect("activate", lambda w: self.canvas.grab_focus())
        bar.append(self.pose_entry)
        save = Gtk.Button(); save.add_css_class("suggested-action")
        sb = Gtk.Box(spacing=4); sb.append(icon_image("save", 14, "#ffffff")); sb.append(Gtk.Label(label=tr("Guardar pose")))
        save.set_child(sb); save.connect("clicked", lambda _: self._save_pose())
        bar.append(save)
        bar.append(Gtk.Separator())

        bar.append(Gtk.Label(label=tr("Fotograma")))
        self.frame_spin = Gtk.SpinButton.new_with_range(1, MAX_FRAMES, 1)
        self.frame_spin.connect("value-changed", self._on_frame_spin)
        self.frame_spin.connect("activate", lambda w: self.canvas.grab_focus())
        bar.append(self.frame_spin)
        new = Gtk.Button(label="+"); new.set_tooltip_text(tr("Nuevo fotograma (Alt+N)"))
        new.connect("clicked", lambda _: self.canvas.duplicate_frame()); bar.append(new)
        self.zoom_lbl = Gtk.Label(label="800%"); self.zoom_lbl.set_size_request(48, -1); bar.append(self.zoom_lbl)
        return bar

    # ══ estado / sincronización ═══════════════════════════════════════════════
    def _sync(self):
        c = self.canvas
        self._syncing = True
        try:
            self.timeline.refresh()
            self.frame_spin.set_range(1, max(1, c.frame_count))
            self.frame_spin.set_value(c._cur + 1)
            self.size_lbl.set_text(f"{c.cw} × {c.ch}")
            pose = self.pose_entry.get_text() if hasattr(self, "pose_entry") else ""
            self.title_lbl.set_text(tr("{pose} · {name} · fotograma {x2}/{frame_count}", pose=pose, name=c.layer.name, x2=c._cur + 1, frame_count=c.frame_count))
        finally:
            self._syncing = False
        self.preview.queue_draw()

    def _on_frame_spin(self, spin):
        if self._syncing: return
        self.canvas.go_to(int(spin.get_value()) - 1)

    def _on_zoom(self):
        self.zoom_lbl.set_text(tr("{x0}%", x0=self.canvas.zoom * 100))

    def _on_cursor(self, cx, cy, px):
        self.cursor_lbl.set_text(f"X:{cx:3d}  Y:{cy:3d}")
        if px is not None:
            self.px_color_lbl.set_text(f"#{px[0]:02x}{px[1]:02x}{px[2]:02x}  α{px[3]}")
        else:
            self.px_color_lbl.set_text("")

    def _flash(self, msg):
        self.save_status.set_text(msg)
        if self._status_id: GLib.source_remove(self._status_id)
        self._status_id = GLib.timeout_add(3500, self._clear_flash)

    def _clear_flash(self):
        self.save_status.set_text(""); self._status_id = None; return False

    # ── vista: acciones con estado ───────────────────────────────────────────
    def _set_grid(self, on):
        self.canvas.show_grid = on; self.canvas.queue_draw()
        if self._gb_grid.get_active() != on: self._gb_grid.set_active(on)

    def _set_grid_n(self, v):
        self.canvas.grid_size = int(v); self.canvas.queue_draw()

    def _set_sym(self, v):
        self.canvas.symmetry = v; self.canvas.queue_draw()
        b = self._sym_btns.get(v)
        if b is not None and not b.get_active(): b.set_active(True)

    def _set_tile(self, v):
        self.canvas.tiled = v; self.canvas.queue_draw()

    def _set_onion(self, which, on):
        setattr(self.canvas, "onion_" + which, on); self.canvas.queue_draw()
        btn = self.onion_p if which == "prev" else self.onion_n
        if btn.get_active() != on: btn.set_active(on)

    # ── vista previa animada ─────────────────────────────────────────────────
    def _set_preview(self, on):
        self.preview.set_visible(on)
        if self._gb_preview.get_active() != on: self._gb_preview.set_active(on)
        if on and not self._prev_id:
            self._prev_i = 0
            self._prev_id = GLib.timeout_add(max(40, 1000 // int(self.fps_spin.get_value())), self._prev_tick)

    def _prev_tick(self):
        if not self.preview.get_visible():
            self._prev_id = None; return False
        n = self.canvas.frame_count
        self._prev_i = (self._prev_i + 1) % n if n > 1 else 0
        self.preview.queue_draw()
        self._prev_id = GLib.timeout_add(max(40, 1000 // int(self.fps_spin.get_value())), self._prev_tick)
        return False

    def _draw_preview(self, area, cr, w, h):
        c = self.canvas
        cr.set_source_rgba(0.13, 0.11, 0.14, 0.92); cr.rectangle(0, 0, w, h); cr.fill()
        i = min(self._prev_i, c.frame_count - 1)
        im = c.flatten(i)
        s = min((w - 12) / c.cw, (h - 12) / c.ch)
        s = max(1, int(s)) if s >= 1 else s
        data = bytearray(im.tobytes("raw", "BGRa"))
        surf = cairo.ImageSurface.create_for_data(data, cairo.Format.ARGB32, c.cw, c.ch, c.cw * 4)
        cr.save(); cr.translate((w - c.cw * s) / 2, (h - c.ch * s) / 2); cr.scale(s, s)
        pat = cairo.SurfacePattern(surf); pat.set_filter(cairo.Filter.NEAREST)
        cr.set_source(pat); cr.paint(); cr.restore()

    # ── reproducción ─────────────────────────────────────────────────────────
    def _on_play_toggle(self, btn):
        self._playing = btn.get_active()
        if self._playing:
            self._play_id = GLib.timeout_add(max(16, 1000 // int(self.fps_spin.get_value())), self._tick)
        elif self._play_id:
            GLib.source_remove(self._play_id); self._play_id = None

    def _tick(self):
        if not self._playing: return False
        self.canvas.go_to((self.canvas._cur + 1) % self.canvas.frame_count)
        self._play_id = GLib.timeout_add(max(16, 1000 // int(self.fps_spin.get_value())), self._tick)
        return False

    # ══ teclado ═══════════════════════════════════════════════════════════════
    def _typing(self):
        f = self.get_focus()
        return isinstance(f, (Gtk.Editable, Gtk.SpinButton))

    def _on_key_up(self, ctrl, keyval, keycode, mods):
        if (Gdk.keyval_name(keyval) or "") == "space":
            self.canvas.set_space(False)

    def _on_key(self, ctrl, keyval, keycode, mods):
        if self._typing(): return False
        c = self.canvas
        key = (Gdk.keyval_name(keyval) or "")
        low = key.lower()
        ctrl_h = bool(mods & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(mods & Gdk.ModifierType.SHIFT_MASK)
        alt = bool(mods & Gdk.ModifierType.ALT_MASK)

        if key == "space":
            c.set_space(True); return True
        if ctrl_h:
            if low == "z":
                (c.redo() if shift else c.undo()); return True
            if low == "y": c.redo(); return True
            if low == "s": self._save_pose(); return True
            if low == "w": self._confirm_close(); return True
            if low == "a": c.select_all(); return True
            if low == "d": c.deselect(); return True
            if low == "c": c.copy_selection(); return True
            if low == "x": c.copy_selection(cut=True); return True
            if low == "v": c.paste_selection(); return True
            if low == "i" and shift: c.invert_selection(); return True
            if key == "0": c.zoom_fit(); return True
            arrows = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}
            if key in arrows: c.nudge(*arrows[key]); return True
            return False
        if alt:
            if low == "n": c.duplicate_frame(); return True
            return False
        if key == "F1": self._show_tutorial(force=True); return True
        if key in ("Return", "KP_Enter"):
            self.play_btn.set_active(not self.play_btn.get_active()); return True
        if key in ("Left", "comma"): c.go_to(c._cur - 1); return True
        if key in ("Right", "period"): c.go_to(c._cur + 1); return True
        if key == "Home": c.go_to(0); return True
        if key == "End": c.go_to(c.frame_count - 1); return True
        if key in ("Delete", "BackSpace"): c.clear_selection_pixels(); return True
        if key in ("plus", "equal", "KP_Add"): c.zoom_in(); return True
        if key in ("minus", "KP_Subtract"): c.zoom_out(); return True
        if len(key) == 1 and key in "123456": c.zoom_to(2 ** (int(key) - 1)); return True
        if key == "bracketleft": self.brush_spin.set_value(max(1, c.brush - 1)); return True
        if key == "bracketright": self.brush_spin.set_value(min(64, c.brush + 1)); return True
        if low == "n" and shift: c.add_layer(); return True
        if low == "x" and not shift: self._swap_colors(); return True
        if low in KEY_TOOLS:
            tool = SHIFT_KEY_TOOLS.get(low) if shift else KEY_TOOLS[low]
            if tool: self._select_tool(tool); return True
        if key == "Escape":
            c.deselect(); return True
        return False

    # ══ diálogos ══════════════════════════════════════════════════════════════
    def _dlg(self, title, w=340):
        dlg = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dlg.set_default_size(w, 100)
        box = dlg.get_content_area()
        box.set_spacing(8)
        for m in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{m}")(14)
        return dlg, box

    def _dlg_ints(self, title, fields, ok_cb, extra=None):
        dlg, box = self._dlg(title)
        spins = []
        grid = Gtk.Grid(row_spacing=6, column_spacing=8)
        for r, (label, value, lo, hi) in enumerate(fields):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, r, 1, 1)
            sp = Gtk.SpinButton.new_with_range(lo, hi, 1); sp.set_value(value); sp.set_hexpand(True)
            grid.attach(sp, 1, r, 1, 1); spins.append(sp)
        box.append(grid)
        extra_w = extra(box) if extra else None
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=tr("Cancelar")); cancel.connect("clicked", lambda _: dlg.destroy())
        ok = Gtk.Button(label=tr("Aceptar")); ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: (ok_cb([int(s.get_value()) for s in spins], extra_w), dlg.destroy()))
        row.append(cancel); row.append(ok); box.append(row)
        dlg.present()

    def _dlg_canvas_size(self):
        def extra(box):
            dd = Gtk.DropDown.new_from_strings([tr("Anclar al centro"), tr("Anclar arriba-izquierda")])
            box.append(dd); return dd
        self._dlg_ints(tr("Tamaño del lienzo (no escala el dibujo)"),
                       [(tr("Ancho"), self.canvas.cw, 1, 512), (tr("Alto"), self.canvas.ch, 1, 512)],
                       lambda v, dd: self.canvas.canvas_size(
                           v[0], v[1], "center" if dd.get_selected() == 0 else "tl"), extra)

    def _dlg_resize(self):
        self._dlg_ints(tr("Redimensionar sprite (escala con píxeles duros)"),
                       [(tr("Ancho"), self.canvas.cw, 1, 512), (tr("Alto"), self.canvas.ch, 1, 512)],
                       lambda v, _e: self.canvas.resize_sprite(v[0], v[1]))

    def _dlg_layer(self, li):
        c = self.canvas
        if not (0 <= li < len(c.layers)): return
        layer = c.layers[li]
        dlg, box = self._dlg(tr("Propiedades de la capa"))
        name = Gtk.Entry(); name.set_text(layer.name)
        box.append(Gtk.Label(label=tr("Nombre"), xalign=0)); box.append(name)
        box.append(Gtk.Label(label=tr("Opacidad"), xalign=0))
        op = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 255, 1); op.set_value(layer.opacity)
        op.set_draw_value(True); box.append(op)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=tr("Cancelar")); cancel.connect("clicked", lambda _: dlg.destroy())
        ok = Gtk.Button(label=tr("Aceptar")); ok.add_css_class("suggested-action")

        def go(_):
            c.rename_layer(li, name.get_text().strip()); c.set_layer_opacity(li, op.get_value())
            self._sync(); dlg.destroy()
        ok.connect("clicked", go); row.append(cancel); row.append(ok); box.append(row)
        dlg.present()

    # ── importar ─────────────────────────────────────────────────────────────
    def _on_import(self, _):
        dlg = Gtk.FileDialog(); dlg.set_title(tr("Elige imagen base"))
        dlg.open(self, None, self._on_file_chosen)

    def _on_file_chosen(self, dlg, result):
        try: gf = dlg.open_finish(result)
        except GLib.Error: return
        md = Gtk.AlertDialog()
        md.set_message(tr("¿Cómo importar la imagen?"))
        md.set_detail(tr("«Pixelar» ajusta a la resolución del lienzo.\n«Suavizado» usa interpolación bicúbica."))
        md.set_buttons([tr("Pixelar"), tr("Suavizado"), tr("Cancelar")])
        md.set_default_button(0); md.set_cancel_button(2)
        md.choose(self, None, lambda d, r, path=gf.get_path(): self._import_done(d, r, path))

    def _import_done(self, dialog, result, path):
        try: idx = dialog.choose_finish(result)
        except GLib.Error: return
        if idx == 2: return
        self.canvas.import_image(path, pixelate=(idx == 0))
        self._sync()

    # ── tutorial ─────────────────────────────────────────────────────────────
    @staticmethod
    def _tool_help():
        return [(ic, tr(tip).split(" — ")[0], k) for _t, ic, tip, k in TOOLS]

    _FRAME_HELP = [
        ("layers", N_("Nuevo fotograma (copia)"), "Alt+N"), ("onion", N_("Papel cebolla"), None),
        ("copy", N_("Copiar / pegar selección"), "Ctrl+C / V"), ("play", N_("Reproducir"), "Enter"),
        ("add", N_("Nueva capa"), "Shift+N"), ("flatten", N_("Unir capas"), None),
    ]

    @staticmethod
    def _tool_grid(items):
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(2)
        flow.set_column_spacing(8); flow.set_row_spacing(8)
        flow.set_homogeneous(True)
        for icon_name, name, tag in items:
            flow.append(gw.item_row(gw.icon_badge(icon_image(icon_name, 18)), tr(name), tag_text=tag))
        return flow

    def _show_tutorial(self, force=False):
        from .. import settings as _s
        if not force and _s.get("tutorial_pixel_shown", False):
            return
        dlg = Gtk.Dialog(title=tr("Editor de Píxeles — Guía rápida"), transient_for=self, modal=True)
        dlg.set_default_size(600, 700)
        box = dlg.get_content_area(); box.set_spacing(0)
        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for m in ("start", "end"): getattr(content, f"set_margin_{m}")(20)
        content.set_margin_top(16); content.set_margin_bottom(16)

        content.append(gw.body(
            tr("Editor de píxeles con la misma disposición, herramientas y atajos que "
            "Aseprite: si ya lo usas, tus manos saben qué hacer.")))
        content.append(gw.section_title(tr("FLUJO RECOMENDADO")))
        steps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for i, s in enumerate([
            tr("Elige el tamaño del lienzo (16², 32², 64²…)."),
            tr("Dibuja con el lápiz (B); clic derecho usa el color de fondo."),
            tr("Crea fotogramas con Alt+N y usa el papel cebolla como guía."),
            tr("Reproduce con Enter para revisar el movimiento."),
            tr("Escribe el nombre de la pose y pulsa «Guardar pose» (Ctrl+S)."),
        ], start=1):
            steps.append(gw.step_row(i, s))
        content.append(steps)

        content.append(gw.section_title(tr("HERRAMIENTAS (caja de la derecha)")))
        content.append(self._tool_grid(self._tool_help()))
        content.append(gw.section_title(tr("MOVERSE POR EL LIENZO")))
        content.append(gw.note(
            tr("Rueda del ratón = zoom hacia el cursor · Espacio + arrastrar (o botón medio) = mover la vista · "
            "Shift + rueda = desplazar · 1–6 = zoom 100–3200% · Ctrl+0 = ajustar.")))
        content.append(gw.section_title(tr("DIBUJO")))
        content.append(gw.note(
            tr("Clic derecho = color de fondo · Alt+clic = cuentagotas · Shift+clic = línea recta desde el último punto · "
            "[ ] = tamaño del pincel · X = intercambiar colores · barra superior: tinta, opacidad y pixel-perfect.")))
        content.append(gw.section_title(tr("SELECCIÓN")))
        content.append(gw.note(
            tr("Marco (M), lazo (Q) y varita (W). Shift añade, Alt resta. Ctrl+A todo · Ctrl+D quitar · "
            "Ctrl+C/X/V copiar, cortar y pegar · Supr borra · Ctrl+flechas mueve 1 px.")))
        content.append(gw.section_title(tr("AYUDAS DE DIBUJO")))
        content.append(gw.note(
            tr("Menú Vista: simetría horizontal, vertical o H+V, modo mosaico (X, Y o X+Y) para texturas que se repiten, "
            "cuadrícula de píxeles (Ctrl+') de 8, 16 o 32 px, papel cebolla anterior/siguiente y una ventana de vista previa "
            "con la animación a tamaño real.")))
        content.append(gw.section_title(tr("SPRITE Y PALETA")))
        content.append(gw.note(
            tr("Menú Sprite: tamaño del lienzo, redimensionar, recortar a la selección, voltear o rotar (90°/180°). También hay un "
            "contorno automático con el color principal. Paleta: clic = color principal, clic derecho = fondo, «+» y «−» añaden o "
            "quitan colores y «↺» la restaura.")))
        content.append(gw.section_title(tr("CAPAS Y FOTOGRAMAS")))
        content.append(self._tool_grid(self._FRAME_HELP))
        content.append(gw.note(
            tr("Ojo = ver/ocultar, candado = bloquear, doble clic en el nombre = propiedades. "
            "Al guardar la pose las capas se combinan en una imagen por fotograma.")))
        content.append(gw.section_title(tr("DESHACER, GUARDAR Y EXPORTAR")))
        content.append(gw.note(
            tr("Ctrl+Z deshace y Ctrl+Y (o Ctrl+Shift+Z) rehace. «Guardar pose» (Ctrl+S) crea o actualiza la mascota. En Archivo "
            "puedes importar una imagen (se pixela) y exportar como GIF animado. F1 vuelve a abrir esta guía.")))
        sc.set_child(content); box.append(sc)

        footer = Gtk.Box(spacing=10)
        footer.set_margin_start(14); footer.set_margin_end(14)
        footer.set_margin_top(8); footer.set_margin_bottom(10)
        no_show = Gtk.CheckButton(label=tr("No mostrar al iniciar el editor")); no_show.set_hexpand(True)
        footer.append(no_show)
        ok = Gtk.Button(label=tr("✓  Entendido")); ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: (_s.set_val("tutorial_pixel_shown", no_show.get_active()), dlg.destroy()))
        footer.append(ok); box.append(footer)
        dlg.present()

    # ── cerrar ───────────────────────────────────────────────────────────────
    def _on_close_request(self, *_):
        if self._play_id: GLib.source_remove(self._play_id); self._play_id = None
        if self._prev_id: GLib.source_remove(self._prev_id); self._prev_id = None
        self._playing = False
        if self._status_id: GLib.source_remove(self._status_id); self._status_id = None
        release_signals(self, [self._grp])
        GLib.idle_add(self._teardown)
        return False

    def _teardown(self):
        """Rompe los ciclos ventana↔widgets↔callbacks que el recolector de Python no
        ve (pasan por GTK) para que al cerrar se libere la memoria del editor."""
        c = self.canvas
        c._stop_ants()
        for n in ("on_pick", "on_frame_changed", "on_layers_changed", "on_cursor_moved",
                  "on_zoom_changed", "on_status", "on_tool_request"):
            setattr(c, n, None)
        c.layers = []; c._surf_cache.clear(); c._undo.clear(); c._redo.clear(); c._clip = None
        if self.get_child() is not None: self.set_child(None)
        self.__dict__.clear()
        return False

    def _confirm_close(self):
        dlg = Gtk.AlertDialog()
        dlg.set_message(tr("¿Cerrar el editor de píxeles?"))
        dlg.set_detail(tr("Si no has guardado la pose (botón «Guardar pose» o Ctrl+S) se perderán los cambios."))
        dlg.set_buttons([tr("Cancelar"), tr("Guardar y cerrar"), tr("Cerrar sin guardar")])
        dlg.set_cancel_button(0); dlg.set_default_button(1)
        dlg.choose(self, None, self._confirm_close_done)

    def _confirm_close_done(self, dlg, result):
        try: idx = dlg.choose_finish(result)
        except Exception:  # noqa: BLE001
            return
        if idx == 1: self._save_pose(); self.close()
        elif idx == 2: self.close()

    # ── guardar pose ─────────────────────────────────────────────────────────
    def _save_pose(self):
        pose = self.pose_entry.get_text().strip() or "default"
        fps = int(self.fps_spin.get_value())
        cw, ch = self.canvas.cw, self.canvas.ch
        from ..core import image_processor as importer

        if self.anim_id is None:
            name = (self.name_entry.get_text().strip() if self.name_entry else tr("Sin nombre")) or tr("Sin nombre")
            aid = self.app.library.new_id()
            fd = self.app.library.frames_dir(aid)
            pose_dir = fd if pose == "default" else fd / pose
            pose_dir.mkdir(parents=True, exist_ok=True)
            self._export_frames(pose_dir)
            self.app.library.add(aid, name, self.canvas.frame_count, cw, ch)
            self.app.library.update(aid, fps=fps)
            importer.ensure_flipped(pose_dir)
            if pose != "default":
                self.app.register_pose(aid, pose, fps)
            self.anim_id = aid
            self._flash(tr("Animación «{name}» creada.", name=name))
        else:
            fd = self.app.library.frames_dir(self.anim_id)
            pose_dir = fd if pose == "default" else fd / pose
            pose_dir.mkdir(parents=True, exist_ok=True)
            self._export_frames(pose_dir)
            importer.ensure_flipped(pose_dir)
            self.app.register_pose(self.anim_id, pose, fps)
            self._flash(tr("Pose «{pose}» guardada.", pose=pose))

        if self.app.control: self.app.control.refresh()
        if self._guided: self._suggest_next_pose()

    def _export_frames(self, dest):
        for i in range(self.canvas.frame_count):
            self.canvas.to_pil(i).save(dest / f"frame_{i:04d}.png")

    def _suggest_next_pose(self):
        if not self.anim_id: return
        from .. import tips
        anim = self.app.library.animations.get(self.anim_id, {})
        nxt = tips.next_missing(anim.get("poses", []))
        if nxt:
            self.pose_entry.set_text(nxt); self._show_tip(nxt)
        else:
            self._flash(tr("¡Todas las poses creadas!"))

    def _show_tip(self, pose):
        from .. import tips
        info = tips.tip_for(pose)
        md = Gtk.AlertDialog()
        md.set_message(tr("Siguiente: {x0}  (~{x1} cuadros)", x0=info['titulo'], x1=info['frames']))
        md.set_detail("\n".join(f"• {t}" for t in info["tips"]))
        md.set_buttons([tr("Entendido")]); md.show(self)

    # ── tamaño inicial del lienzo ────────────────────────────────────────────
    def _ask_canvas_size(self):
        dlg = Gtk.Dialog(title=tr("Nuevo sprite"), transient_for=self, modal=True)
        dlg.set_default_size(380, 300)
        box = dlg.get_content_area()
        box.set_spacing(8)
        for m in ("start", "end", "top", "bottom"): getattr(box, f"set_margin_{m}")(16)
        box.append(gw.note(
            tr("64×64 es un buen punto de partida para mascotas de escritorio: se ve nítido a tamaño real. "
            "Más adelante puedes cambiarlo en Sprite → Tamaño del lienzo.")))
        grid = Gtk.Grid(row_spacing=6, column_spacing=8)
        w_sp = Gtk.SpinButton.new_with_range(1, 512, 8); w_sp.set_value(64)
        h_sp = Gtk.SpinButton.new_with_range(1, 512, 8); h_sp.set_value(64)
        grid.attach(Gtk.Label(label=tr("Ancho (px)"), xalign=0), 0, 0, 1, 1); grid.attach(w_sp, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label=tr("Alto (px)"), xalign=0), 0, 1, 1, 1); grid.attach(h_sp, 1, 1, 1, 1)
        box.append(grid)
        presets = Gtk.Box(spacing=4)
        for lbl, w, h, rec in [("16²", 16, 16, False), ("32²", 32, 32, False), ("64² ★", 64, 64, True),
                               ("128²", 128, 128, False), ("64×96", 64, 96, False)]:
            b = Gtk.Button(label=lbl)
            if rec: b.set_tooltip_text(tr("Recomendado para mascotas de escritorio"))
            b.connect("clicked", lambda _, ww=w, hh=h: (w_sp.set_value(ww), h_sp.set_value(hh)))
            presets.append(b)
        box.append(presets)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=tr("Cancelar")); cancel.connect("clicked", lambda _: (dlg.destroy(), self.close()))
        ok = Gtk.Button(label=tr("Crear lienzo")); ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: self._apply_canvas_size(dlg, int(w_sp.get_value()), int(h_sp.get_value())))
        row.append(cancel); row.append(ok); box.append(row)
        dlg.present()
        return False

    def _apply_canvas_size(self, dlg, w, h):
        self.canvas.reset(w, h)
        dlg.destroy()
        self._sync()
        self._show_tutorial()

    # ── exportar GIF ─────────────────────────────────────────────────────────
    def _export_gif_dialog(self):
        dlg = Gtk.FileDialog()
        dlg.set_title(tr("Guardar como GIF")); dlg.set_initial_name("animacion.gif")
        dlg.save(self, None, self._gif_save_done)

    def _gif_save_done(self, dlg, result):
        try: gf = dlg.save_finish(result)
        except GLib.Error: return
        path = gf.get_path()
        if not path.lower().endswith(".gif"): path += ".gif"
        delay_ms = max(20, 1000 // int(self.fps_spin.get_value()))
        frames = [self.canvas.to_pil(i).convert("RGBA") for i in range(self.canvas.frame_count)]
        if not frames: return
        frames[0].save(path, format="GIF", save_all=True, append_images=frames[1:],
                       loop=0, duration=delay_ms, disposal=2)
        self._flash(tr("GIF guardado: {name}", name=Path(path).name))
