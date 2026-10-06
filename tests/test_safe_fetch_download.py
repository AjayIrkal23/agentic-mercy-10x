"""safe_fetch.download: https only, redirects included, and a pinned hash that cannot be empty (SEC1B-05).

The Windows installers pass ``require_hash=True`` (every pin comes from the manifest); the Linux node
install has no per-file hash (it checks SHASUMS) and keeps working without one. Nothing here touches
the network: the opener is injected.
"""
from __future__ import annotations

import hashlib
import io
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import safe_fetch  # noqa: E402

DATA = b"payload"
GOOD = hashlib.sha256(DATA).hexdigest()


class _Resp:
    headers = {"Content-Length": str(len(DATA))}

    def __init__(self):
        self._io = io.BytesIO(DATA)

    def read(self, n=-1):
        return self._io.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _dl(tmp_path, url="https://h/a", **kw):
    opened = []

    def opener(u, timeout):
        opened.append(u)
        return _Resp()
    safe_fetch.download(url, tmp_path / "a.bin", opener=opener, **kw)
    return opened


@pytest.mark.parametrize("url", ["http://h/a", "ftp://h/a", "file:///etc/passwd", "HTTPS-ish://h/a", ""])
def test_download_refuses_anything_but_https_before_opening_it(tmp_path, url):
    opened = []
    with pytest.raises(ValueError, match="https"):
        safe_fetch.download(url, tmp_path / "a.bin", sha256=GOOD, opener=lambda u, t: opened.append(u))
    assert opened == [] and not (tmp_path / "a.bin").exists()


@pytest.mark.parametrize("bad", ["", " ", "abc", "z" * 64, "0" * 63])
def test_a_present_but_malformed_hash_is_refused_not_skipped(tmp_path, bad):
    with pytest.raises(OSError, match="sha256"):
        _dl(tmp_path, sha256=bad)
    assert not (tmp_path / "a.bin").exists() and not list(tmp_path.glob("*.part"))


def test_require_hash_refuses_a_missing_hash_and_accepts_a_pinned_one(tmp_path):
    with pytest.raises(OSError, match="sha256"):
        _dl(tmp_path, require_hash=True)
    assert _dl(tmp_path, sha256=GOOD.upper(), require_hash=True) == ["https://h/a"]
    assert (tmp_path / "a.bin").read_bytes() == DATA


def test_without_a_hash_and_without_require_hash_the_node_install_path_still_works(tmp_path):
    assert _dl(tmp_path) == ["https://h/a"]


def test_a_denied_rename_of_the_part_file_is_retried(tmp_path, monkeypatch):
    """A5v2-02: Defender scans a fresh download; the first rename can be ACCESS_DENIED."""
    real, left = safe_fetch.os.replace, {"n": 2}

    def replace(a, b, *x, **k):
        if left["n"] > 0:
            left["n"] -= 1
            raise PermissionError(5, "Access is denied")
        return real(a, b, *x, **k)
    monkeypatch.setattr(safe_fetch.os, "replace", replace)
    monkeypatch.setattr(safe_fetch.time, "sleep", lambda s: None)
    _dl(tmp_path, sha256=GOOD)
    assert left["n"] == 0 and (tmp_path / "a.bin").read_bytes() == DATA and not list(tmp_path.glob("*.part"))


def test_a_redirect_to_http_is_refused_but_https_follows():
    h = safe_fetch._HttpsRedirect()
    req = urllib.request.Request("https://h/a")
    with pytest.raises(urllib.error.URLError):
        h.redirect_request(req, None, 302, "Found", {}, "http://evil/a")
    assert h.redirect_request(req, None, 302, "Found", {}, "https://cdn/a").full_url == "https://cdn/a"


def test_the_default_opener_is_https_only_and_fetch_keeps_http_for_localhost():
    with pytest.raises(ValueError):
        safe_fetch._open_https("http://h/a", 1)
    with pytest.raises(ValueError):
        safe_fetch._open("ftp://h/a", 1)  # fetch(): http(s) only, the ollama probe is http://127.0.0.1
