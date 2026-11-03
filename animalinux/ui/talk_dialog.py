"""
Ventana «Hablar con tu mascota»: activar la charla, revisar si el equipo
puede con la IA, bajar el modelo y la voz, y elegir la personalidad y el
nombre de llamada de cada mascota. Todo se guarda al momento.
"""
import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .. import settings  # noqa: E402
from ..i18n import N_, get_language, tr  # noqa: E402
from ..talk import brain as brain_mod, hw, personas, voice  # noqa: E402
from . import guide_widgets as gw  # noqa: E402

LEVEL_TEXT = {
    "fast": N_("✅ Tu equipo va sobrado: la IA responderá rápido."),
    "ok":   N_("✅ Tu equipo cumple: la IA irá bien."),
    "slow": N_("⚠️ Tu equipo es justo: la IA irá lenta. Se recomienda el modelo liviano o las frases escritas."),
    "none": N_("❌ Tu equipo no cumple los requisitos de la IA: se usarán las frases escritas (sin IA)."),
}
REASON_TEXT = {
    "ram_low":  N_("menos de 4 GB de RAM"),
    "ram_mid":  N_("menos de 8 GB de RAM"),
    "no_avx2":  N_("el procesador no tiene AVX2"),
    "cpu_weak": N_("un solo núcleo de CPU"),
    "cpu_mid":  N_("menos de 4 núcleos"),
    "disk_low": N_("poco espacio libre en disco"),
    "disk_mid": N_("no hay espacio para el modelo grande"),
}
SPEED_TEXT = {
    "fast": N_("🚀 {n} tokens/s: responde casi al instante."),
    "ok":   N_("✅ {n} tokens/s: va bien."),
    "slow": N_("⚠️ {n} tokens/s: irá lenta (unos segundos por respuesta)."),
    "none": N_("❌ {n} tokens/s: demasiado lenta; mejor las frases escritas."),
}
ENGINES = (("auto", N_("Automático (IA si se puede, si no frases)")),
           ("ai", N_("Siempre IA")),
           ("phrases", N_("Siempre frases escritas (sin IA)")))


class TalkWindow(Gtk.Window):
    def __init__(self, app, parent=None):
        super().__init__(title=tr("Hablar con tu mascota"))
        if parent is not None:
            self.set_transient_for(parent)
        self.app = app
        self.brain = app.talk
        self.set_default_size(540, 720)
        sc = Gtk.ScrolledWindow()
        sc.set_vexpand(True)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for m in ("start", "end"):
            getattr(box, f"set_margin_{m}")(20)
        box.set_margin_top(16)
        box.set_margin_bottom(18)
        sc.set_child(box)
        self.set_child(sc)
        self._box = box
        self._busy = False

        box.append(gw.section_title(tr("🗣 Hablar con tu mascota")))
        box.append(gw.body(tr("Llámala con «oye <nombre>» o pulsa el micrófono, y te responde en una nube según su personalidad. Todo pasa en tu equipo: no se envía nada a internet.")))
        self._switch(box, "talk_enabled", tr("Activar"))

        # ── equipo ───────────────────────────────────────────────────────
        box.append(gw.section_title(tr("Tu equipo")))
        self._hw_lbl = self._label(box)
        self._hw_detail = self._label(box, dim=True)

        # ── motor ────────────────────────────────────────────────────────
        box.append(gw.section_title(tr("Cómo responde")))
        keys = [k for k, _n in ENGINES]
        dd = Gtk.DropDown.new_from_strings([tr(n) for _k, n in ENGINES])
        cur = brain_mod.cfg("talk_engine")
        dd.set_selected(keys.index(cur) if cur in keys else 0)
        dd.connect("notify::selected", lambda d, _p: self._set("talk_engine", keys[d.get_selected()]))
        box.append(dd)
        self._engine_lbl = self._label(box, dim=True)

        # ── IA ───────────────────────────────────────────────────────────
        box.append(gw.section_title(tr("🧠 IA local (Ollama)")))
        self._ollama_lbl = self._label(box)
        self._install_lbl = self._label(box, dim=True, selectable=True)
        mrow = Gtk.Box(spacing=8)
        self._models = list(hw.MODELS)
        names = [tr("{modelo} · {gb} GB", modelo=hw.MODELS[m]["label"], gb=hw.MODELS[m]["disk"])
                 for m in self._models]
        self._model_dd = Gtk.DropDown.new_from_strings(names)
        self._model_dd.set_hexpand(True)
        self._model_dd.set_selected(self._models.index(self.brain.model()))
        self._model_dd.connect("notify::selected", self._on_model)
        mrow.append(self._model_dd)
        self._dl_btn = Gtk.Button(label=tr("Descargar"))
        self._dl_btn.add_css_class("suggested-action")
        self._dl_btn.connect("clicked", self._download_model)
        mrow.append(self._dl_btn)
        box.append(mrow)
        self._dl_bar = Gtk.ProgressBar()
        self._dl_bar.set_show_text(True)
        self._dl_bar.set_visible(False)
        box.append(self._dl_bar)
        brow = Gtk.Box(spacing=8)
        self._bench_btn = Gtk.Button(label=tr("⏱ Medir velocidad"))
        self._bench_btn.connect("clicked", self._bench)
        brow.append(self._bench_btn)
        recheck = Gtk.Button(label=tr("↻ Comprobar de nuevo"))
        recheck.connect("clicked", lambda _b: self.brain.refresh_status())
        brow.append(recheck)
        box.append(brow)
        self._speed_lbl = self._label(box, dim=True)
        self._switch(box, "talk_swear", tr("🤬 La malhablada puede decir groserías"),
                     tr("Apágalo para que solo se burle sin palabrotas."))

        # ── voz ──────────────────────────────────────────────────────────
        box.append(gw.section_title(tr("🎤 Voz")))
        self._voice_lbl = self._label(box)
        vrow = Gtk.Box(spacing=8)
        self._vdl_btn = Gtk.Button(label="")
        self._vdl_btn.connect("clicked", self._download_voice)
        vrow.append(self._vdl_btn)
        self._vdl_bar = Gtk.ProgressBar()
        self._vdl_bar.set_hexpand(True)
        self._vdl_bar.set_valign(Gtk.Align.CENTER)
        self._vdl_bar.set_visible(False)
        vrow.append(self._vdl_bar)
        box.append(vrow)
        self._wh_lbl = self._label(box, dim=True)
        self._wh_btn = Gtk.Button(label=tr("✨ Entender mejor tu voz (Whisper, 145 MB)"))
        self._wh_btn.set_halign(Gtk.Align.START)
        self._wh_btn.connect("clicked", self._download_whisper)
        box.append(self._wh_btn)
        self._wh_sw = self._switch(box, "talk_whisper", tr("✨ Transcribir tu frase con Whisper"),
                                   tr("Más preciso con voz real y acentos. Tarda ~0,5 s más por frase."))
        self._switch(box, "talk_wake", tr("👂 Escuchar «oye <nombre>» todo el rato"),
                     tr("Como «Ok Google». Gasta muy poco (~2-3 % de un núcleo) y en silencio casi nada. El audio no se guarda ni sale de tu equipo."))
        self._switch(box, "talk_mic_button", tr("🎤 Botón de micrófono en pantalla"),
                     tr("Clic: hablar. Clic derecho: escribirle. Arrástralo para moverlo."))

        # ── mascotas ─────────────────────────────────────────────────────
        box.append(gw.section_title(tr("🐾 Personalidad de cada mascota")))
        box.append(gw.note(tr("El nombre de llamada es lo que dices después de «oye». Mejor una o dos palabras fáciles de decir.")))
        self._pets_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self._pets_box)
        self._build_pets()

        # ── probar ───────────────────────────────────────────────────────
        trow = Gtk.Box(spacing=8)
        b = Gtk.Button(label=tr("🎤 Hablarle ahora"))
        b.add_css_class("pill")
        b.connect("clicked", lambda _b: self.brain.ask())
        trow.append(b)
        b = Gtk.Button(label=tr("💬 Escribirle"))
        b.add_css_class("pill")
        b.connect("clicked", lambda _b: self.brain.open_type())
        trow.append(b)
        box.append(trow)
        self._err_lbl = self._label(box, dim=True)

        self.brain.on_status(self._refresh)
        self.connect("close-request", self._on_close)
        self._refresh()
        self.brain.refresh_status()

    # ── piezas ───────────────────────────────────────────────────────────
    @staticmethod
    def _label(box, dim=False, selectable=False):
        lbl = Gtk.Label(xalign=0)
        lbl.set_wrap(True)
        if dim:
            lbl.add_css_class("dim-label")
        if selectable:
            lbl.set_selectable(True)
        box.append(lbl)
        return lbl

    def _switch(self, box, key, title, hint=None):
        row = Gtk.Box(spacing=10)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.set_hexpand(True)
        lbl = Gtk.Label(label=title, xalign=0)
        lbl.set_wrap(True)
        col.append(lbl)
        if hint:
            h = Gtk.Label(label=hint, xalign=0)
            h.add_css_class("dim-label")
            h.set_wrap(True)
            col.append(h)
        row.append(col)
        sw = Gtk.Switch(valign=Gtk.Align.CENTER)
        sw.set_active(bool(brain_mod.cfg(key)))
        sw.connect("notify::active", lambda s, _p: self._set(key, s.get_active()))
        row.append(sw)
        box.append(row)
        return sw

    def _set(self, key, value):
        settings.set_val(key, value)
        if key == "talk_engine":
            self.brain.too_slow = False
        self.brain.apply()

    def _build_pets(self):
        child = self._pets_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._pets_box.remove(child)
            child = nxt
        pets = self.brain.pets()
        if not pets:
            self._pets_box.append(gw.note(tr("Pon alguna mascota en el escritorio para configurarla.")))
            return
        pkeys = list(personas.PERSONAS)
        plabels = [tr(personas.PERSONAS[k]["label"]) for k in pkeys]
        for aid, name in pets:
            pc = self.brain.pet_cfg(aid)
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.add_css_class("card")
            for m in ("start", "end", "top", "bottom"):
                getattr(card, f"set_margin_{m}")(2)
            title = Gtk.Label(label=name, xalign=0)
            title.add_css_class("heading")
            card.append(title)
            row = Gtk.Box(spacing=8)
            dd = Gtk.DropDown.new_from_strings(plabels)
            dd.set_selected(pkeys.index(pc["persona"]))
            dd.connect("notify::selected",
                       lambda d, _p, a=aid: self.brain.set_pet_cfg(a, persona=pkeys[d.get_selected()]))
            row.append(dd)
            ey = Gtk.Label(label=tr("oye"))
            ey.add_css_class("dim-label")
            row.append(ey)
            ent = Gtk.Entry()
            ent.set_text(pc["wake"])
            ent.set_max_length(24)
            ent.set_hexpand(True)
            ent.set_placeholder_text(tr("nombre de llamada"))
            row.append(ent)
            card.append(row)
            hint = Gtk.Label(xalign=0)
            hint.add_css_class("dim-label")
            hint.set_wrap(True)
            card.append(hint)
            ent.connect("changed", lambda e, a=aid, h=hint: self._wake_changed(a, e, h))
            self._check_wake(aid, pc["wake"], hint)
            self._pets_box.append(card)

    def _wake_changed(self, aid, entry, hint):
        text = entry.get_text()
        self.brain.set_pet_cfg(aid, wake=text)
        if getattr(entry, "_chk", 0):
            GLib.source_remove(entry._chk)
        entry._chk = GLib.timeout_add(500, self._delayed_check, entry, hint, aid)

    def _delayed_check(self, entry, hint, aid=None):
        entry._chk = 0
        self._check_wake(aid, entry.get_text(), hint)
        return False

    def _check_wake(self, aid, name, hint):
        if aid is not None and self.brain.wake_taken(aid, name):
            hint.set_text(tr("⚠️ Otra mascota ya se llama así: ponle otro nombre de llamada."))
            return
        if not self.brain._voice_ready():
            hint.set_text("")
            return

        def done(sp):
            if sp is None:
                hint.set_text("")
            elif sp and any(len(w) == 1 for w in sp[0].split()):
                hint.set_text(tr("⚠️ Difícil de reconocer (lo oiría como «{forma}»): mejor otro nombre.", forma=sp[0]))
            elif sp:
                hint.set_text(tr("✓ Te entenderá como «{forma}».", forma=sp[0]))
            else:
                hint.set_text(tr("⚠️ No sabe cómo se dice este nombre: prueba otro (una palabra común funciona mejor)."))
        self.brain.check_wake_name(name, done)

    # ── acciones ─────────────────────────────────────────────────────────
    def _on_model(self, dd, _p):
        m = self._models[dd.get_selected()]
        settings.set_val("talk_model", m)
        self.brain.too_slow = False
        self._refresh()

    def _download_model(self, _b):
        if self._busy:
            return
        self._busy = True
        name = self._models[self._model_dd.get_selected()]
        self._dl_bar.set_visible(True)
        self._dl_bar.set_fraction(0)
        self._dl_bar.set_text(tr("Preparando…"))
        self._dl_btn.set_sensitive(False)

        def prog(f, status):
            if f is None:
                self._dl_bar.pulse()
            else:
                self._dl_bar.set_fraction(f)
            self._dl_bar.set_text(f"{int((f or 0) * 100)} %  {status}")
            return False

        def done(err):
            self._busy = False
            self._dl_btn.set_sensitive(True)
            self._dl_bar.set_visible(bool(err))
            if err:
                self._dl_bar.set_text(tr("Error: {e}", e=err))
            return False
        self.brain.download_model(name, prog, done)

    def _download_voice(self, _b):
        if self._busy:
            return
        self._busy = True
        self._vdl_bar.set_visible(True)
        self._vdl_btn.set_sensitive(False)

        def prog(f):
            if f is None:
                self._vdl_bar.pulse()
            else:
                self._vdl_bar.set_fraction(f)
            return False

        def done(err):
            self._busy = False
            self._vdl_btn.set_sensitive(True)
            self._vdl_bar.set_visible(False)
            if err:
                self._err_lbl.set_text(tr("Error: {e}", e=err))
            self._build_pets()
            return False
        self.brain.download_voice(prog, done)

    def _download_whisper(self, _b):
        self._wh_btn.set_sensitive(False)
        self._wh_lbl.set_text(tr("Descargando Whisper…"))

        def done(err):
            self._wh_btn.set_sensitive(True)
            self._wh_lbl.set_text(tr("Error: {e}", e=err) if err else "")
        self.brain.download_whisper(done)

    def _bench(self, _b):
        self._bench_btn.set_sensitive(False)
        self._speed_lbl.set_text(tr("Midiendo… (la primera vez carga el modelo, puede tardar)"))

        def done(tps, err):
            self._bench_btn.set_sensitive(True)
            if err:
                self._speed_lbl.set_text(tr("Error: {e}", e=err))
            else:
                self._speed_lbl.set_text(tr(SPEED_TEXT[hw.rate_speed(tps)], n=f"{tps:.1f}"))
        self.brain.benchmark(done)

    # ── refresco ─────────────────────────────────────────────────────────
    def _refresh(self):
        b = self.brain
        h = b.hw
        st = b.status
        if h is None:
            self._hw_lbl.set_text(tr("Revisando tu equipo…"))
            self._hw_detail.set_text("")
        else:
            self._hw_lbl.set_text(tr(LEVEL_TEXT[h["level"]]))
            bits = [tr("{n} GB de RAM", n=h["ram_gb"]), tr("{n} núcleos", n=h["cores"])]
            if h["vram_gb"]:
                bits.append(tr("GPU {n} GB", n=h["vram_gb"]))
            bits.append(tr("{n} GB libres", n=h["disk_gb"]))
            why = ", ".join(tr(REASON_TEXT[r]) for r in h["reasons"] if r in REASON_TEXT)
            extra = f"\n{tr('Motivo')}: {why}" if why else ""
            if st.get("saver"):
                extra += "\n" + tr("⚡ Estás en modo ahorro de energía: la IA irá varias veces más lenta.")
            self._hw_detail.set_text(" · ".join(bits) + extra)
        eng = b.engine()
        txt = tr("Ahora responde con: {motor}",
                 motor=tr("IA") if eng == "ai" else tr("frases escritas"))
        if b.too_slow:
            txt += "\n" + tr("La IA iba demasiado lenta en tu equipo, así que se cambió a frases escritas.")
        self._engine_lbl.set_text(txt)
        # Ollama
        if not st:
            self._ollama_lbl.set_text(tr("Comprobando…"))
        elif not st.get("ollama"):
            self._ollama_lbl.set_text(tr("❌ Ollama no está instalado."))
        elif b.model_installed():
            self._ollama_lbl.set_text(tr("✅ Ollama listo y modelo descargado."))
        elif st.get("server"):
            self._ollama_lbl.set_text(tr("⬇ Falta descargar el modelo."))
        else:
            self._ollama_lbl.set_text(tr("✅ Ollama instalado (se arranca solo cuando hace falta)."))
        if st and not st.get("ollama"):
            cmd = ("https://ollama.com/download" if sys.platform == "win32"
                   else "sudo pacman -S ollama   ·   https://ollama.com/download")
            self._install_lbl.set_text(tr("Para usar la IA, instálalo: {cmd}", cmd=cmd))
        else:
            self._install_lbl.set_text("")
        self._dl_btn.set_visible(bool(st.get("ollama")) and not b.model_installed()
                                 and not self._busy)
        self._bench_btn.set_sensitive(b.model_installed())
        # voz
        lang = get_language()
        mb = voice.MODELS.get(lang, voice.MODELS["es"])[2]
        if not st:
            self._voice_lbl.set_text("")
        elif not st.get("vosk") and getattr(sys, "frozen", False):
            # AnimaWin empaquetado: un pip install no llega dentro de la app
            self._voice_lbl.set_text(tr("En esta versión todavía no viene la voz: puedes escribirle (clic derecho en el micrófono)."))
            self._vdl_btn.set_visible(False)
        elif not st.get("vosk"):
            self._voice_lbl.set_text(tr("❌ Falta el reconocimiento de voz (Vosk). Instálalo: {cmd}",
                                        cmd="sudo pacman -S python-vosk" if sys.platform != "win32"
                                        else "pip install vosk sounddevice"))
            self._vdl_btn.set_visible(False)
        elif not st.get("mic"):
            self._voice_lbl.set_text(tr("❌ No encuentro cómo leer el micrófono (pw-record, parecord o arecord)."))
            self._vdl_btn.set_visible(False)
        elif not voice.model_installed(lang):
            self._voice_lbl.set_text(tr("⬇ Falta el modelo de voz de tu idioma ({mb} MB).", mb=mb))
            self._vdl_btn.set_label(tr("Descargar voz"))
            self._vdl_btn.set_visible(not self._busy)
        else:
            state = {"wake": tr("escuchando «oye…»"), "command": tr("oyendo tu frase"),
                     "off": tr("micrófono apagado")}.get(b.voice_state, "")
            self._voice_lbl.set_text(tr("✅ Voz lista ({estado}).", estado=state))
            self._vdl_btn.set_visible(False)
        # Whisper (transcripción precisa, opcional)
        ready_voice = bool(st.get("vosk") and st.get("mic"))
        has_pkg, has_model = st.get("whisper_pkg"), st.get("whisper")
        self._wh_btn.set_visible(bool(ready_voice and has_pkg and not has_model))
        self._wh_sw.get_parent().set_visible(bool(ready_voice and has_model))
        if ready_voice and not has_pkg and sys.platform != "win32":
            self._wh_lbl.set_text(tr("Para entender mejor tu voz instala Whisper: {cmd}",
                                     cmd="paru -S python-faster-whisper"))
        elif not self._wh_lbl.get_text().startswith(tr("Descargando Whisper…")):
            self._wh_lbl.set_text("")
        self._err_lbl.set_text(tr("Último error: {e}", e=b.last_error) if b.last_error else "")

    def _on_close(self, *_a):
        self.brain.off_status(self._refresh)
        return False
