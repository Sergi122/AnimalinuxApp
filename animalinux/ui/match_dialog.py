"""
Menú «Partido»: deporte, equipos, tiempo o puntos, dificultad y ¡Empezar!

Cada mascota (con vida y en el escritorio) va en UN solo equipo: rival, tu
equipo (una como ayudante) o fuera. Lo elegido se recuerda para la próxima.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import settings  # noqa: E402
from ..core import companion as comp_mod  # noqa: E402
from ..i18n import tr  # noqa: E402
from ..sports import MAX_RIVALS  # noqa: E402
from . import guide_widgets as gw  # noqa: E402

_CSS = """
button.match-card { padding: 10px 14px; border-radius: 14px; border: 2px solid transparent; }
button.match-card:checked { background: rgba(90, 140, 255, 0.30); border-color: rgba(120, 165, 255, 0.95); }
.team-row { padding: 6px 8px; border-radius: 10px; background: rgba(255, 255, 255, 0.04); }
.team-seg button { padding: 4px 10px; }
.team-seg button.t-rival:checked { background: rgba(255, 110, 140, 0.55); color: #ffffff; }
.team-seg button.t-mine:checked { background: rgba(90, 170, 255, 0.6); color: #ffffff; }
.team-seg button.t-out:checked { background: rgba(255, 255, 255, 0.22); color: #ffffff; }
"""


class MatchWindow(Gtk.Window):
    def __init__(self, app, parent=None, sport=None):
        super().__init__(title=tr("Partido"))
        if parent is not None:
            self.set_transient_for(parent)
        self.app = app
        self.set_default_size(560, 640)
        prov = Gtk.CssProvider()
        if hasattr(prov, "load_from_string"):
            prov.load_from_string(_CSS)
        else:
            prov.load_from_data(_CSS.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)

        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for m in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{m}")(20)
        sc.set_child(box)
        self.set_child(sc)

        # ── deporte ──────────────────────────────────────────────────────
        box.append(gw.section_title(tr("Deporte")))
        row = Gtk.Box(spacing=8, homogeneous=True)
        self._sport = sport or comp_mod.cfg("sport_last") or "football"
        first = None
        self._sport_btns = {}
        for key, emo, name, hint in (
                ("football", "⚽", tr("Fútbol"), tr("Empujas el balón")),
                ("volley", "🏐", tr("Vóley"), tr("Empujas + anillos")),
                ("basket", "🏀", tr("Básquet"), tr("Agarras 3 s y tiras"))):
            b = Gtk.ToggleButton()
            b.add_css_class("match-card")
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            big = Gtk.Label(label=emo)
            big.set_markup(f"<span size='xx-large'>{emo}</span>")
            v.append(big)
            v.append(Gtk.Label(label=name))
            d = Gtk.Label(label=hint)
            d.add_css_class("dim-label")
            v.append(d)
            b.set_child(v)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.set_active(key == self._sport)
            b.connect("toggled", lambda bt, k=key: bt.get_active() and self._pick_sport(k))
            self._sport_btns[key] = b
            row.append(b)
        box.append(row)

        # ── equipos ──────────────────────────────────────────────────────
        box.append(gw.section_title(tr("Equipos")))
        box.append(gw.body(tr("Cada mascota juega en un solo equipo. Rivales: de 1 a 4. En tu equipo puede jugar una (arquera / ayudante).")))
        self._team = {}            # id -> "rival" | "mine" | "out"
        rivals = set(comp_mod.cfg("sport_rival_ids") or [])
        mine = comp_mod.cfg("sport_helper_id") or ""
        pets = [a for a in app.library.animations.values()
                if a.get("mode") == "life" and a.get("on_desktop")]
        self._teams_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        if not pets:
            self._teams_box.append(gw.note(tr("No hay mascotas con vida en el escritorio. Activa alguna en el panel.")))
        default_rivals = [a["id"] for a in pets][:2]
        for a in pets:
            aid = a["id"]
            state = ("mine" if aid == mine else "rival" if aid in rivals else
                     "out" if rivals else ("rival" if aid in default_rivals else "out"))
            self._team[aid] = state
            self._teams_box.append(self._pet_row(a, state))
        box.append(self._teams_box)
        self._count = Gtk.Label(xalign=0)
        self._count.add_css_class("dim-label")
        box.append(self._count)

        # ── reglas del partido ───────────────────────────────────────────
        box.append(gw.section_title(tr("Partido")))
        g = Gtk.Grid(column_spacing=12, row_spacing=8)
        g.attach(Gtk.Label(label=tr("Ganar"), xalign=0), 0, 0, 1, 1)
        modes = [("points:10", tr("Llegar a 10 puntos")), ("time:5", tr("5 minutos")),
                 ("time:10", tr("10 minutos"))]
        cur = (f"points:{comp_mod.cfg('sport_points')}" if comp_mod.cfg("sport_mode") == "points"
               else f"time:{comp_mod.cfg('sport_minutes')}")
        self._modes = [k for k, _n in modes]
        self._mode_dd = Gtk.DropDown.new_from_strings([n for _k, n in modes])
        self._mode_dd.set_selected(self._modes.index(cur) if cur in self._modes else 0)
        self._mode_dd.set_hexpand(True)
        g.attach(self._mode_dd, 1, 0, 1, 1)
        g.attach(Gtk.Label(label=tr("Dificultad"), xalign=0), 0, 1, 1, 1)
        diffs = [("easy", tr("Fácil")), ("medium", tr("Medio")), ("hard", tr("Difícil"))]
        self._diffs = [k for k, _n in diffs]
        self._diff_dd = Gtk.DropDown.new_from_strings([n for _k, n in diffs])
        d0 = comp_mod.cfg("sport_difficulty")
        self._diff_dd.set_selected(self._diffs.index(d0) if d0 in self._diffs else 1)
        g.attach(self._diff_dd, 1, 1, 1, 1)
        box.append(g)
        self._diff_hint = gw.note("")
        box.append(self._diff_hint)
        self._diff_dd.connect("notify::selected", lambda *_: self._update())

        # ── empezar ──────────────────────────────────────────────────────
        self._msg = Gtk.Label(xalign=0)
        self._msg.set_wrap(True)
        self._msg.add_css_class("dim-label")
        box.append(self._msg)
        bar = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=tr("Cancelar"))
        cancel.connect("clicked", lambda _b: self.close())
        self._go = Gtk.Button(label=tr("¡Empezar!"))
        self._go.add_css_class("suggested-action")
        self._go.add_css_class("pill")
        self._go.connect("clicked", lambda _b: self._start())
        bar.append(cancel)
        bar.append(self._go)
        box.append(bar)
        self._update()

    # ── piezas ───────────────────────────────────────────────────────────
    def _thumb(self, aid):
        fd = self.app.library.frames_dir(aid)
        p = fd / "frame_0000.png"
        if not p.exists():
            subs = sorted(x for x in fd.iterdir() if x.is_dir()) if fd.exists() else []
            for sdir in subs:
                if (sdir / "frame_0000.png").exists():
                    p = sdir / "frame_0000.png"
                    break
        img = Gtk.Image()
        img.set_pixel_size(44)
        if p.exists():
            try:
                from PIL import Image
                im = Image.open(p).convert("RGBA")
                im.thumbnail((88, 88), Image.NEAREST if max(im.size) <= 96 else Image.LANCZOS)
                tex = Gdk.MemoryTexture.new(im.width, im.height, Gdk.MemoryFormat.R8G8B8A8,
                                            GLib.Bytes.new(im.tobytes()), im.width * 4)
                img.set_from_paintable(tex)
            except Exception:  # noqa: BLE001
                pass
        return img

    def _pet_row(self, a, state):
        row = Gtk.Box(spacing=10)
        row.add_css_class("team-row")
        row.append(self._thumb(a["id"]))
        name = Gtk.Label(label=a.get("name", a["id"]), xalign=0)
        name.set_hexpand(True)
        row.append(name)
        seg = Gtk.Box(spacing=2)
        seg.add_css_class("team-seg")
        seg.set_valign(Gtk.Align.CENTER)
        first = None
        for key, label in (("rival", tr("Rival")), ("mine", tr("Mi equipo")), ("out", tr("No juega"))):
            b = Gtk.ToggleButton(label=label)
            b.add_css_class("t-" + key)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.set_active(state == key)
            b.connect("toggled", lambda bt, k=key, aid=a["id"]: bt.get_active() and self._set_team(aid, k))
            seg.append(b)
        row.append(seg)
        return row

    def _set_team(self, aid, team):
        if team == "mine":
            # solo una en tu equipo: la anterior pasa a «No juega»
            for other, t in self._team.items():
                if other != aid and t == "mine":
                    self._team[other] = "out"
            self._rebuild_rows()
        self._team[aid] = team
        self._update()

    def _rebuild_rows(self):
        child = self._teams_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._teams_box.remove(child)
            child = nxt
        for aid, state in self._team.items():
            a = self.app.library.animations.get(aid)
            if a:
                self._teams_box.append(self._pet_row(a, state))

    def _pick_sport(self, key):
        self._sport = key
        self._update()

    def _update(self):
        rivals = [k for k, t in self._team.items() if t == "rival"]
        mine = [k for k, t in self._team.items() if t == "mine"]
        role = {"football": tr("arquera"), "volley": tr("ayudante"),
                "basket": tr("ayudante")}[self._sport]
        txt = tr("Rivales: {n} de {m}", n=len(rivals), m=MAX_RIVALS)
        txt += " · " + (tr("Tu equipo: tú + 1 {rol}", rol=role) if mine else tr("Tu equipo: solo tú"))
        self._count.set_text(txt)
        ok = 1 <= len(rivals) <= MAX_RIVALS
        self._go.set_sensitive(ok)
        self._msg.set_text("" if ok else (tr("Elige al menos una mascota rival.") if not rivals
                                          else tr("Como máximo 4 rivales.")))
        d = self._diffs[self._diff_dd.get_selected()]
        self._diff_hint.get_first_child().set_text({
            "easy": tr("Fácil: juegan despacio y arman la jugada completa ~3 de cada 10 veces."),
            "medium": tr("Medio: ~6 de cada 10 jugadas completas; atajan y taponan a veces."),
            "hard": tr("Difícil: rápidas, ~9 de cada 10 jugadas completas y casi no fallan."),
        }[d])

    def _start(self):
        rivals = [k for k, t in self._team.items() if t == "rival"]
        mine = next((k for k, t in self._team.items() if t == "mine"), "")
        kind, val = self._modes[self._mode_dd.get_selected()].split(":")
        settings.set_val("sport_mode", kind)
        settings.set_val("sport_points" if kind == "points" else "sport_minutes", int(val))
        settings.set_val("sport_difficulty", self._diffs[self._diff_dd.get_selected()])
        settings.set_val("sport_rival_ids", rivals)
        settings.set_val("sport_helper_id", mine)
        settings.set_val("sport_last", self._sport)
        match, why = self.app.start_sport(self._sport)
        if match is None:
            self._msg.set_text(why or "")
            return
        self.close()
