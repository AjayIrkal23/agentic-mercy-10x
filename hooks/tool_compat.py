"""Cursor + Claude Code tool name compatibility helpers."""
from __future__ import annotations

WRITE_TOOLS = frozenset({"Write", "Edit", "StrReplace", "MultiEdit", "TabWrite"})
SHELL_TOOLS = frozenset({"Shell", "Bash"})
AGENT_TOOLS = frozenset({"Task", "Agent"})
READ_TOOLS = frozenset({"Read", "Grep", "Glob", "TabRead"})


def tool_name(payload: dict) -> str:
    return str(payload.get("tool_name") or payload.get("tool") or "")


def is_write_tool(name: str) -> bool:
    return name in WRITE_TOOLS


def is_shell_tool(name: str) -> bool:
    return name in SHELL_TOOLS


def is_agent_tool(name: str) -> bool:
    return name in AGENT_TOOLS
