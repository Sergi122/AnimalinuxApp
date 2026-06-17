"""
Gestión de proyectos AnimaLinux (.alproj).
Los proyectos se guardan en ~/Documents/AnimaLinux/projects/
"""
import os
from datetime import datetime
from pathlib import Path

# Carpeta raíz de proyectos
PROJECTS_DIR = Path.home() / "Documents" / "AnimaLinux" / "projects"


def ensure_dir() -> Path:
    """Crea la carpeta de proyectos si no existe."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return PROJECTS_DIR


def list_projects() -> list[dict]:
    """Devuelve lista de proyectos ordenados por fecha de modificación (más reciente primero)."""
    ensure_dir()
    projects = []
    for p in sorted(PROJECTS_DIR.glob("*.alproj"),
                    key=lambda f: f.stat().st_mtime, reverse=True):
        stat = p.stat()
        projects.append({
            "path":     str(p),
            "name":     p.stem,
            "size_kb":  stat.st_size // 1024,
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d  %H:%M"),
        })
    return projects


def default_save_path(name: str = "proyecto") -> str:
    """Ruta por defecto para guardar un nuevo proyecto."""
    ensure_dir()
    base = PROJECTS_DIR / f"{name}.alproj"
    if not base.exists():
        return str(base)
    i = 2
    while True:
        candidate = PROJECTS_DIR / f"{name}_{i}.alproj"
        if not candidate.exists():
            return str(candidate)
        i += 1


def open_folder():
    """Abre la carpeta de proyectos en el explorador de archivos."""
    ensure_dir()
    import subprocess
    for cmd in ("xdg-open", "dolphin", "nautilus", "thunar", "pcmanfm"):
        try:
            subprocess.Popen([cmd, str(PROJECTS_DIR)])
            return
        except FileNotFoundError:
            continue
