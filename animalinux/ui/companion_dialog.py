"""
Ventana «Compañía»: reacciones al equipo, juegos y juguetes, Pomodoro,
recordatorios y modo no molestar. Cada cambio se guarda al momento en
settings.json y se aplica sin reiniciar (ver core/companion.py).
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402

from .. import settings  # noqa: E402
from ..core import companion as comp_mod  # noqa: E402
from ..i18n import tr  # noqa: E402
from . import guide_widgets as gw  # noqa: E402


class CompanionWindow(Gtk.Window):
    def __init__(self, app, parent=None):
        super().__init__(title=tr("Compañía"))
        if parent is not None:
            self.set_transient_for(parent)
        self.app = app
        self.set_default_size(520, 680)
        sc = Gtk.ScrolledWindow()
        sc.set_vexpand(True)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(20); box.set_margin_end(20)
        box.set_margin_top(16); box.set_margin_bottom(18)
        sc.set_child(box)
        self.set_child(sc)
        self._box = box

        # ── reacciones ───────────────────────────────────────────────────
        box.append(gw.section_title(tr("Reaccionan a lo que pasa en tu PC")))
        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("dim-label")
        self._status.set_wrap(True)
        box.append(self._status)
        self._switch("react_music", tr("🎵 Bailan cuando suena música"),
                     tr("Spotify, mpv, el navegador… cualquier reproductor que avise al sistema."))
        self._switch("react_cpu", tr("🥵 Se cansan si la CPU va al máximo"))
        self._switch("react_notify", tr("❗ Se sobresaltan con las notificaciones"))
        self._switch("react_battery", tr("🔋 Se preocupan con la batería baja"))
        self._switch("react_night", tr("🌙 De noche duermen más (y juntas)"))
        hours = Gtk.Box(spacing=8)
        hours.set_margin_start(28)
        hours.append(self._dim(tr("Desde las")))
        hours.append(self._spin("night_start", 0, 23))
        hours.append(self._dim(tr("hasta las")))
        hours.append(self._spin("night_end", 0, 23))
        box.append(hours)

        # ── juego ────────────────────────────────────────────────────────
        box.append(gw.section_title(tr("A jugar")))
        self._switch("cursor_play", tr("🖱 Juegan con el cursor"),
                     tr("Si lo dejas quieto, una se acerca a mirarlo; si lo mueves rápido cerca del suelo, lo persigue como un gato con un láser."))
        self._switch("pet_games", tr("🏃 Juegan entre ellas"),
                     tr("De vez en cuando se pillan o juegan a las escondidas detrás de una ventana."))
        toys = Gtk.FlowBox()
        toys.set_selection_mode(Gtk.SelectionMode.NONE)
        toys.set_max_children_per_line(3)
        toys.set_column_spacing(6); toys.set_row_spacing(6)
        for label, cb in ((tr("⚽ Lanzar pelota"), lambda: self._comp().throw_toy("ball")),
                          (tr("🧶 Lanzar ovillo"), lambda: self._comp().throw_toy("yarn")),
                          (tr("🧺 Guardar juguetes"), lambda: self._comp().clear_toys()),
                          (tr("🏃 ¡A pillarse!"), lambda: self._play("tag")),
                          (tr("🙈 ¡Escondidas!"), lambda: self._play("hide"))):
            b = Gtk.Button(label=label)
            b.add_css_class("pill")
            b.connect("clicked", lambda _b, cb=cb: cb())
            toys.append(b)
        box.append(toys)
        box.append(gw.note(tr("Arrastra un juguete y suéltalo rápido para lanzarlo; un clic le da un toquecito y doble clic lo guarda.")))
        self._game_msg = self._dim("")
        box.append(self._game_msg)

        # ── deportes ─────────────────────────────────────────────────────
        box.append(gw.section_title(tr("🏆 Deportes: las mascotas contra ti")))
        box.append(gw.body(tr("⚽ Fútbol, 🏐 vóley, 🏀 básquet, 🏓 ping-pong y 🎾 tenis. Eliges equipos, tiempo o puntos y dificultad.")))
        play = Gtk.Button(label=tr("🏆 Jugar un partido…"))
        play.add_css_class("suggested-action")
        play.add_css_class("pill")
        play.set_halign(Gtk.Align.START)
        play.connect("clicked", lambda _b: self._open_match())
        box.append(play)

        # ── Pomodoro ─────────────────────────────────────────────────────
        box.append(gw.section_title(tr("🍅 Pomodoro")))
        box.append(gw.body(tr("Una mascota sostiene un cartelito con el tiempo que queda. En el descanso se estiran y te avisan.")))
        row = Gtk.Box(spacing=8)
        row.append(self._dim(tr("Trabajo")))
        row.append(self._spin("pomodoro_work", 1, 120))
        row.append(self._dim(tr("Descanso")))
        row.append(self._spin("pomodoro_break", 1, 60))
        row.append(self._dim(tr("Largo")))
        row.append(self._spin("pomodoro_long", 1, 90))
        row.append(self._dim(tr("min")))
        box.append(row)
        prow = Gtk.Box(spacing=8)
        prow.append(self._dim(tr("Mascota del cartel")))
        self._pets = [("", tr("Automática"))] + [
            (a["id"], a.get("name", a["id"]))
            for a in app.library.animations.values() if a.get("on_desktop")]
        dd = Gtk.DropDown.new_from_strings([n for _i, n in self._pets])
        cur = comp_mod.cfg("pomodoro_pet")
        ids = [i for i, _n in self._pets]
        dd.set_selected(ids.index(cur) if cur in ids else 0)
        dd.set_hexpand(True)
        dd.connect("notify::selected",
                   lambda d, _p: settings.set_val("pomodoro_pet", ids[d.get_selected()]))
        prow.append(dd)
        box.append(prow)
        pr = Gtk.Box(spacing=10)
        self._pomo_btn = Gtk.Button()
        self._pomo_btn.add_css_class("suggested-action")
        self._pomo_btn.add_css_class("pill")
        self._pomo_btn.connect("clicked", lambda _b: (self._comp().pomodoro.toggle(), self._refresh()))
        pr.append(self._pomo_btn)
        self._pomo_lbl = self._dim("")
        pr.append(self._pomo_lbl)
        box.append(pr)

        # ── recordatorios ────────────────────────────────────────────────
        box.append(gw.section_title(tr("Recordatorios")))
        for key, text in (("remind_water", tr("💧 Tomar agua cada")),
                          ("remind_stand", tr("🧍 Levantarse cada"))):
            r = Gtk.Box(spacing=8)
            lbl = Gtk.Label(label=text, xalign=0)
            lbl.set_hexpand(True)
            r.append(lbl)
            r.append(self._spin(key, 0, 240, step=5))
            r.append(self._dim(tr("min (0 = nunca)")))
            box.append(r)
        test = Gtk.Button(label=tr("Probar un recordatorio"))
        test.set_halign(Gtk.Align.START)
        test.connect("clicked", lambda _b: self._comp().remind(tr("💧 ¡Toma un poco de agua!")))
        box.append(test)

        # ── no molestar ──────────────────────────────────────────────────
        box.append(gw.section_title(tr("🔕 No molestar")))
        self._switch("dnd_auto", tr("Esconderlas al compartir pantalla o grabar"),
                     tr("Meet, Discord, Zoom, OBS… vuelven solas al terminar."))
        r = Gtk.Box(spacing=10)
        lbl = Gtk.Label(label=tr("Esconderlas ahora"), xalign=0)
        lbl.set_hexpand(True)
        r.append(lbl)
        self._dnd_sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._dnd_sw.set_active(bool(self._comp() and self._comp().dnd_manual))
        self._dnd_sw.connect("notify::active",
                             lambda s, _p: self._comp().set_dnd_manual(s.get_active()))
        r.append(self._dnd_sw)
        box.append(r)

        self._refresh()
        self._tick = GLib.timeout_add(1000, self._refresh)
        self.connect("close-request", self._on_close)

    # ── piezas ───────────────────────────────────────────────────────────
    def _comp(self):
        return getattr(self.app, "companion", None)

    @staticmethod
    def _dim(text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.add_css_class("dim-label")
        return lbl

    def _switch(self, key, title, hint=None):
        row = Gtk.Box(spacing=10)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.set_hexpand(True)
        lbl = Gtk.Label(label=title, xalign=0)
        lbl.set_wrap(True)
        col.append(lbl)
        if hint:
            h = self._dim(hint)
            h.set_wrap(True)
            col.append(h)
        row.append(col)
        sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        sw.set_active(bool(comp_mod.cfg(key)))
        sw.connect("notify::active", lambda s, _p: self._set(key, s.get_active()))
        row.append(sw)
        self._box.append(row)
        return sw

    def _spin(self, key, lo, hi, step=1):
        sp = Gtk.SpinButton(adjustment=Gtk.Adjustment(
            value=int(comp_mod.cfg(key) or 0), lower=lo, upper=hi,
            step_increment=step, page_increment=step * 5))
        sp.set_numeric(True)
        sp.connect("value-changed", lambda s: self._set(key, int(s.get_value())))
        return sp

    def _choice(self, key, items):
        dd = Gtk.DropDown.new_from_strings([n for _k, n in items])
        keys = [k for k, _n in items]
        cur = comp_mod.cfg(key)
        dd.set_selected(keys.index(cur) if cur in keys else 0)
        dd.connect("notify::selected", lambda d, _p: settings.set_val(key, keys[d.get_selected()]))
        return dd

    def _open_match(self):
        from .match_dialog import MatchWindow
        MatchWindow(self.app, parent=self.get_transient_for()).present()
        self.close()

    def _set(self, key, value):
        settings.set_val(key, value)
        c = self._comp()
        if c is not None:
            c.apply_moods()
            c._update_dnd()

    def _play(self, kind):
        c = self._comp()
        ok = c is not None and c.start_game(kind)
        self._game_msg.set_text("" if ok else tr(
            "Hacen falta dos mascotas despiertas en modo Vida (y para las escondidas, una ventana que llegue hasta el suelo)."))

    def _refresh(self):
        c = self._comp()
        if c is None:
            return True
        st = c.sys_state
        bits = []
        if st.get("music"):
            bits.append(tr("🎵 suena música"))
        bits.append(tr("CPU {n} %", n=int(st.get("cpu") or 0)))
        if st.get("battery") is not None:
            bits.append(tr("🔋 {n} %", n=st["battery"]))
        if st.get("night"):
            bits.append(tr("🌙 de noche"))
        if st.get("sharing"):
            bits.append(tr("📺 compartiendo pantalla"))
        self._status.set_text(tr("Ahora: {estado}", estado=" · ".join(bits)))
        p = c.pomodoro
        if p.running:
            self._pomo_btn.set_label(tr("Detener"))
            what = tr("Trabajando") if p.phase == "work" else tr("Descansando")
            self._pomo_lbl.set_text(f"{what} · {comp_mod._fmt(p.remaining())}")
        else:
            self._pomo_btn.set_label(tr("Empezar"))
            self._pomo_lbl.set_text("")
        return True

    def _on_close(self, *_):
        if self._tick:
            GLib.source_remove(self._tick)
            self._tick = 0
        return False
