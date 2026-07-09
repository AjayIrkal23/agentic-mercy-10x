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
import sys
from pathlib import Path

from tool_compat import is_write_tool, tool_name

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR / ".state"

# After this many code writes, trigger the cleanup reminder (matches mandatory protocol Phase 4b).
# Lowered 8->3 so typical surgical sessions (2-5 files) still get the wrap-up nudge.
WRITES_THRESHOLD = 3

SKIP_EXTENSIONS = (
    ".md", ".mdx", ".json", ".yaml", ".yml", ".toml", ".env",
    ".lock", ".css", ".svg", ".png", ".jpg", ".gif",
)


def _is_code_file(file_path: str) -> bool:
    if not file_path:
        return False
    for ext in SKIP_EXTENSIONS:
        if file_path.endswith(ext):
            return False
    return True


def _get_state(cid: str) -> dict:
    if not cid:
        return {"code_writes": 0, "fired": False, "code_paths": []}
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    state_file = STATE_DIR / f"{safe}.desloppify.json"
    if state_file.is_file():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"code_writes": 0, "fired": False, "code_paths": []}


def _save_state(cid: str, state: dict) -> None:
    if not cid:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    state_file = STATE_DIR / f"{safe}.desloppify.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")


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

    state = _get_state(cid)

    # Always count code writes — even after the reminder fired — so the completion
    # gate's thresholds (santa/dead-code) see an accurate count.
    state["code_writes"] = state.get("code_writes", 0) + 1
    paths = state.get("code_paths") or []
    if file_path and file_path not in paths:
        paths.append(file_path.replace("\\", "/"))
    state["code_paths"] = paths[-50:]
    writes = state["code_writes"]

    if state.get("fired"):
        _save_state(cid, state)
        print("{}")
        return 0

    if writes >= WRITES_THRESHOLD:
        state["fired"] = True
        _save_state(cid, state)

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
        _save_state(cid, state)
        print("{}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
