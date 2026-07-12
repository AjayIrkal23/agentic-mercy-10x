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
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "workflow-model-guard.py"
NODE = shutil.which("node")
node_required = pytest.mark.skipif(NODE is None, reason="node not on PATH")


def _clean_home() -> Path:
    """A tmp HOME with an empty ~/.claude/state (no session flags set)."""
    home = Path(tempfile.mkdtemp(prefix="wfguard-home-"))
    (home / ".claude" / "state").mkdir(parents=True)
    return home


def run_hook(tool_input: dict, home: Path | None = None) -> dict:
    """Invoke the hook as a subprocess and return the parsed stdout ({} if empty)."""
    payload = {"tool_name": "Workflow", "tool_input": tool_input}
    h = str(home or _clean_home())
    env = dict(os.environ)
    # Path.home() reads USERPROFILE on Windows and HOME on POSIX — set both so the
    # throwaway ~/.claude/state session flags resolve on every OS.
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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
