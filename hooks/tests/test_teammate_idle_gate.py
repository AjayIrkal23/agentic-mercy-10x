"""teammate-idle-gate finds artifacts written in the run folder (audit 2026-10-05 E-02).

team-lead's run.json names artifacts relative to the run folder
(`IMPL-REPORT-BE.md`); /invoke's names them relative to the repo
(`.claude/runs/<ts>/IMPL-REPORT-BE.md`). The gate only tried the repo, so it
blocked teammates whose artifact existed.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]


def _gate():
    spec = importlib.util.spec_from_file_location("tig", HOOKS / "teammate-idle-gate.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _run(tmp_path, art: str) -> Path:
    run = tmp_path / ".claude" / "runs" / "20261005-x"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"expected_artifacts": {"impl-be": art}}), encoding="utf-8")
    return run


def test_artifact_relative_to_run_folder_counts(tmp_path):
    run = _run(tmp_path, "IMPL-REPORT-BE.md")
    (run / "IMPL-REPORT-BE.md").write_text("x", encoding="utf-8")
    assert _gate().missing_artifact({"teammate_name": "impl-be", "cwd": str(tmp_path)}) is None


def test_artifact_relative_to_repo_counts(tmp_path):
    run = _run(tmp_path, ".claude/runs/20261005-x/IMPL-REPORT-BE.md")
    (run / "IMPL-REPORT-BE.md").write_text("x", encoding="utf-8")
    assert _gate().missing_artifact({"teammate_name": "impl-be", "cwd": str(tmp_path)}) is None


def test_missing_artifact_still_blocks(tmp_path):
    _run(tmp_path, "IMPL-REPORT-BE.md")
    hit = _gate().missing_artifact({"teammate_name": "impl-be", "cwd": str(tmp_path)})
    assert hit and hit[1] == "IMPL-REPORT-BE.md"
