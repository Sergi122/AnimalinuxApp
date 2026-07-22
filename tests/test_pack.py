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
