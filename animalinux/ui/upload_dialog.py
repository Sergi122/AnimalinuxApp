"""
«Subir a la comunidad» desde la app: nombre, autor y descripción, y la
mascota se publica en la galería (tras la validación automática del servidor).
"""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import community  # noqa: E402
from ..i18n import tr  # noqa: E402
from . import guide_widgets as gw  # noqa: E402


class UploadWindow(Gtk.Window):
    def __init__(self, app, aid, parent=None):
        super().__init__(title=tr("Subir a la comunidad"))
        if parent is not None:
            self.set_transient_for(parent)
        self.set_modal(True)
        self.set_default_size(440, 10)
        self.app, self.aid = app, aid
        anim = app.library.animations.get(aid, {})
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{m}")(18)
        self.set_child(box)
        box.append(gw.body(tr("Tu mascota aparecerá en la galería de la comunidad cuando el servidor termine de revisarla (unos segundos).")))
        self.name = self._entry(box, tr("Nombre"), anim.get("name", ""), 60)
        self.author = self._entry(box, tr("Autor (opcional)"), anim.get("author", ""), 60)
        self.desc = self._entry(box, tr("Descripción (opcional)"), "", 300)
        self.ok = Gtk.CheckButton(label=tr("Es mía o tengo permiso para compartirla"))
        self.ok.connect("toggled", lambda *_: self._sync())
        box.append(self.ok)
        self.msg = Gtk.Label(xalign=0)
        self.msg.set_wrap(True)
        self.msg.add_css_class("dim-label")
        box.append(self.msg)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=tr("Cancelar"))
        cancel.connect("clicked", lambda _b: self.close())
        self.go = Gtk.Button(label=tr("Subir"))
        self.go.add_css_class("suggested-action")
        self.go.connect("clicked", lambda _b: self._upload())
        row.append(cancel)
        row.append(self.go)
        box.append(row)
        self._sync()

    @staticmethod
    def _entry(box, label, text, maxlen):
        box.append(Gtk.Label(label=label, xalign=0))
        e = Gtk.Entry()
        e.set_text(text or "")
        e.set_max_length(maxlen)
        box.append(e)
        return e

    def _sync(self):
        self.go.set_sensitive(self.ok.get_active() and bool(self.name.get_text().strip()))

    def _upload(self):
        self.go.set_sensitive(False)
        self.msg.set_text(tr("Subiendo…"))
        name = self.name.get_text().strip()
        author, desc = self.author.get_text().strip(), self.desc.get_text().strip()
        app, aid = self.app, self.aid

        def work():
            try:
                kind, data, mime, prev, meta = community.build_payload(
                    app.library, aid, app.export_pack, app.export_animation)
                meta["name"] = name[:60]
                community.upload(kind, data, mime, prev, meta, author=author, description=desc)
                GLib.idle_add(self._done, None)
            except Exception as e:  # noqa: BLE001
                GLib.idle_add(self._done, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _done(self, err):
        if err:
            self.msg.set_text(tr("No se pudo subir: {err}", err=err))
            self._sync()
        else:
            self.msg.set_text(tr("¡Listo! Aparecerá en la galería en unos segundos."))
            from ..backends import current as backend
            GLib.timeout_add(1500, lambda: (backend.open_url(community.GALLERY), self.close(), False)[2])
        return False
