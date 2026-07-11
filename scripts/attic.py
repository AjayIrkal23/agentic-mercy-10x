#!/usr/bin/env python3
"""attic.py — move-to-attic helper for the 2026-07-11 "100x" overhaul (P0-T1).

Moves a path into ``~/.claude/attic/2026-07-11/<preserved-structure>/`` using
``git mv`` when the path is tracked and a plain filesystem move otherwise.

Charter v3 §6 preservation policy: nothing user-crafted is hard-deleted; retired
items move here with a per-item justification line in
``attic/2026-07-11/MANIFEST.md``.  ``--reason`` is therefore REQUIRED.

Usage:
    attic.py [--dry-run] --reason "why" PATH [PATH ...]

PATHs are interpreted relative to ~/.claude (or given absolute, inside ~/.claude).
Structure is preserved: ``hooks/foo.py`` -> ``attic/2026-07-11/hooks/foo.py``.
"""
from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path

CLAUDE = Path(__file__).resolve().parent.parent          # ~/.claude
ATTIC = CLAUDE / "attic" / "2026-07-11"
MANIFEST = ATTIC / "MANIFEST.md"
MANIFEST_HEADER = (
    "# Attic MANIFEST — 2026-07-11 (100x overhaul)\n\n"
    "Per-item justification for every retired item (Constraint Charter v3 §6\n"
    "preservation policy). `git-mv` = tracked at move time; `mv` = untracked.\n\n"
)


def _tracked(rel: str) -> bool:
    r = subprocess.run(
        ["git", "-C", str(CLAUDE), "ls-files", "--error-unmatch", rel],
        capture_output=True,
    )
    return r.returncode == 0


def _rel_inside_claude(p: str) -> Path | None:
    src = Path(p)
    src = src if src.is_absolute() else (CLAUDE / p)
    rel = Path(os.path.relpath(src, CLAUDE))
    if str(rel).startswith(".."):
        return None
    return rel


def _append_manifest(line: str) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    new = not MANIFEST.exists()
    with open(MANIFEST, "a", encoding="utf-8") as f:
        if new:
            f.write(MANIFEST_HEADER)
        f.write(line + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Move a path into the 2026-07-11 attic.")
    ap.add_argument("paths", nargs="+", help="path(s) relative to ~/.claude")
    ap.add_argument("--reason", required=True, help="per-item justification (recorded in MANIFEST.md)")
    ap.add_argument("--dry-run", action="store_true", help="print intended actions, change nothing")
    a = ap.parse_args()

    ts = datetime.date.today().isoformat()
    rc = 0
    for p in a.paths:
        rel = _rel_inside_claude(p)
        if rel is None:
            print(f"SKIP (outside ~/.claude): {p}", file=sys.stderr)
            rc = 1
            continue
        src = CLAUDE / rel
        if not (src.exists() or src.is_symlink()):
            print(f"SKIP (missing): {rel}", file=sys.stderr)
            rc = 1
            continue
        dest = ATTIC / rel
        tracked = _tracked(str(rel))
        kind = "git-mv" if tracked else "mv"
        line = f"- {ts} | `{rel}` -> `attic/2026-07-11/{rel}` | {kind} | {a.reason}"

        if a.dry_run:
            print(f"[dry-run] would {kind} {rel} -> attic/2026-07-11/{rel}")
            print(f"[dry-run] manifest: {line}")
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        if tracked:
            subprocess.run(
                ["git", "-C", str(CLAUDE), "mv", str(rel), str(Path("attic/2026-07-11") / rel)],
                check=True,
            )
        else:
            shutil.move(str(src), str(dest))
        _append_manifest(line)
        print(f"MOVED [{kind}] {rel} -> attic/2026-07-11/{rel}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
