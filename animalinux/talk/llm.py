"""
Cliente mínimo de Ollama (sin dependencias: urllib).

Seguridad:
  - SOLO habla con 127.0.0.1 (no lee OLLAMA_HOST: un valor raro podría
    mandar lo que dices a otra máquina).
  - Si el servidor no está corriendo y el programa `ollama` existe, lo
    arranca él mismo atado a 127.0.0.1 y lo apaga al salir. Así el modelo no
    ocupa RAM cuando la app no lo usa (keep_alive corto).
  - Solo descarga modelos de la lista de hw.MODELS.

Todas las llamadas son BLOQUEANTES: brain.py las corre en un hilo.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import hw

HOST = "127.0.0.1"
PORT = 11434
BASE = f"http://{HOST}:{PORT}"
KEEP_ALIVE = "4m"          # tras esto sin hablar, Ollama libera el modelo
MAX_REPLY_CHARS = 160

_proc = None               # `ollama serve` que arrancamos nosotros


class OllamaError(Exception):
    pass


# ── servidor ────────────────────────────────────────────────────────────────
def find_binary():
    exe = shutil.which("ollama")
    if exe:
        return exe
    if sys.platform == "win32":
        cand = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if cand.is_file():
            return str(cand)
        return None
    from ..core.components import user_ollama_dir     # instalado por la app sin root
    cand = user_ollama_dir() / "bin" / "ollama"
    if cand.is_file() and os.access(cand, os.X_OK):
        return str(cand)
    return None


def gpu_backend_missing():
    """¿Hay tarjeta NVIDIA pero el Ollama instalado no trae CUDA? (en Arch el
    paquete `ollama` es solo CPU; hace falta `ollama-cuda`). Devuelve el
    comando para arreglarlo, o "" si no hace falta / no se sabe."""
    if sys.platform == "win32" or not os.path.exists("/proc/driver/nvidia/version"):
        return ""
    for d in ("/usr/lib/ollama", "/usr/local/lib/ollama"):
        p = Path(d)
        if p.is_dir():
            try:
                if any("cuda" in f.name.lower() for f in p.rglob("*")):
                    return ""
            except OSError:
                return ""
            return ("sudo pacman -S ollama-cuda" if d == "/usr/lib/ollama"
                    else "curl -fsSL https://ollama.com/install.sh | sh")
    return ""


def _open(path, body=None, timeout=5.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    # sin proxies: es 127.0.0.1 y un proxy del sistema no debe ver la charla
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(req, timeout=timeout)


def is_running(timeout=1.0):
    try:
        with _open("/api/version", timeout=timeout) as r:
            return "version" in json.loads(r.read(4096) or b"{}")
    except (OSError, ValueError, urllib.error.URLError):
        return False


def ensure_server(wait=20.0):
    """Deja el servidor listo. True si responde; False si no hay Ollama."""
    global _proc
    if is_running():
        return True
    exe = find_binary()
    if not exe:
        return False
    if _proc is None or _proc.poll() is not None:
        env = dict(os.environ)
        # nada de orígenes web extra heredados (OLLAMA_ORIGINS=* dejaría que
        # cualquier página del navegador use el modelo local)
        env.pop("OLLAMA_ORIGINS", None)
        env["OLLAMA_HOST"] = f"{HOST}:{PORT}"
        env["OLLAMA_KEEP_ALIVE"] = KEEP_ALIVE
        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = 0x08000000      # CREATE_NO_WINDOW
        _kill_stale()
        _proc = subprocess.Popen([exe, "serve"], env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
        _write_pid(_proc.pid)
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if is_running(0.5):
            return True
        if _proc.poll() is not None:
            return is_running()       # otro proceso ganó el puerto
        time.sleep(0.25)
    return False


def _pidfile():
    from .. import paths
    return paths.RUNTIME_DIR / "ollama.pid"


def _write_pid(pid):
    try:
        _pidfile().write_text(str(pid))
    except OSError:
        pass


def _kill_stale():
    """Si la app murió de golpe (cuelgue, kill -9), su `ollama serve` quedó
    huérfano ocupando el puerto: al volver a arrancar se cierra ese, y solo
    ese (se comprueba que el PID siga siendo un «ollama serve»)."""
    pf = _pidfile()
    try:
        pid = int(pf.read_text().strip())
    except (OSError, ValueError):
        return
    try:
        pf.unlink()
    except OSError:
        pass
    if sys.platform.startswith("linux"):
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            return
        if len(cmd) >= 2 and cmd[0].endswith(b"ollama") and cmd[1] == b"serve":
            try:
                os.kill(pid, 15)
            except OSError:
                pass


def stop_server():
    """Apaga el `ollama serve` que arrancamos (si fue otro, no se toca)."""
    global _proc
    p, _proc = _proc, None
    if p is not None:
        try:
            _pidfile().unlink()
        except OSError:
            pass
    if p is not None and p.poll() is None:
        p.terminate()
        try:
            p.wait(3)
        except subprocess.TimeoutExpired:
            p.kill()


def started_by_us():
    return _proc is not None and _proc.poll() is None


# ── modelos ─────────────────────────────────────────────────────────────────
def installed_models():
    try:
        with _open("/api/tags", timeout=4) as r:
            data = json.loads(r.read(1 << 20))
    except (OSError, ValueError, urllib.error.URLError):
        return []
    return [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]


def has_model(name):
    names = installed_models()
    return name in names or f"{name}:latest" in names


def pull(name, on_progress=None, cancel=None):
    """Descarga un modelo de la lista permitida. on_progress(fracción 0..1, texto)."""
    if name not in hw.MODELS:
        raise OllamaError("modelo no permitido")
    try:
        r = _open("/api/pull", {"model": name, "stream": True}, timeout=60)
    except (OSError, urllib.error.URLError) as e:
        raise OllamaError(str(e)) from e
    with r:
        for raw in r:
            if cancel is not None and cancel():
                raise OllamaError("cancelado")
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            if ev.get("error"):
                raise OllamaError(str(ev["error"])[:200])
            tot, done = ev.get("total") or 0, ev.get("completed") or 0
            if on_progress is not None:
                on_progress((done / tot) if tot else None, str(ev.get("status", ""))[:80])
            if ev.get("status") == "success":
                return True
    return has_model(name)


# ── conversar ───────────────────────────────────────────────────────────────
def clean_reply(text):
    """Una sola frase corta, sin comillas ni prefijos tipo «Nombre:»."""
    t = (text or "").strip()
    t = t.split("\n", 1)[0].strip()
    if ":" in t[:20] and not t[:20].split(":", 1)[0].strip().count(" "):
        head, rest = t.split(":", 1)
        if head and rest.strip() and len(head) <= 16:
            t = rest.strip()
    t = t.strip(" \"'«»“”")
    if len(t) > MAX_REPLY_CHARS:
        cut = t[:MAX_REPLY_CHARS]
        for sep in (". ", "! ", "? ", "。", "！", "？", ", "):
            i = cut.rfind(sep)
            if i > 40:
                cut = cut[:i + 1]
                break
        t = cut.rstrip() + ("" if cut[-1:] in ".!?。！？" else "…")
    return t


def chat(model, messages, on_token=None, cancel=None, max_tokens=48):
    """Conversa en streaming. on_token(texto_hasta_ahora) por cada trozo.
    Devuelve (respuesta_limpia, tokens_por_segundo)."""
    body = {"model": model, "messages": messages, "stream": True, "think": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"temperature": 0.85, "top_p": 0.92, "num_predict": max_tokens,
                        "num_ctx": 1024, "stop": ["\n"]}}
    try:
        r = _open("/api/chat", body, timeout=120)
    except urllib.error.HTTPError as e:
        raise OllamaError(f"HTTP {e.code}") from e
    except (OSError, urllib.error.URLError) as e:
        raise OllamaError(str(e)) from e
    out, tps = "", 0.0
    with r:
        for raw in r:
            if cancel is not None and cancel():
                break
            try:
                ev = json.loads(raw)
            except ValueError:
                continue
            if ev.get("error"):
                raise OllamaError(str(ev["error"])[:200])
            piece = (ev.get("message") or {}).get("content") or ""
            if piece:
                out += piece
                if "\n" in out.strip():
                    break
                if on_token is not None:
                    on_token(clean_reply(out))
            if ev.get("done"):
                n, dur = ev.get("eval_count") or 0, ev.get("eval_duration") or 0
                tps = n / (dur / 1e9) if dur else 0.0
                break
    return clean_reply(out), tps


def warmup(model):
    """Carga el modelo en memoria sin generar nada (unos segundos en frío).
    Se llama al oír «ey <nombre>»: carga mientras terminas de hablar."""
    if model not in hw.MODELS:
        return False
    try:
        with _open("/api/generate", {"model": model, "keep_alive": KEEP_ALIVE}, timeout=120) as r:
            r.read(1 << 16)
        return True
    except (OSError, urllib.error.URLError):
        return False


def unload(model):
    """Saca el modelo de la memoria ya (keep_alive 0), sin esperar los
    minutos de KEEP_ALIVE. Solo si el servidor ya está corriendo."""
    if model not in hw.MODELS or not is_running():
        return False
    try:
        with _open("/api/generate", {"model": model, "keep_alive": 0}, timeout=10) as r:
            r.read(1 << 16)
        return True
    except (OSError, urllib.error.URLError):
        return False


def benchmark(model):
    """Mide tokens/s reales con una pregunta corta (carga el modelo)."""
    msgs = [{"role": "user", "content": "Count from one to twenty in words."}]
    _txt, tps = chat(model, msgs, max_tokens=40)
    return tps
