"""Arranque automático en Windows: valor en HKCU\\...\\CurrentVersion\\Run
(no necesita permisos de administrador y se ve en el Administrador de tareas)."""
import sys
import winreg

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
from . import APP_NAME as _NAME


def _command() -> str:
    if getattr(sys, "frozen", False):          # empaquetado con PyInstaller
        return f'"{sys.executable}" --daemon'
    exe = sys.executable
    if exe.lower().endswith("python.exe"):     # sin consola negra al iniciar
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    return f'"{exe}" -m animalinux --daemon'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
            winreg.QueryValueEx(k, _NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0,
                        winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, _NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(k, _NAME)
            except OSError:
                pass
