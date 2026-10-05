"""Santa installer review: hostile / truncated archives and downloads (items 3 and 4)."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import userspace  # noqa: E402

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))


def _tar(members) -> tarfile.TarFile:
    """members: [(name, kind, payload)] kind in file|sym|hard|dir -> an in-memory archive."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, kind, payload in members:
            ti = tarfile.TarInfo(name)
            if kind == "file":
                ti.size, ti.mode = len(payload), 0o644
                tf.addfile(ti, io.BytesIO(payload))
            elif kind == "dir":
                ti.type, ti.mode = tarfile.DIRTYPE, 0o755
                tf.addfile(ti)
            else:
                ti.type = tarfile.SYMTYPE if kind == "sym" else tarfile.LNKTYPE
                ti.linkname = payload
                tf.addfile(ti)
    buf.seek(0)
    return tarfile.open(fileobj=buf, mode="r")


@pytest.fixture
def box(tmp_path):
    dest, outside = tmp_path / "prefix", tmp_path / "outside"
    dest.mkdir()
    outside.mkdir()
    (outside / "victim").write_text("SAFE", encoding="utf-8")
    return dest, outside


def test_a_symlink_out_of_the_prefix_is_never_followed(box):
    dest, outside = box
    userspace.extract_prefix(_tar([("top/lib/x", "sym", str(outside)),
                                   ("top/lib/x/victim", "file", b"PWNED")]), dest)
    assert (outside / "victim").read_text(encoding="utf-8") == "SAFE"
    assert not (dest / "lib" / "x").is_symlink()


def test_absolute_and_dotdot_symlink_targets_are_refused(box):
    dest, outside = box
    userspace.extract_prefix(_tar([("t/a", "sym", "/etc"), ("t/b", "sym", "../../outside"),
                                   ("t/c", "sym", "sub/../../../outside")]), dest)
    assert not any((dest / n).is_symlink() for n in "abc")


def test_a_hardlink_to_a_file_outside_is_refused(box):
    dest, outside = box
    userspace.extract_prefix(_tar([("t/h", "hard", "../outside/victim"), ("t/g", "hard", "/etc/passwd")]), dest)
    assert not (dest / "h").exists() and not (dest / "g").exists()


def test_symlinks_that_stay_inside_still_work_and_can_be_traversed(box):
    dest, _ = box
    n = userspace.extract_prefix(_tar([
        ("node-v1/lib/node_modules/npm/bin/npm-cli.js", "file", b"js"),
        ("node-v1/bin/npm", "sym", "../lib/node_modules/npm/bin/npm-cli.js"),
        ("node-v1/lib/shortcut", "sym", "node_modules"),
        ("node-v1/lib/shortcut/extra.txt", "file", b"x")]), dest)
    assert (dest / "bin" / "npm").is_symlink() and (dest / "bin" / "npm").read_bytes() == b"js"
    assert (dest / "lib" / "node_modules" / "extra.txt").read_bytes() == b"x" and n >= 3


def test_an_inside_hardlink_is_materialised(box):
    dest, _ = box
    userspace.extract_prefix(_tar([("t/bin/a", "file", b"data"), ("t/bin/b", "hard", "t/bin/a")]), dest)
    assert (dest / "bin" / "b").read_bytes() == b"data"


def test_absolute_and_dotdot_member_names_are_still_skipped(box):
    dest, outside = box
    userspace.extract_prefix(_tar([("t/../../outside/evil", "file", b"x"), ("/abs/evil", "file", b"x")]), dest)
    assert not (outside / "evil").exists() and not list(dest.rglob("evil"))


# --- 4. downloads are verified, then renamed --------------------------------------------- #
class _Resp:
    def __init__(self, data: bytes, length="auto"):
        self._io = io.BytesIO(data)
        n = len(data) if length == "auto" else length
        self.headers = {} if n is None else {"Content-Length": str(n)}

    def read(self, n=-1):
        return self._io.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(resp):
    return lambda url, timeout: resp


def test_a_short_read_is_an_error_and_leaves_no_file(tmp_path):
    dest = tmp_path / "a.tgz"
    with pytest.raises(OSError, match="truncated"):
        userspace.download("https://h/a", dest, opener=_opener(_Resp(b"x" * 500, length=100000)))
    assert not dest.exists() and not list(tmp_path.glob("*.part"))


def test_a_complete_download_is_renamed_into_place(tmp_path):
    dest = tmp_path / "a.tgz"
    userspace.download("https://h/a", dest, opener=_opener(_Resp(b"payload")))
    assert dest.read_bytes() == b"payload" and not list(tmp_path.glob("*.part"))


def test_a_pinned_sha256_is_enforced_before_the_rename(tmp_path):
    dest = tmp_path / "a.tgz"
    good = hashlib.sha256(b"payload").hexdigest()
    userspace.download("https://h/a", dest, sha256=good, opener=_opener(_Resp(b"payload")))
    dest.unlink()
    with pytest.raises(OSError, match="checksum"):
        userspace.download("https://h/a", dest, sha256="0" * 64, opener=_opener(_Resp(b"payload")))
    assert not dest.exists() and not list(tmp_path.glob("*.part"))


def test_a_missing_content_length_is_not_an_error(tmp_path):
    dest = tmp_path / "a.tgz"
    userspace.download("https://h/a", dest, opener=_opener(_Resp(b"payload", length=None)))
    assert dest.read_bytes() == b"payload"


# --- gh is a pinned release with a pinned hash -------------------------------------------- #
def test_manifest_pins_gh_and_ollama_with_sha256():
    gh, ol = M["user_space"]["gh"], M["user_space"]["ollama"]
    assert gh["version"].count(".") == 2 and set(gh["sha256"]) == {"amd64", "arm64"}
    assert ol["version"].startswith("v") and set(ol["sha256"]) == {"linux-amd64", "linux-arm64"}
    assert all(len(h) == 64 for h in [*gh["sha256"].values(), *ol["sha256"].values()])


def test_gh_installs_the_pinned_release_after_a_checked_download(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(userspace, "os_arch", lambda: ("linux", "x64"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        data = b"#!/bin/sh\n"
        ti = tarfile.TarInfo("gh_2.102.0_linux_amd64/bin/gh")
        ti.size, ti.mode = len(data), 0o755
        tf.addfile(ti, io.BytesIO(data))
    seen: dict = {}

    def download(url, dest, timeout=0, sha256=None, **_k):
        seen.update(url=url, sha256=sha256)
        Path(dest).write_bytes(buf.getvalue())

    def no_api(*a, **k):
        raise AssertionError("pinned install must not call the GitHub API")
    st = userspace.install_gh(M["user_space"]["gh"], fetch=no_api, download=download)
    assert st.startswith("INSTALLED gh v2.102.0")
    assert seen["url"] == "https://github.com/cli/cli/releases/download/v2.102.0/gh_2.102.0_linux_amd64.tar.gz"
    assert seen["sha256"] == M["user_space"]["gh"]["sha256"]["amd64"]
    assert (tmp_path / ".local" / "bin" / "gh").is_file()


def test_gh_is_a_warn_when_the_hash_does_not_match(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(userspace, "os_arch", lambda: ("linux", "x64"))

    def download(url, dest, timeout=0, sha256=None, **_k):
        raise OSError("checksum mismatch")
    assert userspace.install_gh(M["user_space"]["gh"], download=download).startswith("WARN")
    assert not (tmp_path / ".local" / "bin" / "gh").exists()
