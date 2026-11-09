"""Importar mascotas de Shimeji (shime1..46.png + actions.xml opcional)."""
from pathlib import Path

import pytest
from PIL import Image

from animalinux import folderimport, shimeji


def _png(path, color, mark_left=True):
    """128x128 transparente con un cuerpo y una 'nariz' a la IZQUIERDA (Shimeji mira
    a la izquierda); así se puede comprobar que el importador la voltea."""
    im = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    for y in range(60, 128):
        for x in range(44, 84):
            im.putpixel((x, y), color)
    if mark_left:
        for y in range(80, 88):
            for x in range(30, 44):
                im.putpixel((x, y), (255, 0, 0, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)


def _make_set(d, n=46):
    for i in range(1, n + 1):
        _png(d / f"shime{i}.png", (i * 5 % 256, 100, 200, 255))


def _red_side(path):
    im = Image.open(path).convert("RGBA")
    left = sum(1 for x in range(0, 64) for y in range(80, 88) if im.getpixel((x, y)) == (255, 0, 0, 255))
    right = sum(1 for x in range(64, 128) for y in range(80, 88) if im.getpixel((x, y)) == (255, 0, 0, 255))
    return "left" if left > right else "right"


def test_detecta_shimeji_en_img_y_en_raiz(tmp_path):
    _make_set(tmp_path / "A" / "img")
    _make_set(tmp_path / "B")
    (tmp_path / "C").mkdir()
    assert shimeji.is_shimeji(tmp_path / "A")
    assert shimeji.is_shimeji(tmp_path / "B")
    assert not shimeji.is_shimeji(tmp_path / "C")


def test_importa_poses_estandar_y_voltea(library, tmp_path):
    _make_set(tmp_path / "Neko" / "img")
    aid, probs = folderimport.import_folder(library, tmp_path / "Neko")
    anim = library.animations[aid]
    assert anim["name"] == "Neko"
    assert anim["mode"] == "life" and anim["source"] == "shimeji"
    # las 3 obligatorias de la app + las que usa el modo Vida
    for p in ("default", "walk", "jump", "fall", "grab", "sleep", "tired", "sit", "climb"):
        assert p in anim["poses"], p
    fd = library.frames_dir(aid)
    assert len(list((fd / "walk").glob("frame_*.png"))) == 4          # 1-2-1-3
    assert len(list((fd / "jump").glob("frame_*.png"))) >= 2          # 1 imagen se repite
    # mira a la derecha como las mascotas de AnimaLinux; flip_ mira a la izquierda
    assert _red_side(fd / "frame_0000.png") == "right"
    assert _red_side(fd / "flip_0000.png") == "left"
    assert _red_side(fd / "walk" / "frame_0001.png") == "right"
    assert not probs


def test_usa_actions_xml_propio(library, tmp_path):
    root = tmp_path / "Custom"
    _make_set(root / "img", n=46)
    _png(root / "img" / "paso_a.png", (0, 255, 0, 255))
    _png(root / "img" / "paso_b.png", (0, 0, 255, 255))
    (root / "conf").mkdir()
    (root / "conf" / "actions.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Mascot xmlns="http://www.group-finity.com/Mascot"><ActionList>'
        '<Action Name="Walk" Type="Move"><Animation>'
        '<Pose Image="/paso_a.png" ImageAnchor="64,128" Velocity="-2,0" Duration="6"/>'
        '<Pose Image="/paso_b.png" ImageAnchor="64,128" Velocity="-2,0" Duration="6"/>'
        '</Animation></Action></ActionList></Mascot>', encoding="utf-8")
    aid, _ = folderimport.import_folder(library, root)
    walk = sorted((library.frames_dir(aid) / "walk").glob("frame_*.png"))
    assert len(walk) == 2
    assert Image.open(walk[0]).getpixel((64, 100)) == (0, 255, 0, 255)


def test_pack_con_varios_personajes(library, tmp_path):
    _make_set(tmp_path / "Pack" / "img" / "Uno")
    _make_set(tmp_path / "Pack" / "img" / "Dos")
    aid, probs = folderimport.import_folder(library, tmp_path / "Pack")
    names = sorted(a["name"] for a in library.animations.values())
    assert names == ["Dos", "Uno"]
    assert "_general" in probs and "2" in probs["_general"][0]


def test_nombre_cuando_la_carpeta_se_llama_img(library, tmp_path):
    _make_set(tmp_path / "Neuro" / "img")
    aid, _ = folderimport.import_folder(library, tmp_path / "Neuro" / "img")
    assert library.animations[aid]["name"] == "Neuro"


def test_faltan_imagenes_no_rompe(library, tmp_path):
    """Un Shimeji incompleto (solo de pie y caminar) se importa igual."""
    d = tmp_path / "Mini"
    for i in (1, 2, 3):
        _png(d / f"shime{i}.png", (50, 50, 50, 255))
    aid, _ = folderimport.import_folder(library, d)
    poses = library.animations[aid]["poses"]
    assert "default" in poses and "walk" in poses
    assert "jump" not in poses and "fall" not in poses   # la app usa sus respaldos


def test_mismo_lienzo_en_todas_las_poses(library, tmp_path):
    d = tmp_path / "Grande"
    _make_set(d)
    Image.new("RGBA", (160, 150), (9, 9, 9, 255)).save(d / "shime22.png")   # salto más grande
    aid, _ = folderimport.import_folder(library, d)
    fd = library.frames_dir(aid)
    sizes = {Image.open(p).size for p in fd.rglob("frame_*.png")}
    assert sizes == {(160, 150)}


def test_carpeta_normal_sigue_igual(library, tmp_path):
    """Las carpetas con poses de AnimaLinux no se confunden con Shimeji."""
    d = tmp_path / "Propia"
    for pose in ("default", "walk"):
        for i in range(2):
            _png(d / pose / f"frame_{i:04d}.png", (1, 2, 3, 255))
    aid, _ = folderimport.import_folder(library, d)
    assert library.animations[aid].get("source") != "shimeji"


REAL = Path("/tmp/claude-1000/-home-maomao/c7799f1d-c173-4d92-be5e-d1f9430c5080/scratchpad/shimeji_real/ShimejiEE")


@pytest.mark.skipif(not REAL.exists(), reason="pack real de Shimeji-ee no descargado")
def test_pack_real_shimeji_ee(library):
    aid, probs = folderimport.import_folder(library, REAL)
    names = sorted(a["name"] for a in library.animations.values())
    assert names == ["KuroShimeji", "Shimeji"]
    for a in library.animations.values():
        assert {"default", "walk", "jump", "fall", "grab"} <= set(a["poses"])
