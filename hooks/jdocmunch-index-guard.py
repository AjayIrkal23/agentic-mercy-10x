#!/usr/bin/env python3
"""SessionStart sub-script: jdocmunch doc-index guard.

Mirrors jcodemunch-index-guard.py for the jDocMunch documentation index.
Detects whether the active workspace has a jdocmunch index under
~/.doc-index/local/<name>.json and whether it is stale (a tracked doc file
is newer than the index manifest).  Emits MANDATORY directives when the
index is missing or stale.

Called by session-start-aggregator.py.  Receives the hook JSON on stdin.
Outputs {"additionalContext": "..."} on stdout.  Fails open on any error.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
INDEX_DIR = HOME / ".doc-index" / "local"
CONFIG_FILE = Path(__file__).parent / "jdocmunch-index-guard.config.json"

# Doc extensions jdocmunch indexes (subset of parser.ALL_EXTENSIONS that
# matters for staleness; keep cheap).
DOC_GLOBS = ["*.md", "*.mdx", "*.markdown", "*.rst", "*.adoc", "*.txt",
             "*.yaml", "*.yml", "*.html", "*.ipynb"]
MAX_STAT_FILES = 20000  # safety cap for the mtime sweep


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


def _newest_doc_mtime(source_root: Path) -> float | None:
    """Newest mtime among git-tracked doc files. None if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "ls-files", "-z", "--"] + DOC_GLOBS,
            capture_output=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        newest = 0.0
        files = result.stdout.split(b"\0")[:MAX_STAT_FILES]
        for rel in files:
            if not rel:
                continue
            try:
                mt = (source_root / rel.decode("utf-8", "replace")).stat().st_mtime
                if mt > newest:
                    newest = mt
            except OSError:
                continue
        return newest or None
    except Exception:
        return None


def _directive_missing(source_root: Path, name: str, manifest: Path) -> str:
    return (
        "### MANDATORY: jdocmunch doc index MISSING for this project\n\n"
        f"Project: `{source_root}`\n"
        f"Expected manifest: `{manifest}` — **DOES NOT EXIST**\n\n"
        "**BEFORE any documentation exploration in this project:**\n\n"
        "1. Call `mcp__jdocmunch__index_local` with:\n"
        f'   `{{ "path": "{source_root}", "name": "{name}" }}`\n\n'
        "2. Verify with `mcp__jdocmunch__doc_list_repos`\n\n"
        "Until then do not brute-read doc files — use jdocmunch "
        "`search_sections` / `get_toc` / `get_section` once indexed."
    )


def _directive_stale(source_root: Path, name: str) -> str:
    return (
        "### URGENT: jdocmunch doc index is STALE for this project\n\n"
        f"Project: `{source_root}` — tracked doc files are newer than the index.\n\n"
        "**Refresh before doc exploration:** call `mcp__jdocmunch__index_local` with:\n"
        f'`{{ "path": "{source_root}", "name": "{name}" }}`'
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

        name = source_root.name
        manifest = INDEX_DIR / f"{name}.json"

        if not manifest.is_file():
            ctx = _directive_missing(source_root, name, manifest)
        else:
            newest = _newest_doc_mtime(source_root)
            if newest and newest > manifest.stat().st_mtime + 2:
                ctx = _directive_stale(source_root, name)
            else:
                ctx = f"jdocmunch doc index: FRESH — `{name}` (`{manifest.name}`)"

        print(json.dumps({"additionalContext": ctx}))
    except Exception:
        print("{}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
