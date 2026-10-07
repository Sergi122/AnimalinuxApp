"""
Ventana de configuración — AnimaLinux.
Dos pestañas: animaciones normales (GIF en bucle) y con vida (camina sola).
La creación siempre pregunta: importar / píxeles / dibujo libre / continuar proyecto.
"""
import os
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gdk, Gio

from .. import __version__
from ..core import image_processor as importer
from ..core import gpu
from ..overlay import BACKEND
from ..backends import current as _backend_mod
from ..overlay.live_animation import MANDATORY_POSES
from ..i18n import t, tr, N_
from . import guide_widgets as gw


def open_url(url: str) -> None:
    """Abre un enlace en el navegador (cada backend sabe cómo hacerlo sin
    romper al navegador, p.ej. sin heredar LD_PRELOAD en Linux)."""
    from ..backends import current as backend
    backend.open_url(url)


# orden de presentación en la guía de poses + emoji ilustrativo de cada una
POSE_GUIDE_ORDER = (
    ("default", "🧍"), ("idle", "💤"), ("walk", "🚶"), ("greet", "👋"),
    ("kiss", "😘"), ("jump", "🦘"), ("angry", "😠"), ("grab", "✊"),
    ("fall", "💫"),
)

BG_METHODS = [
    ("bg_ai", "ai"),
    ("bg_chroma", "chroma"),
    ("bg_none", "none"),
]


class ControlWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=t("app_title"))
        self.add_css_class("ctl")
        self.app = app
        self.set_default_size(1040, 760)
        # timers de las previews GIF animadas (se limpian en cada refresh)
        self._preview_timers = []
        self._filter = "all"          # all | life | gif
        self._query = ""
        self.connect("close-request", self._stop_previews)

        overlay = Gtk.Overlay()
        self.set_child(overlay)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        overlay.set_child(root)

        # aviso al arrastrar archivos encima de la ventana
        self._drop_hint = Gtk.Box(halign=Gtk.Align.FILL, valign=Gtk.Align.FILL)
        self._drop_hint.add_css_class("drop-hint")
        dl = Gtk.Label(label="⬇  " + t("drop_here"), hexpand=True, vexpand=True)
        self._drop_hint.append(dl)
        self._drop_hint.set_visible(False)
        self._drop_hint.set_can_target(False)
        overlay.add_overlay(self._drop_hint)
        dt = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        dt.connect("enter", lambda *_: (self._drop_hint.set_visible(True), Gdk.DragAction.COPY)[1])
        dt.connect("leave", lambda *_: self._drop_hint.set_visible(False))
        dt.connect("drop", self._on_drop)
        self.add_controller(dt)

        root.append(self._build_header())

        # Banner de actualización (se despliega solo si hay versión nueva)
        self._upd_rev = Gtk.Revealer()
        self._upd_rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._upd_bar = Gtk.Box(spacing=10)
        self._upd_bar.add_css_class("upd-banner")
        self._upd_bar.set_margin_start(18); self._upd_bar.set_margin_end(18)
        self._upd_bar.set_margin_top(10)
        self._upd_lbl = Gtk.Label(xalign=0, hexpand=True)
        self._upd_lbl.set_wrap(True)
        self._upd_bar.append(self._upd_lbl)
        self._upd_btn = Gtk.Button(label=t("upd_now"))
        self._upd_btn.add_css_class("suggested-action")
        self._upd_btn.add_css_class("pill")
        self._upd_btn.connect("clicked", lambda _b: self._run_update())
        self._upd_bar.append(self._upd_btn)
        self._upd_rev.set_child(self._upd_bar)
        root.append(self._upd_rev)
        self.refresh_update_banner()

        # Aviso: sin GPU real (render por software, típico de una VM sin
        # passthrough gráfico), el compositor de algunos gestores de
        # ventanas X11 (xfwm4, Muffin...) puede fallar al mostrar varias
        # mascotas fullscreen a la vez. Solo se muestra si hace falta.
        self._software_gpu = BACKEND == "x11" and gpu.is_software_rendering() is True
        self._gpu_warning = Gtk.Label(xalign=0)
        self._gpu_warning.add_css_class("dim-label")
        self._gpu_warning.set_wrap(True)
        self._gpu_warning.set_margin_start(18); self._gpu_warning.set_margin_end(18)
        self._gpu_warning.set_margin_top(6)
        self._gpu_warning.set_markup(GLib.markup_escape_text(t("gpu_warning")))
        self._gpu_warning.set_visible(False)
        root.append(self._gpu_warning)

        root.append(self._build_toolbar())

        # contenido: cuadrícula de tarjetas o estado vacío
        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(260)
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._flow = Gtk.FlowBox()
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_homogeneous(True)
        self._flow.set_min_children_per_line(1)
        self._flow.set_max_children_per_line(8)
        self._flow.set_column_spacing(16); self._flow.set_row_spacing(16)
        self._flow.set_valign(Gtk.Align.START)
        self._flow.set_margin_start(18); self._flow.set_margin_end(18)
        self._flow.set_margin_top(14); self._flow.set_margin_bottom(18)
        self._flow.set_filter_func(self._flow_filter)
        sc.set_child(self._flow)
        self._stack.add_named(sc, "grid")
        self._stack.add_named(self._build_empty(), "empty")
        root.append(self._stack)

        # pie: estado
        foot = Gtk.Box(spacing=8)
        foot.set_margin_start(20); foot.set_margin_end(20)
        foot.set_margin_top(4); foot.set_margin_bottom(10)
        self.status = Gtk.Label(label="", xalign=0)
        self.status.add_css_class("ctl-status")
        self.status.set_hexpand(True)
        foot.append(self.status)
        root.append(foot)

        # atajos: Ctrl+F busca, Ctrl+N crea, Esc limpia la búsqueda
        kc = Gtk.EventControllerKey()
        kc.connect("key-pressed", self._on_key)
        self.add_controller(kc)

        self.refresh()
        from .. import settings as _s
        if not _s.get("welcome_shown", False):
            GLib.timeout_add(600, lambda: (self._show_tour(), False)[1])

    # ── Cabecera ────────────────────────────────────────────────────────────
    def _build_header(self):
        from ..editors.icons import icon_image
        hb = Gtk.Box(spacing=12)
        hb.add_css_class("ctl-header")
        logo_path = Path(__file__).with_name("assets") / _backend_mod.LOGO
        if logo_path.exists():
            pic = Gtk.Image.new_from_file(str(logo_path))
            pic.set_pixel_size(40)
            pic.set_overflow(Gtk.Overflow.HIDDEN)
            pic.add_css_class("ctl-logo")
            hb.append(pic)
        title = Gtk.Label(label="AnimaLinux")
        title.add_css_class("ctl-title")
        hb.append(title)
        chip = Gtk.Label(label=f"v{__version__}")
        chip.add_css_class("chip")
        chip.set_valign(Gtk.Align.CENTER)
        hb.append(chip)

        sp = Gtk.Box(); sp.set_hexpand(True); hb.append(sp)

        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text(t("ctl_search"))
        self._search.add_css_class("ctl-search")
        self._search.set_size_request(190, -1)
        self._search.connect("search-changed", self._on_search)
        hb.append(self._search)

        def ghost(icon, tip, cb, label=None):
            b = Gtk.Button()
            if label:
                box = Gtk.Box(spacing=6)
                box.append(icon_image(icon, 16, "#c9d3e6"))
                box.append(Gtk.Label(label=label))
                b.set_child(box)
            else:
                b.set_child(icon_image(icon, 18, "#c9d3e6"))
            b.set_tooltip_text(tip)
            b.add_css_class("ghost"); b.add_css_class("pill")
            b.connect("clicked", lambda _: cb())
            return b

        hb.append(ghost("film", tr("Novedades e historial de cambios"),
                        lambda: open_url("https://animalinux.web.app/#cambios")))
        hb.append(ghost("help", t("help_tip"), lambda: self._show_tour(force=True)))
        hb.append(ghost("settings", t("settings_title"), self._show_settings_dialog))
        cl = ghost("close", tr("Cerrar esta ventana (las mascotas siguen activas)"), self.close)
        hb.append(cl)
        w = hb.get_first_child()
        while w is not None:                 # todo centrado en vertical, nada se estira
            w.set_valign(Gtk.Align.CENTER)
            w = w.get_next_sibling()
        return hb

    # ── Barra de herramientas: filtros + importar + nueva ─────────────────────
    def _build_toolbar(self):
        bar = Gtk.Box(spacing=12)
        bar.set_margin_start(18); bar.set_margin_end(18)
        bar.set_margin_top(14)
        seg = Gtk.Box(spacing=2)
        seg.add_css_class("seg")
        self._seg = {}
        first = None
        for fid, key in (("all", "f_all"), ("life", "tab_vida"), ("gif", "tab_normal")):
            b = Gtk.ToggleButton(label=t(key))
            b.set_focus_on_click(False)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.connect("toggled", self._on_seg, fid)
            self._seg[fid] = (b, key)
            seg.append(b)
        first.set_active(True)
        bar.append(seg)

        sp = Gtk.Box(); sp.set_hexpand(True); bar.append(sp)

        # Importar ▾
        self.method_combo = Gtk.DropDown.new_from_strings([t(m[0]) for m in BG_METHODS])
        self.method_combo.set_selected(0)
        self.sheet_cols = Gtk.SpinButton(
            adjustment=Gtk.Adjustment(value=0, lower=0, upper=64, step_increment=1))
        comb = Gtk.Button(label="🌐  " + tr("Animaciones de la comunidad"))
        comb.add_css_class("pill")
        comb.set_tooltip_text(tr("Descarga packs de la comunidad y sube los tuyos"))
        comb.connect("clicked", lambda _: open_url("https://animalinux-community.web.app/"))
        bar.append(comb)
        imp = Gtk.MenuButton(label=t("ctl_import") + " ▾")
        imp.add_css_class("pill")
        pop = Gtk.Popover()
        pop.set_has_arrow(False)
        pv = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        pv.set_margin_top(6); pv.set_margin_bottom(6); pv.set_margin_start(6); pv.set_margin_end(6)
        def item(label, cb, box=pv):
            b = Gtk.Button(label=label)
            b.add_css_class("menu-item")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b: (pop.popdown(), cb()))
            box.append(b)
        item(t("imp_gif"), lambda: self._import_media("gif"))
        item(t("imp_video"), lambda: self._import_media("video"))
        item(t("imp_folder"), lambda: self._on_import_folder(None))
        item(t("imp_pack"), lambda: self._start_import(life=True))
        item(t("imp_sheet"), lambda: self._on_import_sheet(None))
        cols = Gtk.Box(spacing=8)
        cols.set_margin_start(10); cols.set_margin_end(10)
        cl = Gtk.Label(label=t("imp_cols"), xalign=0); cl.add_css_class("dim-label"); cl.set_hexpand(True)
        cols.append(cl); cols.append(self.sheet_cols)
        pv.append(cols)
        sep = Gtk.Box(); sep.add_css_class("menu-sep"); pv.append(sep)
        bgt = Gtk.Label(label=t("imp_bg").upper(), xalign=0); bgt.add_css_class("menu-title"); pv.append(bgt)
        self.method_combo.set_margin_start(10); self.method_combo.set_margin_end(10)
        self.method_combo.set_margin_bottom(4)
        pv.append(self.method_combo)
        pop.set_child(pv)
        imp.set_popover(pop)
        bar.append(imp)

        new = Gtk.Button(label="＋  " + t("ctl_new"))
        new.add_css_class("suggested-action")
        new.add_css_class("pill")
        new.connect("clicked", lambda _: self._ask_create())
        bar.append(new)
        return bar

    # ── Estado vacío ────────────────────────────────────────────────────────
    def _build_empty(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER); box.set_valign(Gtk.Align.CENTER)
        logo_path = Path(__file__).with_name("assets") / _backend_mod.LOGO
        if logo_path.exists():
            pic = Gtk.Image.new_from_file(str(logo_path))
            pic.set_pixel_size(112)
            box.append(pic)
        self._empty_title = Gtk.Label(label=t("empty_title"))
        self._empty_title.add_css_class("empty-title")
        box.append(self._empty_title)
        self._empty_sub = Gtk.Label(label=t("empty_sub"))
        self._empty_sub.add_css_class("empty-sub")
        self._empty_sub.set_wrap(True); self._empty_sub.set_max_width_chars(46)
        self._empty_sub.set_justify(Gtk.Justification.CENTER)
        box.append(self._empty_sub)
        self._empty_btns = Gtk.Box(spacing=10, halign=Gtk.Align.CENTER)
        self._empty_btns.set_margin_top(10)
        cta = Gtk.Button(label="＋  " + t("empty_cta"))
        cta.add_css_class("suggested-action"); cta.add_css_class("pill")
        cta.connect("clicked", lambda _: self._ask_create())
        tour = Gtk.Button(label=t("empty_tour")); tour.add_css_class("pill")
        tour.connect("clicked", lambda _: self._show_tour(force=True))
        com = Gtk.Button(label=t("empty_comm")); com.add_css_class("pill")
        com.connect("clicked", lambda _: open_url("https://animalinux-community.web.app/"))
        for b in (cta, tour, com):
            self._empty_btns.append(b)
        box.append(self._empty_btns)
        return box

    # ── Filtros y búsqueda ──────────────────────────────────────────────────
    def _set_filter(self, fid):
        b = self._seg.get(fid)
        if b:
            b[0].set_active(True)

    def _on_seg(self, btn, fid):
        if not btn.get_active():
            return
        self._filter = fid
        self._apply_filter()

    def _on_search(self, entry):
        self._query = entry.get_text().strip().lower()
        self._apply_filter()

    def _flow_filter(self, child):
        a = getattr(child, "_anim", None)
        if a is None:
            return True
        life = a.get("mode") == "life"
        if self._filter == "life" and not life:
            return False
        if self._filter == "gif" and life:
            return False
        return self._query in a.get("name", "").lower()

    def _apply_filter(self):
        if not hasattr(self, "_flow") or not hasattr(self, "_stack"):
            return  # aún construyendo la ventana
        self._flow.invalidate_filter()
        self._update_stack()

    def _update_stack(self):
        anims = self.app.library.animations
        if not anims:
            self._empty_title.set_text(t("empty_title"))
            self._empty_sub.set_text(t("empty_sub"))
            self._empty_btns.set_visible(True)
            self._stack.set_visible_child_name("empty")
            return
        visible = sum(1 for a in anims.values()
                      if self._flow_filter_dict(a))
        if visible == 0:
            q = self._query or t("f_all" if self._filter == "all" else
                                 "tab_vida" if self._filter == "life" else "tab_normal")
            self._empty_title.set_text(t("no_results", q=q))
            self._empty_sub.set_text("")
            self._empty_btns.set_visible(False)
            self._stack.set_visible_child_name("empty")
        else:
            self._stack.set_visible_child_name("grid")

    def _flow_filter_dict(self, a):
        life = a.get("mode") == "life"
        if self._filter == "life" and not life:
            return False
        if self._filter == "gif" and life:
            return False
        return self._query in a.get("name", "").lower()

    def _on_key(self, ctrl, keyval, keycode, mods):
        ctl = bool(mods & Gdk.ModifierType.CONTROL_MASK)
        name = (Gdk.keyval_name(keyval) or "").lower()
        if ctl and name == "f":
            self._search.grab_focus(); return True
        if ctl and name == "n":
            self._ask_create(); return True
        if name == "escape" and self._search.get_text():
            self._search.set_text(""); return True
        return False

    # ── Arrastrar y soltar ──────────────────────────────────────────────────
    def _on_drop(self, target, value, x, y):
        self._drop_hint.set_visible(False)
        try:
            files = value.get_files()
        except Exception:  # noqa: BLE001
            return False
        n = 0
        for f in files:
            path = f.get_path()
            if not path:
                continue
            n += 1
            if os.path.isdir(path):
                self._import_folder_path(path)
            elif path.lower().endswith(".alpack"):
                self._import_pack_path(path)
            else:
                self._pending_live = False
                self._import_path(path)
        return n > 0

    # ── Diálogo de creación ─────────────────────────────────────────────────
    def _ask_create(self, life=None):
        if life is None:
            life = self._filter == "life"
        dialog = Gtk.Dialog(title=t("ctl_new"), transient_for=self, modal=True)
        dialog.set_default_size(640, 300)
        box = dialog.get_content_area()
        box.set_spacing(14)
        for m in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{m}")(20)
        state = {"life": bool(life)}

        head = Gtk.Label(label=t("create_type"))
        head.add_css_class("empty-title")
        head.set_halign(Gtk.Align.CENTER)
        box.append(head)

        seg = Gtk.Box(spacing=2, halign=Gtk.Align.CENTER)
        seg.add_css_class("seg")
        b_life = Gtk.ToggleButton(label=t("tab_vida"))
        b_gif = Gtk.ToggleButton(label=t("tab_normal"))
        b_gif.set_group(b_life)
        (b_life if life else b_gif).set_active(True)
        b_life.connect("toggled", lambda b: b.get_active() and state.update(life=True))
        b_gif.connect("toggled", lambda b: b.get_active() and state.update(life=False))
        seg.append(b_life); seg.append(b_gif)
        box.append(seg)

        row = Gtk.Box(spacing=12, homogeneous=True)
        row.set_margin_top(6)

        def _opt(icon_name, title, desc, cb):
            vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(30)
            vb.append(icon)
            tl = Gtk.Label(label=title)
            tl.add_css_class("opt-title")
            vb.append(tl)
            dl = Gtk.Label(label=desc)
            dl.add_css_class("dim-label")
            dl.set_justify(Gtk.Justification.CENTER)
            dl.set_wrap(True); dl.set_max_width_chars(18)
            vb.append(dl)
            b = Gtk.Button()
            b.add_css_class("opt-card")
            b.set_child(vb)
            b.connect("clicked", lambda _: (dialog.destroy(), cb(state["life"])))
            return b

        row.append(_opt("document-open-symbolic", t("btn_import"), t("btn_import_desc"),
                        lambda lf: self._start_import(life=lf)))
        row.append(_opt("applications-graphics-symbolic", t("btn_pixel"), t("btn_pixel_desc"),
                        lambda lf: self.app.show_pixel_editor(guided=lf)))
        row.append(_opt("edit-symbolic", t("btn_paint"), t("btn_paint_desc"),
                        lambda lf: self.app.show_paint_editor(guided=lf)))
        row.append(_opt("folder-open-symbolic", t("btn_continue"), t("btn_continue_desc"),
                        lambda lf: self._show_projects_dialog()))
        box.append(row)

        foot = Gtk.Box(); foot.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label=t("cancel"))
        cancel.add_css_class("pill")
        cancel.connect("clicked", lambda _: dialog.destroy())
        foot.append(cancel)
        box.append(foot)
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
        child = self._flow.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._flow.remove(child); child = nxt

        anims = self.app.library.animations
        items = sorted(anims.values(), key=lambda a: (a.get("mode") != "life", a.get("name", "").lower()))
        lives = sum(1 for a in items if a.get("mode") == "life")
        active = sum(1 for a in items if a.get("on_desktop"))

        for i, a in enumerate(items):
            card = self._make_card(a, i)
            fc = Gtk.FlowBoxChild()
            fc.set_child(card)
            fc._anim = a
            self._flow.append(fc)

        counts = {"all": len(items), "life": lives, "gif": len(items) - lives}
        for fid, (btn, key) in self._seg.items():
            btn.set_label(tr("{x0}  ·  {x1}", x0=t(key), x1=counts[fid]))
        self.status.set_text(t("summary", n=len(items), a=active) if items else "")
        self._gpu_warning.set_visible(self._software_gpu and active > 1)
        self._flow.invalidate_filter()
        self._update_stack()

    # ── Tarjeta de mascota ──────────────────────────────────────────────────
    def _menu_item(self, pop, label, cb, danger=False):
        b = Gtk.Button(label=label)
        b.add_css_class("menu-item")
        if danger:
            b.add_css_class("danger")
        b.get_child().set_xalign(0)
        b.connect("clicked", lambda _b: (pop.popdown(), cb()))
        return b

    def _make_card(self, anim, index):
        life = anim.get("mode") == "life"
        aid = anim["id"]
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("mcard")
        card.add_css_class(f"d{min(index, 11)}")
        if anim.get("on_desktop"):
            card.add_css_class("on-desktop")
        card.set_size_request(236, -1)

        # escenario con la animación y las insignias
        stage = Gtk.Overlay()
        stage.add_css_class("mcard-stage")
        stage.set_size_request(-1, 176)
        prev = self._animated_preview(anim, 150)
        prev.set_halign(Gtk.Align.CENTER); prev.set_valign(Gtk.Align.CENTER)
        stage.set_child(prev)
        badge = Gtk.Label(label=t("badge_life") if life else t("badge_gif"))
        badge.add_css_class("mbadge"); badge.add_css_class("mbadge-life" if life else "mbadge-gif")
        badge.set_halign(Gtk.Align.START); badge.set_valign(Gtk.Align.START)
        stage.add_overlay(badge)
        live = Gtk.Label(label="●  " + t("badge_live"))
        live.add_css_class("mbadge"); live.add_css_class("mbadge-live")
        live.set_halign(Gtk.Align.END); live.set_valign(Gtk.Align.START)
        live.set_visible(bool(anim.get("on_desktop")))
        stage.add_overlay(live)
        card.append(stage)

        name = self._editable_name(anim)
        name.add_css_class("mcard-title")
        name.set_margin_start(6); name.set_margin_end(6); name.set_margin_top(4)
        card.append(name)

        meta = [tr("{x0} fps", x0=int(anim.get('fps', 12))), tr("{x0}×{x1}", x0=anim.get('width', '?'), x1=anim.get('height', '?'))]
        if life:
            meta.append(t("meta_poses", n=len(anim.get("poses", ["default"]))))
        ml = Gtk.Label(label="  ·  ".join(meta), xalign=0)
        ml.add_css_class("mcard-meta")
        card.append(ml)

        # acciones: interruptor de escritorio, editar y más opciones
        acts = Gtk.Box(spacing=8)
        acts.add_css_class("mcard-actions")
        sw = Gtk.Switch()
        sw.set_valign(Gtk.Align.CENTER)
        sw.set_active(anim.get("on_desktop", False))
        sw.set_tooltip_text(t("show_desktop"))

        def toggled(s, state, aid=aid):
            self._on_toggle(aid, state)
            live.set_visible(state)
            (card.add_css_class if state else card.remove_css_class)("on-desktop")
            active = sum(1 for a in self.app.library.animations.values() if a.get("on_desktop"))
            self.status.set_text(t("summary", n=len(self.app.library.animations), a=active))
            return False
        sw.connect("state-set", toggled)
        acts.append(sw)
        sl = Gtk.Label(label=t("on_desktop")); sl.add_css_class("sw-label")
        acts.append(sl)
        sp = Gtk.Box(); sp.set_hexpand(True); acts.append(sp)

        if not anim.get("source_animated"):
            # Editar: SOLO para contenido creado con la app. Un GIF/MP4 importado
            # trae su propia animación y no se edita frame a frame.
            ed = Gtk.MenuButton(label=t("card_edit") + " ▾")
            ed.add_css_class("pill")
            ep = Gtk.Popover(); ep.set_has_arrow(False)
            ev = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            for m in ("start", "end", "top", "bottom"):
                getattr(ev, f"set_margin_{m}")(6)
            ev.append(self._menu_item(ep, t("btn_pixel"), lambda: self.app.show_pixel_editor(anim_id=aid, pose="default")))
            ev.append(self._menu_item(ep, t("btn_paint"), lambda: self.app.show_paint_editor(anim_id=aid, pose="default")))
            if life:
                s2 = Gtk.Box(); s2.add_css_class("menu-sep"); ev.append(s2)
                ev.append(self._menu_item(ep, t("add_pose") + " · " + t("add_pose_pixel"),
                                          lambda: self.app.show_pixel_editor(anim_id=aid, guided=True)))
                ev.append(self._menu_item(ep, t("add_pose") + " · " + t("add_pose_paint"),
                                          lambda: self.app.show_paint_editor(anim_id=aid, guided=True)))
            ep.set_child(ev); ed.set_popover(ep)
            acts.append(ed)

        more = Gtk.MenuButton()
        more.set_label("⋯")
        more.add_css_class("pill")
        more.set_tooltip_text(t("card_more"))
        mp = Gtk.Popover(); mp.set_has_arrow(False)
        mv = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        for m in ("start", "end", "top", "bottom"):
            getattr(mv, f"set_margin_{m}")(8)
        tt = Gtk.Label(label=t("card_settings").upper(), xalign=0); tt.add_css_class("menu-title")
        mv.append(tt)
        mv.append(self._fps_scale_row(anim))
        if life:
            mv.append(self._pose_toggles_row(anim))
        s3 = Gtk.Box(); s3.add_css_class("menu-sep"); mv.append(s3)
        mv.append(self._menu_item(mp, t("card_export"),
                                  (lambda: self._on_export_pack(aid)) if life else (lambda: self._on_export_gif(aid))))
        mv.append(self._menu_item(mp, "🌐 " + t("card_share"), lambda: self._on_share_pack(aid)))
        s4 = Gtk.Box(); s4.add_css_class("menu-sep"); mv.append(s4)
        mv.append(self._menu_item(mp, t("card_delete"), lambda: self._confirm_delete(anim), danger=True))
        mp.set_child(mv); more.set_popover(mp)
        acts.append(more)
        card.append(acts)
        return card

    def _confirm_delete(self, anim):
        dlg = Gtk.AlertDialog()
        dlg.set_message(t("del_title", n=anim["name"]))
        dlg.set_detail(t("del_detail"))
        dlg.set_buttons([t("cancel"), t("card_delete")])
        dlg.set_cancel_button(0)
        dlg.set_default_button(0)

        def done(d, res):
            try:
                if d.choose_finish(res) == 1:
                    self._on_delete(anim["id"])
            except GLib.Error:
                pass
        dlg.choose(self, None, done)

    # ── Tutorial de bienvenida ───────────────────────────────────────────────
    _TOUR = [
        ("🐾", N_("¡Bienvenido a AnimaLinux!"),
         N_("Mascotas animadas que viven en tu escritorio: caminan, saltan, saludan y "
         "reaccionan a tu ratón. Este recorrido de un minuto te enseña lo esencial."),
         []),
        ("✨", N_("Crea tu primera mascota"),
         N_("Pulsa «Nueva mascota» y elige cómo hacerla:"),
         [N_("📥  Importar un GIF, vídeo, imagen, spritesheet, carpeta o pack .alpack "
          "(también puedes arrastrarlos a la ventana)"),
          N_("🎨  Editor de píxeles, con la disposición y los atajos de Aseprite"),
          N_("🖌  Editor de animación, con capas, papel cebolla y cámara al estilo Toon Boom"),
          N_("📂  Continuar un proyecto guardado")]),
        ("🧬", N_("Normal o con vida"),
         N_("«Normal» es una animación en bucle. «Con vida» usa poses y física real:"),
         ["default · idle · walk · greet · kiss · jump · angry · grab · fall",
          N_("default, walk y jump son obligatorias; el resto es opcional"),
          N_("En «⋯ Ajustes» de cada tarjeta eliges qué poses usa la mascota")]),
        ("🖥", N_("Ponla en tu escritorio"),
         N_("Activa el interruptor «Escritorio» de la tarjeta. Luego prueba:"),
         [N_("Pasa el ratón por encima: te saluda"),
          N_("Haz clic varias veces: se enfada"),
          N_("Arrástrala y suéltala: cae y rebota"),
          N_("Ajusta los FPS y el tamaño en «⋯ Ajustes»")]),
        ("🎛", N_("Personaliza y comparte"),
         N_("En ⚙ Configuración cambias el idioma, el arranque automático, las "
         "actualizaciones y el tema de color: eliges un color y la app calcula sola "
         "los tonos que mejor combinan."),
         [N_("Ctrl+F busca · Ctrl+N crea una mascota nueva"),
          N_("🌐 La comunidad tiene packs para descargar y donde subir los tuyos")]),
    ]

    def _show_tour(self, force=False):
        from .. import settings as _s
        if not force and _s.get("welcome_shown", False):
            return
        win = Gtk.Window(title=t("tour_title"), transient_for=self, modal=True)
        win.add_css_class("tour")
        win.set_default_size(600, 520)
        win.set_resizable(False)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        win.set_child(outer)
        stack = Gtk.Stack()
        stack.set_vexpand(True)
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        stack.set_transition_duration(320)
        for k, (emoji, title, text, bullets) in enumerate(self._TOUR):
            pg = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            pg.set_margin_start(40); pg.set_margin_end(40); pg.set_margin_top(34)
            e = Gtk.Label(label=emoji); e.add_css_class("tour-emoji"); pg.append(e)
            tl = Gtk.Label(label=tr(title)); tl.add_css_class("empty-title"); pg.append(tl)
            tx = Gtk.Label(label=tr(text), wrap=True, justify=Gtk.Justification.CENTER)
            tx.add_css_class("empty-sub"); tx.set_max_width_chars(56); pg.append(tx)
            for b in bullets:
                bl = Gtk.Label(label=tr(b), xalign=0, wrap=True)
                bl.add_css_class("tour-bullet"); bl.set_max_width_chars(60); pg.append(bl)
            stack.add_named(pg, f"p{k}")
        outer.append(stack)

        dots = Gtk.Label(); dots.add_css_class("tour-dots")
        never = Gtk.CheckButton(label=t("tour_never")); never.set_active(True)
        back = Gtk.Button(label=t("tour_back")); back.add_css_class("pill")
        nxt = Gtk.Button(label=t("tour_next")); nxt.add_css_class("suggested-action"); nxt.add_css_class("pill")
        state = {"i": 0}
        n = len(self._TOUR)

        def show(i):
            state["i"] = max(0, min(n - 1, i))
            stack.set_visible_child_name(f"p{state['i']}")
            dots.set_markup("  ".join("<span foreground='%s'>●</span>" % ("#ffffff" if k == state["i"] else "#5b6478")
                                       for k in range(n)))
            back.set_sensitive(state["i"] > 0)
            nxt.set_label(t("tour_done") if state["i"] == n - 1 else t("tour_next"))
            never.set_visible(state["i"] == n - 1)

        def go_next(_b):
            if state["i"] == n - 1:
                if never.get_active():
                    _s.set_val("welcome_shown", True)
                win.destroy()
            else:
                show(state["i"] + 1)
        back.connect("clicked", lambda _b: show(state["i"] - 1))
        nxt.connect("clicked", go_next)
        win.connect("close-request", lambda *_: (_s.set_val("welcome_shown", True) if not force else None, False)[1])

        foot = Gtk.Box(spacing=10)
        foot.set_margin_start(24); foot.set_margin_end(24); foot.set_margin_bottom(20); foot.set_margin_top(10)
        foot.append(never)
        sp = Gtk.Box(); sp.set_hexpand(True); foot.append(sp)
        foot.append(dots)
        sp2 = Gtk.Box(); sp2.set_hexpand(True); foot.append(sp2)
        foot.append(back); foot.append(nxt)
        outer.append(foot)
        show(0)
        win.present()

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
        entry.set_tooltip_text(tr("Editar nombre (Enter para guardar)"))

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
            chk.set_tooltip_text(tr("Usar la pose «{pose}» en modo Vida", pose=pose))
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
            dialog.set_title(tr("Elige un vídeo corto (MP4, WebM, MOV, AVI, M4V…)"))
        else:
            dialog.set_title(tr("Elige una animación (GIF, WebP animado, APNG…)"))

        # Filtro de archivo
        store = Gio.ListStore.new(Gtk.FileFilter)
        f = Gtk.FileFilter()
        if kind == "video":
            f.set_name(tr("Vídeos (MP4, WebM, MOV, AVI, M4V)"))
            for pat in ("*.mp4", "*.webm", "*.mov", "*.avi", "*.m4v"):
                f.add_pattern(pat)
        else:
            f.set_name(tr("Animaciones (GIF, WebP, APNG, PNG)"))
            for pat in ("*.gif", "*.webp", "*.apng", "*.png"):
                f.add_pattern(pat)
        store.append(f)
        all_f = Gtk.FileFilter()
        all_f.set_name(tr("Todos los archivos"))
        all_f.add_pattern("*")
        store.append(all_f)
        dialog.set_filters(store)
        dialog.open(self, None, self._on_file_chosen)

    # ── Importar (gif / mp4 / imagen) ─────────────────────────────────────────
    def _start_import(self, life=False):
        self._pending_live = life
        dialog = Gtk.FileDialog()
        if life:
            dialog.set_title(tr("Elige un pack .alpack"))
            f = Gtk.FileFilter()
            f.set_name(tr("Pack de AnimaLinux (.alpack)"))
            f.add_pattern("*.alpack")
            store = Gio.ListStore.new(Gtk.FileFilter)
            store.append(f)
            dialog.set_filters(store)
            dialog.set_default_filter(f)
        else:
            dialog.set_title(tr("Elige una animación (GIF, WebP, APNG, PNG, MP4…)"))
        dialog.open(self, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        try:
            gfile = dialog.open_finish(result)
        except GLib.Error:
            return
        self._import_path(gfile.get_path())

    def _import_path(self, path):
        if path and path.lower().endswith(".alpack"):
            # el usuario eligió un pack .alpack desde un botón de GIF/vídeo/
            # imagen: es un error de bicicleta esperable (los botones están
            # uno al lado del otro), no un archivo inválido — se importa
            # igual (ver _import_pack_path: el modo se decide según cuántas
            # poses trae el pack, no queda fijo).
            self._import_pack_path(path)
            return
        method = BG_METHODS[self.method_combo.get_selected()][1]
        live = getattr(self, "_pending_live", False)
        self.status.set_text(tr("Procesando… (puede tardar si se usa IA)"))

        def report(texto, frac):
            GLib.idle_add(self.status.set_text, tr("{texto}… {x1}%", texto=texto, x1=int(frac * 100)))

        def work():
            try:
                pre_loaded = importer.load_frames(path)
                use_method = method
                # si el archivo YA viene con fondo transparente (stickers/
                # emotes GIF/WebP/APNG), pasarlo por la IA es contraproducente
                # — recalcula una máscara nueva y puede decolorar detalles
                # finos (correas, guantes) que ya estaban bien recortados.
                if method == "ai" and importer.already_has_transparency(pre_loaded[0]):
                    use_method = "none"
                    GLib.idle_add(
                        self.status.set_text,
                        tr("Este archivo ya tiene fondo transparente — no se aplicó recorte con IA."))
                lib = self.app.library
                aid = lib.new_id()
                dest = lib.frames_dir(aid)
                fc, w, h, fps = importer.import_animation(
                    path, dest, bg_method=use_method, progress=report,
                    pre_loaded=pre_loaded)
                name = os.path.basename(path).rsplit(".", 1)[0]
                GLib.idle_add(self._import_done, aid, name, fc, w, h, fps, live)
            except Exception as e:   # noqa: BLE001
                GLib.idle_add(self.status.set_text, tr("Error al importar: {e}", e=e))

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
                tr("«{name}» lista. Abriendo editor guiado para crear sus acciones…", name=name))
            self.refresh()
            # Offer guided editor
            self._ask_guided_editor(aid)
        else:
            self.status.set_text(
                tr("«{name}» creada ({fc} cuadros). Usa «Editar» para ajustarla.", name=name, fc=fc))
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
        self.status.set_text(tr("Importando pack…"))

        def work():
            try:
                aid = self.app.import_pack(path)
                # un pack con MÁS de una carpeta de pose trae vida propia
                # (walk/idle/greet/...) → modo "life". Con una sola carpeta
                # (sea cual sea su nombre — normalmente "default") es una
                # animación simple → modo "gif", igual que si se hubiera
                # importado directo como GIF/vídeo.
                poses = self.app.library.animations.get(aid, {}).get("poses", [])
                mode = "life" if len(poses) > 1 else "gif"
                self.app.library.update(aid, mode=mode)
                GLib.idle_add(self._pack_done)
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self.status.set_text, tr("Error con el pack: {e}", e=e))

        threading.Thread(target=work, daemon=True).start()

    def _pack_done(self):
        self.status.set_text(tr("Pack importado."))
        self.refresh()
        return False

    def _on_export_pack(self, aid):
        anim = self.app.library.animations.get(aid, {})
        dialog = Gtk.FileDialog()
        dialog.set_title(tr("Guardar pack"))
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
            self.status.set_text(tr("Pack exportado: {name}", name=out.name))
        except Exception as e:  # noqa: BLE001
            self.status.set_text(tr("Error al exportar: {e}", e=e))

    def _on_share_pack(self, aid):
        """Exportar + abrir directo la web de subida — un solo click en vez de
        exportar, buscar la web y navegar hasta 'Subir mascota' a mano."""
        anim = self.app.library.animations.get(aid, {})
        dialog = Gtk.FileDialog()
        dialog.set_title(tr("Guardar pack para compartir"))
        dialog.set_initial_name(f"{anim.get('name', 'mascota')}.alpack")
        dialog.save(self, None,
                    lambda d, r, aid=aid: self._on_share_pack_save(d, r, aid))

    def _on_share_pack_save(self, dialog, result, aid):
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return
        try:
            out = self.app.export_pack(aid, gfile.get_path())
            self.status.set_text(
                tr("Pack guardado en {out} — abriendo la web para subirlo…", out=out))
            Gio.AppInfo.launch_default_for_uri(
                "https://animalinux-community.web.app/upload.html", None)
        except Exception as e:  # noqa: BLE001
            self.status.set_text(tr("Error al exportar: {e}", e=e))

    def _on_export_gif(self, aid):
        """Exportar una mascota 'sin vida' (GIF/MP4 importado o dibujado) —
        se reconstruye desde sus frames guardados, no como .alpack (ese
        formato es para mascotas con vida, con varias poses)."""
        anim = self.app.library.animations.get(aid, {})
        dialog = Gtk.FileDialog()
        dialog.set_title(tr("Exportar animación"))

        gif_filter = Gtk.FileFilter(); gif_filter.set_name(tr("GIF animado (*.gif)"))
        gif_filter.add_pattern("*.gif")
        mp4_filter = Gtk.FileFilter(); mp4_filter.set_name(tr("Vídeo MP4 (*.mp4)"))
        mp4_filter.add_pattern("*.mp4")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(gif_filter); filters.append(mp4_filter)
        dialog.set_filters(filters)

        dialog.set_initial_name(f"{anim.get('name', 'mascota')}.gif")
        dialog.save(self, None,
                    lambda d, r, aid=aid: self._on_gif_save(d, r, aid))

    def _on_gif_save(self, dialog, result, aid):
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return
        path = gfile.get_path()
        if not path.lower().endswith((".gif", ".mp4")):
            path += ".gif"
        try:
            out = self.app.export_animation(aid, path)
            self.status.set_text(tr("Animación exportada: {name}", name=out.name))
        except Exception as e:  # noqa: BLE001
            self.status.set_text(tr("Error al exportar: {e}", e=e))

    # ── Carpeta vida ─────────────────────────────────────────────────────────
    def _on_import_folder(self, _btn):
        dialog = Gtk.FileDialog()
        dialog.set_title(tr("Elige la carpeta de la mascota"))
        dialog.select_folder(self, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog, result):
        try:
            gfile = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        self._import_folder_path(gfile.get_path())

    def _import_folder_path(self, path):
        self.status.set_text(tr("Importando carpeta y validando…"))

        def work():
            try:
                aid, problemas = self.app.import_life_folder(path)
                GLib.idle_add(self._folder_done, aid, problemas)
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self.status.set_text, tr("Error: {e}", e=e))

        threading.Thread(target=work, daemon=True).start()

    def _folder_done(self, aid, problemas):
        self.refresh()
        self._set_filter("life")
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

        lineas = [tr("POSES ENCONTRADAS\n") + "─" * 38 + "\n"]
        for pose in fi.KNOWN_POSES:
            if pose in poses_encontradas:
                aviso = ""
                if pose in problemas:
                    aviso = "  ⚠ " + "; ".join(problemas[pose])
                lineas.append(tr("  ✔  {pose:<10}{aviso}", pose=pose, aviso=aviso))
            else:
                lineas.append(tr("  ✘  {pose:<10}  (falta — añade subcarpeta '{x1}/')", pose=pose, x1=pose))

        extras = poses_encontradas - set(fi.KNOWN_POSES) - {"default"}
        if extras:
            lineas.append(tr("\nPOSES EXTRA DETECTADAS"))
            for p in sorted(extras):
                lineas.append(f"  ·  {p}")

        if "_general" in problemas:
            lineas.append("\n⚠  " + "\n   ".join(problemas["_general"]))

        lineas.append("\n" + "─" * 38)
        lineas.append(tr("ESTRUCTURA ESPERADA\n"))
        lineas.append(tr("  NombreMascota/"))
        for pose in fi.KNOWN_POSES:
            req = tr(" ← obligatoria") if pose == "default" else ""
            estado = "✔" if pose in poses_encontradas else "✘"
            lineas.append(tr("  {estado} {pose}/", estado=estado, pose=pose))
            lineas.append(tr("      frame_0000.png …{req}", req=req))

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
        dialog.set_title(tr("Elige un spritesheet"))
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
        self.status.set_text(tr("Cortando spritesheet…"))

        def work():
            try:
                self.app.import_spritesheet(gfile.get_path(), cols)
                GLib.idle_add(self._sheet_done)
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self.status.set_text, tr("Error: {e}", e=e))

        threading.Thread(target=work, daemon=True).start()

    def _sheet_done(self):
        self.status.set_text(tr("Spritesheet importado."))
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
                name_lbl.set_markup(tr("<b>{x0}</b>", x0=proj['name']))
                info.append(name_lbl)
                meta_lbl = Gtk.Label(
                    label=tr("{x0} {x1}  •  {x2} KB", x0=t('projects_modified'), x1=proj['modified'], x2=proj['size_kb']),
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
    # ── Actualizaciones ──────────────────────────────────────────────────────
    def refresh_update_banner(self):
        from ..core import updater
        v = updater.pending()
        self._upd_rev.set_reveal_child(bool(v))
        if v:
            self._upd_lbl.set_text("🆕 " + t("upd_available", v=v))
            self._upd_btn.set_sensitive(True)
            self._upd_btn.set_label(t("upd_now"))

    def _run_update(self):
        from ..core import updater
        v = updater.pending()
        if not v:
            return
        self._upd_btn.set_sensitive(False)
        self._upd_btn.set_label(t("upd_working"))

        def log(msg):
            GLib.idle_add(self._upd_lbl.set_text, msg)

        def work():
            try:
                updater.apply_update(v, log)
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self._update_failed, str(e))
                return
            GLib.idle_add(self._update_ok, v)
        threading.Thread(target=work, daemon=True).start()

    def _update_failed(self, msg):
        self._upd_lbl.set_text(tr("{x0} {msg}", x0=t('upd_failed'), msg=msg))
        self._upd_btn.set_sensitive(True)
        self._upd_btn.set_label(t("upd_now"))

    def _update_ok(self, v):
        from ..core import updater
        self._upd_lbl.set_text(t("upd_done", v=v))
        updater.restart()

    def _show_settings_dialog(self):
        from .. import i18n as _i18n
        dlg = Gtk.Dialog(title=t("settings_title"), transient_for=self, modal=True)
        dlg.set_default_size(430, 200)
        box = dlg.get_content_area()
        box.set_spacing(12)
        box.set_margin_start(20); box.set_margin_end(20)
        box.set_margin_top(16); box.set_margin_bottom(16)

        # ── Tema de color: el color principal define TODA la combinación ─────
        from . import theme as _theme
        orig_theme = _theme.current_theme()
        th_title = Gtk.Label(label=t("theme_title"), xalign=0)
        th_title.add_css_class("opt-title")
        box.append(th_title)
        sw_row = Gtk.Box(spacing=10)
        swatches = {}
        preview = Gtk.DrawingArea()
        preview.set_content_width(150); preview.set_content_height(20)

        def draw_preview(_a, cr, w, h):
            pal = _theme.build_palette(_theme.resolve(_theme.current_theme()))
            for k, col in enumerate((pal["BG"], pal["ACCENT"], pal["G1"], pal["G2"], pal["ACCENT2"])):
                r, g, bl = (int(col[i:i + 2], 16) / 255 for i in (1, 3, 5))
                cr.set_source_rgb(r, g, bl)
                cr.arc(10 + k * 30, h / 2, 9, 0, 6.2832); cr.fill()
        preview.set_draw_func(draw_preview)

        def mark():
            cur = _theme.current_theme()
            for tid, b in swatches.items():
                (b.add_css_class if tid == cur else b.remove_css_class)("swatch-on")
            preview.queue_draw()

        def pick(tid):
            _theme.set_theme(tid)
            mark()

        def make_swatch(tid, name, colhex):
            b = Gtk.Button()
            b.add_css_class("swatch")
            da = Gtk.DrawingArea(); da.set_content_width(22); da.set_content_height(22)
            r, g, bl = (int(colhex[i:i + 2], 16) / 255 for i in (1, 3, 5))
            da.set_draw_func(lambda _a, cr, w, h: (cr.set_source_rgb(r, g, bl), cr.arc(w / 2, h / 2, 10, 0, 6.2832), cr.fill()))
            b.set_child(da)
            b.set_tooltip_text(name)
            b.connect("clicked", lambda _b: pick(tid))
            swatches[tid] = b
            return b
        for tid, (name, colhex) in _theme.PRESETS.items():
            sw_row.append(make_swatch(tid, name, colhex))
        if hasattr(Gtk, "ColorDialogButton"):
            cust = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog())
        else:
            cust = Gtk.ColorButton()
        cust.set_tooltip_text(t("theme_custom"))
        cur_id = _theme.current_theme()
        c0 = Gdk.RGBA(); c0.parse(_theme.resolve(cur_id))
        try:
            cust.set_rgba(c0)
        except Exception:  # noqa: BLE001
            pass

        def custom_changed(*_):
            c = cust.get_rgba()
            pick("#%02x%02x%02x" % (round(c.red * 255), round(c.green * 255), round(c.blue * 255)))
        cust.connect("notify::rgba", custom_changed)
        sw_row.append(cust)
        box.append(sw_row)
        pv_row = Gtk.Box(spacing=10)
        pl = Gtk.Label(label=t("theme_combo"), xalign=0); pl.add_css_class("dim-label"); pl.set_hexpand(True)
        pv_row.append(pl); pv_row.append(preview)
        box.append(pv_row)
        mark()
        sep_t = Gtk.Separator(); box.append(sep_t)

        lang_row = Gtk.Box(spacing=10)
        lang_row.append(Gtk.Label(label=t("lang_label")))
        lang_codes = list(_i18n.LANGUAGES.keys())
        lang_names = [tr("{x0}  ({c})", x0=_i18n.LANGUAGES[c], c=c) for c in lang_codes]
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

        # Actualizaciones
        from ..core import updater
        upd_row = Gtk.Box(spacing=10)
        upd_lbl = Gtk.Label(label=t("upd_auto"), xalign=0)
        upd_lbl.set_hexpand(True)
        upd_lbl.set_wrap(True)
        upd_row.append(upd_lbl)
        upd_sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        upd_sw.set_active(updater.enabled())
        upd_row.append(upd_sw)
        box.append(upd_row)

        chk_row = Gtk.Box(spacing=10)
        chk_msg = Gtk.Label(label="", xalign=0, hexpand=True)
        chk_msg.add_css_class("dim-label")
        chk_msg.set_wrap(True)
        chk_row.append(chk_msg)
        chk_btn = Gtk.Button(label=t("upd_check"))

        def _check(_b):
            chk_btn.set_sensitive(False)
            chk_msg.set_text(t("upd_checking"))

            def work():
                latest = updater.check_latest()
                new = latest if latest and updater.is_newer(latest) else None
                if latest:
                    from .. import settings as _st
                    import time as _time
                    _st.set_val("last_update_check", _time.time())
                    _st.set_val("update_available", new or "")

                def done():
                    chk_btn.set_sensitive(True)
                    chk_msg.set_text(
                        t("upd_available", v=new) if new else
                        t("upd_uptodate") if latest else t("upd_nonet"))
                    self.refresh_update_banner()
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()
        chk_btn.connect("clicked", _check)
        chk_row.append(chk_btn)
        box.append(chk_row)

        btn_row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=t("cancel"))
        cancel.connect("clicked", lambda _: (_theme.set_theme(orig_theme), dlg.destroy()))
        btn_row.append(cancel)
        ok = Gtk.Button(label=t("ok"))
        ok.add_css_class("suggested-action")
        def _apply(_b):
            code = lang_codes[dd.get_selected()]
            _i18n.set_language(code)
            from .. import settings as _st
            _st.set_val("auto_update_check", upd_sw.get_active())
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
            ("grab", "grab" in MANDATORY_POSES, None), ("fall", "fall" in MANDATORY_POSES, None),
        ]
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.add_css_class("folder-tree")
        root = Gtk.Label(label="📁 mi_mascota/", xalign=0)
        box.append(root)
        for name, required, frames in entries:
            lbl = Gtk.Label(label=tr("   📁 {name}/", name=name), xalign=0)
            if required:
                lbl.add_css_class("folder-required")
            box.append(lbl)
            if frames:
                sub = Gtk.Label(label=tr("      🖼 {frames}", frames=frames), xalign=0)
                sub.add_css_class("dim-label")
                box.append(sub)
        return box

    def _show_vida_help(self):
        dlg = Gtk.Dialog(title=tr("Guía: Animaciones con vida"),
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
