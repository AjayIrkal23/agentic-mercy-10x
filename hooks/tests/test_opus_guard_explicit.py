"""opus-guard: an explicit `model` (or [label]) may not override a pin or escalation unless
the user's own turn names that model (audit 2026-10-05 E-04, B1-21). Fable always needs
that phrase; a model outside the policy (haiku) is replaced with a logged reason."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "opus-guard.py"


def _transcript(tmp: Path, user_text: str | None) -> str:
    rows = [{"type": "user", "message": {"content": "earlier: use opus for everything"},
             "timestamp": "2026-10-05T10:00:00Z"},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}}]
    if user_text is not None:
        rows.append({"type": "user", "message": {"content": user_text},
                     "timestamp": "2026-10-05T10:01:00Z"})
    rows.append({"type": "user", "isMeta": True, "message": {"content": "use sonnet (skill body)"}})
    p = tmp / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return str(p)


def run(tool_input: dict, tmp: Path, user_text: str | None = "do the work") -> tuple[dict, list]:
    home = tmp / "home"
    (home / ".claude" / "state").mkdir(parents=True, exist_ok=True)
    tele = tmp / "tele"
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               CLAUDE_CONFIG_DIR=str(home / ".claude"), CLAUDE_HOOK_TELEMETRY_DIR=str(tele))
    env.pop("CLAUDE_HOOK_DOCTOR", None)
    payload = {"tool_name": "Agent", "tool_input": tool_input, "session_id": "s1",
               "cwd": str(tmp), "transcript_path": _transcript(tmp, user_text)}
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip() or "{}")
    log = tele / "s1.model-routing.jsonl"
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return out, rows


def model(out: dict, tool_input: dict) -> str:
    return out["hookSpecificOutput"]["updatedInput"]["model"] if out else tool_input.get("model", "")


def test_explicit_sonnet_cannot_downgrade_a_pinned_judge(tmp_path):
    ti = {"description": "review", "subagent_type": "santa-reviewer", "model": "sonnet"}
    out, rows = run(ti, tmp_path)
    assert model(out, ti) == "opus"
    assert "ignored" in rows[-1]["reason"] and "sonnet" in rows[-1]["reason"]


def test_user_phrase_lets_an_explicit_model_override_a_pin(tmp_path):
    ti = {"description": "review", "subagent_type": "santa-reviewer", "model": "sonnet"}
    out, rows = run(ti, tmp_path, "review the diff, use sonnet for this")
    assert model(out, ti) == "sonnet"
    assert "use sonnet" in rows[-1]["reason"]


def test_explicit_opus_cannot_upgrade_an_executor_without_a_phrase(tmp_path):
    ti = {"description": "build", "subagent_type": "implementation-engineer", "model": "opus"}
    assert model(run(ti, tmp_path)[0], ti) == "sonnet"
    assert model(run(ti, tmp_path, "build it, use opus")[0], ti) == "opus"


def test_explicit_sonnet_cannot_block_retry_escalation(tmp_path):
    ti = {"description": "fix", "subagent_type": "implementation-engineer", "model": "sonnet",
          "prompt": "Previous attempt failed: still broken."}
    assert model(run(ti, tmp_path)[0], ti) == "opus"


def test_opus_label_cannot_upgrade_an_executor_without_a_phrase(tmp_path):
    ti = {"description": "[opus] build", "subagent_type": "backend-implementor-specialist"}
    assert model(run(ti, tmp_path)[0], ti) == "sonnet"


def test_unguarded_agent_keeps_an_explicit_opus(tmp_path):
    ti = {"description": "research", "subagent_type": "general-purpose", "model": "opus"}
    out, rows = run(ti, tmp_path)
    assert model(out, ti) == "opus"
    assert rows[-1]["reason"] == "explicit model param"


def test_fable_needs_the_users_phrase_everywhere(tmp_path):
    ti = {"description": "special", "subagent_type": "general-purpose", "model": "fable"}
    assert model(run(ti, tmp_path)[0], ti) == "sonnet"
    assert model(run(ti, tmp_path, "use fable for this")[0], ti) == "fable"


def test_meta_rows_and_older_turns_are_not_the_users_phrase(tmp_path):
    # "use opus" sits in an older turn and "use sonnet" in an isMeta skill body: neither counts.
    ti = {"description": "review", "subagent_type": "santa-reviewer", "model": "sonnet"}
    assert model(run(ti, tmp_path, "now review it")[0], ti) == "opus"


def test_haiku_is_replaced_with_a_visible_reason(tmp_path):
    ti = {"description": "tests", "subagent_type": "test-author", "model": "haiku"}
    out, rows = run(ti, tmp_path)
    assert model(out, ti) == "sonnet"
    assert "haiku" in rows[-1]["reason"]
    assert "haiku" in out["hookSpecificOutput"]["additionalContext"]


def test_no_transcript_means_no_phrase(tmp_path):
    ti = {"description": "plan", "subagent_type": "planning-director", "model": "sonnet"}
    out, _ = run(ti, tmp_path, None)
    assert model(out, ti) == "opus"
