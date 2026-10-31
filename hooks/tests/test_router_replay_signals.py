"""scripts/router_replay.py judges: precision signals must not trust the router's own classifier,
and recall signals (A-09, workflow-audit 2026-10-31) flag the skills a prompt should have got.

The audit's 17:57 misroute pushed react-hooks-patterns onto a claude-infra prompt because the judge
asked the same classifier that had just made the mistake. Prompts here are paraphrased.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))


def _load():
    spec = importlib.util.spec_from_file_location("_router_replay_sig", _HOOKS.parent / "scripts" / "router_replay.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RR = _load()


def _ctx(*skills: str) -> str:
    return "\n".join(f"- **{s}** (SHOULD-READ) ACTION: Skill(\"{s}\")" for s in skills)


def _flags(prompt: str, cwd: str = "/nonexistent-dir", ctx: str = "") -> list[str]:
    return RR.flags_for(prompt, cwd, ctx, RR._fe_only_skills())


def test_fe_judge_does_not_trust_the_router_classifier(monkeypatch):
    from prompt_router import classify as C
    monkeypatch.setattr(C, "classify", lambda payload: C.TaskProfile(
        text="x", surfaces={"frontend", "ui"}, is_ui=True, intents={"IMPLEMENT": 1}))
    prompt = "we should save more thoroughly and be careful with every answer"
    assert "fe_skill_no_ui" in _flags(prompt, ctx=_ctx("react-hooks-patterns"))


def test_zero_skill_dev_flags_a_dev_prompt_with_no_skill():
    prompt = "fix the failing test in src/app.py, the retry logic throws"
    assert "zero_skill_dev" in _flags(prompt, ctx="")
    assert "zero_skill_dev" not in _flags(prompt, ctx=_ctx("debug-investigation"))
    assert "zero_skill_dev" not in _flags("thanks, that looks good", ctx="")


def test_audit_prompt_needs_an_audit_skill():
    prompt = "audit this repo for tech debt and list what to delete"
    assert "audit_no_audit_skill" in _flags(prompt, ctx=_ctx("backend-standards-always-follow"))
    assert "audit_no_audit_skill" not in _flags(prompt, ctx=_ctx("tech-debt-audit"))
    assert "audit_no_audit_skill" not in _flags(prompt, ctx=_ctx("ponytail:ponytail-audit"))


def test_infra_prompt_with_a_frontend_skill_is_flagged():
    prompt = "the skills and hooks do not trigger when i work on apis and infra"
    assert "infra_got_fe_skill" in _flags(prompt, ctx=_ctx("frontend-standards-always-follow"))
    assert "infra_got_fe_skill" not in _flags(prompt, ctx=_ctx("skill-linkage-story"))


@pytest.fixture
def fastify_repo(tmp_path):
    root = tmp_path / "svc"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "package.json").write_text(json.dumps(
        {"dependencies": {"fastify": "4.28.0", "mongoose": "8.5.0"}, "devDependencies": {"vitest": "2.0.0"}}),
        encoding="utf-8")
    return root


def test_stack_skill_missed_reads_repo_deps(fastify_repo):
    prompt = "add an endpoint that returns invoices sorted by date with an index on the date field"
    cwd = str(fastify_repo)
    assert "stack_skill_missed" in _flags(prompt, cwd, _ctx("backend-standards-always-follow"))
    assert "stack_skill_missed" not in _flags(prompt, cwd, _ctx("mongoose-patterns", "fastify-patterns"))
    # a frontend-only prompt in the same repo owes the backend stack skills nothing
    assert "stack_skill_missed" not in _flags("restyle the login button colour", cwd, "")


def test_report_carries_recall_and_zero_skill_numbers():
    counts, _ = RR.replay([{"prompt": "fix the failing test in src/app.py, the retry logic throws",
                            "cwd": "/nonexistent-dir", "ref": "p/s.jsonl:1"}])
    assert {"zero_skill_prompts", "distinct_skills", "dev_prompts", "zero_skill_dev"} <= set(counts)
    rates = RR.rates(counts)
    assert "zero_skill_dev" in rates and "zero_skill_prompts" in rates


def test_machine_markers_are_judged_independently():
    assert "[Subagent hand-back]" in " ".join(RR._MACHINE)
    assert "<agent-message from=" in " ".join(RR._MACHINE)
