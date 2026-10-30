"""test_memwatch_brake.py — hooks/memwatch-brake.py (PreToolUse) and hooks/memwatch-ensure.py (SessionStart)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
BRAKE = HOOKS / "memwatch-brake.py"
sys.path.insert(0, str(HOOKS))

from lib import memwatch_state as mws  # noqa: E402
from lib import platform as plat  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    e = {k: v for k, v in os.environ.items() if k != "CLAUDE_WORKBENCH_UNATTENDED"}
    e.update(CLAUDE_HOOK_STATE_DIR=str(tmp_path / "state"), CLAUDE_HOOK_TELEMETRY_DIR=str(tmp_path / "tele"))
    return e


def write_state(level, mem_mb=6246, swap_pct=1.0, age_s=0):
    mws.write_atomic(mws.State(level=level, mem_available_mb=mem_mb, swap_free_pct=swap_pct, ts=time.time() - age_s))


def brake(env, payload=None, *, raw=None, sid="s1", **extra_env):
    if payload is not None:
        payload = {"session_id": sid, **payload}
    p = subprocess.run([sys.executable, str(BRAKE)], input=raw if raw is not None else json.dumps(payload),
                       capture_output=True, text=True, env={**env, **extra_env}, timeout=10)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


AGENT = {"tool_name": "Agent", "tool_input": {"prompt": "x"}}


def test_no_state_and_ok_are_silent(env):
    assert brake(env, AGENT) == {}
    write_state("ok")
    assert brake(env, AGENT) == {}


def test_warn_once_per_tier_value(env, tmp_path):
    write_state("warn")
    out = brake(env, AGENT)["hookSpecificOutput"]
    assert out["additionalContext"].startswith("memory warn: 6.1 GB free, swap 99 %")
    assert "do not fan out agents or start vitest" in out["additionalContext"] and "permissionDecision" not in out
    assert brake(env, AGENT) == {}
    assert (tmp_path / "state" / "s1.brake-tier").read_text(encoding="utf-8") == "warn"
    write_state("crit")
    brake(env, AGENT)
    write_state("warn")
    assert "additionalContext" in brake(env, AGENT)["hookSpecificOutput"]


def test_warn_names_usage_guard(env, tmp_path):
    write_state("warn")
    (tmp_path / "state" / "usage-guard.json").write_text(json.dumps({"active": True}), encoding="utf-8")
    assert "usage guard active" in brake(env, AGENT)["hookSpecificOutput"]["additionalContext"]


def test_stale_crit_is_ok(env):
    write_state("crit", age_s=31)
    assert brake(env, AGENT) == {}


def test_crit_asks_with_numbers(env):
    write_state("crit", mem_mb=2048)
    out = brake(env, AGENT)["hookSpecificOutput"]
    assert out["permissionDecision"] == "ask" and "2.0 GB" in out["permissionDecisionReason"]
    assert "`Agent`" in out["permissionDecisionReason"]


def _tele_rows(tmp_path):
    return [json.loads(x) for f in (tmp_path / "tele").glob("*.jsonl") for x in f.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("payload,extra,why", [
    ({**AGENT, "agent_id": "a1"}, {}, "subagent"),
    (AGENT, {"CLAUDE_WORKBENCH_UNATTENDED": "1"}, "unattended"),
    ({"tool_name": "Agent", "tool_input": {"workflow_id": "w1"}}, {}, "workflow"),
    (AGENT, {"LEDGER": "1"}, "restored")])
def test_crit_downgrades_when_unattended(env, tmp_path, payload, extra, why):
    write_state("crit")
    if extra.pop("LEDGER", None):
        (tmp_path / "state" / "live-sessions").mkdir()
        (tmp_path / "state" / "live-sessions" / "s1.json").write_text(json.dumps({"restored": True}), encoding="utf-8")
    out = brake(env, payload, **extra)["hookSpecificOutput"]
    assert "permissionDecision" not in out and f"(ask downgraded: {why}" in out["additionalContext"]
    assert out["additionalContext"].startswith("memory crit")
    assert any(r.get("decision") == "ask_downgraded" and r.get("reason") == why for r in _tele_rows(tmp_path))


@pytest.mark.parametrize("cmd", ["npx vitest run", "npm run test", "npm test", "pytest -q", "graphify update .",
                                 "tsc -p .", "npx playwright test", "jest", "npm run build"])
def test_heavy_shell_commands_apply(env, cmd):
    write_state("crit")
    assert brake(env, {"tool_name": "Bash", "tool_input": {"command": cmd}})["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_light_commands_and_other_tools_pass(env):
    write_state("crit")
    assert brake(env, {"tool_name": "Bash", "tool_input": {"command": "ls"}}) == {}
    assert brake(env, {"tool_name": "Read", "tool_input": {}}) == {}
    assert "permissionDecision" in brake(env, {"tool_name": "PowerShell", "tool_input": {"command": "npm run build"}},
                                         sid="s2")["hookSpecificOutput"]
    assert "permissionDecision" in brake(env, {"tool_name": "mcp__playwright__browser_navigate", "tool_input": {}},
                                         sid="s3")["hookSpecificOutput"]
    write_state("warn")
    assert "additionalContext" in brake(env, {"tool_name": "Workflow", "tool_input": {}}, sid="s4")["hookSpecificOutput"]


def test_malformed_and_link_doctor_probe(env):
    assert brake(env, raw="not json") == {} and brake(env, raw="") == {} and brake(env, raw="[1]") == {}
    t0 = time.monotonic()
    p = brake(env, {"tool_name": "Agent", "tool_input": {}}, sid="link-doctor")
    assert p == {} and time.monotonic() - t0 < 2


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_heavy_re_is_a_plain_pattern():
    mod = _load(BRAKE, "memwatch_brake")
    assert hasattr(mod.HEAVY_RE, "pattern") and isinstance(mod.HEAVY_RE.pattern, str)


# ---- memwatch-ensure.py (SessionStart) ---------------------------------------------------------
ENSURE = HOOKS / "memwatch-ensure.py"
FAKE_SYSTEMCTL = '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$FAKE_LOG"\n[ -f "$FAKE_HANG" ] && sleep 20\ncat "$FAKE_ANSWER"\n'


@pytest.fixture
def ens(env, tmp_path):
    fb = tmp_path / "fakebin"
    fb.mkdir()
    (fb / "systemctl").write_text(FAKE_SYSTEMCTL, encoding="utf-8")
    (fb / "systemctl").chmod(0o755)
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "bus").write_text("", encoding="utf-8")
    (tmp_path / "answer").write_text("inactive\n", encoding="utf-8")
    env.update(PATH=f"{fb}:{env.get('PATH', '/usr/bin:/bin')}", HOME=str(tmp_path), XDG_RUNTIME_DIR=str(tmp_path / "run"),
               FAKE_LOG=str(tmp_path / "log"), FAKE_ANSWER=str(tmp_path / "answer"), FAKE_HANG=str(tmp_path / "hang"),
               MEMWATCH_ENSURE_ALLOW_TEST="1")
    return env


def _ensure(env, payload=None, **extra):
    p = subprocess.run([sys.executable, str(ENSURE)], input=json.dumps(payload or {"session_id": "s1", "source": "startup"}),
                       capture_output=True, text=True, env={**env, **extra}, timeout=15)
    assert p.returncode == 0 and json.loads(p.stdout) == {}
    return p


def _log(tmp_path):
    p = tmp_path / "log"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


@pytest.mark.skipif(plat.IS_WINDOWS, reason="bash fake systemctl")
def test_ensure_active_does_nothing_inactive_starts(ens, tmp_path):
    (tmp_path / "answer").write_text("active\n", encoding="utf-8")
    _ensure(ens)
    assert _log(tmp_path) == ["--user is-active claude-memwatch"]
    (tmp_path / "answer").write_text("inactive\n", encoding="utf-8")
    unit = tmp_path / ".config" / "systemd" / "user" / "claude-memwatch.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("[Unit]\n", encoding="utf-8")
    _ensure(ens)
    assert _log(tmp_path)[-1] == "--user start claude-memwatch"


@pytest.mark.skipif(plat.IS_WINDOWS, reason="bash fake systemctl")
@pytest.mark.parametrize("extra,payload", [({"CLAUDE_HOOK_DOCTOR": "1"}, None),
                                           ({}, {"session_id": "link-doctor"}),
                                           ({"MEMWATCH_ENSURE_ALLOW_TEST": ""}, None),
                                           ({"XDG_RUNTIME_DIR": "/nonexistent"}, None)])
def test_ensure_skips(ens, tmp_path, extra, payload):
    _ensure(ens, payload, **extra)
    assert _log(tmp_path) == []


@pytest.mark.skipif(plat.IS_WINDOWS, reason="bash fake systemctl")
def test_ensure_hanging_systemctl_times_out(ens, tmp_path):
    (tmp_path / "hang").write_text("", encoding="utf-8")
    t0 = time.monotonic()
    _ensure(ens)
    assert time.monotonic() - t0 < 9
    assert _log(tmp_path) == ["--user is-active claude-memwatch"]  # a timeout never falls through to install


def test_ensure_missing_unit_runs_setup_under_lock(tmp_path, monkeypatch):
    mod = _load(ENSURE, "memwatch_ensure")
    calls = []
    mod.ensure_fn = lambda dry: calls.append(dry)
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MEMWATCH_ENSURE_ALLOW_TEST", "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    import types
    monkeypatch.setattr(mod.plat, "systemd_user_bus", lambda: tmp_path / "bus")
    monkeypatch.setattr(mod, "_setup", lambda: types.SimpleNamespace(
        unit_state=lambda **k: "inactive", unit_file=lambda home=None: tmp_path / "absent.service"))
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO('{"session_id": "s1"}'))
    assert mod.main() == 0 and calls == [False]
    assert (tmp_path / "state" / "oomguard-ensure.lock").exists()
    monkeypatch.setattr(mod.plat, "IS_WINDOWS", True)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("{}"))
    assert mod.main() == 0 and calls == [False]


def test_ensure_hook_names_no_unit_manager():
    """hooks/*.py never carry the unit-manager literal (test_index_lifecycle grep gate); the installer owns it."""
    assert "systemctl" not in ENSURE.read_text(encoding="utf-8")
