#!/usr/bin/env python3
"""Tests for hooks/opus-guard.py: plan-tier-aware model routing for the Agent tool (R3.3).

Order: session flags -> per-project mode -> explicit model / [label] (guarded roles and fable need
the user's phrase: test_opus_guard_explicit.py) -> role x tier -> escalation -> usage step-down ->
tier ceiling. Every scenario pins its tier through tests/fixtures/plan-tier/tier_fixture.py
(default max20, no usage reading). Plus policy-load fail-open, full-input echo and the routing log.

Session-flag tests use HOME=<tmp> so ~/.claude/state/*-only-mode files come from a throwaway dir.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "opus-guard.py"
ROOT = HOOK.parent.parent
sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "plan-tier"))
import tier_fixture as TF  # noqa: E402


@pytest.fixture(autouse=True)
def _max20_default():
    TF.set_tier("max20")
    TF.set_usage(None)
    yield
    TF.clear()


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
    # Path.home() reads USERPROFILE on Windows and HOME on POSIX — set both.
    env["HOME"] = h
    env["USERPROFILE"] = h
    env.pop("HOMEDRIVE", None)
    env.pop("HOMEPATH", None)
    env.pop("CLAUDE_CONFIG_DIR", None)
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, f"hook exited {proc.returncode}: {proc.stderr}"
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def resolved(out: dict) -> dict:
    """The updatedInput dict, or {} when the hook allowed unchanged."""
    if not out:
        return {}
    return out["hookSpecificOutput"]["updatedInput"]


# --- resolution order (max20) -----------------------------------------------

def test_default_is_sonnet():
    # no subagent_type (and any unknown agent) -> role `default` -> sonnet on max20
    ui = resolved(run_agent({"description": "do a thing"}))
    assert ui["model"] == "sonnet"
    assert ui["description"] == "[sonnet] do a thing"


def test_agent_pin_opus_beats_sonnet_label():
    out = run_agent({"description": "[sonnet] polish UI", "subagent_type": "frontend-uiux-designer"})
    ui = resolved(out)
    assert ui["model"] == "opus"
    assert ui["description"] == "[opus] polish UI"


def test_judges_pinned_opus():
    for at in ("santa-reviewer", "planning-director", "spec-architect", "debug-detective",
               "audit-specialist", "plan"):
        out = run_agent({"description": "[sonnet] work", "subagent_type": at})
        assert resolved(out)["model"] == "opus", at


def test_implementors_default_to_sonnet():
    for at in ("implementation-engineer", "backend-implementor-specialist",
               "frontend-implementor-specialist", "integrator-specialist"):
        out = run_agent({"description": "build feature", "subagent_type": at,
                         "prompt": "Add a created_at column to the users table and update the handler."})
        assert resolved(out)["model"] == "sonnet", at


# --- escalation --------------------------------------------------------------

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
    out = run_agent({"description": "fix", "model": "sonnet", "subagent_type": "implementation-engineer",
                     "prompt": "Previous attempt failed: still broken."})
    assert resolved(out)["model"] == "opus"


def test_non_execution_agents_never_escalate():
    # explore / docs roles are haiku; general-purpose is role `default` (sonnet on max20). None escalates.
    for at, want in (("explore", "haiku"), ("general-purpose", "sonnet"), ("deadcode-reaper", "haiku")):
        out = run_agent({"description": "x", "subagent_type": at,
                         "prompt": "Previous attempt failed. " + HEAVY})
        assert resolved(out)["model"] == want, at
        assert "escalated" not in out["hookSpecificOutput"]["additionalContext"]


def test_escalation_fail_open(monkeypatch):
    mod = _load_module()
    mod._POLICY_CACHE = None
    policy = mod._load_policy()
    mod._POLICY_CACHE = {**policy, "escalation": {**policy["escalation"], "retry_markers": ["("]}}
    monkeypatch.setattr(mod, "_flag_paths", lambda: {})
    assert mod._resolve_required("implementation-engineer", "", "x", None, HEAVY)[:2] == \
        ("sonnet", "role impl -> sonnet (tier max20)")


def test_routing_log_records_every_decision(monkeypatch, tmp_path):
    mod = _load_module()
    monkeypatch.setattr(mod, "_TELEMETRY_DIR", tmp_path)
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    mod._log_route("sid/1", "implementation-engineer", "opus", "previous attempt failed",
                   tier="max20", usage=False, fallback=["sonnet", "haiku"])
    rec = json.loads((tmp_path / "sid_1.model-routing.jsonl").read_text(encoding="utf-8").strip())
    assert (rec["agent"], rec["model"], rec["reason"]) == \
        ("implementation-engineer", "opus", "previous attempt failed")
    assert rec["tier"] == "max20" and rec["usage_guard"] is False and rec["fallback"] == ["sonnet", "haiku"]
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    mod._log_route("sid2", "x", "sonnet", "default")
    assert not (tmp_path / "sid2.model-routing.jsonl").exists()


def test_no_agent_is_auto_pinned_to_fable():
    mod = _load_module()
    mod._POLICY_CACHE = None
    pol = mod._load_policy()
    for t, blk in pol["tiers"].items():
        assert "fable" not in json.dumps(blk["roles"]) and "fable" not in json.dumps(blk["escalate"]), t
    assert not pol["agent_pins"]["fable"]


def test_unguarded_explore_label_honoured_within_cap():
    ui = resolved(run_agent({"description": "[opus] map the code", "subagent_type": "explore"}))
    assert ui["model"] == "opus" and ui["description"] == "[opus] map the code"
    TF.set_tier("pro")
    out = run_agent({"description": "[opus] map the code", "subagent_type": "explore"})
    assert resolved(out)["model"] == "sonnet" and "tier-cap" in out["hookSpecificOutput"]["additionalContext"]


def test_explicit_model_param_honored():
    ui = resolved(run_agent({"description": "special task", "model": "opus", "subagent_type": "general-purpose"}))
    assert ui["model"] == "opus"
    assert ui["description"] == "[opus] special task"


def test_label_prefix_used_when_no_pin_or_model():
    out = run_agent({"description": "[opus] heavy novel architecture", "subagent_type": "general-purpose"})
    assert resolved(out)["model"] == "opus"


def test_noop_when_already_correct():
    out = run_agent({"description": "[opus] polish", "model": "opus", "subagent_type": "frontend-uiux-designer"})
    assert out == {}


# --- session flags: haiku > sonnet > opus > fable, capped to the tier -------

def _flag_home(*flags: str) -> Path:
    home = _clean_home()
    for f in flags:
        (home / ".claude" / "state" / f).write_text("")
    return home


def test_sonnet_flag_overrides_opus_agent():
    out = run_agent({"description": "[opus] polish", "model": "opus", "subagent_type": "frontend-uiux-designer"},
                    home=_flag_home("sonnet-only-mode"))
    assert resolved(out)["model"] == "sonnet"


def test_opus_flag_overrides_sonnet_agent():
    out = run_agent({"description": "map", "subagent_type": "explore"}, home=_flag_home("opus-only-mode"))
    assert resolved(out)["model"] == "opus"


def test_fable_flag_forces_fable():
    out = run_agent({"description": "task", "subagent_type": "general-purpose"}, home=_flag_home("fable-only-mode"))
    assert resolved(out)["model"] == "fable"


def test_fable_flag_capped_on_pro():
    TF.set_tier("pro")
    out = run_agent({"description": "task", "subagent_type": "general-purpose"}, home=_flag_home("fable-only-mode"))
    assert resolved(out)["model"] == "sonnet" and "tier-cap" in out["hookSpecificOutput"]["additionalContext"]


def test_sonnet_flag_wins_precedence_over_opus_flag():
    out = run_agent({"description": "task", "subagent_type": "general-purpose"},
                    home=_flag_home("sonnet-only-mode", "opus-only-mode"))
    assert resolved(out)["model"] == "sonnet"


def test_haiku_flag_forces_haiku():
    out = run_agent({"description": "review", "subagent_type": "santa-reviewer"}, home=_flag_home("haiku-only-mode"))
    assert resolved(out)["model"] == "haiku"


def test_haiku_flag_beats_sonnet_flag():
    out = run_agent({"description": "task", "subagent_type": "general-purpose"},
                    home=_flag_home("sonnet-only-mode", "haiku-only-mode"))
    assert resolved(out)["model"] == "haiku"


# --- full-input echo --------------------------------------------------------

def test_full_input_echoed():
    ui = resolved(run_agent({"description": "do a thing", "subagent_type": "general-purpose",
                             "prompt": "a long prompt that must survive", "extra_key": {"nested": [1, 2]}}))
    assert ui["prompt"] == "a long prompt that must survive"
    assert ui["extra_key"] == {"nested": [1, 2]}
    assert ui["subagent_type"] == "general-purpose"
    assert ui["model"] == "sonnet"  # general-purpose is role default (sonnet on max20)


def test_general_purpose_is_the_plain_agent_default():
    """Claude Code's Agent default type is general-purpose and opus-guard already labels a call without
    `subagent_type` that way. Both spellings must land on the same model on every tier (FIX-1)."""
    for tier, want in (("pro", "haiku"), ("max5", "sonnet"), ("max20", "sonnet"), ("api", "sonnet")):
        TF.set_tier(tier)
        plain = resolved(run_agent({"description": "do a thing", "prompt": "x"}))["model"]
        named = run_agent({"description": "do a thing", "prompt": "x", "subagent_type": "general-purpose"})
        assert plain == resolved(named)["model"] == want, (tier, plain, resolved(named)["model"])
        assert "role default" in named["hookSpecificOutput"]["additionalContext"], tier


def test_name_never_rewritten():
    ui = resolved(run_agent({"description": "x", "subagent_type": "general-purpose", "name": "impl-crud-opus"}))
    assert ui["name"] == "impl-crud-opus"


def test_explicit_model_param_without_user_phrase_does_not_beat_pin():
    ui = resolved(run_agent({"description": "build it", "model": "sonnet", "subagent_type": "santa-reviewer"}))
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
    assert mod._resolve_required("general-purpose", "sonnet", "[sonnet] x", str(repo))[:2] == \
        ("opus", "per-project model mode")
    TF.set_tier("pro")  # the stored opus pin outranks the tier only up to its ceiling
    assert mod._resolve_required("general-purpose", "sonnet", "x", str(repo))[:2] == \
        ("sonnet", "per-project model mode; tier-cap: opus -> sonnet (pro)")
    assert mod._mm.set_mode(str(repo), None)
    assert mod._resolve_required("general-purpose", "sonnet", "x", str(repo))[0] == "sonnet"


# --- tiers, usage guard, telemetry ------------------------------------------

@pytest.mark.parametrize("tier,agent,want", [
    ("pro", "santa-reviewer", "sonnet"), ("pro", "frontend-uiux-designer", "sonnet"),
    ("pro", "implementation-engineer", "haiku"), ("pro", "test-author", "haiku"), ("pro", "qa-verifier", "haiku"),
    ("pro", "security-sentinel", "haiku"), ("pro", "general-purpose", "haiku"),
    ("max5", "santa-reviewer", "sonnet"), ("max5", "implementation-engineer", "sonnet"), ("max5", "explore", "haiku"),
    ("max5", "test-author", "sonnet"),
    ("max20", "santa-reviewer", "opus"), ("max20", "implementation-engineer", "sonnet"),
    ("max20", "docs-sync-agent", "haiku"), ("max20", "audit-specialist", "opus"),
    ("api", "santa-reviewer", "sonnet"), ("api", "deadcode-reaper", "haiku")])
def test_tier_matrix_per_role(tier, agent, want):
    TF.set_tier(tier)
    assert resolved(run_agent({"description": "work", "subagent_type": agent,
                               "prompt": "do the small thing"}))["model"] == want


def test_escalation_stays_within_the_ceiling():
    ti = {"description": "fix", "subagent_type": "implementation-engineer", "prompt": "Previous attempt failed."}
    for tier, want in (("pro", "sonnet"), ("max5", "sonnet"), ("max20", "opus")):
        TF.set_tier(tier)
        assert resolved(run_agent(ti))["model"] == want, tier


def test_usage_guard_steps_down_and_names_itself():
    TF.set_usage(85.0, time.time() + 3600)
    out = run_agent({"description": "fix", "subagent_type": "implementation-engineer",
                     "prompt": "Previous attempt failed."})
    assert resolved(out)["model"] == "sonnet" and "usage-guard" in out["hookSpecificOutput"]["additionalContext"]
    assert resolved(run_agent({"description": "review", "subagent_type": "santa-reviewer"}))["model"] == "sonnet"
    TF.set_tier("pro")
    assert resolved(run_agent({"description": "review", "subagent_type": "santa-reviewer"}))["model"] == "haiku"
    TF.set_usage(10.0, time.time() + 3600)
    TF.set_tier("max20")
    assert resolved(run_agent({"description": "review", "subagent_type": "santa-reviewer"}))["model"] == "opus"


def test_usage_guard_state_file_written_on_flip():
    TF.set_usage(90.0, time.time() + 3600)
    run_agent({"description": "x", "subagent_type": "explore"})
    assert json.loads((TF.state_dir() / "usage-guard.json").read_text(encoding="utf-8"))["active"] is True


def test_tier_cap_reason_in_telemetry(monkeypatch, tmp_path, capsys):
    mod = _load_module()
    monkeypatch.setattr(mod, "_TELEMETRY_DIR", tmp_path)
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    TF.set_tier("pro")
    assert mod.main_with_payload({"tool_name": "Agent", "session_id": "s9", "tool_input": {
        "description": "[opus] review", "model": "opus", "subagent_type": "general-purpose"}}) == 0
    rec = json.loads((tmp_path / "s9.model-routing.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["model"] == "sonnet" and "tier-cap" in rec["reason"] and rec["tier"] == "pro"
    assert rec["fallback"] == ["haiku"]
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["updatedInput"]["model"] == "sonnet"


def test_missing_tier_state_defaults_to_max20():
    TF.clear()
    assert resolved(run_agent({"description": "review", "subagent_type": "santa-reviewer"}))["model"] == "opus"


def test_note_is_short():
    out = run_agent({"description": "x", "subagent_type": "general-purpose"})
    assert len(out["hookSpecificOutput"]["additionalContext"]) <= 220


def test_doctor_fixture_exits_zero_with_json():
    payload = (ROOT / "tests" / "fixtures" / "hook-events" / "pre-tool-use-agent.json").read_text(encoding="utf-8")
    cp = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True)
    assert cp.returncode == 0 and isinstance(json.loads(cp.stdout), dict)


# --- policy-load fail-open (in-process; corrupt/missing policy -> literals) --

def _isolated_home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / ".claude" / "state").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


def test_policy_load_fail_open_missing(monkeypatch, tmp_path):
    mod = _load_module()
    mod._POLICY_CACHE = None
    monkeypatch.setattr(mod, "POLICY_PATH", tmp_path / "does-not-exist.json")
    _isolated_home(monkeypatch, tmp_path)
    assert mod._resolve_required("frontend-uiux-designer", "", "x")[0] == "opus"
    assert mod._resolve_required("general-purpose", "", "x")[0] == "sonnet"
    assert mod._default_model() == "sonnet"
    TF.set_tier("pro")
    assert mod._resolve_required("santa-reviewer", "", "x")[0] == "sonnet"  # literal ceiling


def test_policy_load_fail_open_corrupt(monkeypatch, tmp_path):
    mod = _load_module()
    mod._POLICY_CACHE = None
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not valid json ][")
    monkeypatch.setattr(mod, "POLICY_PATH", bad)
    _isolated_home(monkeypatch, tmp_path)
    assert mod._resolve_required("explore", "", "x")[0] == "sonnet"
    assert mod._resolve_required("santa-reviewer", "", "x")[0] == "opus"
    assert mod._resolve_required("implementation-engineer", "", "x")[0] == "sonnet"


def test_policy_actually_loaded_from_disk():
    mod = _load_module()
    mod._POLICY_CACHE = None
    agents = mod._load_policy()["roles"]["agents"]
    for j in ("santa-reviewer", "frontend-uiux-designer", "planning-director", "spec-architect",
              "debug-detective", "audit-specialist"):
        assert agents[j] == "judge", j
    for i in ("implementation-engineer", "backend-implementor-specialist", "frontend-implementor-specialist"):
        assert agents[i] == "impl", i
    assert agents["explore"] == "explore"
    assert mod._default_model() == "sonnet"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
