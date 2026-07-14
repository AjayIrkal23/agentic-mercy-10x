#!/usr/bin/env python3
"""detect.py — OS / interpreter / tool detection for the installer (P6-T5).

Resolves the concrete values the render + deps steps need, all OS branching via
``hooks/lib/platform.py`` (this module never OS-branches directly). Pure stdlib.

``detect()`` returns an ``Env`` with:
  os_name        "windows" | "posix"
  is_windows     bool
  python         python invocation string (Windows: prefer the ``py -3`` launcher)
  node           node interpreter path (or "node")
  git            git path (or None)
  claude_cli     path to the ``claude`` CLI (or None — MCP registration skipped)
  tokens         {"PYTHON","NODE","CLAUDE_DIR"} for render/manifest substitution
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402


def _python_invocation() -> str:
    """Best portable python invocation.

    Windows: prefer the ``py -3`` launcher (present on standard installs, resolves
    the right 3.x); else the running interpreter. POSIX: keep ``python3`` so the
    rendered settings.json stays byte-identical to the committed live file.
    """
    if plat.IS_WINDOWS:
        if shutil.which("py"):
            return "py -3"
        return sys.executable or "python"
    return "python3"


def _claude_dir_token() -> str:
    """CLAUDE_DIR token value.

    POSIX: keep the literal ``${HOME}/.claude`` so Claude Code expands it and the
    rendered file matches the committed one byte-for-byte. Windows: the concrete
    path (``${HOME}`` is not expanded there).
    """
    if plat.IS_WINDOWS:
        return str(plat.claude_dir())
    return "${HOME}/.claude"


@dataclass
class Env:
    os_name: str
    is_windows: bool
    python: str
    node: str
    git: str | None
    claude_cli: str | None
    tokens: dict = field(default_factory=dict)  # RENDER tokens (CLAUDE_DIR may be ${HOME}/.claude)
    real_dir: str = ""                            # concrete ~/.claude path for subprocess commands
    npm: str | None = None                        # npm path (or None) — lean-ctx/tdd-guard/npx MCPs
    uv: str | None = None                         # uv path (or None) — semgrep/jcode/jdoc + uvx fetch (POSIX)
    pipx: str | None = None                       # pipx path (or None) — Windows installer for the above


def detect() -> Env:
    is_win = plat.IS_WINDOWS
    python = _python_invocation()
    node = plat.node_exe() or "node"
    git = shutil.which("git")
    claude_cli = shutil.which("claude")
    tokens = {
        "PYTHON": python,
        "NODE": node,
        "CLAUDE_DIR": _claude_dir_token(),
    }
    return Env(
        os_name="windows" if is_win else "posix",
        is_windows=is_win,
        python=python,
        node=node,
        git=git,
        claude_cli=claude_cli,
        tokens=tokens,
        real_dir=str(plat.claude_dir()),
        npm=shutil.which("npm"),
        uv=shutil.which("uv"),
        pipx=shutil.which("pipx"),
    )


def _fmt(env: Env) -> str:
    return (
        f"os={env.os_name} python={env.python!r} node={env.node!r} "
        f"git={'yes' if env.git else 'MISSING'} claude={'yes' if env.claude_cli else 'MISSING'} "
        f"uv={'yes' if env.uv else 'no'} npm={'yes' if env.npm else 'no'} pipx={'yes' if env.pipx else 'no'}"
    )


if __name__ == "__main__":
    print(_fmt(detect()))
