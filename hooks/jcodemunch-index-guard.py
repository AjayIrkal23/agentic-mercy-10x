#!/usr/bin/env python3
"""SessionStart sub-script: strict jcodemunch index guard.

Detects whether the active workspace has a jcodemunch index and whether it is
stale (git HEAD mismatch).  Emits MANDATORY directives when the index is
missing or stale.

Note: superseded at SessionStart by index-lifecycle.py (P3); retained on disk
for flip-back parity until P7-T4. The systemd watch-daemon refcount was removed
here (P3-T2) — freshness is now handled event-driven by index-lifecycle.py.

Called by session-start-aggregator.py.  Receives the hook JSON on stdin.
Outputs {"additional_context": "..."} on stdout.  Fails open on any error.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
INDEX_DIR = HOME / ".code-index"
CONFIG_FILE = Path(__file__).parent / "jcodemunch-index-guard.config.json"


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


def _db_path_for(source_root: Path) -> Path | None:
    h = hashlib.sha1(str(source_root).encode()).hexdigest()[:8]
    candidates = [
        INDEX_DIR / f"local-{source_root.name}-{h}.db",
        INDEX_DIR / f"AjayIrkal23-{source_root.name}.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # default for "missing" check


def _get_indexed_head(db_path: Path) -> str | None:
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.execute("SELECT value FROM meta WHERE key='git_head'")
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _get_current_head(source_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None



def _directive_missing(source_root: Path, db_path: Path) -> str:
    return (
        "### MANDATORY: jcodemunch index MISSING for this project\n\n"
        f"Project: `{source_root}`\n"
        f"Expected DB: `{db_path}` — **DOES NOT EXIST**\n\n"
        "**YOU MUST PERFORM THIS STEP BEFORE ANY CODE WORK:**\n\n"
        "1. Call `mcp__jcodemunch__index_folder` with:\n"
        f'   `{{ "path": "{source_root}" }}`\n\n'
        "2. Wait for indexing to complete (do not proceed until confirmed)\n\n"
        "3. Verify with `mcp__jcodemunch__list_repos`\n\n"
        "This is NOT optional. Do not read, search, or modify any code files "
        "in this project until the index exists."
    )


def _directive_stale(source_root: Path, indexed_head: str, current_head: str) -> str:
    return (
        "### URGENT: jcodemunch index is STALE for this project\n\n"
        f"Project: `{source_root}`\n"
        f"Indexed HEAD: `{indexed_head[:12]}`\n"
        f"Current HEAD: `{current_head[:12]}`\n\n"
        "**YOU MUST REFRESH THE INDEX BEFORE CODE WORK:**\n\n"
        "Call `mcp__jcodemunch__index_folder` with:\n"
        f'`{{ "path": "{source_root}", "incremental": true }}`'
    )



def main() -> int:
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    try:
        source_root = _find_workspace_root(payload)
        if source_root is None:
            print("{}")
            return 0

        db_path = _db_path_for(source_root)
        parts: list[str] = []

        if not db_path.is_file():
            parts.append(_directive_missing(source_root, db_path))
        else:
            indexed_head = _get_indexed_head(db_path)
            current_head = _get_current_head(source_root)
            if indexed_head and current_head and indexed_head != current_head:
                parts.append(_directive_stale(source_root, indexed_head, current_head))
            else:
                parts.append(
                    f"jcodemunch index: FRESH — `{source_root.name}` "
                    f"(HEAD `{(current_head or 'unknown')[:8]}`)"
                )

        if not parts:
            print("{}")
            return 0

        ctx = "\n\n".join(parts)
        print(json.dumps({
            "additionalContext": ctx,
        }))

    except Exception:
        print("{}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
