"""test_memwatch_state.py — lib/memwatch_state.py and the OOM-guard parts of lib/session_notices.py."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import memwatch_state as mws  # noqa: E402
from lib import platform as plat  # noqa: E402
from lib import session_notices as sn  # noqa: E402


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    return tmp_path / "state"


def test_write_then_read_round_trip():
    assert mws.read().level == "ok" and mws.read().stale is True  # no file yet
    now = time.time()
    assert mws.write_atomic(mws.State(level="crit", mem_available_mb=2000, ts=now))
    st = mws.read()
    assert st.level == "crit" and st.stale is False and st.mem_available_mb == 2000
    raw = json.loads(mws.paths()["state"].read_text(encoding="utf-8"))
    assert raw["schema"] == 1 and "stale" not in raw and "raw_level" not in raw
    mws.write_atomic(mws.State(level="crit", ts=time.time() - 31))  # stale: ok, raw level kept
    st = mws.read(stale_s=30)
    assert st.level == "ok" and st.stale is True and st.raw_level == "crit"


def test_corrupt_and_wrong_types_are_tolerated():
    p = mws.paths()["state"]
    p.write_text("{oops", encoding="utf-8")
    assert mws.read().level == "ok"
    p.write_text(json.dumps({"ts": time.time(), "level": "melting", "top": "x", "mem_available_mb": "1"}), encoding="utf-8")
    st = mws.read()
    assert st.level == "ok" and st.top == [] and st.mem_available_mb is None


def test_append_event_fills_ts_and_appends_lines():
    for i in range(3):
        assert mws.append_event({"kind": "tier", "n": i})
    lines = mws.paths()["events"].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and all("ts" in json.loads(x) for x in lines)


def test_unreported_events_filters_by_cursor_and_kind(tmp_path):
    ev = tmp_path / "e.jsonl"
    for ts, kind in ((10, "kill"), (20, "tier"), (30, "restore"), (40, "kill")):
        mws.append_event({"kind": kind, "ts": ts}, path=ev)
    got, newest = mws.unreported_events(15, path=ev)
    assert [e["ts"] for e in got] == [30, 40] and newest == 40
    assert mws.unreported_events(40, path=ev) == ([], 40)


def test_big_events_file_is_read_from_the_tail():
    p = mws.paths()["events"]
    p.write_text("".join(json.dumps({"kind": "kill", "ts": i, "pad": "x" * 80}) + "\n" for i in range(20000)), encoding="utf-8")
    t0 = time.perf_counter()
    got = mws.tail_events()
    assert time.perf_counter() - t0 < 0.2 and got[-1]["ts"] == 19999 and len(got) < 20000


def test_paths_and_windows(monkeypatch):
    assert set(mws.paths()) >= {"state", "events", "cursor", "mod_active", "ledger_dir"}
    monkeypatch.setattr(plat, "IS_WINDOWS", True)  # append_event on Windows needs msvcrt: replica run
    assert mws.write_atomic(mws.State(level="warn", ts=time.time())) and mws.read().level == "warn"


# ---- session_notices --------------------------------------------------------------------------
def _kills():
    mws.append_event({"kind": "tier", "from": "ok", "to": "warn", "ts": 100})
    mws.append_event({"kind": "kill", "victim": "node", "rss_mb": 3994, "unit": "ptyxis-spawn-aaaa.scope",
                      "source": "kernel", "ts": 101})
    mws.append_event({"kind": "kill", "victim": "Isolated Web Co", "rss_mb": 2458, "source": "memwatch",
                      "stage": 2, "ts": 102})
    mws.append_event({"kind": "restore", "sid": "abc", "ok": True, "ts": 103})


def test_memwatch_line_once_then_empty():
    assert sn.memwatch_line() == ""
    _kills()
    line = sn.memwatch_line()
    assert line.startswith("OOM guard since last session: 2 kills (node 3.9 GB, kernel; "
                           "Isolated Web Co 2.4 GB, memwatch stage 2), 1 session restored"), line
    assert len(line) <= 300
    assert json.loads(mws.paths()["cursor"].read_text(encoding="utf-8"))["reported_until"] == 103
    assert sn.memwatch_line() == ""


def test_memwatch_line_ignores_old_and_doctor(monkeypatch):
    mws.paths()["cursor"].write_text(json.dumps({"reported_until": 500}), encoding="utf-8")
    _kills()
    assert sn.memwatch_line() == ""
    mws.append_event({"kind": "kill", "victim": "bash", "source": "toolcap", "limit": "6G", "ts": 600})
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    assert sn.memwatch_line() == ""
    assert json.loads(mws.paths()["cursor"].read_text(encoding="utf-8"))["reported_until"] == 500
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR")
    assert "tool cap 6G" in sn.memwatch_line()


def test_mod_active():
    p = mws.paths()["mod_active"]
    assert sn.mod_active("s1") is False
    p.mkdir(parents=True)
    (p / "s1.json").write_text(json.dumps({"sid": "s1", "pid": 1, "ts": time.time() - 10}), encoding="utf-8")
    assert sn.mod_active("s1") is True and sn.mod_active("s2") is False
    (p / "s2.json").write_text(json.dumps({"sid": "s2", "ts": time.time() - 5}), encoding="utf-8")
    assert sn.mod_active("s1") and sn.mod_active("s2")  # two live sessions, both own their nudge
    (p / "s1.json").write_text(json.dumps({"sid": "s1", "pid": 1, "ts": time.time() - 90}), encoding="utf-8")
    assert sn.mod_active("s1") is False
    (p / "s3.json").write_text(json.dumps({"sid": "other", "ts": time.time()}), encoding="utf-8")
    assert sn.mod_active("s3") is False  # the body's sid must match the file's
    assert sn.mod_active("../s2") is False


def _tool(tmp_path, name, body):
    (tmp_path / "hooks" / "tools").mkdir(parents=True, exist_ok=True)
    (tmp_path / "hooks" / "tools" / f"{name}.py").write_text(body, encoding="utf-8")


def test_worktree_line(tmp_path, monkeypatch):
    monkeypatch.setattr(sn, "_HOOKS", tmp_path / "hooks")
    assert sn.worktree_line() == ""
    _tool(tmp_path, "worktree_audit", "def one_line(cwd, budget_ms=400):\n    return 'wt: x'\n")
    assert sn.worktree_line(str(tmp_path)) == "wt: x"
    _tool(tmp_path, "worktree_audit", "def one_line(cwd, budget_ms=400):\n    raise RuntimeError('x')\n")
    assert sn.worktree_line() == ""


def test_instinct_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(sn, "_HOOKS", tmp_path / "hooks")
    assert sn.instinct_lines() == []
    _tool(tmp_path, "instincts", "def lines(cwd, limit=3, min_confidence=0.7):\n    return list('abcde')\n")
    assert sn.instinct_lines(str(tmp_path)) == ["a", "b", "c"]
    _tool(tmp_path, "instincts", "def lines(cwd, limit=3, min_confidence=0.7):\n    raise ValueError\n")
    assert sn.instinct_lines() == []


# ---- memwatch step 8: notify, restore nudge, stuck, the loop (test_memwatch.py is at 250 lines) ----
def _mw_ctx(tmp_path, monkeypatch, tree="proc-warn", **seams):
    from test_memwatch import FIX, _ctx
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    return _ctx(tmp_path, FIX / tree, **seams), FIX


def test_notify_always_sends_desktop_and_records_the_toast_owner(tmp_path, monkeypatch):
    sent = []
    c, fix = _mw_ctx(tmp_path, monkeypatch, notify=lambda t, b, u="normal": sent.append(u))
    from test_memwatch import mw
    now = time.time()
    mw.pass_once(c, now)
    mw.pass_once(c, now + 1)
    c.proc_root = str(fix / "proc-crit")
    mw.pass_once(c, now + 2)
    assert sent == ["normal", "critical"]
    flag = mws.paths()["mod_active"] / "x.json"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(json.dumps({"sid": "x", "ts": now - 10}), encoding="utf-8")
    c.announce("crit", "t", "critical", now)
    assert sent == ["normal", "critical", "critical"] and c.notify_owner == "mod"
    flag.write_text(json.dumps({"sid": "x", "ts": now - 120}), encoding="utf-8")
    c.announce("crit", "t", "critical", now)
    assert len(sent) == 4 and c.notify_owner == "memwatch"


def test_quiet_hours(tmp_path, monkeypatch):
    from test_memwatch import mw
    late, noon = time.mktime((2026, 1, 1, 23, 30, 0, 0, 0, -1)), time.mktime((2026, 1, 1, 12, 0, 0, 0, 0, -1))
    assert mw.in_quiet_hours(late, "23:00-07:00") and not mw.in_quiet_hours(noon, "23:00-07:00")
    assert not mw.in_quiet_hours(late, "") and mw.in_quiet_hours(noon, "11:00-13:00")
    sent = []
    c, _ = _mw_ctx(tmp_path, monkeypatch, notify=lambda *a: sent.append(a[2]))
    c.cfg = {**c.cfg, "notify": {"quiet_hours": "11:00-13:00"}}
    c.announce("warn", "w", "normal", noon)
    c.announce("crit", "c", "critical", noon)
    assert sent == ["critical"]


def _restore_ctx(tmp_path, monkeypatch, **seams):
    root = tmp_path / "root"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "restore_sessions.py").write_text("", encoding="utf-8")
    return _mw_ctx(tmp_path, monkeypatch, root=root, **seams)[0], root


LEDGER = [{"sid": "s1", "pid": 999, "scope": "ptyxis-spawn-aaaa.scope"}]


@pytest.mark.parametrize("unit,enabled,want", [("ptyxis-spawn-aaaa.scope", True, True),
                                               ("ptyxis-spawn-aaaa.scope", False, False),
                                               ("snap.firefox.firefox-1111.scope", True, False)])
def test_ledger_matched_kill_sets_restore_pending(tmp_path, monkeypatch, unit, enabled, want):
    c, _ = _restore_ctx(tmp_path, monkeypatch)
    (tmp_path / "cfg").mkdir(exist_ok=True)
    (tmp_path / "cfg" / "oomguard.local.json").write_text(json.dumps({"restore_enabled": enabled}), encoding="utf-8")
    c.ingest([{"kind": "kill", "source": "kernel", "pid": 5, "victim": "node", "unit": unit}], time.time(), LEDGER)
    assert c.restore_pending is want


def test_maybe_restore_spawns_once_under_a_lock(tmp_path, monkeypatch):
    from test_memwatch import mw
    spawned = []
    c, root = _restore_ctx(tmp_path, monkeypatch, spawn=spawned.append)
    now = time.time()
    c.restore_pending, c.level, c.ok_since = True, "ok", now - 61
    assert mw.maybe_restore(c, now) is True
    assert spawned == [[mw.plat.python_exe(), str(root / "scripts" / "restore_sessions.py"), "--only-if-ok",
                        "--max-age", "7200", "--max", "6", "--per-window", "2"]]
    lock = mws.paths()["state"].parent / "restore.spawned"  # restore.lock is restore_sessions.py's own
    assert lock.is_file() and not (lock.parent / "restore.lock").exists()
    assert c.restore_pending is True  # held until a restore row lands (settle_restore)
    assert mw.maybe_restore(c, now) is False and len(spawned) == 1
    os.utime(lock, (now - 700, now - 700))
    assert mw.maybe_restore(c, now) is True and len(spawned) == 2


def test_stuck_scan(tmp_path):
    from test_memwatch import mw
    now, tr = time.time(), tmp_path / "t.jsonl"
    use = {"timestamp": now - 1900, "message": {"content": [{"type": "tool_use", "name": "Bash", "id": "b1"}]}}
    res = {"message": {"content": [{"type": "tool_result", "tool_use_id": "b1"}]}}
    led = [{"sid": "s", "transcript": str(tr)}]
    tr.write_text(json.dumps(use) + "\n", encoding="utf-8")
    assert mw.stuck_scan(led, now) == [{"sid": "s", "since": now - 1900}]
    tr.write_text(json.dumps(use) + "\n" + json.dumps(res) + "\n", encoding="utf-8")
    assert mw.stuck_scan(led, now) == []


def test_run_loop_iterates_and_survives_a_bad_queue(tmp_path, monkeypatch):
    from test_memwatch import mw

    class BadQ:
        n = 0

        def get_nowait(self):
            BadQ.n += 1
            if BadQ.n == 1:
                raise RuntimeError("boom")
            raise mw.queue.Empty
    c, _ = _mw_ctx(tmp_path, monkeypatch, tree="proc-ok")
    c.queue = BadQ()
    writes = []
    monkeypatch.setattr(mw, "write_state", lambda ctx, now, s: writes.append(now))
    ticks = iter(range(100))
    assert mw.run_loop(c, max_iterations=3, clock=lambda: 1000.0 + next(ticks), sleep=lambda s: None) == 0
    assert c.iterations == 3 and len(writes) == 3
