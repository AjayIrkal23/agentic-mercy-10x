"""jcodemunch-enforce: locked state, empty-sid guard, dead prompt mode gone (PKG hooks-hygiene-mod step 4)."""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))


def _load():
    spec = importlib.util.spec_from_file_location("jcm_state_ut", HOOKS / "jcodemunch-enforce.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def env(tmp_path, monkeypatch):
    jcm = _load()
    state = tmp_path / "state"
    monkeypatch.setattr(jcm, "STATE_DIR", state)
    monkeypatch.setattr(jcm, "INDEX_DIR", tmp_path / "idx")
    monkeypatch.setattr(jcm, "_is_exempt", lambda t, c: False)
    monkeypatch.setattr(jcm, "_is_plan_or_ask", lambda p: False)
    monkeypatch.setattr(jcm, "_coding_started", lambda cid: True)
    monkeypatch.setattr(jcm, "_index_building", lambda p: False)
    monkeypatch.setattr(jcm, "_check_index_exists", lambda t: True)
    monkeypatch.setattr(jcm, "_load_enforce_config", lambda: {"initial_block_count": 2, "strict_mode": True})

    def _io(fn, payload):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        fn()
        out = buf.getvalue().strip()
        return json.loads(out) if out else {}

    def fire(sid, tool="Read"):
        return _io(jcm.pre_tool_use, {"session_id": sid, "tool_name": tool,
                                      "tool_input": {"file_path": str(tmp_path / "repo" / "src" / "a.py")}})

    def used(sid, tool="mcp__jcodemunch__search_symbols"):
        return _io(jcm.mcp_used, {"session_id": sid, "tool_name": tool})

    return {"jcm": jcm, "state": state, "fire": fire, "used": used, "mp": monkeypatch}


def test_no_prompt_submit_mode(env):
    jcm = env["jcm"]
    assert not hasattr(jcm, "prompt_submit") and not hasattr(jcm, "REMINDER")
    cp = subprocess.run([sys.executable, str(HOOKS / "jcodemunch-enforce.py"), "prompt-submit"],
                        input=json.dumps({"session_id": "x", "prompt": "hi"}), text=True,
                        capture_output=True, timeout=30)
    assert cp.returncode == 0 and cp.stdout.strip() == ""


def test_gate3_counts_blocks_then_allows_with_advisory(env):
    assert env["fire"]("s").get("permissionDecision") == "deny"
    assert env["fire"]("s").get("permissionDecision") == "deny"
    third = env["fire"]("s")
    assert "permissionDecision" not in third and "jcodemunch" in third.get("additionalContext", "")
    p = env["state"] / "s.mcp-enforce.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["read_blocked_count"] == 2 and data["read_allowed_count"] == 1
    assert (env["state"] / "s.mcp-enforce.json.lock").exists()


def test_empty_session_id_fails_open_everywhere(env):
    jcm, mp = env["jcm"], env["mp"]
    mp.setattr(jcm, "_check_index_exists", lambda t: False)
    mp.setattr(jcm, "_start_index_build", lambda p, r: (False, ""))
    assert env["fire"]("") == {}
    mp.setattr(jcm, "_check_index_exists", lambda t: True)
    assert env["fire"]("") == {}
    assert not env["state"].exists() or list(env["state"].iterdir()) == []


def test_mcp_used_increments_under_lock_and_records_deadcode(env):
    env["used"]("s", "mcp__jcodemunch__find_dead_code")
    env["used"]("s", "mcp__jcodemunch__find_dead_code")
    data = json.loads((env["state"] / "s.mcp-enforce.json").read_text(encoding="utf-8"))
    assert data["jcodemunch_calls"] == 2
    assert json.loads((env["state"] / "s.deadcode.json").read_text(encoding="utf-8")) == {"fired": True}
    assert env["fire"]("s") == {}


def test_corrupt_state_resets_and_never_raises(env):
    env["state"].mkdir(parents=True, exist_ok=True)
    (env["state"] / "s.mcp-enforce.json").write_text("{bad", encoding="utf-8")
    assert env["fire"]("s").get("permissionDecision") == "deny"
