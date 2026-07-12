#!/usr/bin/env python3
"""sessionStart: soft reminder for plan-mode-gate (ECC port). Optional JSON from plan-mode-check.js."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_SCRIPT = Path.home() / ".claude" / "skills" / "plan-mode-gate" / "scripts" / "plan-mode-check.js"


def main() -> None:
    raw = sys.stdin.read()
    roots: list[str] = []
    try:
        payload = json.loads(raw.strip()) if raw.strip() else {}
        roots = list(payload.get("workspace_roots") or [])
    except json.JSONDecodeError:
        payload = {}

    cwd = roots[0] if roots else os.getcwd()
    extra = ""
    if SKILL_SCRIPT.is_file() and Path(cwd).is_dir():
        try:
            r = subprocess.run(
                ["node", str(SKILL_SCRIPT)],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=12,
            )
            if r.returncode == 0 and r.stdout.strip():
                snippet = r.stdout.strip()
                if len(snippet) > 4000:
                    snippet = snippet[:4000] + "\n…"
                extra = f"\n\n### plan-mode-check.js (cwd: {cwd})\n\n```json\n{snippet}\n```\n"
        except (OSError, subprocess.TimeoutExpired):
            pass

    msg = (
        "### Session: plan / code discipline\n\n"
        "- Before large plans or multi-file work, skim **`~/.claude/skills/plan-mode-gate/SKILL.md`** "
        "after **`workflow-orchestrator`**.\n"
        "- **jcodemunch** steps in that skill are **MANDATORY** (codebase-intel-first rule): "
        "run the symbol index + dependency graph BEFORE reading/grepping.\n"
        "- Manual pre-flight from repo root: "
        "`node ~/.claude/skills/plan-mode-gate/scripts/plan-mode-check.js`.\n"
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": msg + extra}}))


if __name__ == "__main__":
    main()
