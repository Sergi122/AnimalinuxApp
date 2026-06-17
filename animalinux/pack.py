"""
Formato de PACK compartible (.alpack) — el corazón de la comunidad.

Un .alpack es un .zip con esta estructura:

    mascot.json
    poses/
        default/        (obligatoria; se usa para todo si no hay más)
            frame_0000.png ...
        walk/  idle/  greet/  jump/   (opcionales)
            frame_0000.png ...

mascot.json:
    {
      "format": "animalinux-pack",
      "version": 1,
      "name": "Theresa",
      "author": "tu_nombre",
      "fps": 12,
      "poses": ["default", "walk", "idle"]
    }

Cualquiera puede crear un pack (un solo gif basta: se vuelve la pose 'default')
y compartirlo. Eso es lo que hizo famoso a Shimeji.
"""
import json
import shutil
import zipfile
from pathlib import Path

from . import importer

POSE_NAMES = ["default", "walk", "idle", "greet", "jump"]
MAGIC = "animalinux-pack"
MAX_PACK_BYTES = 200 * 1024 * 1024   # 200 MB: tope de seguridad al importar


# ----------------------------------------------------------------------
# EXPORTAR
# ----------------------------------------------------------------------
def export_pack(library, anim_id, dest_path):
    """Crea un .alpack a partir de una animación de la librería."""
    anim = library.animations.get(anim_id)
    if not anim:
        raise RuntimeError("Esa animación no existe.")
    frames_dir = library.frames_dir(anim_id)
    dest_path = Path(dest_path)
    if dest_path.suffix != ".alpack":
        dest_path = dest_path.with_suffix(".alpack")

    poses_found = _discover_poses(frames_dir)
    meta = {
        "format": MAGIC,
        "version": 1,
        "name": anim.get("name", "Mascota"),
        "author": anim.get("author", ""),
        "fps": anim.get("fps", 12),
        "poses": list(poses_found.keys()),
    }

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mascot.json", json.dumps(meta, indent=2, ensure_ascii=False))
        for pose, files in poses_found.items():
            for f in files:
                z.write(f, f"poses/{pose}/{f.name}")
    return dest_path


def _discover_poses(frames_dir):
    """Devuelve {pose: [archivos frame_*.png]} mirando carpeta plana + subcarpetas."""
    frames_dir = Path(frames_dir)
    poses = {}
    # capa plana = pose 'default'
    flat = sorted(frames_dir.glob("frame_*.png"))
    if flat:
        poses["default"] = flat
    # subcarpetas = poses extra
    for sub in sorted(p for p in frames_dir.iterdir() if p.is_dir()):
        files = sorted(sub.glob("frame_*.png"))
        if files:
            poses[sub.name] = files
    return poses


# ----------------------------------------------------------------------
# IMPORTAR
# ----------------------------------------------------------------------
def import_pack(library, pack_path):
    """Instala un .alpack en la librería. Devuelve el id de la nueva animación."""
    pack_path = Path(pack_path)
    if pack_path.stat().st_size > MAX_PACK_BYTES:
        raise RuntimeError("El pack es demasiado grande (límite 200 MB).")

    with zipfile.ZipFile(pack_path) as z:
        _validate_zip(z)
        meta = json.loads(z.read("mascot.json"))
        if meta.get("format") != MAGIC:
            raise RuntimeError("Ese archivo no es un pack de AnimaLinux válido.")

        anim_id = library.new_id()
        frames_dir = library.frames_dir(anim_id)
        frames_dir.mkdir(parents=True, exist_ok=True)

        # extraer cada pose
        poses = meta.get("poses", ["default"])
        for pose in poses:
            members = [n for n in z.namelist()
                       if n.startswith(f"poses/{pose}/") and n.endswith(".png")]
            if not members:
                continue
            if pose == "default":
                target = frames_dir            # 'default' va en la capa plana
            else:
                target = frames_dir / pose
                target.mkdir(parents=True, exist_ok=True)
            for i, name in enumerate(sorted(members)):
                data = z.read(name)
                (target / f"frame_{i:04d}.png").write_bytes(data)

    # generar espejados de cada pose (para mirar a la izquierda en modo Vida)
    importer.ensure_flipped(frames_dir)
    for sub in [p for p in frames_dir.iterdir() if p.is_dir()]:
        importer.ensure_flipped(sub)

    # medir tamaño del primer frame default
    first = sorted(frames_dir.glob("frame_*.png"))
    from PIL import Image
    w, h = Image.open(first[0]).size if first else (100, 100)
    fc = len(first)

    library.add(anim_id, meta.get("name", "Mascota"), fc, w, h)
    library.update(anim_id, fps=meta.get("fps", 12),
                   author=meta.get("author", ""),
                   poses=poses)
    return anim_id


def _validate_zip(z):
    """Protege contra Zip Slip (rutas tipo ../) y miembros sospechosos."""
    for name in z.namelist():
        p = Path(name)
        if p.is_absolute() or ".." in p.parts:
            raise RuntimeError("Pack inseguro: contiene rutas no permitidas.")
    if "mascot.json" not in z.namelist():
        raise RuntimeError("El pack no tiene mascot.json.")
