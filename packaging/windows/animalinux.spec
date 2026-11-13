# PyInstaller: construye build/win-dist/AnimaWin (ver build.sh).
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, '..', '..'))
sys.path.insert(0, ROOT)

import glob  # noqa: E402

from PyInstaller.utils.hooks import collect_data_files, collect_submodules  # noqa: E402

# GTK4 y sus typelibs: sin estos imports ocultos y las versiones explícitas
# PyInstaller no incluye los .typelib y la app falla con "Namespace Gtk not available".
GI_MODULES = ['Gtk', 'Gdk', 'Gsk', 'GLib', 'Gio', 'GObject', 'GdkPixbuf',
              'Graphene', 'Pango', 'PangoCairo', 'GdkWin32', 'cairo']
hidden = collect_submodules('animalinux') + ['gi', 'cairo'] + \
    [f'gi.repository.{m}' for m in GI_MODULES] + \
    ['vosk', 'vosk.vosk_cffi', '_cffi_backend', 'cffi', 'srt', 'requests', 'tqdm', 'sounddevice']

# Complementos que vienen dentro (ver build.sh): onnxruntime (recorte IA, abajo),
# Vosk (voz; carga libvosk.dll desde su propia carpeta con ruta absoluta) y
# PortAudio para sounddevice (micrófono).
import vosk as _vosk  # noqa: E402
_vdir = os.path.dirname(_vosk.__file__)
binaries = [(f, 'vosk') for f in glob.glob(os.path.join(_vdir, '*.dll'))]
# onnxruntime.dll oficial (build.sh la baja a build/ort) → _internal/onnxruntime_capi
binaries += [(f, 'onnxruntime_capi') for f in glob.glob(os.path.join(ROOT, 'build', 'ort', '*.dll'))]
if not any(d == 'onnxruntime_capi' for _f, d in binaries):
    raise SystemExit('falta build/ort/onnxruntime.dll (ver build.sh)')
_bin = os.path.dirname(sys.executable)
binaries += [(f, '.') for f in glob.glob(os.path.join(_bin, 'libportaudio*.dll'))]

a = Analysis(
    [os.path.join(SPECPATH, 'run_animalinux.py')],
    pathex=[ROOT],
    datas=collect_data_files('animalinux'),
    binaries=binaries,
    hiddenimports=hidden,
    excludes=['onnxruntime'],   # el de MSYS2 viene roto: se usa la DLL oficial (ort_capi)
    hooksconfig={'gi': {'module-versions': {
        'Gtk': '4.0', 'Gdk': '4.0', 'Gsk': '4.0', 'GdkWin32': '4.0',
        'GdkPixbuf': '2.0', 'Pango': '1.0', 'PangoCairo': '1.0',
        'Graphene': '1.0', 'GLib': '2.0', 'Gio': '2.0', 'GObject': '2.0'}}},
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AnimaWin',
          console=False, icon=os.path.join(SPECPATH, 'animawin.ico'))
coll = COLLECT(exe, a.binaries, a.datas, name='AnimaWin')
