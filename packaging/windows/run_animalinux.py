"""Punto de entrada del ejecutable de Windows (PyInstaller)."""
import os
import sys

# ffmpeg, ffprobe y mpv vienen dentro del instalador (carpeta tools/): se
# ponen primero en el PATH para que la app los encuentre con shutil.which.
_base = os.path.dirname(sys.executable)
for _d in (os.path.join(_base, "tools"), os.path.join(_base, "_internal", "tools")):
    if os.path.isdir(_d):
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")

from animalinux.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
