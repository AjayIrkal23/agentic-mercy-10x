"""Tests for hooks/session-ledger.py (L4 live-session ledger).

The ledger exists because a SIGKILLed session never runs SessionEnd: an entry whose
pid is dead and whose `ended` is null is a killed session that restore_sessions.py may
bring back. Pure stdlib + pytest; the module is driven in-process.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("session_ledger_under_test", _HOOKS / "session-ledger.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sl = _load()
DEAD_PID = 4190000
ZERO_BOOT = "00000000-0000-0000-0000-000000000000"
S1 = "5f0c3a3e-1d2b-4c5d-9e8f-0a1b2c3d4e5f"  # Claude Code session ids are UUIDs; mode_start ignores anything else (O6)


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(sl, "_claude_pid", lambda *a, **k: 4242)
    return tmp_path / "state"


def _main(argv, payload):
    stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    old = sys.stdin
    sys.stdin = stdin
    try:
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = sl.main(argv)
    finally:
        sys.stdin = old
    return rc, buf.getvalue().strip()


def _entry(state: Path, sid: str):
    p = state / "live-sessions" / f"{sid}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _start(tmp_path, sid=S1, source="startup", cwd=None):
    cwd = cwd or str(tmp_path)
    return _main(["start"], {"session_id": sid, "source": source, "cwd": cwd,
                             "transcript_path": str(tmp_path / "t.jsonl")})


def _git_repo(where: Path) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(where)], check=True)
    return where


def test_start_writes_the_ledger_entry(tmp_path, _state):
    repo = _git_repo(tmp_path / "repo")
    rc, _ = _start(tmp_path, cwd=str(repo))
    assert rc == 0
    e = _entry(_state, S1)
    for k in ("sid", "pid", "cwd", "transcript", "tmux", "scope", "started", "seen", "ended", "restored"):
        assert k in e
    assert e["pid"] == 4242 and e["ended"] is None and e["restored"] is False
    assert isinstance(e["started"], int) and e["started"] == e["seen"]
    assert isinstance(e["boot_id"], (str, type(None)))
    if sl.current_boot_id() is not None:
        assert isinstance(e["boot_id"], str)
    assert e["cwd"] == str(repo)


def test_startup_prints_a_session_title_resume_and_compact_do_not(tmp_path):
    repo = _git_repo(tmp_path / "myrepo")
    rc, out = _start(tmp_path, cwd=str(repo))
    d = json.loads(out)
    hso = d["hookSpecificOutput"]
    assert hso["hookEventName"] == "SessionStart"
    assert hso["sessionTitle"] == f"myrepo {time.strftime('%Y-%m-%d')}"
    for source in ("resume", "compact", "clear"):
        rc, out = _start(tmp_path, source=source, cwd=str(repo))
        assert rc == 0 and json.loads(out) == {}


def test_title_uses_the_git_root_name(tmp_path):
    repo = _git_repo(tmp_path / "rootname")
    sub = repo / "sub" / "dir"
    sub.mkdir(parents=True)
    _, out = _start(tmp_path, cwd=str(sub))
    assert json.loads(out)["hookSpecificOutput"]["sessionTitle"].startswith("rootname ")


def test_resume_keeps_started_and_refreshes_seen_and_pid(tmp_path, _state, monkeypatch):
    monkeypatch.setattr(sl, "_now", lambda: 1000)
    _start(tmp_path)
    e = _entry(_state, S1)
    e["restored"] = True
    sl.write_entry(e)
    monkeypatch.setattr(sl, "_now", lambda: 1500)
    monkeypatch.setattr(sl, "_claude_pid", lambda *a, **k: 7)
    _start(tmp_path, source="resume")
    e = _entry(_state, S1)
    assert e["started"] == 1000 and e["seen"] == 1500 and e["pid"] == 7
    assert e["restored"] is True


def test_end_deletes_the_entry(tmp_path, _state):
    _start(tmp_path)
    rc, out = _main(["end"], {"session_id": S1, "reason": "prompt_input_exit"})
    assert rc == 0 and json.loads(out) == {}
    assert _entry(_state, S1) is None


def test_end_marks_ended_when_the_unlink_fails(tmp_path, _state, monkeypatch):
    _start(tmp_path)

    def boom(path):
        raise OSError("busy")

    monkeypatch.setattr(sl, "_unlink", boom)
    rc, out = _main(["end"], {"session_id": S1, "reason": "other"})
    assert rc == 0 and json.loads(out) == {}
    e = _entry(_state, S1)
    assert isinstance(e["ended"], int)


@pytest.mark.parametrize("sid", ["doctor-fixture", "verify-hookrt-r2-ss2", "s1", "5f0c3a3e-1d2b-4c5d-9e8f"])
def test_start_ignores_non_uuid_session_ids(tmp_path, _state, sid):
    rc, out = _start(tmp_path, sid=sid)
    assert rc == 0 and json.loads(out) == {}
    assert _entry(_state, sid) is None and not list((_state / "live-sessions").glob("*.json"))


def test_start_under_doctor_replay_writes_nothing(tmp_path, _state, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    rc, out = _start(tmp_path)
    assert rc == 0 and json.loads(out) == {}
    assert _entry(_state, S1) is None


def test_start_accepts_an_uppercase_uuid(tmp_path, _state):
    _start(tmp_path, sid=S1.upper())
    assert _entry(_state, S1.upper())["sid"] == S1.upper()


def test_end_without_an_entry_is_a_silent_noop(_state):
    rc, out = _main(["end"], {"session_id": "nope", "reason": "other"})
    assert rc == 0 and json.loads(out) == {}
    assert _entry(_state, "nope") is None


def _hand(sid, **over):
    e = {"sid": sid, "pid": DEAD_PID, "cwd": "/tmp", "transcript": None, "tmux": None, "scope": None,
         "started": sl._now() - 100, "seen": sl._now() - 100, "ended": None, "restored": False}
    e.update(over)
    assert sl.write_entry(e)
    return e


def test_classify_and_dead_entries():
    now = sl._now()
    a = _hand("A", started=now - 100)
    _hand("B", started=now - 10000, seen=None)
    _hand("C", pid=os.getpid())
    _hand("D", ended=now - 5)
    g = sl.classify(7200)
    assert [e["sid"] for e in g["eligible"]] == ["A"]
    assert [e["sid"] for e in g["stale"]] == ["B"]
    assert [e["sid"] for e in g["ended"]] == ["D"]
    assert [e["sid"] for e in g["live"]] == ["C"]
    assert sl.dead_entries(7200) == [a]


def test_seen_heartbeat_keeps_an_old_session_eligible():
    now = sl._now()
    _hand("H", started=now - 20000, seen=now - 60)
    assert [e["sid"] for e in sl.dead_entries(7200)] == ["H"]


def test_max_age_boundary():
    now = 10_000_000
    _hand("edge", started=now - 7200, seen=None)
    _hand("over", started=now - 7201, seen=None)
    g = sl.classify(7200, now=now)
    assert [e["sid"] for e in g["eligible"]] == ["edge"]
    assert [e["sid"] for e in g["stale"]] == ["over"]


def test_other_boot_id_counts_as_dead_even_if_the_pid_is_alive():
    if sl.current_boot_id() is None:
        pytest.skip("no boot_id on this platform")
    _hand("rb", pid=os.getpid(), boot_id=ZERO_BOOT)
    g = sl.classify(7200)
    assert [e["sid"] for e in g["eligible"]] == ["rb"]
    assert g["live"] == []


def test_dead_entries_are_sorted_by_started():
    now = sl._now()
    _hand("late", started=now - 10, seen=None)
    _hand("early", started=now - 500, seen=None)
    _hand("mid", started=now - 200, seen=None)
    assert [e["sid"] for e in sl.dead_entries(7200)] == ["early", "mid", "late"]


def test_mark_restored(_state):
    _hand("m", title="x 2026-01-01")
    assert sl.mark_restored("m") is True
    e = _entry(_state, "m")
    assert e["restored"] is True and isinstance(e["restored_at"], int)
    assert e["title"] == "x 2026-01-01" and e["pid"] == DEAD_PID
    assert sl.mark_restored("missing") is False
    assert _entry(_state, "missing") is None


def _proc(root: Path, pid: int, ppid: int, comm: str, cmdline: str) -> None:
    d = root / str(pid)
    d.mkdir(parents=True)
    (d / "stat").write_text(f"{pid} ({comm}) S {ppid} {pid} {pid} 0 -1 4194304", encoding="utf-8")
    (d / "status").write_text(f"Name:\t{comm}\nState:\tS\nPid:\t{pid}\nPPid:\t{ppid}\n", encoding="utf-8")
    (d / "comm").write_text(comm + "\n", encoding="utf-8")
    (d / "cmdline").write_text(cmdline, encoding="utf-8")


@pytest.mark.parametrize("use_lib_chain", [False, True])
def test_claude_pid_walks_the_proc_chain(tmp_path, monkeypatch, use_lib_chain):
    real = _load()  # the autouse fixture stubbed sl._claude_pid
    if not use_lib_chain:
        monkeypatch.setattr(real.plat, "proc_chain", None, raising=False)
    elif not callable(getattr(real.plat, "proc_chain", None)):
        pytest.skip("lib.platform has no proc_chain here")
    proc = tmp_path / "proc"
    _proc(proc, 300, 200, "python3", "python3\0hook.py\0")
    _proc(proc, 200, 100, "python3", "python3\0dispatch.py\0")
    _proc(proc, 100, 1, "claude", "claude\0")
    assert real._claude_pid(300, proc_root=proc) == 100

    proc2 = tmp_path / "proc2"
    _proc(proc2, 300, 200, "python3", "python3\0")
    _proc(proc2, 200, 100, "python3", "python3\0")
    _proc(proc2, 100, 1, "2.1.312", "/opt/x/.local/bin/claude\0")
    assert real._claude_pid(300, proc_root=proc2) == 100

    proc3 = tmp_path / "proc3"
    _proc(proc3, 300, 200, "python3", "python3\0")
    _proc(proc3, 200, 100, "python3", "python3\0")
    _proc(proc3, 100, 1, "node", "node\0cli.js\0")
    # no claude in the chain: fall back to the grandparent (hook -> dispatch -> claude)
    assert real._claude_pid(300, proc_root=proc3) == 100


def test_windows_start_and_end_exit_zero_with_empty_output(tmp_path, _state, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    monkeypatch.setattr(sl.plat, "IS_WINDOWS", True)
    rc, out = _start(tmp_path)
    assert rc == 0 and json.loads(out) == {}
    assert not (_state / "live-sessions").exists()
    rc, out = _main(["end"], {"session_id": S1, "reason": "other"})
    assert rc == 0 and json.loads(out) == {}


def test_garbage_stdin_prints_empty_json():
    for argv in (["start"], ["end"]):
        rc, out = _main(argv, "not json")
        assert rc == 0 and json.loads(out) == {}


def test_entry_write_is_atomic_json(tmp_path, _state):
    _start(tmp_path)
    d = _state / "live-sessions"
    assert [p.name for p in d.iterdir()] == [f"{S1}.json"]
    assert not list(d.glob("*.tmp")) and not list(d.glob(".tmp-*"))
