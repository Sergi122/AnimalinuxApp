"""
Arranque automático al iniciar sesión.

En Hyprland (el objetivo principal) el autostart es una línea
``exec-once = animalinux --daemon`` en la configuración. Aquí la activamos o
desactivamos comentándola/descomentándola, sin tocar nada más del config del
usuario. Si no existe y se activa, se añade a un archivo del config de hypr.

En otros escritorios se usa el estándar XDG: ``~/.config/autostart/animalinux.desktop``.

Activar/desactivar solo afecta al PRÓXIMO inicio de sesión (es justo lo que
significa "arrancar al encender"): no lanza ni cierra la app en caliente.
"""
import os
import re
import shutil
from pathlib import Path

DAEMON_ARG = "--daemon"

# exec-once = [#] ... animalinux ... --daemon ...
#   grupo 1: sangría   grupo 2: '#' si está comentada   grupo 3: la directiva
_LINE_RE = re.compile(
    r"^(\s*)(#+\s*)?(exec-once\s*=\s*\S*animalinux\b.*--daemon.*)$"
)


def _config_home() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base)


def _hypr_dir() -> Path:
    return _config_home() / "hypr"


def _use_hypr() -> bool:
    """Gestionamos vía Hyprland si existe su carpeta de config."""
    return _hypr_dir().is_dir()


def _hypr_conf_files():
    d = _hypr_dir()
    if not d.is_dir():
        return []
    return sorted(d.rglob("*.conf"))


def _bin_path() -> str:
    """Ruta absoluta al ejecutable si la conocemos (el autostart no hereda PATH)."""
    local = Path.home() / ".local" / "bin" / "animalinux"
    if local.exists():
        return str(local)
    found = shutil.which("animalinux")
    return found or "animalinux"


# ── Hyprland ────────────────────────────────────────────────────────────────
def _hypr_is_enabled() -> bool:
    for f in _hypr_conf_files():
        try:
            for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = _LINE_RE.match(line)
                if m and not m.group(2):  # encontrada y NO comentada
                    return True
        except OSError:
            continue
    return False


def _hypr_set(enabled: bool):
    found_any = False
    for f in _hypr_conf_files():
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        out, changed = [], False
        for line in text.splitlines():
            m = _LINE_RE.match(line)
            if m:
                found_any = True
                indent, commented, directive = m.group(1), m.group(2), m.group(3)
                if enabled and commented:
                    line = f"{indent}{directive}"
                    changed = True
                elif not enabled and not commented:
                    line = f"{indent}# {directive}"
                    changed = True
            out.append(line)
        if changed:
            f.write_text("\n".join(out) + "\n", encoding="utf-8")

    # No existía ninguna línea y se quiere activar → crearla.
    if enabled and not found_any:
        files = _hypr_conf_files()
        target = None
        # Preferir un archivo de "execs" si existe; si no, el primero.
        for f in files:
            if "exec" in f.name.lower():
                target = f
                break
        if target is None:
            target = files[0] if files else (_hypr_dir() / "hyprland.conf")
        target.parent.mkdir(parents=True, exist_ok=True)
        prev = ""
        if target.exists():
            prev = target.read_text(encoding="utf-8", errors="ignore").rstrip("\n") + "\n"
        block = (
            "\n# Autostart de AnimaLinux\n"
            f"exec-once = {_bin_path()} {DAEMON_ARG}\n"
        )
        target.write_text(prev + block, encoding="utf-8")


# ── XDG (otros escritorios) ─────────────────────────────────────────────────
def _xdg_file() -> Path:
    return _config_home() / "autostart" / "animalinux.desktop"


def _xdg_is_enabled() -> bool:
    f = _xdg_file()
    if not f.exists():
        return False
    txt = f.read_text(encoding="utf-8", errors="ignore").lower()
    return "hidden=true" not in txt


def _xdg_set(enabled: bool):
    f = _xdg_file()
    if not enabled:
        if f.exists():
            f.unlink()
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=AnimaLinux\n"
        "Comment=Mascotas animadas en el escritorio\n"
        f"Exec={_bin_path()} {DAEMON_ARG}\n"
        "Icon=animalinux\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )


# ── API pública ─────────────────────────────────────────────────────────────
def is_enabled() -> bool:
    """¿Arranca AnimaLinux al iniciar sesión?"""
    try:
        return _hypr_is_enabled() if _use_hypr() else _xdg_is_enabled()
    except OSError:
        return False


def set_enabled(enabled: bool):
    """Activa o desactiva el arranque automático (efecto al próximo login)."""
    if _use_hypr():
        _hypr_set(enabled)
    else:
        _xdg_set(enabled)
