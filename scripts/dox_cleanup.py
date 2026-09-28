#!/usr/bin/env python3
"""dox_cleanup.py — one-shot removal of UNTOUCHED dox template stubs under ~.

Before 2026-09-27 the dox sweep treated `$HOME` as a repo and documented every
directory (12k+ `CLAUDE.md`/`AGENTS.md` files, 499 under ~/Android/Sdk). This
deletes only the stubs nobody ever edited:

  * a `CLAUDE.md` that carries BOTH the `<!-- dox:child v1 -->` marker AND the
    template placeholder `<One or two lines` (i.e. byte-for-byte the template
    apart from the dir name), plus its sibling `AGENTS.md` — only when that is
    still the generated pointer text (a hand-edited AGENTS.md is kept).
  * Hand-edited docs (placeholder gone) are KEPT, and so is their AGENTS.md.

Walks ~ to depth 12, skipping hidden dirs and dox_engine.SKIP_DIRS' build/deps
entries (NOT the vendor/SDK names — those are exactly where the stubs live).

Usage:  dox_cleanup.py [--dry-run] [--apply] [--root PATH]
        --dry-run (default) prints counts per top-level dir; --apply deletes.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))
import dox_engine  # noqa: E402

MAX_DEPTH = 12
# Never descend into these (deps / VCS / caches / envs). Vendor-ish names
# (Android, Sdk, res, ...) are deliberately NOT here — the stubs live there.
WALK_SKIP = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "site-packages",
    ".cache", ".doc-index", ".code-index", ".npm", ".local", "snap",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}


def is_untouched_stub(doc: Path) -> bool:
    try:
        text = doc.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return (dox_engine.CHILD_MARKER in text[:200]
            and dox_engine.TEMPLATE_PLACEHOLDER in text)


def is_untouched_pointer(ptr: Path) -> bool:
    """True only for the generated AGENTS.md pointer (with or without the
    `<!-- dox:pointer -->` marker) — a hand-edited AGENTS.md is kept (Santa P6)."""
    try:
        text = ptr.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    def norm(s: str) -> str:
        return "\n".join(ln.strip() for ln in s.splitlines()
                         if ln.strip() and ln.strip() != dox_engine.POINTER_MARKER)

    known = {norm(dox_engine.pointer_text({})), norm(dox_engine._FALLBACK_POINTER),
             norm(dox_engine.root_pointer_text({}))}
    return norm(text) in known


def find_candidates(root: Path):
    """Yield (CLAUDE.md, AGENTS.md|None) pairs that are untouched template stubs."""
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".") and d not in WALK_SKIP)
        if len(rel.parts) >= MAX_DEPTH:
            dirnames[:] = []
        if dox_engine.ROOT_DOC not in filenames:
            continue
        doc = Path(dirpath) / dox_engine.ROOT_DOC
        if not is_untouched_stub(doc):
            continue
        ptr = Path(dirpath) / dox_engine.POINTER_DOC
        yield doc, (ptr if ptr.is_file() and is_untouched_pointer(ptr) else None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="delete (default is dry run)")
    ap.add_argument("--dry-run", action="store_true", help="report only (default)")
    ap.add_argument("--root", default=str(Path.home()), help="walk root (default: ~)")
    args = ap.parse_args(argv)
    root = Path(args.root).expanduser().resolve()

    per_top: Counter = Counter()
    files: list = []
    for doc, ptr in find_candidates(root):
        rel = doc.relative_to(root)
        per_top[rel.parts[0] if len(rel.parts) > 1 else "."] += 1
        files.append(doc)
        if ptr is not None:
            files.append(ptr)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] untouched dox stubs under {root}: "
          f"{sum(per_top.values())} dir(s), {len(files)} file(s)")
    for top, n in per_top.most_common():
        print(f"  {n:6d}  {top}/")

    if not args.apply:
        return 0
    deleted = 0
    for f in files:
        try:
            f.unlink()
            deleted += 1
        except OSError as exc:
            print(f"  ! could not delete {f}: {exc}", file=sys.stderr)
    print(f"deleted {deleted} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
