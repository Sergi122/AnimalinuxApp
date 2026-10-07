"""
Actualizaciones de AnimaLinux.

- check_latest(): consulta los tags de GitHub y devuelve la versión más nueva.
- should_check(): una consulta cada vez que se abre la app y solo si el usuario no la
  desactivó (settings: auto_update_check).
- apply_update(): descarga el tag y lo instala igual que se instaló la app:
    * paquete de pacman  -> makepkg + `pkexec pacman -U` (queda registrado)
    * cualquier otro     -> pip install --user
  Nunca se instala nada sin que el usuario pulse "Actualizar ahora".

Canal de Windows (AnimaWin): las versiones se publican como releases de GitHub
con la etiqueta «win-vX.Y.Z», el instalador «AnimaWin-Setup-X.Y.Z.exe» y su
huella en las notas («SHA-256: <64 hex>»). apply_update() descarga el instalador
(solo HTTPS y solo desde GitHub), comprueba la huella y lo ejecuta en silencio;
el instalador cierra la app, reemplaza los archivos y la vuelve a abrir.
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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from ..i18n import tr

from .. import __version__
from .. import settings
from ..backends import current as backend

REPO = "Sergi122/AnimalinuxApp"
_TAGS_URL = f"https://api.github.com/repos/{REPO}/tags?per_page=30"
_TARBALL_URL = f"https://github.com/{REPO}/archive/refs/tags/v{{v}}.tar.gz"
_RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
_WIN_TAG_RE = re.compile(r"^win-v(\d+\.\d+\.\d+)$")
_SHA_RE = re.compile(r"SHA-256:\s*`?([0-9a-fA-F]{64})`?")
_WIN_ASSET = "AnimaWin-Setup-{v}.exe"
_ALLOWED_HOSTS = ("github.com", "githubusercontent.com")   # y sus subdominios
MAX_INSTALLER_BYTES = 400 * 1024 * 1024
_WIN = backend.NAME == "windows"
MIN_GAP = 60   # solo evita martillar la API si se abre/cierra la ventana a ráfagas


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


def _windows_releases() -> dict:
    """{versión: release} de las releases «win-vX.Y.Z» publicadas (no borradores)."""
    out = {}
    for r in json.loads(_get(_RELEASES_URL)):
        m = _WIN_TAG_RE.match(str(r.get("tag_name", "")))
        if m and not r.get("draft"):
            out[m.group(1)] = r
    return out


def check_latest() -> str | None:
    """Versión más nueva publicada (sin la 'v'), o None si no hay red/tags."""
    try:
        if _WIN:
            versions = list(_windows_releases())
            return max(versions, key=_parse) if versions else None
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
    return time.time() - float(settings.get("last_update_check", 0)) >= MIN_GAP


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
    if _WIN:
        return _apply_windows(version, log)
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
                  *backend.PIP_EXTRA, "."], src, log)
        settings.set_val("update_available", "")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Solo se siguen redirecciones HTTPS hacia GitHub (las descargas de las
    releases acaban en un subdominio de githubusercontent.com)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _host_ok(newurl):
            raise urllib.error.URLError(f"redirección no permitida: {newurl[:80]}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _host_ok(url: str) -> bool:
    u = urllib.parse.urlsplit(url)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in _ALLOWED_HOSTS)


def _download_verified(url: str, dest: Path, expected_sha: str, log=lambda _m: None) -> None:
    """Descarga `url` a `dest` comprobando tamaño máximo y SHA-256. Si algo no
    cuadra borra el archivo y lanza RuntimeError."""
    import hashlib
    if not _host_ok(url):
        raise RuntimeError(tr("Descarga no permitida: solo se admite HTTPS desde GitHub."))
    opener = urllib.request.build_opener(_SafeRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": f"animalinux/{__version__}"})
    h, done = hashlib.sha256(), 0
    try:
        with opener.open(req, timeout=30) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            if total > MAX_INSTALLER_BYTES:
                raise RuntimeError(tr("El instalador es demasiado grande."))
            last = -1
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_INSTALLER_BYTES:
                    raise RuntimeError(tr("El instalador es demasiado grande."))
                h.update(chunk)
                f.write(chunk)
                if total and done * 20 // total != last:
                    last = done * 20 // total
                    log(tr("Descargando… {x1}%", x1=done * 100 // total))
        if h.hexdigest().lower() != expected_sha.lower():
            raise RuntimeError(tr("La descarga está dañada o fue alterada (no coincide la huella SHA-256). No se instaló nada."))
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def _apply_windows(version: str, log=lambda _m: None) -> None:
    if not getattr(sys, "frozen", False):
        # fuera del instalador (p.ej. ejecutado desde el código fuente) no se
        # puede reemplazar la app: se lleva al usuario a descargarlo
        backend.open_url(f"https://github.com/{REPO}/releases")
        raise RuntimeError(tr("Descarga el instalador nuevo desde la página de versiones (se abrió en el navegador)."))
    rel = _windows_releases().get(version)
    if rel is None:
        raise RuntimeError(tr("No se encontró la versión {version} en GitHub.", version=version))
    asset_name = _WIN_ASSET.format(v=version)
    asset = next((a for a in rel.get("assets", []) if a.get("name") == asset_name), None)
    m = _SHA_RE.search(rel.get("body") or "")
    if asset is None or m is None:
        raise RuntimeError(tr("La versión no incluye instalador o huella de verificación."))
    tmp = Path(tempfile.mkdtemp(prefix="animawin-update-"))
    exe = tmp / asset_name
    log(tr("Descargando v{version}…", version=version))
    _download_verified(asset["browser_download_url"], exe, m.group(1), log)
    log(tr("Instalando… la app se reiniciará sola."))
    subprocess.Popen(
        [str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        creationflags=0x00000008 | 0x08000000,   # DETACHED_PROCESS | CREATE_NO_WINDOW
        close_fds=True)
    settings.set_val("update_available", "")


def restart() -> None:
    """Cierra la instancia actual y arranca la nueva, desacoplada."""
    backend.restart_app()
