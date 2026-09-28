#!/usr/bin/env python3
"""tdd_guard_launcher.py — gate tdd-guard to ACTIVE git projects only.

  A repo is "active" iff it has  <git-root>/.claude/tdd-guard/data/config.json
  with ``"guardEnabled"`` NOT set to false.

  Active repo   -> forward the hook payload (stdin) to tdd-guard-gate.py (WARN
                   mode: allows out-of-project files, downgrades blocks to
                   advisories; never pauses).
  Inactive repo -> exit 0 immediately (allow, ZERO validation/LLM cost).
  $HOME / non-git cwd -> exit 0 immediately. HOME is a container, never a project
                   (the old `<cwd>/.claude/tdd-guard` lookup made every session
                   started in `~` pay an LLM round-trip per write — A03-B2).
  TodoWrite      -> exit 0 (not a code write).

Wired on PreToolUse(Write|Edit|MultiEdit) via dispatch. Fails OPEN on any error.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
try:
    from lib import platform as _plat  # noqa: E402
except Exception:  # pragma: no cover - fail-open
    _plat = None
try:
    from lib.code_files import git_root, is_home  # noqa: E402
except Exception:  # pragma: no cover - fail-open (no root → inactive)
    def git_root(path):  # type: ignore
        return None

    def is_home(root):  # type: ignore
        return True

# Matches the grep the .sh used: "guardEnabled" : false (tolerant of raw/malformed JSON).
_DISABLED_RE = re.compile(r'"guardEnabled"\s*:\s*false')
_GATE_TIMEOUT_S = 8


def main() -> int:
    try:
        stdin_data = sys.stdin.read()
    except Exception:  # pragma: no cover
        stdin_data = ""

    try:
        tool = str((json.loads(stdin_data or "{}") or {}).get("tool_name") or "")
    except Exception:
        tool = ""
    if tool == "TodoWrite":
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    root = git_root(project_dir)
    if root is None or is_home(root):
        return 0  # HOME / not a git repo -> never a tdd project
    project_dir = str(root)
    cfg = root / ".claude" / "tdd-guard" / "data" / "config.json"

    active = False
    if cfg.is_file():
        try:
            text = cfg.read_text(encoding="utf-8", errors="replace")
            active = not _DISABLED_RE.search(text)
        except OSError:
            active = False

    if not active:
        return 0  # inactive project -> allow silently

    gate = _HOOKS / "tdd-guard-gate.py"
    if not gate.is_file():
        return 0  # nothing to forward to -> fail open

    py = _plat.python_exe() if _plat else (sys.executable or "python3")
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = project_dir
    try:
        # Forward stdin to the gate; the gate writes its advisory JSON straight
        # to our (inherited) stdout, exactly as the shell pipe did. Always 0.
        subprocess.run(
            [py, str(gate)],
            input=stdin_data,
            text=True,
            env=env,
            timeout=_GATE_TIMEOUT_S,
            check=False,
        )
    except Exception:  # pragma: no cover - fail open
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
