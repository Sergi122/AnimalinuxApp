"""Suaviza las animaciones GIF (sin vida): interpolación de cuadros por flujo óptico
(ffmpeg minterpolate) con el bucle CERRADO (el último cuadro se interpola hacia el primero),
y limpieza opcional del halo del borde.

Uso:  improve_gifs.py <id_animacion> [--factor 2] [--defringe] [--out DIR] [--apply]
Sin --apply solo escribe el resultado en --out (por defecto /tmp/gif_out/<id>) y muestra las
métricas; con --apply respalda el original en ~/animalinux-audit/backup_gifs/ y lo reemplaza,
ajustando el fps de la biblioteca (fps × factor, misma duración)."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from animalinux.core import image_processor  # noqa: E402

LIB = Path.home() / ".local/share/animalinux/animations"
CFG = Path.home() / ".config/animalinux/library.json"
BAK = Path.home() / "animalinux-audit/backup_gifs"


def load_frames(folder):
    return [Image.open(f).convert("RGBA") for f in sorted(Path(folder).glob("frame_*.png"))]


def motion(frames):
    a = [np.asarray(f).astype(int) for f in frames]
    m = [np.abs(a[i][..., :3] - a[i + 1][..., :3]).mean() for i in range(len(a) - 1)]
    seam = np.abs(a[-1][..., :3] - a[0][..., :3]).mean()
    return float(np.mean(m)), float(seam)


def interpolate(frames, factor, fps, hard_thr=45.0):
    """N cuadros -> N*factor cuadros, bucle cerrado. RGB premultiplicado + alfa por separado."""
    n = len(frames)
    seq = frames + [frames[0], frames[0]]   # el 2.º duplicado hace que ffmpeg cubra todo el tramo de cierre
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for i, f in enumerate(seq):
            a = np.asarray(f).astype(np.float32) / 255.0
            rgb = (a[..., :3] * a[..., 3:4] * 255).astype(np.uint8)
            Image.fromarray(rgb, "RGB").save(td / f"c_{i:04d}.png")
            Image.fromarray((a[..., 3] * 255).astype(np.uint8), "L").save(td / f"a_{i:04d}.png")
        for kind in ("c", "a"):
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
                 "-i", str(td / f"{kind}_%04d.png"),
                 "-vf", f"minterpolate=fps={fps * factor}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
                 str(td / f"o{kind}_%04d.png")], check=True)
        # pasos con cambio brusco (giros, cambios de pose): el flujo óptico los deforma;
        # ahí se mantiene el cuadro original en vez de inventar cuadros intermedios
        diffs = [np.abs(np.asarray(seq[k]).astype(int)[..., :3] - np.asarray(seq[k + 1]).astype(int)[..., :3]).mean()
                 for k in range(n)]
        thr = max(hard_thr, 1.4 * float(np.median(diffs)))
        hold = {k for k, d in enumerate(diffs) if d > thr}
        print("   pasos sin interpolar (cambio brusco):", sorted(hold), "umbral %.1f" % thr,
              "diffs", [int(d) for d in diffs])
        out = []
        for i in range(n * factor):
            c = np.asarray(Image.open(td / f"oc_{i + 1:04d}.png").convert("RGB")).astype(np.float32)
            a = np.asarray(Image.open(td / f"oa_{i + 1:04d}.png").convert("L")).astype(np.float32) / 255.0
            rgb = np.where(a[..., None] > 0.003, c / np.maximum(a[..., None], 0.003), 0)
            rgba = np.dstack([np.clip(rgb, 0, 255), a * 255]).astype(np.uint8)
            out.append(Image.fromarray(rgba, "RGBA"))
        for k in hold:
            for j in range(1, factor):
                out[k * factor + j] = out[k * factor]
    return out


def defringe(f):
    """Quita el halo: alfa bajo -> 0 y erosión de 1 px del borde."""
    a = f.getchannel("A").point(lambda v: 0 if v < 40 else v).filter(ImageFilter.MinFilter(3))
    f = f.copy()
    f.putalpha(a)
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("anim_id")
    ap.add_argument("--factor", type=int, default=2)
    ap.add_argument("--defringe", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    src = LIB / args.anim_id
    frames = load_frames(src)
    lib = json.load(open(CFG))
    fps = int(lib["animations"][args.anim_id].get("fps", 12))
    m0, s0 = motion(frames)
    out = interpolate(frames, args.factor, fps) if args.factor > 1 else list(frames)
    if args.defringe:
        out = [defringe(f) for f in out]
    m1, s1 = motion(out)
    print(f"{args.anim_id}: {len(frames)} cuadros @ {fps} fps  movimiento {m0:.1f}  costura {s0:.1f} ({s0/m0:.2f}x)")
    print(f"        -> {len(out)} cuadros @ {fps*args.factor} fps  movimiento {m1:.1f}  costura {s1:.1f} ({s1/m1:.2f}x)")

    dst = Path(args.out or f"/tmp/gif_out/{args.anim_id}")
    dst.mkdir(parents=True, exist_ok=True)
    for f in dst.glob("*.png"):
        f.unlink()
    for i, f in enumerate(out):
        f.save(dst / f"frame_{i:04d}.png", optimize=True)
    if not args.apply:
        print("escrito en", dst, "(sin --apply: la biblioteca no se toca)")
        return
    BAK.mkdir(parents=True, exist_ok=True)
    if not (BAK / args.anim_id).exists():
        shutil.copytree(src, BAK / args.anim_id)
    for f in list(src.glob("frame_*.png")) + list(src.glob("flip_*.png")):
        f.unlink()
    for f in sorted(dst.glob("frame_*.png")):
        shutil.copy(f, src / f.name)
    image_processor.ensure_flipped(src)
    lib["animations"][args.anim_id]["fps"] = fps * args.factor
    json.dump(lib, open(CFG, "w"), indent=2, ensure_ascii=False)
    print("aplicado; respaldo en", BAK / args.anim_id)


if __name__ == "__main__":
    main()
