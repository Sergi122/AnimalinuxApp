"""`animalinux --selftest`: comprueba que todo lo que viene dentro funcione
de verdad y deja un informe en DATA_DIR/selftest.txt (también sirve para
diagnosticar el equipo de un usuario). Abre además el catálogo y los
complementos para verlos."""
import importlib
import shutil
import subprocess
import threading
import time
import traceback

from gi.repository import GLib

from . import paths


def _checks():
    out = []

    def ok(name, fn):
        t = time.time()
        try:
            r = fn()
            out.append(f"OK    {name}: {r} ({time.time() - t:.1f} s)")
        except Exception as e:  # noqa: BLE001
            out.append(f"FALLA {name}: {e!r}")
            out.append("      " + traceback.format_exc().strip().splitlines()[-1])

    def mod(n):
        m = importlib.import_module(n)
        return getattr(m, "__version__", "importa")
    def engine():
        from .core import cutout, ort_capi
        if cutout._py_engine():
            return "módulo de Python " + mod("onnxruntime")
        ort_capi.api()
        return "API en C: " + str(ort_capi.find_library())
    ok("motor IA (onnxruntime)", engine)
    ok("vosk", lambda: (importlib.import_module("vosk").Model.__name__, "libvosk cargada")[1])
    import sys
    if sys.platform == "win32":    # en Linux el micrófono va con pw-record/parecord
        ok("sounddevice", lambda: f"{len(importlib.import_module('sounddevice').query_devices())} dispositivos")
    for exe in ("ffmpeg", "ffprobe", "mpv"):
        def run(exe=exe):
            p = shutil.which(exe)
            if not p:
                raise RuntimeError("no está en el PATH")
            from .backends import current as backend
            r = subprocess.run([p, "-version" if exe != "mpv" else "--version"], capture_output=True,
                               text=True, timeout=30, **getattr(backend, "SUBPROCESS_KW", {}))
            lines = (r.stdout or r.stderr or "").splitlines()
            if r.returncode != 0 or not lines:
                raise RuntimeError(f"terminó con código {r.returncode:#x}")
            return lines[0][:60]
        ok(exe, run)

    def cut():
        from pathlib import Path
        from PIL import Image
        from .core import cutout
        s = cutout.ensure_ready()
        ball = Image.open(Path(__file__).parent / "ui" / "assets" / "toys" / "volley"
                          / "frame_0000.png").convert("RGBA").resize((160, 160), Image.NEAREST)
        im = Image.new("RGBA", (256, 256), (40, 160, 60, 255))
        im.alpha_composite(ball, (48, 48))
        a = cutout.remove(im, s).getchannel("A")
        w, h = a.size
        return f"esquina alfa={a.getpixel((2, 2))}, centro alfa={a.getpixel((w // 2, h // 2))}"
    ok("recorte IA (baja el modelo si falta)", cut)

    def cat():
        from . import community
        ps = community.list_packs()
        return f"{len(ps)} mascotas; vista previa {len(community.preview_bytes(ps[0]) or b'')} bytes"
    ok("catálogo de la comunidad", cat)

    def comps():
        from .core import components
        return components.summary()
    ok("complementos", comps)
    return out


def run(app):
    def work():
        lines = _checks()
        rep = paths.DATA_DIR / "selftest.txt"
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines), flush=True)
    threading.Thread(target=work, daemon=True).start()
    GLib.timeout_add(1500, lambda: (app.show_catalog(), False)[1])
    GLib.timeout_add(9000, lambda: (app.show_components(), False)[1])
