"""WP-C (autonomy 2026-10-05) item 2: saving a memory no longer depends on the model remembering.

When the user's prompt this human turn said remember / going forward / we decided / from
now on / always ... / never ..., and the turn saved nothing (no Memory MCP add_observations
or create_entities, no write under projects/*/memory/, no CODEX.md edit), the Stop gate
blocks ONCE (same once-per-turn budget as the other gates) and tells the model to save.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
GATE = _HOOKS / "hard-completion-gate.py"
NOW = datetime.now(timezone.utc).isoformat()


def _user(text: str) -> dict:
    return {"type": "user", "timestamp": NOW, "message": {"role": "user", "content": text}}


def _tool(name: str, **inp) -> dict:
    return {"type": "assistant", "timestamp": NOW, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": name, "input": inp}]}}


def _run(tmp_path, rows: list, cid: str = "mem-c1", **extra) -> dict:
    tr = tmp_path / f"{cid}.jsonl"
    tr.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    env = dict(os.environ, CLAUDE_HOOK_DOTSTATE_DIR=str(tmp_path / "dot"),
               CLAUDE_HOOK_TELEMETRY_DIR=str(tmp_path / "tel"))
    payload = dict({"session_id": cid, "transcript_path": str(tr)}, **extra)
    cp = subprocess.run([sys.executable, str(GATE)], input=json.dumps(payload), text=True,
                        capture_output=True, timeout=20, check=False, env=env)
    return json.loads(cp.stdout.strip().splitlines()[-1])


CUES = ["remember that the staging db is read-only", "going forward use pnpm here",
        "we decided to keep Redux for the store", "from now on commit messages are lowercase",
        "always use the typed-routes helpers", "never use raw Error in controllers",
        "please remember this", "Remember: deploys happen on Friday"]


@pytest.mark.parametrize("prompt", CUES)
def test_blocks_once_when_a_remember_cue_saved_nothing(tmp_path, prompt):
    out = _run(tmp_path, [_user(prompt), _tool("Read", file_path="/x")])
    assert out.get("decision") == "block", out
    reason = out["reason"]
    assert "save it now" in reason and "mcp__memory__add_observations" in reason
    assert "decision::<repo>::<topic>" in reason and "auto-memory file" in reason
    assert "then finish" in reason and "/invoke" not in reason


def test_second_stop_in_the_same_turn_passes(tmp_path):
    rows = [_user("going forward use pnpm here")]
    assert _run(tmp_path, rows).get("decision") == "block"
    again = _run(tmp_path, rows)
    assert again.get("decision") is None and "systemMessage" not in again  # CLAUDE.md §11: queued for the model


@pytest.mark.parametrize("saved", [
    _tool("mcp__memory__add_observations", observations=[]),
    _tool("mcp__memory__create_entities", entities=[]),
    _tool("Write", file_path="/srv/cfg/.claude/projects/-srv-repo/memory/feedback_pnpm.md"),
    _tool("Edit", file_path="/work/repo/CODEX.md"),
    _tool("Edit", file_path="D:\\cfg\\.claude\\projects\\p\\memory\\MEMORY.md"),
])
def test_any_save_this_turn_passes(tmp_path, saved):
    assert _run(tmp_path, [_user("we decided to keep Redux"), saved]) == {}


def test_a_save_in_an_earlier_turn_does_not_count(tmp_path):
    rows = [_user("remember this"), _tool("mcp__memory__add_observations"),
            _user("going forward use pnpm"), _tool("Read", file_path="/x")]
    assert _run(tmp_path, rows).get("decision") == "block"


@pytest.mark.parametrize("prompt", [
    "fix the login bug", "do you remember how the router works?",
    "never mind, carry on", "it is always sunny in the test fixtures",
    # SANTA-autonomy: prompts that mention the words but ask for no save
    "I don't remember which file has the auth check, find it and fix it.",
    "Remember the failing test from yesterday; fix it now.",
    "why does the cron job always run twice",
    "the old code would never touch the cache, restore that behavior",
    "fix the bug where `remember me` checkbox is ignored",
    'the toast says "always use HTTPS", make it smaller',
    "does it always use the cache? check it",
])
def test_no_cue_no_block(tmp_path, prompt):
    assert _run(tmp_path, [_user(prompt), _tool("Read", file_path="/x")]) == {}


def test_stop_hook_active_and_missing_transcript_fail_open(tmp_path):
    rows = [_user("remember that x")]
    assert _run(tmp_path, rows, stop_hook_active=True) == {}
    cp = subprocess.run([sys.executable, str(GATE)], text=True, capture_output=True, check=False,
                        input=json.dumps({"session_id": "m3", "transcript_path": str(tmp_path / "none")}),
                        env=dict(os.environ, CLAUDE_HOOK_DOTSTATE_DIR=str(tmp_path / "d2"),
                                 CLAUDE_HOOK_TELEMETRY_DIR=str(tmp_path / "t2")))
    assert json.loads(cp.stdout) == {}


def test_cue_inside_a_code_fence_is_ignored(tmp_path):
    prompt = "fix this:\n```\n# remember that x\n```\nthanks"
    assert _run(tmp_path, [_user(prompt)]) == {}


def test_mercy_remember_tool_counts_as_a_save(tmp_path):
    assert _run(tmp_path, [_user("remember that x"), _tool("mcp__mercy__remember", fact="x")]) == {}
