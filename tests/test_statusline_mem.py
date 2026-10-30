"""test_statusline_mem.py — scripts/statusline.py OOM-guard parts: seg_mem, plan tier, usage guard,
the session bridge and the ledger heartbeat."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from test_statusline import EPOCH, SCRIPT, cache, full_payload, repo, run  # noqa: F401 (fixtures)

ESC = "\x1b"


@pytest.fixture
def state(tmp_path):
    d = tmp_path / "state"
    d.mkdir()
    return d


def _mem(state, level="warn", age=0, **kv):
    (state / "mem-pressure.json").write_text(json.dumps({"schema": 1, "ts": time.time() - age, "level": level,
                                                         "mem_available_mb": 11210, "swap_free_pct": 1.2, **kv}),
                                             encoding="utf-8")


def _out(run, state, payload=None, **env):
    p = run(payload or {"model": {"display_name": "Opus 4.7"}, "effort": {"level": "xhigh"}},
            env={"CLAUDE_HOOK_STATE_DIR": str(state), **env})
    assert p.returncode == 0
    return p.stdout.decode()


def test_mem_segment(run, state):
    _mem(state)
    assert "mem 11G sw99%" in _out(run, state)


@pytest.mark.parametrize("level,code", [("crit", 203), ("warn", 220), ("ok", 78)])
def test_mem_colour(run, state, level, code):
    _mem(state, level)
    assert f"{ESC}[38;5;{code}mmem 11G" in _out(run, state, NO_COLOR=None)


def test_stale_unsupported_or_missing_hides(run, state):
    assert "mem " not in _out(run, state)
    _mem(state, age=40)
    assert "mem " not in _out(run, state)
    _mem(state, unsupported=True)
    assert "mem " not in _out(run, state)


def test_launch_caps_add_workflow_cap(run, state):
    _mem(state)
    (state / "launch-caps").mkdir()
    (state / "launch-caps" / f"{os.getpid()}.json").write_text(json.dumps({"workflow_agents": 4, "subagents": 5}),
                                                               encoding="utf-8")
    assert "mem 11G sw99% wf4" in _out(run, state)


@pytest.mark.parametrize("tier,suffix", [("max20", " 20x"), ("pro", " pro"), ("max5", " 5x"), ("api", " api")])
def test_plan_tier_suffix(run, state, tier, suffix):
    (state / "plan-tier.json").write_text(json.dumps({"schema": 1, "tier": tier}), encoding="utf-8")
    assert f"◆ Opus 4.7 (xhigh){suffix}" in _out(run, state)


def test_usage_guard_arrow(run, state):
    (state / "usage-guard.json").write_text(json.dumps({"schema": 1, "active": True}), encoding="utf-8")
    assert "◆ Opus 4.7 (xhigh) ↓" in _out(run, state)


def test_bridge_written_and_throttled(run, state, repo):
    pl = {**full_payload(repo), "session_id": "sess-1"}
    _out(run, state, pl)
    path = state / "session-bridge" / "sess-1.json"
    b = json.loads(path.read_text(encoding="utf-8"))
    assert (b["context_pct"], b["cost_usd"], b["five_hour_pct"], b["five_hour_resets_at"]) == (42, 1.3649, 31, EPOCH)
    assert abs(b["ts"] - time.time()) < 30
    first = path.stat().st_mtime_ns
    _out(run, state, pl)
    assert path.stat().st_mtime_ns == first
    old = time.time() - 11
    os.utime(path, (old, old))
    _out(run, state, pl)
    assert path.stat().st_mtime_ns != int(old * 1e9)


def test_heartbeat_refreshes_only_seen(run, state):
    (state / "live-sessions").mkdir()
    led = state / "live-sessions" / "sess-2.json"
    led.write_text(json.dumps({"sid": "sess-2", "pid": 1, "seen": 0, "started": 0, "cwd": "/x"}), encoding="utf-8")
    _out(run, state, {"session_id": "sess-2"})
    got = json.loads(led.read_text(encoding="utf-8"))
    assert got["seen"] > time.time() - 30 and {k: v for k, v in got.items() if k != "seen"} == \
        {"sid": "sess-2", "pid": 1, "started": 0, "cwd": "/x"}


def test_no_ledger_no_session_id_no_writes(run, state):
    _out(run, state, {"session_id": "sess-3"})
    assert not (state / "live-sessions").exists()
    _out(run, state, {"model": {"display_name": "x"}})
    assert [p.name for p in (state / "session-bridge").iterdir()] == ["sess-3.json"]


def test_warm_path_with_state_imports_nothing_heavy(run, state, repo, cache):
    _mem(state)
    pl = {**full_payload(repo), "session_id": "sess-4"}
    run(pl, env={"CLAUDE_HOOK_STATE_DIR": str(state)})
    base = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "COLUMNS")}
    base.update(CLAUDE_STATUSLINE_CACHE_DIR=str(cache), NO_COLOR="1", CLAUDE_HOOK_STATE_DIR=str(state))
    p = subprocess.run([sys.executable, "-X", "importtime", str(SCRIPT)], input=json.dumps(pl).encode(),
                       capture_output=True, env=base, cwd=str(repo), timeout=10)
    mods = {ln.rsplit("|", 1)[1].strip() for ln in p.stderr.decode("utf-8", "replace").splitlines()
            if ln.startswith("import time:") and "|" in ln}
    assert p.returncode == 0 and "mem 11G" in p.stdout.decode()
    assert not mods & {"hashlib", "tempfile", "subprocess"}


def test_columns_70_drops_mem_first(run, state, repo):
    _mem(state)
    out = _out(run, state, full_payload(repo), COLUMNS="70").strip()
    assert len(out) <= 70 and "mem " not in out and "⎇ main" in out and "$1.36" in out
