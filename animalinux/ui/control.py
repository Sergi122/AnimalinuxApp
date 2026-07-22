"""
Ventana de configuración — AnimaLinux.
Dos pestañas: animaciones normales (GIF en bucle) y con vida (camina sola).
La creación siempre pregunta: importar / píxeles / dibujo libre / continuar proyecto.
"""
import threading

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk, Gio

from ..core import image_processor as importer
from ..core import gpu
from ..overlay import BACKEND
from ..overlay.live_animation import MANDATORY_POSES
from ..i18n import t
from . import guide_widgets as gw

# orden de presentación en la guía de poses + emoji ilustrativo de cada una
POSE_GUIDE_ORDER = (
    ("default", "🧍"), ("idle", "💤"), ("walk", "🚶"), ("greet", "👋"),
    ("kiss", "😘"), ("jump", "🦘"), ("angry", "😠"), ("grab", "✊"),
)

BG_METHODS = [
    ("bg_ai", "ai"),
    ("bg_chroma", "chroma"),
    ("bg_none", "none"),
]


class ControlWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=t("app_title"))
        self.app = app
        self.set_default_size(640, 760)
        # timers de las previews GIF animadas (se limpian en cada refresh)
        self._preview_timers = []
        self.connect("close-request", self._stop_previews)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(root)

        # barra superior: estado + botón configuración
        topbar = Gtk.Box(spacing=6)
        topbar.set_margin_start(12); topbar.set_margin_end(8)
        topbar.set_margin_top(4); topbar.set_margin_bottom(2)
        self.status = Gtk.Label(label="", xalign=0)
        self.status.add_css_class("dim-label")
        self.status.set_hexpand(True)
        topbar.append(self.status)
        cfg_btn = Gtk.Button(label=t("settings_title"))
        cfg_btn.set_tooltip_text(t("lang_label"))
        cfg_btn.connect("clicked", lambda _: self._show_settings_dialog())
        topbar.append(cfg_btn)
        close_btn = Gtk.Button(label="✕")
        close_btn.set_tooltip_text("Cerrar esta ventana (las mascotas siguen activas)")
        close_btn.add_css_class("close-btn")
        close_btn.connect("clicked", lambda _: self.close())
        topbar.append(close_btn)
        root.append(topbar)

        # Aviso: sin GPU real (render por software, típico de una VM sin
        # passthrough gráfico), el compositor de algunos gestores de
        # ventanas X11 (xfwm4, Muffin...) puede fallar al mostrar varias
        # mascotas fullscreen a la vez -- cada una es su propia ventana
        # ARGB, y sin aceleración por hardware el compositor no siempre da
        # abasto. No aplica en Wayland/Hyprland ni con GPU real: se detecta
        # una sola vez al abrir y solo se muestra si hace falta (ver
        # refresh()).
        self._software_gpu = BACKEND == "x11" and gpu.is_software_rendering() is True
        self._gpu_warning = Gtk.Label(xalign=0)
        self._gpu_warning.add_css_class("dim-label")
        self._gpu_warning.set_wrap(True)
        self._gpu_warning.set_margin_start(12); self._gpu_warning.set_margin_end(12)
        self._gpu_warning.set_margin_bottom(4)
        self._gpu_warning.set_markup(GLib.markup_escape_text(t("gpu_warning")))
        self._gpu_warning.set_visible(False)
        root.append(self._gpu_warning)

        # pestañas
        self.notebook = Gtk.Notebook()
        self.notebook.set_vexpand(True)
        root.append(self.notebook)

        self.notebook.append_page(self._build_normal_tab(),
                                  Gtk.Label(label=t("tab_normal")))
        self.notebook.append_page(self._build_vida_tab(),
                                  Gtk.Label(label=t("tab_vida")))

        # pie: enlace a la web (más animaciones / compartir las tuyas)
        footer = Gtk.Box(spacing=6)
        footer.set_halign(Gtk.Align.CENTER)
        footer.set_margin_top(4); footer.set_margin_bottom(8)
        footer.set_margin_start(12); footer.set_margin_end(12)
        web = Gtk.Label()
        web.add_css_class("dim-label")
        web.set_use_markup(True)
        web.set_markup(
            '🌐 ¿Buscas más animaciones o quieres compartir las tuyas?  '
            '<a href="https://sergi122.github.io/Animalinux/">'
            'sergi122.github.io/Animalinux</a>')
        footer.append(web)
        root.append(footer)

        self.refresh()

    # ── Tab Normal ──────────────────────────────────────────────────────────
    def _build_normal_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10); box.set_margin_start(12)
        box.set_margin_end(12); box.set_margin_bottom(8)

        btn = Gtk.Button(label=t("new_normal"))
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda _: self._ask_create(life=False))
        box.append(btn)

        # Fila 1: importar video/gif (los packs .alpack son solo para
        # animaciones "con vida" — ver _build_vida_tab)
        imp1 = Gtk.Box(spacing=6)
        imp1.set_margin_bottom(2)
        imp1.append(Gtk.Label(label=t("import_label")))
        gif_btn = Gtk.Button(label=t("import_gif"))
        gif_btn.connect("clicked", lambda _: self._import_media("gif"))
        imp1.append(gif_btn)
        mp4_btn = Gtk.Button(label=t("import_video"))
        mp4_btn.connect("clicked", lambda _: self._import_media("video"))
        imp1.append(mp4_btn)
        box.append(imp1)

        # Fila 2: spritesheet
        imp2 = Gtk.Box(spacing=6)
        sheet_btn = Gtk.Button(label=t("spritesheet"))
        sheet_btn.set_tooltip_text("Corta una tira de sprites en fotogramas")
        sheet_btn.connect("clicked", self._on_import_sheet)
        imp2.append(sheet_btn)
        imp2.append(Gtk.Label(label=t("cols")))
        self.sheet_cols = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=64, step_increment=1))
        self.sheet_cols.set_size_request(60, -1)
        imp2.append(self.sheet_cols)
        box.append(imp2)

        bg = Gtk.Box(spacing=6)
        bg.append(Gtk.Label(label=t("bg_method")))
        self.method_combo = Gtk.DropDown.new_from_strings(
            [t(m[0]) for m in BG_METHODS])
        self.method_combo.set_selected(0)
        bg.append(self.method_combo)
        box.append(bg)

        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        self._normal_list = Gtk.ListBox()
        self._normal_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._normal_list.add_css_class("boxed-list")
        sc.set_child(self._normal_list)
        box.append(sc)
        return box

    # ── Tab Vida ────────────────────────────────────────────────────────────
    def _build_vida_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10); box.set_margin_start(12)
        box.set_margin_end(12); box.set_margin_bottom(8)

        top = Gtk.Box(spacing=6)
        btn = Gtk.Button(label=t("new_vida"))
        btn.add_css_class("suggested-action")
        btn.set_hexpand(True)
        btn.connect("clicked", lambda _: self._ask_create(life=True))
        top.append(btn)
        help_btn = Gtk.Button(label=t("vida_help"))
        help_btn.set_tooltip_text("Ver guía de poses, nombres y estructura de carpetas")
        help_btn.connect("clicked", lambda _: self._show_vida_help())
        top.append(help_btn)
        box.append(top)

        imp = Gtk.Box(spacing=6)
        imp.append(Gtk.Label(label=t("import_folder")))
        folder_btn = Gtk.Button(label=t("folder_mascot"))
        folder_btn.set_tooltip_text(
            "Carpeta = mascota; subcarpetas = acciones (idle, walk, greet, jump, angry, grab…)")
        folder_btn.connect("clicked", self._on_import_folder)
        imp.append(folder_btn)
        box.append(imp)

        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        self._life_list = Gtk.ListBox()
        self._life_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._life_list.add_css_class("boxed-list")
        sc.set_child(self._life_list)
        box.append(sc)
        return box

    # ── Diálogo de creación ─────────────────────────────────────────────────
    def _ask_create(self, life=False):
        dialog = Gtk.Dialog(
            title=t("how_create_vida") if life else t("how_create"),
            transient_for=self, modal=True)
        dialog.set_default_size(560, 240)
        box = dialog.get_content_area()
        box.set_spacing(12); box.set_margin_start(16); box.set_margin_end(16)
        box.set_margin_top(14); box.set_margin_bottom(14)

        lbl = Gtk.Label()
        question = t("how_create_vida") if life else t("how_create")
        lbl.set_markup(f"<b>{question}</b>")
        lbl.set_justify(Gtk.Justification.CENTER)
        box.append(lbl)

        btn_row = Gtk.Box(spacing=8, homogeneous=True)
        btn_row.set_margin_top(8)

        def _opt(icon_name, title, desc, cb):
            vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            vb.set_margin_top(8); vb.set_margin_bottom(8)
            vb.set_margin_start(4); vb.set_margin_end(4)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(22)
            vb.append(icon)
            tl = Gtk.Label(label=title)
            tl.set_markup(f"<b>{title}</b>")
            vb.append(tl)
            dl = Gtk.Label(label=desc)
            dl.add_css_class("dim-label")
            dl.set_justify(Gtk.Justification.CENTER)
            vb.append(dl)
            b = Gtk.Button()
            b.set_child(vb)
            b.connect("clicked", lambda _: (dialog.destroy(), cb()))
            return b

        btn_row.append(_opt(
            "document-open-symbolic", t("btn_import"),
            t("btn_import_desc_vida") if life else t("btn_import_desc"),
            lambda: self._start_import(life=life)))
        btn_row.append(_opt("applications-graphics-symbolic", t("btn_pixel"),
                            t("btn_pixel_desc"),
                            lambda: self.app.show_pixel_editor(guided=life)))
        btn_row.append(_opt("edit-symbolic", t("btn_paint"), t("btn_paint_desc"),
                            lambda: self.app.show_paint_editor(guided=life)))
        btn_row.append(_opt("folder-open-symbolic", t("btn_continue"),
                            t("btn_continue_desc"),
                            lambda: self._show_projects_dialog()))
        box.append(btn_row)

        footer = Gtk.Box(); footer.set_halign(Gtk.Align.END)
        footer.set_margin_top(6)
        cancel_btn = Gtk.Button(label=t("cancel"))
        cancel_btn.connect("clicked", lambda _: dialog.destroy())
        footer.append(cancel_btn)
        box.append(footer)
        dialog.present()

    # ── Previews animadas ─────────────────────────────────────────────────────
    def _stop_previews(self, *_):
        for tid in self._preview_timers:
            GLib.source_remove(tid)
        self._preview_timers = []
        return False

    # ── Refresh ─────────────────────────────────────────────────────────────
    def refresh(self):
        self._stop_previews()   # cancela timers de previews de la tanda anterior
        for lb in (self._normal_list, self._life_list):
            child = lb.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                lb.remove(child); child = nxt

        anims = self.app.library.animations
        normals = [a for a in anims.values() if a.get("mode", "gif") != "life"]
        lives   = [a for a in anims.values() if a.get("mode") == "life"]

        if not anims:
            self.status.set_text("Sin animaciones todavía — crea la primera arriba.")
        else:
            self.status.set_text(
                f"{len(normals)} animación(es) GIF · {len(lives)} con vida")

        active_count = sum(1 for a in anims.values() if a.get("on_desktop"))
        self._gpu_warning.set_visible(self._software_gpu and active_count > 1)

        for a in normals:
            self._normal_list.append(self._make_normal_row(a))
        for a in lives:
            self._life_list.append(self._make_life_row(a))

    # ── Fila animación normal ────────────────────────────────────────────────
    def _make_normal_row(self, anim):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.add_css_class("mascot-card")
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(6); box.set_margin_end(6)

        box.append(self._animated_preview(anim))

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info.set_hexpand(True)
        info.set_valign(Gtk.Align.CENTER)
        info.append(self._editable_name(anim))
        info.append(self._fps_scale_row(anim))
        box.append(info)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        sw = Gtk.Switch()
        sw.set_active(anim.get("on_desktop", False))
        sw.set_halign(Gtk.Align.END)
        sw.set_tooltip_text(t("show_desktop"))
        sw.connect("state-set",
                   lambda s, st, aid=anim["id"]: self._on_toggle(aid, st))
        col.append(sw)

        # Editar: SOLO para contenido creado/empaquetado con la app (packs de la
        # app, dibujo, spritesheet, imagen estática). Un GIF/MP4 importado trae
        # su propia animación y no se edita frame a frame → no se muestra Editar.
        if not anim.get("source_animated"):
            edit_r = Gtk.Box(spacing=4)
            b1 = Gtk.Button(label=t("edit_pixel"))
            b1.connect("clicked",
                       lambda _, aid=anim["id"]: self.app.show_pixel_editor(
                           anim_id=aid, pose="default"))
            b2 = Gtk.Button(label=t("edit_paint"))
            b2.connect("clicked",
                       lambda _, aid=anim["id"]: self.app.show_paint_editor(
                           anim_id=aid, pose="default"))
            edit_r.append(b1); edit_r.append(b2)
            col.append(edit_r)

        exp_btn = Gtk.Button(label=t("export"))
        exp_btn.connect("clicked",
                        lambda _, aid=anim["id"]: self._on_export_pack(aid))
        col.append(exp_btn)

        del_btn = Gtk.Button(label=t("delete"))
        del_btn.add_css_class("destructive-action")
        del_btn.connect("clicked", lambda _, aid=anim["id"]: self._on_delete(aid))
        col.append(del_btn)

        box.append(col)
        row.set_child(box)
        return row

    # ── Fila animación con vida ──────────────────────────────────────────────
    def _make_life_row(self, anim):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.add_css_class("mascot-card")
        box.add_css_class("card-life")
        box.set_margin_top(6); box.set_margin_bottom(6)
        box.set_margin_start(6); box.set_margin_end(6)

        box.append(self._animated_preview(anim))

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info.set_hexpand(True)
        info.append(self._editable_name(anim))
        info.append(self._fps_scale_row(anim))

        info.append(self._pose_toggles_row(anim))

        add_r = Gtk.Box(spacing=4)
        add_r.append(Gtk.Label(label=t("add_pose")))
        ap1 = Gtk.Button(label=t("add_pose_pixel"))
        ap1.connect("clicked",
                    lambda _, aid=anim["id"]: self.app.show_pixel_editor(
                        anim_id=aid, guided=True))
        ap2 = Gtk.Button(label=t("add_pose_paint"))
        ap2.connect("clicked",
                    lambda _, aid=anim["id"]: self.app.show_paint_editor(
                        anim_id=aid, guided=True))
        add_r.append(ap1); add_r.append(ap2)
        info.append(add_r)
        box.append(info)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        sw = Gtk.Switch()
        sw.set_active(anim.get("on_desktop", False))
        sw.set_halign(Gtk.Align.END)
        sw.set_tooltip_text(t("show_desktop"))
        sw.connect("state-set",
                   lambda s, st, aid=anim["id"]: self._on_toggle(aid, st))
        col.append(sw)

        exp = Gtk.Button(label=t("export"))
        exp.connect("clicked", lambda _, aid=anim["id"]: self._on_export_pack(aid))
        col.append(exp)

        del_btn = Gtk.Button(label=t("delete"))
        del_btn.add_css_class("destructive-action")
        del_btn.connect("clicked", lambda _, aid=anim["id"]: self._on_delete(aid))
        col.append(del_btn)

        box.append(col)
        row.set_child(box)
        return row

    # ── Widgets reutilizables ─────────────────────────────────────────────────
    def _animated_preview(self, anim, size=64):
        """Preview que reproduce la animación (GIF) en pequeño dentro de la card."""
        pic = Gtk.Picture()
        pic.set_size_request(size, size)
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        pic.add_css_class("card-preview")
        fd = self.app.library.frames_dir(anim["id"])
        textures = []
        for p in sorted(fd.glob("frame_*.png"))[:60]:
            try:
                textures.append(Gdk.Texture.new_from_filename(str(p)))
            except GLib.Error:
                pass
        if not textures:
            return pic
        pic.set_paintable(textures[0])
        if len(textures) > 1:
            state = {"i": 0}
            fps = max(1, int(anim.get("fps", 12)))

            def tick():
                if pic.get_parent() is None:
                    return False   # card destruida (refresh) → cancela el timer
                state["i"] = (state["i"] + 1) % len(textures)
                pic.set_paintable(textures[state["i"]])
                return True

            self._preview_timers.append(GLib.timeout_add(int(1000 / fps), tick))
        return pic

    def _editable_name(self, anim):
        """Nombre editable in situ; guarda al pulsar Enter o salir del campo."""
        entry = Gtk.Entry()
        entry.set_text(anim["name"])
        entry.add_css_class("card-title")
        entry.set_hexpand(True)
        entry.set_has_frame(False)
        entry.set_tooltip_text("Editar nombre (Enter para guardar)")

        def save(*_):
            new = entry.get_text().strip()
            if new and new != anim["name"]:
                self.app.library.update(anim["id"], name=new)
                anim["name"] = new
            return False

        entry.connect("activate", save)
        foc = Gtk.EventControllerFocus()
        foc.connect("leave", save)
        entry.add_controller(foc)
        return entry

    def _fps_scale_row(self, anim):
        row = Gtk.Box(spacing=6)
        row.append(Gtk.Label(label=t("fps_label")))
        adj = Gtk.Adjustment(value=anim.get("fps", 12), lower=1, upper=60,
                             step_increment=1)
        spin = Gtk.SpinButton(adjustment=adj)
        spin.set_size_request(70, -1)
        spin.connect("value-changed",
                     lambda s, aid=anim["id"]: self._on_fps(aid, int(s.get_value())))
        row.append(spin)
        row.append(Gtk.Label(label="×"))
        sadj = Gtk.Adjustment(value=anim.get("scale", 1.0), lower=0.2, upper=4.0,
                              step_increment=0.1)
        ssp = Gtk.SpinButton(adjustment=sadj, digits=1)
        ssp.set_size_request(70, -1)
        ssp.connect("value-changed",
                    lambda s, aid=anim["id"]: self._on_scale(
                        aid, round(s.get_value(), 1)))
        row.append(ssp)
        return row

    def _pose_toggles_row(self, anim):
        """Chips «Poses:» con un checkbutton por pose OPCIONAL (greet, kiss,
        angry, sleep, grab...) para que el usuario decida cuáles usa la
        mascota en modo Vida sin borrar el dibujo — solo se guarda en
        "disabled_poses". "default"/"walk"/"jump" son obligatorias (ver
        MANDATORY_POSES): sin ellas la mascota no se movería de forma
        creíble, así que ni se muestran como desactivables."""
        poses = [p for p in anim.get("poses", ["default"])
                 if p not in MANDATORY_POSES]

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl = Gtk.Label(label=t("active_poses"), xalign=0)
        lbl.add_css_class("dim-label")
        outer.append(lbl)

        if not poses:
            hint = Gtk.Label(label=t("active_poses_hint"), xalign=0)
            hint.add_css_class("dim-label")
            outer.append(hint)
            return outer

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(6)
        flow.set_row_spacing(2)
        flow.set_column_spacing(10)

        disabled = set(anim.get("disabled_poses", []))
        for pose in poses:
            chk = Gtk.CheckButton(label=pose)
            chk.set_active(pose not in disabled)
            chk.set_tooltip_text(f"Usar la pose «{pose}» en modo Vida")
            chk.connect("toggled", self._on_pose_toggled, anim["id"], pose)
            flow.append(chk)
        outer.append(flow)
        return outer

    def _on_pose_toggled(self, chk, anim_id, pose):
        anim = self.app.library.animations.get(anim_id, {})
        disabled = set(anim.get("disabled_poses", []))
        if chk.get_active():
            disabled.discard(pose)
        else:
            disabled.add(pose)
        self.app.library.update(anim_id, disabled_poses=sorted(disabled))
        self.app.reload_mascot(anim_id)

    # ── Importar GIF / MP4 directo desde el tab Normal ───────────────────────
    def _import_media(self, kind="gif"):
        """Botón rápido en tab Normal: abre el picker filtrado por tipo."""
        self._pending_live = False
        dialog = Gtk.FileDialog()
        if kind == "video":
            dialog.set_title("Elige un vídeo corto (MP4, WebM, MOV, AVI, M4V…)")
        else:
            dialog.set_title("Elige una animación (GIF, WebP animado, APNG…)")

        # Filtro de archivo
        store = Gio.ListStore.new(Gtk.FileFilter)
        f = Gtk.FileFilter()
        if kind == "video":
            f.set_name("Vídeos (MP4, WebM, MOV, AVI, M4V)")
            for pat in ("*.mp4", "*.webm", "*.mov", "*.avi", "*.m4v"):
                f.add_pattern(pat)
        else:
            f.set_name("Animaciones (GIF, WebP, APNG, PNG)")
            for pat in ("*.gif", "*.webp", "*.apng", "*.png"):
                f.add_pattern(pat)
        store.append(f)
        all_f = Gtk.FileFilter()
        all_f.set_name("Todos los archivos")
        all_f.add_pattern("*")
        store.append(all_f)
        dialog.set_filters(store)
        dialog.open(self, None, self._on_file_chosen)

    # ── Importar (gif / mp4 / imagen) ─────────────────────────────────────────
    def _start_import(self, life=False):
        self._pending_live = life
        dialog = Gtk.FileDialog()
        if life:
            dialog.set_title("Elige un pack .alpack")
            f = Gtk.FileFilter()
            f.set_name("Pack de AnimaLinux (.alpack)")
            f.add_pattern("*.alpack")
            store = Gio.ListStore.new(Gtk.FileFilter)
            store.append(f)
            dialog.set_filters(store)
            dialog.set_default_filter(f)
        else:
            dialog.set_title("Elige una animación (GIF, WebP, APNG, PNG, MP4…)")
        dialog.open(self, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        path = gfile.get_path()
        if path and path.lower().endswith(".alpack"):
            # el usuario eligió un pack .alpack desde un botón de GIF/vídeo/
            # imagen: es un error de bicicleta esperable (los botones están
            # uno al lado del otro), no un archivo inválido — se importa
            # igual, siempre como "con vida" (ver _import_pack_path).
            self._import_pack_path(path)
            return
        method = BG_METHODS[self.method_combo.get_selected()][1]
        live = getattr(self, "_pending_live", False)
        self.status.set_text("Procesando… (puede tardar si se usa IA)")

        def report(texto, frac):
            GLib.idle_add(self.status.set_text, f"{texto}… {int(frac*100)}%")

        def work():
            try:
                lib = self.app.library
                aid = lib.new_id()
                dest = lib.frames_dir(aid)
                fc, w, h, fps = importer.import_animation(
                    path, dest, bg_method=method, progress=report)
                name = gfile.get_basename().rsplit(".", 1)[0]
                GLib.idle_add(self._import_done, aid, name, fc, w, h, fps, live)
            except Exception as e:   # noqa: BLE001
                GLib.idle_add(self.status.set_text, f"Error al importar: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _import_done(self, aid, name, fc, w, h, fps, live=False):
        self.app.library.add(aid, name, fc, w, h)
        # Marca si el origen ya traía animación propia (GIF/WebP/APNG/vídeo con
        # >1 frame). Se usa para NO ofrecer «Editar» en esas (no se editan frame
        # a frame). Spritesheets entran por otra ruta y NO se marcan; las
        # imágenes estáticas dan fc == 1 → sí editables.
        self.app.library.update(aid, fps=fps, source_animated=(fc > 1))
        if live:
            self.app.library.update(aid, mode="life")
            self.status.set_text(
                f"«{name}» lista. Abriendo editor guiado para crear sus acciones…")
            self.refresh()
            # Offer guided editor
            self._ask_guided_editor(aid)
        else:
            self.status.set_text(
                f"«{name}» creada ({fc} cuadros). Usa «Editar» para ajustarla.")
            self.refresh()
        self._pending_live = False
        return False

    def _ask_guided_editor(self, aid):
        dialog = Gtk.Dialog(title=t("guided_editor_title"),
                            transient_for=self, modal=True)
        dialog.set_default_size(320, 160)
        box = dialog.get_content_area()
        box.set_spacing(10); box.set_margin_start(16); box.set_margin_end(16)
        box.set_margin_top(14); box.set_margin_bottom(14)
        box.append(Gtk.Label(label=t("guided_editor_desc")))
        row = Gtk.Box(spacing=8, homogeneous=True)
        b1 = Gtk.Button(label=t("btn_pixel"))
        b1.connect("clicked", lambda _: (dialog.destroy(),
                                         self.app.show_pixel_editor(anim_id=aid,
                                                                    guided=True)))
        b2 = Gtk.Button(label=t("btn_paint"))
        b2.connect("clicked", lambda _: (dialog.destroy(),
                                         self.app.show_paint_editor(anim_id=aid,
                                                                    guided=True)))
        row.append(b1); row.append(b2)
        box.append(row)

        footer = Gtk.Box(); footer.set_halign(Gtk.Align.END)
        footer.set_margin_top(4)
        cancel_btn = Gtk.Button(label=t("cancel"))
        cancel_btn.connect("clicked", lambda _: dialog.destroy())
        footer.append(cancel_btn)
        box.append(footer)
        dialog.present()

    # ── Handlers comunes ─────────────────────────────────────────────────────
    def _on_fps(self, aid, fps):
        self.app.library.update(aid, fps=fps)
        self.app.set_mascot_fps(aid, fps)

    def _on_scale(self, aid, scale):
        self.app.library.update(aid, scale=scale)
        self.app.set_mascot_scale(aid, scale)

    def _on_toggle(self, aid, state):
        self.app.library.update(aid, on_desktop=state)
        self.app.set_mascot_visible(aid, state)
        active_count = sum(
            1 for a in self.app.library.animations.values() if a.get("on_desktop"))
        self._gpu_warning.set_visible(self._software_gpu and active_count > 1)
        return False

    def _on_delete(self, aid):
        self.app.set_mascot_visible(aid, False)
        self.app.library.remove(aid)
        self.refresh()


    # ── Packs ────────────────────────────────────────────────────────────────
    def _import_pack_path(self, path):
        self.status.set_text("Importando pack…")

        def work():
            try:
                aid = self.app.import_pack(path)
                # los packs .alpack son siempre animaciones "con vida" (traen
                # sus propias poses walk/idle/greet/...) — nunca quedan en
                # modo "gif", venga la importación de donde venga.
                self.app.library.update(aid, mode="life")
                GLib.idle_add(self._pack_done)
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self.status.set_text, f"Error con el pack: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _pack_done(self):
        self.status.set_text("Pack importado.")
        self.refresh()
        return False

    def _on_export_pack(self, aid):
        anim = self.app.library.animations.get(aid, {})
        dialog = Gtk.FileDialog()
        dialog.set_title("Guardar pack")
        dialog.set_initial_name(f"{anim.get('name', 'mascota')}.alpack")
        dialog.save(self, None,
                    lambda d, r, aid=aid: self._on_pack_save(d, r, aid))

    def _on_pack_save(self, dialog, result, aid):
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return
        try:
            out = self.app.export_pack(aid, gfile.get_path())
            self.status.set_text(f"Pack exportado: {out.name}")
        except Exception as e:  # noqa: BLE001
            self.status.set_text(f"Error al exportar: {e}")

    # ── Carpeta vida ─────────────────────────────────────────────────────────
    def _on_import_folder(self, _btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Elige la carpeta de la mascota")
        dialog.select_folder(self, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog, result):
        try:
            gfile = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        self.status.set_text("Importando carpeta y validando…")

        def work():
            try:
                aid, problemas = self.app.import_life_folder(gfile.get_path())
                GLib.idle_add(self._folder_done, aid, problemas)
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self.status.set_text, f"Error: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _folder_done(self, aid, problemas):
        self.refresh()
        self.notebook.set_current_page(1)
        anim = self.app.library.animations.get(aid, {})
        poses_encontradas = set(anim.get("poses", []))
        self._show_folder_result(aid, poses_encontradas, problemas)
        return False

    def _show_folder_result(self, aid, poses_encontradas, problemas):
        from .. import folderimport as fi
        dlg = Gtk.Dialog(title=t("mascot_imported"), transient_for=self, modal=True)
        dlg.set_default_size(460, 420)
        box = dlg.get_content_area()
        box.set_spacing(0)

        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        tv = Gtk.TextView(); tv.set_editable(False); tv.set_cursor_visible(False)
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        tv.set_margin_start(16); tv.set_margin_end(16)
        tv.set_margin_top(12); tv.set_margin_bottom(12)
        buf = tv.get_buffer()

        lineas = ["POSES ENCONTRADAS\n" + "─" * 38 + "\n"]
        for pose in fi.KNOWN_POSES:
            if pose in poses_encontradas:
                aviso = ""
                if pose in problemas:
                    aviso = "  ⚠ " + "; ".join(problemas[pose])
                lineas.append(f"  ✔  {pose:<10}{aviso}")
            else:
                lineas.append(f"  ✘  {pose:<10}  (falta — añade subcarpeta '{pose}/')")

        extras = poses_encontradas - set(fi.KNOWN_POSES) - {"default"}
        if extras:
            lineas.append("\nPOSES EXTRA DETECTADAS")
            for p in sorted(extras):
                lineas.append(f"  ·  {p}")

        if "_general" in problemas:
            lineas.append("\n⚠  " + "\n   ".join(problemas["_general"]))

        lineas.append("\n" + "─" * 38)
        lineas.append("ESTRUCTURA ESPERADA\n")
        lineas.append("  NombreMascota/")
        for pose in fi.KNOWN_POSES:
            req = " ← obligatoria" if pose == "default" else ""
            estado = "✔" if pose in poses_encontradas else "✘"
            lineas.append(f"  {estado} {pose}/")
            lineas.append(f"      frame_0000.png …{req}")

        buf.set_text("\n".join(lineas))
        sc.set_child(tv)
        box.append(sc)

        ftr = Gtk.Box(spacing=8)
        ftr.set_margin_start(12); ftr.set_margin_end(12)
        ftr.set_margin_top(8); ftr.set_margin_bottom(10)
        ftr.set_halign(Gtk.Align.END)

        edit_btn = Gtk.Button(label=t("add_poses_editor"))
        edit_btn.connect("clicked", lambda _: (dlg.close(),
            self._ask_guided_editor(aid)))
        ftr.append(edit_btn)

        ok = Gtk.Button(label=t("done_btn"))
        ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: dlg.close())
        ftr.append(ok)
        box.append(ftr)
        dlg.present()

    # ── Spritesheet ──────────────────────────────────────────────────────────
    def _on_import_sheet(self, _btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Elige un spritesheet")
        dialog.open(self, None, self._on_sheet_chosen)

    def _on_sheet_chosen(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        path = gfile.get_path()
        if path and path.lower().endswith(".alpack"):
            self._import_pack_path(path)
            return
        cols = int(self.sheet_cols.get_value())
        self.status.set_text("Cortando spritesheet…")

        def work():
            try:
                self.app.import_spritesheet(gfile.get_path(), cols)
                GLib.idle_add(self._sheet_done)
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self.status.set_text, f"Error: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _sheet_done(self):
        self.status.set_text("Spritesheet importado.")
        self.refresh()
        return False

    # ── Diálogo de proyectos ─────────────────────────────────────────────────
    def _show_projects_dialog(self):
        from .. import projects as _proj
        dlg = Gtk.Dialog(title=t("projects_title"), transient_for=self, modal=True)
        dlg.set_default_size(520, 480)
        box = dlg.get_content_area()
        box.set_spacing(0)

        toolbar = Gtk.Box(spacing=6)
        toolbar.set_margin_start(12); toolbar.set_margin_end(12)
        toolbar.set_margin_top(10); toolbar.set_margin_bottom(6)
        folder_btn = Gtk.Button(label=t("projects_folder"))
        folder_btn.connect("clicked", lambda _: _proj.open_folder())
        toolbar.append(folder_btn)
        box.append(toolbar)

        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)

        projs = _proj.list_projects()
        if not projs:
            empty = Gtk.Label(label=t("projects_empty"))
            empty.set_justify(Gtk.Justification.CENTER)
            empty.set_margin_top(30); empty.set_margin_bottom(30)
            empty.set_margin_start(20); empty.set_margin_end(20)
            empty.add_css_class("dim-label")
            listbox.append(Gtk.ListBoxRow())
            listbox.get_first_child().set_child(empty)
        else:
            for proj in projs:
                row = Gtk.ListBoxRow()
                row_box = Gtk.Box(spacing=10)
                row_box.set_margin_start(12); row_box.set_margin_end(12)
                row_box.set_margin_top(10); row_box.set_margin_bottom(10)

                icon = Gtk.Image.new_from_icon_name("folder-symbolic")
                icon.set_pixel_size(20)
                icon.set_size_request(32, -1)
                row_box.append(icon)

                info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                info.set_hexpand(True)
                name_lbl = Gtk.Label(label=proj["name"], xalign=0)
                name_lbl.set_markup(f"<b>{proj['name']}</b>")
                info.append(name_lbl)
                meta_lbl = Gtk.Label(
                    label=f"{t('projects_modified')} {proj['modified']}  •  {proj['size_kb']} KB",
                    xalign=0)
                meta_lbl.add_css_class("dim-label")
                info.append(meta_lbl)
                row_box.append(info)

                open_btn = Gtk.Button(label=t("projects_open"))
                open_btn.add_css_class("suggested-action")
                path = proj["path"]
                open_btn.connect("clicked", lambda _, p=path: (
                    dlg.destroy(),
                    self.app.show_paint_editor_project(p)))
                row_box.append(open_btn)
                row.set_child(row_box)
                listbox.append(row)

        sc.set_child(listbox)
        box.append(sc)

        close_btn = Gtk.Button(label=t("cancel"))
        close_btn.set_margin_start(12); close_btn.set_margin_end(12)
        close_btn.set_margin_top(8); close_btn.set_margin_bottom(10)
        close_btn.set_halign(Gtk.Align.END)
        close_btn.connect("clicked", lambda _: dlg.destroy())
        box.append(close_btn)
        dlg.present()

    # ── Diálogo de configuración / idioma ────────────────────────────────────
    def _show_settings_dialog(self):
        from .. import i18n as _i18n
        dlg = Gtk.Dialog(title=t("settings_title"), transient_for=self, modal=True)
        dlg.set_default_size(360, 200)
        box = dlg.get_content_area()
        box.set_spacing(12)
        box.set_margin_start(20); box.set_margin_end(20)
        box.set_margin_top(16); box.set_margin_bottom(16)

        lang_row = Gtk.Box(spacing=10)
        lang_row.append(Gtk.Label(label=t("lang_label")))
        lang_codes = list(_i18n.LANGUAGES.keys())
        lang_names = [f"{_i18n.LANGUAGES[c]}  ({c})" for c in lang_codes]
        dd = Gtk.DropDown.new_from_strings(lang_names)
        cur = _i18n.get_language()
        dd.set_selected(lang_codes.index(cur) if cur in lang_codes else 0)
        dd.set_hexpand(True)
        lang_row.append(dd)
        box.append(lang_row)

        hint = Gtk.Label(label=t("lang_restart"))
        hint.add_css_class("dim-label")
        hint.set_wrap(True)
        box.append(hint)

        # Arranque automático al iniciar sesión
        from ..core import autostart
        auto_row = Gtk.Box(spacing=10)
        auto_lbl = Gtk.Label(label=t("autostart_label"), xalign=0)
        auto_lbl.set_hexpand(True)
        auto_lbl.set_wrap(True)
        auto_row.append(auto_lbl)
        auto_sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        auto_sw.set_active(autostart.is_enabled())
        auto_row.append(auto_sw)
        box.append(auto_row)

        auto_hint = Gtk.Label(label=t("autostart_hint"))
        auto_hint.add_css_class("dim-label")
        auto_hint.set_wrap(True)
        box.append(auto_hint)

        btn_row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=t("cancel"))
        cancel.connect("clicked", lambda _: dlg.destroy())
        btn_row.append(cancel)
        ok = Gtk.Button(label=t("ok"))
        ok.add_css_class("suggested-action")
        def _apply(_b):
            code = lang_codes[dd.get_selected()]
            _i18n.set_language(code)
            try:
                autostart.set_enabled(auto_sw.get_active())
            except OSError:
                pass
            dlg.destroy()
        ok.connect("clicked", _apply)
        btn_row.append(ok)
        box.append(btn_row)
        dlg.present()

    # ── Ayuda poses "Con vida" ───────────────────────────────────────────────
    @staticmethod
    def _guide_pose_row(emoji, name, desc, mandatory):
        tag = t("badge_mandatory") if mandatory else t("badge_optional")
        return gw.item_row(gw.emoji_badge(emoji), name, desc,
                            tag_text=tag,
                            tag_kind="mandatory" if mandatory else "optional",
                            highlight=mandatory)

    @staticmethod
    def _guide_folder_tree():
        # nombres de carpeta LITERALES que la app espera — no se traducen
        entries = [
            ("default", "default" in MANDATORY_POSES, "frame_0000.png, frame_0001.png…"),
            ("idle", "idle" in MANDATORY_POSES, "frame_0000.png … frame_0003.png"),
            ("walk", "walk" in MANDATORY_POSES, "frame_0000.png … frame_0007.png"),
            ("greet", "greet" in MANDATORY_POSES, None), ("kiss", "kiss" in MANDATORY_POSES, None),
            ("jump", "jump" in MANDATORY_POSES, None), ("angry", "angry" in MANDATORY_POSES, None),
            ("grab", "grab" in MANDATORY_POSES, None),
        ]
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.add_css_class("folder-tree")
        root = Gtk.Label(label="📁 mi_mascota/", xalign=0)
        box.append(root)
        for name, required, frames in entries:
            lbl = Gtk.Label(label=f"   📁 {name}/", xalign=0)
            if required:
                lbl.add_css_class("folder-required")
            box.append(lbl)
            if frames:
                sub = Gtk.Label(label=f"      🖼 {frames}", xalign=0)
                sub.add_css_class("dim-label")
                box.append(sub)
        return box

    def _show_vida_help(self):
        dlg = Gtk.Dialog(title="Guía: Animaciones con vida",
                         transient_for=self, modal=True)
        dlg.set_default_size(520, 620)
        box = dlg.get_content_area()
        box.set_spacing(0)

        sc = Gtk.ScrolledWindow(); sc.set_vexpand(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_start(20); content.set_margin_end(20)
        content.set_margin_top(16); content.set_margin_bottom(16)

        content.append(gw.body(t("guide_intro")))

        content.append(gw.section_title(t("guide_title_poses")))
        poses_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for key, emoji in POSE_GUIDE_ORDER:
            raw = t(f"guide_pose_{key}")
            name, _, desc = raw.partition(" — ")
            poses_box.append(self._guide_pose_row(
                emoji, name, desc, mandatory=(key in MANDATORY_POSES)))
        content.append(poses_box)
        content.append(gw.note(t("guide_only_default")))

        content.append(gw.section_title(t("guide_title_create")))
        content.append(gw.body(t("guide_create_intro")))
        steps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for i, line in enumerate(t("guide_steps").split("\n"), start=1):
            text = line.split(".", 1)[1].strip() if "." in line[:3] else line
            steps_box.append(gw.step_row(i, text))
        content.append(steps_box)
        content.append(gw.note(t("guide_add_existing")))

        content.append(gw.section_title(t("guide_title_folder")))
        folder_intro = t("guide_folder_intro").split("\n\n")[0]
        content.append(gw.body(folder_intro))
        content.append(self._guide_folder_tree())
        content.append(gw.note(t("guide_png_note")))

        sc.set_child(content)
        box.append(sc)

        footer = Gtk.Box()
        footer.set_margin_start(14); footer.set_margin_end(14)
        footer.set_margin_top(8); footer.set_margin_bottom(10)
        footer.set_halign(Gtk.Align.END)
        ok = Gtk.Button(label=t("understood_btn"))
        ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _: dlg.destroy())
        footer.append(ok)
        box.append(footer)
        dlg.present()
