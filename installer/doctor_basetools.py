"""doctor_basetools.py — doctor row ``base-tools``: can this machine run the workbench at all?

Without Claude Code, node + npm, git and uv there are no MCP servers, no plugins and no tool
installs, yet every other row can still read green (the 2026-10-06 fresh-Windows rehearsal: SUCCESS
with none of them). FAIL names what is missing (``selfheal._repair`` runs the OS's no-admin
installer again), WARN covers gh and ollama and, on Windows, a git with no ``bash.exe`` beside it
(Claude Code's Bash tool). SKIP under ``--ci`` and under ``AGENTIC_MERCY_SKIP_BASE_TOOLS`` (offline
machines, the test suite: nothing would be installed, so a FAIL could never be repaired).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from lib import platform as plat  # noqa: E402
import winutil  # noqa: E402

REQUIRED = ("claude", "node", "npm", "git", "uv")
OPTIONAL = ("gh", "ollama")


def check_base_tools(ci: bool, which: Callable = winutil.which, environ=None) -> tuple[str, str]:
    environ = os.environ if environ is None else environ
    if ci:
        return "SKIP", "--ci"
    if environ.get("AGENTIC_MERCY_SKIP_BASE_TOOLS"):
        return "SKIP", "AGENTIC_MERCY_SKIP_BASE_TOOLS is set (nothing would be installed)"

    def found(name: str) -> str | None:
        p = which(name)
        return None if p and plat.IS_WINDOWS and winutil.store_stub(p) else p  # a Store shim is not a tool

    missing = [n for n in REQUIRED if not found(n)]
    if missing:
        return "FAIL", f"missing: {', '.join(missing)} (the installer installs them per user; re-run it)"
    soft = [f"{n} missing (optional)" for n in OPTIONAL if not found(n)]
    git = found("git")
    if plat.IS_WINDOWS and git and not winutil.git_bash(git, [environ.get("CLAUDE_CODE_GIT_BASH_PATH", "")]):
        soft.append("git has no bash.exe beside it (Claude Code's Bash tool needs Git Bash)")
    if soft:
        return "WARN", "; ".join(soft)
    return "PASS", "claude, node + npm, git, uv resolve; gh and ollama present"
