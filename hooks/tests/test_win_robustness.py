"""W6b hook robustness on Windows, part 1: spawning, console windows, atomic writes and
appends (A4-02, A4-03, A4-04, A4-05). Part 2: ``test_win_platform_locks.py``; part 3:
``test_win_robustness_hooks.py``.

Every Windows branch is driven with ``plat.IS_WINDOWS`` monkeypatched, so this file runs
the same on Ubuntu and Windows (stub ``Popen`` / ``os.replace``). One test runs the real
thing (4 processes appending).
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import time
import types

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import dispatch  # noqa: E402
import dispatch_support as ds  # noqa: E402
from lib import hook_telemetry as tel  # noqa: E402
from lib import platform as plat  # noqa: E402

CNW_NG = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
DETACHED = 0x00000008


class _Stdin:
    def __init__(self):
        self.text, self.closed = "", False

    def write(self, s):
        self.text += s

    def close(self):
        self.closed = True


@pytest.fixture
def popen(monkeypatch):
    rec: list = []

    class _Popen:
        def __init__(self, cmd, **kw):
            self.pid, self.stdin = 4242, _Stdin()
            rec.append((cmd, kw, self))

    monkeypatch.setattr(subprocess, "Popen", _Popen)
    return rec


def _os(monkeypatch, windows: bool):
    monkeypatch.setattr(plat, "IS_WINDOWS", windows)


# --------------------------------------------------------------------------- #
# A4-02 / A4-03: one spawn helper, no visible console window
# --------------------------------------------------------------------------- #
_SPAWNS = [
    pytest.param(lambda: plat.spawn_worker(["x"]), id="spawn_worker"),
    pytest.param(lambda: plat.spawn_detached(["x"]), id="spawn_detached"),
    pytest.param(lambda: dispatch._spawn_async({"id": "t", "cmd": ["x"]}, "SessionStart", "{}", "sid"),
                 id="dispatch._spawn_async"),
    pytest.param(lambda: ds.spawn_deferred(["x"], 5, "{}", "sid", "SessionStart", "t"),
                 id="dispatch_support.spawn_deferred"),
]


@pytest.mark.parametrize("spawn", _SPAWNS)
def test_every_background_spawn_uses_no_window_flags_on_windows(monkeypatch, popen, spawn):
    _os(monkeypatch, True)
    spawn()
    kw = popen[-1][1]
    assert kw["creationflags"] == CNW_NG
    assert not kw["creationflags"] & DETACHED  # DETACHED_PROCESS voids CREATE_NO_WINDOW
    assert "start_new_session" not in kw


@pytest.mark.parametrize("spawn", _SPAWNS)
def test_every_background_spawn_starts_a_new_session_on_posix(monkeypatch, popen, spawn):
    _os(monkeypatch, False)
    spawn()
    kw = popen[-1][1]
    assert kw["start_new_session"] is True and "creationflags" not in kw


def test_spawn_worker_hands_stdin_text_over_as_a_file_not_a_pipe(monkeypatch):
    """A4v2-06: a pipe would block the caller past 4 KB on Windows; the child reads a file instead."""
    _os(monkeypatch, False)
    got: list = []

    class _Popen:
        pid = 4242

        def __init__(self, cmd, **kw):
            got.append((kw["stdin"] is not subprocess.PIPE, kw["stdin"].read()))  # the stub is the "child"
    monkeypatch.setattr(subprocess, "Popen", _Popen)
    assert plat.spawn_worker(["x"], stdin_text="payloadé") == 4242
    assert got == [(True, "payloadé".encode("utf-8"))]
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: got.append(kw["stdin"]) or types.SimpleNamespace(pid=1))
    plat.spawn_worker(["x"])
    assert got[-1] == subprocess.DEVNULL


def test_spawn_worker_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("no")
    monkeypatch.setattr(subprocess, "Popen", boom)
    assert plat.spawn_worker(["x"]) is None


def test_captured_children_get_no_window_on_windows(monkeypatch):
    """A hook process without a console must not make git / jcodemunch / npm / taskkill
    pop one: every captured synchronous spawn carries CREATE_NO_WINDOW."""
    _os(monkeypatch, True)
    seen: list = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(kw) or
                        subprocess.CompletedProcess(cmd, 0, "", ""))
    plat.run(["git", "status"])
    plat.kill_tree(99)
    assert [kw.get("creationflags") for kw in seen] == [0x08000000, 0x08000000]
    _os(monkeypatch, False)
    seen.clear()
    plat.run(["git", "status"])
    assert "creationflags" not in seen[0]


def test_popen_new_group_hides_the_window_only_when_output_is_redirected(monkeypatch, popen):
    _os(monkeypatch, True)
    plat.popen_new_group(["x"])  # inherited console stays (old behaviour)
    assert popen[-1][1]["creationflags"] == 0x00000200
    plat.popen_new_group(["x"], stdout=subprocess.DEVNULL)
    assert popen[-1][1]["creationflags"] == 0x00000200 | 0x08000000


def test_index_lifecycle_fallback_spawn_uses_no_window_flags(monkeypatch, popen):
    spec = importlib.util.spec_from_file_location("il_w6b", _HOOKS / "index-lifecycle.py")
    il = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(il)
    monkeypatch.setattr(il, "_LIBS_OK", False)  # the path taken when lib failed to import
    monkeypatch.setattr(il, "os", types.SimpleNamespace(name="nt"))
    il._spawn_detached(["x"])
    assert popen[-1][1]["creationflags"] == CNW_NG


def test_dispatch_rewrite_guard_uses_the_shared_shell_tool_set():
    import tool_compat
    assert dispatch._is_shell_tool is tool_compat.is_shell_tool and dispatch._is_shell_tool("Bash")


# --------------------------------------------------------------------------- #
# A4-04: atomic_write retries os.replace on Windows
# --------------------------------------------------------------------------- #
def _flaky_replace(monkeypatch, fails: int):
    real, calls = os.replace, []

    def fake(src, dst):
        calls.append(1)
        if len(calls) <= fails:
            raise PermissionError(13, "[WinError 5] Access is denied")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", fake)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return calls


def test_atomic_write_retries_a_denied_replace_on_windows(monkeypatch, tmp_path):
    _os(monkeypatch, True)
    calls = _flaky_replace(monkeypatch, 19)
    assert plat.atomic_write(tmp_path / "f.json", "ok") is True
    assert (tmp_path / "f.json").read_text(encoding="utf-8") == "ok" and len(calls) == 20


def test_atomic_write_gives_up_after_20_tries_and_leaves_no_temp(monkeypatch, tmp_path):
    _os(monkeypatch, True)
    calls = _flaky_replace(monkeypatch, 99)
    assert plat.atomic_write(tmp_path / "f.json", "ok") is False
    assert len(calls) == 20 and list(tmp_path.iterdir()) == []


def test_atomic_write_tries_once_on_posix(monkeypatch, tmp_path):
    _os(monkeypatch, False)
    calls = _flaky_replace(monkeypatch, 1)
    assert plat.atomic_write(tmp_path / "f.json", "ok") is False and len(calls) == 1


# --------------------------------------------------------------------------- #
# A4-05: append_line
# --------------------------------------------------------------------------- #
_APPENDER = (
    "import sys; sys.path.insert(0, sys.argv[1])\n"
    "from lib import platform as p\n"
    "for i in range(int(sys.argv[4])):\n"
    "    p.append_line(sys.argv[2], ('%s-%d\\n' % (sys.argv[3], i)).encode())\n")


def test_append_line_loses_nothing_across_four_processes(tmp_path):
    target, n = tmp_path / "q.jsonl", 500
    procs = [subprocess.Popen([sys.executable, "-c", _APPENDER, str(_HOOKS), str(target), f"w{k}", str(n)])
             for k in range(4)]
    assert [p.wait(timeout=120) for p in procs] == [0] * 4
    raw = target.read_bytes()
    assert b"\r" not in raw
    assert set(raw.decode().split("\n")[:-1]) == {f"w{k}-{i}" for k in range(4) for i in range(n)}


def test_append_line_takes_the_sidecar_lock_on_windows_only(monkeypatch, tmp_path):
    held: list = []
    monkeypatch.setattr(plat, "_lock", lambda fh, timeout=1.0: held.append(fh.name))
    _os(monkeypatch, True)
    assert plat.append_line(tmp_path / "t.jsonl", b"a\n") is True
    assert held == [str(tmp_path / "t.jsonl") + ".lock"]
    _os(monkeypatch, False)
    assert plat.append_line(tmp_path / "t.jsonl", b"b\n") is True
    assert len(held) == 1 and (tmp_path / "t.jsonl").read_bytes() == b"a\nb\n"


def test_append_line_still_writes_when_the_lock_times_out(monkeypatch, tmp_path):
    def stuck(fh, timeout=1.0):
        raise OSError("held")
    monkeypatch.setattr(plat, "_lock", stuck)
    _os(monkeypatch, True)
    assert plat.append_line(tmp_path / "t.jsonl", b"a\n") is True


def test_append_line_reports_failure(tmp_path):
    assert plat.append_line(tmp_path / "no-such-dir" / "t.jsonl", b"a\n") is False


def test_enqueue_and_telemetry_append_through_append_line(monkeypatch, tmp_path):
    rec: list = []
    monkeypatch.setattr(plat, "append_line", lambda p, data: rec.append((str(p), data)) or True)
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "st"))
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    assert ds.enqueue("sid-1", "lnk", "ctx text") is True
    tel.record("PreToolUse", "lnk", ms=1)
    assert rec[0][0].endswith("sid-1.jsonl") and json.loads(rec[0][1])["ctx"] == "ctx text"
    assert rec[1][0].endswith(".jsonl") and json.loads(rec[1][1])["link_id"] == "lnk"
