"""
El cerebro de la charla: une voz, IA/frases y la nube de cada mascota.

Corre en el hilo principal (GLib). Lo lento (Vosk, Ollama, descargas) va en
hilos y vuelve con GLib.idle_add.

Motor de respuestas (`talk_engine`):
  "auto"     IA si está lista (Ollama + modelo + equipo que cumple) y si no,
             frases escritas. Si la IA resulta demasiado lenta en la práctica
             (<2 tokens/s) o falla, pasa sola a frases.
  "ai"       siempre IA (si falla, frases para no dejarte sin respuesta).
  "phrases"  siempre frases escritas.

Privacidad: el historial (últimas 3 frases por mascota) solo vive en RAM.
"""
import random
import threading
import time
from collections import deque

from gi.repository import GLib

from .. import settings
from ..i18n import get_language, tr
from . import hw, llm, personas, phrases, voice

DEFAULTS = {
    "talk_enabled": False,
    "talk_engine": "auto",
    "talk_model": "",            # "" = el que recomiende hw.assess()
    "talk_wake": False,          # escuchar «ey <nombre>» todo el rato
    "talk_mic_button": True,     # botón de micrófono flotante
    "talk_swear": True,          # la malhablada puede decir groserías
    "talk_whisper": True,        # si Whisper está instalado, transcribe la frase
    "talk_pet": "",              # quién responde al botón ("" = automática)
    "talk_pets": {},             # anim_id -> {"persona": ..., "wake": ...}
}
SLOW_TPS = 2.0
HISTORY = 3


def cfg(key):
    """Valor de settings.json con el tipo esperado (un archivo dañado o
    editado a mano no debe romper la charla)."""
    v = settings.get(key, DEFAULTS.get(key))
    d = DEFAULTS.get(key)
    if v is None or (d is not None and not isinstance(v, type(d))):
        return d
    return v


class TalkBrain:
    def __init__(self, app):
        self.app = app
        self.listener = None
        self.mic_button = None
        self.type_window = None
        self.hw = None                   # resultado de hw.assess()
        self.status = {}                 # ver refresh_status()
        self.voice_state = "off"
        self.last_tps = 0.0
        self.too_slow = False
        self.last_error = ""
        self._hist = {}
        self._gen = {}                   # pet_id -> nº de pregunta en curso
        self._last_pet = None
        self._status_cbs = []
        self._refreshing = False
        self._warm_at = 0.0

    # ── arranque / parada ─────────────────────────────────────────────────
    def start(self):
        self.refresh_status()
        self.apply()

    def stop(self):
        if self.listener is not None:
            self.listener.shutdown()
            self.listener = None
        self._set_mic_button(False)
        if self.type_window is not None:
            self.type_window.close()
        threading.Thread(target=llm.stop_server, daemon=True).start()

    def apply(self):
        """Aplica la configuración (la llama la ventana al cambiar algo)."""
        on = bool(cfg("talk_enabled"))
        self._set_mic_button(on and bool(cfg("talk_mic_button")))
        if on and cfg("talk_wake") and self._voice_ready():
            self._ensure_listener()
            self.listener.set_names(self.wake_names())
            self.listener.start_wake()
        elif self.listener is not None:
            self.listener.stop_wake()
            self.listener.release()
        self._notify()

    def pets_changed(self):
        if self.listener is not None and self.listener.state != "off":
            self.listener.set_names(self.wake_names())
        self._notify()

    # ── estado (para la ventana) ──────────────────────────────────────────
    def on_status(self, cb):
        self._status_cbs.append(cb)

    def off_status(self, cb):
        if cb in self._status_cbs:
            self._status_cbs.remove(cb)

    def _notify(self):
        for cb in list(self._status_cbs):
            try:
                cb()
            except Exception:  # noqa: BLE001
                pass

    def refresh_status(self, done=None):
        """Revisa equipo, Ollama, modelos y voz en un hilo."""
        if self._refreshing:
            return
        self._refreshing = True

        def work():
            st = {}
            try:
                if self.hw is None:
                    self.hw = hw.assess()
                st["saver"] = hw.power_saver()
                st["ollama"] = bool(llm.find_binary())
                st["server"] = llm.is_running() if st["ollama"] else False
                st["models"] = llm.installed_models() if st["server"] else []
                st["vosk"] = voice.vosk_available()
                st["mic"] = voice.mic_available()
                st["voice_model"] = voice.model_installed(get_language())
                st["whisper_pkg"] = voice.whisper_available()
                st["whisper"] = voice.whisper_installed()
            finally:
                GLib.idle_add(fin, st)

        def fin(st):
            self._refreshing = False
            self.status = st
            self._notify()
            if done is not None:
                done()
            return False
        threading.Thread(target=work, daemon=True).start()

    def model(self):
        m = cfg("talk_model")
        if m in hw.MODELS:
            return m
        rec = (self.hw or {}).get("model")
        return rec or hw.DEFAULT_MODEL

    def model_installed(self, name=None):
        name = name or self.model()
        ms = self.status.get("models", [])
        return name in ms or f"{name}:latest" in ms

    def ai_possible(self):
        return bool(self.status.get("ollama")) and (self.hw or {}).get("level") != "none"

    def engine(self):
        """Motor que se usará AHORA: "ai" o "phrases"."""
        want = cfg("talk_engine")
        if want == "phrases":
            return "phrases"
        if not self.status.get("ollama"):
            return "phrases"
        if want == "auto" and ((self.hw or {}).get("level") == "none" or self.too_slow):
            return "phrases"
        # el modelo se comprueba al usarlo (si no está, frases)
        return "ai"

    def _voice_ready(self):
        st = self.status
        return bool(st.get("vosk") and st.get("mic") and voice.model_installed(get_language()))

    # ── mascotas ──────────────────────────────────────────────────────────
    def pets(self):
        """[(anim_id, nombre)] de las mascotas en el escritorio."""
        out = []
        for aid, w in self.app.manager.mascots.items():
            out.append((aid, (w.anim or {}).get("name") or aid))
        return out

    def pet_cfg(self, aid):
        raw = cfg("talk_pets").get(aid)
        d = dict(raw) if isinstance(raw, dict) else {}
        if not isinstance(d.get("wake"), str):
            d.pop("wake", None)
        d["persona"] = personas.valid(d.get("persona"))
        if not (d.get("wake") or "").strip():
            d["wake"] = self.default_wake(aid)
        return d

    def set_pet_cfg(self, aid, **kw):
        allp = dict(cfg("talk_pets"))
        d = dict(allp.get(aid) or {})
        for k, v in kw.items():
            if k == "persona":
                v = personas.valid(v)
            elif k == "wake":
                v = " ".join(str(v).split())[:24]
            d[k] = v
        allp[aid] = d
        settings.set_val("talk_pets", allp)
        if "wake" in kw and self.listener is not None:
            self.listener.set_names(self.wake_names())

    def default_wake(self, aid):
        """Primera palabra del nombre («Gato Pixel» → «gato»), salvo que otra
        mascota empiece igual: entonces el nombre completo («gato pixel»)."""
        def words(a):
            anim = self.app.library.animations.get(a) or {}
            return (anim.get("name") or a).strip().lower().split() or [a]
        mine = words(aid)
        clash = any(words(o)[0] == mine[0] for o in self.app.library.animations if o != aid)
        return " ".join(mine if clash else mine[:1])[:24]

    def wake_taken(self, aid, name):
        """¿Otra mascota del escritorio ya usa este nombre de llamada?"""
        n = " ".join(str(name).lower().split())
        return any(o != aid and self.pet_cfg(o)["wake"].lower() == n for o, _x in self.pets())

    def wake_names(self):
        return {aid: self.pet_cfg(aid)["wake"] for aid, _n in self.pets()}

    def check_wake_name(self, name, cb):
        """¿Se puede llamar así? cb(lista de formas) en el hilo principal."""
        def work():
            try:
                lst = self._ensure_listener()
                sp = voice.spellings(name, lst.known)
                lst.release()
            except Exception:  # noqa: BLE001
                sp = None
            GLib.idle_add(lambda: (cb(sp), False)[1])
        threading.Thread(target=work, daemon=True).start()

    def _pick_pet(self, aid=None):
        ms = self.app.manager.mascots
        for cand in (aid, cfg("talk_pet"), self._last_pet):
            if cand and cand in ms:
                return cand
        for a, w in ms.items():
            if getattr(w, "mode", "") == "life":
                return a
        return next(iter(ms), None)

    def _win(self, aid):
        return self.app.manager.mascots.get(aid)

    # ── voz ───────────────────────────────────────────────────────────────
    def _ensure_listener(self):
        lang = get_language()
        if self.listener is not None and self.listener.lang == (lang if lang in voice.MODELS else "es"):
            return self.listener
        if self.listener is not None:
            self.listener.shutdown()

        def idle(fn):
            return lambda *a: GLib.idle_add(lambda: (fn(*a), False)[1])
        self.listener = voice.Listener(lang, {
            "on_wake": idle(self._on_wake),
            "on_heard": idle(self._on_heard),
            "on_state": idle(self._on_voice_state),
            "on_error": idle(self._on_voice_error),
        })
        if cfg("talk_whisper") and voice.whisper_available() and voice.whisper_installed():
            self.listener.whisper = voice.Whisper()
        return self.listener

    def _on_voice_state(self, st):
        self.voice_state = st
        if self.mic_button is not None:
            self.mic_button.set_state("listen" if st == "command" else "idle")
        self._notify()

    def _on_voice_error(self, msg):
        self.last_error = msg
        # la mascota que esperaba tu frase deja de escuchar
        for w in self.app.manager.mascots.values():
            cl = getattr(w, "_cloud", None)
            if cl is not None and cl.mode == "listen":
                w.talk_close()
        self._notify()

    def _on_wake(self, aid):
        w = self._win(aid)
        if w is None:
            return
        self._last_pet = aid
        w.talk_listen()
        self.warmup(aid)

    def route_by_name(self, aid, text):
        """Con el botón (o al escribir) la app no sabe a quién le hablas: si
        la frase EMPIEZA con el nombre de una mascota («panda, ¿me quieres?»
        u «oye panda, …») responde esa y el nombre se quita de la frase."""
        from difflib import SequenceMatcher
        toks = (text or "").split()
        if not toks:
            return aid, text
        wk = {voice.phonetic(w) for w in voice.WAKE_WORDS.get(get_language(), [])}
        start = 1 if voice.phonetic(toks[0]) in wk and len(toks) > 1 else 0
        best = (0.0, None, 0)
        for other, name in self.wake_names().items():
            n = len(name.split())
            cand = " ".join(toks[start:start + n]).strip(",.!?¿¡")
            if not cand:
                continue
            r = SequenceMatcher(None, voice.phonetic(name), voice.phonetic(cand)).ratio()
            if r > best[0]:
                best = (r, other, start + n)
        r, other, cut = best
        if other is not None and r >= 0.8:
            rest = " ".join(toks[cut:]).lstrip(",.!?¿¡ ")
            return other, rest
        return aid, text

    def _on_heard(self, aid, text):
        if text:
            new, rest = self.route_by_name(aid, text)
            if new != aid and new in self.app.manager.mascots:
                old = self._win(aid)
                if old is not None:
                    old.talk_close()             # la que escuchaba se calla…
                aid, text = new, rest
                self._last_pet = aid
                self._win(aid).talk_listen()     # …y atiende la nombrada
        w = self._win(aid)
        if w is None:
            return
        if text is None:                 # falsa alarma
            w.talk_close()
            return
        text = text.strip()
        if not text:
            w.talk_say(tr("¿Mmm? No te escuché bien."))
            return
        self.respond(aid, text)

    def warmup(self, aid=None):
        """Mientras el usuario habla: carga el modelo (~3 s en frío) y procesa
        ya las instrucciones de ESA mascota, que Ollama guarda en caché. Al
        llegar la frase solo queda lo nuevo (respuesta ~1 s después)."""
        if self.engine() != "ai" or not self.model_installed():
            return
        aid = self._pick_pet(aid)
        now = time.monotonic()
        if aid is None or (aid == getattr(self, "_warm_pet", None) and now - self._warm_at < 60):
            return
        self._warm_at, self._warm_pet = now, aid
        model = self.model()
        w = self._win(aid)
        pc = self.pet_cfg(aid)
        name = ((w.anim or {}).get("name") if w is not None else None) or aid
        lang = get_language()
        msgs = personas.build_messages(name, pc["persona"], lang, "…",
                                       phrases.examples(lang, pc["persona"]),
                                       list(self._hist.get(aid, ())), bool(cfg("talk_swear")))

        def work():
            if llm.ensure_server():
                try:
                    llm.chat(model, msgs, max_tokens=1)
                except llm.OllamaError:
                    llm.warmup(model)
        threading.Thread(target=work, daemon=True).start()

    # ── botón / escribir ──────────────────────────────────────────────────
    def ask(self, aid=None):
        """Botón del micrófono: escucha una frase (o abre «escribir» si no hay
        voz disponible)."""
        aid = self._pick_pet(aid)
        if aid is None:
            return False
        if not self._voice_ready():
            self.open_type(aid)
            return True
        self._ensure_listener()
        self._last_pet = aid
        w = self._win(aid)
        if w is not None:
            w.talk_listen()
        self.listener.listen_once(aid)
        self.warmup(aid)
        return True

    def open_type(self, aid=None):
        aid = self._pick_pet(aid)
        if aid is None:
            return
        from ..ui.talk_entry import TalkEntryWindow
        if self.type_window is None:
            self.type_window = TalkEntryWindow(self)
            self.type_window.connect("close-request", self._on_type_closed)
        self.type_window.set_pet(aid)
        self.type_window.present()
        self.warmup(aid)

    def _on_type_closed(self, *_a):
        self.type_window = None
        return False

    # ── responder ─────────────────────────────────────────────────────────
    def respond(self, aid, text):
        w = self._win(aid)
        if w is None:
            return
        self._last_pet = aid
        gen = self._gen.get(aid, 0) + 1
        self._gen[aid] = gen
        pc = self.pet_cfg(aid)
        name = (w.anim or {}).get("name") or aid
        lang = get_language()
        if self.engine() == "ai":
            w.talk_think()
            self._ai_reply(aid, gen, name, pc["persona"], lang, text)
        else:
            w.talk_think()
            reply, _topic = phrases.reply(text, lang, pc["persona"], name)
            GLib.timeout_add(random.randint(350, 650), self._deliver, aid, gen, text, reply)

    def _deliver(self, aid, gen, question, reply):
        if self._gen.get(aid) != gen:
            return False
        w = self._win(aid)
        if w is not None:
            w.talk_say(reply, final=True)
        h = self._hist.setdefault(aid, deque(maxlen=HISTORY))
        h.append((question, reply))
        return False

    def _ai_reply(self, aid, gen, name, persona, lang, text):
        model = self.model()
        hist = list(self._hist.get(aid, ()))
        examples = phrases.examples(lang, persona, n=2)
        swear = bool(cfg("talk_swear"))
        # temas de crisis: el modelo pequeño no siempre «sale del papel»;
        # la respuesta escrita de apoyo es segura y se usa directamente
        if phrases.detect(text, lang) == "crisis":
            reply, _t = phrases.reply(text, lang, persona, name)
            GLib.timeout_add(300, self._deliver, aid, gen, text, reply)
            return
        hint = personas.clock_hint() if phrases.detect(text, lang) in ("time", "date") else ""
        msgs = personas.build_messages(name, persona, lang, text, examples, hist, swear, hint)
        last = [0.0]

        def cancelled():
            return self._gen.get(aid) != gen

        def on_token(partial):
            now = time.monotonic()
            if now - last[0] >= 0.07 and partial:
                last[0] = now
                GLib.idle_add(self._partial, aid, gen, partial)

        def work():
            reply, tps, err = "", 0.0, ""
            try:
                if not llm.ensure_server():
                    raise llm.OllamaError("Ollama no responde")
                if not llm.has_model(model):
                    raise llm.OllamaError("falta el modelo")
                t0 = time.monotonic()
                reply, tps = llm.chat(model, msgs, on_token=on_token, cancel=cancelled)
                if not tps:
                    dt = time.monotonic() - t0
                    tps = (len(reply.split()) * 1.3 / dt) if dt else 0.0
            except Exception as e:  # noqa: BLE001
                err = str(e)[:160]
            GLib.idle_add(self._ai_done, aid, gen, name, persona, lang, text, reply, tps, err)

        threading.Thread(target=work, daemon=True).start()

    def _partial(self, aid, gen, partial):
        if self._gen.get(aid) == gen:
            w = self._win(aid)
            if w is not None:
                w.talk_say(partial, final=False)
        return False

    def _ai_done(self, aid, gen, name, persona, lang, text, reply, tps, err):
        if err or not reply:
            self.last_error = err or "respuesta vacía"
            reply, _t = phrases.reply(text, lang, persona, name)
        else:
            self.last_error = ""
            self.last_tps = tps
            if cfg("talk_engine") == "auto" and 0 < tps < SLOW_TPS:
                self.too_slow = True
        self._deliver(aid, gen, text, reply)
        self._notify()
        return False

    # ── botón flotante ────────────────────────────────────────────────────
    def _set_mic_button(self, on):
        if on and self.mic_button is None:
            try:
                from ..overlay.mic_button import MicButton
                self.mic_button = MicButton(self)
                self.mic_button.present()
            except Exception as e:  # noqa: BLE001
                self.last_error = f"botón: {e}"
                self.mic_button = None
        elif not on and self.mic_button is not None:
            self.mic_button.destroy()
            self.mic_button = None

    # ── descargas (desde la ventana) ──────────────────────────────────────
    def download_voice(self, on_progress, on_done):
        lang = get_language()

        def work():
            err = ""
            try:
                voice.download_model(lang, lambda f: GLib.idle_add(on_progress, f))
            except Exception as e:  # noqa: BLE001
                err = str(e)[:200]
            GLib.idle_add(lambda: (on_done(err), self.refresh_status(self.apply), False)[2])
        threading.Thread(target=work, daemon=True).start()

    def download_whisper(self, on_done):
        def work():
            err = ""
            try:
                voice.download_whisper()
            except Exception as e:  # noqa: BLE001
                err = str(e)[:200]
            def fin():
                on_done(err)
                if self.listener is not None and not err:
                    self.listener.whisper = voice.Whisper()
                self.refresh_status()
                return False
            GLib.idle_add(fin)
        threading.Thread(target=work, daemon=True).start()

    def download_model(self, name, on_progress, on_done):
        def work():
            err = ""
            try:
                if not llm.ensure_server():
                    raise llm.OllamaError(tr("Ollama no está instalado o no arranca."))
                llm.pull(name, lambda f, s: GLib.idle_add(on_progress, f, s))
            except Exception as e:  # noqa: BLE001
                err = str(e)[:200]
            GLib.idle_add(lambda: (on_done(err), self.refresh_status(), False)[2])
        threading.Thread(target=work, daemon=True).start()

    def benchmark(self, on_done):
        model = self.model()

        def work():
            tps, err = 0.0, ""
            try:
                if not llm.ensure_server():
                    raise llm.OllamaError(tr("Ollama no está instalado o no arranca."))
                tps = llm.benchmark(model)
            except Exception as e:  # noqa: BLE001
                err = str(e)[:200]
            GLib.idle_add(lambda: (self._bench_done(tps, err, on_done), False)[1])
        threading.Thread(target=work, daemon=True).start()

    def _bench_done(self, tps, err, on_done):
        if not err:
            self.last_tps = tps
            self.too_slow = 0 < tps < SLOW_TPS
        on_done(tps, err)
        self._notify()
