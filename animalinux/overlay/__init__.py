"""
Capa visible: ventana wlr-layer-shell por mascota (modos GIF y Vida) en
Wayland/wlroots (Hyprland, Sway...), o ventana EWMH en X11 (GNOME, Cinnamon,
MATE, Xfce...) cuando no hay wlr-layer-shell disponible.

Punto único de bifurcación entre backends: normal_animation.py (Hyprland,
probado y no se toca) y x11_animation.py (X11) exponen la misma clase
MascotWindow con idéntica interfaz pública, así que mascot_manager.py no
necesita saber cuál está usando.
"""
import os


def _select_backend():
    if os.environ.get("ANIMALINUX_X11_FORCED"):
        # app.py ya decidió forzar XWayland (Wayland sin wlr-layer-shell,
        # p.ej. GNOME/KDE): usar el backend X11 sin más comprobaciones.
        from .x11_animation import MascotWindow
        return MascotWindow
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    is_wayland = session == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))
    if is_wayland:
        try:
            import gi
            gi.require_version("Gtk4LayerShell", "1.0")
            from gi.repository import Gtk4LayerShell  # noqa: F401
        except Exception:  # noqa: BLE001
            pass  # Wayland sin wlr-layer-shell (p.ej. GNOME Wayland): cae a X11
        else:
            from .normal_animation import MascotWindow
            return MascotWindow
    from .x11_animation import MascotWindow
    return MascotWindow


MascotWindow = _select_backend()
__all__ = ["MascotWindow"]
