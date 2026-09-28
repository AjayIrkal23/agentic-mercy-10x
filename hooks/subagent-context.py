#!/usr/bin/env python3
"""subagent-context.py — SubagentStart advisory (D3).

A subagent starts in a fresh context and inherits none of the session's rules.
Every spawn passes through SubagentStart, so the write protocol and the
no-servers / no-commit rules are injected HERE (this replaces opus-guard's old
`prompt` mutation, which the dispatcher always dropped). Output stays under
~1,800 chars (incl. the compact MCP protocol block). Fail-open: any error -> {}.

stdin : {"agent_id": "...", "agent_type": "...", "cwd": "..."}
stdout: {"hookSpecificOutput":{"hookEventName":"SubagentStart","additionalContext":"..."}}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

_PROTOCOL = (
    "FILE ACCESS PROTOCOL: Read a file immediately before you Edit it (Edit requires a "
    "prior Read of that exact file). Write files ONLY with Edit / Write / ctx_patch. "
    "Never write through the shell: no `sed -i`, `perl -i`, heredocs (`cat > f <<EOF`, "
    "`python3 - <<EOF`), `tee`, `echo >`, or `python3 -c` / `node -e` writes. Bash is for "
    "builds, tests, git, package managers and read-only inspection."
)
_RULES = (
    "Never start dev servers or open browsers on your own; the user runs apps — verify "
    "with builds/tests that exit. Never `git commit` unless your prompt explicitly says to."
)
_SKILLS = (
    "Surface skills: FE files -> frontend-standards-always-follow; BE -> "
    "backend-standards-always-follow (native `paths:` surfaces the rest)."
)
_MCP = (
    "MCP PROTOCOL (MUST; skip only trivial lookups): code -> jcodemunch first "
    "(get_context_bundle / search_symbols / get_symbol_source; get_blast_radius + "
    "find_references before editing a shared symbol); architecture/dependencies -> graphify "
    "query_graph / get_neighbors; doc sets -> jdocmunch search_sections; plan/debug/design/"
    "audit/decide -> mcp__sequential-thinking__sequentialthinking first; library APIs or new "
    "imports -> context7 resolve-library-id -> query-docs; auth/session/middleware/input "
    "files -> mcp__semgrep__semgrep_scan. A server is down -> say so, fall back."
)


def build(payload: dict) -> str:
    lines = [_PROTOCOL, _RULES, _MCP]
    try:
        from lib import model_mode

        mode = model_mode.forced_mode(payload.get("cwd"))
        if mode:
            lines.append(f"Model mode for this repo is pinned to {mode}: pass "
                         f"model:\"{mode}\" on every Agent call you make.")
    except Exception:  # noqa: BLE001
        pass
    lines.append(_SKILLS)
    return "\n".join(lines)[:1800]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            payload = {}
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": build(payload),
        }}))
    except Exception:  # noqa: BLE001
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
