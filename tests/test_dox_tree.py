"""test_dox_tree.py — each directory CLAUDE.md names every tracked file beside it.

The dox contract in every local CLAUDE.md is "update this file whenever you add,
remove, or rename files here". A tracked file its directory doc never names is
doc drift, so it fails here instead of being found by an audit.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SKIP = {"CLAUDE.md", "AGENTS.md", "README.md", "__init__.py"}


def test_directory_claude_md_names_every_tracked_file():
    cp = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(_ROOT), "ls-files"],
                        capture_output=True, text=True)
    tracked = cp.stdout.splitlines() if cp.returncode == 0 else []
    docs = [p for p in tracked if p.endswith("/CLAUDE.md") and not p.startswith("skills/")]
    if not docs:
        pytest.skip("not a git checkout")
    gaps = {}
    for doc in docs:
        d = doc[: -len("CLAUDE.md")]
        text = (_ROOT / doc).read_text(encoding="utf-8")
        beside = (p[len(d):] for p in tracked if p.startswith(d) and "/" not in p[len(d):])
        missing = sorted(f for f in beside if f not in _SKIP and f not in text)
        if missing:
            gaps[doc] = missing
    assert not gaps, f"files not named in their directory CLAUDE.md: {gaps}"
