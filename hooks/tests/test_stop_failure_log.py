"""stop-failure-log.py (StopFailure exec): telemetry row per API-error stop, and
state/<sid>.stop-failure.json only for rate_limit (restore_sessions --resume-after-limit
relaunches every such file without checking the reason)."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402


@pytest.fixture
def sfl(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("sfl_t", _HOOKS / "stop-failure-log.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    return m


def _run(m, monkeypatch, payload) -> tuple:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = m.main()
    return rc, buf.getvalue().strip()


def _rows() -> list:
    p = plat.telemetry_dir() / f"hook-fires-{time.strftime('%Y%m%d')}.jsonl"
    if not p.is_file():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _state_files(tmp_path) -> list:
    d = tmp_path / "state"
    return sorted(d.glob("*.stop-failure.json")) if d.is_dir() else []


def test_rate_limit_writes_the_state_file_and_a_telemetry_row(sfl, monkeypatch, tmp_path):
    details = "5-hour limit reached ∙ resets 3pm " + "x" * 400
    rc, out = _run(sfl, monkeypatch, {"session_id": "s1", "cwd": "/w", "transcript_path": "/w/t.jsonl",
                                      "error": "rate_limit", "error_details": details,
                                      "last_assistant_message": "SECRET-ASSISTANT-TEXT"})
    assert rc == 0 and out == "{}"
    st = json.loads((tmp_path / "state" / "s1.stop-failure.json").read_text(encoding="utf-8"))
    assert set(st) == {"sid", "reason", "details", "ts", "cwd", "transcript"}
    assert st["sid"] == "s1" and st["reason"] == "rate_limit" and st["details"] == details[:300]
    assert isinstance(st["ts"], float) and st["cwd"] == "/w" and st["transcript"] == "/w/t.jsonl"
    rows = _rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "StopFailure" and row["link_id"] == "stop-failure-log"
    assert row["error"] == "rate_limit" and row["session"] == "s1"
    assert "SECRET-ASSISTANT-TEXT" not in json.dumps(rows)


@pytest.mark.parametrize("err", ["overloaded", "server_error", "max_output_tokens", "unknown", None])
def test_other_errors_log_but_leave_no_state_file(sfl, monkeypatch, tmp_path, err):
    payload = {"session_id": "s2"}
    if err is not None:
        payload["error"] = err
    rc, out = _run(sfl, monkeypatch, payload)
    assert rc == 0 and out == "{}"
    assert len(_rows()) == 1 and _rows()[0]["error"] == (err or "unknown")
    assert _state_files(tmp_path) == []


def test_bad_payload_and_doctor_are_silent(sfl, monkeypatch, tmp_path):
    assert _run(sfl, monkeypatch, "x") == (0, "{}")
    assert _rows() == [] and _state_files(tmp_path) == []
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    assert _run(sfl, monkeypatch, {"session_id": "s1", "error": "rate_limit"}) == (0, "{}")
    assert _rows() == [] and _state_files(tmp_path) == []


def test_sid_is_sanitised_in_the_filename(sfl, monkeypatch, tmp_path):
    _run(sfl, monkeypatch, {"session_id": "../evil/..x", "error": "rate_limit"})
    files = _state_files(tmp_path)
    assert len(files) == 1
    assert files[0].parent == tmp_path / "state"
    stem = files[0].name[: -len(".stop-failure.json")]
    assert all(c.isalnum() or c in "._-" for c in stem)
    assert "/" not in stem and stem == ".._evil_..x"
