"""Recorte de fondo con IA, sin rembg.

Hace lo mismo que `rembg.remove(img, session=new_session("isnet-anime"))`
(mismo modelo, misma normalización y mismo recorte «naive»), pero solo
necesita onnxruntime + numpy + Pillow. rembg arrastraba opencv, scipy,
scikit-image, numba y pymatting: en AnimaWin eso no se podía empaquetar y la
app pedía «pip install rembg», que un usuario de Windows no puede hacer.

- El motor (onnxruntime) viene con la app: en Arch es dependencia del paquete
  y en AnimaWin va dentro del instalador (la onnxruntime.dll oficial, usada
  por su API en C con ctypes: ver ort_capi.py). Si falta (instalación con pip), se
  instala solo con pip --user la primera vez.
- El modelo (176 MB) se baja solo la primera vez, por HTTPS desde la release
  oficial de rembg, y se comprueba su SHA-256 antes de usarlo.
"""
import hashlib
import importlib
import importlib.util
import os
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .. import paths
from ..i18n import tr

MODEL_NAME = "isnet-anime"
MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-anime.onnx"
MODEL_SHA256 = "f15622d853e8260172812b657053460e20806f04b9e05147d49af7bed31a6e99"
MODEL_SIZE = 176069933
INPUT_SIZE = (1024, 1024)
MEAN = (0.485, 0.456, 0.406)

_lock = threading.Lock()
_session = None


class CutoutError(RuntimeError):
    pass


# ── motor ───────────────────────────────────────────────────────────────────
_PY_OK = None


def _py_engine():
    """¿Hay onnxruntime de Python QUE CARGUE? (el de MSYS2 existe pero falla al importar)."""
    global _PY_OK
    if _PY_OK is None or not _PY_OK:
        try:
            if importlib.util.find_spec("onnxruntime") is None:
                return False
            import onnxruntime  # noqa: F401
            _PY_OK = True
        except Exception:  # noqa: BLE001
            _PY_OK = False
    return _PY_OK


def engine_available():
    """onnxruntime de Python, o la librería oficial en C (AnimaWin, ver ort_capi)."""
    if _py_engine():
        return True
    from . import ort_capi
    return ort_capi.find_library() is not None


def _install_engine():
    """pip install --user onnxruntime (solo fuera del AnimaWin empaquetado)."""
    if getattr(sys, "frozen", False):
        raise CutoutError(tr("Falta el motor de IA en esta instalación. Reinstala la app."))
    cmd = [sys.executable, "-m", "pip", "install", "--user", "--quiet", "onnxruntime"]
    if sys.platform != "win32":
        cmd.insert(5, "--break-system-packages")    # pip --user en distros con PEP 668
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=1800)
    except (OSError, subprocess.SubprocessError) as e:
        raise CutoutError(tr("No se pudo instalar el motor de IA: {e}", e=e)) from e
    import site
    importlib.invalidate_caches()
    usp = site.getusersitepackages()
    if usp not in sys.path:
        sys.path.append(usp)
    if r.returncode != 0 or not engine_available():
        tail = (r.stderr or r.stdout or "").strip()[-200:]
        raise CutoutError(tr("No se pudo instalar el motor de IA: {e}", e=tail))


# ── modelo ──────────────────────────────────────────────────────────────────
def model_path():
    return paths.DATA_DIR / "models" / f"{MODEL_NAME}.onnx"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


_checked = {}      # ruta → (tamaño, mtime) ya verificados: la huella se calcula una vez


def _valid(path):
    try:
        st = path.stat()
        if not path.is_file() or st.st_size != MODEL_SIZE:
            return False
        key = (st.st_size, st.st_mtime_ns)
        if _checked.get(str(path)) == key:
            return True
        ok = _sha256(path) == MODEL_SHA256
        if ok:
            _checked[str(path)] = key
        return ok
    except OSError:
        return False


def _reuse_rembg_copy(dest):
    """Si rembg ya bajó el mismo modelo (~/.u2net), se copia en vez de bajarlo."""
    home = os.environ.get("U2NET_HOME") or os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~")), ".u2net")
    src = Path(home) / f"{MODEL_NAME}.onnx"
    if not _valid(src):
        return False
    tmp = dest.with_suffix(".part")
    with open(src, "rb") as a, open(tmp, "wb") as b:
        while chunk := a.read(1 << 20):
            b.write(chunk)
    os.replace(tmp, dest)
    return True


def _download(dest, progress=None):
    tmp = dest.with_suffix(".part")
    opener = urllib.request.build_opener()
    req = urllib.request.Request(MODEL_URL, headers={"User-Agent": "AnimaLinux"})
    try:
        with opener.open(req, timeout=60) as r, open(tmp, "wb") as f:
            if not r.geturl().startswith("https://"):
                raise CutoutError(tr("Descarga no permitida: solo se admite HTTPS desde GitHub."))
            got = 0
            while chunk := r.read(1 << 16):
                got += len(chunk)
                if got > MODEL_SIZE:
                    raise CutoutError(tr("La descarga del modelo de IA está dañada. Inténtalo de nuevo."))
                f.write(chunk)
                if progress:
                    progress(tr("Descargando modelo de IA (solo la primera vez)"), got / MODEL_SIZE)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        raise CutoutError(tr("No se pudo descargar el modelo de IA (¿hay internet?): {e}", e=e)) from e
    except CutoutError:
        tmp.unlink(missing_ok=True)
        raise
    if not _valid(tmp):
        tmp.unlink(missing_ok=True)
        raise CutoutError(tr("La descarga del modelo de IA está dañada. Inténtalo de nuevo."))
    os.replace(tmp, dest)


def ensure_model(progress=None):
    dest = model_path()
    if _valid(dest):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not _reuse_rembg_copy(dest):
        _download(dest, progress)
    return dest


def ensure_ready(progress=None):
    """Deja motor y modelo listos (instala/baja lo que falte). Devuelve la sesión."""
    global _session
    with _lock:
        if _session is not None:
            return _session
        if not engine_available():
            if progress:
                progress(tr("Instalando motor de IA (solo la primera vez)"), 0.0)
            _install_engine()
        model = ensure_model(progress)
        if _py_engine():
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            _session = ort.InferenceSession(str(model), sess_options=opts,
                                            providers=["CPUExecutionProvider"])
        else:
            from . import ort_capi
            _session = ort_capi.Session(model, "img", "mask", (1, 1) + INPUT_SIZE)
        return _session


# ── recorte ─────────────────────────────────────────────────────────────────
def predict_mask(session, img):
    """Máscara L del tamaño de `img` (igual que rembg DisSession.predict)."""
    im = img.convert("RGB").resize(INPUT_SIZE, Image.Resampling.LANCZOS)
    a = np.asarray(im, dtype=np.float64)
    a = a / max(float(a.max()), 1e-6)
    a = (a - np.array(MEAN)) / 1.0
    x = np.expand_dims(a.transpose((2, 0, 1)), 0).astype(np.float32)
    name = session.get_inputs()[0].name
    pred = session.run(None, {name: x})[0][:, 0, :, :]
    ma, mi = float(pred.max()), float(pred.min())
    pred = (pred - mi) / ((ma - mi) or 1.0)
    mask = Image.fromarray((np.squeeze(pred) * 255).astype("uint8"), mode="L")
    return mask.resize(img.size, Image.Resampling.LANCZOS)


def remove(img, session):
    img = ImageOps.exif_transpose(img) or img
    mask = predict_mask(session, img)
    return Image.composite(img.convert("RGBA"), Image.new("RGBA", img.size, 0), mask)
