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


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "STATE_FILE", tmp_path / "state" / "pipeline-evidence.json")
    run = tmp_path / "proj" / ".claude" / "runs" / "20261103T1200-x"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"expected_artifacts": {"qa-verifier": "VERIFY-REPORT.md"}}),
                                  encoding="utf-8")
    return tmp_path / "proj", run


def _payload(cwd: Path, **kw) -> dict:
    return {"agent_type": "qa-verifier", "agent_id": "a1", "cwd": str(cwd), "stop_hook_active": False, **kw}


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
    assert gate.decide(_payload(tmp_path)) == {}


def test_dispatch_returns_the_top_level_block(repo):
    cwd, _ = repo
    env = {**os.environ, "CLAUDE_HOOK_DOCTOR": "1"}
    cp = subprocess.run([sys.executable, str(HOOKS / "dispatch.py"), "subagent-stop"],
                        input=json.dumps(_payload(cwd, agent_id="dispatch-1")), capture_output=True,
                        text=True, env=env, timeout=30, check=False)
    out = json.loads(cp.stdout.strip().splitlines()[-1])
    assert out.get("decision") == "block" and "qa-verifier" in out.get("reason", "")
    assert "hookSpecificOutput" not in out
