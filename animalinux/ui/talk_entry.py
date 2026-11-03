"""
Ventanita «Escribirle a tu mascota»: para quien no tiene micrófono o prefiere
teclear. Enter envía; la respuesta sale en la nube de la mascota.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..i18n import tr  # noqa: E402

MAX_LEN = 300


class TalkEntryWindow(Gtk.Window):
    def __init__(self, brain):
        super().__init__(title=tr("Hablar con tu mascota"))
        self.brain = brain
        self.aid = None
        self.set_default_size(380, -1)
        self.set_resizable(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{m}")(14)
        self._who = Gtk.DropDown()
        self._who.connect("notify::selected", self._on_who)
        box.append(self._who)
        row = Gtk.Box(spacing=6)
        self._entry = Gtk.Entry()
        self._entry.set_hexpand(True)
        self._entry.set_max_length(MAX_LEN)
        self._entry.set_placeholder_text(tr("Escríbele algo…"))
        self._entry.connect("activate", self._send)
        row.append(self._entry)
        send = Gtk.Button(label=tr("Enviar"))
        send.add_css_class("suggested-action")
        send.connect("clicked", self._send)
        row.append(send)
        box.append(row)
        self._hint = Gtk.Label(xalign=0)
        self._hint.add_css_class("dim-label")
        self._hint.set_wrap(True)
        box.append(self._hint)
        self.set_child(box)
        self._ids = []

    def set_pet(self, aid):
        pets = self.brain.pets()
        self._ids = [a for a, _n in pets]
        self._who.set_model(Gtk.StringList.new([n for _a, n in pets]))
        self.aid = aid if aid in self._ids else (self._ids[0] if self._ids else None)
        if self.aid in self._ids:
            self._who.set_selected(self._ids.index(self.aid))
        self._refresh_hint()
        self._entry.grab_focus()

    def _on_who(self, dd, _p):
        i = dd.get_selected()
        if 0 <= i < len(self._ids):
            self.aid = self._ids[i]
            self._refresh_hint()

    def _refresh_hint(self):
        eng = self.brain.engine()
        self._hint.set_text(tr("Responde con IA (en tu equipo).") if eng == "ai"
                            else tr("Responde con frases escritas (sin IA)."))

    def _send(self, *_a):
        text = self._entry.get_text().strip()[:MAX_LEN]
        if not text or self.aid is None:
            return
        self._entry.set_text("")
        aid, rest = self.brain.route_by_name(self.aid, text)   # «panda, hola» → el panda
        self.brain.respond(aid, rest or text)
