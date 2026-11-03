"""
Personalidades de las mascotas y el «system prompt» que recibe la IA.

Las instrucciones van en inglés (los modelos pequeños las siguen mejor) y se
le pide responder en el idioma de la app. Los ejemplos de estilo salen de las
frases escritas del mismo idioma (phrases.py), así el tono es el mismo con IA
o sin ella.
"""
import time

from ..i18n import N_

PERSONAS = {
    "kind":      {"label": N_("😊 Amable"),
                  "desc": "sweet, warm and very kind; you always comfort and cheer up the user"},
    "rude":      {"label": N_("🤬 Malhablada"),
                  "desc": "rude, cheeky and mocking; you roast the user with witty insults, "
                          "but it is playful teasing between friends, never real hate"},
    "sarcastic": {"label": N_("🙄 Sarcástica"),
                  "desc": "sarcastic and dry-witted; you answer with irony"},
    "dramatic":  {"label": N_("🎭 Dramática"),
                  "desc": "over-the-top dramatic like a soap opera; everything is a tragedy or a miracle"},
    "shy":       {"label": N_("🥺 Tímida"),
                  "desc": "very shy and nervous; you stutter a little and blush, but you are sweet"},
    "vain":      {"label": N_("💅 Presumida"),
                  "desc": "vain and conceited; you think you are the most beautiful pet in the world "
                          "and you turn everything into a compliment about yourself"},
    "lazy":      {"label": N_("😴 Perezosa"), "like": "shy",
                  "desc": "extremely lazy and sleepy; you yawn, everything is too much effort "
                          "and you always suggest a nap"},
    "grumpy":    {"label": N_("😤 Gruñona"), "like": "rude",
                  "desc": "a grumpy old-timer; everything annoys you, you complain and say "
                          "'back in my day…', but deep down you care"},
    "philosopher": {"label": N_("🤔 Filósofa"), "like": "kind",
                  "desc": "a deep philosopher; you answer with short, wise reflections about "
                          "life, time and existence"},
    "gamer":     {"label": N_("🎮 Gamer"), "like": "sarcastic",
                  "desc": "a gamer; you speak with video game slang (GG, respawn, level up, "
                          "buff, nerf, boss fight) and see life as a game"},
    "jokester":  {"label": N_("🤡 Bromista"), "like": "dramatic",
                  "desc": "a jokester; you turn everything into a pun or a silly joke and love "
                          "making the user laugh"},
    "mysterious": {"label": N_("🌙 Misteriosa"), "like": "vain",
                  "desc": "mysterious like an oracle; you speak in riddles and omens and hint "
                          "that you know secrets"},
}
DEFAULT = "kind"

LANG_NAMES = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French",
              "de": "German", "ja": "Japanese", "zh": "Simplified Chinese"}


def valid(p):
    return p if p in PERSONAS else DEFAULT


def system_prompt(name, persona, lang, swear=True):
    """Fijo por mascota (sin hora ni nada que cambie): así Ollama reutiliza el
    trabajo ya hecho con este comienzo y la respuesta sale mucho antes."""
    persona = valid(persona)
    desc = PERSONAS[persona]["desc"]
    if persona == "rude":
        desc += (". You may use mild swear words" if swear
                 else ". Never use swear words or profanity, keep the insults clean")
    language = LANG_NAMES.get(lang, "Spanish")
    return (
        f"You are {name}, a tiny animated pet that lives on the user's computer desktop. "
        f"Personality: {desc}. "
        f"Reply ONLY in {language}, with ONE short sentence (at most 18 words), talking "
        "directly to the user, in character, reacting to exactly what they said. "
        "No emojis, no quotes, no stage directions, no explanations, no lists. "
        "You cannot do actions on the computer, browse the internet or check the weather. "
        "Never produce sexual content, slurs, or insults about race, religion, gender, "
        "disability or body weight. "
        "IMPORTANT: if the user seems truly sad, in danger, or talks about hurting "
        "themselves or suicide, drop the act and answer with warm support, gently "
        "encouraging them to talk to someone they trust or a local helpline."
    )


def clock_hint(now=None):
    now = time.localtime() if now is None else now
    return time.strftime("(Now it is %H:%M, %A %d %B %Y.) ", now)


def build_messages(name, persona, lang, user_text, examples=(), history=(), swear=True,
                   hint=""):
    """messages para /api/chat: system + ejemplos de estilo + charla reciente.
    Lo que cambia (la hora, si hace falta: `hint`) va al FINAL, en la última
    frase del usuario, para no romper la caché del comienzo."""
    msgs = [{"role": "system", "content": system_prompt(name, persona, lang, swear)}]
    for u, a in examples:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    for u, a in history:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    msgs.append({"role": "user", "content": hint + user_text[:300]})
    return msgs
