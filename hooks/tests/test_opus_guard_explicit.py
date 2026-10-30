"""opus-guard: an explicit `model` (or [label]) may not override a guarded role (judge, executor)
or escalation unless the user's own turn names that model (audit 2026-10-05 E-04, B1-21). Fable
always needs that phrase; every result is capped to the plan tier (R3.3), and the usage guard
pauses fable. The tier is pinned per test (default max20) through tier_fixture."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "opus-guard.py"
sys.path.insert(0, str(HOOK.parent.parent / "tests" / "fixtures" / "plan-tier"))
import tier_fixture as TF  # noqa: E402


@pytest.fixture(autouse=True)
def _max20_default():
    TF.set_tier("max20")
    TF.set_usage(None)
    yield
    TF.clear()


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


def test_haiku_is_a_policy_model_now(tmp_path):
    ti = {"description": "tests", "subagent_type": "test-author", "model": "haiku"}
    out, rows = run(ti, tmp_path)
    assert model(out, ti) == "sonnet"  # test-author is guarded: no phrase, the request is ignored
    assert "ignored" in rows[-1]["reason"] and "haiku" in rows[-1]["reason"]
    assert "haiku" in out["hookSpecificOutput"]["additionalContext"]
    assert model(run(ti, tmp_path, "write the tests, use haiku")[0], ti) == "haiku"


def test_opus_phrase_lifts_a_judge_on_max5_but_not_on_pro(tmp_path):
    TF.set_tier("max5")
    ti = {"description": "review", "subagent_type": "santa-reviewer"}
    assert model(run(ti, tmp_path, "review it")[0], ti) == "sonnet"
    assert model(run(ti, tmp_path, "review it, use opus")[0], ti) == "opus"  # the phrase alone lifts
    ti2 = {**ti, "model": "opus"}
    assert model(run(ti2, tmp_path, "review it, use opus")[0], ti2) == "opus"
    TF.set_tier("pro")
    out, rows = run(ti2, tmp_path, "review it, use opus")
    assert model(out, ti2) == "sonnet" and "over the pro ceiling" in rows[-1]["reason"]


def test_fable_phrase_only_counts_on_max20(tmp_path):
    ti = {"description": "special", "subagent_type": "general-purpose", "model": "fable"}
    assert model(run(ti, tmp_path, "use fable for this")[0], ti) == "fable"
    TF.set_tier("max5")
    # SANTA-FINAL D4: over the max5 ceiling -> role route, not a silent Opus (that needs "use opus")
    out, rows = run(ti, tmp_path, "use fable for this")
    assert model(out, ti) == "sonnet" and "over the max5 ceiling" in rows[-1]["reason"]
    assert model(run(ti, tmp_path, "use fable for this, or use opus")[0], ti) == "opus"


def test_fable_paused_under_usage_guard(tmp_path):
    TF.set_usage(88.0, time.time() + 3600)
    ti = {"description": "special", "subagent_type": "general-purpose", "model": "fable"}
    out, rows = run(ti, tmp_path, "use fable for this")
    assert model(out, ti) == "sonnet" and "usage-guard" in rows[-1]["reason"]


def test_explicit_opus_with_phrase_survives_usage_guard(tmp_path):  # the user's word wins over the guard
    TF.set_usage(88.0, time.time() + 3600)
    ti = {"description": "build", "subagent_type": "implementation-engineer", "model": "opus"}
    assert model(run(ti, tmp_path, "build it, use opus")[0], ti) == "opus"


@pytest.mark.parametrize("tier", ["max5", "api"])
def test_ask_only_opus_needs_the_phrase_for_an_unguarded_role(tmp_path, tier):
    TF.set_tier(tier)
    ti = {"description": "research", "subagent_type": "general-purpose", "model": "opus"}
    out, rows = run(ti, tmp_path)
    assert model(out, ti) == "sonnet" and "ignored" in rows[-1]["reason"]
    assert model(run(ti, tmp_path, "please use opus for this")[0], ti) == "opus"


def test_bare_explicit_opus_is_stepped_down_by_the_usage_guard(tmp_path):
    TF.set_usage(88.0, time.time() + 3600)
    ti = {"description": "research", "subagent_type": "general-purpose", "model": "opus"}
    out, rows = run(ti, tmp_path)
    assert model(out, ti) == "sonnet" and "usage-guard: opus -> sonnet" in rows[-1]["reason"]


def test_max20_judge_with_the_users_opus_phrase_survives_the_usage_guard(tmp_path):
    """Final-fix 3 (live r2): max20 + guard on + "use opus" + no model param used to land on sonnet."""
    TF.set_usage(88.0, time.time() + 3600)
    ti = {"description": "review", "subagent_type": "santa-reviewer"}
    out, rows = run(ti, tmp_path, "review the diff, use opus")
    assert model(out, ti) == "opus" and "user said" in rows[-1]["reason"]
    TF.set_tier("pro")  # inside the Pro ceiling the phrase also wins over the guard
    ti2 = {"description": "build", "subagent_type": "implementation-engineer"}
    out, rows = run(ti2, tmp_path, "build it, use sonnet")
    assert model(out, ti2) == "sonnet" and "user said" in rows[-1]["reason"]


def test_no_transcript_means_no_phrase(tmp_path):
    ti = {"description": "plan", "subagent_type": "planning-director", "model": "sonnet"}
    out, _ = run(ti, tmp_path, None)
    assert model(out, ti) == "opus"
