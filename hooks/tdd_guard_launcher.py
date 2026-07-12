#!/usr/bin/env python3
"""tdd_guard_launcher.py — gate tdd-guard to ACTIVE projects only (P6-T2 port).

Portable 1:1 replacement for ``tdd-guard-launcher.sh`` (zero bash in the live
hook path). Byte-identical behaviour:

  A repo is "active" iff it has  <project>/.claude/tdd-guard/data/config.json
  with ``"guardEnabled"`` NOT set to false.

  Active repo   -> forward the hook payload (stdin) to tdd-guard-gate.py (WARN
                   mode: allows out-of-project files, downgrades blocks to
                   advisories; never pauses).
  Inactive repo -> exit 0 immediately (allow, ZERO validation/LLM cost).

Wired on PreToolUse(Write|Edit|MultiEdit|TodoWrite), UserPromptSubmit, and
SessionStart. Fails OPEN on any error. The .sh is retained only as the 30-day
flip-back path (legacy-settings-hooks.json).
"""

from __future__ import annotations

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

# Matches the grep the .sh used: "guardEnabled" : false (tolerant of raw/malformed JSON).
_DISABLED_RE = re.compile(r'"guardEnabled"\s*:\s*false')


def main() -> int:
    try:
        stdin_data = sys.stdin.read()
    except Exception:  # pragma: no cover
        stdin_data = ""

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    cfg = Path(project_dir) / ".claude" / "tdd-guard" / "data" / "config.json"

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
            timeout=55,
            check=False,
        )
    except Exception:  # pragma: no cover - fail open
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
