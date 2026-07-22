"""Fixtures compartidas: aíslan las rutas XDG (paths.py) en un directorio temporal
para que ningún test toque ~/.local/share o ~/.config del usuario real."""
import pytest

from animalinux import paths
from animalinux.core.library import Library


@pytest.fixture
def xdg_tmp(tmp_path, monkeypatch):
    """Redirige las constantes de paths.py a subcarpetas de tmp_path."""
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    animations_dir = data_dir / "animations"
    library_file = config_dir / "library.json"

    monkeypatch.setattr(paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(paths, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(paths, "ANIMATIONS_DIR", animations_dir)
    monkeypatch.setattr(paths, "LIBRARY_FILE", library_file)
    return tmp_path


@pytest.fixture
def library(xdg_tmp):
    """Library real (no un mock) apuntando al filesystem temporal aislado."""
    return Library()
