"""Complementos, recorte IA propio y catálogo: lo que se puede probar sin red."""
import hashlib
import io

import numpy as np
import pytest
from PIL import Image

from animalinux import community
from animalinux.core import components, cutout


class _Resp(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data)
        self._url = url
        self.headers = {"Content-Length": str(len(data))}

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_only_https_github(xdg_tmp):
    for bad in ("http://github.com/x", "https://evil.example/x", "file:///etc/passwd",
                "https://github.com.evil.io/x"):
        with pytest.raises(components.ComponentError):
            components.download(bad, xdg_tmp / "f")


def test_download_rejects_redirect_away(xdg_tmp, monkeypatch):
    monkeypatch.setattr(components.urllib.request, "urlopen",
                        lambda *a, **k: _Resp(b"x", "https://evil.example/x"))
    with pytest.raises(components.ComponentError):
        components.download("https://github.com/a/b", xdg_tmp / "f")
    assert not (xdg_tmp / "f").exists()


def test_download_checks_sha256(xdg_tmp, monkeypatch):
    data = b"hola mundo"
    url = "https://github.com/a/b"
    monkeypatch.setattr(components.urllib.request, "urlopen", lambda *a, **k: _Resp(data, url))
    with pytest.raises(components.ComponentError):
        components.download(url, xdg_tmp / "f", sha256="0" * 64)
    assert not (xdg_tmp / "f").exists() and not (xdg_tmp / "f.part").exists()
    out = components.download(url, xdg_tmp / "f", sha256=hashlib.sha256(data).hexdigest())
    assert out.read_bytes() == data


def test_download_size_cap(xdg_tmp, monkeypatch):
    url = "https://github.com/a/b"
    monkeypatch.setattr(components.urllib.request, "urlopen", lambda *a, **k: _Resp(b"x" * 100, url))
    with pytest.raises(components.ComponentError):
        components.download(url, xdg_tmp / "f", max_bytes=10)


def test_every_component_has_status_and_text():
    for cid in components.ORDER:
        title, desc, mb = components.describe(cid)
        assert title and desc and mb > 0
        assert components.status(cid) in ("ok", "missing", "unsupported")


def test_community_paths_are_safe():
    assert community.public_url("packs", "abc-1/123.alpack").endswith("/public/packs/abc-1/123.alpack")
    for bad in ("../x/y.alpack", "a/../../b", "a/b/c.alpack", "a\\b.alpack", "", None, "a/b?x=1"):
        with pytest.raises(community.UploadError):
            community.public_url("packs", bad)
    with pytest.raises(community.UploadError):
        community.fetch("https://evil.example/x.alpack", 10)


def test_list_packs_filters_bad_rows(monkeypatch):
    rows = [{"id": "1", "kind": "alpack", "file_path": "a/1.alpack"},
            {"id": "2", "kind": "exe", "file_path": "a/2.exe"},
            {"id": "3", "kind": "gif", "file_path": "../../etc/passwd"},
            "basura"]
    import json
    monkeypatch.setattr(community, "_req", lambda *a, **k: (200, json.dumps(rows).encode()))
    assert [p["id"] for p in community.list_packs()] == ["1"]


class _FakeSession:
    """Como el modelo real: (1,3,1024,1024) → máscara (1,1,1024,1024)."""
    def get_inputs(self):
        return [type("I", (), {"name": "img"})()]

    def run(self, _out, feed):
        x = feed["img"]
        assert x.shape == (1, 3, 1024, 1024) and x.dtype == np.float32
        m = np.zeros((1, 1, 1024, 1024), np.float32)
        m[:, :, 256:768, 256:768] = 3.0      # cuadrado central = la mascota
        return [m]


def test_cutout_keeps_subject_and_clears_background():
    im = Image.new("RGBA", (200, 100), (0, 255, 0, 255))
    out = cutout.remove(im, _FakeSession())
    assert out.size == im.size and out.mode == "RGBA"
    a = out.getchannel("A")
    assert a.getpixel((2, 2)) == 0 and a.getpixel((100, 50)) == 255


def test_model_validation_rejects_wrong_file(xdg_tmp):
    p = xdg_tmp / "m.onnx"
    p.write_bytes(b"no es un modelo")
    assert not cutout._valid(p)
    assert not cutout._valid(xdg_tmp / "no-existe.onnx")
