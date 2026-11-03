"""pipeline-evidence-gate (SubagentStop, 2026-11-03): an /invoke act agent proves it ran its pipeline."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("pipeline_evidence_gate_u", HOOKS / "pipeline-evidence-gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)  # type: ignore[union-attr]


RUN = "20261103T1200-x"
PROMPT = f"Verify the change. Run folder: /p/.claude/runs/{RUN}/ . Write your artifact to /p/.claude/runs/{RUN}/VERIFY-REPORT.md"
TRANSCRIPTS: dict[str, Path] = {}


def _transcript(tmp: Path, prompt: str, name: str = "agent.jsonl") -> str:
    p = tmp / name
    rows = [{"type": "system", "message": {"role": "system", "content": "x"}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": "done"}}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return str(p)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "STATE_FILE", tmp_path / "state" / "pipeline-evidence.json")
    run = tmp_path / "proj" / ".claude" / "runs" / RUN
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"expected_artifacts": {"qa-verifier": "VERIFY-REPORT.md"}}),
                                  encoding="utf-8")
    TRANSCRIPTS["default"] = Path(_transcript(tmp_path, PROMPT))
    return tmp_path / "proj", run


def _payload(cwd: Path, **kw) -> dict:
    return {"agent_type": "qa-verifier", "agent_id": "a1", "cwd": str(cwd), "stop_hook_active": False,
            "agent_transcript_path": str(TRANSCRIPTS["default"]), **kw}


def test_missing_artifact_blocks_once(repo):
    cwd, _ = repo
    out = gate.decide(_payload(cwd))
    assert out["decision"] == "block" and "does not exist yet" in out["reason"] and "## Pipeline" in out["reason"]
    assert gate.decide(_payload(cwd)) == {}          # one block per (run.json, agent_id)


def test_artifact_without_pipeline_blocks(repo):
    cwd, run = repo
    (run / "VERIFY-REPORT.md").write_text("# Verify\n\nPASS\n", encoding="utf-8")
    out = gate.decide(_payload(cwd))
    assert out["decision"] == "block" and "has no ## Pipeline section" in out["reason"]


def test_artifact_with_pipeline_passes(repo):
    cwd, run = repo
    (run / "VERIFY-REPORT.md").write_text("# Verify\n\n## Pipeline\n- P1 `npm test` -> 12 passed\n",
                                          encoding="utf-8")
    assert gate.decide(_payload(cwd)) == {}


def test_subdirectory_cwd_finds_the_run(repo):
    cwd, _ = repo
    sub = cwd / "src" / "app"
    sub.mkdir(parents=True)
    assert gate.decide(_payload(sub)).get("decision") == "block"


@pytest.mark.parametrize("extra", [{"stop_hook_active": True}, {"agent_type": "Explore"},
                                   {"agent_type": "general-purpose"}])
def test_second_round_and_non_act_agents_pass(repo, extra):
    cwd, _ = repo
    assert gate.decide(_payload(cwd, **extra)) == {}


def test_agent_not_in_the_run_passes(repo):
    cwd, _ = repo
    assert gate.decide(_payload(cwd, agent_type="santa-reviewer")) == {}


def test_stale_run_passes(repo):
    cwd, run = repo
    old = time.time() - gate.MAX_AGE_S - 60
    os.utime(run / "run.json", (old, old))
    assert gate.decide(_payload(cwd)) == {}


def test_no_runs_dir_passes(tmp_path):
    TRANSCRIPTS["default"] = Path(_transcript(tmp_path, PROMPT))
    assert gate.decide(_payload(tmp_path)) == {}


def test_an_agent_of_another_run_or_no_run_passes(repo, tmp_path):
    cwd, _ = repo
    other = _transcript(tmp_path, "Verify. Run folder: /p/.claude/runs/20261103T0900-older/ VERIFY-REPORT.md", "o.jsonl")
    assert gate.decide(_payload(cwd, agent_transcript_path=other)) == {}
    plain = _transcript(tmp_path, "Check that the build passes.", "plain.jsonl")
    assert gate.decide(_payload(cwd, agent_transcript_path=plain)) == {}


def test_workflow_helpers_that_write_notes_pass(repo, tmp_path):
    """review.js starts chunk reviewers and verifiers of the act's type that must not write the report."""
    cwd, run = repo
    (run / "run.json").write_text(json.dumps({"expected_artifacts": {"santa-reviewer": "SANTA-REVIEW.md"}}),
                                  encoding="utf-8")
    helper = _transcript(tmp_path, f"BREAKER for chunk 2. Run folder: /p/.claude/runs/{RUN}/ — write "
                                   f"notes/santa-2-a.md; never write SANTA-REVIEW.md yourself.", "h.jsonl")
    assert gate.decide(_payload(cwd, agent_type="santa-reviewer", agent_transcript_path=helper)) == {}


def test_the_dispatched_agent_of_two_live_runs_is_judged_by_its_own(repo, tmp_path):
    cwd, run = repo
    newer = run.parent / "20261103T1300-y"
    newer.mkdir()
    (newer / "run.json").write_text(json.dumps({"expected_artifacts": {"qa-verifier": "VERIFY-REPORT.md"}}),
                                    encoding="utf-8")
    (newer / "VERIFY-REPORT.md").write_text("## Pipeline\n- P1 ok\n", encoding="utf-8")
    out = gate.decide(_payload(cwd))                  # prompt names the older run, whose report is missing
    assert out.get("decision") == "block" and RUN in out["reason"]


def test_unreadable_transcript_fails_open(repo):
    cwd, _ = repo
    assert gate.decide(_payload(cwd, agent_transcript_path="/nonexistent/t.jsonl")) == {}


def test_dispatch_returns_the_top_level_block(repo):
    cwd, _ = repo
    env = {**os.environ, "CLAUDE_HOOK_DOCTOR": "1"}
    cp = subprocess.run([sys.executable, str(HOOKS / "dispatch.py"), "subagent-stop"],
                        input=json.dumps(_payload(cwd, agent_id="dispatch-1")), capture_output=True,
                        text=True, env=env, timeout=30, check=False)
    out = json.loads(cp.stdout.strip().splitlines()[-1])
    assert out.get("decision") == "block" and "qa-verifier" in out.get("reason", "")
    assert "hookSpecificOutput" not in out
