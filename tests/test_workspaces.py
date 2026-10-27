"""Escritorios: todas las mascotas (con vida y sin vida) se ven en todos los
escritorios; la fijación vieja de las sin vida (0.7.0–0.8.1.4) se borra."""
import json

from animalinux.core import library as lib_mod
from animalinux.core import mascot_manager as mm


def test_manager_no_longer_pins_to_a_desktop():
    for name in ("start_workspace_watch", "_on_workspace", "_pin_here", "_apply_workspace"):
        assert not hasattr(mm.MascotManager, name), name


def test_old_desktop_pin_is_removed_on_load(tmp_path, monkeypatch):
    f = tmp_path / "library.json"
    f.write_text(json.dumps({"config": {}, "animations": {
        "g": {"id": "g", "mode": "gif", "workspace": "hypr:4"},
        "l": {"id": "l", "mode": "life"}}}))
    monkeypatch.setattr(lib_mod.paths, "LIBRARY_FILE", f)
    monkeypatch.setattr(lib_mod.paths, "ensure_dirs", lambda: None)
    lib = lib_mod.Library()
    lib.load()
    assert "workspace" not in lib.animations["g"]
    assert "workspace" not in json.loads(f.read_text())["animations"]["g"]   # guardado
