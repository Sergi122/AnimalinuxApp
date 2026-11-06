"""Hablar con la mascota: frases, voz (sin micrófono), equipo, IA y nube."""
import io
import json
import re
import time
import zipfile

import pytest

from animalinux.talk import hw, llm, personas, phrases, voice

LANGS = ("es", "en", "pt", "fr", "de", "ja", "zh")
PH_OK = {"{time}", "{day}", "{name}"}


# ── frases escritas ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang", LANGS)
def test_phrase_files_complete(lang):
    ref = phrases.load("es")
    d = phrases.load(lang)
    assert d["_lang"] == lang
    assert (phrases.DATA / f"{lang}.json").is_file(), "falta el archivo del idioma"
    assert set(d["topics"]) == set(ref["topics"]), "temas distintos a es"
    assert d["replies"]["_all"]["crisis"], "crisis debe tener respuesta de apoyo"
    for persona in personas.PERSONAS:
        if persona not in d["replies"]:
            assert lang != "es", f"es debe tener todas las personalidades ({persona})"
            assert personas.PERSONAS[persona]["like"] in d["replies"]
            continue
        rep = d["replies"][persona]
        need = (set(ref["topics"]) - {"crisis"}) | {"question", "unknown"}
        missing = need - set(rep)
        assert not missing, f"{lang}/{persona} sin temas: {sorted(missing)[:5]}"
        for topic, lst in rep.items():
            assert len(lst) >= 3, f"{lang}/{persona}/{topic}: menos de 3 frases"
            for s in lst:
                assert s.strip() and len(s) <= 140, (lang, persona, topic, s)
                assert set(re.findall(r"\{[^}]*\}", s)) <= PH_OK, (lang, persona, topic, s)
    for user, topic in d["examples"]:
        assert phrases.detect(user, lang) == topic, (lang, user, topic)


@pytest.mark.parametrize("text,topic", [
    ("ella no me quiere", "love_sad"),
    ("Estoy MUY aburrida", "bored"),
    ("¿qué hora es?", "time"),
    ("me quiero morir", "crisis"),
    ("me quiero morir de risa jaja", "crisis"),       # prioridad: mejor de más
    ("eres un tonto", "insult_pet"),
    ("sigo aquí", "unknown"),                        # «si» exacto no casa «sigo»
    ("sí", "yes"),
    ("¿por qué el cielo es azul?", "question"),
    ("tengo hambre", "hungry"),
])
def test_detect_spanish(text, topic):
    assert phrases.detect(text, "es") == topic


def test_reply_fills_placeholders_and_avoids_repeat():
    now = time.struct_time((2026, 11, 2, 15, 4, 0, 0, 306, 0))
    seen = set()
    for _ in range(6):
        r, topic = phrases.reply("qué hora es", "es", "kind", "Lacri", now=now)
        assert topic == "time" and "15:04" in r and "{" not in r
        seen.add(r)
    assert len(seen) >= 2
    r1, _ = phrases.reply("hola", "es", "rude", "Lacri")
    r2, _ = phrases.reply("hola", "es", "rude", "Lacri")
    assert r1 != r2


def test_crisis_same_support_for_every_persona():
    for p in personas.PERSONAS:
        r, topic = phrases.reply("ya no quiero vivir", "es", p, "X")
        assert topic == "crisis" and r in phrases.load("es")["replies"]["_all"]["crisis"]


def test_examples_have_no_placeholders():
    for lang in LANGS:
        for p in personas.PERSONAS:
            for u, a in phrases.examples(lang, p, n=3):
                assert "{" not in a and u


# ── personalidades / prompt ─────────────────────────────────────────────────
def test_system_prompt_language_and_swear():
    s = personas.system_prompt("Lacri", "rude", "fr", swear=False)
    assert "French" in s and "Never use swear" in s and "Lacri" in s
    assert "suicide" in s
    assert "mild swear" in personas.system_prompt("Lacri", "rude", "es", swear=True)
    assert personas.valid("nope") == personas.DEFAULT


def test_build_messages_truncates_user_text():
    m = personas.build_messages("A", "kind", "es", "x" * 1000, [("a", "b")], [("c", "d")])
    assert [x["role"] for x in m] == ["system", "user", "assistant", "user", "assistant", "user"]
    assert len(m[-1]["content"]) == 300


# ── IA (sin red) ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw,out", [
    ('"Hola, humano."', "Hola, humano."),
    ("Lacri: ¿Qué quieres?", "¿Qué quieres?"),
    ("Primera línea.\nSegunda línea.", "Primera línea."),
    ("«Claro que sí»", "Claro que sí"),
])
def test_clean_reply(raw, out):
    assert llm.clean_reply(raw) == out


def test_clean_reply_cuts_long_text():
    r = llm.clean_reply("Esto es una frase. " * 30)
    assert len(r) <= llm.MAX_REPLY_CHARS + 1


def test_pull_only_allowed_models():
    with pytest.raises(llm.OllamaError):
        llm.pull("evil/model:latest")
    assert llm.warmup("evil/model") is False


def test_client_only_talks_to_localhost(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://203.0.113.9:11434")
    monkeypatch.setenv("http_proxy", "http://203.0.113.10:3128")
    seen = {}

    class FakeOpener:
        def __init__(self, handlers):
            seen["handlers"] = handlers

        def open(self, req, timeout=0):
            seen["url"] = req.full_url
            raise OSError("sin red en la prueba")

    monkeypatch.setattr(llm.urllib.request, "build_opener",
                        lambda *h: FakeOpener(h))
    assert llm.is_running() is False
    assert seen["url"].startswith("http://127.0.0.1:11434/")
    assert seen["handlers"][0].proxies == {}


# ── equipo ──────────────────────────────────────────────────────────────────
GB = hw.GB


@pytest.mark.parametrize("kw,level", [
    (dict(ram=2 * GB, cores=4, avx2=True, vram=0, disk=50 * GB), "none"),
    (dict(ram=16 * GB, cores=8, avx2=False, vram=0, disk=50 * GB), "none"),
    (dict(ram=16 * GB, cores=8, avx2=True, vram=0, disk=0.5 * GB), "none"),
    (dict(ram=6 * GB, cores=4, avx2=True, vram=0, disk=50 * GB), "slow"),
    (dict(ram=16 * GB, cores=2, avx2=True, vram=0, disk=50 * GB), "slow"),
    (dict(ram=16 * GB, cores=8, avx2=True, vram=0, disk=50 * GB), "ok"),
    (dict(ram=16 * GB, cores=8, avx2=None, vram=0, disk=50 * GB), "ok"),
    (dict(ram=16 * GB, cores=8, avx2=True, vram=6 * GB, disk=50 * GB), "fast"),
])
def test_assess_levels(kw, level):
    a = hw.assess(**kw)
    assert a["level"] == level
    assert (a["model"] == "") == (level == "none")
    if level == "slow":
        assert a["model"] == hw.LIGHT_MODEL


def test_assess_real_machine_runs():
    a = hw.assess()
    assert a["level"] in ("none", "slow", "ok", "fast") and a["cores"] >= 1


def test_rate_speed():
    assert [hw.rate_speed(x) for x in (30, 8, 3, 1)] == ["fast", "ok", "slow", "none"]


# ── voz (sin micrófono) ─────────────────────────────────────────────────────
VOCAB = {"la", "cri", "michi", "kao", "ru", "ko", "oye", "ey", "hey", "her", "ta", "a", "l", "ak", "ri"}


def test_spellings_prefers_few_real_words():
    k = VOCAB.__contains__
    assert voice.spellings("Michi", k) == ["michi"]
    assert voice.spellings("lacri", k)[0] == "la cri"
    assert voice.spellings("Kaoruko", k)[0] == "kao ru ko"
    assert voice.spellings("zzzz", k) == []
    assert voice.spellings("", k) == []


def test_match_wake_needs_call_word_and_confidence():
    table = {"p1": ["la cri"], "p2": ["michi"]}
    ww = ["oye", "ey", "hey"]
    assert voice.match_wake([("oye", 1), ("la", .9), ("cri", .9)], ww, table) == "p1"
    assert voice.match_wake([("michi", 1)], ww, table, bare_ok={"michi"}) == "p2"  # nombre real, solo, al inicio
    assert voice.match_wake([("la", 1), ("cri", 1)], ww, table) is None        # inventado: necesita «oye»
    assert voice.match_wake([("la", .6), ("cri", .5)], ww, table) is None      # nombre solo pero dudoso
    assert voice.match_wake([("el", 1), ("la", 1), ("cri", 1)], ww, table) is None   # a mitad de frase
    assert voice.match_wake([("hey", 1), ("michi", .3)], ww, table) is None    # poca confianza
    assert voice.match_wake([("x", 1), ("hey", 1), ("michi", .8), ("y", 1)], ww, table,
                            with_end=True) == ("p2", 2)


def test_strip_wake():
    assert voice.strip_wake("oye la cri estoy triste", ["oye"], ["la cri"]) == "estoy triste"


def test_noise_gate_adapts_to_background():
    g = voice.NoiseGate()
    for _ in range(50):
        assert not g.loud(5000) or g.floor is None   # ruido constante = silencio
    assert not g.loud(5200)
    assert g.loud(15000)                             # la voz sobresale
    for _ in range(30):
        g.loud(15000)                                # una frase larga no lo «aprende»
    assert g.floor < 8000
    for _ in range(10):
        g.loud(100)                                  # se calla el ventilador: baja rápido
    assert g.threshold() < 1000


def test_rms_gate():
    import array
    silent = bytes(voice.CHUNK)
    loud = array.array("h", [3000, -3000] * (voice.CHUNK // 4)).tobytes()
    assert voice.rms(silent) < voice.GATE_RMS < voice.rms(loud)


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data, mode in entries:
            info = zipfile.ZipInfo(name)
            if mode:
                info.external_attr = mode << 16
            z.writestr(info, data)
    buf.seek(0)
    return zipfile.ZipFile(buf)


@pytest.mark.parametrize("name,mode", [
    ("../evil.txt", 0), ("/abs/evil.txt", 0), ("a/../../evil.txt", 0),
    ("C:evil.txt", 0), ("link", 0o120777), ("a\\..\\..\\evil.txt", 0),
])
def test_safe_extract_rejects_bad_entries(tmp_path, name, mode):
    with pytest.raises(voice.VoiceError):
        voice._safe_extract(_zip([(name, b"x", mode)]), tmp_path)
    assert not any(tmp_path.iterdir())


def test_safe_extract_rejects_zip_bomb(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "MAX_UNZIPPED", 1000)
    with pytest.raises(voice.VoiceError):
        voice._safe_extract(_zip([("big.bin", b"0" * 5000, 0)]), tmp_path)
    assert not any(tmp_path.iterdir())


def test_safe_extract_ok(tmp_path):
    voice._safe_extract(_zip([("m/am/final.mdl", b"x", 0)]), tmp_path)
    assert (tmp_path / "m/am/final.mdl").read_bytes() == b"x"


def test_download_rejects_bad_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "models_root", lambda: tmp_path)

    class R(io.BytesIO):
        headers = {"Content-Length": "3"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(voice.urllib.request, "urlopen", lambda *a, **k: R(b"bad"))
    with pytest.raises(voice.VoiceError):
        voice.download_model("es")
    assert not voice.model_installed("es")
    assert [p.name for p in tmp_path.iterdir()] == []        # sin restos


def test_models_have_hashes_for_every_app_language():
    for lang in LANGS:
        name, sha, mb = voice.MODELS[lang]
        assert name.startswith("vosk-model-small-") and len(sha) == 64 and mb < 100
        assert voice.WAKE_WORDS[lang]


# ── nube ────────────────────────────────────────────────────────────────────
def test_cloud_typing_and_close():
    from animalinux.overlay import bubble
    c = bubble.Cloud("think")
    w0, h0, _a = c.size()
    c.set("say", "Hola, ¿qué tal?")
    assert not c.typing_done()
    c.step(10.0)
    assert c.typing_done()
    w1, h1, _a = c.size()
    assert w1 >= w0 * 0.9 and h1 > 0
    c.set("say", "Hola, ¿qué tal? Bien.")          # streaming: no reinicia
    assert c.shown > 0
    c.close()
    c.closing_at -= 1.0
    assert c.finished()


def test_cloud_remembers_when_mode_changed():
    from animalinux.overlay import bubble
    c = bubble.Cloud("listen")
    t0 = c.mode_t
    c.set("listen")
    assert c.mode_t == t0                      # mismo modo: no reinicia el reloj
    time.sleep(0.01)
    c.set("think")
    assert c.mode_t > t0


def test_listener_error_without_model_reports_and_stops(monkeypatch):
    monkeypatch.setattr(voice, "model_installed", lambda lang: False)
    ev = []
    L = voice.Listener("es", {"on_error": lambda m: ev.append(m),
                              "on_state": lambda s: ev.append(s)})
    L.listen_once("p")
    for _ in range(50):
        if L._thread is None:
            break
        time.sleep(0.02)
    # sin modelo (o sin el módulo vosk, como en Windows): avisa y se apaga
    assert any(("modelo" in str(e) or "vosk" in str(e)) for e in ev) and L.state == "off"
    assert L._command_for is None and not L._want_wake


def test_settings_json_roundtrip_for_talk(tmp_path, monkeypatch):
    from animalinux import settings
    monkeypatch.setattr(settings, "_PATH", tmp_path / "s.json")
    settings.set_val("talk_pets", {"a": {"persona": "rude", "wake": "lacri"}})
    assert json.loads((tmp_path / "s.json").read_text())["talk_pets"]["a"]["wake"] == "lacri"


# ── cerebro (sin GTK: app falsa) ────────────────────────────────────────────
class _Win:
    def __init__(self, name):
        self.anim = {"name": name}
        self.mode = "life"
        self.said = []

    def talk_say(self, text, final=True):
        self.said.append((text, final))

    def talk_think(self):
        self.said.append(("…", None))

    def talk_listen(self):
        pass

    def talk_close(self):
        pass


class _App:
    def __init__(self, names):
        class Lib:
            animations = {f"id{i}": {"name": n} for i, n in enumerate(names)}

        class Man:
            mascots = {f"id{i}": _Win(n) for i, n in enumerate(names)}
        self.library, self.manager = Lib(), Man()


@pytest.fixture
def brain(tmp_path, monkeypatch):
    from animalinux import settings
    from animalinux.talk import brain as bm
    monkeypatch.setattr(settings, "_PATH", tmp_path / "s.json")
    b = bm.TalkBrain(_App(["Gato Pixel", "Gato Minecraft", "Lacri", "Panda Rojo"]))
    b.hw = hw.assess(ram=16 * GB, cores=8, avx2=True, vram=0, disk=50 * GB)
    b.status = {"ollama": True, "models": ["gemma3:4b"], "vosk": True, "mic": True}
    return b


def test_default_wake_names_are_unique(brain):
    names = brain.wake_names()
    assert names == {"id0": "gato pixel", "id1": "gato minecraft", "id2": "lacri", "id3": "panda"}
    assert brain.wake_taken("id2", "Panda") and not brain.wake_taken("id3", "panda")
    brain.set_pet_cfg("id2", wake="  Mi   Lacri  ", persona="nope")
    pc = brain.pet_cfg("id2")
    assert pc["wake"] == "Mi Lacri" and pc["persona"] == "kind"


def test_engine_choice(brain):
    from animalinux import settings
    assert brain.engine() == "ai"
    brain.too_slow = True
    assert brain.engine() == "phrases"                 # auto: demasiado lenta → frases
    settings.set_val("talk_engine", "ai")
    assert brain.engine() == "ai"                      # forzada: sigue con IA
    brain.status["ollama"] = False
    assert brain.engine() == "phrases"                 # sin Ollama no hay IA
    settings.set_val("talk_engine", "auto")
    brain.status["ollama"] = True
    brain.too_slow = False
    brain.hw = hw.assess(ram=2 * GB, cores=2, avx2=True, vram=0, disk=50 * GB)
    assert brain.engine() == "phrases"                 # equipo que no cumple
    assert brain.model() == hw.DEFAULT_MODEL           # sin recomendación: el normal


def test_ai_failure_falls_back_to_phrase(brain):
    w = brain.app.manager.mascots["id2"]
    brain._gen["id2"] = 7
    brain._ai_done("id2", 7, "Lacri", "rude", "es", "tengo hambre", "", 0.0, "Ollama no responde")
    text, final = w.said[-1]
    assert final is True and text in phrases.load("es")["replies"]["rude"]["hungry"]
    assert brain.last_error == "Ollama no responde"
    # respuesta vieja (otra pregunta en curso): se descarta
    n = len(w.said)
    brain._ai_done("id2", 6, "Lacri", "rude", "es", "x", "vieja", 10.0, "")
    assert len(w.said) == n


def test_slow_ai_switches_auto_to_phrases(brain):
    brain._gen["id3"] = 1
    brain._ai_done("id3", 1, "Panda", "kind", "es", "hola", "¡Hola!", 1.2, "")
    assert brain.too_slow and brain.engine() == "phrases"
    assert brain.app.manager.mascots["id3"].said[-1] == ("¡Hola!", True)


# ── seguridad: importar vídeo (ffmpeg) ──────────────────────────────────────
def test_video_import_rejects_playlists(tmp_path):
    import shutil as sh
    from animalinux.core import image_processor as ip
    if not sh.which("ffprobe") or not sh.which("ffmpeg"):
        pytest.skip("sin ffmpeg")
    secret = tmp_path / "secreto.txt"
    secret.write_text("x")
    pl = tmp_path / "v.m3u8"
    pl.write_text(f"#EXTM3U\n#EXTINF:1.0,\nfile://{secret}\n#EXT-X-ENDLIST\n")
    assert ip._video_container_ok(pl) is False
    cc = tmp_path / "c.ffconcat"
    cc.write_text(f"ffconcat version 1.0\nfile {secret}\n")
    assert ip._video_container_ok(cc) is False
    vid = tmp_path / "ok.mp4"
    import subprocess as sp
    sp.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=32x32:d=1",
            "-pix_fmt", "yuv420p", str(vid)], check=True)
    assert ip._video_container_ok(vid) is True
    frames = ip._load_video(vid)
    assert len(frames) >= 1


def test_corrupt_settings_do_not_break_talk(brain):
    from animalinux import settings
    settings.set_val("talk_pets", ["no", "soy", "dict"])
    settings.set_val("talk_engine", 42)
    settings.set_val("talk_wake", "sí")
    assert brain.pet_cfg("id2")["wake"] == "lacri"
    assert brain.engine() == "ai"                     # vuelve al valor por defecto (auto)
    settings.set_val("talk_pets", {"id2": {"wake": 5, "persona": None}})
    pc = brain.pet_cfg("id2")
    assert pc["wake"] == "lacri" and pc["persona"] == "kind"


@pytest.mark.parametrize("free,name,ok", [
    # casos reales medidos con voz neuronal (Piper) + Vosk
    ([("oye", 1.0), ("panda", 1.0)], "panda", True),
    ([("el", 0.54), ("panda", 0.98)], "panda", True),          # «ey panda» mal oído, poca confianza
    ([("hey", 0.32), ("caucho", 0.92)], "kao ru ko", True),    # nombre raro, suena parecido
    ([("oye", 1.0), ("no", 1.0), ("sé", 0.8)], "no ce", True),
    ([("hola", 0.94), ("bolita", 1.0)], "bolita", True),
    ([("el", 1.0), ("panda", 1.0)], "panda", False),           # «el panda come bambú»
    ([("oye", 1.0), ("pásame", 1.0)], "panda", False),         # «oye, pásame la sal»
    ([], "panda", True),
    ([("oye", 0.49), ("sí", 0.34)], "azul", True),          # voz real: la libre DUDA → vale la gramática
    ([("oye", 1.0), ("pásame", 0.95)], "panda", False),     # la libre está SEGURA de otra palabra
])
def test_verify_wake_real_cases(free, name, ok):
    assert voice.verify_wake(free, name, ["oye", "ey", "hey", "hola"]) is ok


def test_phonetic():
    assert voice.phonetic("Kaoruko") == voice.phonetic("caoruco")
    assert voice.phonetic("noce") == voice.phonetic("no se")


def test_words_in_span_uses_timing():
    free = [("oye", 1.0, 0.0, 0.3), ("pásame", 1.0, 0.35, 0.8), ("la", 1.0, 0.85, 0.9),
            ("sal", 1.0, 0.95, 1.2)]
    inside, before = voice.words_in_span(free, 0.35, 0.7)
    assert inside == [("pásame", 1.0)] and before == ("oye", 1.0)
    assert voice.verify_wake([before] + inside, "panda", ["oye"]) is False


@pytest.mark.parametrize("before,ok", [
    (("hey", 1.0), True), (("the", 1.0), False), (("he", 0.4), True), (("", 0.0), True),
])
def test_verify_wake_unknown_names_only_checks_call_word(before, ok):
    assert voice.verify_wake([before], "bo lita", ["hey", "hi", "okay", "hello"], strict=False) is ok


# ── seguridad: proyectos .alproj ajenos ─────────────────────────────────────
def _png(w, h):
    import struct
    import zlib
    raw = b"".join(b"\0" + b"\0" * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


@pytest.mark.parametrize("img_size,ok", [((12000, 12000), False), ((32, 32), False), ((64, 64), True)])
def test_alproj_rejects_decompression_bomb(tmp_path, img_size, ok):
    from animalinux.editors import anim_engine as ae
    p = tmp_path / "x.alproj"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("d.png", _png(*img_size))
        z.writestr("project.json", json.dumps({
            "version": 2, "w": 64, "h": 64, "frames": 1, "fps": 12,
            "layers": [{"name": "x", "kind": "raster", "exposure": [0], "drawings": [{"img": "d.png"}]}]}))
    if ok:
        assert ae.Scene.load(p).layers[0].name == "x"
    else:
        with pytest.raises(ValueError):
            ae.Scene.load(p)


# ── seguridad: fuzzing del lector de Aseprite ───────────────────────────────
def test_aseprite_fuzz_only_raises_aseerror():
    import random
    from animalinux.editors import aseprite as A
    spr = A.AseSprite(16, 12)
    lay = A.AseLayer("c")
    lay.frames = [bytes([(i * 3) % 256 for i in range(16 * 12 * 4)])] * 2
    spr.layers.append(lay)
    spr.durations = [100, 100]
    base = A.build(spr)
    rng = random.Random(5)
    for _ in range(400):
        d = bytearray(base)
        for _k in range(rng.choice((1, 4, 16))):
            i = rng.randrange(len(d))
            d[i] = rng.randrange(256)
        try:
            A.parse(bytes(d))
        except A.AseError:
            pass


# ── seguridad: fuzzing de packs (.alpack) ───────────────────────────────────
def test_pack_import_fuzz_leaves_no_orphan_dirs(tmp_path):
    import io
    import random
    from PIL import Image
    from animalinux import pack

    class Lib:
        def __init__(s):
            s.n, s.added = 0, []

        def new_id(s):
            s.n += 1
            return f"id{s.n}"

        def frames_dir(s, aid):
            return tmp_path / "lib" / aid

        def add(s, aid, *a):
            s.added.append(aid)

        def update(s, *a, **k):
            pass
    b = io.BytesIO()
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(b, "PNG")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mascot.json", json.dumps({"format": pack.MAGIC, "name": "x", "poses": ["default", "walk"]}))
        for p in ("default", "walk"):
            for i in range(3):
                z.writestr(f"poses/{p}/frame_{i:04d}.png", b.getvalue())
    base = buf.getvalue()
    lib, rng = Lib(), random.Random(11)
    (tmp_path / "lib").mkdir()
    for k in range(200):
        d = bytearray(base)
        for _ in range(rng.choice((1, 3, 8))):
            d[rng.randrange(len(d))] = rng.randrange(256)
        f = tmp_path / f"f{k}.alpack"
        f.write_bytes(d)
        try:
            pack.import_pack(lib, f)
        except Exception:  # noqa: BLE001
            pass
    left = {p.name for p in (tmp_path / "lib").iterdir()}
    assert left == set(lib.added), f"huérfanas: {sorted(left - set(lib.added))[:5]}"
    with pytest.raises(RuntimeError):
        g = tmp_path / "lista.alpack"
        with zipfile.ZipFile(g, "w") as z:
            z.writestr("mascot.json", "[1, 2]")
        pack.import_pack(lib, g)


# ── robustez: library.json / settings.json dañados ──────────────────────────
@pytest.mark.parametrize("content", ["{roto", "[1, 2, 3]", '{"animations": [1]}', '{"config": 5}'])
def test_corrupt_library_is_backed_up_not_lost(tmp_path, monkeypatch, content):
    from animalinux import paths
    from animalinux.core import library as libmod
    lf = tmp_path / "library.json"
    lf.write_text(content)
    monkeypatch.setattr(paths, "LIBRARY_FILE", lf)
    monkeypatch.setattr(paths, "ensure_dirs", lambda: None)
    lib = libmod.Library.__new__(libmod.Library)
    lib.config, lib.animations = {}, {}
    lib.load()                                       # no debe lanzar
    assert isinstance(lib.animations, dict) and isinstance(lib.config, dict)
    if content != '{"config": 5}':
        baks = list(tmp_path.glob("library.json.corrupto-*"))
        assert len(baks) == 1 and baks[0].read_text() == content


def test_settings_write_is_atomic_and_tolerates_garbage(tmp_path, monkeypatch):
    from animalinux import settings
    p = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "_PATH", p)
    p.write_text("[1, 2]")
    assert settings.get("talk_wake", False) is False   # no rompe con basura
    settings.set_val("x", 1)
    assert json.loads(p.read_text()) == {"x": 1}
    assert not (tmp_path / "settings.json.tmp").exists()


@pytest.mark.parametrize("text,who,rest", [
    ("panda me quieres", "id3", "me quieres"),
    ("oye panda, tengo hambre", "id3", "tengo hambre"),
    ("gato pixel eres lindo", "id0", "eres lindo"),
    ("lacri qué hora es", "id2", "qué hora es"),
    ("tengo hambre", "id1", "tengo hambre"),             # sin nombre: la de siempre
    ("el panda come bambú", "id1", "el panda come bambú"),
])
def test_button_routes_to_named_pet(brain, text, who, rest):
    assert brain.route_by_name("id1", text) == (who, rest)


def test_stale_ollama_is_killed_only_if_it_is_ollama(tmp_path, monkeypatch):
    import subprocess
    import sys as _sys
    from animalinux import paths
    monkeypatch.setattr(paths, "RUNTIME_DIR", tmp_path)
    # un proceso que NO es ollama: nunca se toca
    p = subprocess.Popen([_sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        llm._write_pid(p.pid)
        llm._kill_stale()
        time.sleep(0.3)
        assert p.poll() is None and not (tmp_path / "ollama.pid").exists()
    finally:
        p.kill()
    # sin archivo: no pasa nada
    llm._kill_stale()


def test_new_personas_fall_back_in_other_languages():
    r, topic = phrases.reply("tengo hambre", "es", "gamer", "X")
    assert topic == "hungry" and r in phrases.load("es")["replies"]["gamer"]["hungry"]
    r, topic = phrases.reply("i am hungry", "en", "gamer", "X")       # en aún sin «gamer»
    assert r in phrases.load("en")["replies"]["sarcastic"]["hungry"]
    assert phrases.examples("en", "gamer") == []
    assert "slang" in personas.system_prompt("X", "gamer", "en")


# ── Whisper de fábrica (05-nov-2026) ───────────────────────────────────────
def test_whisper_prompt_adds_pet_names():
    p = voice.whisper_prompt("es", ["Conejo", "Pollito", "Conejo", " ", "Claudio"])
    assert p.startswith(voice.WHISPER_HINT["es"])
    assert p.endswith("Conejo, Pollito, Claudio.")
    assert voice.whisper_prompt("xx", []) is None
    assert voice.whisper_prompt("xx", ["Panda"]) == "Panda."


def test_whisper_cpu_model_is_accurate_one():
    # base acertaba 83 %; small con beam 5, 96 % (ver comentario en voice.py)
    assert voice.WHISPER_MODEL == "small" and voice.CPU_BEAM >= 5
    assert voice.GPU_MODEL == "large-v3-turbo"


def test_whisper_falls_back_to_cpu_when_gpu_fails(monkeypatch):
    calls = []

    class FakeModel:
        def __init__(self, path, device, **kw):
            self.device = device
            calls.append(device)

        def transcribe(self, x, **kw):
            if self.device == "cuda":
                raise RuntimeError("Library libcublas.so.12 is not found")
            assert kw["beam_size"] == voice.CPU_BEAM
            assert "Conejo" in kw["initial_prompt"]

            class S:
                text = " Oye Conejo"
            return [S()], None

    import types
    fake = types.SimpleNamespace(WhisperModel=FakeModel)
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", fake)
    monkeypatch.setattr(voice, "cuda_usable", lambda: True)
    monkeypatch.setattr(voice, "whisper_installed", lambda model=None: True)
    w = voice.Whisper()
    out = w.transcribe(b"\0\0" * 1600, "es", ["Conejo"])
    assert out == "Oye Conejo"
    assert calls == ["cuda", "cpu"] and w.device == "cpu"


def test_no_gpu_without_nvidia(monkeypatch):
    monkeypatch.setattr(voice, "_cuda_ok", None)
    monkeypatch.setattr(voice, "nvidia_present", lambda: False)
    assert voice.cuda_usable() is False
    assert voice.whisper_model() == voice.WHISPER_MODEL


def test_install_whisper_pkg_uses_user_pip(monkeypatch):
    seen = {}
    monkeypatch.setattr(voice, "whisper_available", lambda: bool(seen))
    monkeypatch.setattr(voice, "can_install_whisper", lambda: True)

    def run(cmd, **kw):
        seen["cmd"] = cmd

        class R:
            returncode = 0
            stderr = stdout = ""
        return R()
    monkeypatch.setattr(voice.subprocess, "run", run)
    voice.install_whisper_pkg()
    assert seen["cmd"][1:5] == ["-m", "pip", "install", "--user"]
    assert "faster-whisper" in seen["cmd"]


def test_brain_start_applies_after_status(monkeypatch):
    from animalinux.talk import brain as brain_mod
    b = brain_mod.TalkBrain.__new__(brain_mod.TalkBrain)
    got = {}
    b._set_mic_button = lambda on: got.setdefault("btn", on)
    b.refresh_status = lambda done=None: got.setdefault("done", done)
    b.apply = lambda: None
    b.start()
    assert got["done"] == b.apply      # apply corre cuando ya se sabe si hay micrófono


def test_set_listening_toggles_and_enables(monkeypatch):
    from animalinux.talk import brain as brain_mod
    store = {"talk_enabled": False, "talk_wake": False}
    monkeypatch.setattr(brain_mod.settings, "get", lambda k, d=None: store.get(k, d))
    monkeypatch.setattr(brain_mod.settings, "set_val", lambda k, v: store.__setitem__(k, v))
    b = brain_mod.TalkBrain.__new__(brain_mod.TalkBrain)
    b.apply = lambda: None
    assert b.set_listening() is True and store == {"talk_enabled": True, "talk_wake": True}
    assert b.set_listening() is False and store["talk_wake"] is False
    assert b.set_listening(True) is True
