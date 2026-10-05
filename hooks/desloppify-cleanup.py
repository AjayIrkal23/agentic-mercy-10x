#!/usr/bin/env python3
"""De-Sloppify: PostToolUse hook on Write/Edit — triggers cleanup pass reminder.

After a threshold of code writes in a conversation, injects a one-time reminder
to run a dedicated cleanup pass SEPARATE from implementation.

The key insight: telling an implementation agent "don't be sloppy" makes it
over-cautious. Instead, let it focus on correctness, then run a separate
cleanup pass focused purely on:
- Dead imports
- Inconsistent naming within the file
- Redundant nil/undefined checks
- Formatting drift from project standards
- Unnecessary type assertions
- Console.log / fmt.Println left behind

Fires once per conversation after N code writes.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from tool_compat import is_write_tool, tool_name

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or SCRIPT_DIR / ".state")

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from lib.platform import locked_update  # noqa: E402
try:
    from lib.code_files import is_code_file as _is_code_file  # noqa: E402
except Exception:  # pragma: no cover - fail-open (count nothing)
    def _is_code_file(path):  # type: ignore
        return False

# After this many code writes, trigger the one-time wrap-up reminder (Phase 4b).
# The Stop gates read `code_files` (unique paths), NOT this counter.
WRITES_THRESHOLD = 8


def _record_write(cid: str, file_path: str) -> tuple[int, bool]:
    """Count the write and remember the unique path under the file lock (parallel
    PostToolUse runs lost updates, audit J-01). Returns (writes, fire_now)."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    result = {"writes": 0, "fire": False}

    def update(state: dict) -> dict:
        # Always record — even after the reminder fired — so the completion gate's
        # thresholds (santa/dead-code) see the UNIQUE code files touched this session.
        state["code_writes"] = int(state.get("code_writes") or 0) + 1
        files = state.get("code_files") or state.get("code_paths") or []
        norm = file_path.replace("\\", "/")
        if norm not in files:
            files.append(norm)
        state["code_files"] = files[-500:]
        state.pop("code_paths", None)  # legacy key (renamed 2026-09-27)
        result["writes"] = state["code_writes"]
        result["fire"] = not state.get("fired") and state["code_writes"] >= WRITES_THRESHOLD
        state["fired"] = bool(state.get("fired")) or result["fire"]
        return state

    locked_update(STATE_DIR / f"{safe}.desloppify.json", update)
    return result["writes"], result["fire"]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0

    if not is_write_tool(tool_name(payload)):
        print("{}")
        return 0

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not _is_code_file(file_path):
        print("{}")
        return 0

    cid = (payload.get("conversation_id") or payload.get("session_id") or "")
    if not cid:
        print("{}")
        return 0

    writes, fire = _record_write(cid, file_path)

    if fire:
        msg = (
            "🧹 WRAP-UP PASS DUE — {writes} code writes done. Before completing, "
            "run a dedicated cleanup sweep on ALL files you touched:\n"
            "- Remove dead/unused imports\n"
            "- Remove leftover debug statements (console.log, fmt.Println, print)\n"
            "- Fix inconsistent naming within files\n"
            "- Remove redundant nil/undefined checks where type guarantees safety\n"
            "- Remove unnecessary type assertions\n"
            "- Verify no commented-out code left behind\n"
            "- Ensure consistent formatting with project standards\n\n"
            "⚖️ The completion gate will BLOCK on stop until you also:\n"
            "- Run mcp__jcodemunch__find_dead_code on your changes (satisfies the dead-code gate)\n"
            "- Dispatch a code-review pass — a code-reviewer subagent or Santa BREAKER+SIMPLIFIER (satisfies the review gate)\n"
            "- Update the local CLAUDE.md for any changed directory (satisfies the docs gate)\n\n"
            "Cleanup is SEPARATE from implementation — do not second-guess your logic, "
            "only clean surface-level sloppiness."
        ).format(writes=writes)

        print(json.dumps({"additionalContext": msg}))
    else:
        print("{}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
