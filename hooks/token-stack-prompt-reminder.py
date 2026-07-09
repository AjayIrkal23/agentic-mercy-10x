#!/usr/bin/env python3
"""Merged beforeSubmitPrompt reminder for jcodemunch + graphify token stacks."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent


def _run_hook(script: str, *args: str, payload: str) -> str:
    try:
        proc = subprocess.run(
            ["python3", str(HOOKS_DIR / script), *args],
            input=payload,
            capture_output=True,
            text=True,
            timeout=18,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return ""
        blob = json.loads(proc.stdout)
        chunk = blob.get("additionalContext") or blob.get("additional_context") or ""
        return chunk.strip()
    except Exception:
        return ""


def main() -> int:
    payload = sys.stdin.read() or "{}"
    parts: list[str] = []

    # Task-aware directive (plan/audit/implement/debug) — leads because it is the
    # most actionable, recurring, phase-specific guidance. Emitted at most once
    # per task-type per session by the router itself.
    intel = _run_hook("codebase-intel-router.py", payload=payload)
    if intel:
        parts.append(intel)

    # Auto-init tdd-guard for the active repo (cheap: no-op once config exists).
    tdd = _run_hook("tdd-guard-init-guard.py", "prompt", payload=payload)
    if tdd:
        parts.append(tdd)

    # Auto-stub the dox CLAUDE.md tree root (cheap: no-op once a root exists).
    dox = _run_hook("dox-tree-guard.py", "prompt", payload=payload)
    if dox:
        parts.append(dox)

    jcm = _run_hook("jcodemunch-enforce.py", "prompt-submit", payload=payload)
    if jcm:
        parts.append(jcm)

    gf = _run_hook("graphify-enforce.py", "prompt-submit", payload=payload)
    if gf:
        parts.append(gf)

    if not parts:
        print("{}")
        return 0

    ctx = "\n\n".join(parts)
    print(json.dumps({
        "continue": True,
        "additionalContext": ctx,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
