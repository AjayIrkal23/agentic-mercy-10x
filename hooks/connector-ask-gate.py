#!/usr/bin/env python3
"""connector-ask-gate.py — PreToolUse gate on claude.ai connector and plugin MCP tools.

Sessions run in bypassPermissions with an empty deny list while connectors expose
destructive or outbound tools (Zoho ``delete_*``, Drive ``trash_file`` / ``share_file``,
Apollo ``*send_now``, Shopify ``graphql_mutation``). This gate answers
``permissionDecision: "ask"`` for those, so a person confirms each one; it never denies
(audit 2026-10-05 G-02). Read-only tools (list, search, get, read) pass silently.

Scope: tool names starting ``mcp__claude_ai_`` or ``mcp__plugin_``; the verb is judged
on the tool's own name (the last ``__`` segment) split on ``_`` and ``-``.
Exit 0 always; any error prints ``{}`` (fail open).
"""
from __future__ import annotations

import json
import re
import sys

_PREFIXES = ("mcp__claude_ai_", "mcp__plugin_")
_DESTRUCTIVE = frozenset({
    "delete", "remove", "trash", "destroy", "purge", "drop", "wipe", "erase",
    "share", "send", "publish", "bulk", "mutation", "approve", "refund", "void",
    "cancel", "unsubscribe", "transfer", "revoke",
})


def verdict(tool: str) -> str | None:
    """The destructive verb found in ``tool``'s own name, or None."""
    if not tool.startswith(_PREFIXES):
        return None
    name = tool.rsplit("__", 1)[-1].lower()
    for token in re.split(r"[_\-]+", name):
        if token in _DESTRUCTIVE:
            return token
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        tool = str(payload.get("tool_name") or "")
        verb = verdict(tool)
        if verb is None:
            print("{}")
            return 0
        server, _, name = tool[len("mcp__"):].rpartition("__")
        reason = (f"CONNECTOR CHECK: `{name}` on `{server}` is a {verb} action against a live "
                  f"external account (this session bypasses permission prompts). Confirm to run it.")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }}))
    except Exception:  # noqa: BLE001 - a broken gate must never brick a session
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
