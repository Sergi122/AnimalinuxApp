"""
Subir una mascota a la comunidad (https://animalinux-community.web.app)
directamente desde la app, sin abrir el navegador.

Hace lo mismo que la página de subida: guarda el .alpack (o el .gif) y una
vista previa en Supabase Storage y crea la fila en `packs`. La mascota NO
aparece al instante: la función validate-pack del servidor revisa el
archivo (rutas, PNG reales, tamaños) y recién entonces la marca verificada.
Se usa la clave pública (anon) de la web: no da ningún permiso especial.
"""
import io
import re
import json
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

SUPABASE_URL = "https://vutmbldvzgqcqenuzjav.supabase.co"
SUPABASE_ANON = "sb_publishable_TpezmyjjZmEoDeP47E8h7A_IjJ4maa9"
GALLERY = "https://animalinux-community.web.app/"
DISCORD = "https://discord.gg/wshjY2WChB"  # invitación permanente al servidor oficial
MAX_MB = 50


class UploadError(RuntimeError):
    pass


def _req(method, path, data=None, headers=None, timeout=60):
    h = {"apikey": SUPABASE_ANON, "Authorization": f"Bearer {SUPABASE_ANON}"}
    h.update(headers or {})
    r = urllib.request.Request(SUPABASE_URL + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        raise UploadError(f"{e.code}: {e.read()[:200].decode('utf-8', 'replace')}") from None
    except urllib.error.URLError as e:
        raise UploadError(str(e.reason)) from None


def _preview_png(frames_dir):
    from PIL import Image
    d = Path(frames_dir)
    first = d / "frame_0000.png"
    if not first.exists():
        subs = sorted(p for p in d.iterdir() if p.is_dir())
        first = next((s / "frame_0000.png" for s in subs if (s / "frame_0000.png").exists()), None)
    if first is None:
        return None
    im = Image.open(first).convert("RGBA")
    k = 256 / max(im.size)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))),
                   Image.NEAREST if max(im.size) <= 128 else Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def build_payload(library, anim_id, export_pack, export_gif):
    """Prepara (kind, bytes del archivo, mime, png de vista previa, meta)."""
    anim = library.animations.get(anim_id)
    if not anim:
        raise UploadError("no existe")
    life = anim.get("mode") == "life" or len(anim.get("poses", ["default"])) > 1
    with tempfile.TemporaryDirectory() as tmp:
        if life:
            out = Path(export_pack(anim_id, Path(tmp) / "m.alpack"))
            kind, mime = "alpack", "application/zip"
        else:
            out = Path(export_gif(anim_id, str(Path(tmp) / "m.gif")))
            kind, mime = "gif", "image/gif"
        data = out.read_bytes()
    if len(data) > MAX_MB * 1024 * 1024:
        raise UploadError(f"> {MAX_MB} MB")
    meta = {"name": anim.get("name", "Mascota")[:60], "fps": int(anim.get("fps", 12)),
            "poses": list(anim.get("poses", ["default"]))}
    prev = _preview_png(library.frames_dir(anim_id)) if kind != "gif" else None
    return kind, data, mime, prev, meta


def upload(kind, data, mime, preview, meta, author="", description="", tags=()):
    folder = uuid.uuid4().hex
    ts = int(time.time() * 1000)
    file_path = f"{folder}/{ts}.{kind}"
    _req("POST", f"/storage/v1/object/packs/{file_path}", data,
         {"Content-Type": mime, "x-upsert": "false"})
    prev_path = None
    if preview:
        prev_path = f"{folder}/{ts}.png"
        _req("POST", f"/storage/v1/object/previews/{prev_path}", preview,
             {"Content-Type": "image/png", "x-upsert": "false"})
    row = {"name": meta["name"], "description": (description or None) and description[:300],
           "author": (author or "")[:60] or None, "fps": max(1, min(60, meta["fps"])),
           "poses": meta["poses"], "tags": list(tags) or None, "kind": kind,
           "file_path": file_path, "preview_path": prev_path, "file_size": len(data),
           "user_id": None, "downloads": 0}
    _req("POST", "/rest/v1/packs", json.dumps(row).encode(),
         {"Content-Type": "application/json", "Prefer": "return=minimal"})
    return file_path


# ── catálogo: ver y bajar mascotas desde la app ─────────────────────────────
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_-]{1,64}/[A-Za-z0-9_.-]{1,80}$")
KINDS = {"alpack": "alpack", "gif": "gif"}


def public_url(bucket, path):
    if not path or not _SAFE_PATH.match(path) or ".." in path:
        raise UploadError("ruta inválida")
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"


def list_packs(order="downloads", limit=200):
    """Mascotas verificadas de la galería (lo mismo que muestra la web)."""
    col = {"downloads": "downloads.desc", "votes": "votes.desc",
           "new": "created_at.desc"}.get(order, "downloads.desc")
    q = ("/rest/v1/packs?select=id,name,author,description,fps,poses,kind,file_path,"
         f"preview_path,file_size,downloads,votes,created_at&verified=eq.true&order={col}"
         f"&limit={int(limit)}")
    _st, body = _req("GET", q, timeout=20)
    rows = json.loads(body.decode("utf-8"))
    return [r for r in rows if isinstance(r, dict) and r.get("kind") in KINDS
            and _SAFE_PATH.match(r.get("file_path") or "")]


def fetch(url, max_bytes, timeout=60):
    if not url.startswith(SUPABASE_URL + "/storage/v1/object/public/"):
        raise UploadError("url no permitida")
    req = urllib.request.Request(url, headers={"User-Agent": "AnimaLinux"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(max_bytes + 1)
    except urllib.error.URLError as e:
        raise UploadError(str(getattr(e, "reason", e))) from None
    if len(data) > max_bytes:
        raise UploadError(f"> {max_bytes // (1024 * 1024)} MB")
    return data


def preview_bytes(pack):
    if not pack.get("preview_path") and pack.get("kind") == "gif":
        return fetch(public_url("packs", pack["file_path"]), 8 * 1024 * 1024)
    if not pack.get("preview_path"):
        return None
    return fetch(public_url("previews", pack["preview_path"]), 2 * 1024 * 1024)


def download_pack(pack, dest_dir):
    """Baja el archivo de la mascota a dest_dir y suma una descarga. Devuelve la ruta."""
    kind = KINDS[pack["kind"]]
    data = fetch(public_url("packs", pack["file_path"]), MAX_MB * 1024 * 1024)
    out = Path(dest_dir) / f"comunidad-{uuid.uuid4().hex[:8]}.{kind}"
    out.write_bytes(data)
    try:   # contador de la web (por RPC: RLS no deja un UPDATE directo)
        _req("POST", "/rest/v1/rpc/increment_pack_downloads",
             json.dumps({"pack_id": pack["id"]}).encode(),
             {"Content-Type": "application/json"}, timeout=10)
    except UploadError:
        pass
    return out
