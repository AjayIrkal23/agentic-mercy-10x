#!/usr/bin/env python3
"""Tests for hooks/opus-guard.py (P2-T3): policy-driven, behavior-preserving.

Covers the resolution order sourced from model-policy.json:
  session_flags -> agent_pins -> explicit model param -> [label] prefix -> default
(task_matrix is intentionally NOT consulted here — the Agent tool carries no
TaskProfile, so that global-order step is a no-op at this boundary). Plus policy-load
fail-open (corrupt/missing policy -> hardcoded literals) and full-input echo (the whole
tool_input is returned in updatedInput, only model/description overridden).

Session-flag tests use HOME=<tmp> so ~/.claude/state/*-only-mode files are read from a
throwaway dir; the real state is never touched. The policy file itself loads via
__file__ from the real hooks dir (unaffected by HOME).
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "opus-guard.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("opus_guard_under_test", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _clean_home() -> Path:
    home = Path(tempfile.mkdtemp(prefix="opusguard-home-"))
    (home / ".claude" / "state").mkdir(parents=True)
    return home


def run_agent(tool_input: dict, home: Path | None = None) -> dict:
    payload = {"tool_name": "Agent", "tool_input": tool_input}
    env = dict(os.environ)
    env["HOME"] = str(home or _clean_home())
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, f"hook exited {proc.returncode}: {proc.stderr}"
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def resolved(out: dict) -> dict:
    """The updatedInput dict, or {} when the hook allowed unchanged."""
    if not out:
        return {}
    return out["hookSpecificOutput"]["updatedInput"]


# --- resolution order (in precedence) --------------------------------------

def test_default_is_sonnet():
    out = run_agent({"description": "do a thing", "subagent_type": "general-purpose"})
    ui = resolved(out)
    assert ui["model"] == "sonnet"
    assert ui["description"] == "[sonnet] do a thing"


def test_agent_pin_opus_beats_sonnet_label():
    # frontend-uiux-designer is pinned opus even with a [sonnet] label.
    out = run_agent({"description": "[sonnet] polish UI", "subagent_type": "frontend-uiux-designer"})
    ui = resolved(out)
    assert ui["model"] == "opus"
    assert ui["description"] == "[opus] polish UI"


def test_agent_pin_opus_implementation_engineer():
    out = run_agent({"description": "[sonnet] build feature", "subagent_type": "implementation-engineer"})
    assert resolved(out)["model"] == "opus"


def test_agent_pin_sonnet_beats_opus_label():
    out = run_agent({"description": "[opus] map the code", "subagent_type": "explore"})
    ui = resolved(out)
    assert ui["model"] == "sonnet"
    assert ui["description"] == "[sonnet] map the code"


def test_explicit_model_param_honored():
    out = run_agent({"description": "special task", "model": "fable", "subagent_type": "general-purpose"})
    ui = resolved(out)
    assert ui["model"] == "fable"
    assert ui["description"] == "[fable] special task"


def test_label_prefix_used_when_no_pin_or_model():
    out = run_agent({"description": "[opus] heavy novel architecture", "subagent_type": "general-purpose"})
    assert resolved(out)["model"] == "opus"


def test_noop_when_already_correct():
    # opus agent + [opus] label + model opus -> nothing to change -> allow unchanged.
    out = run_agent({
        "description": "[opus] polish",
        "model": "opus",
        "subagent_type": "frontend-uiux-designer",
    })
    assert out == {}


# --- session flags win over everything, in precedence sonnet>opus>fable -----

def test_sonnet_flag_overrides_opus_agent():
    home = _clean_home()
    (home / ".claude" / "state" / "sonnet-only-mode").write_text("")
    out = run_agent(
        {"description": "[opus] polish", "model": "opus", "subagent_type": "frontend-uiux-designer"},
        home=home,
    )
    assert resolved(out)["model"] == "sonnet"


def test_opus_flag_overrides_sonnet_agent():
    home = _clean_home()
    (home / ".claude" / "state" / "opus-only-mode").write_text("")
    out = run_agent({"description": "map", "subagent_type": "explore"}, home=home)
    assert resolved(out)["model"] == "opus"


def test_fable_flag_forces_fable():
    home = _clean_home()
    (home / ".claude" / "state" / "fable-only-mode").write_text("")
    out = run_agent({"description": "task", "subagent_type": "general-purpose"}, home=home)
    assert resolved(out)["model"] == "fable"


def test_sonnet_flag_wins_precedence_over_opus_flag():
    # both flags present -> sonnet wins (kill-switch precedence).
    home = _clean_home()
    (home / ".claude" / "state" / "sonnet-only-mode").write_text("")
    (home / ".claude" / "state" / "opus-only-mode").write_text("")
    out = run_agent({"description": "task", "subagent_type": "general-purpose"}, home=home)
    assert resolved(out)["model"] == "sonnet"


# --- full-input echo --------------------------------------------------------

def test_full_input_echoed():
    out = run_agent({
        "description": "do a thing",
        "subagent_type": "general-purpose",
        "prompt": "a long prompt that must survive",
        "extra_key": {"nested": [1, 2]},
    })
    ui = resolved(out)
    # every original key preserved; only model/description overridden.
    assert ui["prompt"] == "a long prompt that must survive"
    assert ui["extra_key"] == {"nested": [1, 2]}
    assert ui["subagent_type"] == "general-purpose"
    assert ui["model"] == "sonnet"


# --- policy-load fail-open (in-process; corrupt/missing policy -> literals) --

def test_policy_load_fail_open_missing(monkeypatch, tmp_path):
    mod = _load_module()
    mod._POLICY_CACHE = None
    monkeypatch.setattr(mod, "POLICY_PATH", tmp_path / "does-not-exist.json")
    home = tmp_path / "home"
    (home / ".claude" / "state").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    # Missing policy -> literal fallback still pins the UI agent to opus and defaults sonnet.
    assert mod._resolve_required("frontend-uiux-designer", "", "x")[0] == "opus"
    assert mod._resolve_required("general-purpose", "", "x")[0] == "sonnet"
    assert mod._default_model() == "sonnet"


def test_policy_load_fail_open_corrupt(monkeypatch, tmp_path):
    mod = _load_module()
    mod._POLICY_CACHE = None
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not valid json ][")
    monkeypatch.setattr(mod, "POLICY_PATH", bad)
    home = tmp_path / "home"
    (home / ".claude" / "state").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    assert mod._resolve_required("explore", "", "x")[0] == "sonnet"
    assert mod._resolve_required("implementation-engineer", "", "x")[0] == "opus"


def test_policy_actually_loaded_from_disk():
    # sanity: the real policy file parses and pins match the shipped literals.
    mod = _load_module()
    mod._POLICY_CACHE = None
    sonnet_set, opus_set = mod._agent_sets()
    assert "frontend-uiux-designer" in opus_set
    assert "implementation-engineer" in opus_set
    assert "explore" in sonnet_set
    assert mod._default_model() == "sonnet"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
