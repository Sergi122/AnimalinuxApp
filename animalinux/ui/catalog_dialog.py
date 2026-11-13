"""
Ventana «Catálogo de la comunidad»: las mascotas de
animalinux-community.web.app dentro de la app. Un clic en «＋ Añadir» la
descarga, la instala en tu librería y queda lista para usar; no hace falta
abrir la web, bajar el archivo ni importarlo a mano.
"""
import io
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import community, paths  # noqa: E402
from ..backends import current as backend  # noqa: E402
from ..i18n import N_, tr  # noqa: E402
from . import guide_widgets as gw  # noqa: E402

ORDERS = (("downloads", N_("⬇ Más descargadas")), ("votes", N_("★ Más votadas")),
          ("new", N_("🆕 Más nuevas")))
THUMB = 128


def _texture(data):
    """PNG/GIF (bytes) → textura del primer cuadro, escalada a THUMB."""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.seek(0)
    im = im.convert("RGBA")
    k = THUMB / max(im.size)
    if k < 1:
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))),
                       Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return Gdk.Texture.new_from_bytes(GLib.Bytes.new(buf.getvalue()))


class CatalogWindow(Gtk.Window):
    def __init__(self, app, parent=None):
        super().__init__(title=tr("Catálogo de la comunidad"))
        if parent is not None:
            self.set_transient_for(parent)
        self.app = app
        gw.close_header(self)
        self.set_default_size(760, 640)
        self._packs = []
        self._gen = 0

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for m in ("start", "end", "top", "bottom"):
            getattr(root, f"set_margin_{m}")(16)
        root.append(gw.note(tr("Mascotas que comparte la comunidad. «＋ Añadir» la descarga y la deja en tu librería al momento.")))

        bar = Gtk.Box(spacing=8)
        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text(tr("Buscar por nombre o autor"))
        self._search.set_hexpand(True)
        self._search.connect("search-changed", lambda _e: self._render())
        bar.append(self._search)
        self._order = Gtk.DropDown.new_from_strings([tr(n) for _k, n in ORDERS])
        self._order.connect("notify::selected", lambda *_a: self.reload())
        bar.append(self._order)
        rl = Gtk.Button(label="↻")
        rl.set_tooltip_text(tr("Actualizar"))
        rl.connect("clicked", lambda _b: self.reload())
        bar.append(rl)
        web = Gtk.Button(label="🌐 " + tr("Web"))
        web.set_tooltip_text(tr("Abrir la galería en el navegador (para subir las tuyas o votar)"))
        web.connect("clicked", lambda _b: backend.open_url(community.GALLERY))
        bar.append(web)
        # importar desde archivos (GIF, vídeo, carpeta, pack, hoja): el mismo
        # menú que antes colgaba del botón «Importar» de la ventana principal
        ctl = getattr(app, "control", None)
        pop = getattr(ctl, "import_popover", None)
        if pop is not None:
            if pop.get_parent() is not None:
                pop.unparent()
            local = Gtk.MenuButton(label="📁 " + tr("Desde mi PC"))
            local.set_popover(pop)
            bar.append(local)
            self._local = local
            self.connect("close-request", lambda *_a: (local.set_popover(None), False)[1])
        root.append(bar)

        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("dim-label")
        self._status.set_wrap(True)
        root.append(self._status)

        sc = Gtk.ScrolledWindow()
        sc.set_vexpand(True)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._flow = Gtk.FlowBox()
        self._flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow.set_homogeneous(True)
        self._flow.set_max_children_per_line(6)
        self._flow.set_min_children_per_line(2)
        self._flow.set_row_spacing(10)
        self._flow.set_column_spacing(10)
        self._flow.set_valign(Gtk.Align.START)
        sc.set_child(self._flow)
        root.append(sc)
        self.set_child(root)
        self.reload()

    # ── datos ───────────────────────────────────────────────────────────
    def _installed_ids(self):
        return {a.get("community_id") for a in self.app.library.animations.values()
                if a.get("community_id")}

    def reload(self):
        self._gen += 1
        gen = self._gen
        order = ORDERS[self._order.get_selected()][0]
        self._status.set_text(tr("Conectando con la comunidad…"))

        def work():
            try:
                packs, err = community.list_packs(order), ""
            except Exception as e:  # noqa: BLE001
                packs, err = [], str(e)[:200]
            GLib.idle_add(self._loaded, gen, packs, err)
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, gen, packs, err):
        if gen != self._gen:
            return False
        if err:
            self._status.set_text(tr("No se pudo abrir el catálogo (¿hay internet?): {e}", e=err))
            return False
        self._packs = packs
        self._render()
        return False

    def _render(self):
        while (c := self._flow.get_first_child()) is not None:
            self._flow.remove(c)
        q = self._search.get_text().strip().lower()
        shown = [p for p in self._packs
                 if not q or q in (p.get("name") or "").lower() or q in (p.get("author") or "").lower()]
        self._status.set_text(tr("{n} mascotas", n=len(shown)) if shown
                              else tr("No hay mascotas que coincidan."))
        have = self._installed_ids()
        for p in shown:
            self._flow.append(self._card(p, p["id"] in have))

    # ── tarjeta ─────────────────────────────────────────────────────────
    def _card(self, p, installed):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.add_css_class("card")
        for m in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{m}")(4)
        pic = Gtk.Picture()
        pic.set_size_request(THUMB, THUMB)
        pic.set_can_shrink(True)
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        box.append(pic)
        self._load_thumb(p, pic)
        name = Gtk.Label(label=p.get("name") or "?", ellipsize=3, max_width_chars=16)
        name.add_css_class("heading")
        box.append(name)
        life = p.get("kind") == "alpack" and len(p.get("poses") or []) > 1
        sub = (tr("con vida") if life else tr("animación")) + f" · ⬇ {p.get('downloads') or 0}"
        if p.get("author"):
            sub = f"{p['author'][:20]} · " + sub
        s = Gtk.Label(label=sub, ellipsize=3, max_width_chars=22)
        s.add_css_class("dim-label")
        box.append(s)
        btn = Gtk.Button(label=tr("✓ En tu librería") if installed else tr("＋ Añadir"))
        btn.set_sensitive(not installed)
        if not installed:
            btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda b, p=p: self._add(p, b))
        box.append(btn)
        if p.get("description"):
            box.set_tooltip_text(p["description"][:300])
        return box

    def _load_thumb(self, p, pic):
        def work():
            try:
                data = community.preview_bytes(p)
                tex = _texture(data) if data else None
            except Exception:  # noqa: BLE001
                tex = None
            if tex is not None:
                GLib.idle_add(lambda: (pic.set_paintable(tex), False)[1])
        threading.Thread(target=work, daemon=True).start()

    # ── añadir ──────────────────────────────────────────────────────────
    def _add(self, p, btn):
        btn.set_sensitive(False)
        btn.set_label(tr("Descargando…"))

        def work():
            path = None
            try:
                path = community.download_pack(p, paths.RUNTIME_DIR)
                aid = self._install(p, path)
                err = ""
            except Exception as e:  # noqa: BLE001
                aid, err = None, str(e)[:200]
            finally:
                if path is not None:
                    path.unlink(missing_ok=True)
            GLib.idle_add(self._added, p, btn, aid, err)
        threading.Thread(target=work, daemon=True).start()

    def _install(self, p, path):
        lib = self.app.library
        if p["kind"] == "alpack":
            aid = self.app.import_pack(str(path))
            poses = lib.animations.get(aid, {}).get("poses", [])
            lib.update(aid, mode="life" if len(poses) > 1 else "gif")
        else:
            from ..core import image_processor as importer
            aid = lib.new_id()
            fc, w, h, fps = importer.import_animation(str(path), lib.frames_dir(aid),
                                                      bg_method="none")
            lib.add(aid, (p.get("name") or tr("Mascota"))[:60], fc, w, h)
            lib.update(aid, fps=fps, source_animated=(fc > 1))
        lib.update(aid, community_id=p["id"])
        return aid

    def _added(self, p, btn, aid, err):
        if err:
            btn.set_label(tr("＋ Añadir"))
            btn.set_sensitive(True)
            self._status.set_text(tr("No se pudo añadir «{name}»: {e}", name=p.get("name"), e=err))
            return False
        btn.set_label(tr("✓ En tu librería"))
        btn.remove_css_class("suggested-action")
        self._status.set_text(tr("«{name}» ya está en tu librería.", name=p.get("name")))
        ctl = getattr(self.app, "control", None)
        if ctl is not None:
            ctl.refresh()
        return False
