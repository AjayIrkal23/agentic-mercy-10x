#!/usr/bin/env python3
"""Track semgrep execution for security completion gate.

post-tool-use (Shell): set semgrep_ran only after command completes successfully.
Legacy pre-tool-use mode kept for backward compatibility but does not set semgrep_ran.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from tool_compat import is_shell_tool, tool_name

STATE_DIR = Path(__file__).resolve().parent / ".state"
SEMGREP_RE = re.compile(r"\bsemgrep\s+(scan|ci)\b", re.I)
FAKE_RE = re.compile(r"^\s*(echo|which|type)\s+.*semgrep", re.I)


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _load_state(cid: str) -> dict:
    p = STATE_DIR / f"{_safe_cid(cid)}.security-scan.json"
    if not p.is_file():
        return {"security_files": [], "reminded": False}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"security_files": [], "reminded": False}


def _save_state(cid: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = STATE_DIR / f"{_safe_cid(cid)}.security-scan.json"
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _command_from(payload: dict) -> str:
    ti = payload.get("tool_input") or {}
    return str(ti.get("command") or "")


def _shell_succeeded(payload: dict) -> bool:
    tr = payload.get("tool_result") or payload.get("result") or {}
    if isinstance(tr, dict):
        if tr.get("is_error") is True or tr.get("success") is False:
            return False
        ec = tr.get("exit_code")
        if ec is not None:
            try:
                return int(ec) == 0
            except (TypeError, ValueError):
                pass
        stderr = str(tr.get("stderr") or "")
        if "error" in stderr.lower() and "semgrep" in stderr.lower():
            return False
    output = str(payload.get("tool_output") or payload.get("output") or "")
    if "exit code: 0" in output.lower() or "exit_code=0" in output:
        return True
    if "exit code:" in output.lower() and "exit code: 0" not in output.lower():
        return False
    return True


def post_tool_use(payload: dict) -> int:
    if not is_shell_tool(tool_name(payload)):
        return 0
    command = _command_from(payload)
    if not SEMGREP_RE.search(command) or FAKE_RE.search(command):
        return 0
    if not _shell_succeeded(payload):
        return 0
    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        return 0
    state = _load_state(cid)
    state["semgrep_ran"] = True
    state["semgrep_command"] = command[:500]
    if "semgrep_findings" not in state:
        state["semgrep_findings"] = 0
    _save_state(cid, state)
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0

    mode = sys.argv[1] if len(sys.argv) > 1 else "post-tool-use"
    if mode == "post-tool-use":
        post_tool_use(payload)
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
