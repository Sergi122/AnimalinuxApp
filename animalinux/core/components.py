"""Complementos: lo que algunas funciones necesitan y no siempre viene puesto.

Lo que se puede empaquetar ya viene dentro (AnimaWin trae onnxruntime,
ffmpeg, mpv, Vosk y sounddevice; el paquete de Arch los pide como
dependencias). Lo demás se descarga e instala con un clic desde la ventana
«Complementos» o desde la función que lo necesita:

  cutout   recorte de fondo con IA: motor onnxruntime + modelo (176 MB)
  ffmpeg   importar vídeos y exportar MP4 / stickers
  mpv      sonido en el editor de animación
  ollama   IA local para hablar con las mascotas (+ el modelo, en «Hablar»)
  vosk     reconocimiento de voz (+ el modelo de tu idioma)
  whisper  entender mejor tu voz (solo Linux: AnimaWin no puede cargarlo)

Seguridad: las descargas son HTTPS desde GitHub y se comparan con la huella
SHA-256 que publica el proyecto antes de ejecutar o instalar nada. Lo que
necesita permisos de administrador en Linux pasa por pkexec (te pide tu
contraseña el propio sistema, la app nunca la ve).
"""
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from .. import paths
from ..i18n import N_, tr

FROZEN = bool(getattr(sys, "frozen", False))
WIN = sys.platform == "win32"
_ALLOWED_HOSTS = ("github.com", "objects.githubusercontent.com",
                  "release-assets.githubusercontent.com")
OLLAMA_RELEASE = "https://github.com/ollama/ollama/releases/latest/download/"


class ComponentError(RuntimeError):
    pass


# ── catálogo ────────────────────────────────────────────────────────────────
COMPONENTS = {
    "cutout":  (N_("✂ Recorte de fondo con IA"), N_("Quita el fondo al importar imágenes, GIF y vídeos."), 180),
    "ffmpeg":  (N_("🎬 ffmpeg"), N_("Importar vídeos y exportar MP4 o stickers."), 60),
    "mpv":     (N_("🔊 mpv"), N_("Sonido en el editor de animación."), 40),
    "ollama":  (N_("🧠 Ollama (IA para hablar)"), N_("Las mascotas te responden con IA en tu equipo, sin internet."), 1800),
    "vosk":    (N_("🎤 Reconocimiento de voz"), N_("Hablarle a tu mascota con el micrófono («oye <nombre>»)."), 30),
    "whisper": (N_("✨ Whisper"), N_("Entiende mucho mejor tu voz y tu acento."), 460),
}
ORDER = ("cutout", "ffmpeg", "mpv", "ollama", "vosk", "whisper")


def status(cid):
    """'ok' | 'missing' | 'unsupported'."""
    if cid == "cutout":
        from . import cutout
        return "ok" if cutout.engine_available() and cutout._valid(cutout.model_path()) else "missing"
    if cid in ("ffmpeg", "mpv"):
        return "ok" if shutil.which(cid) else ("unsupported" if WIN else "missing")
    if cid == "ollama":
        from ..talk import llm
        return "ok" if llm.find_binary() else "missing"
    if cid == "vosk":
        from ..talk import voice
        ok = voice.vosk_available() and voice.mic_available()
        return "ok" if ok else ("unsupported" if FROZEN else "missing")
    if cid == "whisper":
        from ..talk import voice
        if voice.whisper_available() and voice.whisper_installed():
            return "ok"
        return "missing" if voice.can_install_whisper() else "unsupported"
    return "unsupported"


def install(cid, progress=None):
    """Instala `cid`. progress(texto, fracción 0..1 o None). Lanza ComponentError."""
    progress = progress or (lambda *_a: None)
    try:
        if cid == "cutout":
            from . import cutout
            cutout.ensure_ready(progress)
        elif cid in ("ffmpeg", "mpv"):
            _system_packages([cid], progress)
        elif cid == "ollama":
            _install_ollama(progress)
        elif cid == "vosk":
            _install_vosk(progress)
        elif cid == "whisper":
            from ..talk import voice
            progress(tr("Instalando Whisper…"), None)
            if not voice.vosk_available():
                _install_vosk(progress)
            voice.ensure_whisper()
        else:
            raise ComponentError(tr("Complemento desconocido."))
    except ComponentError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ComponentError(str(e)[:300]) from e
    if status(cid) != "ok" and cid != "cutout":
        raise ComponentError(tr("Se instaló, pero todavía no responde. Reinicia la app."))


# ── ayudantes ───────────────────────────────────────────────────────────────
def _check_url(url):
    u = urllib.parse.urlparse(url)
    if u.scheme != "https" or u.hostname not in _ALLOWED_HOSTS:
        raise ComponentError(tr("Descarga no permitida: solo se admite HTTPS desde GitHub."))


def download(url, dest, progress=None, label="", sha256=None, max_bytes=4 << 30):
    """Baja `url` a `dest` (vía .part) comprobando host, tamaño y SHA-256."""
    _check_url(url)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "AnimaLinux"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            _check_url(r.geturl())             # también tras las redirecciones
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while chunk := r.read(1 << 18):
                got += len(chunk)
                if got > max_bytes:
                    raise ComponentError(tr("La descarga es demasiado grande."))
                h.update(chunk)
                f.write(chunk)
                if progress:
                    progress(label, got / total if total else None)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise ComponentError(tr("No se pudo descargar (¿hay internet?): {e}", e=e)) from e
    except ComponentError:
        tmp.unlink(missing_ok=True)
        raise
    if sha256 and h.hexdigest() != sha256.lower():
        tmp.unlink(missing_ok=True)
        raise ComponentError(tr("La descarga está dañada o fue alterada (no coincide la huella SHA-256). No se instaló nada."))
    os.replace(tmp, dest)
    return dest


def _ollama_sha(name):
    """Huella que publica Ollama en sha256sum.txt de su última versión."""
    _check_url(OLLAMA_RELEASE + "sha256sum.txt")
    req = urllib.request.Request(OLLAMA_RELEASE + "sha256sum.txt",
                                 headers={"User-Agent": "AnimaLinux"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            _check_url(r.geturl())
            text = r.read(1 << 20).decode("utf-8", "replace")
    except OSError as e:
        raise ComponentError(tr("No se pudo descargar (¿hay internet?): {e}", e=e)) from e
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*./") == name:
            return parts[0]
    raise ComponentError(tr("No encontré la huella SHA-256 de {name}.", name=name))


def _run(cmd, progress, label, timeout=3600):
    progress(label, None)
    from ..backends import current as backend
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=timeout, **getattr(backend, "SUBPROCESS_KW", {}))
    except (OSError, subprocess.SubprocessError) as e:
        raise ComponentError(str(e)) from e
    if cmd[0] == "pkexec" and r.returncode in (126, 127):
        raise ComponentError(tr("Cancelaste la contraseña: no se instaló nada."))
    if r.returncode != 0:
        raise ComponentError((r.stderr or r.stdout or "").strip()[-300:] or f"{cmd[0]}: {r.returncode}")
    return r


def _pkg_manager():
    for pm, cmd in (("pacman", ["pacman", "-S", "--needed", "--noconfirm"]),
                    ("apt-get", ["apt-get", "install", "-y"]),
                    ("dnf", ["dnf", "install", "-y"]),
                    ("zypper", ["zypper", "--non-interactive", "install"])):
        if shutil.which(pm):
            return pm, cmd
    return None, None


def _system_packages(pkgs, progress):
    if WIN:
        raise ComponentError(tr("En Windows ya viene dentro de la app. Reinstala AnimaWin."))
    pm, cmd = _pkg_manager()
    if not pm or not shutil.which("pkexec"):
        raise ComponentError(tr("No encontré cómo instalar paquetes del sistema. Instala a mano: {pkgs}",
                                pkgs=" ".join(pkgs)))
    _run(["pkexec", *cmd, *pkgs], progress, tr("Instalando {pkgs}… (el sistema te pedirá tu contraseña)",
                                               pkgs=", ".join(pkgs)))


def _pip(pkgs, progress):
    if FROZEN:
        raise ComponentError(tr("En Windows ya viene dentro de la app. Reinstala AnimaWin."))
    cmd = [sys.executable, "-m", "pip", "install", "--user", "--quiet", *pkgs]
    if not WIN:
        cmd.insert(5, "--break-system-packages")
    _run(cmd, progress, tr("Instalando {pkgs}…", pkgs=", ".join(pkgs)), timeout=1800)
    import importlib
    import site
    importlib.invalidate_caches()
    usp = site.getusersitepackages()
    if usp not in sys.path:
        sys.path.append(usp)


def _install_vosk(progress):
    from ..talk import voice
    if not voice.vosk_available():
        pm, _c = _pkg_manager()
        if pm == "pacman":
            _system_packages(["python-vosk"], progress)
            import importlib
            importlib.invalidate_caches()
        else:
            _pip(["vosk"], progress)
    if not voice.mic_available():
        pm, _c = _pkg_manager()
        pkg = {"pacman": "pipewire", "apt-get": "pipewire-bin", "dnf": "pipewire-utils"}.get(pm)
        if pkg:
            _system_packages([pkg], progress)


# ── Ollama ──────────────────────────────────────────────────────────────────
def user_ollama_dir():
    """Ollama instalado por la app sin root (distros sin paquete)."""
    return paths.DATA_DIR / "ollama"


def _nvidia():
    return os.path.exists("/proc/driver/nvidia/version") or bool(shutil.which("nvidia-smi"))


def _install_ollama(progress):
    if WIN:
        name = "OllamaSetup.exe"
        sha = _ollama_sha(name)
        dest = paths.RUNTIME_DIR / name
        download(OLLAMA_RELEASE + name, dest, progress,
                 tr("Descargando Ollama (~1,8 GB, solo una vez)"), sha256=sha)
        try:
            _run([str(dest), "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"],
                 progress, tr("Instalando Ollama…"))
        finally:
            dest.unlink(missing_ok=True)
        return
    pm, _c = _pkg_manager()
    if pm == "pacman":
        pkgs = ["ollama"] + (["ollama-cuda"] if _nvidia() else [])
        _system_packages(pkgs, progress)
        return
    # otras distros: el paquete oficial, en la carpeta de la app (sin root)
    import platform
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine(), "")
    if not arch or not shutil.which("tar"):
        raise ComponentError(tr("Instala Ollama desde https://ollama.com/download"))
    name = f"ollama-linux-{arch}.tar.zst"
    sha = _ollama_sha(name)
    tgz = paths.DATA_DIR / name
    download(OLLAMA_RELEASE + name, tgz, progress,
             tr("Descargando Ollama (~1,5 GB, solo una vez)"), sha256=sha)
    out = user_ollama_dir()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    try:
        _run(["tar", "--zstd", "-xf", str(tgz), "-C", str(out)], progress, tr("Instalando Ollama…"))
    finally:
        tgz.unlink(missing_ok=True)


def summary():
    """{cid: status} de todo (para la ventana y los tests)."""
    return {cid: status(cid) for cid in ORDER}


def describe(cid):
    title, desc, mb = COMPONENTS[cid]
    return tr(title), tr(desc), mb


__all__ = ["COMPONENTS", "ORDER", "ComponentError", "install", "status", "summary",
           "describe", "download", "user_ollama_dir"]
