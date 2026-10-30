"""instructions-loaded-log.py (InstructionsLoaded exec, async): one row per loaded
instruction file into hooks/.telemetry/<YYYY-MM-DD>.instructions-loaded.jsonl
(scripts/measure_context_cost.py --observed sums `chars` per `source`)."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
SCRIPT = _HOOKS / "instructions-loaded-log.py"
FIXTURE = _HOOKS / "tests" / "fixtures" / "instructions-loaded.json"
KEYS = {"ts", "sid", "path", "chars", "source", "load_reason"}


@pytest.fixture
def ill(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("ill_t", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    (tmp_path / "home" / ".claude").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "home" / ".claude"))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    return m


def _rows() -> list:
    p = Path(os.environ["CLAUDE_HOOK_TELEMETRY_DIR"]) / f"{time.strftime('%Y-%m-%d')}.instructions-loaded.jsonl"
    if not p.is_file():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _call(m, monkeypatch, payload) -> tuple:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = m.main()
    return rc, buf.getvalue()


def test_row_shape_and_source_mapping(ill, monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CLAUDE.md").write_text("c" * 1234, encoding="utf-8")
    rules = tmp_path / "home" / ".claude" / "rules"
    rules.mkdir()
    (rules / "00-x.md").write_text("rule", encoding="utf-8")
    for mt in ("User", "Project", "Local", "Managed"):
        _call(ill, monkeypatch, {"session_id": "s1", "file_path": str(repo / "CLAUDE.md"),
                                 "memory_type": mt, "load_reason": "session_start"})
    _call(ill, monkeypatch, {"session_id": "s1", "file_path": str(rules / "00-x.md"),
                             "memory_type": "User", "load_reason": "path_glob_match"})
    rows = _rows()
    assert len(rows) == 5 and all(set(r) == KEYS for r in rows)
    assert [r["source"] for r in rows] == ["user", "project", "local", "managed", "rules"]
    assert all(r["chars"] == 1234 for r in rows[:4]) and rows[4]["chars"] == 4
    assert all(r["sid"] == "s1" for r in rows) and rows[4]["load_reason"] == "path_glob_match"


def test_no_stdout_and_exit_zero(ill, monkeypatch, tmp_path):
    rc, out = _call(ill, monkeypatch, {"session_id": "s1", "file_path": str(tmp_path / "x.md"),
                                       "memory_type": "Project"})
    assert rc == 0 and out == ""


def test_bad_payload_missing_file_and_doctor(ill, monkeypatch, tmp_path):
    assert _call(ill, monkeypatch, "nope") == (0, "")
    assert _rows() == []
    assert _call(ill, monkeypatch, {"session_id": "s1", "memory_type": "Project"}) == (0, "")
    assert _rows() == []
    _call(ill, monkeypatch, {"session_id": "s1", "file_path": str(tmp_path / "missing.md")})
    rows = _rows()
    assert len(rows) == 1 and rows[0]["chars"] == 0 and rows[0]["source"] == "unknown"
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    _call(ill, monkeypatch, {"session_id": "s1", "file_path": str(tmp_path / "missing.md")})
    assert len(_rows()) == 1


def test_fixture_runs_through_the_cli(ill, tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_HOOK_DOCTOR"}
    env["CLAUDE_HOOK_TELEMETRY_DIR"] = str(tmp_path / "tel")
    cp = subprocess.run([sys.executable, str(SCRIPT)], input=FIXTURE.read_text(encoding="utf-8"),
                        capture_output=True, text=True, timeout=30, env=env, check=False)
    assert cp.returncode == 0 and cp.stdout == ""
    rows = _rows()
    assert len(rows) == 1 and rows[0]["sid"] == "doctor-fixture" and rows[0]["source"] == "project"


def test_rows_append_across_calls_and_the_name_rotates_daily(ill, monkeypatch, tmp_path):
    for _ in range(2):
        _call(ill, monkeypatch, {"session_id": "s1", "file_path": str(tmp_path / "a.md")})
    assert len(_rows()) == 2
    assert ill._row_path(datetime(2026, 1, 2)).name == "2026-01-02.instructions-loaded.jsonl"
