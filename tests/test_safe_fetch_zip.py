"""safe_fetch.extract_zip_prefix: the contained zip twin of extract_prefix (A5-14).

Windows assets (node, gh, uv, ollama) are zips. A crafted archive must never write outside the
prefix, make a symlink, create a Windows-reserved name or a path past MAX_PATH, and an interrupted
extraction must never leave a half-installed tool. Pure zipfile in memory, any OS.
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import safe_fetch  # noqa: E402

SYMLINK_ATTR = 0o120777 << 16  # S_IFLNK | 0777 in the high 16 bits (external_attr >> 28 == 0xA)


def _zip(entries) -> zipfile.ZipFile:
    """entries: (name, data) or (name, data, external_attr)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for e in entries:
            name, data = e[0], e[1]
            zi = zipfile.ZipInfo(name)
            if len(e) > 2:
                zi.external_attr = e[2]
            zf.writestr(zi, data)
    return zipfile.ZipFile(io.BytesIO(buf.getvalue()))


@pytest.fixture
def dest(tmp_path):
    return tmp_path / "tools" / "node"


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_wrapper_dir_is_stripped_and_only_filters(dest):
    zf = _zip([("node-v22/node.exe", b"N"), ("node-v22/npm.cmd", b"C"), ("node-v22/lib/x.js", b"j")])
    assert safe_fetch.extract_zip_prefix(zf, dest) == 3
    assert _files(dest) == {"node.exe", "npm.cmd", "lib/x.js"}
    only = tmp = dest.parent / "only"
    assert safe_fetch.extract_zip_prefix(zf, only, only=lambda p: p.startswith("lib/")) == 1
    assert _files(tmp) == {"lib/x.js"}


def test_strip_zero_keeps_the_top_level(dest):
    zf = _zip([("ollama.exe", b"O"), ("lib/ollama/a.dll", b"d")])
    assert safe_fetch.extract_zip_prefix(zf, dest, strip=0) == 2
    assert _files(dest) == {"ollama.exe", "lib/ollama/a.dll"}


@pytest.mark.parametrize("strip", [0, 1])
def test_escaping_names_are_skipped(dest, strip):
    evil = ["../evil", "w/../evil", "/abs/evil", "c:\\x", "w/c:/x", "w/f:stream", "a\\..\\..\\b", "\\root\\evil"]
    zf = _zip([("w/good.txt", b"ok"), *[(n, b"x") for n in evil]])
    safe_fetch.extract_zip_prefix(zf, dest, strip=strip)
    got = _files(dest)
    assert got <= {"good.txt", "w/good.txt"}, got
    outside = {p.name for p in dest.parent.rglob("*") if p.is_file()} - {"good.txt"}
    assert outside <= set(), outside


def test_symlink_entries_are_skipped(dest):
    zf = _zip([("w/ok.txt", b"ok"), ("w/link", b"/etc/passwd", SYMLINK_ATTR)])
    safe_fetch.extract_zip_prefix(zf, dest)
    assert _files(dest) == {"ok.txt"} and not (dest / "link").exists() and not (dest / "link").is_symlink()


@pytest.mark.parametrize("bad", ["nul.txt", "CON", "com1.log", "Lpt9", "aux.", "trail.", "space ", "d/NUL/x.txt",
                                 "COM¹", "lpt².txt", "COM³.log", "CONOUT$", "conin$", "d/CONIN$/x"])  # SEC1B-11
def test_windows_reserved_and_trailing_dot_space_names_are_skipped(dest, bad):
    zf = _zip([("w/ok.txt", b"ok"), (f"w/{bad}", b"x")])
    safe_fetch.extract_zip_prefix(zf, dest)
    assert _files(dest) == {"ok.txt"}


def test_a_path_longer_than_240_chars_fails_the_whole_extraction(dest):
    """A real file that cannot be written would leave a tool without part of itself (ollama.exe
    without `lib/`): the extraction fails and dest is never created (the caller reports a WARN)."""
    assert safe_fetch.MAX_PATH == 240
    zf = _zip([("w/" + "b" * 300, b"2"), ("w/ok", b"3")])
    with pytest.raises(OSError, match="too long"):
        safe_fetch.extract_zip_prefix(zf, dest)
    assert not dest.exists()


def test_the_length_limit_counts_the_whole_final_path(dest, monkeypatch):
    """Same rule at a limit this scratch dir can reach: the dest prefix counts, not just the name."""
    monkeypatch.setattr(safe_fetch, "MAX_PATH", len(str(dest.resolve())) + 40)
    with pytest.raises(OSError, match="too long"):
        safe_fetch.extract_zip_prefix(_zip([("w/" + "a" * 10, b"1"), ("w/" + "b" * 60, b"2")]), dest)
    safe_fetch.extract_zip_prefix(_zip([("w/" + "a" * 10, b"1")]), dest)
    assert _files(dest) == {"a" * 10}


def test_the_limit_judges_the_installed_path_not_the_pid_tmp_dir(dest, monkeypatch):
    """`<dest>.tmp-<pid>` is longer than dest; a file whose final path fits must still land
    (a 5-digit pid pushed a 231-char ollama lib path past 240 and it was silently dropped)."""
    name = "a" * 10
    monkeypatch.setattr(safe_fetch, "MAX_PATH", len(str((dest / name).resolve())))
    safe_fetch.extract_zip_prefix(_zip([("w/" + name, b"1")]), dest)
    assert _files(dest) == {name}


def test_extraction_lands_through_a_pid_tmp_dir_then_one_rename(dest, monkeypatch):
    seen = []
    real = os.replace

    def spy(a, b, *x, **k):
        seen.append((Path(a), Path(b)))
        return real(a, b, *x, **k)
    monkeypatch.setattr(safe_fetch.os, "replace", spy)
    safe_fetch.extract_zip_prefix(_zip([("w/a.txt", b"a")]), dest)
    assert (dest.with_name(dest.name + f".tmp-{os.getpid()}"), dest) in seen
    assert not list(dest.parent.glob("*.tmp-*"))


def test_an_interrupted_extraction_leaves_no_dest_and_no_tmp(dest, monkeypatch):
    calls = {"n": 0}
    real = safe_fetch.shutil.copyfileobj

    def boom(src, dst, *a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(safe_fetch.shutil, "copyfileobj", boom)
    with pytest.raises(OSError):
        safe_fetch.extract_zip_prefix(_zip([("w/a", b"a"), ("w/b", b"b"), ("w/c", b"c")]), dest)
    assert not dest.exists() and not list(dest.parent.glob("*.tmp-*"))


def _denied(times):
    """An ``os.replace`` that fails with Windows' ACCESS_DENIED ``times`` times (Defender / the indexer hold
    a fresh file open), then works."""
    real, left = os.replace, {"n": times}

    def replace(a, b, *x, **k):
        if left["n"] > 0:
            left["n"] -= 1
            raise PermissionError(5, "Access is denied")
        return real(a, b, *x, **k)
    return replace, left


@pytest.mark.parametrize("existing", [False, True])
def test_a_denied_rename_is_retried_so_the_tool_still_lands(dest, monkeypatch, existing):
    """A5v2-02: one PermissionError on the extraction dir's rename used to lose the whole tool."""
    if existing:
        dest.mkdir(parents=True)
        (dest / "old.txt").write_bytes(b"o")
    replace, left = _denied(2)
    monkeypatch.setattr(safe_fetch.os, "replace", replace)
    monkeypatch.setattr(safe_fetch.time, "sleep", lambda s: None)
    assert safe_fetch.extract_zip_prefix(_zip([("w/a.txt", b"a")]), dest) == 1
    assert left["n"] == 0 and "a.txt" in _files(dest) and not list(dest.parent.glob("*.tmp-*"))


def test_a_rename_denied_for_good_raises_after_the_wait_and_leaves_no_tmp(dest, monkeypatch):
    replace, _ = _denied(10 ** 6)
    monkeypatch.setattr(safe_fetch.os, "replace", replace)
    monkeypatch.setattr(safe_fetch.time, "sleep", lambda s: None)
    monkeypatch.setattr(safe_fetch, "RENAME_WAIT_S", 0.05)
    with pytest.raises(PermissionError):
        safe_fetch.extract_zip_prefix(_zip([("w/a.txt", b"a")]), dest)
    assert not dest.exists() and not list(dest.parent.glob("*.tmp-*"))


def test_only_a_dead_pids_tmp_dir_is_swept_a_live_peers_survives(dest, monkeypatch):
    """A5v2-04: a second installer / the daily self-heal used to delete every ``<dest>.tmp-*`` of any pid."""
    dest.parent.mkdir(parents=True)
    live, dead, own, odd = (dest.with_name(f"node.tmp-{n}") for n in (424242, 999999, os.getpid(), "abc"))
    for d in (live, dead, own, odd):
        (d / "sub").mkdir(parents=True)
    monkeypatch.setattr(safe_fetch, "pid_alive", lambda pid: pid in (424242, os.getpid()))
    safe_fetch.extract_zip_prefix(_zip([("w/a.txt", b"a")]), dest)
    assert live.is_dir() and not dead.exists() and not own.exists() and not odd.exists()
    assert _files(dest) == {"a.txt"}


def test_an_existing_dest_is_repaired_in_place_keeping_unrelated_files(dest):
    dest.mkdir(parents=True)
    (dest / "node.exe").write_bytes(b"truncated")
    (dest / "keep.txt").write_bytes(b"mine")
    safe_fetch.extract_zip_prefix(_zip([("w/node.exe", b"FULL"), ("w/lib/x", b"x")]), dest)
    assert (dest / "node.exe").read_bytes() == b"FULL"
    assert (dest / "keep.txt").read_bytes() == b"mine" and (dest / "lib" / "x").is_file()
