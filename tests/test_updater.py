"""Tests del actualizador: canal de Windows (releases «win-vX.Y.Z»), verificación
SHA-256, hosts permitidos y tope de tamaño. Sin red: todo con falsos."""
import hashlib
import io
import json

import pytest

from animalinux.core import updater

SHA = hashlib.sha256(b"instalador-falso").hexdigest()


def _release(tag, body=f"notas\n\nSHA-256: {SHA}", draft=False, assets=None):
    return {"tag_name": tag, "draft": draft, "body": body,
            "assets": assets if assets is not None else [
                {"name": f"AnimaWin-Setup-{tag.removeprefix('win-v')}.exe",
                 "browser_download_url": "https://github.com/Sergi122/AnimalinuxApp/releases/download/x/a.exe"}]}


def test_windows_releases_only_win_tags_and_no_drafts(monkeypatch):
    data = [_release("win-v0.6.0"), _release("v0.9.9"), _release("win-v0.7.0", draft=True), _release("win-vX"),
            _release("win-v0.5.5")]
    monkeypatch.setattr(updater, "_get", lambda *a, **k: json.dumps(data).encode())
    assert set(updater._windows_releases()) == {"0.6.0", "0.5.5"}


def test_check_latest_windows_picks_highest(monkeypatch):
    monkeypatch.setattr(updater, "_WIN", True)
    data = [_release("win-v0.5.5"), _release("win-v0.10.0"), _release("win-v0.6.0")]
    monkeypatch.setattr(updater, "_get", lambda *a, **k: json.dumps(data).encode())
    assert updater.check_latest() == "0.10.0"


def test_check_latest_linux_ignores_windows_tags(monkeypatch):
    monkeypatch.setattr(updater, "_WIN", False)
    tags = [{"name": "win-v9.9.9"}, {"name": "v0.5.5"}, {"name": "v0.6.0"}]
    monkeypatch.setattr(updater, "_get", lambda *a, **k: json.dumps(tags).encode())
    assert updater.check_latest() == "0.6.0"


def test_sha_is_parsed_from_release_notes():
    assert updater._SHA_RE.search(f"hola\nSHA-256: {SHA}\n").group(1) == SHA
    assert updater._SHA_RE.search("sin huella") is None
    assert updater._SHA_RE.search("SHA-256: abc123") is None


@pytest.mark.parametrize("url,ok", [
    ("https://github.com/x/y/releases/download/a/b.exe", True),
    ("https://objects.githubusercontent.com/abc", True),
    ("https://release-assets.githubusercontent.com/abc", True),
    ("http://github.com/x", False),
    ("https://evil.com/github.com", False),
    ("https://github.com.evil.com/x", False),
    ("https://notgithub.com/x", False),
    ("file:///etc/passwd", False),
    ("ftp://github.com/x", False),
])
def test_host_allowlist(url, ok):
    assert updater._host_ok(url) is ok


class _FakeResp(io.BytesIO):
    def __init__(self, data, length=None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data) if length is None else length)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_opener(monkeypatch, resp):
    class _O:
        def open(self, req, timeout=0):
            return resp
    monkeypatch.setattr(updater.urllib.request, "build_opener", lambda *a, **k: _O())


def test_download_verified_ok(tmp_path, monkeypatch):
    _patch_opener(monkeypatch, _FakeResp(b"instalador-falso"))
    dest = tmp_path / "a.exe"
    updater._download_verified("https://github.com/x/a.exe", dest, SHA)
    assert dest.read_bytes() == b"instalador-falso"


def test_download_with_wrong_hash_is_deleted(tmp_path, monkeypatch):
    _patch_opener(monkeypatch, _FakeResp(b"contenido alterado"))
    dest = tmp_path / "a.exe"
    with pytest.raises(RuntimeError):
        updater._download_verified("https://github.com/x/a.exe", dest, SHA)
    assert not dest.exists()


def test_download_rejects_foreign_host_without_network(tmp_path):
    with pytest.raises(RuntimeError):
        updater._download_verified("https://evil.example/a.exe", tmp_path / "a.exe", SHA)


def test_download_rejects_oversized(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "MAX_INSTALLER_BYTES", 5)
    _patch_opener(monkeypatch, _FakeResp(b"instalador-falso"))
    dest = tmp_path / "a.exe"
    with pytest.raises(RuntimeError):
        updater._download_verified("https://github.com/x/a.exe", dest, SHA)
    assert not dest.exists()


def test_apply_windows_not_frozen_opens_releases_page(monkeypatch):
    opened = []
    monkeypatch.setattr(updater.backend, "open_url", opened.append, raising=False)
    monkeypatch.setattr(updater.sys, "frozen", False, raising=False)
    with pytest.raises(RuntimeError):
        updater._apply_windows("0.6.0")
    assert opened and "releases" in opened[0]


def test_apply_windows_requires_hash_and_asset(monkeypatch):
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater, "_windows_releases", lambda: {"0.6.0": _release("win-v0.6.0", body="sin huella")})
    with pytest.raises(RuntimeError):
        updater._apply_windows("0.6.0")
    monkeypatch.setattr(updater, "_windows_releases", lambda: {"0.6.0": _release("win-v0.6.0", assets=[])})
    with pytest.raises(RuntimeError):
        updater._apply_windows("0.6.0")


def test_apply_windows_runs_silent_installer_after_verifying(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater, "_windows_releases", lambda: {"0.6.0": _release("win-v0.6.0")})
    _patch_opener(monkeypatch, _FakeResp(b"instalador-falso"))
    calls = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw)))
    monkeypatch.setattr(updater.settings, "set_val", lambda *a: None)
    updater._apply_windows("0.6.0")
    cmd, kw = calls[0]
    assert cmd[0].endswith("AnimaWin-Setup-0.6.0.exe") and "/VERYSILENT" in cmd and kw.get("close_fds")


def test_apply_update_rejects_bad_version():
    with pytest.raises(RuntimeError):
        updater.apply_update("0.6.0; calc.exe")


def test_is_newer():
    assert updater.is_newer("0.6.0", "0.5.5") and not updater.is_newer("0.5.5", "0.5.5")
    assert updater.is_newer("0.10.0", "0.9.9") and not updater.is_newer("basura", "0.1.0")
