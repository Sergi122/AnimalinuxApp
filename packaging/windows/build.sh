#!/usr/bin/env bash
# Paso 1: construye build/win-dist/AnimaWin (PyInstaller). Ejecutar en una consola
# "MSYS2 UCRT64" con GTK4 + PyGObject instalados (ver packaging/windows/README.md).
#
# Todo lo que la app usa va DENTRO del instalador (el usuario no tiene que
# instalar nada): onnxruntime (recorte IA), Vosk + sounddevice (voz), ffmpeg
# y ffprobe (vídeos/MP4/stickers) y mpv (sonido del editor). Lo que no se
# puede empaquetar (Ollama, modelos) se baja con un clic desde la app.
set -euo pipefail
cd "$(dirname "$0")/../.."
P=mingw-w64-ucrt-x86_64
# MSYS2 no admite actualizaciones a medias: con paquetes viejos, el ffmpeg
# nuevo pedía libz-1.dll y la zlib instalada solo traía zlib1.dll (error
# 0xc0000135 en Windows). Se actualiza todo antes (2 pasadas: núcleo y resto).
pacman -Syuu --noconfirm || true
pacman -Syuu --noconfirm
pacman -S --noconfirm --needed \
    $P-pyinstaller $P-pyinstaller-hooks-contrib $P-python-pip \
    $P-python-sounddevice $P-portaudio $P-python-cffi \
    $P-python-requests $P-python-tqdm $P-ffmpeg $P-mpv unzip

# Vosk: su wheel oficial de Windows trae libvosk.dll compilada con MinGW,
# compatible con este Python, pero pip no la acepta por la etiqueta de
# plataforma: se baja con huella fija y se descomprime a mano.
SITE=$(python -c "import sysconfig;print(sysconfig.get_paths()['purelib'])")
mkdir -p build/wheels
cat > build/wheels/req.txt <<'R'
vosk==0.3.45 --hash=sha256:6994ddc68556c7e5730c3b6f6bad13320e3519b13ce3ed2aa25a86724e7c10ac
R
python -m pip download --require-hashes --no-deps --only-binary=:all: --platform win_amd64 \
    --python-version 3.12 -r build/wheels/req.txt -d build/wheels
unzip -o -q build/wheels/vosk-0.3.45-py3-none-win_amd64.whl -d "$SITE"
python packaging/windows/patch_vosk.py "$SITE/vosk"     # DLL de msvcrt aisladas de las de MSYS2
cat > build/wheels/req2.txt <<'R'
srt==3.5.3 --hash=sha256:4884315043a4f0740fd1f878ed6caa376ac06d70e135f306a6dc44632eed0cc0
R
python -c 'import srt' 2>/dev/null || \
    python -m pip install --require-hashes --no-deps --break-system-packages -r build/wheels/req2.txt
# onnxruntime: el paquete de MSYS2 viene sin su módulo de Python, así que se
# usa la DLL oficial de Microsoft por su API en C (animalinux/core/ort_capi.py)
ORT=onnxruntime-win-x64-1.31.1
if [ ! -f build/ort/onnxruntime.dll ]; then
    curl -fL -o build/wheels/$ORT.zip https://github.com/microsoft/onnxruntime/releases/download/v1.31.1/$ORT.zip
    echo "5869e26bb25314375f2d5ef1877e3ea06b1543d6c710e6e4a1ec2f7177ab4b2c  build/wheels/$ORT.zip" | sha256sum -c
    rm -rf build/ort && mkdir -p build/ort
    unzip -j -o -q build/wheels/$ORT.zip "$ORT/lib/onnxruntime.dll" "$ORT/lib/onnxruntime_providers_shared.dll" "$ORT/LICENSE" -d build/ort
fi
ANIMALINUX_ORT_LIB="$(cygpath -w "$PWD/build/ort/onnxruntime.dll")" python -c "
from animalinux.core import ort_capi; ort_capi.api(); import vosk, sounddevice
print('onnxruntime (C) OK · vosk OK · sounddevice', sounddevice.__version__)"

VERSION=$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
python packaging/windows/make_logo.py
rm -rf build/win-dist build/win-work
pyinstaller --noconfirm --clean --distpath build/win-dist --workpath build/win-work \
    packaging/windows/animalinux.spec
# ffmpeg, ffprobe y mpv con sus DLL → AnimaWin/tools (run_animalinux.py los pone en el PATH)
python packaging/windows/collect_tools.py build/win-dist/AnimaWin/tools ffmpeg ffprobe mpv
# prueba real: arrancan solos, sin MSYS2 en el PATH (como en el equipo del usuario)
(cd build/win-dist/AnimaWin/tools && PATH=/c/Windows/System32 ./ffmpeg.exe -version | head -1 \
    && PATH=/c/Windows/System32 ./ffprobe.exe -version | head -1 \
    && PATH=/c/Windows/System32 ./mpv.exe --version | head -1)
echo "Listo: build/win-dist/AnimaWin. Ahora, en PowerShell:"
echo "  packaging\\windows\\build-installer.ps1 -Version $VERSION"
