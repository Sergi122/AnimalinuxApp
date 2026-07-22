"""
Icono de bandeja (como Steam en segundo plano). Va en SU PROPIO proceso porque
usa AppIndicator (GTK3) y no se puede mezclar con la app principal (GTK4).

El menú simplemente relanza el comando principal:
  - "Configurar / añadir animaciones"  ->  animalinux --show
  - "Salir"                            ->  animalinux --quit

Nota: en Hyprland el icono aparece si tu barra (Caelestia/Quickshell, Waybar…)
implementa un host de StatusNotifier/bandeja. Si no se ve, igual puedes abrir
la config con `animalinux --show` o un atajo de teclado.
"""
import os
import subprocess
import sys


def _run(*args):
    """Lanza el comando principal de forma robusta. El menú de la bandeja
    fallaba en silencio cuando `animalinux` no estaba en el PATH del proceso de
    bandeja: la excepción se la tragaba el callback de GTK. Aquí usamos el mismo
    intérprete (`python -m animalinux`), con un entorno limpio para que el
    re-exec de gtk4-layer-shell ocurra, y dejamos traza si algo falla."""
    env = os.environ.copy()
    env.pop("LD_PRELOAD", None)            # que main() vuelva a precargar limpio
    env.pop("ANIMALINUX_PRELOADED", None)
    candidates = (
        [sys.executable, "-m", "animalinux", *args],
        ["animalinux", *args],
    )
    for cmd in candidates:
        try:
            subprocess.Popen(cmd, env=env)
            return
        except Exception as e:  # noqa: BLE001
            last = e
    try:
        with open("/tmp/animalinux_tray.log", "a") as f:
            f.write(f"_run{args} falló: {last}\n")
    except Exception:  # noqa: BLE001
        pass


def main():
    import gi
    try:
        gi.require_version("Gtk", "3.0")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import Gtk, AyatanaAppIndicator3 as AppIndicator
    except (ValueError, ImportError):
        try:
            gi.require_version("AppIndicator3", "0.1")
            from gi.repository import Gtk, AppIndicator3 as AppIndicator
        except (ValueError, ImportError):
            print("[tray] No hay AppIndicator. Instala libayatana-appindicator. "
                  "Mientras tanto usa: animalinux --show")
            return 1

    indicator = AppIndicator.Indicator.new(
        "animalinux",
        "face-smile",  # icono del tema — igual que el menú de aplicaciones
        AppIndicator.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)

    menu = Gtk.Menu()

    item_cfg = Gtk.MenuItem(label="⚙  Configurar")
    item_cfg.connect("activate", lambda _w: _run("--show"))
    menu.append(item_cfg)

    item_add = Gtk.MenuItem(label="➕  Añadir animación")
    item_add.connect("activate", lambda _w: _run("--show"))
    menu.append(item_add)

    menu.append(Gtk.SeparatorMenuItem())

    item_quit = Gtk.MenuItem(label="⏻  Salir de AnimaLinux")
    item_quit.connect("activate", lambda _w: (_run("--quit"), Gtk.main_quit()))
    menu.append(item_quit)

    menu.show_all()
    indicator.set_menu(menu)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
