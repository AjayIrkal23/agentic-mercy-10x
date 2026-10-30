"""test_gate_mode.py — lib/gate_mode.py (directive 31 ask-or-advise)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import gate_mode  # noqa: E402


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_WORKBENCH_UNATTENDED", raising=False)
    return tmp_path


def test_interactive_asks():
    assert gate_mode.decide({"tool_name": "Agent", "session_id": "s1"}, want="ask") == ("ask", "interactive")


@pytest.mark.parametrize("extra", [{"agent_id": "a1"}, {"agent_type": "general-purpose"}])
def test_subagent_advises(extra):
    assert gate_mode.decide({"session_id": "s1", **extra}) == ("advise", "subagent")


def test_unattended_env_advises(monkeypatch):
    monkeypatch.setenv("CLAUDE_WORKBENCH_UNATTENDED", "1")
    assert gate_mode.decide({"session_id": "s1"}) == ("advise", "unattended")
    assert gate_mode.decide({"session_id": "s1"}, environ={}) == ("ask", "interactive")


def test_restored_ledger_advises(_state):
    (_state / "live-sessions").mkdir()
    (_state / "live-sessions" / "s1.json").write_text(json.dumps({"restored": True}), encoding="utf-8")
    assert gate_mode.decide({"session_id": "s1"}) == ("advise", "restored")
    (_state / "live-sessions" / "s1.json").write_text(json.dumps({"restored": False}), encoding="utf-8")
    assert gate_mode.decide({"session_id": "s1"}) == ("ask", "interactive")


@pytest.mark.parametrize("payload", [{"workflow_id": "w"}, {"tool_input": {"workflow_id": "w"}}])
def test_workflow_advises(payload):
    assert gate_mode.decide(payload) == ("advise", "workflow")


def test_deny_and_allow_pass_through():
    assert gate_mode.decide({"agent_id": "a"}, want="deny") == ("deny", "deny-never-downgraded")
    assert gate_mode.decide({"agent_id": "a"}, want="allow") == ("allow", "interactive")


@pytest.mark.parametrize("payload", [None, [1, 2], "x"])
def test_malformed_payload_asks(payload):
    assert gate_mode.decide(payload) == ("ask", "interactive")


def test_once_per_file(_state):
    assert gate_mode.once_per_file("s1", "brake", "/x") is True
    assert gate_mode.once_per_file("s1", "brake", "/x") is False
    assert gate_mode.once_per_file("s1", "brake", "/y") is True
    assert (_state / "s1.brake.once.json").is_file()


def test_once_per_file_sanitises_sid(_state):
    assert gate_mode.once_per_file("../x", "brake", "/x") is True
    files = [p.name for p in _state.iterdir() if p.name.endswith(".once.json")]
    assert files and all("/" not in f and not f.startswith(".") for f in files)
    assert not (_state.parent / "x.brake.once.json").exists()
