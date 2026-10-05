#!/usr/bin/env python3
"""Tests for hooks/opus-guard.py: policy-driven model routing for the Agent tool.

Covers the resolution order sourced from model-policy.json:
  session_flags -> per-project mode -> explicit model / [label] (guarded agents and
  fable need the user's phrase: test_opus_guard_explicit.py) -> agent_pins ->
  escalation (execution agents: retry / large unplanned work) -> default
Opus judges (pinned), Sonnet executes (default), escalation lifts execution agents.
Plus policy-load fail-open (corrupt/missing policy -> hardcoded literals), full-input
echo (only model/description overridden) and the per-session routing log.

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
    h = str(home or _clean_home())
    env = dict(os.environ)
    # Path.home() reads USERPROFILE on Windows and HOME on POSIX — set both (and
    # clear HOMEDRIVE/HOMEPATH) so the throwaway ~/.claude/state session flags are
    # found on every OS, not just Linux.
    env["HOME"] = h
    env["USERPROFILE"] = h
    env.pop("HOMEDRIVE", None)
    env.pop("HOMEPATH", None)
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
    # frontend-uiux-designer is pinned opus (2026-07-19: Fable-first directive removed)
    # even when the call carries a [sonnet] label.
    out = run_agent({"description": "[sonnet] polish UI", "subagent_type": "frontend-uiux-designer"})
    ui = resolved(out)
    assert ui["model"] == "opus"
    assert ui["description"] == "[opus] polish UI"


def test_judges_pinned_opus():
    # Opus judges (2026-09-29 Sonnet 5.5 remap): review, design, plan, spec, debug.
    for at in ("santa-reviewer", "planning-director", "spec-architect", "debug-detective"):
        out = run_agent({"description": "[sonnet] work", "subagent_type": at})
        assert resolved(out)["model"] == "opus", at


def test_implementors_default_to_sonnet():
    # Sonnet 5.5 executes: implementors are no longer Opus-pinned.
    for at in ("implementation-engineer", "backend-implementor-specialist",
               "frontend-implementor-specialist", "integrator-specialist"):
        out = run_agent({"description": "build feature", "subagent_type": at,
                         "prompt": "Add a created_at column to the users table and update the handler."})
        assert resolved(out)["model"] == "sonnet", at


# --- escalation: execution agents lift to opus on retry / large unplanned work ---

HEAVY = ("Rebuild the whole notification system end-to-end: real-time websocket "
         "event-driven pipeline across the codebase, frontend and backend.")


def test_retry_escalates_implementor():
    out = run_agent({"description": "fix tests", "subagent_type": "backend-implementor-specialist",
                     "prompt": "Previous attempt failed: the migration test is still red. Fix it."})
    assert resolved(out)["model"] == "opus"
    assert "previous attempt failed" in out["hookSpecificOutput"]["additionalContext"]


def test_large_unplanned_task_escalates_even_with_sonnet_label():
    out = run_agent({"description": "[sonnet] notifications", "subagent_type": "implementation-engineer",
                     "prompt": HEAVY})
    ui = resolved(out)
    assert ui["model"] == "opus"
    assert ui["description"] == "[opus] notifications"


def test_plan_reference_keeps_large_task_on_sonnet():
    out = run_agent({"description": "notifications", "subagent_type": "implementation-engineer",
                     "prompt": HEAVY + " Execute docs/superpowers/plans/plan-2026-09-29-notify.md task by task."})
    assert resolved(out)["model"] == "sonnet"


def test_explicit_model_without_user_phrase_does_not_block_escalation():
    # E-04: an unprompted model param no longer outranks escalation for an executor
    out = run_agent({"description": "fix", "model": "sonnet", "subagent_type": "implementation-engineer",
                     "prompt": "Previous attempt failed: still broken."})
    assert resolved(out)["model"] == "opus"


def test_non_execution_agents_never_escalate():
    for at in ("explore", "general-purpose", "deadcode-reaper"):
        out = run_agent({"description": "x", "subagent_type": at,
                         "prompt": "Previous attempt failed. " + HEAVY})
        assert resolved(out)["model"] == "sonnet", at


def test_escalation_fail_open(monkeypatch):
    # a malformed marker regex must degrade to "no escalation", never raise.
    mod = _load_module()
    mod._POLICY_CACHE = None
    policy = mod._load_policy()
    mod._POLICY_CACHE = {**policy, "escalation": {**policy["escalation"], "retry_markers": ["("]}}
    monkeypatch.setattr(mod, "_flag_paths", lambda: {})
    assert mod._resolve_required("implementation-engineer", "", "x", None, HEAVY) == \
        ("sonnet", "default (no opus/fable signal)")


def test_routing_log_records_every_decision(monkeypatch, tmp_path):
    mod = _load_module()
    monkeypatch.setattr(mod, "_TELEMETRY_DIR", tmp_path)
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    mod._log_route("sid/1", "implementation-engineer", "opus", "previous attempt failed")
    rec = json.loads((tmp_path / "sid_1.model-routing.jsonl").read_text(encoding="utf-8").strip())
    assert (rec["agent"], rec["model"], rec["reason"]) == \
        ("implementation-engineer", "opus", "previous attempt failed")
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    mod._log_route("sid2", "x", "sonnet", "default")
    assert not (tmp_path / "sid2.model-routing.jsonl").exists()


def test_no_agent_is_auto_pinned_to_fable():
    """2026-07-19 regression guard: Fable must never be reachable by a pin.
    It is opt-in only (explicit label / model param / fable-only-mode flag)."""
    mod = _load_module()
    mod._POLICY_CACHE = None
    _sonnet, _opus, fable_set = mod._agent_sets()
    assert fable_set == set(), f"agent_pins.fable must stay empty, got {fable_set}"


def test_agent_pin_sonnet_beats_opus_label():
    out = run_agent({"description": "[opus] map the code", "subagent_type": "explore"})
    ui = resolved(out)
    assert ui["model"] == "sonnet"
    assert ui["description"] == "[sonnet] map the code"


def test_explicit_model_param_honored():
    out = run_agent({"description": "special task", "model": "opus", "subagent_type": "general-purpose"})
    ui = resolved(out)
    assert ui["model"] == "opus"
    assert ui["description"] == "[opus] special task"


def test_label_prefix_used_when_no_pin_or_model():
    out = run_agent({"description": "[opus] heavy novel architecture", "subagent_type": "general-purpose"})
    assert resolved(out)["model"] == "opus"


def test_noop_when_already_correct():
    # opus-pinned agent + [opus] label + model opus -> nothing to change -> allow unchanged.
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
    # every original key preserved; only model/description change. The prompt
    # and name are never touched (write protocol moved to SubagentStart, D3).
    assert ui["prompt"] == "a long prompt that must survive"
    assert ui["extra_key"] == {"nested": [1, 2]}
    assert ui["subagent_type"] == "general-purpose"
    assert ui["model"] == "sonnet"


def test_name_never_rewritten():
    ui = resolved(run_agent({"description": "x", "subagent_type": "general-purpose",
                             "name": "impl-crud-opus"}))
    assert ui["name"] == "impl-crud-opus"


def test_explicit_model_param_without_user_phrase_does_not_beat_pin():
    # E-04: only the user's own phrase this turn moves a pinned judge
    # (the phrase case: test_opus_guard_explicit.py)
    ui = resolved(run_agent({"description": "build it", "model": "sonnet",
                             "subagent_type": "santa-reviewer"}))
    assert ui["model"] == "opus"
    assert ui["description"] == "[opus] build it"


def test_per_project_mode_beats_explicit(monkeypatch, tmp_path):
    mod = _load_module()
    mod._POLICY_CACHE = None
    monkeypatch.setattr(mod, "_flag_paths", lambda: {})
    monkeypatch.setattr(mod._mm, "modes_dir", lambda: tmp_path / "model-modes")
    repo = tmp_path / "repo"
    repo.mkdir()
    assert mod._mm.set_mode(str(repo), "opus")
    assert mod._resolve_required("general-purpose", "sonnet", "[sonnet] x", str(repo)) == \
        ("opus", "per-project model mode")
    assert mod._mm.set_mode(str(repo), None)
    assert mod._resolve_required("general-purpose", "sonnet", "x", str(repo))[0] == "sonnet"


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
    assert mod._resolve_required("santa-reviewer", "", "x")[0] == "opus"
    assert mod._resolve_required("implementation-engineer", "", "x")[0] == "sonnet"


def test_policy_actually_loaded_from_disk():
    # sanity: the real policy file parses and pins match the shipped literals.
    mod = _load_module()
    mod._POLICY_CACHE = None
    sonnet_set, opus_set, fable_set = mod._agent_sets()
    assert {"frontend-uiux-designer", "santa-reviewer", "planning-director"} <= opus_set
    assert "implementation-engineer" not in opus_set
    assert "backend-implementor-specialist" not in opus_set
    assert fable_set == set(), "Fable is opt-in only; no agent may be pinned to it"
    assert "explore" in sonnet_set
    assert mod._default_model() == "sonnet"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
