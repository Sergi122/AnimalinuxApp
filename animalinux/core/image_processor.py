"""
Importador de animaciones.

Acepta:  GIF, APNG, WebP animado, PNG/JPG (estático o secuencia), MP4/WebM.
Saca todos los frames como RGBA y, opcionalmente, les quita el fondo dejando
solo la mascota. Luego guarda cada frame como PNG con transparencia.

Quitar el fondo:
  - "ai":     rembg. Por defecto el modelo 'isnet-anime', entrenado para
              personajes anime -> recorte mucho más limpio para tus mascotas.
  - "chroma": quita un fondo plano usando las esquinas (rápido, sin IA).
  - "none":   no toca nada (animaciones que ya vienen transparentes).

Seguridad: límites contra "bombas de descompresión" (imágenes que se inflan a
gigas y cuelgan el equipo) y topes de tamaño/cantidad de frames.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageSequence

# --- Límites de seguridad ---------------------------------------------------
Image.MAX_IMAGE_PIXELS = 40_000_000      # ~6300x6300: frena bombas de descompresión
MAX_FRAMES = 300                          # tope de frames por animación
MAX_DIMENSION = 1024                       # si un frame es más grande, se reduce


def _guard_open(path):
    """Abre con Pillow protegiendo contra archivos maliciosos."""
    try:
        img = Image.open(path)
        img.verify()              # valida que sea una imagen real
    except Exception as e:        # noqa: BLE001
        raise RuntimeError(f"El archivo no es una imagen/animación válida: {e}")
    return Image.open(path)       # reabrir tras verify()


# ----------------------------------------------------------------------
# 1) Cargar frames segun el formato
# ----------------------------------------------------------------------
def load_frames(path):
    """Devuelve (lista_de_imagenes_RGBA, fps_sugerido)."""
    path = Path(path)
    ext = path.suffix.lower()

    if ext in (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"):
        return _load_video(path)

    img = _guard_open(path)       # gif / apng / webp / png / jpg
    frames = []
    durations = []
    for i, frame in enumerate(ImageSequence.Iterator(img)):
        if i >= MAX_FRAMES:
            break
        frames.append(_clamp_size(frame.convert("RGBA")))
        durations.append(frame.info.get("duration", 0))

    valid = [d for d in durations if d and d > 0]
    if valid:
        avg_ms = sum(valid) / len(valid)
        fps = max(1, min(60, round(1000.0 / avg_ms)))
    else:
        fps = 12
    return frames, fps


def _clamp_size(img):
    """Reduce el frame si excede MAX_DIMENSION (memoria/rendimiento)."""
    w, h = img.size
    m = max(w, h)
    if m > MAX_DIMENSION:
        ratio = MAX_DIMENSION / m
        img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))))
    return img


def _install_ffmpeg_hint():
    """El proyecto soporta tanto Arch/Hyprland como Mint/Ubuntu/Xfce; el
    comando de instalación no es el mismo, así que se detecta el gestor de
    paquetes disponible en vez de asumir pacman."""
    for cmd, pkg_cmd in (
        ("pacman", "sudo pacman -S ffmpeg"),
        ("apt", "sudo apt install ffmpeg"),
        ("dnf", "sudo dnf install ffmpeg"),
        ("zypper", "sudo zypper install ffmpeg"),
    ):
        if shutil.which(cmd):
            return pkg_cmd
    return "el gestor de paquetes de tu distro (paquete 'ffmpeg')"


def _load_video(path):
    """Extrae frames de un video usando ffmpeg (debe estar instalado)."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg no está instalado. Instálalo con: " + _install_ffmpeg_hint()
        )
    tmp = Path(tempfile.mkdtemp(prefix="animalinux_"))
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path),
             "-vf", "fps=15", "-frames:v", str(MAX_FRAMES),
             str(tmp / "f_%04d.png")],
            check=True, capture_output=True,
        )
        frames = [_clamp_size(Image.open(p).convert("RGBA"))
                  for p in sorted(tmp.glob("f_*.png"))[:MAX_FRAMES]]
        if not frames:
            raise RuntimeError("ffmpeg no produjo frames de ese video.")
        return frames, 15
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ----------------------------------------------------------------------
# 2) Quitar el fondo
# ----------------------------------------------------------------------
def remove_background(frames, method="ai", chroma_tolerance=40,
                      model="isnet-anime", progress=None):
    if method == "none":
        return frames
    if method == "ai":
        try:
            return _remove_bg_ai(frames, model=model, progress=progress)
        except ImportError:
            raise RuntimeError(
                "Para el recorte con IA necesitas rembg. Instálalo con:\n"
                "  pip install --user --break-system-packages rembg onnxruntime\n"
                "O elige el método «Color de fondo» (solo para fondos planos)."
            )
    if method == "chroma":
        out = []
        n = len(frames)
        for i, f in enumerate(frames):
            out.append(_remove_bg_chroma(f, chroma_tolerance))
            if progress:
                progress("Quitando fondo", (i + 1) / n)
        return out
    return frames


def _remove_bg_ai(frames, model="isnet-anime", progress=None):
    from rembg import remove, new_session  # import perezoso (dep opcional)
    try:
        session = new_session(model)       # 'isnet-anime' para personajes
    except Exception:                      # noqa: BLE001
        session = new_session("u2net")     # respaldo si no baja el modelo anime
    out = []
    n = len(frames)
    for i, f in enumerate(frames):
        out.append(remove(f, session=session).convert("RGBA"))
        if progress:
            progress("Recortando con IA", (i + 1) / n)
    return out


def _remove_bg_chroma(img, tol):
    """Quita el fondo asumiendo que el color de las 4 esquinas es el fondo."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    bg = tuple(sum(c[i] for c in corners) // 4 for i in range(3))

    new_data = []
    for r, g, b, a in img.getdata():
        if abs(r - bg[0]) <= tol and abs(g - bg[1]) <= tol and abs(b - bg[2]) <= tol:
            new_data.append((r, g, b, 0))
        else:
            new_data.append((r, g, b, a))
    img.putdata(new_data)
    return img


# ----------------------------------------------------------------------
# 3) Recortar al contenido y guardar
# ----------------------------------------------------------------------
def _autocrop(frames):
    box = None
    for f in frames:
        b = f.getbbox()
        if b:
            box = b if box is None else (
                min(box[0], b[0]), min(box[1], b[1]),
                max(box[2], b[2]), max(box[3], b[3]))
    if box:
        frames = [f.crop(box) for f in frames]
    return frames


def import_animation(src_path, dest_dir, bg_method="ai",
                     model="isnet-anime", autocrop=True, progress=None):
    """
    Pipeline completo. Devuelve (frame_count, width, height, fps).
    progress: callback opcional progress(texto, fraccion 0..1) para la barra.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if progress:
        progress("Leyendo archivo", 0.0)
    frames, fps = load_frames(src_path)
    frames = remove_background(frames, method=bg_method, model=model,
                               progress=progress)
    if autocrop:
        frames = _autocrop(frames)
    if not frames:
        raise RuntimeError("No se obtuvo ningún frame de ese archivo.")

    w, h = frames[0].size
    n = len(frames)
    for i, f in enumerate(frames):
        if f.size != (w, h):
            f = f.resize((w, h))
        f.save(dest_dir / f"frame_{i:04d}.png")
        if progress:
            progress("Guardando", (i + 1) / n)

    # generar también los frames espejados (para el modo Vida: mirar a la izq.)
    ensure_flipped(dest_dir)
    return n, w, h, fps


def ensure_flipped(frames_dir):
    """Crea flip_XXXX.png (espejo horizontal) si faltan. Para el modo Vida."""
    frames_dir = Path(frames_dir)
    normals = sorted(frames_dir.glob("frame_*.png"))
    for p in normals:
        flip = frames_dir / p.name.replace("frame_", "flip_")
        if not flip.exists():
            try:
                Image.open(p).transpose(Image.FLIP_LEFT_RIGHT).save(flip)
            except Exception:  # noqa: BLE001
                pass
