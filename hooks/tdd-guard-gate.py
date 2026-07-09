#!/usr/bin/env python3
"""tdd-guard-gate.py — run tdd-guard in WARN mode, scoped to the project.

Invoked by tdd-guard-launcher.sh (only for active projects). Reads the hook
payload on stdin and:

  1. SCOPE — if the edited file is OUTSIDE the active project root, allow it
     silently (tdd-guard governs the project's own code, not ~/.claude infra,
     dotfiles, or other repos opened in the same session).
  2. RUN — forward the payload to the real `tdd-guard` binary.
  3. WARN, don't pause — if tdd-guard returns a BLOCK/deny, downgrade it to a
     non-blocking PreToolUse advisory (the agent sees the TDD feedback and
     proceeds). Allow/passthrough output is forwarded unchanged.

Never blocks. Fails OPEN (any error -> allow). exit 0 always.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

FILE_TOOLS = {"Write", "Edit", "MultiEdit"}


def _within(path: str, root: str) -> bool:
    try:
        p = Path(path).resolve()
        r = Path(root).resolve()
        return r == p or r in p.parents
    except Exception:
        return True  # uncertain -> don't skip on scope grounds


def _extract_file_path(tool_input: dict) -> str:
    for k in ("file_path", "path", "filePath", "notebook_path"):
        v = tool_input.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def _is_block(stdout: str, rc: int) -> tuple[bool, str]:
    """Detect a tdd-guard block and extract its reason."""
    reason = ""
    try:
        obj = json.loads(stdout) if stdout.strip() else {}
    except Exception:
        obj = {}
    if isinstance(obj, dict):
        # Newer Claude Code shape
        hso = obj.get("hookSpecificOutput")
        if isinstance(hso, dict):
            if str(hso.get("permissionDecision", "")).lower() == "deny":
                return True, str(hso.get("permissionDecisionReason") or "")
        # Common shapes
        if str(obj.get("permissionDecision", "")).lower() == "deny":
            return True, str(obj.get("permissionDecisionReason") or obj.get("reason") or "")
        if str(obj.get("decision", "")).lower() in ("block", "deny"):
            return True, str(obj.get("reason") or obj.get("message") or "")
        reason = str(obj.get("reason") or obj.get("message") or "")
    # Exit code 2 is the Claude Code "block" convention.
    if rc == 2:
        return True, reason or stdout.strip()
    return False, reason


def _advisory(reason: str) -> str:
    reason = (reason or "TDD violation").strip()
    if len(reason) > 700:
        reason = reason[:700] + "…"
    msg = (
        "⚠️ TDD GUARD (advisory — not blocking): " + reason +
        "\nPreferred path: write the failing test first (golang-testing / "
        "test-driven-development skill), `make tdd`, then implement. Proceeding as requested."
    )
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": msg,
        }
    })


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}

    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    tool = payload.get("tool_name") or payload.get("tool") or ""
    tool_input = payload.get("tool_input") or payload.get("input") or {}

    # 1. Scope: external files (outside the active project) -> allow silently.
    if tool in FILE_TOOLS and isinstance(tool_input, dict):
        fpath = _extract_file_path(tool_input)
        if fpath and not _within(fpath, root):
            return 0  # exit 0, no output = allow

    # 2. Run tdd-guard.
    try:
        proc = subprocess.run(
            ["tdd-guard"], input=raw, capture_output=True, text=True, timeout=55
        )
        out, rc = proc.stdout, proc.returncode
    except Exception:
        return 0  # fail open

    # 3. Warn, don't pause.
    blocked, reason = _is_block(out, rc)
    if blocked:
        sys.stdout.write(_advisory(reason))
    elif out.strip():
        sys.stdout.write(out)  # passthrough allow / state-capture output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
