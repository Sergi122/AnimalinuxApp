#!/usr/bin/env bash
# Paso 1: construye build/win-dist/AnimaLinux (PyInstaller). Ejecutar en una consola
# "MSYS2 UCRT64" con GTK4 + PyGObject instalados (ver packaging/windows/README.md).
set -euo pipefail
cd "$(dirname "$0")/../.."
pacman -S --noconfirm --needed \
    mingw-w64-ucrt-x86_64-pyinstaller mingw-w64-ucrt-x86_64-pyinstaller-hooks-contrib
VERSION=$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
python packaging/windows/make_icon.py
rm -rf build/win-dist build/win-work
pyinstaller --noconfirm --clean --distpath build/win-dist --workpath build/win-work \
    packaging/windows/animalinux.spec
echo "Listo: build/win-dist/AnimaLinux. Ahora, en PowerShell:"
echo "  packaging\\windows\\build-installer.ps1 -Version $VERSION"
