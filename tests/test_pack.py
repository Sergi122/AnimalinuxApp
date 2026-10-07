"""Tests para animalinux/pack.py: export/import de .alpack y protección zip-slip."""
import json
import zipfile

import pytest
from PIL import Image

from animalinux import pack


def _write_frames(frames_dir, count=3, size=(20, 20)):
    frames_dir.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        Image.new("RGBA", size, (255, 0, 0, 255)).save(frames_dir / f"frame_{i:04d}.png")


def _make_anim(library, name="Theresa", poses=("default",), frame_count=3):
    anim_id = library.new_id()
    frames_dir = library.frames_dir(anim_id)
    _write_frames(frames_dir, frame_count)
    for pose in poses:
        if pose != "default":
            _write_frames(frames_dir / pose, frame_count)
    library.add(anim_id, name, frame_count, 20, 20)
    library.update(anim_id, author="tester", fps=24)
    return anim_id


class TestExportPack:
    def test_export_pack_raises_for_unknown_animation(self, library, tmp_path):
        with pytest.raises(RuntimeError):
            pack.export_pack(library, "no-existe", tmp_path / "out.alpack")

    def test_export_pack_adds_alpack_suffix(self, library, tmp_path):
        anim_id = _make_anim(library)
        dest = pack.export_pack(library, anim_id, tmp_path / "out.zip")
        assert dest.suffix == ".alpack"
        assert dest.exists()

    def test_export_pack_contains_mascot_json_and_frames(self, library, tmp_path):
        anim_id = _make_anim(library)
        dest = pack.export_pack(library, anim_id, tmp_path / "out.alpack")

        with zipfile.ZipFile(dest) as z:
            names = z.namelist()
            assert "mascot.json" in names
            meta = json.loads(z.read("mascot.json"))
            assert meta["format"] == "animalinux-pack"
            assert meta["name"] == "Theresa"
            assert meta["author"] == "tester"
            assert meta["fps"] == 24
            assert meta["poses"] == ["default"]
            assert "poses/default/frame_0000.png" in names

    def test_export_pack_discovers_extra_poses(self, library, tmp_path):
        anim_id = _make_anim(library, poses=("default", "walk"))
        dest = pack.export_pack(library, anim_id, tmp_path / "out.alpack")

        with zipfile.ZipFile(dest) as z:
            meta = json.loads(z.read("mascot.json"))
            assert set(meta["poses"]) == {"default", "walk"}
            assert "poses/walk/frame_0000.png" in z.namelist()


class TestImportPack:
    def test_roundtrip_export_then_import(self, library, tmp_path):
        anim_id = _make_anim(library, name="Nube", poses=("default", "walk"))
        alpack = pack.export_pack(library, anim_id, tmp_path / "nube.alpack")

        new_id = pack.import_pack(library, alpack)

        assert new_id != anim_id
        assert new_id in library.animations
        entry = library.animations[new_id]
        assert entry["name"] == "Nube"
        assert entry["author"] == "tester"
        assert entry["fps"] == 24
        assert set(entry["poses"]) == {"default", "walk"}

        frames_dir = library.frames_dir(new_id)
        assert (frames_dir / "frame_0000.png").exists()
        assert (frames_dir / "walk" / "frame_0000.png").exists()

    def test_import_generates_flipped_frames(self, library, tmp_path):
        anim_id = _make_anim(library)
        alpack = pack.export_pack(library, anim_id, tmp_path / "out.alpack")

        new_id = pack.import_pack(library, alpack)
        frames_dir = library.frames_dir(new_id)
        assert (frames_dir / "flip_0000.png").exists()

    def test_import_rejects_oversized_pack(self, library, tmp_path, monkeypatch):
        anim_id = _make_anim(library)
        alpack = pack.export_pack(library, anim_id, tmp_path / "out.alpack")
        monkeypatch.setattr(pack, "MAX_PACK_BYTES", 1)

        with pytest.raises(RuntimeError, match="grande"):
            pack.import_pack(library, alpack)

    def test_import_rejects_wrong_format_magic(self, library, tmp_path):
        bad = tmp_path / "bad.alpack"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("mascot.json", json.dumps({"format": "other-thing"}))

        with pytest.raises(RuntimeError, match="válido"):
            pack.import_pack(library, bad)

    def test_import_rejects_missing_mascot_json(self, library, tmp_path):
        bad = tmp_path / "bad.alpack"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("poses/default/frame_0000.png", b"not a real png")

        with pytest.raises(RuntimeError, match="mascot.json"):
            pack.import_pack(library, bad)


class TestValidateZipSecurity:
    def test_rejects_relative_traversal_path(self, tmp_path):
        evil = tmp_path / "evil.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("mascot.json", "{}")
            z.writestr("../../etc/passwd", "pwned")

        with zipfile.ZipFile(evil) as z, pytest.raises(RuntimeError, match="inseguro"):
            pack._validate_zip(z)

    def test_rejects_absolute_path(self, tmp_path):
        evil = tmp_path / "evil.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("mascot.json", "{}")
            z.writestr("/etc/passwd", "pwned")

        with zipfile.ZipFile(evil) as z, pytest.raises(RuntimeError, match="inseguro"):
            pack._validate_zip(z)

    def test_accepts_safe_paths(self, tmp_path):
        safe = tmp_path / "safe.zip"
        with zipfile.ZipFile(safe, "w") as z:
            z.writestr("mascot.json", "{}")
            z.writestr("poses/default/frame_0000.png", b"data")

        with zipfile.ZipFile(safe) as z:
            pack._validate_zip(z)  # no debe lanzar


def _evil_pack(path, meta_extra=None, members=None):
    """Pack con mascot.json válido + las alteraciones que se quieran probar."""
    import io
    png = io.BytesIO()
    Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(png, "PNG")
    meta = {"format": pack.MAGIC, "version": 1, "name": "x", "poses": ["default"]}
    meta.update(meta_extra or {})
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mascot.json", json.dumps(meta))
        for name, data in (members or {"poses/default/frame_0000.png": png.getvalue()}).items():
            z.writestr(name, data)
    return path


class TestPackHardening:
    """Un .alpack viene de internet: nada de su contenido debe poder escapar de
    la carpeta de la librería ni agotar la memoria (sobre todo en Windows)."""

    @pytest.mark.parametrize("pose", ["C:", "..", "a/b", "a\\b", "CON", "nul", "", "x" * 80, "../x", "/etc"])
    def test_rejects_unsafe_pose_names(self, library, tmp_path, pose):
        p = _evil_pack(tmp_path / "e.alpack", {"poses": ["default", pose]})
        with pytest.raises(RuntimeError):
            pack.import_pack(library, p)
        assert library.animations == {}

    def test_rejects_non_list_poses(self, library, tmp_path):
        p = _evil_pack(tmp_path / "e.alpack", {"poses": "default"})
        with pytest.raises(RuntimeError):
            pack.import_pack(library, p)

    @pytest.mark.parametrize("name", ["C:x/frame.png", "poses\\default\\a.png", "/abs.png", "a/../../b.png"])
    def test_rejects_unsafe_member_names(self, library, tmp_path, name):
        p = _evil_pack(tmp_path / "e.alpack", members={name: b"x"})
        with pytest.raises(RuntimeError):
            pack.import_pack(library, p)

    def test_rejects_oversized_member(self, library, tmp_path, monkeypatch):
        monkeypatch.setattr(pack, "MAX_MEMBER_BYTES", 10)
        p = _evil_pack(tmp_path / "e.alpack")
        with pytest.raises(RuntimeError):
            pack.import_pack(library, p)

    def test_rejects_png_with_huge_dimensions(self, library, tmp_path, monkeypatch):
        monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10)   # el PNG de 8x8 = 64 px
        p = _evil_pack(tmp_path / "e.alpack")
        with pytest.raises(RuntimeError):
            pack.import_pack(library, p)

    def test_rejects_non_image_frame(self, library, tmp_path):
        p = _evil_pack(tmp_path / "e.alpack", members={"poses/default/frame_0000.png": b"no soy un png"})
        with pytest.raises(RuntimeError):
            pack.import_pack(library, p)

    def test_sanitizes_metadata(self, library, tmp_path):
        p = _evil_pack(tmp_path / "e.alpack", {"name": "N" * 500, "author": 123, "fps": "mucho"})
        aid = pack.import_pack(library, p)
        a = library.animations[aid]
        assert len(a["name"]) <= 60 and a["author"] == "" and a["fps"] == 12

    def test_fps_is_clamped(self, library, tmp_path):
        aid = pack.import_pack(library, _evil_pack(tmp_path / "e.alpack", {"fps": 100000}))
        assert library.animations[aid]["fps"] == 60
