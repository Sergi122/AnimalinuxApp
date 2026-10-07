"""Cobertura de traducciones: nadie debería ver español mezclado en otro idioma.

- cada clave de tr()/N_() del código existe en i18n_data.TR (6 idiomas rellenos);
- los marcadores {nombre} coinciden entre idiomas (si no, .format() fallaría);
- las claves de i18n._T están completas en los 7 idiomas.
"""
import ast
import re
from pathlib import Path

from animalinux import i18n, i18n_data

ROOT = Path(__file__).resolve().parents[1] / "animalinux"
_PH = lambda s: sorted(re.findall(r"\{[^}]*\}", s))  # noqa: E731


def _tr_keys():
    out = {}
    for p in ROOT.rglob("*.py"):
        if p.name == "i18n_data.py":
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and n.args:
                f = n.func
                name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
                a = n.args[0]
                if name in ("tr", "N_") and isinstance(a, ast.Constant) and isinstance(a.value, str):
                    if a.value.strip() and any(c.isalpha() for c in a.value):
                        out[a.value] = f"{p.name}:{n.lineno}"
    return out


def test_every_tr_key_has_a_translation():
    missing = {k: w for k, w in _tr_keys().items() if k not in i18n_data.TR}
    assert not missing, f"{len(missing)} textos sin traducir: " + "; ".join(f"{w}: {k[:50]!r}" for k, w in list(missing.items())[:8])


def test_translations_complete_and_placeholders_match():
    bad = []
    for k, v in i18n_data.TR.items():
        if len(v) != len(i18n._TR_LANGS):
            bad.append((k[:40], "longitud"))
            continue
        for lang, x in zip(i18n._TR_LANGS, v):
            if not x:
                bad.append((k[:40], lang, "vacío"))
            elif _PH(x) != _PH(k):
                bad.append((k[:40], lang, "marcadores"))
    assert not bad, bad[:8]


def test_keyed_strings_complete_in_all_languages():
    bad = []
    for key, entry in i18n._T.items():
        for lang in i18n.LANGUAGES:
            if not entry.get(lang):
                bad.append((key, lang))
        base = _PH(entry.get("es", ""))
        bad += [(key, lang, "marcadores") for lang in i18n.LANGUAGES if entry.get(lang) and _PH(entry[lang]) != base]
    assert not bad, bad[:8]


def test_brand_is_adapted_per_platform(monkeypatch):
    monkeypatch.setattr(i18n, "_APP_NAME", "AnimaWin")
    assert "AnimaWin" in i18n.tr("⏻  Salir de AnimaLinux") and "AnimaLinux" not in i18n.tr("⏻  Salir de AnimaLinux")
    monkeypatch.setattr(i18n, "_APP_NAME", "AnimaLinux")
    assert "AnimaLinux" in i18n.tr("⏻  Salir de AnimaLinux")
