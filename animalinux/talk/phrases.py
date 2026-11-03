"""
Modo SIN IA: frases escritas por tema y personalidad (talk/data/<idioma>.json).

  topics   tema → palabras clave. Una clave casa por PREFIJO al inicio de una
           palabra («aburr» → aburrido, aburrida, aburrimiento). En japonés y
           chino (sin espacios) casa en cualquier parte.
  replies  personalidad → tema → frases. «_all» vale para todas (p. ej. el
           tema «crisis», que siempre responde con apoyo de verdad).
  examples (frase del usuario, tema) para dar ejemplos de estilo a la IA.

Marcadores en las frases: {time} hora, {day} día de la semana, {name} nombre
de la mascota.
"""
import json
import random
import re
import time
import unicodedata
from pathlib import Path

DATA = Path(__file__).with_name("data")
PRIORITY = ("crisis",)          # se miran antes que cualquier otro tema
NO_SPACES = ("ja", "zh")

_cache = {}


def load(lang):
    if lang not in _cache:
        p = DATA / f"{lang}.json"
        if not p.is_file():
            p = DATA / "es.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["_lang"] = lang
        d["_re"] = _compile(d.get("topics", {}), lang in NO_SPACES)
        _cache[lang] = d
    return _cache[lang]


def norm(text):
    t = unicodedata.normalize("NFKD", (text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("'", "").replace("\u2019", "")        # «i'm» = «im», «j'ai» = «jai»
    return re.sub(r"\s+", " ", t).strip()


def _compile(topics, no_spaces):
    """Una clave que empieza por «=» es palabra EXACTA («=si» no casa «sigo»)."""
    out = {}
    for topic, kws in topics.items():
        pats = []
        for k in sorted({k for k in kws if k.strip(" =")}, key=len, reverse=True):
            exact = k.startswith("=")
            p = re.escape(norm(k.lstrip("=")))
            if not no_spaces:
                p = rf"(?<!\w){p}" + (r"(?!\w)" if exact else "")
            pats.append(p)
        if pats:
            out[topic] = re.compile("(" + "|".join(pats) + ")")
    return out


def detect(text, lang):
    """Tema de la frase (o "question" / "unknown")."""
    d = load(lang)
    t = norm(text)
    if not t:
        return "unknown"
    for topic in PRIORITY:
        rx = d["_re"].get(topic)
        if rx and rx.search(t):
            return topic
    # gana la clave más larga; si empatan, la que va más atrás en la frase
    # («你好可爱»: «可爱» pesa más que el saludo del principio)
    best, score = None, (0, -1)
    for topic, rx in d["_re"].items():
        for m in rx.finditer(t):
            s = (len(m.group(1)), m.start())
            if s > score:
                best, score = topic, s
    if best:
        return best
    if text.strip().endswith(("?", "？")) or t.startswith(tuple(d.get("question_words", ()))):
        return "question"
    return "unknown"


def _fill(s, name, now):
    d = time.strftime("%A", now)
    return s.replace("{time}", time.strftime("%H:%M", now)).replace(
        "{day}", d).replace("{name}", name)


def _persona_in(rep, persona):
    """Si este idioma aún no tiene frases de la personalidad, la más parecida
    (personas.PERSONAS[p]["like"]); la IA sí usa la personalidad exacta."""
    if persona in rep:
        return persona
    from .personas import PERSONAS
    return PERSONAS.get(persona, {}).get("like", "kind")


def options(lang, persona, topic):
    d = load(lang)
    rep = d.get("replies", {})
    persona = _persona_in(rep, persona)
    lst = rep.get("_all", {}).get(topic) or rep.get(persona, {}).get(topic)
    if not lst:
        lst = rep.get(persona, {}).get("unknown") or ["…"]
    return lst


_last = {}      # (lang, persona, topic) -> última frase dicha (no repetir)


def reply(text, lang, persona, name="", now=None, rng=random):
    """Respuesta escrita: (frase, tema)."""
    now = time.localtime() if now is None else now
    topic = detect(text, lang)
    lst = options(lang, persona, topic)
    key = (lang, persona, topic)
    choices = [x for x in lst if x != _last.get(key)] or lst
    s = rng.choice(choices)
    _last[key] = s
    return _fill(s, name, now), topic


def examples(lang, persona, n=2):
    """Pares (usuario, respuesta) de estilo para la IA. SIEMPRE los mismos
    para una personalidad: el comienzo del prompt no cambia y Ollama reutiliza
    lo ya procesado (la respuesta llega segundos antes en CPU)."""
    d = load(lang)
    out = []
    if persona not in d.get("replies", {}):
        return out          # sin frases en este idioma: la IA se guía por la descripción
    for user, topic in d.get("examples", []):
        if topic in PRIORITY:
            continue
        lst = [x for x in d.get("replies", {}).get(persona, {}).get(topic, ()) if "{" not in x]
        if lst:
            out.append((user, lst[0]))
        if len(out) >= n:
            break
    return out


def wake_words(lang):
    return list(load(lang).get("wake", []))
