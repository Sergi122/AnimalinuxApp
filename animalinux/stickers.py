"""
Exportar una mascota (o lo que hay en el editor) como sticker animado.

Cada plataforma pide otra cosa; aquí se respetan sus reglas y, si el archivo
sale pesado, se baja la calidad / los colores / los cuadros hasta que entra:

  Telegram  → .webm VP9 con transparencia, 512 px de lado mayor, ≤ 3 s,
              ≤ 30 fps, ≤ 256 KB (necesita ffmpeg con libvpx-vp9)
  Discord   → .png animado (APNG) 320×320, ≤ 512 KB
  WhatsApp  → .webp animado 512×512, ≤ 500 KB
  GIF       → .gif, 512 px de lado mayor (sirve para casi todo)

El pixel art se agranda con vecino más cercano (sin difuminar); el resto con
Lanczos.
"""
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from .i18n import N_

TARGETS = {
    "telegram": {"name": N_("Telegram (.webm)"), "ext": ".webm", "size": 512,
                 "square": False, "max_kb": 256, "max_s": 3.0, "max_fps": 30},
    "discord": {"name": N_("Discord (.png animado)"), "ext": ".png", "size": 320,
                "square": True, "max_kb": 512, "max_s": 10.0, "max_fps": 30},
    "whatsapp": {"name": N_("WhatsApp (.webp)"), "ext": ".webp", "size": 512,
                 "square": True, "max_kb": 500, "max_s": 10.0, "max_fps": 30},
    "gif": {"name": N_("GIF animado"), "ext": ".gif", "size": 512,
            "square": False, "max_kb": 0, "max_s": 15.0, "max_fps": 50},
}


class StickerError(RuntimeError):
    pass


def load_pose(frames_dir, pose="default"):
    d = Path(frames_dir)
    if pose != "default" and (d / pose).is_dir():
        d = d / pose
    files = sorted(d.glob("frame_*.png"))
    if not files:
        files = sorted(Path(frames_dir).glob("frame_*.png"))
    return [Image.open(f).convert("RGBA") for f in files]


def _crop_union(frames):
    box = None
    for f in frames:
        b = f.getbbox()
        if b is None:
            continue
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                     max(box[2], b[2]), max(box[3], b[3]))
    return [f.crop(box) for f in frames] if box else frames


def fit(frames, size, square):
    """Recorta lo transparente común y escala al tamaño de la plataforma."""
    frames = _crop_union(frames)
    w, h = frames[0].size
    k = size / float(max(w, h))
    nw, nh = max(1, round(w * k)), max(1, round(h * k))
    pixel = max(w, h) <= 160            # sprites chicos = pixel art
    out = []
    for f in frames:
        g = f.resize((nw, nh), Image.NEAREST if pixel else Image.LANCZOS)
        cw, ch = (size, size) if square else (nw, nh)
        if (cw, ch) != (nw, nh):
            c = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
            c.alpha_composite(g, ((cw - nw) // 2, (ch - nh) // 2))
            g = c
        out.append(g)
    return out


def _timeline(frames, fps, cfg):
    fps = max(1, min(int(fps), cfg["max_fps"]))
    n_max = max(1, int(cfg["max_s"] * fps))
    return frames[:n_max], fps


def export(frames, fps, target, out_path):
    """Escribe el sticker. Devuelve (ruta, KB)."""
    cfg = TARGETS[target]
    if not frames:
        raise StickerError(N_("No hay fotogramas para exportar."))
    out = Path(out_path)
    if out.suffix.lower() != cfg["ext"]:
        out = out.with_suffix(cfg["ext"])
    frames, fps = _timeline(frames, fps, cfg)
    frames = fit(frames, cfg["size"], cfg["square"])
    if target == "telegram":
        data = _webm(frames, fps, cfg["max_kb"])
    elif target == "discord":
        data = _apng(frames, fps, cfg["max_kb"])
    elif target == "whatsapp":
        data = _webp(frames, fps, cfg["max_kb"])
    else:
        data = _gif(frames, fps)
    out.write_bytes(data)
    return out, len(data) / 1024.0


# ── formatos ───────────────────────────────────────────────────────────────
def _fits(data, max_kb):
    return not max_kb or len(data) <= max_kb * 1024


def _apng(frames, fps, max_kb):
    dur = round(1000 / fps)
    for colors in (0, 128, 64, 32):
        for step in (1, 2, 3):
            fr = frames[::step]
            if colors:
                fr = [f.quantize(colors, method=Image.Quantize.FASTOCTREE).convert("RGBA")
                      for f in fr]
            buf = io.BytesIO()
            fr[0].save(buf, format="PNG", save_all=True, append_images=fr[1:],
                       duration=dur * step, loop=0, disposal=1, optimize=True)
            if _fits(buf.getvalue(), max_kb):
                return buf.getvalue()
    raise StickerError(N_("No se pudo dejar el sticker bajo el límite de tamaño."))


def _webp(frames, fps, max_kb):
    dur = round(1000 / fps)
    for q in (90, 75, 60, 45, 30):
        for step in (1, 2):
            fr = frames[::step]
            buf = io.BytesIO()
            fr[0].save(buf, format="WEBP", save_all=True, append_images=fr[1:],
                       duration=dur * step, loop=0, quality=q, method=6)
            if _fits(buf.getvalue(), max_kb):
                return buf.getvalue()
    raise StickerError(N_("No se pudo dejar el sticker bajo el límite de tamaño."))


def _gif(frames, fps):
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   duration=max(20, round(1000 / fps)), loop=0, disposal=2)
    return buf.getvalue()


def ffmpeg_ok():
    exe = shutil.which("ffmpeg")
    if not exe:
        return False
    try:
        out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True,
                             text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "libvpx-vp9" in out


def _webm(frames, fps, max_kb):
    if not ffmpeg_ok():
        raise StickerError(N_("Para Telegram hace falta ffmpeg (con VP9). Instálalo y vuelve a intentarlo."))
    tmp = Path(tempfile.mkdtemp(prefix="animalinux_sticker_"))
    try:
        for i, f in enumerate(frames):
            f.save(tmp / f"f_{i:04d}.png")
        dur = len(frames) / float(fps)
        for crf in (30, 36, 42, 50, 58):
            kbps = int(max_kb * 8 * 0.92 / max(0.5, dur))
            out = tmp / "s.webm"
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
                 "-i", str(tmp / "f_%04d.png"), "-c:v", "libvpx-vp9",
                 "-pix_fmt", "yuva420p", "-crf", str(crf), "-b:v", f"{kbps}k",
                 "-an", "-auto-alt-ref", "0", str(out)],
                capture_output=True, timeout=120)
            if r.returncode != 0:
                raise StickerError(N_("ffmpeg falló al crear el .webm."))
            data = out.read_bytes()
            if _fits(data, max_kb):
                return data
        raise StickerError(N_("No se pudo dejar el sticker bajo el límite de tamaño."))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
