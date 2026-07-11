#!/usr/bin/env python3
"""
UserPromptSubmit: nudge agents to consult or build graphify-out/.

Fires ONCE per conversation (first UserPromptSubmit only). Subsequent prompts
get an empty response to avoid repeating identical hint text every turn.

State file: ~/.claude/hooks/.state/{cid}.graphify-hint.json

stdin: Cursor hook JSON (workspace_roots, ...).
stdout: {} or { continue: true, additional_context: "..." }

Only Path.stat checks — never shells out to graphify.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

STATE_DIR = Path.home() / ".claude" / "hooks" / ".state"


def _safe_cid(raw: str) -> str:
    """Sanitize conversation_id to a safe filename component."""
    return re.sub(r"[^a-zA-Z0-9\-_]", "_", raw)[:80]


def _state_path(cid: str) -> Path:
    return STATE_DIR / f"{_safe_cid(cid)}.graphify-hint.json"


def _already_emitted(cid: str) -> bool:
    try:
        p = _state_path(cid)
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            return bool(data.get("emitted"))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return False


def _mark_emitted(cid: str) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state_path(cid).write_text(json.dumps({"emitted": True}), encoding="utf-8")
    except OSError:
        pass


def _repo_root(payload: dict) -> Path | None:
    roots = payload.get("workspace_roots") or []
    if isinstance(roots, list) and roots:
        p = Path(str(roots[0])).expanduser().resolve()
        return p if p.is_dir() else None
    cwd = os.getcwd()
    if cwd:
        p = Path(cwd).expanduser().resolve()
        return p if p.is_dir() else None
    return None


def _artifacts(root: Path) -> tuple[bool, bool]:
    base = root / "graphify-out"
    gj = base / "graph.json"
    rep = base / "GRAPH_REPORT.md"
    return gj.is_file(), rep.is_file()


def _context(payload: dict) -> str:
    root = _repo_root(payload)
    if root is None:
        return ""

    graph_json, report_md = _artifacts(root)

    if graph_json or report_md:
        return (
            "[Graphify] Graph exists for this project. "
            "Query via mcp__graphify before broad file exploration. "
            f"Report: {root}/graphify-out/GRAPH_REPORT.md"
        )

    return (
        "[Graphify] No graph.json found. "
        f"Run `graphify update {root}` before architecture questions."
    )


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw if raw.strip() else "{}")
    except json.JSONDecodeError:
        print("{}")
        return 0
    if not isinstance(payload, dict):
        print("{}")
        return 0

    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not isinstance(cid, str):
        cid = ""

    # Only emit once per conversation; all subsequent prompts get nothing.
    if cid and _already_emitted(cid):
        print("{}")
        return 0

    ctx = _context(payload).strip()
    if not ctx:
        print("{}")
        return 0

    if cid:
        _mark_emitted(cid)

    print(json.dumps({
        "continue": True,
        "additionalContext": ctx,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
