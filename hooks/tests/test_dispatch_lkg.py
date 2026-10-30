"""FIX2 item 2 (REVERIFY R3): a missing or corrupt hooks/dispatch.config.json used to switch every gate off
(`print("{}")`). The dispatcher now keeps a last-known-good copy in the state dir whenever the live file
parses, falls back to it, and fails open only when neither parses: then it says so on stderr, in a
systemMessage and in a telemetry row."""
from __future__ import annotations

import glob
import importlib.util
import io
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]


def _deny_cfg(tmp_path: Path) -> str:
    gate = tmp_path / "deny_gate.py"
    gate.write_text("import json, sys\njson.load(sys.stdin)\nprint(json.dumps({'hookSpecificOutput': {"
                    "'hookEventName': 'PreToolUse', 'permissionDecision': 'deny', "
                    "'permissionDecisionReason': 'LKG-GATE'}}))\n", encoding="utf-8")
    return json.dumps({"chains": {"pre-tool-use": [
        {"id": "lkg-gate", "type": "gate", "tools": "Bash", "cmd": [sys.executable, str(gate)]}]}})


@pytest.fixture()
def dp(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(f"dispatch_lkg_{uuid.uuid4().hex}", HOOKS / "dispatch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    state = tmp_path / "state"
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(state))
    monkeypatch.setattr(mod, "CONFIG", tmp_path / "dispatch.config.json")
    mod.lkg = state / "dispatch.config.lkg.json"
    return mod


def _main(mod, monkeypatch, event: str = "pre-tool-use") -> tuple[dict, str]:
    payload = {"session_id": f"lkg-{uuid.uuid4().hex}", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    assert mod.main([event]) == 0
    return json.loads(out.getvalue() or "{}"), err.getvalue()


def _decision(out: dict) -> str | None:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision")


def _rows(decision: str) -> list:
    rows = []
    for f in glob.glob(os.path.join(os.environ["CLAUDE_HOOK_TELEMETRY_DIR"], "hook-fires-*.jsonl")):
        rows += [r for r in map(json.loads, Path(f).read_text(encoding="utf-8").splitlines())
                 if r.get("decision") == decision]
    return rows


def test_a_good_config_refreshes_the_last_known_good_copy(dp, monkeypatch, tmp_path):
    dp.CONFIG.write_text(_deny_cfg(tmp_path), encoding="utf-8")
    out, _ = _main(dp, monkeypatch)
    assert _decision(out) == "deny"
    assert dp.lkg.read_text(encoding="utf-8") == dp.CONFIG.read_text(encoding="utf-8")
    first = dp.lkg.stat().st_mtime_ns
    _main(dp, monkeypatch)
    assert dp.lkg.stat().st_mtime_ns == first  # unchanged config: no rewrite per hook call


@pytest.mark.parametrize("broken", [None, "{oops", "[1, 2]", '{"chains": []}'])
def test_missing_or_corrupt_config_runs_the_last_known_good_copy(dp, monkeypatch, tmp_path, broken):
    dp.CONFIG.write_text(_deny_cfg(tmp_path), encoding="utf-8")
    _main(dp, monkeypatch)
    if broken is None:
        dp.CONFIG.unlink()
    else:
        dp.CONFIG.write_text(broken, encoding="utf-8")
    out, err = _main(dp, monkeypatch)
    assert _decision(out) == "deny", out  # the gate still runs
    assert "last-known-good" in err
    assert _rows("config-lkg")
    assert json.loads(dp.lkg.read_text(encoding="utf-8"))["chains"]["pre-tool-use"]  # never overwritten by junk


def test_the_fallback_is_shown_to_the_user_once_per_prompt(dp, monkeypatch, tmp_path):
    dp.CONFIG.write_text(_deny_cfg(tmp_path), encoding="utf-8")
    _main(dp, monkeypatch)
    dp.CONFIG.unlink()
    out, _ = _main(dp, monkeypatch, "user-prompt-submit")
    assert "last-known-good" in out.get("systemMessage", "")


@pytest.mark.parametrize("lkg_text", [None, "{oops"])
def test_neither_parses_fails_open_loudly(dp, monkeypatch, lkg_text):
    if lkg_text is not None:
        dp.lkg.parent.mkdir(parents=True, exist_ok=True)
        dp.lkg.write_text(lkg_text, encoding="utf-8")
    out, err = _main(dp, monkeypatch)
    assert _decision(out) is None                      # fail open, as before
    assert "OFF" in out["systemMessage"] and "OFF" in err
    assert _rows("config-fail-open")
