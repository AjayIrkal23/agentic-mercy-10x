#!/usr/bin/env python3
"""tool-failure-hint.py — PostToolUseFailure advisory.

Turns the two most-misdiagnosed tool failures into a one-line hint
(rules/claude-infra.md, "Misdiagnosis order"):
  Edit/Write whose error mentions "has not been read" or "Read deny"
      -> Read the exact file, then retry immediately.
  Bash whose error contains "path escapes project root"
      -> lean-ctx PathJail intercepted it; re-run as plain Bash.
Anything else -> {}. Fail-open.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tool_compat import is_shell_tool  # noqa: E402


def hint(tool: str, error: str) -> str:
    err = (error or "").lower()
    if tool in ("Edit", "Write") and ("has not been read" in err or "read deny" in err):
        return ("Edit/Write failed because the file was not read first: Read the exact "
                "file, then retry the edit immediately (no other call in between). Do not shell out.")
    if is_shell_tool(tool) and "path escapes project root" in err:
        return "lean-ctx PathJail intercepted this command; re-run it as plain Bash (not ctx_shell)."
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        error = payload.get("error")
        if not isinstance(error, str):
            error = json.dumps(error, ensure_ascii=False) if error is not None else ""
        text = hint(str(payload.get("tool_name") or ""), error)
        if text:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUseFailure",
                "additionalContext": text,
            }}))
            return 0
    except Exception:  # noqa: BLE001
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
