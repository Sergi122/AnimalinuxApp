"""
Capa visible de las mascotas. Qué ventana se usa lo decide el backend de la
plataforma (ver backends/): en Linux, wlr-layer-shell (Hyprland/Sway) o EWMH
(X11); en Windows, ventanas Win32 nativas. Todas exponen la misma clase
MascotWindow con idéntica interfaz pública, así que mascot_manager.py no
necesita saber cuál está usando.

Los módulos de este paquete (clock, poses, live_animation) son los comunes a
los backends basados en GTK.
"""
from ..backends import current as _backend

MascotWindow, BACKEND = _backend.overlay()
__all__ = ["MascotWindow", "BACKEND"]
