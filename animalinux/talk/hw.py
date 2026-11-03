"""
¿Puede este equipo con la IA de conversación?

Mira la RAM, la CPU (núcleos y AVX2 en x86), la GPU (VRAM de NVIDIA) y el
disco libre, y devuelve un nivel:

  "none"  no cumple: se usa el modo de frases escritas
  "slow"  funciona, pero lento → modelo liviano o frases
  "ok"    va bien con el modelo normal en CPU
  "fast"  GPU con VRAM de sobra

Después, `rate_speed()` clasifica la velocidad REAL medida (tokens/s) con el
modelo ya descargado, que es lo que de verdad nota el usuario.
"""
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

GB = 1024 ** 3

# Modelos que ofrece la app (tamaño en disco ≈ RAM que ocupa al cargarse)
MODELS = {
    "gemma3:4b": {"disk": 3.4, "ram": 4.0, "label": "Gemma 3 · 4B"},
    "gemma3:1b": {"disk": 0.8, "ram": 1.5, "label": "Gemma 3 · 1B"},
}
DEFAULT_MODEL = "gemma3:4b"
LIGHT_MODEL = "gemma3:1b"


def total_ram():
    """RAM total en bytes (0 si no se pudo leer)."""
    if sys.platform == "win32":
        import ctypes

        class MEMSTAT(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MEMSTAT()
        st.dwLength = ctypes.sizeof(st)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return int(st.ullTotalPhys)
        except Exception:  # noqa: BLE001
            pass
        return 0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return 0


def has_avx2():
    """True/False en x86; None si no aplica o no se sabe (ARM, Windows)."""
    mach = platform.machine().lower()
    if mach not in ("x86_64", "amd64", "i686", "i386"):
        return None
    if sys.platform == "win32":
        try:
            import ctypes
            # PF_AVX2_INSTRUCTIONS_AVAILABLE = 40
            return bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))
        except Exception:  # noqa: BLE001
            return None
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.startswith("flags"):
                    return " avx2 " in f" {line.split(':', 1)[-1].strip()} "
    except OSError:
        pass
    return None


def gpu_vram():
    """VRAM de la GPU NVIDIA en bytes (0 si no hay o no se sabe)."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return 0
    try:
        out = subprocess.run([exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=4).stdout
        return max(int(x.strip()) for x in out.splitlines() if x.strip()) * 1024 ** 2
    except Exception:  # noqa: BLE001
        return 0


def power_saver():
    """True si el equipo está en modo ahorro de energía (la IA irá varias
    veces más lenta). Linux: perfil ACPI / power-profiles-daemon."""
    if sys.platform == "win32":
        return False
    try:
        prof = Path("/sys/firmware/acpi/platform_profile").read_text().strip()
        if prof in ("low-power", "quiet", "cool"):
            return True
    except OSError:
        pass
    exe = shutil.which("powerprofilesctl")
    if exe:
        try:
            out = subprocess.run([exe, "get"], capture_output=True, text=True, timeout=2).stdout
            return out.strip() == "power-saver"
        except Exception:  # noqa: BLE001
            pass
    return False


def free_disk(path):
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return 0


def models_dir():
    env = os.environ.get("OLLAMA_MODELS")
    return Path(env) if env else Path.home() / ".ollama" / "models"


def assess(ram=None, cores=None, avx2="?", vram=None, disk=None):
    """Evalúa el equipo. Los argumentos permiten probarlo con valores fijos.

    Devuelve dict: level, model (recomendado o ""), ram_gb, cores, avx2,
    vram_gb, disk_gb, reasons (lista de claves de motivo, ver brain.py)."""
    ram = total_ram() if ram is None else ram
    cores = (os.cpu_count() or 1) if cores is None else cores
    avx2 = has_avx2() if avx2 == "?" else avx2
    vram = gpu_vram() if vram is None else vram
    disk = free_disk(models_dir()) if disk is None else disk
    reasons = []
    if ram and ram < 3.5 * GB:
        reasons.append("ram_low")
    if avx2 is False:
        reasons.append("no_avx2")
    if cores < 2:
        reasons.append("cpu_weak")
    big, light = MODELS[DEFAULT_MODEL], MODELS[LIGHT_MODEL]
    if disk and disk < (light["disk"] + 0.5) * GB:
        reasons.append("disk_low")

    if reasons:
        level, model = "none", ""
    elif vram >= 5.5 * GB and ram >= 7 * GB:
        level, model = "fast", DEFAULT_MODEL
    elif ram >= 7 * GB and cores >= 4 and disk >= (big["disk"] + 1) * GB:
        level, model = "ok", DEFAULT_MODEL
    else:
        level, model = "slow", LIGHT_MODEL
        if ram < 7 * GB:
            reasons.append("ram_mid")
        if cores < 4:
            reasons.append("cpu_mid")
        if disk and disk < (big["disk"] + 1) * GB:
            reasons.append("disk_mid")
    return {"level": level, "model": model, "reasons": reasons,
            "ram_gb": round(ram / GB, 1), "cores": cores, "avx2": avx2,
            "vram_gb": round(vram / GB, 1), "disk_gb": round(disk / GB, 1)}


def rate_speed(tokens_per_s):
    """Velocidad medida → "fast" | "ok" | "slow" | "none"."""
    if tokens_per_s >= 15:
        return "fast"
    if tokens_per_s >= 6:
        return "ok"
    if tokens_per_s >= 2.5:
        return "slow"
    return "none"
