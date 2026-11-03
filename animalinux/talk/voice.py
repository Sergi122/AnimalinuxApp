"""
Voz: micrófono + Vosk (reconocimiento local, sin internet).

Dos modos en un único hilo:

  "wake"     escucha SOLO «ey/oye/hey <nombre>» con una gramática cerrada:
             ~2-3 % de un núcleo. Además, si hay silencio no se le pasa audio
             a Vosk (puerta de energía), así que en una habitación callada el
             gasto es casi cero.
  "command"  tras oír el nombre (o pulsar el micrófono) transcribe la frase
             completa hasta que te callas (o 8 s) y vuelve a «wake» (o apaga
             el micrófono si el «ey» está desactivado).

El audio nunca se guarda: se procesa por trozos de 0,1 s en memoria.

Nombres que el modelo no conoce («lacri») se escriben con palabras que sí
conoce («la cri»): ver spellings(). Para evitar falsas alarmas («la crisis»)
el nombre SOLO cuenta si va detrás de una palabra de llamada («oye lacri»),
como «ey Google».
"""
import array
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.request
import zipfile
from collections import deque
from pathlib import Path

from .. import paths

RATE = 16000
CHUNK = 3200                  # bytes = 1600 muestras s16 = 0,1 s
COMMAND_MAX_S = 8.0
COMMAND_WAIT_S = 6.0          # si no empiezas a hablar en este tiempo, se cancela
MIN_CONF = 0.55               # confianza media mínima del nombre (tras «oye»)
BARE_CONF = 0.8               # nombre solo, al empezar la frase: más exigente
GATE_RMS = 260                # mínimo absoluto de la puerta de silencio
GATE_K = 1.8                  # voz = nivel > ruido de fondo × GATE_K
GATE_HANG = 6                 # trozos que se siguen pasando tras el último ruido
PREROLL = 4                   # trozos previos al ruido que también se pasan

BASE_URL = "https://alphacephei.com/vosk/models/"
# idioma de la app → modelo pequeño de Vosk (nombre, sha256 del .zip, MB)
MODELS = {
    "es": ("vosk-model-small-es-0.42",
           "09b239888f633ef2f0b4e09736e3d9936acfd810bc65d53fad45261762c6511f", 40),
    "en": ("vosk-model-small-en-us-0.15",
           "30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498", 41),
    "pt": ("vosk-model-small-pt-0.3",
           "6e1ce909032e1afa7a88e68a3d628ecafff302bdf195befab308826c395e93b7", 32),
    "fr": ("vosk-model-small-fr-0.22",
           "cabf6180e177eb9b3a9a9d43a437bd5e549f3a7d09525e5d69a3fed787be12ad", 42),
    "de": ("vosk-model-small-de-0.15",
           "b7e53c90b1f0a38456f4cd62b366ecd58803cd97cd42b06438e2c131713d5e43", 47),
    "ja": ("vosk-model-small-ja-0.22",
           "efa092d280153a77615e9e0c7d7283e93e600de3d19d3bec686c57ef19d52eac", 50),
    "zh": ("vosk-model-small-cn-0.22",
           "3af8b0e7e0f835ae9d414ce5df580237a3cfb08d586c9fbbb0f7ff29ad5b14ba", 44),
}
WAKE_WORDS = {
    "es": ["oye", "ey", "hey", "hola"],
    "en": ["hey", "hi", "okay", "hello"],
    "pt": ["oi", "ei", "olá", "hey"],
    "fr": ["hé", "dis", "salut", "hey"],
    "de": ["hey", "hallo", "he"],
    "ja": ["ねえ", "おい", "ヘイ"],
    "zh": ["嘿", "喂", "你好"],
}


class VoiceError(Exception):
    pass


# ── disponibilidad ──────────────────────────────────────────────────────────
def _has_module(name):
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def vosk_available():
    return _has_module("vosk")


def recorder_cmd():
    """Programa para leer el micrófono como PCM s16le 16 kHz mono por stdout."""
    if sys.platform == "win32":
        return None
    if shutil.which("pw-record") and _pw_has_raw():
        # --raw es OBLIGATORIO: sin él pw-record escribe un .au (cabecera
        # «.snd» y muestras big-endian) y Vosk solo oiría ruido
        return ["pw-record", "--raw", "--rate", str(RATE), "--channels", "1",
                "--format", "s16", "--media-role", "Communication", "-"]
    if shutil.which("parecord"):
        return ["parecord", "--raw", f"--rate={RATE}", "--channels=1", "--format=s16le",
                "--latency-msec=100"]
    if shutil.which("arecord"):
        return ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(RATE), "-c", "1"]
    return None


_PW_RAW = None


def _pw_has_raw():
    """¿Esta versión de pw-record tiene --raw? (las viejas no)."""
    global _PW_RAW
    if _PW_RAW is None:
        try:
            out = subprocess.run(["pw-record", "--help"], capture_output=True,
                                 text=True, timeout=3)
            _PW_RAW = "--raw" in (out.stdout + out.stderr)
        except (OSError, subprocess.SubprocessError):
            _PW_RAW = False
    return _PW_RAW


def mic_available():
    return bool(recorder_cmd()) or _has_module("sounddevice")


# ── modelos de voz ──────────────────────────────────────────────────────────
def models_root():
    return paths.DATA_DIR / "voice"


def model_path(lang):
    name = MODELS.get(lang, MODELS["es"])[0]
    return models_root() / name


def model_installed(lang):
    p = model_path(lang)
    return (p / "am" / "final.mdl").is_file() and (p / "conf" / "model.conf").is_file()


MAX_UNZIPPED = 400 * 1024 * 1024     # los modelos pequeños ocupan ~50-90 MB


def _safe_extract(zf, dest):
    """Extrae sin permitir rutas absolutas, «..», enlaces simbólicos ni
    «bombas zip» (un zip pequeño que se descomprime en gigas)."""
    dest = dest.resolve()
    if sum(i.file_size for i in zf.infolist()) > MAX_UNZIPPED:
        raise VoiceError("el zip descomprimido sería demasiado grande")
    from ..pack import _unsafe_member      # misma regla que los packs (POSIX + Windows)
    for info in zf.infolist():
        name = info.filename
        if _unsafe_member(name) or ":" in name:
            raise VoiceError(f"ruta sospechosa en el zip: {name!r}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise VoiceError(f"enlace simbólico en el zip: {name!r}")
        target = (dest / name).resolve()
        if dest not in target.parents and target != dest:
            raise VoiceError(f"ruta fuera del destino: {name!r}")
    zf.extractall(dest)


def download_model(lang, on_progress=None, cancel=None):
    """Baja el modelo pequeño del idioma, comprueba su SHA-256 y lo instala."""
    if lang not in MODELS:
        lang = "es"
    name, sha, _mb = MODELS[lang]
    root = models_root()
    root.mkdir(parents=True, exist_ok=True)
    if model_installed(lang):
        return model_path(lang)
    url = BASE_URL + name + ".zip"
    h = hashlib.sha256()
    fd, tmp = tempfile.mkstemp(prefix=".dl-", suffix=".zip", dir=root)
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(url, timeout=30) as r:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancel is not None and cancel():
                    raise VoiceError("cancelado")
                buf = r.read(1 << 16)
                if not buf:
                    break
                out.write(buf)
                h.update(buf)
                done += len(buf)
                if done > 200 * 1024 * 1024:
                    raise VoiceError("descarga demasiado grande")
                if on_progress is not None:
                    on_progress(done / total if total else None)
        if h.hexdigest() != sha:
            raise VoiceError("la huella SHA-256 no coincide: descarga dañada o alterada")
        stage = Path(tempfile.mkdtemp(prefix=".x-", dir=root))
        try:
            with zipfile.ZipFile(tmp) as zf:
                _safe_extract(zf, stage)
            src = stage / name
            if not (src / "am" / "final.mdl").is_file():
                raise VoiceError("el zip no tiene el modelo esperado")
            dst = model_path(lang)
            if dst.exists():
                shutil.rmtree(dst)
            src.rename(dst)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return model_path(lang)


# ── nombres → frases que el modelo entiende ────────────────────────────────
def norm_word(s):
    t = unicodedata.normalize("NFKD", (s or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return "".join(c for c in t if c.isalnum() or c == " ").strip()


def _respellings(name):
    """Variantes de escritura que suenan igual (para buscarlas en el modelo)."""
    out = [name]
    for a, b in (("k", "c"), ("c", "k"), ("y", "i"), ("i", "y"), ("v", "b"), ("z", "s"),
                 ("ll", "y"), ("sh", "ch"), ("qu", "k"), ("ph", "f"), ("w", "u"), ("h", "")):
        if a in name:
            v = name.replace(a, b)
            if v and v not in out:
                out.append(v)
    return out


def segment(word, known):
    """Parte `word` en el menor número de palabras conocidas (o None)."""
    n = len(word)
    best = [None] * (n + 1)
    best[0] = []
    for i in range(1, n + 1):
        for j in range(max(0, i - 14), i):
            if best[j] is not None and known(word[j:i]):
                c = best[j] + [word[j:i]]
                if best[i] is None or len(c) < len(best[i]):
                    best[i] = c
    return best[n]


def spellings(name, known, limit=3):
    """Formas de escribir el nombre con el vocabulario del modelo: lista de
    frases («la cri»). Vacía si no hay forma (cambiar el nombre)."""
    out = []
    raw = (name or "").strip().lower()
    if not raw:
        return out
    if " " not in raw and known(raw):
        return [raw]
    words = norm_word(raw).split()
    if not words:
        return out
    if all(known(w) for w in words):
        out.append(" ".join(words))
    for joined in _respellings("".join(words)):
        if known(joined):
            v = joined
        else:
            seg = segment(joined, known)
            v = " ".join(seg) if seg else None
        if v and v not in out:
            out.append(v)
    # preferir pocas palabras y sin letras sueltas («la cri» antes que «l ak ri»)
    out.sort(key=lambda v: (sum(len(w) == 1 for w in v.split()), len(v.split())))
    return out[:limit]


def strip_wake(text, wake_words, name_phrases):
    """Quita «oye la cri» del principio de lo transcrito."""
    toks = text.split()
    drop = {norm_word(w) for w in wake_words}
    for ph in name_phrases:
        drop.update(ph.split())
    i = 0
    while i < len(toks) and i < 6 and norm_word(toks[i]) in drop:
        i += 1
    return " ".join(toks[i:])


def match_wake(words, wake_words, table, with_end=False, bare_ok=()):
    """words = [(palabra, conf)] de Vosk. table = {pet_id: [frase, ...]}.
    Devuelve el pet_id si se oyó «<llamada> <nombre>» con confianza
    (con with_end: (pet_id, índice de la última palabra del nombre))."""
    toks = [w for w, _c in words]
    confs = [c for _w, c in words]
    wk = {norm_word(w) for w in wake_words}
    for pid, phrases in table.items():
        for ph in phrases:
            pt = ph.split()
            n = len(pt)
            for i in range(0, len(toks) - n + 1):
                if toks[i:i + n] != pt:
                    continue
                c = sum(confs[i:i + n]) / n
                called = i > 0 and norm_word(toks[i - 1]) in wk
                # la gente también llama solo con el nombre («Azul, ¿me
                # quieres?»): vale si ABRE la frase y se oyó claro
                # (solo nombres que son palabras reales: «noce» sin «oye»
                # se confunde con «no sé…»)
                bare = i == 0 and c >= BARE_CONF and ph in bare_ok
                if (called and c >= MIN_CONF) or bare:
                    return (pid, i + n - 1) if with_end else pid
    return (None, -1) if with_end else None


def phonetic(s):
    """Forma «como suena» para comparar nombres: kaoruko ≈ caucho, noce ≈ no sé."""
    t = norm_word(s).replace(" ", "")
    for a, b in (("qu", "k"), ("ce", "se"), ("ci", "si"), ("c", "k"), ("z", "s"),
                 ("v", "b"), ("ll", "y"), ("w", "u"), ("ph", "f"), ("h", "")):
        t = t.replace(a, b)
    return t


VERIFY_SIM = 0.6        # parecido mínimo entre el nombre y lo transcrito
VERIFY_OTHER_CONF = 0.8  # palabra «normal» segura delante del nombre → no era una llamada


def words_in_span(free, start, end, slack=0.1):
    """free = [(palabra, conf, ini, fin)] → (palabras que caen en [start, end],
    palabra justo anterior o None). Sirve para comparar lo que la gramática
    creyó oír como nombre con lo que la transcripción libre oyó EN ESE MISMO
    momento («oye, pásame…»: el «panda» de la gramática era «pásame»)."""
    inside, before = [], None
    for w, c, a, b in free:
        mid = (a + b) / 2
        if start - slack <= mid <= end + slack:
            inside.append((w, c))
        elif b <= start + slack:
            before = (w, c)
    return inside, before


def verify_wake(free_words, name_phrase, wake_words, strict=True):
    """Segunda opinión (transcripción libre de la frase).

    free_words = [(palabra, conf)]. True si de verdad suena a «<llamada> <nombre>»:
      - las últimas 1-3 palabras se parecen al nombre (fonéticamente), y
      - lo de delante del nombre no es una palabra normal dicha con seguridad
        («el panda come…» no es «ey panda»)."""
    from difflib import SequenceMatcher
    if not free_words:
        return True                          # sin segunda opinión: vale la primera
    if not strict:
        # nombre que el modelo NO conoce: la transcripción libre lo escribe
        # como otras palabras («bolita» → «billeter»), así que el parecido no
        # sirve; solo se mira que delante no haya una palabra normal segura
        w, c = free_words[0]
        wk = {phonetic(x) for x in wake_words}
        return phonetic(w) in wk or c < VERIFY_OTHER_CONF
    target = phonetic(name_phrase)
    best, best_k = 0.0, 0
    for k in (1, 2, 3):
        if k > len(free_words):
            break
        cand = phonetic(" ".join(w for w, _c in free_words[-k:]))
        r = SequenceMatcher(None, target, cand).ratio()
        if r > best:
            best, best_k = r, k
    if best < VERIFY_SIM:
        # solo veta si la transcripción libre está SEGURA de otra palabra; con
        # voz real a menudo duda («azul» → «sí» 0,34) y ahí gana la gramática
        doubt = [c for _w, c in free_words[-best_k or len(free_words):]]
        if doubt and sum(doubt) / len(doubt) < VERIFY_OTHER_CONF - 0.2:
            return True
        return False
    before = free_words[:-best_k]
    if before:
        w, c = before[-1]
        wk = {phonetic(x) for x in wake_words}
        if phonetic(w) not in wk and c >= VERIFY_OTHER_CONF:
            return False
    return True


def norm_text(t):
    """Whisper devuelve mayúsculas y puntuación: se deja como en Vosk."""
    import re
    return " ".join(re.sub(r"[^\w\s']", " ", (t or "").lower()).split())


# ── Whisper (opcional): transcripción precisa de la frase ───────────────────
WHISPER_MODEL = "base"          # ~145 MB; «small» (~460 MB) entiende algo más y tarda ×3
# frase de ejemplo que orienta el estilo: en español, tuteo latino («estás»,
# no «estáis»), que es como se le habla a una mascota
WHISPER_HINT = {"es": "Hola, ¿cómo estás? ¿Qué estás haciendo? Tengo hambre.",
                "pt": "Oi, tudo bem? O que você está fazendo?"}


def whisper_available():
    return _has_module("faster_whisper")


def whisper_dir():
    return models_root() / f"whisper-{WHISPER_MODEL}"


def whisper_installed():
    d = whisper_dir()
    return (d / "model.bin").is_file() and (d / "config.json").is_file()


def download_whisper(on_progress=None):
    """Baja el modelo de Whisper (Hugging Face, HTTPS) a la carpeta de voz."""
    from faster_whisper.utils import download_model
    d = whisper_dir()
    d.mkdir(parents=True, exist_ok=True)
    if on_progress is not None:
        on_progress(None)
    download_model(WHISPER_MODEL, output_dir=str(d))
    if not whisper_installed():
        raise VoiceError("el modelo de Whisper no se descargó completo")
    return d


class Whisper:
    """Carga perezosa: solo ocupa RAM (~200 MB) la primera vez que transcribe."""

    def __init__(self):
        self._m = None

    def transcribe(self, pcm, lang):
        try:
            import numpy as np
            if self._m is None:
                from faster_whisper import WhisperModel
                self._m = WhisperModel(str(whisper_dir()), device="cpu", compute_type="int8",
                                       cpu_threads=max(1, min(4, (os.cpu_count() or 2) // 2)))
            x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
            segs, _info = self._m.transcribe(x, language={"zh": "zh"}.get(lang, lang),
                                             beam_size=1, without_timestamps=True,
                                             condition_on_previous_text=False,
                                             initial_prompt=WHISPER_HINT.get(lang))
            return " ".join(s.text for s in segs).strip()
        except Exception:  # noqa: BLE001
            return ""

    def release(self):
        self._m = None


# ── micrófono ───────────────────────────────────────────────────────────────
class _ProcMic:
    def __init__(self, cmd):
        self.p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, bufsize=0)

    def read(self):
        buf = b""
        while len(buf) < CHUNK:
            part = self.p.stdout.read(CHUNK - len(buf))
            if not part:
                return None
            buf += part
        return buf

    def close(self):
        if self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(2)
            except subprocess.TimeoutExpired:
                self.p.kill()
        try:
            self.p.stdout.close()
        except OSError:
            pass


class _SdMic:
    def __init__(self):
        import sounddevice as sd
        self.s = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                                   blocksize=CHUNK // 2)
        self.s.start()

    def read(self):
        data, _over = self.s.read(CHUNK // 2)
        return bytes(data)

    def close(self):
        try:
            self.s.stop()
            self.s.close()
        except Exception:  # noqa: BLE001
            pass


def open_mic():
    cmd = recorder_cmd()
    if cmd:
        return _ProcMic(cmd)
    try:
        return _SdMic()
    except Exception as e:  # noqa: BLE001
        raise VoiceError("no hay micrófono") from e


class NoiseGate:
    """Puerta de silencio que aprende el ruido de fondo (ventilador, calle…):
    deja pasar solo lo que sobresale claramente. El suelo de ruido baja rápido
    y sube despacio, así una frase larga no lo «aprende» como ruido."""

    def __init__(self):
        self.floor = None

    def threshold(self):
        return max(GATE_RMS, (self.floor or 0) * GATE_K)

    def loud(self, level):
        if self.floor is None:
            self.floor = level
        elif level < self.floor:
            self.floor += (level - self.floor) * 0.3        # baja rápido
        elif level < self.floor * GATE_K:
            self.floor += (level - self.floor) * 0.02       # sube despacio
        return level >= self.threshold()


def rms(chunk):
    a = array.array("h")
    a.frombytes(chunk[: len(chunk) - (len(chunk) % 2)])
    if sys.byteorder == "big":
        a.byteswap()
    if not a:
        return 0.0
    step = 4                                  # submuestreo: basta para la puerta
    s = 0
    n = 0
    for i in range(0, len(a), step):
        v = a[i]
        s += v * v
        n += 1
    return math.sqrt(s / n)


def _trim_heap():
    """Devuelve al sistema la memoria que soltó el modelo (glibc se la queda
    si no se le pide). No hace nada fuera de Linux/glibc."""
    import gc
    gc.collect()
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except (OSError, AttributeError):
            pass


# ── el que escucha ──────────────────────────────────────────────────────────
class Listener:
    """Hilo de escucha. Callbacks (desde el HILO de audio; brain.py los pasa a
    GLib): on_wake(pet_id), on_heard(pet_id, texto), on_partial(pet_id, texto),
    on_state(estado: "off"|"wake"|"command"), on_error(msg)."""

    def __init__(self, lang, callbacks):
        self.lang = lang if lang in MODELS else "es"
        self.cb = callbacks
        self._model = None
        self._table = {}
        self._vocab_names = set()
        self._wake_words = WAKE_WORDS.get(self.lang, WAKE_WORDS["es"])
        self._lock = threading.Lock()
        self._want_wake = False
        self._command_for = None       # pet_id pedido por el botón
        self._stop = threading.Event()
        self._thread = None
        self.state = "off"
        self.cpu_s = 0.0               # CPU que llevamos (para medir)
        self.whisper = None            # Whisper (opcional) para transcribir la frase

    # -- modelo / nombres
    def _load(self):
        if self._model is None:
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            if not model_installed(self.lang):
                raise VoiceError("falta el modelo de voz")
            self._model = Model(str(model_path(self.lang)))
        return self._model

    def known(self, w):
        m = self._load()
        try:
            return m.vosk_model_find_word(w) >= 0
        except AttributeError:
            return m.find_word(w) >= 0

    def set_names(self, names):
        """names = {pet_id: nombre_de_llamada}. Devuelve {pet_id: [frases]}."""
        table, vocab = {}, set()
        for pid, name in names.items():
            sp = spellings(name, self.known)
            if sp:
                table[pid] = sp
                if " ".join(norm_word(name).split()) == sp[0]:
                    vocab.add(sp[0])           # se escribe igual: el modelo lo conoce
        with self._lock:
            self._table = table
            self._vocab_names = vocab
        return table

    # -- control
    def start_wake(self):
        self._want_wake = True
        self._ensure_thread()

    def stop_wake(self):
        self._want_wake = False

    def listen_once(self, pet_id):
        self._command_for = pet_id
        self._ensure_thread()

    def release(self):
        """Suelta el modelo de voz si no hay nada escuchando (libera RAM)."""
        t = self._thread
        if (t is None or not t.is_alive()) and not self._want_wake \
                and self._model is not None:
            self._model = None
            _trim_heap()

    def shutdown(self):
        self._want_wake = False
        self._command_for = None
        self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(3)
        self._thread = None
        self._model = None

    def _ensure_thread(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="animalinux-voice",
                                            daemon=True)
            self._thread.start()

    def _set_state(self, st):
        if st != self.state:
            self.state = st
            self._emit("on_state", st)

    def _emit(self, name, *a):
        f = self.cb.get(name)
        if f is not None:
            try:
                f(*a)
            except Exception:  # noqa: BLE001
                pass

    # -- bucle
    def _run(self):
        try:
            from vosk import KaldiRecognizer
            model = self._load()
            mic = open_mic()
        except Exception as e:  # noqa: BLE001
            self._command_for = None       # ese pedido ya no se puede cumplir
            self._want_wake = False        # sin modelo o sin micrófono: no reintentar en bucle
            self._emit("on_error", str(e))
            self._set_state("off")
            self._thread = None
            return
        c0 = time.process_time()
        try:
            wake_rec = None
            table = {}
            pre = deque(maxlen=PREROLL)
            utter = []                 # audio de la frase en curso (≤ 10 s)
            early = None               # pet_id ya avisado por un parcial
            hang = 0
            gate = NoiseGate()
            trim = 0                   # trozos de la frase que ya no están en `utter`
            while not self._stop.is_set():
                if self._command_for is not None:
                    pid, self._command_for = self._command_for, None
                    self._command(model, mic, pid, list(pre))
                    wake_rec, utter, early, hang = None, [], None, 0
                    pre.clear()
                    continue
                if not self._want_wake:
                    break
                self._set_state("wake")
                if wake_rec is None:
                    with self._lock:
                        table = dict(self._table)
                    wake_rec = self._wake_recognizer(KaldiRecognizer, model, table)
                chunk = mic.read()
                if chunk is None:
                    raise VoiceError("se cortó el micrófono")
                loud = gate.loud(rms(chunk))
                if not loud and hang <= 0:
                    pre.append(chunk)
                    continue
                if loud:
                    hang = GATE_HANG
                else:
                    hang -= 1
                while pre:
                    c = pre.popleft()
                    utter.append(c)
                    wake_rec.AcceptWaveform(c)
                utter.append(chunk)
                if len(utter) > 100:
                    trim += len(utter) - 100
                    del utter[:len(utter) - 100]
                done = wake_rec.AcceptWaveform(chunk)
                if not done and hang <= 0:
                    done = True               # la puerta se cerró: cerrar la frase
                    res = json.loads(wake_rec.FinalResult())
                elif done:
                    res = json.loads(wake_rec.Result())
                else:
                    # sin aviso temprano por resultados parciales: la mascota
                    # solo reacciona cuando la llamada está VERIFICADA (si no,
                    # «el panda come bambú» le hacía levantar las orejas)
                    res = None
                if not done:
                    continue
                items = res.get("result", [])
                words = [(x.get("word", ""), float(x.get("conf", 0))) for x in items]
                pid, end = match_wake(words, self._wake_words, table, with_end=True,
                                      bare_ok=self._vocab_names) if words else (None, -1)
                audio, utter = utter, []
                # cada frase usa un reconocedor nuevo: sus tiempos empiezan en
                # el primer trozo de `utter` (más los recortados)
                wake_rec, cut, trim = None, 0, trim
                if pid is not None:
                    cut = max(0, int(float(items[end].get("end", 0)) * RATE * 2 / CHUNK) - trim)
                    # segunda opinión (solo cuando la gramática cree oír un nombre):
                    # la frase entera, comparando lo oído en el mismo intervalo
                    phrase = table.get(pid, [""])[0]
                    n = len(phrase.split())
                    t_off = trim * CHUNK / (RATE * 2)
                    span = (float(items[end - n + 1].get("start", 0)) - t_off,
                            float(items[end].get("end", 0)) - t_off)
                    if not self._verify(KaldiRecognizer, model, audio, phrase, span):
                        self._emit("on_debug", "verificación rechazó", phrase, words,
                                   "| libre:", getattr(self, "_last_free", None))
                        pid = None
                elif words:
                    self._emit("on_debug", "oído (sin llamada)", words)
                trim = 0
                if pid is None:
                    if early is not None:
                        self._emit("on_heard", early, None)    # falsa alarma: bajar orejas
                    early = None
                    continue
                if early != pid:
                    self._emit("on_wake", pid)
                early = None
                # lo dicho tras el nombre (si lo hubo) entra como inicio de la
                # orden y se sigue escuchando hasta que te callas
                self._command(model, mic, pid, audio[cut:], skip=table.get(pid, []))
                hang = 0
        except Exception as e:  # noqa: BLE001
            self._emit("on_error", str(e))
        finally:
            mic.close()
            self.cpu_s += time.process_time() - c0
            # soltar TODAS las referencias al modelo (los reconocedores lo
            # sujetan) antes de liberarlo
            model = wake_rec = None  # noqa: F841
            if not self._want_wake and self._model is not None:
                self._model = None         # ~130 MB de RAM: fuera si no se escucha
                if self.whisper is not None:
                    self.whisper.release()
                _trim_heap()
            self._set_state("off")
            self._thread = None
            # ¿llegó un pedido mientras salíamos? (botón pulsado justo ahora)
            if not self._stop.is_set() and (self._command_for is not None or self._want_wake):
                self._ensure_thread()

    def _verify(self, KaldiRecognizer, model, chunks, phrase, span):
        rec = KaldiRecognizer(model, RATE)
        rec.SetWords(True)
        for c in chunks:
            rec.AcceptWaveform(c)
        res = json.loads(rec.FinalResult()).get("result", [])
        free = [(x.get("word", ""), float(x.get("conf", 0)),
                 float(x.get("start", 0)), float(x.get("end", 0))) for x in res]
        inside, before = words_in_span(free, *span)
        self._last_free = (before, inside)          # para el diagnóstico
        strict = phrase in self._vocab_names        # nombre que el modelo conoce tal cual
        if not inside:
            return not free           # no oyó nada en ese momento: mejor no activarse
        if not strict:
            return verify_wake([before] if before else [("", 0.0)], phrase,
                               self._wake_words, strict=False)
        return verify_wake(([before] if before else []) + inside, phrase, self._wake_words)

    def _wake_recognizer(self, KaldiRecognizer, model, table):
        phr = []
        for ps in table.values():
            for p in ps:
                phr += [f"{w} {p}" for w in self._wake_words]
        phr += self._wake_words + ["[unk]"]
        rec = KaldiRecognizer(model, RATE, json.dumps(phr, ensure_ascii=False))
        rec.SetWords(True)
        return rec

    def _command(self, model, mic, pid, preroll, skip=()):
        from vosk import KaldiRecognizer
        self._set_state("command")
        rec = KaldiRecognizer(model, RATE)
        audio = list(preroll)                 # para Whisper (si está)
        for c in preroll:
            rec.AcceptWaveform(c)
        start = time.monotonic()
        heard_any = False
        text = ""
        last_partial = ""
        while not self._stop.is_set():
            chunk = mic.read()
            if chunk is None:
                break
            audio.append(chunk)
            if rec.AcceptWaveform(chunk):
                text = json.loads(rec.Result()).get("text", "")
                if text.strip():
                    break
            else:
                p = json.loads(rec.PartialResult()).get("partial", "")
                if p and p != last_partial:
                    heard_any = True
                    last_partial = p
                    self._emit("on_partial", pid, strip_wake(p, self._wake_words, skip))
            el = time.monotonic() - start
            if el > COMMAND_MAX_S or (not heard_any and el > COMMAND_WAIT_S):
                break
        if not text.strip():
            text = json.loads(rec.FinalResult()).get("text", "")
        # Vosk marca el final de la frase; si hay Whisper, él la transcribe
        # (mucho más preciso con voz real) y Vosk queda de respaldo
        if text.strip() and self.whisper is not None:
            better = self.whisper.transcribe(b"".join(audio), self.lang)
            if better:
                self._emit("on_debug", "whisper", repr(better), "| vosk", repr(text))
                text = better
        text = strip_wake(norm_text(text), self._wake_words, skip).strip()
        self._emit("on_heard", pid, text)
