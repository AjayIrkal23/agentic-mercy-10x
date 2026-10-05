#!/usr/bin/env python3
"""Track semgrep execution for security completion gate.

post-tool-use (Shell): set semgrep_ran only after `semgrep scan|ci` completes
successfully.
post-tool-use (mcp__semgrep__*): any semgrep MCP tool call sets semgrep_ran (+ a
findings count when the result is parseable) — the security-sentinel agent scans
through the MCP, which the Bash-only match never credited (A03-B8).
Legacy pre-tool-use mode kept for backward compatibility but does not set semgrep_ran.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.platform import locked_update  # noqa: E402
from tool_compat import is_shell_tool, tool_name  # noqa: E402

STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or Path(__file__).resolve().parent / ".state")
SEMGREP_RE = re.compile(r"\bsemgrep\s+(scan|ci)\b", re.I)
FAKE_RE = re.compile(r"^\s*(echo|which|type)\s+.*semgrep", re.I)


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _update_state(cid: str, fn) -> None:
    """security-scan-gate writes the same file: locked RMW (audit J-01)."""
    def apply(state: dict) -> dict:
        state.setdefault("security_files", [])
        state.setdefault("reminded", False)
        fn(state)
        return state
    locked_update(STATE_DIR / f"{_safe_cid(cid)}.security-scan.json", apply)


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


def _mcp_findings(payload: dict) -> int:
    """Best-effort count of semgrep MCP findings from the tool result (0 if unknown)."""
    tr = payload.get("tool_response") or payload.get("tool_result") or payload.get("result")
    try:
        if isinstance(tr, str):
            tr = json.loads(tr)
        if isinstance(tr, list):  # MCP content blocks
            for block in tr:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    try:
                        tr = json.loads(block["text"])
                        break
                    except Exception:
                        continue
        if isinstance(tr, dict):
            res = tr.get("results")
            if isinstance(res, list):
                return len(res)
            for k in ("findings", "findings_count", "count"):
                v = tr.get(k)
                if isinstance(v, list):
                    return len(v)
                if isinstance(v, int):
                    return v
    except Exception:
        pass
    return 0


def post_tool_use(payload: dict) -> int:
    name = str(tool_name(payload) or "")
    if name.startswith("mcp__semgrep__"):
        cid = payload.get("conversation_id") or payload.get("session_id") or ""
        if not cid:
            return 0
        found = _mcp_findings(payload)

        def mark_mcp(state: dict) -> None:
            state["semgrep_ran"] = True
            state["semgrep_command"] = name
            state["semgrep_findings"] = max(int(state.get("semgrep_findings") or 0), found)
        _update_state(cid, mark_mcp)
        return 0
    if not is_shell_tool(name):
        return 0
    command = _command_from(payload)
    if not SEMGREP_RE.search(command) or FAKE_RE.search(command):
        return 0
    if not _shell_succeeded(payload):
        return 0
    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        return 0
    def mark_cli(state: dict) -> None:
        state["semgrep_ran"] = True
        state["semgrep_command"] = command[:500]
        state.setdefault("semgrep_findings", 0)
    _update_state(cid, mark_cli)
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
