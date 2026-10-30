#!/usr/bin/env python3
"""Regression tests for hooks/workflow-model-guard.py (P2-T1, Spec A §3.3 t1-t6).

These lock in the arg-drop crash fix. Where runtime behavior of the injected JS
wrapper matters (t2/t3/t4/t6), the rewritten script is EXECUTED under node with a
recording `agent` stub — the gold standard: we observe the exact arguments the real
`agent` runtime global receives, so the tests prove the wrapper does not truncate or
corrupt calls rather than merely inspecting the rewritten text.

Isolation: every hook run uses HOME=<tmp> so session-flag files
(~/.claude/state/*-only-mode) are read from a throwaway dir — the real state is never
touched. model-policy.json (once P2-T3 lands) loads via __file__ from the real hooks
dir, unaffected by the HOME override.

Requires: node on PATH (for the runtime-behavior tests). Run: pytest hooks/tests/
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "workflow-model-guard.py"
ROOT = HOOK.parent.parent
NODE = shutil.which("node")
node_required = pytest.mark.skipif(NODE is None, reason="node not on PATH")
sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "plan-tier"))
import tier_fixture as TF  # noqa: E402


@pytest.fixture(autouse=True)
def _max20_default():
    TF.set_tier("max20")
    TF.set_usage(None)
    yield
    TF.clear()


_HOMES: list = []


def _clean_home() -> Path:
    """A tmp HOME with an empty ~/.claude/state (no session flags set); removed after the test."""
    home = Path(tempfile.mkdtemp(prefix="wfguard-home-"))
    _HOMES.append(home)
    (home / ".claude" / "state").mkdir(parents=True)
    return home


@pytest.fixture(autouse=True)
def _remove_homes():
    yield
    while _HOMES:
        shutil.rmtree(_HOMES.pop(), ignore_errors=True)


def run_hook(tool_input: dict, home: Path | None = None, env_extra: dict | None = None,
             payload_extra: dict | None = None) -> dict:
    """Invoke the hook as a subprocess and return the parsed stdout ({} if empty)."""
    payload = {"tool_name": "Workflow", "tool_input": tool_input, **(payload_extra or {})}
    h = str(home or _clean_home())
    env = dict(os.environ)
    # Path.home() reads USERPROFILE on Windows and HOME on POSIX — set both so the
    # throwaway ~/.claude/state session flags resolve on every OS.
    env["HOME"] = h
    env["USERPROFILE"] = h
    env.pop("HOMEDRIVE", None)
    env.pop("HOMEPATH", None)
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.update(env_extra or {})
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


def rewritten_script(out: dict) -> str:
    return out["hookSpecificOutput"]["updatedInput"]["script"]


def run_in_node(script: str) -> list:
    """Execute a rewritten workflow script under node with a recording `agent` stub.

    Returns the list of argument-arrays the underlying agent runtime received.
    """
    assert NODE is not None
    harness = (
        "globalThis.__calls = [];\n"
        "globalThis.agent = (...a) => { globalThis.__calls.push(a); return 'R'; };\n"
        + script
        + "\nprocess.stdout.write(JSON.stringify(globalThis.__calls));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(harness)
        path = f.name
    try:
        proc = subprocess.run([NODE, path], capture_output=True, text=True)
        assert proc.returncode == 0, f"node failed: {proc.stderr}"
        return json.loads(proc.stdout)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# t1 — a top-level tool_input.args survives byte-for-byte in updatedInput.
# ---------------------------------------------------------------------------
def test_t1_toplevel_args_survive_byte_for_byte():
    script = "export const meta = { name: 'x' };\nagent('P', {});\n"
    args = {"foo": "bar", "n": 3, "nested": {"a": [1, 2, 3]}}
    out = run_hook({"script": script, "args": args})
    updated = out["hookSpecificOutput"]["updatedInput"]
    assert updated["args"] == args  # byte-for-byte, not dropped or mutated
    assert "__wfAgent" in updated["script"]


# ---------------------------------------------------------------------------
# t2 — a 3rd+ argument to agent() is preserved (defect 1: the crash).
# ---------------------------------------------------------------------------
@node_required
def test_t2_extra_argument_preserved():
    script = "agent('P', {agentType: 'coder'}, 'EXTRA_ARG');\n"
    out = run_hook({"script": script})
    new_script = rewritten_script(out)
    assert "__wfAgent" in new_script
    assert "...rest" in new_script  # wrapper forwards trailing args
    calls = run_in_node(new_script)
    assert len(calls) == 1
    assert calls[0][0] == "P"
    assert calls[0][2] == "EXTRA_ARG"  # the 3rd arg was NOT truncated
    assert calls[0][1]["agentType"] == "coder"
    assert calls[0][1]["model"] == "sonnet"  # default pin still applied to opts


# ---------------------------------------------------------------------------
# t3 — a non-object 2nd arg passes through unmodified (defect 2).
# ---------------------------------------------------------------------------
@node_required
def test_t3_string_opts_passthrough_unmodified():
    script = "agent('P', 'stringopts');\n"
    out = run_hook({"script": script})
    calls = run_in_node(rewritten_script(out))
    # untouched: no {} replacement, no injected model — exact original args
    assert calls == [["P", "stringopts"]]


# ---------------------------------------------------------------------------
# t4 — a script with NO meta block still gets pinned (defect 3).
# ---------------------------------------------------------------------------
@node_required
def test_t4_no_meta_script_still_pinned():
    script = "agent('P', {});\n"  # no `export const meta = {`
    out = run_hook({"script": script})
    new_script = rewritten_script(out)
    assert "__wfAgent" in new_script
    calls = run_in_node(new_script)
    assert calls[0][1]["model"] == "sonnet"


# ---------------------------------------------------------------------------
# t5 — idempotence: an already-processed script (marker present) is left alone.
# ---------------------------------------------------------------------------
def test_t5_idempotent_when_marker_present():
    script = "export const meta = {};\n/* __wfAgent already injected */\nagent('P', {});\n"
    out = run_hook({"script": script})
    assert out == {}  # allow unchanged


# ---------------------------------------------------------------------------
# t6 — each session flag forces its model on every agent() (kill-switch).
# ---------------------------------------------------------------------------
@node_required
@pytest.mark.parametrize(
    "flag,model",
    [
        ("haiku-only-mode", "haiku"),
        ("sonnet-only-mode", "sonnet"),
        ("opus-only-mode", "opus"),
        ("fable-only-mode", "fable"),
    ],
)
def test_t6_session_flag_forces_model(flag, model):
    home = _clean_home()
    (home / ".claude" / "state" / flag).write_text("")
    # coder would default to sonnet; the flag must override to the forced model.
    script = "agent('P', {agentType: 'coder'});\n"
    out = run_hook({"script": script}, home=home)
    calls = run_in_node(rewritten_script(out))
    assert calls[0][1]["model"] == model


# ---------------------------------------------------------------------------
# t7-t10 — plan tiers (R3.3): role lookup, I-5 escalation, cap, usage guard, saved scripts.
# ---------------------------------------------------------------------------
@node_required
def test_t7_role_lookup_by_agent_type_then_label_then_default():
    script = ("agent('a', {agentType: 'santa-reviewer'});\nagent('b', {label: 'backend'});\n"
              "agent('c', {label: 'qa'});\nagent('d', {});\nagent('e', {agentType: 'explore'});\n")
    calls = run_in_node(rewritten_script(run_hook({"script": script})))
    assert [c[1]["model"] for c in calls] == ["opus", "sonnet", "haiku", "sonnet", "haiku"]
    TF.set_tier("pro")
    calls = run_in_node(rewritten_script(run_hook({"script": script})))
    assert [c[1]["model"] for c in calls] == ["sonnet", "haiku", "haiku", "haiku", "haiku"]


@node_required
def test_t8_escalation_from_the_call_prompt_lifts_executors_only_within_ceiling():
    script = ("export const meta = {name: 'x'};\n"
              "agent('the previous attempt failed; implement the fix', {agentType: 'implementation-engineer'});\n"
              "agent('the previous attempt failed; review it', {agentType: 'santa-reviewer'});\n"
              "agent('the previous attempt failed; look', {agentType: 'explore'});\n")
    for tier, want in (("pro", ["sonnet", "sonnet", "haiku"]), ("max5", ["sonnet", "sonnet", "haiku"]),
                       ("max20", ["opus", "opus", "haiku"])):
        TF.set_tier(tier)
        out = run_hook({"script": script})
        assert [c[1]["model"] for c in run_in_node(rewritten_script(out))] == want, tier
        assert "escalat" in out["hookSpecificOutput"]["additionalContext"]


@node_required
def test_retry_template_in_the_script_escalates_per_call_not_statically():
    """REVIEW2 fix 3: a fix loop's retry wording in the script source lifts only the calls whose
    prompt actually reports a failed attempt; the first call runs on the tier's normal model."""
    script = ("export const meta = {name: 'loop'};\nlet err = null;\n"
              "for (let i = 0; i < 3; i++) {\n"
              "  agent(err ? 'The previous attempt failed: ' + err : 'implement it', "
              "{agentType: 'implementation-engineer'});\n"
              "  err = 'tests red';\n}\nagent('look around', {agentType: 'explore'});\n")
    for tier, want in (("max20", ["sonnet", "opus", "opus", "haiku"]),
                       ("max5", ["sonnet", "sonnet", "sonnet", "haiku"]),
                       ("pro", ["haiku", "sonnet", "sonnet", "haiku"])):
        TF.set_tier(tier)
        assert [c[1]["model"] for c in run_in_node(rewritten_script(run_hook({"script": script})))] == want, tier
    # a task-level retry still escalates every executor call
    TF.set_tier("max20")
    out = run_hook({"script": script, "args": {"task": "the previous attempt failed, redo it"}})
    assert [c[1]["model"] for c in run_in_node(rewritten_script(out))] == ["opus", "opus", "opus", "haiku"]


@node_required
def test_label_role_lookup_matches_tokens_not_substrings():
    """REVIEW2 fix 4: `inspect-logs` is not `spec`, `preview-pages` is not `review`."""
    labels = ["inspect-logs", "preview-pages", "redesign-hero", "simple-fix",
              "review:pkg", "spec:auth", "integrator", "santa-2"]
    script = "".join(f"agent('x', {{label: '{lb}'}});\n" for lb in labels)
    calls = run_in_node(rewritten_script(run_hook({"script": script})))
    assert [c[1]["model"] for c in calls] == ["sonnet"] * 4 + ["opus", "opus", "sonnet", "opus"]
    TF.set_tier("max20")
    out = run_hook({"script": "agent('x', {label: 'integrator'});\n", "args": {"task": "previous attempt failed"}})
    assert run_in_node(rewritten_script(out))[0][1]["model"] == "opus"  # integrat -> integrate, escalated


def _pin(home: Path, cwd: Path, model: str) -> None:
    sys.path.insert(0, str(HOOK.parent))
    from lib import model_mode as mm  # noqa: PLC0415
    d = home / ".claude" / "state" / "model-modes"
    d.mkdir(parents=True, exist_ok=True)
    (d / mm.repo_key(str(cwd))).write_text(model + "\n", encoding="utf-8")


@node_required
def test_forced_per_project_pin_steps_down_under_the_usage_guard(tmp_path):
    """REVIEW2 fix 2: the per-project pin is not the user's words this turn, so the guard steps it
    down like opus-guard does; a global flag is the user's words and is kept."""
    script = "agent('P', {agentType: 'coder'});\n"
    cwd = tmp_path / "proj"
    cwd.mkdir()
    home = _clean_home()
    _pin(home, cwd, "opus")
    pl = {"cwd": str(cwd)}
    assert run_in_node(rewritten_script(run_hook({"script": script}, home=home, payload_extra=pl)))[0][1]["model"] == "opus"
    TF.set_usage(90.0, time.time() + 3600)
    out = run_hook({"script": script}, home=home, payload_extra=pl)
    assert run_in_node(rewritten_script(out))[0][1]["model"] == "sonnet"
    flag_home = _clean_home()
    (flag_home / ".claude" / "state" / "opus-only-mode").write_text("")
    out = run_hook({"script": script}, home=flag_home, payload_extra=pl)
    assert run_in_node(rewritten_script(out))[0][1]["model"] == "opus"


@node_required
def test_t8b_escalation_from_args_task():
    out = run_hook({"script": "agent('p', {agentType: 'implementation-engineer'});\n",
                    "args": {"task": "Previous attempt failed: tests still red"}})
    assert run_in_node(rewritten_script(out))[0][1]["model"] == "opus"  # max20


@node_required
def test_explicit_model_capped_and_fable_needs_phrase():
    script = ("agent('a', {model: 'opus'});\nagent('b', {model: 'fable'});\n"
              "agent('c', {model: 'haiku', agentType: 'santa-reviewer'});\n")
    TF.set_tier("pro")
    calls = run_in_node(rewritten_script(run_hook({"script": script})))
    assert [c[1]["model"] for c in calls] == ["sonnet", "sonnet", "haiku"]
    TF.set_tier("max20")
    calls = run_in_node(rewritten_script(run_hook({"script": script})))
    assert [c[1]["model"] for c in calls] == ["opus", "sonnet", "haiku"]  # fable without the phrase -> sonnet


@node_required
def test_explicit_fable_with_the_users_phrase(tmp_path):
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"type": "user", "message": {"content": "run it, use fable for this"},
                              "timestamp": "2026-10-29T10:00:00Z"}) + "\n", encoding="utf-8")
    out = run_hook({"script": "agent('b', {model: 'fable'});\n"}, payload_extra={"transcript_path": str(tr)})
    assert run_in_node(rewritten_script(out))[0][1]["model"] == "fable"


@node_required
def test_ask_only_opus_needs_the_phrase_inline(tmp_path):
    script = "agent('a', {model: 'opus'});\n"
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps({"type": "user", "message": {"content": "run it, use opus for this"},
                              "timestamp": "2026-10-29T10:00:00Z"}) + "\n", encoding="utf-8")
    TF.set_tier("max5")
    assert run_in_node(rewritten_script(run_hook({"script": script})))[0][1]["model"] == "sonnet"
    out = run_hook({"script": script}, payload_extra={"transcript_path": str(tr)})
    assert run_in_node(rewritten_script(out))[0][1]["model"] == "opus"
    TF.set_tier("max20")
    assert run_in_node(rewritten_script(run_hook({"script": script})))[0][1]["model"] == "opus"
    TF.set_usage(90.0, time.time() + 3600)
    assert run_in_node(rewritten_script(run_hook({"script": script})))[0][1]["model"] == "sonnet"


@node_required
def test_usage_guard_applies_inside_the_wrapper():
    TF.set_usage(90.0, time.time() + 3600)
    script = ("agent('a', {agentType: 'implementation-engineer'});\nagent('b', {agentType: 'santa-reviewer'});\n"
              "agent('c', {model: 'fable'});\n")
    out = run_hook({"script": script})
    calls = run_in_node(rewritten_script(out))
    assert [c[1]["model"] for c in calls] == ["haiku", "sonnet", "sonnet"]
    assert "usage-guard" in out["hookSpecificOutput"]["additionalContext"]


def test_t9_saved_script_advisory_only_on_drift():
    home = _clean_home()
    wf = home / ".claude" / "workflows"
    wf.mkdir(parents=True)
    (wf / ".rendered.json").write_text(json.dumps({"tier": "max20", "usage_guard": False, "policy_sha": "x", "ts": 1}))
    env_extra = {"CLAUDE_CONFIG_DIR": str(home / ".claude")}
    assert run_hook({"name": "review", "args": {"run": "/tmp/r"}}, home=home, env_extra=env_extra) == {}
    TF.set_tier("pro")
    out = run_hook({"name": "review", "args": {"run": "/tmp/r"}}, home=home, env_extra=env_extra)
    note = out["hookSpecificOutput"]["additionalContext"]
    assert "max20" in note and "pro" in note and "regenerat" in note
    assert "updatedInput" not in out["hookSpecificOutput"]  # nothing on disk or in the input is rewritten


def test_t9b_saved_script_without_rendered_json_gets_the_legacy_advisory():
    out = run_hook({"scriptPath": "/x/y.js"})
    assert "explicit model" in out["hookSpecificOutput"]["additionalContext"]


def test_t10_saved_script_gets_tier_hint_when_args_task_escalates():
    out = run_hook({"name": "invoke", "args": {"acts": ["impl"], "task": "Previous attempt failed, redo it",
                                               "run": "/tmp/r"}})
    ui = out["hookSpecificOutput"]["updatedInput"]
    assert ui["args"]["tier_hint"] == "escalate" and ui["args"]["task"].startswith("Previous") and "name" in ui
    out = run_hook({"name": "invoke", "args": {"acts": ["impl"], "task": "small fix per plan-2026-10-29-x.md",
                                               "run": "/tmp/r"}})
    assert "updatedInput" not in out.get("hookSpecificOutput", {})  # no escalation -> args untouched


def test_routing_telemetry_row(tmp_path):
    tele = tmp_path / "tele"
    run_hook({"script": "agent('p', {agentType: 'explore'});\n"}, env_extra={"CLAUDE_HOOK_TELEMETRY_DIR": str(tele)},
             payload_extra={"session_id": "w1"})
    rec = json.loads((tele / "w1.model-routing.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["agent"] == "workflow:inline" and rec["tier"] == "max20" and rec["usage_guard"] is False


def test_doctor_fixture_still_rewrites():
    payload = (ROOT / "tests" / "fixtures" / "hook-events" / "workflow-model-guard.json").read_text(encoding="utf-8")
    cp = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True)
    assert cp.returncode == 0 and "__wfAgent" in cp.stdout


def test_the_throwaway_homes_are_removed_after_each_test(tmp_path):
    """A7v2-06: `_clean_home()` left a `wfguard-home-*` dir in %TEMP% per hook run (8 per suite run).
    Run two of the file's tests in a child pytest whose temp dir is ours: nothing may be left behind."""
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    env = {**os.environ, "TEMP": str(tmpdir), "TMP": str(tmpdir), "TMPDIR": str(tmpdir),
           "CLAUDE_HOOK_DOCTOR": "1"}
    for var in ("CLAUDE_HOOK_TELEMETRY_DIR", "CLAUDE_HOOK_STATE_DIR", "CLAUDE_HOOK_DOTSTATE_DIR"):
        env.pop(var, None)  # the child's conftest makes its own, inside our temp dir
    cp = subprocess.run([sys.executable, "-m", "pytest", str(Path(__file__)), "-q", "-p", "no:cacheprovider",
                         "-k", "t1_toplevel or t5_idempotent"], env=env, capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=120)
    assert cp.returncode == 0, cp.stdout[-800:]
    assert [p.name for p in tmpdir.iterdir() if p.name.startswith("wfguard-home-")] == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
