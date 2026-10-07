"""Arranque automático al iniciar sesión: delega en el backend de la plataforma
(Hyprland/XDG en Linux, clave Run del registro en Windows)."""
from ..backends import current as _backend


def is_enabled() -> bool:
    """¿Arranca AnimaLinux al iniciar sesión?"""
    return _backend.autostart.is_enabled()


def set_enabled(enabled: bool):
    """Activa o desactiva el arranque automático (efecto al próximo login)."""
    _backend.autostart.set_enabled(enabled)
