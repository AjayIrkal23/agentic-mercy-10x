"""B-08 tracker half: every semgrep scan records `scanned_at` per target path, so Gate 3
can demand a scan NEWER than each security file's last edit (one early scan no longer
covers an auth file edited hours later)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]


def _load(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("sst_files", HOOKS / "security-semgrep-tracker.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)
    return mod


def _state(tmp_path) -> dict:
    return json.loads((tmp_path / "s.security-scan.json").read_text(encoding="utf-8"))


def test_mcp_scan_records_each_file(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch)
    mod.post_tool_use({"session_id": "s", "agent_id": "a1", "tool_name": "mcp__semgrep__semgrep_scan", "cwd": "/r",
                       "tool_input": {"code_files": [{"path": "/r/src/auth.ts"}, "src/login.ts"]}})
    st = _state(tmp_path)  # plain session id: the parent's Stop gate sees subagent scans
    assert st["semgrep_ran"] is True
    assert set(st["scanned_at"]) == {"/r/src/auth.ts", "/r/src/login.ts"}
    assert all(isinstance(v, float) for v in st["scanned_at"].values())


def test_cli_scan_records_targets_not_option_values(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch)
    mod.post_tool_use({"session_id": "s", "tool_name": "Bash", "cwd": "/r",
                       "tool_input": {"command": "semgrep scan --config p/owasp-top-ten --json src/auth.ts lib"},
                       "tool_result": {"exit_code": 0}})
    assert set(_state(tmp_path)["scanned_at"]) == {"/r/src/auth.ts", "/r/lib"}
