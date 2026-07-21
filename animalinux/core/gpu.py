"""
Detección best-effort de si hay una GPU real (aceleración por hardware).

Solo importa en el backend X11 (ver overlay/x11_animation.py y
ui/control.py): cada mascota "Con vida" es una ventana fullscreen ARGB
independiente, y con render por software (VMs sin passthrough gráfico, tipo
llvmpipe) el compositor de algunos gestores de ventanas (xfwm4, Muffin...)
puede fallar al componerlas cuando hay varias a la vez -- confirmado en vivo:
sin GPU, el contenido de la ventana siempre se pinta bien por dentro, pero el
compositor no siempre logra copiarlo a pantalla. En Wayland/Hyprland
(wlr-layer-shell) no aplica: el compositor gestiona las superficies de otra
forma y no se ha visto el mismo fallo.
"""
import subprocess

_SOFTWARE_MARKERS = (
    "llvmpipe", "softpipe", "swrast", "software rasterizer", "softwarerasterizer",
)


def is_software_rendering():
    """True si se detecta render por software, False si hay GPU real,
    None si no se pudo determinar (glxinfo no instalado, etc.) — en ese
    caso el llamador no debería avisar nada, para no dar falsos positivos."""
    try:
        out = subprocess.run(
            ["glxinfo", "-B"], capture_output=True, text=True, timeout=3
        ).stdout.lower()
    except Exception:  # noqa: BLE001
        return None
    if not out:
        return None
    for line in out.splitlines():
        if "opengl renderer" in line:
            return any(marker in line for marker in _SOFTWARE_MARKERS)
    return None
