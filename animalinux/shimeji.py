"""
Importar mascotas de SHIMEJI (Shimeji-ee, Shijima-Qt, Shijima Android).

Un Shimeji es una carpeta con imágenes sueltas de nombre fijo:

    MiShimeji/
        img/                       (a veces las imágenes están en la raíz)
            shime1.png … shime46.png
        conf/actions.xml           (opcional: qué imágenes forma cada acción)

Shimeji-ee también trae VARIOS personajes juntos:  img/<Personaje>/shime1.png
— en ese caso se importa cada uno como una mascota distinta.

Los números de imagen significan siempre lo mismo (shime1 = de pie, shime2/3 =
pasos, shime4 = cayendo…). Si la carpeta trae su propio actions.xml se usa ése;
si no, la tabla estándar de abajo.

Las imágenes de Shimeji miran a la IZQUIERDA y las de AnimaLinux a la DERECHA
(la app espeja para caminar al otro lado), así que aquí se voltean.
"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from .core import image_processor as importer
from .i18n import tr

# acción de Shimeji -> imágenes (tabla estándar del actions.xml de Shimeji-ee)
STANDARD = {
    "Stand": [1],
    "Walk": [1, 2, 1, 3],
    "Falling": [4],
    "Resisting": [1, 5, 1, 6],
    "Jumping": [22],
    "Sprawl": [21],
    "Sit": [11],
    "SitAndLookUp": [26],
    "ClimbWall": [14, 12, 13],
    "Creep": [20, 21],
    "Bouncing": [18, 19],
}

# pose de AnimaLinux <- acciones de Shimeji (la primera que exista)
POSE_MAP = {
    "default": ["Stand"],
    "walk": ["Walk"],
    "jump": ["Jumping"],
    "fall": ["Falling"],
    "grab": ["Resisting"],      # colgando y pataleando: se ve bien agarrado al cursor
    "sleep": ["Sprawl"],
    "tired": ["Sit"],
    "surprised": ["SitAndLookUp"],
    # poses extra: la app aún no las usa, se guardan para el futuro
    "sit": ["Sit"],
    "climb": ["ClimbWall"],
    "crawl": ["Creep"],
}

_NUM = re.compile(r"shime(\d+)\.png$", re.I)


def _set_dirs(folder):
    """Carpetas que contienen shime1.png (cada una = un personaje)."""
    folder = Path(folder)
    cands = [folder, folder / "img"]
    out = []
    for c in cands:
        if (c / "shime1.png").is_file():
            out.append(c)
    if not out:
        for base in (folder / "img", folder):
            if base.is_dir():
                for d in sorted(base.iterdir()):
                    if d.is_dir() and (d / "shime1.png").is_file():
                        out.append(d)
            if out:
                break
    return out


def is_shimeji(folder):
    return bool(_set_dirs(folder))


def _find_actions_xml(set_dir, root):
    for p in (set_dir / "conf" / "actions.xml", set_dir.parent.parent / "conf" / "actions.xml",
              Path(root) / "conf" / "actions.xml"):
        if p.is_file():
            return p
    return None


def _parse_actions(xml_path):
    """{NombreAcción: [nombres de imagen]} leyendo un actions.xml (sin espacio de
    nombres; Shimeji-ee lo usa en japonés o inglés, aquí basta el atributo Image)."""
    try:
        tree = ET.parse(xml_path)
    except (ET.ParseError, OSError):
        return {}
    acts = {}
    for el in tree.iter():
        if el.tag.split("}")[-1] != "Action":
            continue
        name = el.get("Name")
        imgs = []
        for pose in el.iter():
            img = pose.get("Image")
            if img:
                imgs.append(img.strip().lstrip("/\\").split("/")[-1])
        if name and imgs and name not in acts:
            acts[name] = imgs
    return acts


def _load(set_dir, filename, cache):
    if filename not in cache:
        p = set_dir / filename
        if not p.is_file():
            # algunos packs ponen mayúsculas distintas
            low = {f.name.lower(): f for f in set_dir.iterdir()}
            p = low.get(filename.lower())
        im = None
        if p is not None:
            try:
                im = Image.open(p).convert("RGBA")
                im = im.transpose(Image.FLIP_LEFT_RIGHT)       # izquierda -> derecha
                im = importer._clamp_size(im)
            except Exception:  # noqa: BLE001
                im = None
        cache[filename] = im
    return cache[filename]


def scan_set(set_dir, root=None):
    """Devuelve {pose: [frames RGBA]} de un personaje Shimeji."""
    set_dir = Path(set_dir)
    xml = _find_actions_xml(set_dir, root or set_dir)
    custom = _parse_actions(xml) if xml else {}
    cache = {}
    poses = {}
    for pose, actions in POSE_MAP.items():
        for act in actions:
            names = custom.get(act) or [f"shime{n}.png" for n in STANDARD.get(act, [])]
            frames = [f for f in (_load(set_dir, n, cache) for n in names) if f is not None]
            if frames:
                if len(frames) == 1:          # una sola imagen: se repite (Shimeji usa poses
                    frames = frames * 2       # fijas para saltar/caer; aquí se anima igual)
                poses[pose] = frames
                break
    return poses


def _save_pet(library, poses, name, fps):
    aid = library.new_id()
    fd = library.frames_dir(aid)
    fd.mkdir(parents=True, exist_ok=True)
    # mismo lienzo para TODAS las poses: así no salta al cambiar de pose
    w = max(f.width for fr in poses.values() for f in fr)
    h = max(f.height for fr in poses.values() for f in fr)
    for pose, frames in poses.items():
        target = fd if pose == "default" else fd / pose
        target.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(frames):
            if f.size != (w, h):
                c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                c.alpha_composite(f, ((w - f.width) // 2, h - f.height))
                f = c
            f.save(target / f"frame_{i:04d}.png")
        importer.ensure_flipped(target)
    n = len(list(fd.glob("frame_*.png")))
    library.add(aid, name, n, w, h)
    library.update(aid, fps=fps, poses=list(poses), mode="life", source="shimeji")
    return aid


def import_shimeji(library, folder, fps=8, name=None):
    """Importa todos los personajes Shimeji de la carpeta.
    Devuelve [(anim_id, nombre)]."""
    folder = Path(folder)
    sets = _set_dirs(folder)
    if not sets:
        raise RuntimeError(tr("No es un Shimeji: no encontré shime1.png."))
    out = []
    for s in sets:
        poses = scan_set(s, folder)
        if "default" not in poses:
            continue
        if s == folder or s == folder / "img":
            nm = name or folder.name
        else:
            nm = s.name
        if nm.lower() == "img":                 # Pack/<Personaje>/img/shime1.png
            nm = (s.parent if s.name.lower() == "img" else folder.parent).name
        out.append((_save_pet(library, poses, nm, fps), nm))
    if not out:
        raise RuntimeError(tr("No es un Shimeji: no encontré shime1.png."))
    return out
