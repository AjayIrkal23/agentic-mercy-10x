#!/usr/bin/env python3
"""connector-ask-gate.py — PreToolUse gate on claude.ai connector, plugin and github MCP tools.

Sessions run in bypassPermissions with an empty deny list while connectors expose
destructive or outbound tools (Zoho ``delete_*``, Drive ``trash_file`` / ``share_file``,
Apollo ``*send_now``, Shopify ``graphql_mutation``). This gate answers
``permissionDecision: "ask"`` for those, so a person confirms each one (audit 2026-10-05
G-02). Read-only tools (list, search, get, read) pass silently.

Scope: tool names starting ``mcp__claude_ai_`` or ``mcp__plugin_``; the verb is judged
on the tool's own name (the last ``__`` segment) split on ``_`` and ``-``. Two harmless
higgsfield tools are allow-listed (audit 07 issue 11).

github MCP (P4): write tools (merge / push / create_or_update_file / PR / issue / branch / repo)
ask too. lib/gate_mode judges who can answer: when nobody can (subagent, Workflow script, `-p`
run, restored session) the action is DENIED, never downgraded to an advisory, since an advisory
would let the push / send / delete run (REVIEW2 Fix 2). Exit 0 always; any error prints ``{}``
(fail open).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

_PREFIXES = ("mcp__claude_ai_", "mcp__plugin_")
_GITHUB = "mcp__github__"
_DESTRUCTIVE = frozenset({
    "delete", "remove", "trash", "destroy", "purge", "drop", "wipe", "erase",
    "share", "send", "publish", "bulk", "mutation", "approve", "refund", "void",
    "cancel", "unsubscribe", "transfer", "revoke",
})
_GITHUB_WRITE = frozenset({"merge_pull_request", "push_files", "create_or_update_file", "create_pull_request",
                           "update_issue", "create_issue", "add_issue_comment", "create_branch", "create_repository",
                           "fork_repository", "create_pull_request_review", "update_pull_request_branch",
                           "delete_file", "update_pull_request", "create_release", "delete_branch"})
_GIT_WRITE_VERBS = frozenset({"merge", "push", "create", "update", "delete", "fork", "add", "close"})  # unknown tools
_SAFE_TOOLS = frozenset({"mcp__claude_ai_higgsfield__remove_background",
                         "mcp__claude_ai_higgsfield__ads_studio_cancel_run"})


def verdict(tool: str) -> str | None:
    """'github-write', the destructive verb found in ``tool``'s own name, or None."""
    if tool in _SAFE_TOOLS:
        return None
    if tool.startswith(_GITHUB):
        name = tool[len(_GITHUB):].lower()
        if name in _GITHUB_WRITE or (name.split("_")[0] in _GIT_WRITE_VERBS
                                     and not name.startswith(("get", "list", "search"))):
            return "github-write"
        return None
    if not tool.startswith(_PREFIXES):
        return None
    name = tool.rsplit("__", 1)[-1].lower()
    for token in re.split(r"[_\-]+", name):
        if token in _DESTRUCTIVE:
            return token
    return None


def _decide(payload) -> tuple:
    try:
        from lib import gate_mode
        return gate_mode.decide(payload, "ask")
    except Exception:  # noqa: BLE001 - oom-sentinel absent or broken: plain ask
        return "ask", "interactive"


def _telemetry(**fields) -> None:
    try:
        from lib import hook_telemetry
        hook_telemetry.record("PreToolUse", "connector-ask-gate", **fields)
    except Exception:  # noqa: BLE001
        pass


def _emit(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        tool = str(payload.get("tool_name") or "")
        verb = verdict(tool)
        if verb is None:
            print("{}")
            return 0
        server, _, name = tool[len("mcp__"):].rpartition("__")
        decision, why = _decide(payload)
        row = {"tool": tool, "session": str(payload.get("session_id") or "")}
        if verb == "github-write":
            reason = (f"GITHUB WRITE: `{name}` changes a live GitHub repository (this session bypasses permission "
                      "prompts). Confirm to run it.")
        else:
            reason = (f"CONNECTOR CHECK: `{name}` on `{server}` is a {verb} action against a live "
                      f"external account (this session bypasses permission prompts). Confirm to run it.")
        # never downgraded to an advisory (REVIEW2 Fix 2), and never auto-denied (2026-10-31, owner): when
        # no prompt can show, the session's own permission mode decides the ask.
        _telemetry(decision="ask", **row, **({} if decision == "ask" else {"reason": why}))
        _emit("ask", reason if decision == "ask" else reason + f" ({why} context: the session's permission "
                                                             "mode decides.)")
    except Exception:  # noqa: BLE001 - a broken gate must never brick a session
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
