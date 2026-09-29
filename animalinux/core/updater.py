"""
Actualizaciones de AnimaLinux.

- check_latest(): consulta los tags de GitHub y devuelve la versión más nueva.
- should_check(): a lo sumo una consulta cada 24 h y solo si el usuario no la
  desactivó (settings: auto_update_check).
- apply_update(): descarga el tag y lo instala igual que se instaló la app:
    * paquete de pacman  -> makepkg + `pkexec pacman -U` (queda registrado)
    * cualquier otro     -> pip install --user
  Nunca se instala nada sin que el usuario pulse "Actualizar ahora".
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path
from ..i18n import tr

from .. import __version__
from .. import settings

REPO = "Sergi122/AnimalinuxApp"
_TAGS_URL = f"https://api.github.com/repos/{REPO}/tags?per_page=30"
_TARBALL_URL = f"https://github.com/{REPO}/archive/refs/tags/v{{v}}.tar.gz"
CHECK_INTERVAL = 24 * 3600


def _parse(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def is_newer(candidate: str, current: str = __version__) -> bool:
    try:
        return _parse(candidate) > _parse(current)
    except ValueError:
        return False


def _get(url: str, timeout: int = 10) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"animalinux/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (https fijo)
        return r.read()


def check_latest() -> str | None:
    """Versión más nueva publicada (sin la 'v'), o None si no hay red/tags."""
    try:
        tags = json.loads(_get(_TAGS_URL))
        versions = [t["name"].lstrip("v") for t in tags
                    if re.fullmatch(r"v\d+\.\d+\.\d+", t.get("name", ""))]
        return max(versions, key=_parse) if versions else None
    except Exception:  # noqa: BLE001 — sin red no es un error
        return None


def enabled() -> bool:
    return bool(settings.get("auto_update_check", True))


def should_check() -> bool:
    if not enabled():
        return False
    return time.time() - float(settings.get("last_update_check", 0)) >= CHECK_INTERVAL


def check_and_store() -> str | None:
    """Consulta y guarda el resultado. Devuelve la versión nueva o None."""
    latest = check_latest()
    settings.set_val("last_update_check", time.time())
    if latest and is_newer(latest):
        settings.set_val("update_available", latest)
        return latest
    settings.set_val("update_available", "")
    return None


def pending() -> str | None:
    """Versión nueva ya detectada (y aún mayor que la instalada), si la hay."""
    v = settings.get("update_available", "")
    return v if v and is_newer(v) else None


def install_method() -> str:
    """'pacman' si el paquete lo gestiona pacman, si no 'pip'."""
    if shutil.which("pacman"):
        try:
            r = subprocess.run(["pacman", "-Qo", str(Path(__file__).resolve())],
                               capture_output=True, timeout=15)
            if r.returncode == 0:
                return "pacman"
        except Exception:  # noqa: BLE001
            pass
    return "pip"


def _run(cmd, cwd, log):
    log(" ".join(cmd))
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        tail = (p.stderr or p.stdout).strip().splitlines()[-6:]
        raise RuntimeError("\n".join(tail) or tr("{cmd} falló ({code})", cmd=cmd[0], code=p.returncode))


def apply_update(version: str, log=lambda _m: None) -> None:
    """Descarga e instala `version`. Lanza RuntimeError si algo falla.
    Bloqueante: llamar desde un hilo."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise RuntimeError(tr("versión inválida: {version}", version=version))
    tmp = Path(tempfile.mkdtemp(prefix="animalinux-update-"))
    try:
        log(tr("Descargando v{version}…", version=version))
        tgz = tmp / "src.tar.gz"
        tgz.write_bytes(_get(_TARBALL_URL.format(v=version), timeout=60))
        with tarfile.open(tgz) as tf:
            tf.extractall(tmp, filter="data")
        src = next(p for p in tmp.iterdir() if p.is_dir())

        if install_method() == "pacman":
            if not shutil.which("makepkg"):
                raise RuntimeError(tr("Falta makepkg (paquete base-devel)."))
            log(tr("Construyendo el paquete…"))
            # --skipchecksums: el sha256 del PKGBUILD de un tag es el de la
            # versión anterior (se calcula después de crear el tag).
            _run(["makepkg", "-f", "--noconfirm", "--skipchecksums"], src, log)
            pkgs = sorted(src.glob("animalinux-*.pkg.tar.*"))
            pkgs = [p for p in pkgs if not p.name.endswith(".sig")]
            if not pkgs:
                raise RuntimeError(tr("makepkg no generó ningún paquete."))
            log(tr("Instalando (pide tu contraseña)…"))
            _run(["pkexec", "pacman", "-U", "--noconfirm", str(pkgs[-1])], src, log)
        else:
            log(tr("Instalando con pip…"))
            _run([sys.executable, "-m", "pip", "install", "--user",
                  "--break-system-packages", "."], src, log)
        settings.set_val("update_available", "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def restart() -> None:
    """Cierra la instancia actual y arranca la nueva, desacoplada."""
    env = os.environ.copy()
    env.pop("LD_PRELOAD", None)
    env.pop("ANIMALINUX_PRELOADED", None)
    subprocess.Popen(
        ["sh", "-c", "animalinux --quit; sleep 2; exec animalinux --show"],
        env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
