#!/usr/bin/env python3
"""links.py — symlink scan for the doctor row ``locked-source-links``.

``find_symlinks(scope)`` lists every symlink (or NTFS junction) under the installed
skill surface. Windows cannot rely on POSIX symlinks, so the doctor fails when one
appears. Materialisation was removed 2026-10-29: it was never called (the installer
copies skills through ``installer/deps.py``; the manifest ``links`` list is read by the
doctor only).

Pure stdlib. Never raises.
"""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# Vendored / dependency trees that carry their own (gitignored) symlinks are not
# part of the tracked skill surface.
_SYMLINK_SCAN_SKIP = {"node_modules", ".bin", "dist", ".git", "__pycache__"}


def find_symlinks(scope: Path | None = None) -> list[Path]:
    """Every symlink under the INSTALLED skill surface (excludes upstream/vendored
    trees such as node_modules and dist, which the workbench never owns)."""
    base = scope or (_ROOT / "skills")
    out: list[Path] = []
    if not base.exists():
        return out
    isjunction = getattr(os.path, "isjunction", lambda _p: False)  # 3.12+; Windows junctions
    for p in base.rglob("*"):
        if _SYMLINK_SCAN_SKIP & set(p.parts):
            continue
        try:
            if p.is_symlink() or isjunction(p):
                out.append(p)
        except OSError:
            continue
    return out


if __name__ == "__main__":
    syms = find_symlinks()
    print(f"installed-surface symlinks: {len(syms)}")
    for s in syms[:10]:
        print(f"  {s}")
