"""
Editor de animación — AnimaLinux (v4, disposición y funciones estilo Toon Boom Harmony)

  ┌ menús: Archivo Editar Vista Reproducir Insertar Escena Dibujo Animación Ventanas Ayuda ┐
  │ barra de herramientas (archivo · edición · vista)                                       │
  ├ caja de ┬──── Cámara | Dibujo ────────────────────┬─ Propiedades de herramienta | Capa ┤
  │ herram. │     vista con papel cebolla,             │                                    │
  │         │     mesa de luz y guías                  ├─ Color | Cámara ───────────────────┤
  ├─────────┴──────────────────────────────────────────┴────────────────────────────────────┤
  │ Reproducir · Bucle · Sonido · Fotograma · Inicio · Fin · FPS                            │
  │ Línea de tiempo: capas × fotogramas (hoja de exposición), cabezal y rango               │
  └──────────────────────────────────────────────────────────────────────────────────────────┘

Teclas: V seleccionar · A contorno · B pincel · N lápiz · E borrador · U dedo · P pintar
        G degradado · I cuentagotas · L línea · R rectángulo · O elipse · Y polilínea
        Q lazo · H mano · Z zoom · C cámara · X intercambiar colores · [ ] tamaño
        , . fotograma anterior/siguiente · Enter reproducir · Espacio+arrastrar mover vista
        F5 extender exposición · F6 dibujo nuevo · F7 duplicar dibujo · Supr limpiar celda
"""
import subprocess
import tempfile
import shutil
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Gio

from . import anim_engine as ae
from .anim_canvas import AnimCanvas
from .anim_widgets import Timeline, ToolProps, LayerProps, ColorDock, CameraDock
from .icons import icon_image
from .menubar import build_menubar
from .teardown import release_signals
from ..ui import guide_widgets as gw

ICO = "#e6e6e6"

PALETTE = [
    (0, 0, 0, 255), (60, 60, 60, 255), (120, 120, 120, 255), (190, 190, 190, 255), (255, 255, 255, 255),
    (180, 30, 30, 255), (230, 70, 50, 255), (240, 140, 40, 255), (245, 200, 50, 255), (170, 210, 60, 255),
    (60, 170, 70, 255), (30, 120, 90, 255), (50, 190, 180, 255), (70, 140, 220, 255), (40, 70, 190, 255),
    (90, 50, 180, 255), (150, 70, 200, 255), (215, 90, 190, 255), (235, 130, 185, 255), (255, 200, 220, 255),
    (120, 75, 35, 255), (170, 110, 60, 255), (215, 165, 115, 255), (255, 225, 190, 255), (0, 0, 0, 0),
]

# id, icono, nombre, tecla
TOOLS = [
    ("select",   "arrow",        "Seleccionar (V)", "V"),
    ("contour",  "contour_edit", "Editor de contorno (A)", "A"),
    ("brush",    "brush",        "Pincel (B)", "B"),
    ("pencil",   "pencil",       "Lápiz (N)", "N"),
    ("eraser",   "eraser",       "Borrador (E)", "E"),
    ("smudge",   "smudge",       "Dedo / difuminar (U)", "U"),
    ("paint",    "fill",         "Pintar — bote con cierre de huecos (P)", "P"),
    ("gradient", "gradient",     "Degradado (G)", "G"),
    ("dropper",  "pick",         "Cuentagotas (I) — Alt+clic con otra herramienta", "I"),
    ("line",     "line",         "Línea (L)", "L"),
    ("rect",     "outline",      "Rectángulo (R)", "R"),
    ("ellipse",  "ellipse",      "Elipse (O)", "O"),
    ("polyline", "polyline",     "Polilínea (Y)", "Y"),
    ("lasso",    "lasso",        "Lazo (Q)", "Q"),
    ("hand",     "hand",         "Mano (H) — o mantén Espacio", "H"),
    ("zoom",     "zoom_in",      "Zoom (Z) — clic acerca, clic derecho aleja", "Z"),
    ("camera",   "camera",       "Cámara (C) — en la vista Cámara", "C"),
]
KEY_TOOLS = {t[3].lower(): t[0] for t in TOOLS}

CSS = """
window.hm, window.hm box { background-color: #3c3c3c; }
window.hm, window.hm label { color: #dcdcdc; }
window.hm .hm-menu { background-color: #2c2c2c; border-bottom: 1px solid #1a1a1a; padding: 0 2px; }
window.hm .hm-menubtn, window.hm .hm-menubtn > button { padding: 0; border: none; border-radius: 0; background: transparent; box-shadow: none; }
window.hm .hm-menubtn > button { padding: 3px 10px; min-height: 20px; }
window.hm .hm-menubtn > button label { color: #dcdcdc; }
window.hm .hm-menubtn > button:hover, window.hm .hm-menubtn > button:checked { background-color: #494949; border: none; }
popover.hm-pop, popover.hm-pop > arrow { background: transparent; box-shadow: none; border: none; }
popover.hm-pop > contents { background-color: #383838; color: #e6e6e6; border: 1px solid #1a1a1a; border-radius: 3px; padding: 3px; }
popover.hm-pop modelbutton { color: #e6e6e6; padding: 4px 12px; min-height: 22px; border-radius: 2px; }
popover.hm-pop modelbutton:hover { background-color: #3d6f9c; color: #ffffff; }
popover.hm-pop modelbutton label, popover.hm-pop modelbutton accelerator { color: inherit; }
popover.hm-pop separator { background-color: #232323; min-height: 1px; margin: 3px 0; }
window.hm .hm-bar { background-color: #333333; border-bottom: 1px solid #1a1a1a; padding: 3px 6px; }
window.hm .hm-tools { background-color: #2f2f2f; border-right: 1px solid #1a1a1a; padding: 4px 3px; }
window.hm .hm-view { background-color: #808080; }
window.hm .hm-viewbar { background-color: #333333; border-top: 1px solid #1a1a1a; padding: 2px 6px; }
window.hm .hm-tabs { background-color: #2f2f2f; padding: 0 4px; }
window.hm .hm-dock { background-color: #444444; border-left: 1px solid #1a1a1a; }
window.hm .hm-tl { background-color: #3c3c3c; border-top: 1px solid #1a1a1a; }
window.hm .hm-status { background-color: #2c2c2c; border-top: 1px solid #1a1a1a; padding: 2px 8px; }
window.hm button { background-image: none; background-color: #4d4d4d; border: 1px solid #262626; border-radius: 3px;
   color: #e6e6e6; padding: 2px 7px; min-height: 22px; box-shadow: none; }
window.hm button:hover { background-color: #5d5d5d; }
window.hm button:checked, window.hm button:active { background-color: #3d6f9c; border-color: #1d3f5f; }
window.hm button.hm-tool { padding: 3px; min-width: 28px; min-height: 28px; background-color: transparent; border-color: transparent; }
window.hm button.hm-tool:hover { background-color: #484848; }
window.hm button.hm-tool:checked { background-color: #3d6f9c; border-color: #24455f; }
window.hm button.hm-tab { border-radius: 3px 3px 0 0; background-color: #3a3a3a; }
window.hm button.hm-tab:checked { background-color: #808080; color: #1a1a1a; }
window.hm button.suggested-action { background-color: #3d7fbf; color: #fff; }
window.hm entry, window.hm spinbutton, window.hm spinbutton text { background-color: #2b2b2b; color: #e6e6e6;
   border-radius: 3px; min-height: 22px; border-color: #202020; }
window.hm entry text, window.hm text { color: #e6e6e6; background-color: transparent; }
window.hm spinbutton button { min-height: 18px; padding: 0 3px; }
window.hm separator { background-color: #232323; min-width: 1px; }
window.hm notebook > header { background-color: #2f2f2f; }
window.hm notebook > header > tabs > tab { padding: 4px 10px; color: #cfcfcf; }
window.hm notebook > header > tabs > tab:checked { background-color: #444444; color: #ffffff; }
window.hm notebook > stack { background-color: #444444; }
window.hm scale trough { background-color: #262626; min-height: 4px; }
window.hm scale highlight { background-color: #5e93c4; }
window.hm scale slider { background-color: #d8d8d8; border: 1px solid #111; min-width: 12px; min-height: 12px; }
window.hm scrolledwindow { background-color: #3c3c3c; }
window.hm .dim-label { color: #a9a9a9; }
window.hm .heading { font-weight: bold; color: #ffffff; }
"""

_css = False


def _load_css():
    global _css
    if _css: return
    prov = Gtk.CssProvider()
    try: prov.load_from_string(CSS)
    except AttributeError: prov.load_from_data(CSS.encode())
    d = Gdk.Display.get_default()
    if d:
        Gtk.StyleContext.add_provider_for_display(d, prov, Gtk.STYLE_PROVIDER_PRIORITY_USER + 5); _css = True


class PaintEditor(Gtk.Window):
    def __init__(self, app, anim_id=None, pose=None, guided=False, project=None):
        super().__init__(application=app, title="Editor de Animación — AnimaLinux")
        self.app = app
        self.anim_id = anim_id
        self._guided = guided
        self._playing = False
        self._play_id = None
        self._audio = None
        self._status_id = None
        self._syncing = False
        self._project_path = None

        from ..ui import theme
        theme.apply(self)
        _load_css()
        self.add_css_class("hm")
        self.set_default_size(1420, 880)

        from .. import settings as _s
        saved = _s.get("anim_palette", None)
        self.palette = [tuple(c) for c in saved] if saved else list(PALETTE)

        self.canvas = AnimCanvas(ae.Scene(512, 512, 12))
        c = self.canvas
        c.on_frame = self._sync; c.on_layers = self._sync
        c.on_cursor = self._on_cursor; c.on_zoom = self._on_zoom
        c.on_status = self._flash; c.on_tool = self._select_tool
        c.on_pick = self._on_pick

        self._build_actions()
        self._build_ui()
        self.connect("close-request", self._on_close_request)

        if pose: self.pose_entry.set_text(pose)
        elif guided: self._suggest_next_pose()

        if anim_id is not None and pose in (None, "default"):
            if c.load_from_dir(app.library.frames_dir(anim_id)):
                fps = app.library.animations.get(anim_id, {}).get("fps")
                if fps: c.scene.fps = int(fps)
                self._sync()

        if project:
            if c.load_project(project):
                self._project_path = project; self._started = True; self._sync()
                self._flash(f"Proyecto cargado: {Path(project).name}")
            else:
                self._flash("No se pudo abrir el proyecto")
        elif anim_id is None: GLib.idle_add(self._ask_scene_size)
        else: GLib.idle_add(self._show_tutorial)

    # ══ acciones ══════════════════════════════════════════════════════════════
    def _build_actions(self):
        self._grp = Gio.SimpleActionGroup(); self.insert_action_group("an", self._grp)
        c = self.canvas

        def act(name, cb, state=None, ptype=None):
            if state is None:
                a = Gio.SimpleAction.new(name, None); a.connect("activate", lambda *_: cb())
            elif ptype is None:
                a = Gio.SimpleAction.new_stateful(name, None, GLib.Variant.new_boolean(state))
                a.connect("change-state", lambda x, v: (x.set_state(v), cb(v.get_boolean())))
            else:
                a = Gio.SimpleAction.new_stateful(name, GLib.VariantType.new("s"), GLib.Variant.new_string(state))
                a.connect("change-state", lambda x, v: (x.set_state(v), cb(v.get_string())))
            self._grp.add_action(a); return a

        # archivo
        act("new", self._ask_scene_size); act("open", self._open_project_dialog)
        act("save_project", lambda: self._save_project_dialog())
        act("save_pose", self._save_pose)
        act("import_image", self._import_image_dialog); act("import_seq", self._import_seq_dialog)
        act("import_audio", self._import_audio)
        act("export_gif", self._export_gif_dialog); act("export_mp4", self._export_mp4_dialog)
        act("export_png", self._export_png_dialog)
        act("close", self._confirm_close)
        # editar
        act("undo", c.undo); act("redo", c.redo)
        act("cut", lambda: c.copy_selection(cut=True)); act("copy", c.copy_selection); act("paste", c.paste_selection)
        act("clear", c.clear_selection); act("select_all", c.select_all); act("deselect", c.deselect)
        act("invert", c.invert_selection)
        # vista
        act("zoom_in", lambda: c.zoom_at(1.25)); act("zoom_out", lambda: c.zoom_at(1 / 1.25))
        act("fit", c.zoom_fit); act("zoom100", lambda: c.zoom_to(1.0))
        self._a_onion = act("onion", self._set_onion, state=False)
        self._a_light = act("light", self._set_light, state=False)
        self._a_grid = act("grid", self._set_grid, state=False)
        self._a_safe = act("safe", self._set_safe, state=False)
        self._a_paper = act("paper", self._set_paper, state=False)
        self._a_mirror = act("mirror", self._set_mirror, state=False)
        self._a_sym = act("sym", self._set_sym, state="none", ptype="s")
        self._a_view = act("view", self._set_view, state="draw", ptype="s")
        # reproducir
        act("play", lambda: self.play_btn.set_active(not self.play_btn.get_active()))
        self._a_loop = act("loop", lambda v: self.loop_btn.set_active(v), state=True)
        act("first", lambda: c.go_to(c.scene.start)); act("last", lambda: c.go_to(c.scene.stop))
        act("prev", lambda: c.go_to(c.cur - 1)); act("next", lambda: c.go_to(c.cur + 1))
        act("set_start", lambda: self._set_range(start=c.cur)); act("set_stop", lambda: self._set_range(stop=c.cur))
        # insertar
        act("layer_raster", lambda: c.add_layer("raster")); act("layer_vector", lambda: c.add_layer("vector"))
        act("layer_dup", c.duplicate_layer); act("layer_del", c.remove_layer)
        act("layer_up", lambda: c.move_layer(1)); act("layer_down", lambda: c.move_layer(-1))
        act("layer_merge", c.merge_down)
        act("frame_insert", c.insert_frame); act("frame_delete", c.delete_frame)
        act("drawing_new", c.new_drawing_here); act("drawing_dup", c.duplicate_drawing_here)
        act("extend", lambda: c.extend_exposure(1)); act("clear_cell", c.clear_cell)
        # escena
        act("scene_size", self._dlg_scene); act("scene_length", self._dlg_length)
        # dibujo
        act("flip_h", lambda: c.flip_drawing(True)); act("flip_v", lambda: c.flip_drawing(False))
        act("rot_cw", lambda: c.rotate_drawing(90)); act("rot_ccw", lambda: c.rotate_drawing(-90))
        act("rot_180", lambda: c.rotate_drawing(180)); act("nudge_up", lambda: c.nudge(0, -1))
        # animación
        act("cam_key", c.camera_key); act("cam_del", c.camera_remove_key); act("cam_reset", c.camera_reset)
        act("reverse", self._reverse_range); act("pingpong", self._pingpong_range)
        # ventanas / ayuda
        act("help", lambda: self._show_tutorial(force=True))

    @staticmethod
    def _it(label, action, accel=None, target=None):
        it = Gio.MenuItem.new(label, None)
        if target is None: it.set_detailed_action(action)
        else: it.set_action_and_target_value(action, GLib.Variant.new_string(target))
        if accel: it.set_attribute_value("accel", GLib.Variant.new_string(accel))
        return it

    def _build_menu(self):
        I = self._it

        def sect(*items):
            m = Gio.Menu()
            for i in items: m.append_item(i)
            return m

        def menu(*sections):
            m = Gio.Menu()
            for s in sections: m.append_section(None, s)
            return m

        archivo = menu(
            sect(I("Nueva escena…", "an.new", "<Control>n"), I("Abrir proyecto…", "an.open", "<Control>o"),
                 I("Guardar proyecto…", "an.save_project", "<Control><Shift>s"), I("Guardar pose", "an.save_pose", "<Control>s")),
            sect(I("Importar imagen a la celda…", "an.import_image"), I("Importar secuencia de imágenes…", "an.import_seq"),
                 I("Importar audio…", "an.import_audio")),
            sect(I("Exportar GIF…", "an.export_gif"), I("Exportar MP4…", "an.export_mp4"),
                 I("Exportar secuencia PNG…", "an.export_png")),
            sect(I("Cerrar el editor", "an.close", "<Control>w")))
        editar = menu(
            sect(I("Deshacer", "an.undo", "<Control>z"), I("Rehacer", "an.redo", "<Control>y")),
            sect(I("Cortar", "an.cut", "<Control>x"), I("Copiar", "an.copy", "<Control>c"), I("Pegar", "an.paste", "<Control>v"),
                 I("Borrar selección", "an.clear", "Delete")),
            sect(I("Seleccionar todo", "an.select_all", "<Control>a"), I("Deseleccionar", "an.deselect", "<Control>d"),
                 I("Invertir selección", "an.invert")))
        sym = sect(I("Sin simetría", "an.sym", target="none"), I("Simetría horizontal", "an.sym", target="h"),
                   I("Simetría vertical", "an.sym", target="v"), I("Simetría H + V", "an.sym", target="hv"))
        vista = menu(
            sect(I("Acercar", "an.zoom_in", "plus"), I("Alejar", "an.zoom_out", "minus"),
                 I("Ajustar a la ventana", "an.fit", "<Control>0"), I("Tamaño real (100%)", "an.zoom100", "1")),
            sect(I("Vista Dibujo", "an.view", target="draw"), I("Vista Cámara", "an.view", target="camera")),
            sect(I("Papel cebolla", "an.onion", "<Alt>o"), I("Mesa de luz", "an.light", "<Shift>l"),
                 I("Cuadrícula", "an.grid", "<Control>apostrophe"), I("Zona segura", "an.safe"),
                 I("Fondo de papel", "an.paper"), I("Vista espejo", "an.mirror")),
            sym)
        reproducir = menu(
            sect(I("Reproducir / pausar", "an.play", "Return"), I("Bucle", "an.loop")),
            sect(I("Ir al inicio del rango", "an.first", "Home"), I("Ir al final del rango", "an.last", "End"),
                 I("Fotograma anterior", "an.prev", "comma"), I("Fotograma siguiente", "an.next", "period")),
            sect(I("Fijar inicio en el fotograma actual", "an.set_start"), I("Fijar fin en el fotograma actual", "an.set_stop")))
        insertar = menu(
            sect(I("Capa de dibujo", "an.layer_raster", "<Control><Shift>n"), I("Capa vectorial", "an.layer_vector"),
                 I("Duplicar capa", "an.layer_dup"), I("Borrar capa", "an.layer_del"),
                 I("Subir capa", "an.layer_up"), I("Bajar capa", "an.layer_down"), I("Unir con la de abajo", "an.layer_merge")),
            sect(I("Insertar fotograma (todas las capas)", "an.frame_insert", "F8"),
                 I("Borrar fotograma (todas las capas)", "an.frame_delete", "<Shift>F8")),
            sect(I("Dibujo nuevo en la celda", "an.drawing_new", "F6"), I("Duplicar dibujo", "an.drawing_dup", "F7"),
                 I("Extender exposición", "an.extend", "F5"), I("Limpiar celda", "an.clear_cell")))
        escena = menu(sect(I("Tamaño de la escena…", "an.scene_size"), I("Duración (fotogramas)…", "an.scene_length")))
        dibujo = menu(
            sect(I("Voltear dibujo horizontal", "an.flip_h"), I("Voltear dibujo vertical", "an.flip_v"),
                 I("Girar 90° horario", "an.rot_cw"), I("Girar 90° antihorario", "an.rot_ccw"), I("Girar 180°", "an.rot_180")))
        animacion = menu(
            sect(I("Crear clave de cámara", "an.cam_key", "F9"), I("Borrar clave de cámara", "an.cam_del"),
                 I("Reiniciar cámara", "an.cam_reset")),
            sect(I("Invertir fotogramas del rango", "an.reverse"), I("Ida y vuelta (ping-pong) del rango", "an.pingpong")))
        ayuda = menu(sect(I("Guía rápida y atajos", "an.help", "F1")))
        top = Gio.Menu()
        for n, m in (("Archivo", archivo), ("Editar", editar), ("Vista", vista), ("Reproducir", reproducir),
                     ("Insertar", insertar), ("Escena", escena), ("Dibujo", dibujo), ("Animación", animacion),
                     ("Ayuda", ayuda)):
            top.append_submenu(n, m)
        return build_menubar(top, "hm-menubtn", "hm-pop")

    # ══ interfaz ══════════════════════════════════════════════════════════════
    @staticmethod
    def _hscroll(w):
        sc = Gtk.ScrolledWindow(); sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        sc.set_propagate_natural_height(True); sc.set_min_content_width(40); sc.set_child(w); return sc

    def _ib(self, icon, tip, cb, toggle=False, css=None, size=16):
        b = Gtk.ToggleButton() if toggle else Gtk.Button()
        b.set_child(icon_image(icon, size, ICO)); b.set_tooltip_text(tip); b.set_focus_on_click(False)
        if css: b.add_css_class(css)
        if toggle: b.connect("toggled", lambda w: cb(w.get_active()))
        else: b.connect("clicked", lambda w: cb())
        return b

    def _build_ui(self):
        c = self.canvas
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.set_child(root)

        top = Gtk.Box(); top.add_css_class("hm-menu")
        top.append(self._build_menu())
        self.title_lbl = Gtk.Label(); self.title_lbl.set_hexpand(True); self.title_lbl.add_css_class("dim-label")
        top.append(self.title_lbl)
        top.append(self._ib("help", "Guía rápida (F1)", lambda: self._show_tutorial(force=True)))
        top.append(self._ib("close", "Cerrar el editor (Ctrl+W)", self._confirm_close))
        root.append(top)

        root.append(self._hscroll(self._build_toolbar()))

        mid = Gtk.Box(); mid.set_vexpand(True); root.append(mid)
        mid.append(self._build_toolbox())

        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); center.set_hexpand(True); mid.append(center)
        tabs = Gtk.Box(spacing=2); tabs.add_css_class("hm-tabs")
        self.tab_draw = Gtk.ToggleButton(label="Dibujo"); self.tab_cam = Gtk.ToggleButton(label="Cámara")
        for b in (self.tab_draw, self.tab_cam): b.add_css_class("hm-tab"); b.set_focus_on_click(False)
        self.tab_cam.set_group(self.tab_draw); self.tab_draw.set_active(True)
        self.tab_draw.connect("toggled", lambda b: b.get_active() and self._a_view.change_state(GLib.Variant.new_string("draw")))
        self.tab_cam.connect("toggled", lambda b: b.get_active() and self._a_view.change_state(GLib.Variant.new_string("camera")))
        tabs.append(self.tab_draw); tabs.append(self.tab_cam)
        center.append(tabs)
        frame = Gtk.Box(); frame.add_css_class("hm-view"); frame.set_vexpand(True); frame.append(self.canvas)
        center.append(frame)
        center.append(self._hscroll(self._build_viewbar()))
        mid.append(self._build_docks())

        root.append(self._build_timeline())
        root.append(self._hscroll(self._build_status()))

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key); key.connect("key-released", self._on_key_up)
        self.add_controller(key)
        self._select_tool("brush")
        self._sync()

    # ── barra de herramientas ────────────────────────────────────────────────
    def _build_toolbar(self):
        bar = Gtk.Box(spacing=3); bar.add_css_class("hm-bar")
        for icon, tip, name in (("newfile", "Nueva escena (Ctrl+N)", "new"), ("folder_open", "Abrir proyecto (Ctrl+O)", "open"),
                                ("save", "Guardar proyecto (Ctrl+Shift+S)", "save_project")):
            bar.append(self._ib(icon, tip, lambda n=name: self._grp.lookup_action(n).activate(None)))
        bar.append(Gtk.Separator())
        for icon, tip, name in (("undo", "Deshacer (Ctrl+Z)", "undo"), ("redo", "Rehacer (Ctrl+Y)", "redo"),
                                ("cut", "Cortar", "cut"), ("copy", "Copiar", "copy"), ("paste", "Pegar", "paste")):
            bar.append(self._ib(icon, tip, lambda n=name: self._grp.lookup_action(n).activate(None)))
        bar.append(Gtk.Separator())
        self.tb_onion = self._ib("onion_skin", "Papel cebolla (Alt+O)", lambda on: self._a_onion.change_state(GLib.Variant.new_boolean(on)), toggle=True)
        self.tb_light = self._ib("light", "Mesa de luz (Shift+L)", lambda on: self._a_light.change_state(GLib.Variant.new_boolean(on)), toggle=True)
        self.tb_grid = self._ib("grid", "Cuadrícula", lambda on: self._a_grid.change_state(GLib.Variant.new_boolean(on)), toggle=True)
        self.tb_mirror = self._ib("mirror", "Vista espejo", lambda on: self._a_mirror.change_state(GLib.Variant.new_boolean(on)), toggle=True)
        for b in (self.tb_onion, self.tb_light, self.tb_grid, self.tb_mirror): bar.append(b)
        bar.append(Gtk.Separator())
        bar.append(self._ib("zoom_out", "Alejar", lambda: c_zoom(self, 1 / 1.25)))
        bar.append(self._ib("zoom_in", "Acercar", lambda: c_zoom(self, 1.25)))
        bar.append(self._ib("fit", "Ajustar a la ventana (Ctrl+0)", self.canvas.zoom_fit))
        sp = Gtk.Box(); sp.set_hexpand(True); bar.append(sp)
        gif = self._ib("gif", "Exportar GIF", self._export_gif_dialog); bar.append(gif)
        return bar

    def _build_toolbox(self):
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1); col.add_css_class("hm-tools")
        self._tool_btns = {}; first = None
        for tid, ic, tip, _k in TOOLS:
            b = Gtk.ToggleButton(); b.add_css_class("hm-tool"); b.set_child(icon_image(ic, 18, ICO))
            b.set_tooltip_text(tip); b.set_focus_on_click(False)
            if first is None: first = b
            else: b.set_group(first)
            b.connect("toggled", lambda w, t=tid: w.get_active() and self._on_tool(t))
            self._tool_btns[tid] = b; col.append(b)
        sc = Gtk.ScrolledWindow(); sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_child(col); sc.set_min_content_width(40); return sc

    def _build_viewbar(self):
        bar = Gtk.Box(spacing=6); bar.add_css_class("hm-viewbar")
        self.vb_light = self._ib("light", "Mesa de luz", lambda on: self._a_light.change_state(GLib.Variant.new_boolean(on)), toggle=True, size=14)
        self.vb_onion = self._ib("onion_skin", "Papel cebolla", lambda on: self._a_onion.change_state(GLib.Variant.new_boolean(on)), toggle=True, size=14)
        self.vb_grid = self._ib("grid", "Cuadrícula", lambda on: self._a_grid.change_state(GLib.Variant.new_boolean(on)), toggle=True, size=14)
        self.vb_paper = self._ib("paper", "Fondo de papel", lambda on: self._a_paper.change_state(GLib.Variant.new_boolean(on)), toggle=True, size=14)
        for b in (self.vb_light, self.vb_onion, self.vb_grid, self.vb_paper): bar.append(b)
        bar.append(Gtk.Label(label="◀"))
        self.onion_prev = Gtk.SpinButton.new_with_range(0, 6, 1); self.onion_prev.set_value(2)
        self.onion_prev.connect("value-changed", lambda w: self._onion_n("prev", w))
        self.onion_next = Gtk.SpinButton.new_with_range(0, 6, 1); self.onion_next.set_value(2)
        self.onion_next.connect("value-changed", lambda w: self._onion_n("next", w))
        bar.append(self.onion_prev); bar.append(Gtk.Label(label="▶")); bar.append(self.onion_next)
        bar.append(Gtk.Separator())
        sym = Gtk.DropDown.new_from_strings(["Sin simetría", "Simetría H", "Simetría V", "Simetría H+V"])
        sym.connect("notify::selected", lambda w, _p: self._a_sym.change_state(
            GLib.Variant.new_string(("none", "h", "v", "hv")[w.get_selected()])))
        bar.append(sym)
        sp = Gtk.Box(); sp.set_hexpand(True); bar.append(sp)
        self.frame_lbl = Gtk.Label(label="Fotograma 1/1"); bar.append(self.frame_lbl)
        self.zoom_lbl = Gtk.Label(label="100%"); self.zoom_lbl.set_size_request(52, -1); bar.append(self.zoom_lbl)
        return bar

    def _build_docks(self):
        c = self.canvas
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); col.add_css_class("hm-dock"); col.set_size_request(340, -1)

        def nb(*pages):
            n = Gtk.Notebook(); n.set_vexpand(True)
            for w, label in pages:
                sc = Gtk.ScrolledWindow(); sc.set_child(w); sc.set_propagate_natural_height(False)
                n.append_page(sc, Gtk.Label(label=label))
            return n

        self.props_panel = ToolProps(c, self._sel_action)
        self.layer_panel = LayerProps(c, self._sync)
        col.append(nb((self.props_panel, "Propiedades de herramienta"), (self.layer_panel, "Capa")))
        self.color_dock = ColorDock(c, self.palette, self._palette_changed)
        self.cam_dock = CameraDock(c)
        col.append(nb((self.color_dock, "Color"), (self.cam_dock, "Cámara")))
        return col

    def _build_timeline(self):
        c = self.canvas; s = c.scene
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); box.add_css_class("hm-tl")
        bar = Gtk.Box(spacing=5); bar.add_css_class("hm-bar")
        self.play_btn = self._ib("play", "Reproducir (Enter)", self._on_play, toggle=True)
        self.loop_btn = self._ib("loop", "Bucle", lambda on: setattr(self, "_loop", on), toggle=True)
        self.loop_btn.set_active(True); self._loop = True
        bar.append(self.play_btn); bar.append(self.loop_btn)
        bar.append(self._ib("sound", "Importar audio", self._import_audio))
        bar.append(Gtk.Separator())

        def spin(label, lo, hi, cb):
            bar.append(Gtk.Label(label=label))
            sp = Gtk.SpinButton.new_with_range(lo, hi, 1); sp.set_width_chars(4)
            sp.connect("value-changed", lambda w: cb(int(w.get_value())))
            sp.connect("activate", lambda w: self.canvas.grab_focus()); bar.append(sp); return sp
        self.sp_frame = spin("Fotograma", 1, 2000, lambda v: (not self._syncing) and c.go_to(v - 1))
        self.sp_start = spin("Inicio", 1, 2000, lambda v: (not self._syncing) and self._set_range(start=v - 1))
        self.sp_stop = spin("Fin", 1, 2000, lambda v: (not self._syncing) and self._set_range(stop=v - 1))
        self.sp_fps = spin("FPS", 1, 60, lambda v: (not self._syncing) and setattr(c.scene, "fps", v))
        bar.append(Gtk.Separator())
        for icon, tip, name in (("add", "Capa de dibujo nueva", "layer_raster"), ("vec_pen", "Capa vectorial nueva", "layer_vector"),
                                ("duplicate", "Duplicar capa", "layer_dup"), ("up", "Subir capa", "layer_up"),
                                ("down", "Bajar capa", "layer_down"), ("merge", "Unir con la de abajo", "layer_merge"),
                                ("trash", "Borrar capa", "layer_del")):
            bar.append(self._ib(icon, tip, lambda n=name: self._grp.lookup_action(n).activate(None), size=14))
        box.append(self._hscroll(bar))
        self.timeline = Timeline(c, on_rename=self._rename_layer, on_menu=self._cell_menu, on_range=self._sync)
        sc = Gtk.ScrolledWindow(); sc.set_child(self.timeline)
        sc.set_min_content_height(150); sc.set_max_content_height(240); sc.set_propagate_natural_height(True)
        box.append(sc)
        return box

    def _build_status(self):
        bar = Gtk.Box(spacing=8); bar.add_css_class("hm-status")
        self.cursor_lbl = Gtk.Label(label="X:—  Y:—"); self.cursor_lbl.set_size_request(120, -1); self.cursor_lbl.set_xalign(0)
        bar.append(self.cursor_lbl)
        self.msg = Gtk.Label(label=""); self.msg.set_hexpand(True); self.msg.set_xalign(0); self.msg.add_css_class("dim-label")
        bar.append(self.msg)
        self.size_lbl = Gtk.Label(label="512 × 512"); bar.append(self.size_lbl)
        bar.append(Gtk.Separator())
        if self.anim_id is None:
            bar.append(Gtk.Label(label="Nombre"))
            self.name_entry = Gtk.Entry(); self.name_entry.set_placeholder_text("Mi mascota"); self.name_entry.set_width_chars(12)
            bar.append(self.name_entry)
        else:
            self.name_entry = None
        bar.append(Gtk.Label(label="Pose"))
        self.pose_entry = Gtk.Entry(); self.pose_entry.set_text("default"); self.pose_entry.set_width_chars(8)
        self.pose_entry.connect("activate", lambda w: self.canvas.grab_focus()); bar.append(self.pose_entry)
        save = Gtk.Button(); save.add_css_class("suggested-action")
        sb = Gtk.Box(spacing=4); sb.append(icon_image("save", 14, "#ffffff")); sb.append(Gtk.Label(label="Guardar pose"))
        save.set_child(sb); save.connect("clicked", lambda _: self._save_pose()); bar.append(save)
        return bar

    # ══ estado ════════════════════════════════════════════════════════════════
    def _sync(self):
        c = self.canvas; s = c.scene
        self._syncing = True
        try:
            self.timeline.refresh()
            self.layer_panel.refresh(); self.cam_dock.refresh()
            for sp, v, hi in ((self.sp_frame, c.cur + 1, s.frame_count), (self.sp_start, s.start + 1, s.frame_count),
                              (self.sp_stop, s.stop + 1, s.frame_count)):
                sp.set_range(1, max(1, hi)); sp.set_value(v)
            self.sp_fps.set_value(s.fps)
            self.frame_lbl.set_text(f"Fotograma {c.cur + 1}/{s.frame_count}")
            self.size_lbl.set_text(f"{s.w} × {s.h}")
            self.title_lbl.set_text(f"{c.layer.name} · fotograma {c.cur + 1}")
        finally:
            self._syncing = False

    def _on_cursor(self, x, y):
        self.cursor_lbl.set_text(f"X:{x:6.1f}  Y:{y:6.1f}")

    def _on_zoom(self):
        self.zoom_lbl.set_text(f"{round(self.canvas._z * 100)}%")

    def _flash(self, m):
        self.msg.set_text(m)
        if self._status_id: GLib.source_remove(self._status_id)
        self._status_id = GLib.timeout_add(4000, self._clear_flash)

    def _clear_flash(self):
        self.msg.set_text(""); self._status_id = None; return False

    def _palette_changed(self):
        from .. import settings as _s
        _s.set_val("anim_palette", [list(c) for c in self.palette])

    def _on_pick(self, color, right):
        d = self.color_dock
        (d.set_colors(self.canvas.fg, color) if right else d.set_colors(color, self.canvas.bg))

    # ── herramientas ─────────────────────────────────────────────────────────
    def _on_tool(self, tid):
        self.canvas.set_tool(tid); self.props_panel.show_tool(tid)
        if tid == "camera" and self.canvas.mode != "camera": self._a_view.change_state(GLib.Variant.new_string("camera"))

    def _select_tool(self, tid):
        b = self._tool_btns.get(tid)
        if b is not None: b.set_active(True)
        self._on_tool(tid)

    def _sel_action(self, name):
        c = self.canvas
        {"flip_h": lambda: c.flip_drawing(True), "flip_v": lambda: c.flip_drawing(False),
         "rot_cw": lambda: c.rotate_drawing(90), "copy": c.copy_selection,
         "cut": lambda: c.copy_selection(cut=True), "paste": c.paste_selection,
         "invert": c.invert_selection, "clear": c.clear_selection,
         "zoom100": lambda: c.zoom_to(1.0), "fit": c.zoom_fit}[name]()

    # ── vista ────────────────────────────────────────────────────────────────
    def _set_onion(self, on):
        self.canvas.onion = on; self.canvas.queue_draw()
        for b in (self.tb_onion, self.vb_onion):
            if b.get_active() != on: b.set_active(on)

    def _onion_n(self, which, w):
        setattr(self.canvas, "onion_" + which, int(w.get_value())); self.canvas.queue_draw()

    def _set_light(self, on):
        self.canvas.light_table = on; self.canvas.queue_draw()
        for b in (self.tb_light, self.vb_light):
            if b.get_active() != on: b.set_active(on)

    def _set_grid(self, on):
        self.canvas.show_grid = on; self.canvas.queue_draw()
        for b in (self.tb_grid, self.vb_grid):
            if b.get_active() != on: b.set_active(on)

    def _set_safe(self, on): self.canvas.safe_area = on; self.canvas.queue_draw()

    def _set_paper(self, on):
        self.canvas.paper = on; self.canvas.queue_draw()
        if self.vb_paper.get_active() != on: self.vb_paper.set_active(on)

    def _set_mirror(self, on):
        self.canvas.mirror_view = on; self.canvas.queue_draw()
        if self.tb_mirror.get_active() != on: self.tb_mirror.set_active(on)

    def _set_sym(self, v): self.canvas.symmetry = v; self.canvas.queue_draw()

    def _set_view(self, v):
        self.canvas.mode = v; self.canvas.queue_draw()
        (self.tab_cam if v == "camera" else self.tab_draw).set_active(True)

    # ── rango / reproducción ─────────────────────────────────────────────────
    def _set_range(self, start=None, stop=None):
        s = self.canvas.scene
        if start is not None: s.start = max(0, min(start, s.frame_count - 1)); s.stop = max(s.stop, s.start)
        if stop is not None: s.stop = max(s.start, min(stop, s.frame_count - 1))
        self._sync()

    def _on_play(self, on):
        self._playing = on
        c = self.canvas; s = c.scene
        if on:
            if not (s.start <= c.cur <= s.stop): c.go_to(s.start)
            self._schedule()
            if s.audio and shutil.which("mpv"):
                try:
                    self._audio = subprocess.Popen(
                        ["mpv", "--no-video", f"--start={c.cur / max(1, s.fps):.3f}", s.audio],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except OSError: self._audio = None
        else:
            if self._play_id: GLib.source_remove(self._play_id); self._play_id = None
            self._stop_audio()

    def _stop_audio(self):
        proc, self._audio = self._audio, None
        if not proc: return
        try: proc.terminate()
        except OSError: return
        tries = [0]

        def reap():                      # recoge el proceso terminado (evita zombis)
            tries[0] += 1
            if proc.poll() is not None: return False
            if tries[0] > 15:
                try: proc.kill()
                except OSError: pass
            return tries[0] < 40
        GLib.timeout_add(150, reap)

    def _schedule(self):
        self._play_id = GLib.timeout_add(max(16, 1000 // max(1, self.canvas.scene.fps)), self._tick)

    def _tick(self):
        self._play_id = None
        if not self._playing: return False
        c = self.canvas; s = c.scene
        nxt = c.cur + 1
        if nxt > s.stop:
            if self._loop:
                nxt = s.start
                self._stop_audio()
                if s.audio and shutil.which("mpv"):
                    try:
                        self._audio = subprocess.Popen(["mpv", "--no-video", f"--start={nxt / max(1, s.fps):.3f}", s.audio],
                                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except OSError: pass
            else:
                self.play_btn.set_active(False); return False
        c.go_to(nxt)
        self._schedule()
        return False

    # ── línea de tiempo ──────────────────────────────────────────────────────
    def _rename_layer(self, li):
        c = self.canvas
        dlg = Gtk.Dialog(title="Renombrar capa", transient_for=self, modal=True)
        box = dlg.get_content_area(); box.set_spacing(8)
        for m in ("start", "end", "top", "bottom"): getattr(box, f"set_margin_{m}")(14)
        e = Gtk.Entry(); e.set_text(c.scene.layers[li].name); e.set_activates_default(True); box.append(e)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancelar"); cancel.connect("clicked", lambda _: dlg.destroy())
        ok = Gtk.Button(label="Aceptar"); ok.add_css_class("suggested-action")

        def go(_):
            c.scene.layers[li].name = e.get_text().strip() or c.scene.layers[li].name; dlg.destroy(); c._changed(True)
        ok.connect("clicked", go); e.connect("activate", go); row.append(cancel); row.append(ok); box.append(row)
        dlg.present()

    def _cell_menu(self, widget, x, y):
        m = Gio.Menu()
        I = self._it
        m.append_item(I("Dibujo nuevo en la celda", "an.drawing_new")); m.append_item(I("Duplicar dibujo", "an.drawing_dup"))
        m.append_item(I("Extender exposición (+1)", "an.extend")); m.append_item(I("Limpiar celda", "an.clear_cell"))
        m2 = Gio.Menu()
        m2.append_item(I("Insertar fotograma", "an.frame_insert")); m2.append_item(I("Borrar fotograma", "an.frame_delete"))
        m2.append_item(I("Fijar inicio aquí", "an.set_start")); m2.append_item(I("Fijar fin aquí", "an.set_stop"))
        m.append_section(None, m2)
        pop = Gtk.PopoverMenu.new_from_model(m); pop.add_css_class("hm-pop"); pop.set_has_arrow(False); pop.set_parent(widget)
        r = Gdk.Rectangle(); r.x, r.y, r.width, r.height = int(x), int(y), 1, 1
        pop.set_pointing_to(r); pop.popup()

    def _reverse_range(self):
        s = self.canvas.scene; s.reverse_frames(s.start, s.stop); self.canvas._after_struct(False)

    def _pingpong_range(self):
        s = self.canvas.scene; s.pingpong(s.start, s.stop); self.canvas._after_struct(False)

    # ══ teclado ═══════════════════════════════════════════════════════════════
    def _typing(self):
        f = self.get_focus()
        return isinstance(f, (Gtk.Editable, Gtk.SpinButton))

    def _on_key_up(self, ctrl, kv, kc, mods):
        if (Gdk.keyval_name(kv) or "") == "space": self.canvas.set_space(False)

    def _on_key(self, ctrl, kv, kc, mods):
        if self._typing(): return False
        c = self.canvas
        key = Gdk.keyval_name(kv) or ""; low = key.lower()
        ctl = bool(mods & Gdk.ModifierType.CONTROL_MASK); shift = bool(mods & Gdk.ModifierType.SHIFT_MASK)
        alt = bool(mods & Gdk.ModifierType.ALT_MASK)
        if key == "space": c.set_space(True); return True
        if ctl:
            if low == "z": (c.redo() if shift else c.undo()); return True
            if low == "y": c.redo(); return True
            if low == "s": (self._save_project_dialog() if shift else self._save_pose()); return True
            if low == "o": self._open_project_dialog(); return True
            if low == "n": (c.add_layer("raster") if shift else self._ask_scene_size()); return True
            if low == "w": self._confirm_close(); return True
            if low == "a": c.select_all(); return True
            if low == "d": c.deselect(); return True
            if low == "c": c.copy_selection(); return True
            if low == "x": c.copy_selection(cut=True); return True
            if low == "v": c.paste_selection(); return True
            if key == "0": c.zoom_fit(); return True
            if key == "1": c.zoom_to(1.0); return True
            arrows = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}
            if key in arrows: c.nudge(*arrows[key]); return True
            return False
        if alt:
            if low == "o": self._a_onion.change_state(GLib.Variant.new_boolean(not c.onion)); return True
            return False
        if shift and low == "l": self._a_light.change_state(GLib.Variant.new_boolean(not c.light_table)); return True
        if key == "F1": self._show_tutorial(force=True); return True
        if key == "F5": c.extend_exposure(1); return True
        if key == "F6": c.new_drawing_here(); return True
        if key == "F7": c.duplicate_drawing_here(); return True
        if key == "F8": (c.delete_frame() if shift else c.insert_frame()); return True
        if key == "F9": c.camera_key(); return True
        if key in ("Return", "KP_Enter"):
            if c._poly: c.finish_polyline(close=True)
            else: self.play_btn.set_active(not self.play_btn.get_active())
            return True
        if key == "Escape":
            if c._poly: c.finish_polyline(False)
            else: c.deselect()
            return True
        if key in ("comma", "Left"): c.go_to(c.cur - 1); return True
        if key in ("period", "Right"): c.go_to(c.cur + 1); return True
        if key == "Home": c.go_to(c.scene.start); return True
        if key == "End": c.go_to(c.scene.stop); return True
        if key == "Delete":
            if c.layer.kind == "vector" and c.vsel: c.clear_selection()
            elif c.tool == "contour" and c._vpoint: c.delete_point()
            elif c.sel is not None: c.clear_selection()
            else: c.clear_cell()
            return True
        if key in ("plus", "equal"): c.zoom_at(1.25); return True
        if key == "minus": c.zoom_at(1 / 1.25); return True
        if key == "bracketleft": self._resize_brush(0.85); return True
        if key == "bracketright": self._resize_brush(1 / 0.85); return True
        if low == "x" and not shift: self.color_dock.swap(); return True
        if low in KEY_TOOLS and not shift: self._select_tool(KEY_TOOLS[low]); return True
        return False

    def _resize_brush(self, f):
        p = self.canvas.props
        k = {"brush": "brush_size", "pencil": "pencil_size", "eraser": "eraser_size", "smudge": "smudge_size"}.get(self.canvas.tool)
        if k:
            p[k] = max(1.0, min(300.0, p[k] * f)); self.props_panel.show_tool(self.canvas.tool)
            self.canvas.queue_draw()

    # ══ diálogos / archivos ═══════════════════════════════════════════════════
    def _dlg(self, title, w=380):
        dlg = Gtk.Dialog(title=title, transient_for=self, modal=True); dlg.set_default_size(w, 100)
        box = dlg.get_content_area(); box.set_spacing(8)
        for m in ("start", "end", "top", "bottom"): getattr(box, f"set_margin_{m}")(14)
        return dlg, box

    def _dlg_scene(self):
        s = self.canvas.scene
        dlg, box = self._dlg("Tamaño de la escena")
        box.append(gw.note("Cambiar el tamaño reencuadra todos los dibujos (sin escalar). El contenido fuera del nuevo marco se recorta."))
        grid = Gtk.Grid(row_spacing=6, column_spacing=8)
        w = Gtk.SpinButton.new_with_range(64, 4096, 16); w.set_value(s.w)
        h = Gtk.SpinButton.new_with_range(64, 4096, 16); h.set_value(s.h)
        grid.attach(Gtk.Label(label="Ancho", xalign=0), 0, 0, 1, 1); grid.attach(w, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Alto", xalign=0), 0, 1, 1, 1); grid.attach(h, 1, 1, 1, 1); box.append(grid)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancelar"); cancel.connect("clicked", lambda _: dlg.destroy())
        ok = Gtk.Button(label="Aceptar"); ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: (self._resize_scene(int(w.get_value()), int(h.get_value())), dlg.destroy()))
        row.append(cancel); row.append(ok); box.append(row); dlg.present()

    def _resize_scene(self, w, h):
        import numpy as np
        c = self.canvas; s = c.scene
        s.snap()
        ox, oy = (w - s.w) // 2, (h - s.h) // 2
        for l in s.layers:
            for i, d in enumerate(l.drawings):
                if d.kind == "raster":
                    out = np.zeros((h, w, 4), np.uint8)
                    sx0, sy0, dx0, dy0 = max(0, -ox), max(0, -oy), max(0, ox), max(0, oy)
                    cw_, ch_ = min(s.w - sx0, w - dx0), min(s.h - sy0, h - dy0)
                    if cw_ > 0 and ch_ > 0: out[dy0:dy0 + ch_, dx0:dx0 + cw_] = d.arr[sy0:sy0 + ch_, sx0:sx0 + cw_]
                    l.drawings[i] = ae.Drawing(w, h, "raster", out)
                else:                          # copia nueva: así deshacer recupera los trazos originales
                    nd = ae.Drawing(w, h, "vector")
                    nd.strokes = [{**st, "pts": [(p[0] + ox, p[1] + oy, *p[2:]) for p in st["pts"]]} for st in d.strokes]
                    l.drawings[i] = nd
        s.w, s.h = w, h
        c.sel = None; c._sel_segs = None; c._fit_pending = True
        c._after_struct(False)

    def _dlg_length(self):
        s = self.canvas.scene
        dlg, box = self._dlg("Duración de la escena")
        sp = Gtk.SpinButton.new_with_range(1, 2000, 1); sp.set_value(s.frame_count)
        box.append(Gtk.Label(label="Fotogramas totales", xalign=0)); box.append(sp)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancelar"); cancel.connect("clicked", lambda _: dlg.destroy())
        ok = Gtk.Button(label="Aceptar"); ok.add_css_class("suggested-action")

        def go(_):
            n = int(sp.get_value()); s.set_length(n)
            s.stop = min(s.stop, n - 1) if n < s.stop + 1 else (n - 1 if s.stop == s.frame_count - 1 or n > s.stop else s.stop)
            self.canvas._after_struct(False); dlg.destroy()
        ok.connect("clicked", go); row.append(cancel); row.append(ok); box.append(row); dlg.present()

    def _ask_scene_size(self):
        dlg, box = self._dlg("Nueva escena", 430)
        box.append(gw.note(
            "512×512 es un buen punto de partida para mascotas: da espacio para detalle sin generar archivos enormes. "
            "Las poses guardadas son PNG con transparencia."))
        grid = Gtk.Grid(row_spacing=6, column_spacing=8)
        w = Gtk.SpinButton.new_with_range(64, 4096, 16); w.set_value(512)
        h = Gtk.SpinButton.new_with_range(64, 4096, 16); h.set_value(512)
        fps = Gtk.SpinButton.new_with_range(1, 60, 1); fps.set_value(12)
        for r, (lbl, wd) in enumerate((("Ancho (px)", w), ("Alto (px)", h), ("FPS", fps))):
            grid.attach(Gtk.Label(label=lbl, xalign=0), 0, r, 1, 1); grid.attach(wd, 1, r, 1, 1)
        box.append(grid)
        pres = Gtk.Box(spacing=4)
        for lbl, ww, hh, rec in (("512² ★", 512, 512, True), ("800×600", 800, 600, False), ("1024²", 1024, 1024, False),
                                 ("1280×720", 1280, 720, False), ("1920×1080", 1920, 1080, False)):
            b = Gtk.Button(label=lbl)
            if rec: b.set_tooltip_text("Recomendado")
            b.connect("clicked", lambda _, a=ww, z=hh: (w.set_value(a), h.set_value(z))); pres.append(b)
        box.append(pres)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label="Cancelar")
        cancel.connect("clicked", lambda _: (dlg.destroy(), (self.close() if self.anim_id is None and not getattr(self, "_started", False) else None)))
        ok = Gtk.Button(label="Crear escena"); ok.add_css_class("suggested-action")

        def go(_):
            self._started = True
            self.canvas.new_scene(int(w.get_value()), int(h.get_value()), int(fps.get_value()))
            dlg.destroy(); self._sync(); self._show_tutorial()
        ok.connect("clicked", go); row.append(cancel); row.append(ok); box.append(row); dlg.present()
        return False

    # proyecto
    def _ffilter(self, name, *pats):
        f = Gtk.FileFilter(); f.set_name(name)
        for p in pats: f.add_pattern(p)
        fl = Gio.ListStore.new(Gtk.FileFilter); fl.append(f); return fl

    def _save_project_dialog(self, on_done=None):
        from .. import projects
        dlg = Gtk.FileDialog(); dlg.set_title("Guardar proyecto (.alproj)")
        dlg.set_filters(self._ffilter("Proyecto AnimaLinux (*.alproj)", "*.alproj"))
        try: dlg.set_initial_folder(Gio.File.new_for_path(str(projects.ensure_dir())))
        except Exception: pass  # noqa: BLE001
        dlg.set_initial_name(f"{self.pose_entry.get_text().strip() or 'proyecto'}.alproj")
        dlg.save(self, None, lambda d, r: self._save_project_done(d, r, on_done))

    def _save_project_done(self, dlg, res, on_done):
        try: gf = dlg.save_finish(res)
        except GLib.Error: return
        path = gf.get_path()
        if not path.endswith(".alproj"): path += ".alproj"
        try:
            self.canvas.save_project(path); self._project_path = path
            self._flash(f"Proyecto guardado: {Path(path).name}")
            if on_done: on_done()
        except Exception as e:  # noqa: BLE001
            self._flash(f"No se pudo guardar: {e}")

    def _open_project_dialog(self):
        from .. import projects
        dlg = Gtk.FileDialog(); dlg.set_title("Abrir proyecto (.alproj)")
        dlg.set_filters(self._ffilter("Proyecto AnimaLinux (*.alproj)", "*.alproj"))
        try: dlg.set_initial_folder(Gio.File.new_for_path(str(projects.ensure_dir())))
        except Exception: pass  # noqa: BLE001
        dlg.open(self, None, self._open_project_done)

    def _open_project_done(self, dlg, res):
        try: gf = dlg.open_finish(res)
        except GLib.Error: return
        if self.canvas.load_project(gf.get_path()):
            self._project_path = gf.get_path(); self._sync(); self._flash("Proyecto abierto")
        else: self._flash("No se pudo abrir el proyecto")

    # importar
    def _import_image_dialog(self):
        dlg = Gtk.FileDialog(); dlg.set_title("Importar imagen a la celda actual")
        dlg.open(self, None, lambda d, r: self._file_done(d, r, self.canvas.import_image))

    def _import_seq_dialog(self):
        dlg = Gtk.FileDialog(); dlg.set_title("Importar secuencia de imágenes")
        dlg.open_multiple(self, None, self._seq_done)

    def _seq_done(self, dlg, res):
        try: files = dlg.open_multiple_finish(res)
        except GLib.Error: return
        paths = sorted(f.get_path() for f in files)
        self.canvas.import_sequence(paths); self._flash(f"{len(paths)} imágenes importadas")

    def _file_done(self, dlg, res, cb):
        try: gf = dlg.open_finish(res)
        except GLib.Error: return
        cb(gf.get_path()); self._sync()

    def _import_audio(self):
        dlg = Gtk.FileDialog(); dlg.set_title("Seleccionar archivo de audio")
        dlg.open(self, None, self._audio_done)

    def _audio_done(self, dlg, res):
        try: gf = dlg.open_finish(res)
        except GLib.Error: return
        self.canvas.scene.audio = gf.get_path(); self._sync(); self.timeline.refresh()
        self._flash("Audio cargado: se reproduce con ▶ (requiere mpv)")

    # exportar
    def _range(self):
        s = self.canvas.scene; return range(s.start, s.stop + 1)

    def _export_gif_dialog(self):
        dlg = Gtk.FileDialog(); dlg.set_title("Guardar como GIF animado"); dlg.set_initial_name("animacion.gif")
        dlg.save(self, None, self._gif_done)

    def _gif_done(self, dlg, res):
        try: gf = dlg.save_finish(res)
        except GLib.Error: return
        path = gf.get_path()
        if not path.lower().endswith(".gif"): path += ".gif"
        frames = [self.canvas.to_pil(i) for i in self._range()]
        if not frames: return
        frames[0].save(path, format="GIF", save_all=True, append_images=frames[1:], loop=0,
                       duration=max(20, 1000 // self.canvas.scene.fps), disposal=2)
        self._flash(f"GIF guardado: {Path(path).name}")

    def _export_mp4_dialog(self):
        dlg = Gtk.FileDialog(); dlg.set_title("Exportar como MP4"); dlg.set_initial_name("animacion.mp4")
        dlg.save(self, None, self._mp4_done)

    def _mp4_done(self, dlg, res):
        try: gf = dlg.save_finish(res)
        except GLib.Error: return
        out = gf.get_path(); s = self.canvas.scene
        if not out.lower().endswith(".mp4"): out += ".mp4"
        tmp = tempfile.mkdtemp(prefix="animalinux_mp4_")
        try:
            for k, i in enumerate(self._range()):
                im = self.canvas.to_pil(i)
                bg = __import__("PIL.Image", fromlist=["Image"]).new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[3]); bg.save(f"{tmp}/frame_{k:04d}.png")
            cmd = ["ffmpeg", "-y", "-framerate", str(s.fps), "-i", f"{tmp}/frame_%04d.png"]
            if s.audio: cmd += ["-i", s.audio, "-shortest"]
            cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", out]
            r = subprocess.run(cmd, capture_output=True)
            self._flash(f"MP4 guardado: {Path(out).name}" if r.returncode == 0 else "Error: ffmpeg no encontrado o falló.")
        except FileNotFoundError:
            self._flash("Error: ffmpeg no está instalado.")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _export_png_dialog(self):
        dlg = Gtk.FileDialog(); dlg.set_title("Elige la carpeta para la secuencia PNG")
        dlg.select_folder(self, None, self._png_done)

    def _png_done(self, dlg, res):
        try: gf = dlg.select_folder_finish(res)
        except GLib.Error: return
        dest = Path(gf.get_path())
        for k, i in enumerate(self._range()): self.canvas.to_pil(i).save(dest / f"frame_{k:04d}.png")
        self._flash(f"Secuencia PNG guardada en {dest.name}/")

    # ── guardar pose ─────────────────────────────────────────────────────────
    def _save_pose(self):
        pose = self.pose_entry.get_text().strip() or "default"
        s = self.canvas.scene; fps = s.fps
        from ..core import image_processor as importer
        n = len(self._range())
        if self.anim_id is None:
            name = (self.name_entry.get_text().strip() if self.name_entry else "Sin nombre") or "Sin nombre"
            aid = self.app.library.new_id(); fd = self.app.library.frames_dir(aid)
            pose_dir = fd if pose == "default" else fd / pose
            pose_dir.mkdir(parents=True, exist_ok=True); self._export_frames(pose_dir)
            self.app.library.add(aid, name, n, s.w, s.h); self.app.library.update(aid, fps=fps)
            importer.ensure_flipped(pose_dir)
            if pose != "default": self.app.register_pose(aid, pose, fps)
            self.anim_id = aid; self._flash(f"Animación «{name}» creada.")
        else:
            fd = self.app.library.frames_dir(self.anim_id)
            pose_dir = fd if pose == "default" else fd / pose
            pose_dir.mkdir(parents=True, exist_ok=True); self._export_frames(pose_dir)
            importer.ensure_flipped(pose_dir); self.app.register_pose(self.anim_id, pose, fps)
            self._flash(f"Pose «{pose}» guardada.")
        if self.app.control: self.app.control.refresh()
        if self._guided: self._suggest_next_pose()

    def _export_frames(self, dest):
        for k, i in enumerate(self._range()):
            self.canvas.to_pil(i).save(dest / f"frame_{k:04d}.png")

    def _suggest_next_pose(self):
        if not self.anim_id: return
        from .. import tips
        anim = self.app.library.animations.get(self.anim_id, {})
        nxt = tips.next_missing(anim.get("poses", []))
        if nxt: self.pose_entry.set_text(nxt); self._show_tip(nxt)
        else: self._flash("¡Todas las poses creadas!")

    def _show_tip(self, pose):
        from .. import tips
        info = tips.tip_for(pose)
        md = Gtk.AlertDialog(); md.set_message(f"Siguiente: {info['titulo']}  (~{info['frames']} cuadros)")
        md.set_detail("\n".join(f"• {t}" for t in info["tips"])); md.set_buttons(["Entendido"]); md.show(self)

    # ── cerrar ───────────────────────────────────────────────────────────────
    def _on_close_request(self, *_):
        self._playing = False
        if self._play_id: GLib.source_remove(self._play_id); self._play_id = None
        self._stop_audio()
        if self._status_id: GLib.source_remove(self._status_id); self._status_id = None
        release_signals(self, [self._grp])
        GLib.idle_add(self._teardown)
        return False

    def _teardown(self):
        """Rompe los ciclos ventana↔widgets↔callbacks (invisibles para el recolector de
        Python) para que al cerrar se libere la escena y los dibujos."""
        c = self.canvas
        c._stop_ants()
        for n in ("on_pick", "on_frame", "on_layers", "on_cursor", "on_zoom", "on_status", "on_tool", "on_edit"):
            setattr(c, n, None)
        c.scene = ae.Scene(8, 8); c._clip = None; c.sel = None
        if self.get_child() is not None: self.set_child(None)
        self.__dict__.clear()
        return False

    def _confirm_close(self):
        dlg = Gtk.AlertDialog(); dlg.set_message("¿Cerrar el editor de animación?")
        dlg.set_detail("Guarda la pose (Ctrl+S) para usarla en tu mascota, o el proyecto (Ctrl+Shift+S) para seguir editándolo con capas.")
        dlg.set_buttons(["Cancelar", "Guardar pose y cerrar", "Guardar proyecto y cerrar", "Cerrar sin guardar"])
        dlg.set_cancel_button(0); dlg.set_default_button(1)
        dlg.choose(self, None, self._confirm_done)

    def _confirm_done(self, dlg, res):
        try: idx = dlg.choose_finish(res)
        except Exception: return  # noqa: BLE001
        if idx == 1: self._save_pose(); self.close()
        elif idx == 2: self._save_project_dialog(on_done=self.close)
        elif idx == 3: self.close()

    # ── tutorial ─────────────────────────────────────────────────────────────
    _TOOL_HELP = [(ic, tip.split(" — ")[0], k) for _t, ic, tip, k in TOOLS]

    @staticmethod
    def _grid(items):
        flow = Gtk.FlowBox(); flow.set_selection_mode(Gtk.SelectionMode.NONE); flow.set_max_children_per_line(2)
        flow.set_column_spacing(8); flow.set_row_spacing(8); flow.set_homogeneous(True)
        for icon, name, tag in items: flow.append(gw.item_row(gw.icon_badge(icon_image(icon, 18)), name, tag_text=tag))
        return flow

    def _show_tutorial(self, force=False):
        from .. import settings as _s
        if not force and _s.get("tutorial_paint_shown", False): return
        dlg = Gtk.Dialog(title="Editor de Animación — Guía rápida", transient_for=self, modal=True)
        dlg.set_default_size(620, 720)
        box = dlg.get_content_area(); box.set_spacing(0)
        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for m in ("start", "end"): getattr(content, f"set_margin_{m}")(20)
        content.set_margin_top(16); content.set_margin_bottom(16)
        content.append(gw.body("Editor de animación con la disposición de Toon Boom Harmony: caja de herramientas, vista con "
                               "pestañas Dibujo/Cámara, paneles a la derecha y una línea de tiempo con hoja de exposición."))
        content.append(gw.section_title("FLUJO RECOMENDADO"))
        st = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for i, s in enumerate([
            "Crea la escena (tamaño y FPS) y dibuja en la celda del fotograma 1 con el pincel (B).",
            "Avanza con «.» y dibuja el siguiente fotograma; activa el papel cebolla (Alt+O) como guía.",
            "Mantén un dibujo varios fotogramas con F5 (extender exposición); F6 crea un dibujo nuevo en la celda.",
            "Usa capas separadas (línea, color, fondo) y una capa vectorial si quieres editar los trazos.",
            "Reproduce con Enter, ajusta Inicio/Fin/FPS y guarda la pose (Ctrl+S) o el proyecto (Ctrl+Shift+S).",
        ], start=1): st.append(gw.step_row(i, s))
        content.append(st)
        content.append(gw.section_title("HERRAMIENTAS"))
        content.append(self._grid(self._TOOL_HELP))
        content.append(gw.section_title("CAPAS Y EXPOSICIÓN"))
        content.append(gw.note("Cada capa tiene dibujos y una exposición: qué dibujo se ve en cada fotograma. Ojo = visible, candado = "
                               "bloqueada, círculo = papel cebolla. Clic derecho en una celda: dibujo nuevo, duplicar, extender, limpiar."))
        content.append(gw.section_title("CÁMARA"))
        content.append(gw.note("En la pestaña Cámara mueve (arrastrar), gira (Alt+arrastrar) y escala (rueda) la cámara; cada cambio crea una "
                               "clave y la cámara se interpola entre claves. Se aplica al exportar y al guardar la pose."))
        content.append(gw.section_title("VISTA"))
        content.append(gw.note("Rueda = zoom · Espacio+arrastrar = mover · Alt+O papel cebolla · Shift+L mesa de luz · vista espejo para "
                               "revisar proporciones · clic derecho usa el color de fondo · Alt+clic = cuentagotas."))
        content.append(gw.note("No incluye la vista de nodos ni el rigging de recortes de Harmony."))
        sc.set_child(content); box.append(sc)
        footer = Gtk.Box(spacing=10)
        footer.set_margin_start(14); footer.set_margin_end(14); footer.set_margin_top(8); footer.set_margin_bottom(10)
        ns = Gtk.CheckButton(label="No mostrar al iniciar el editor"); ns.set_hexpand(True); footer.append(ns)
        ok = Gtk.Button(label="✓  Entendido"); ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: (_s.set_val("tutorial_paint_shown", ns.get_active()), dlg.destroy()))
        footer.append(ok); box.append(footer); dlg.present()


def c_zoom(editor, f):
    editor.canvas.zoom_at(f)
