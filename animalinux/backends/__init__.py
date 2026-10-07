"""
Capa de plataforma de AnimaLinux.

La app (app.py, core/, ui/, editors/) solo habla con la interfaz de este
paquete; cada sistema operativo implementa la suya en su propio subpaquete:

    backends/linux/    Wayland (layer-shell/Hyprland) y X11 (EWMH)
    backends/windows/  Win32 nativo (ventanas en capas, sin GTK en el overlay)

``current`` es el módulo del sistema en el que se ejecuta. Contrato que cada
backend debe cumplir:

    NAME                          "linux" | "windows"
    dirs()                        -> (data_dir, config_dir, runtime_dir)
    prepare_process()             se llama ANTES de importar GTK (re-exec, env)
    overlay()                     -> (MascotWindow, kind)  kind: "wayland"|"x11"|"win32"
    platforms_async(callback)     callback(list[(x0, x1, y)] | None): bordes
                                  superiores de las ventanas abiertas, en
                                  coordenadas globales; se llama en el hilo
                                  principal
    fullscreen_watch(pause, cfg)  -> handle con .stop() | None; llama a
                                  pause(bool) al entrar/salir de pantalla
                                  completa (cfg = pause_on_fullscreen)
    start_tray() / stop_tray()    icono de bandeja (proceso o ventana propia)
    autostart                     módulo con is_enabled() / set_enabled(bool)

Este módulo debe seguir siendo barato de importar: nada de GTK aquí.
"""
import sys

if sys.platform == "win32":
    from . import windows as current
else:
    from . import linux as current

__all__ = ["current"]
