"""
Ventana «Complementos»: muestra qué funciones ya tienen todo lo que
necesitan y, con un clic, descarga e instala lo que falta (ver
core/components.py). «Instalar todo» los hace uno detrás de otro.
"""
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from ..core import components as comp  # noqa: E402
from ..i18n import tr  # noqa: E402
from . import guide_widgets as gw  # noqa: E402


class ComponentsWindow(Gtk.Window):
    def __init__(self, app, parent=None, focus=None):
        super().__init__(title=tr("Complementos"))
        if parent is not None:
            self.set_transient_for(parent)
        self.app = app
        gw.close_header(self)
        self.set_default_size(560, 600)
        self._rows = {}
        self._busy = False

        sc = Gtk.ScrolledWindow()
        sc.set_vexpand(True)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for m in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{m}")(18)
        box.append(gw.note(tr("Lo que se puede ya viene dentro de la app. Lo demás se descarga e instala solo con un clic.")))
        self._all = Gtk.Button(label=tr("⬇ Instalar todo lo que falta"))
        self._all.add_css_class("suggested-action")
        self._all.add_css_class("pill")
        self._all.set_halign(Gtk.Align.START)
        self._all.connect("clicked", lambda _b: self._install_many(
            [c for c in comp.ORDER if comp.status(c) == "missing"]))
        box.append(self._all)
        for cid in comp.ORDER:
            box.append(self._row(cid))
        self._err = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self._err.add_css_class("dim-label")
        box.append(self._err)
        sc.set_child(box)
        self.set_child(sc)
        self._refresh()
        if focus in self._rows and comp.status(focus) == "missing":
            GLib.idle_add(lambda: (self._install_many([focus]), False)[1])

    def _row(self, cid):
        title, desc, mb = comp.describe(cid)
        fr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        fr.add_css_class("card")
        for m in ("start", "end", "top", "bottom"):
            getattr(fr, f"set_margin_{m}")(2)
        top = Gtk.Box(spacing=8)
        lb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lb.set_hexpand(True)
        t = Gtk.Label(label=title, xalign=0)
        t.add_css_class("heading")
        lb.append(t)
        d = Gtk.Label(label=desc, xalign=0, wrap=True)
        d.add_css_class("dim-label")
        lb.append(d)
        st = Gtk.Label(xalign=0)
        lb.append(st)
        top.append(lb)
        btn = Gtk.Button(label=tr("Instalar (~{mb} MB)", mb=mb))
        btn.set_valign(Gtk.Align.CENTER)
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda _b, c=cid: self._install_many([c]))
        top.append(btn)
        fr.append(top)
        bar = Gtk.ProgressBar(show_text=True)
        bar.set_visible(False)
        fr.append(bar)
        self._rows[cid] = (st, btn, bar)
        return fr

    def _refresh(self):
        missing = 0
        for cid, (st, btn, bar) in self._rows.items():
            s = comp.status(cid)
            st.set_text({"ok": tr("✅ Listo"), "missing": tr("⬇ Falta instalar"),
                         "unsupported": tr("— No disponible en este sistema")}[s])
            btn.set_visible(s == "missing" and not self._busy)
            missing += s == "missing"
        self._all.set_visible(missing > 0 and not self._busy)

    def _install_many(self, cids):
        if self._busy or not cids:
            return
        self._busy = True
        self._err.set_text("")
        self._refresh()

        def work():
            errs = []
            for cid in cids:
                st, _btn, bar = self._rows[cid]
                GLib.idle_add(lambda b=bar: (b.set_visible(True), b.set_text(tr("Empezando…")), False)[2])

                def prog(text, frac, bar=bar):
                    def ui():
                        bar.set_text(f"{text}  {int(frac * 100)} %" if frac is not None else text)
                        if frac is None:
                            bar.pulse()
                        else:
                            bar.set_fraction(max(0.0, min(1.0, frac)))
                        return False
                    GLib.idle_add(ui)
                try:
                    comp.install(cid, prog)
                except Exception as e:  # noqa: BLE001
                    errs.append(f"{comp.describe(cid)[0]}: {e}")
                GLib.idle_add(lambda b=bar: (b.set_visible(False), False)[1])
            GLib.idle_add(self._done, errs)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, errs):
        self._busy = False
        self._err.set_text("\n".join(errs))
        self._refresh()
        talk = getattr(self.app, "talk", None)
        if talk is not None:
            talk.refresh_status()
        return False
