"""
Importar una mascota de VIDA desde una CARPETA.

Formato esperado:

    MiMascota/                     <- la carpeta = nombre de la mascota
        default/                   <- OBLIGATORIA — pose base
            frame_0000.png ...
        idle/                      <- Respirar / quieta
        walk/                      <- Caminar
        greet/                     <- Saludar al acercarse
        jump/                      <- Saltar
        angry/                     <- Enojo
        grab/                      <- Agarra el ratón (tras 4 clicks)

Cada subcarpeta = una acción (pose). Acepta PNG/WebP/GIF por frame.
Solo 'default' es obligatoria; el resto son opcionales.
Al importar, VALIDA cada pose; si algo está mal, devuelve los problemas.
"""
from pathlib import Path

from PIL import Image

from . import importer

KNOWN_POSES = ["default", "idle", "walk", "greet", "jump", "angry", "grab"]
IMG_EXT = (".png", ".webp", ".gif", ".jpg", ".jpeg", ".apng")


def _load_pose_frames(folder):
    """Carga los frames de una subcarpeta (ordenados, como RGBA)."""
    files = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() in IMG_EXT)
    frames = []
    for f in files:
        try:
            im = Image.open(f).convert("RGBA")
            frames.append(importer._clamp_size(im))
        except Exception:  # noqa: BLE001
            pass
    return frames


def scan_folder(folder):
    """Devuelve {pose: [frames]} a partir de la estructura de carpetas."""
    folder = Path(folder)
    poses = {}
    subdirs = [d for d in folder.iterdir() if d.is_dir()]
    if subdirs:
        for d in subdirs:
            name = d.name.lower()
            frames = _load_pose_frames(d)
            if frames:
                poses[name if name in KNOWN_POSES else d.name] = frames
    else:
        # sin subcarpetas: todas las imágenes sueltas = pose 'default'
        frames = _load_pose_frames(folder)
        if frames:
            poses["default"] = frames
    return poses


def validate_poses(poses):
    """Revisa cada pose. Devuelve {pose: [avisos]} (vacío = todo bien)."""
    problemas = {}
    if "default" not in poses:
        problemas["_general"] = [
            "Falta la pose 'default' (la base de la mascota)."]
    for pose, frames in poses.items():
        avisos = []
        if len(frames) < 1:
            avisos.append("No tiene cuadros.")
        sizes = {f.size for f in frames}
        if len(sizes) > 1:
            avisos.append("Cuadros de distinto tamaño (se uniformarán, pero "
                          "puede verse un salto).")
        if pose in ("walk", "greet", "angry", "jump", "grab") and len(frames) < 2:
            avisos.append("Una animación necesita 2+ cuadros para moverse.")
        # pies desalineados
        bottoms = [f.getbbox()[3] for f in frames if f.getbbox()]
        if bottoms and (max(bottoms) - min(bottoms)) > max(4, frames[0].height * 0.08):
            avisos.append("Los pies se desalinean entre cuadros (puede patinar).")
        if avisos:
            problemas[pose] = avisos
    return problemas


def import_folder(library, folder, fps=8, name=None):
    """
    Importa la carpeta como una mascota de Vida con varias poses.
    Devuelve (anim_id, problemas). Si hay problemas, igual la crea pero los
    reporta para que el usuario edite.
    """
    folder = Path(folder)
    poses = scan_folder(folder)
    if not poses:
        raise RuntimeError("La carpeta no tiene imágenes ni subcarpetas válidas.")

    problemas = validate_poses(poses)

    # si no hay 'default', usar la primera pose como default
    if "default" not in poses:
        first = next(iter(poses))
        poses["default"] = poses[first]

    aid = library.new_id()
    fd = library.frames_dir(aid)
    fd.mkdir(parents=True, exist_ok=True)

    saved = []
    for pose, frames in poses.items():
        # uniformar tamaño por pose
        w = max(f.width for f in frames)
        h = max(f.height for f in frames)
        target = fd if pose == "default" else fd / pose
        target.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(frames):
            if f.size != (w, h):
                c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                c.alpha_composite(f, ((w - f.width) // 2, h - f.height))
                f = c
            f.save(target / f"frame_{i:04d}.png")
        importer.ensure_flipped(target)
        saved.append(pose)

    first = sorted(fd.glob("frame_*.png"))
    bw, bh = Image.open(first[0]).size if first else (100, 100)
    library.add(aid, name or folder.name, len(first), bw, bh)
    library.update(aid, fps=fps, poses=saved, mode="life")
    return aid, problemas
