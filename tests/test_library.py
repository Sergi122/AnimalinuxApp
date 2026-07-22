"""Tests para animalinux/core/library.py: persistencia en library.json."""
import json

from animalinux import paths
from animalinux.core.library import Library


class TestLibraryPersistence:
    def test_add_creates_entry_and_persists_to_disk(self, library):
        anim_id = library.new_id()
        library.add(anim_id, "Theresa", 10, 200, 260)

        assert anim_id in library.animations
        assert paths.LIBRARY_FILE.exists()

        reloaded = Library()
        assert anim_id in reloaded.animations
        assert reloaded.animations[anim_id]["name"] == "Theresa"

    def test_update_merges_fields_without_dropping_others(self, library):
        anim_id = library.new_id()
        library.add(anim_id, "Theresa", 10, 200, 260)

        library.update(anim_id, fps=30)

        assert library.animations[anim_id]["fps"] == 30
        assert library.animations[anim_id]["name"] == "Theresa"

    def test_update_on_unknown_id_is_a_noop(self, library):
        library.update("no-existe", fps=30)  # no debe lanzar
        assert "no-existe" not in library.animations

    def test_remove_deletes_entry_and_frame_files(self, library):
        anim_id = library.new_id()
        frames_dir = library.frames_dir(anim_id)
        frames_dir.mkdir(parents=True)
        (frames_dir / "frame_0000.png").write_bytes(b"fake")
        library.add(anim_id, "Theresa", 1, 20, 20)

        library.remove(anim_id)

        assert anim_id not in library.animations
        assert not frames_dir.exists()

    def test_active_returns_only_on_desktop_animations(self, library):
        shown = library.new_id()
        hidden = library.new_id()
        library.add(shown, "Visible", 1, 20, 20)
        library.add(hidden, "Oculta", 1, 20, 20)
        library.update(shown, on_desktop=True)

        active_ids = [a["id"] for a in library.active()]
        assert active_ids == [shown]

    def test_load_recovers_from_corrupt_json(self, xdg_tmp):
        paths.ensure_dirs()
        paths.LIBRARY_FILE.write_text("{not valid json")

        lib = Library()

        assert lib.animations == {}

    def test_save_writes_atomically_no_leftover_tmp_file(self, library):
        anim_id = library.new_id()
        library.add(anim_id, "Theresa", 1, 20, 20)

        tmp_file = paths.LIBRARY_FILE.with_suffix(".json.tmp")
        assert not tmp_file.exists()
        data = json.loads(paths.LIBRARY_FILE.read_text())
        assert anim_id in data["animations"]
