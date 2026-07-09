#!/usr/bin/env python3
"""Marker-driven workspace documentation reminders (generic; no repo name in prose).

Triggers when `{workspace_root}/.claude/documentation-lifecycle.md` exists.
stdin: Cursor hook JSON (workspace_roots, status for stop).
stdout JSON: partial hook response for session-start or empty {}.

CLI: python3 documentation_lifecycle_hook.py session-start|stop < stdin
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MARKER = ".claude/documentation-lifecycle.md"


def repo_root(payload: dict) -> Path | None:
    roots = payload.get("workspace_roots") or []
    if isinstance(roots, list) and roots:
        p = Path(str(roots[0])).resolve()
        return p if p.is_dir() else None
    cwd = os.getcwd()
    if cwd:
        return Path(cwd).resolve()
    return None


def has_lifecycle_marker(root: Path | None) -> bool:
    return root is not None and (root / MARKER).is_file()


def session_start_context(payload: dict) -> str:
    root = repo_root(payload)
    if root is None or not has_lifecycle_marker(root):
        return ""
    marker_rel = MARKER.replace("\\", "/")
    bullets: list[str] = []
    if (root / "AGENTS.md").is_file():
        bullets.append("- Read **[`AGENTS.md`](AGENTS.md)** first (repo root onboarding).")
    bullets.extend(
        [
            f"- Read **[`{marker_rel}`]({marker_rel})** for Plan gate (where defined), Phase A/B, "
            "and Phase B **Handoff** — project-specific paths, audit taxonomy, and linkage rules live there.",
            "- Use the **`update-docs`** Cursor skill when that file maps diffs to your documentation tree.",
        ]
    )
    return "### Workspace documentation lifecycle\n\n" + "\n".join(bullets) + "\n"


def stop_followup_message(payload: dict) -> str:
    if payload.get("status") != "completed":
        return ""
    root = repo_root(payload)
    if not has_lifecycle_marker(root):
        return ""
    marker_rel = MARKER.replace("\\", "/")
    return (
        "### Workspace: Phase B + Handoff\n\n"
        f"- Follow Phase B + **Handoff** in **[`{marker_rel}`]({marker_rel})** for this repository.\n"
        "- Summarize documentation updates completed, or state explicitly that none were required.\n"
    )


def session_start_json(payload: dict) -> dict:
    ctx = session_start_context(payload)
    if not ctx.strip():
        return {}
    return {"continue": True, "additionalContext": ctx}


def stop_json(payload: dict) -> dict:
    msg = stop_followup_message(payload)
    if not msg.strip():
        return {}
    return {"followup_message": msg}


def main() -> int:
    if len(sys.argv) < 2:
        print("{}")
        return 0
    mode = sys.argv[1].strip().lower().replace("-", "_")
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw.strip()) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    if mode == "session_start":
        out = session_start_json(payload)
    elif mode == "stop":
        out = stop_json(payload)
    else:
        out = {}

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
