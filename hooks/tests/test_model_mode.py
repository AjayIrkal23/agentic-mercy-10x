"""lib/model_mode.py — per-project subagent model mode (D4), tier caps, the shared resolver
(role -> tier -> escalation -> usage -> cap) and the scripts/model-mode.py CLI (MERGE-PLAN R3.3)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent
ROOT = HOOKS.parent
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "plan-tier"))
from lib import model_mode as mm  # noqa: E402
import tier_fixture as TF  # noqa: E402

POL = json.loads((HOOKS / "model-policy.json").read_text(encoding="utf-8"))
HEAVY = ("Rebuild the whole notification system end-to-end: real-time websocket "
         "event-driven pipeline across the codebase, frontend and backend.")


@pytest.fixture(autouse=True)
def _max20_default():
    TF.set_tier("max20")
    TF.set_usage(None)
    yield
    TF.clear()


@pytest.fixture
def repo(monkeypatch, tmp_path):
    monkeypatch.setattr(mm, "modes_dir", lambda: tmp_path / "model-modes")
    r = tmp_path / "repo"
    (r / "sub").mkdir(parents=True)
    return r


def test_repo_key_stable_and_none_for_empty(repo):
    assert mm.repo_key(None) is None
    assert mm.repo_key(str(repo)) == mm.repo_key(str(repo))
    assert mm.repo_key(str(repo)).startswith("repo-")


def test_set_get_clear(repo):
    assert mm.forced_mode(str(repo)) is None
    assert mm.set_mode(str(repo), "OPUS")
    assert mm.forced_mode(str(repo)) == "opus"
    assert not mm.set_mode(str(repo), "gpt")
    assert mm.set_mode(str(repo), None)
    assert mm.forced_mode(str(repo)) is None


def test_subdir_shares_mode_when_git_repo(repo):
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert mm.set_mode(str(repo / "sub"), "fable")
    assert mm.forced_mode(str(repo)) == "fable"


def test_modes_include_haiku_and_set_mode_caps_to_the_tier(repo):
    assert mm.MODES == ("haiku", "sonnet", "opus", "fable")
    TF.set_tier("pro")
    assert mm.set_mode(str(repo), "opus") and mm.forced_mode(str(repo)) == "sonnet"  # stored capped
    assert mm.cap_reason("opus") == "opus exceeds the pro ceiling (sonnet); stored sonnet"
    TF.set_tier("max20")
    assert mm.set_mode(str(repo), "fable") and mm.forced_mode(str(repo)) == "fable"
    assert mm.cap_reason("fable") is None
    TF.set_tier("max5")
    assert mm.forced_mode(str(repo)) == "opus"  # an over-ceiling pin is capped on READ too
    assert mm.forced_mode(str(repo), cap=False) == "fable"  # the file itself is untouched


def test_escalation_signal_text_only():
    assert mm.escalation_signal(POL, "Previous attempt failed: still red", None) == "previous attempt failed"
    assert mm.escalation_signal(POL, "Execute plan-2026-10-29-x.md task 3", None) is None
    assert mm.escalation_signal(POL, "fix the typo in README", None) is None
    assert "large task with no plan" in (mm.escalation_signal(POL, HEAVY, None) or "")
    assert mm.escalation_signal({"escalation": {"enabled": True, "retry_markers": ["("]}}, "x", None) is None


def test_escalation_reason_keeps_its_signature_and_membership():
    assert mm.escalation_reason(POL, "implementation-engineer", "Previous attempt failed", None)
    assert mm.escalation_reason(POL, "test-author", "Previous attempt failed", None)  # role test escalates on pro/max5
    assert mm.escalation_reason(POL, "explore", "Previous attempt failed", None) is None
    assert mm.escalation_reason(POL, "santa-reviewer", "Previous attempt failed", None) is None


@pytest.mark.parametrize("tier,agent,asked,phrase,text,usage,want,why", [
    ("max20", "santa-reviewer", None, None, "review", False, "opus", "role judge"),
    ("pro", "santa-reviewer", None, None, "review", False, "sonnet", "role judge"),
    ("max5", "santa-reviewer", None, None, "review", False, "sonnet", "role judge"),
    ("max5", "santa-reviewer", None, "use opus", "review", False, "opus", "phrase lift"),
    # the user's own phrase is not stepped down by the usage guard (REVIEW2 fix 5)
    ("max5", "santa-reviewer", None, "use opus", "review", True, "opus", "phrase lift"),
    ("api", "santa-reviewer", None, "use opus", "review", True, "opus", "phrase lift"),
    ("max5", "santa-reviewer", None, None, "review", True, "sonnet", "role judge"),
    ("pro", "santa-reviewer", None, "use opus", "review", True, "haiku", "usage-guard"),
    # final-fix 3: the user's phrase wins inside the ceiling on every tier and role, guard on or off
    ("max20", "santa-reviewer", None, "use opus", "review", True, "opus", "user said"),
    ("max20", "implementation-engineer", None, "use opus", "build it", True, "opus", "user said"),
    ("pro", "implementation-engineer", None, "use sonnet", "build it", True, "sonnet", "user said"),
    ("pro", "santa-reviewer", None, "use sonnet", "review", True, "sonnet", "user said"),
    ("pro", "implementation-engineer", None, "use opus", "build it", True, "haiku", "role impl -> haiku"),  # over the ceiling: no lift
    ("max20", "explore", None, "use haiku", "look", False, "haiku", "user said"),
    ("max5", "implementation-engineer", None, "use opus", "build it", True, "opus", "user said"),
    ("pro", "santa-reviewer", "opus", "use opus", "review", False, "sonnet", "over the pro ceiling"),
    ("pro", "implementation-engineer", None, None, "build it", False, "haiku", "role impl"),
    ("pro", "implementation-engineer", None, None, "Previous attempt failed", False, "sonnet", "escalated"),
    ("pro", "implementation-engineer", None, None, "Previous attempt failed", True, "haiku", "usage-guard"),
    ("max5", "implementation-engineer", None, None,
     "Add a column. Execute docs/superpowers/plans/plan-2026-10-29-x.md", False, "haiku", "planned small"),
    ("max5", "implementation-engineer", None, None, HEAVY, False, "sonnet", "escalated"),
    ("max20", "implementation-engineer", None, None, HEAVY, False, "opus", "escalated"),
    ("max20", "implementation-engineer", None, None, HEAVY, True, "sonnet", "usage-guard"),
    # 2026-10-31: max20 verify runs opus outright, no size bump left in any tier (see test_size_bump_*)
    ("max20", "qa-verifier", None, None, HEAVY, False, "opus", "role verify"),
    ("max20", "qa-verifier", None, None, "check it", False, "opus", "role verify"),
    ("max5", "qa-verifier", None, None, "check it", False, "haiku", "role verify"),
    ("max20", "general-purpose", "opus", None, "research", False, "opus", "explicit model param"),
    ("pro", "general-purpose", "opus", None, "research", False, "haiku", "explicit 'opus' ignored"),  # D6 ask_only
    ("max20", "general-purpose", "fable", None, "x", False, "sonnet", "ignored"),
    ("max20", "general-purpose", "fable", "use fable", "x", False, "fable", "user said"),
    ("max20", "general-purpose", "fable", "use fable", "x", True, "sonnet", "usage-guard"),
    ("max20", "unknown-agent", None, None, "x", False, "sonnet", "role default"),
    ("pro", "unknown-agent", None, None, "x", False, "haiku", "role default")])
def test_resolve_matrix(tier, agent, asked, phrase, text, usage, want, why):
    model, reason = mm.resolve(POL, agent, asked=asked,
                               phrase_for=(lambda m: phrase if phrase and m in phrase else None),
                               text=text, cwd=None, tier=tier, usage_active=usage, flags=[], pin=None)
    assert model == want and why in reason, (model, reason)


def test_size_bump_mechanism_lifts_a_role_at_its_size():
    # no shipped tier carries size_bumps since 2026-10-31; keep the resolver path covered with a copy
    pol = json.loads(json.dumps(POL))
    pol["tiers"]["max5"]["size_bumps"] = {"verify": {"L": "sonnet"}}
    kw = dict(asked=None, phrase_for=lambda m: None, cwd=None, tier="max5", usage_active=False, flags=[], pin=None)
    model, reason = mm.resolve(pol, "qa-verifier", text=HEAVY, **kw)
    assert model == "sonnet" and "size bump L -> sonnet" in reason, (model, reason)
    assert mm.resolve(pol, "qa-verifier", text="check it", **kw)[0] == "haiku"
    assert all(not blk["size_bumps"] for blk in POL["tiers"].values())


def test_resolve_flags_and_pins_then_cap():
    r = mm.resolve(POL, "explore", asked=None, phrase_for=lambda m: None, text="x", cwd=None, tier="pro",
                   usage_active=False, flags=["fable"], pin=None)
    assert r == ("sonnet", "fable-only-mode active; tier-cap: fable -> sonnet (pro)")
    r = mm.resolve(POL, "explore", asked=None, phrase_for=lambda m: None, text="x", cwd=None, tier="max20",
                   usage_active=True, flags=[], pin="opus")
    assert r[0] == "sonnet" and "per-project model mode" in r[1] and "usage-guard" in r[1]
    # the guard never raises a judge: a haiku pin stays haiku (REVIEW2 fix 1)
    r = mm.resolve(POL, "santa-reviewer", asked=None, phrase_for=lambda m: None, text="x", cwd=None,
                   tier="max20", usage_active=True, flags=[], pin="haiku")
    assert r[0] == "haiku", r


def test_resolve_fail_open_on_empty_policy():
    # literal tables: six judges -> judge, everyone else default
    assert mm.resolve({}, "santa-reviewer", asked=None, phrase_for=lambda m: None, text="x", cwd=None,
                      tier="max20", usage_active=False, flags=[], pin=None)[0] == "opus"
    assert mm.resolve({}, "santa-reviewer", asked=None, phrase_for=lambda m: None, text="x", cwd=None,
                      tier="pro", usage_active=False, flags=[], pin=None)[0] == "sonnet"
    assert mm.resolve({}, "explore", asked=None, phrase_for=lambda m: None, text="x", cwd=None,
                      tier="max20", usage_active=False, flags=[], pin=None)[0] == "sonnet"


# --- negated / questioned phrases are not requests (SANTA-FINAL fix 1) --------------------
def _one_row(tmp_path, text):
    t = tmp_path / "t.jsonl"
    t.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": text},
                             "timestamp": "2026-10-30T10:00:00Z"}) + "\n", encoding="utf-8")
    return t


SANTA_PROMPTS = ("why did you use opus for this? that burned my quota",
                 "don't use fable for this, it is a small fix")


@pytest.mark.parametrize("text,model,expected", [
    (SANTA_PROMPTS[0], "opus", None),
    (SANTA_PROMPTS[1], "fable", None),
    ("never use opus here", "opus", None),
    ("use opus for this", "opus", "use opus"),
    ("I was unsure. use fable", "fable", "use fable"),
    # SANTA-GATE 2: "want", "agent", "important" end in n+t but are not contractions
    ("I want you to use opus for this", "opus", "use opus"),
    ("this agent should use opus", "opus", "use opus"),
    ("important: use fable here", "fable", "use fable"),
    ("dont use opus for this", "opus", None),
    ("you can't use fable here", "fable", None)])
def test_user_phrase_skips_negation_and_questions(tmp_path, text, model, expected):
    assert mm.user_phrase(model, _one_row(tmp_path, text), POL["override_phrases"]) == expected


@pytest.mark.parametrize("tier", ["max5", "max20"])
@pytest.mark.parametrize("text", SANTA_PROMPTS)
def test_santa_prompts_keep_the_role_route(tmp_path, tier, text):
    t = _one_row(tmp_path, text)

    def said(m):
        return mm.user_phrase(m, t, POL["override_phrases"])

    for agent in ("explore", "general-purpose", "docs-sync-agent"):
        kw = dict(asked=None, text=text, cwd=None, tier=tier, usage_active=False, flags=[], pin=None)
        got = mm.resolve(POL, agent, phrase_for=said, **kw)[0]
        assert got == mm.resolve(POL, agent, phrase_for=lambda m: None, **kw)[0], (agent, got)
        # explore keeps its tier route (haiku on max5, sonnet on max20 since 2026-10-31)
        assert got != "fable" and (agent != "explore" or got == POL["tiers"][tier]["roles"]["explore"]), (agent, got)


def test_max5_use_fable_is_not_a_silent_opus():
    # SANTA-FINAL D4: on max5 an explicit fable + "use fable" is over the ceiling; Opus needs "use opus"
    kw = dict(asked="fable", text="x", cwd=None, tier="max5", usage_active=False, flags=[], pin=None)
    assert mm.resolve(POL, "general-purpose", phrase_for=lambda m: "use fable" if m == "fable" else None,
                      **kw)[0] == "sonnet"
    both = {"fable": "use fable", "opus": "use opus"}
    assert mm.resolve(POL, "general-purpose", phrase_for=both.get, **kw)[0] == "opus"


# --- scripts/model-mode.py (first CLI test, audit I-11) ------------------------------------
CLI = ROOT / "scripts" / "model-mode.py"


def _cli(args, cwd, env_extra=None):
    return subprocess.run([sys.executable, str(CLI), *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **(env_extra or {})})


def test_cli_pin_is_capped_with_a_reason(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    env = {"HOME": str(home), "USERPROFILE": str(home), "CLAUDE_CONFIG_DIR": str(home / ".claude")}
    repo = tmp_path / "repo"
    repo.mkdir()
    TF.set_tier("pro")
    cp = _cli(["opus"], repo, env)
    assert cp.returncode == 0 and "stored sonnet" in cp.stdout and "pro ceiling" in cp.stdout
    cp = _cli(["show"], repo, env)
    assert "this-repo pin       : sonnet" in cp.stdout and "plan tier           : pro" in cp.stdout
    assert "usage guard         : inactive" in cp.stdout
    cp = _cli(["haiku"], repo, env)
    assert cp.returncode == 0 and "-> haiku" in cp.stdout
    cp = _cli(["clear"], repo, env)
    assert "pin cleared" in cp.stdout
    assert _cli(["gpt"], repo, env).returncode == 2
