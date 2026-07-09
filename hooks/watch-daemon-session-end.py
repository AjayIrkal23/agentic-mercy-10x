#!/usr/bin/env python3
"""SessionEnd hook: release this session's ref on the graphify/jcodemunch watch
daemons for the active workspace, stopping each once no session still needs it.

Called on Claude Code SessionEnd. Receives the hook JSON on stdin. Fails open.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _watch_refcount import release  # noqa: E402


def _find_workspace_root(payload: dict) -> Path | None:
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots:
        p = Path(str(roots[0]))
        if p.is_dir():
            return p

    cwd = Path(os.getcwd())
    if (cwd / ".git").exists():
        return cwd

    cur = cwd
    for _ in range(20):
        parent = cur.parent
        if parent == cur:
            break
        if (parent / ".git").exists():
            return parent
        cur = parent

    return None


def main() -> int:
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    try:
        source_root = _find_workspace_root(payload)
        cid = payload.get("conversation_id") or payload.get("session_id") or ""
        if source_root and cid:
            release("graphify", source_root, cid)
            release("jcodemunch", source_root, cid)
    except Exception:
        pass

    print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
