"""test_statusline_win.py — the Windows-motivated statusline fixes (audit A3), proven on every OS.

Split from test_statusline.py (250-line cap); the fixtures and payload helpers live there.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_statusline import SCRIPT, cache, full_payload, repo, run  # noqa: F401 (fixtures)

GOOD = {"b": "main", "ahead": 0, "behind": 0, "staged": 1, "mod": 1, "new": 1}


def _module():
    spec = importlib.util.spec_from_file_location("statusline_p1", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_warm_path_skips_openssl(run, repo, cache):
    """hashlib (OpenSSL DLL) and tempfile cost 27-29 ms of a 150 ms Windows run (A3-01); a warm hit
    needs neither, nor subprocess."""
    pl = full_payload(repo)
    run(pl)
    base = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "COLUMNS")}
    base.update(CLAUDE_STATUSLINE_CACHE_DIR=str(cache), NO_COLOR="1")
    p = subprocess.run([sys.executable, "-X", "importtime", str(SCRIPT)], input=json.dumps(pl).encode(),
                       capture_output=True, env=base, cwd=str(repo), timeout=10)
    mods = {ln.rsplit("|", 1)[1].strip() for ln in p.stderr.decode("utf-8", "replace").splitlines()
            if ln.startswith("import time:") and "|" in ln}
    assert p.returncode == 0 and "⎇ main" in p.stdout.decode()
    assert not mods & {"hashlib", "tempfile", "subprocess"}, sorted(mods & {"hashlib", "tempfile", "subprocess"})


def test_failed_replace_leaves_no_tmp(cache, monkeypatch):
    """Windows refuses os.replace while another process has the cache open; the tmp file named
    after the pid must not pile up (A3-02)."""
    sl = _module()
    monkeypatch.setenv("CLAUDE_STATUSLINE_CACHE_DIR", str(cache))
    monkeypatch.setattr(sl, "_git_status", lambda cwd: dict(GOOD))

    def deny(src, dst):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(sl.os, "replace", deny)
    assert sl.git_info("x") == GOOD
    assert list(cache.iterdir()) == []


def _slow_git(sl, cache, monkeypatch, age_s):
    """A cache entry ``age_s`` old and a git that times out on every call; returns (path, calls)."""
    monkeypatch.setenv("CLAUDE_STATUSLINE_CACHE_DIR", str(cache))
    cache.mkdir()
    path = Path(sl._cache_path("D:/big/repo"))
    path.write_text(json.dumps({"t": time.time() - age_s, "g": GOOD}), encoding="utf-8")
    calls: list = []

    def slow(cwd):
        calls.append(cwd)
        raise subprocess.TimeoutExpired("git", 1.5)
    monkeypatch.setattr(sl, "_git_status", slow)
    return path, calls


def test_timeout_keeps_a_recent_good_git_and_restamps_it(cache, monkeypatch):
    """A git timeout must not overwrite the last good entry with a miss (A3-03), and the entry is
    re-stamped so the 5 s TTL applies: no GIT_TIMEOUT wait on every refresh (SANTA P1)."""
    sl = _module()
    path, calls = _slow_git(sl, cache, monkeypatch, 10)
    before = time.time()
    assert sl.git_info("D:/big/repo") == GOOD and len(calls) == 1
    assert json.loads(path.read_text(encoding="utf-8"))["t"] >= before
    assert sl.git_info("D:/big/repo") == GOOD and len(calls) == 1  # inside the TTL: git is not asked again
    monkeypatch.setattr(sl, "_git_status", lambda cwd: None)  # a real "not a repo" is still cached
    path.write_text(json.dumps({"t": time.time() - 30, "g": GOOD}), encoding="utf-8")
    assert sl.git_info("D:/big/repo") is None
    assert json.loads(path.read_text(encoding="utf-8"))["g"] is None


def test_timeout_never_returns_a_git_summary_older_than_a_minute(cache, monkeypatch):
    """Frozen branch / dirty counts after a `git switch` while git status keeps timing out (SANTA P1)."""
    sl = _module()
    path, calls = _slow_git(sl, cache, monkeypatch, 3600)
    assert sl.git_info("D:/big/repo") is None and len(calls) == 1
    assert sl.git_info("D:/big/repo") is None and len(calls) == 1  # re-stamped: no second wait, still None
    assert json.loads(path.read_text(encoding="utf-8"))["t"] > time.time() - 5
    path.write_text(json.dumps({"t": time.time() - 61, "g": GOOD}), encoding="utf-8")
    assert sl.git_info("D:/big/repo") is None
    path.write_text(json.dumps({"t": time.time() - 59, "g": GOOD}), encoding="utf-8")
    assert sl.git_info("D:/big/repo") == GOOD
    monkeypatch.setattr(sl, "_git_status", lambda cwd: dict(GOOD))  # git answers again: fresh, returned
    path.write_text(json.dumps({"t": time.time() - 7200, "g": None}), encoding="utf-8")
    assert sl.git_info("D:/big/repo") == GOOD


def test_git_timeout_is_longer_on_windows():
    assert _module().GIT_TIMEOUT == (1.5 if os.name == "nt" else 0.5)


def test_cache_key_and_dir_need_no_hashlib_or_tempfile(monkeypatch, tmp_path):
    sl = _module()
    assert re.fullmatch(r".*[\\/][0-9a-f]{16}\.json", sl._cache_path("E:/prof/.claude"))
    assert sl._cache_path("a") != sl._cache_path("b")
    for var in ("CLAUDE_STATUSLINE_CACHE_DIR", "XDG_RUNTIME_DIR", "TMPDIR", "TEMP", "TMP"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TEMP", str(tmp_path))
    assert Path(sl._cache_dir()).parent == tmp_path
    monkeypatch.delenv("TEMP")
    (tmp_path / "t").mkdir()  # a TMP that does not exist is "dead" now (falls back, see below)
    monkeypatch.setenv("TMP", str(tmp_path / "t"))
    assert Path(sl._cache_dir()).parent == tmp_path / "t"
    monkeypatch.delenv("TMP")
    import tempfile  # nothing usable in the env: the same answer main gave (A3v2-05), not the drive-relative \tmp
    assert Path(sl._cache_dir()).parent == Path(tempfile.gettempdir())


def _no_temp_env(monkeypatch):
    for var in ("CLAUDE_STATUSLINE_CACHE_DIR", "XDG_RUNTIME_DIR", "TMPDIR", "TEMP", "TMP"):
        monkeypatch.delenv(var, raising=False)


def test_a_dead_temp_dir_falls_back_to_a_writable_one(monkeypatch, tmp_path):
    """TEMP on a removed drive / RAM disk: main picked tempfile's writable fallback; so does this (A3v2-05)."""
    sl = _module()
    _no_temp_env(monkeypatch)
    dead = tmp_path / "gone"  # never created
    monkeypatch.setenv("TEMP", str(dead))
    monkeypatch.setenv("TMP", str(dead))
    parent = Path(sl._cache_dir()).parent
    assert parent != dead and parent.is_dir()


def test_a_usable_temp_dir_never_imports_tempfile(monkeypatch, tmp_path):
    sl = _module()
    _no_temp_env(monkeypatch)
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setitem(sys.modules, "tempfile", None)  # `import tempfile` now raises ImportError
    assert Path(sl._cache_dir()).parent == tmp_path


def test_a_fresh_cache_entry_means_no_git_call(cache, monkeypatch):
    """The warm path is fast because git is not asked (A3v2-06): a call count, not a stopwatch."""
    sl = _module()
    monkeypatch.setenv("CLAUDE_STATUSLINE_CACHE_DIR", str(cache))
    calls: list = []
    monkeypatch.setattr(sl, "_git_status", lambda cwd: calls.append(cwd) or dict(GOOD))
    assert sl.git_info("D:/x") == GOOD and sl.git_info("D:/x") == GOOD and sl.git_info("D:/x") == GOOD
    assert len(calls) == 1


def test_a_git_child_holding_the_pipe_cannot_extend_the_timeout(tmp_path, monkeypatch):
    """`subprocess.run(timeout=)` kills git, then waits for every process that inherited the stdout pipe (a
    fsmonitor hook, the cmd\\git.exe launcher's real git): the refresh took git's full duration and then
    threw the answer away (A3v2-01). The whole tree must die at the timeout."""
    sl = _module()
    beat = tmp_path / "beat"
    grand = (f"import time\nt = time.time()\nwhile time.time() - t < 12:\n"
             f"    open({str(beat)!r}, 'w').write('x')\n    time.sleep(0.1)\n")
    child = f"import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', {grand!r}])\ntime.sleep(60)\n"
    monkeypatch.setattr(sl, "GIT_ARGV", [sys.executable, "-c", child], raising=False)
    monkeypatch.setattr(sl, "GIT_TIMEOUT", 1.5)
    t0 = time.perf_counter()
    with pytest.raises(subprocess.TimeoutExpired):
        sl._git_status(str(tmp_path))
    assert time.perf_counter() - t0 < 6, "waited for the grandchild that still held the pipe (12 s)"
    time.sleep(0.4)
    if beat.exists():  # started before the kill: it must be dead now
        seen = beat.stat().st_mtime_ns
        time.sleep(1.0)
        assert beat.stat().st_mtime_ns == seen


def test_a_character_utf8_cannot_encode_never_crashes(run):
    """A lone surrogate is valid JSON (NTFS names, Node strings) but not encodable: replaced, not a traceback
    and a blank line (A3v2-04)."""
    p = run(raw=json.dumps({"model": {"display_name": "A\ud800B"}}).encode())
    assert p.returncode == 0 and p.stderr == b""
    assert p.stdout.decode("utf-8") == "◆ A?B\n"


def test_stdout_is_lf(run, repo):
    """Windows text mode turns \\n into \\r\\n (A3-05)."""
    out = run(full_payload(repo)).stdout
    assert out.endswith(b"\n") and not out.endswith(b"\r\n") and b"\r" not in out


def test_bom_stdin_parses(run):
    """PowerShell 5.1 pipes put a UTF-8 BOM in front of the JSON (A3-07)."""
    raw = b"\xef\xbb\xbf" + json.dumps({"model": {"display_name": "Opus 4.7"}}).encode()
    assert "◆ Opus 4.7" in run(raw=raw).stdout.decode()


def test_stdout_utf8_without_pythonutf8(run, repo):
    """No PYTHONUTF8 and a cp1252 default: redirected stdout must still be UTF-8 (A3-08)."""
    p = run(full_payload(repo), env={"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"})
    assert p.returncode == 0 and p.stderr == b""
    assert "▰▰▰▰▱▱▱▱▱▱".encode("utf-8") in p.stdout and p.stdout.decode("utf-8")
