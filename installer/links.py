#!/usr/bin/env python3
"""links.py — materialize skill trees as REAL files, never symlinks (P6-T5).

Windows cannot rely on POSIX symlinks (they need admin/developer mode), so every
skill that used to be a symlink is materialized as a real directory (copy) or an
NTFS junction. This workbench was already fully de-symlinked in P5-T12 (gstack
pointer skills + higgsfield/mmx real dirs), so on an existing install this is an
idempotent verify. On a fresh clone it (re)creates any declared link target and
runs the gstack pointer generator.

Strategy per target:
  * target already a real dir/file      -> OK (skip)
  * target is a symlink                 -> replace with a junction (Windows) or a
                                           copy (POSIX) so no symlink survives
  * target missing, source present      -> junction (Windows) / copytree (POSIX)

Pure stdlib; OS branching via hooks/lib/platform.py. Never raises.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_HOOKS = _ROOT / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402

MANIFEST = _ROOT / "installer" / "manifest.json"


def _junction(src: Path, dst: Path) -> bool:
    """Create an NTFS junction dst -> src (Windows). Returns success."""
    cp = plat.run(["cmd", "/c", "mklink", "/J", str(dst), str(src)], timeout=30)
    return cp.returncode == 0


def _materialize_one(src: Path, dst: Path) -> str:
    if dst.exists() and not dst.is_symlink():
        return "OK(present)"
    if dst.is_symlink():
        try:
            dst.unlink()
        except OSError:
            return "WARN(unlink-failed)"
    if not src.exists():
        return "SKIP(no-source)"
    try:
        if plat.IS_WINDOWS:
            if src.is_dir() and _junction(src, dst):
                return "JUNCTION"
            # fall back to copy
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return "COPIED"
    except OSError as exc:
        return f"WARN({exc.__class__.__name__})"


def materialize(*, dry_run: bool = False) -> list[tuple[str, str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    results: list[tuple[str, str]] = []
    for link in manifest.get("links", []):
        if "target" not in link:  # the _about placeholder
            continue
        dst = Path(link["target"].replace("${HOME}/.claude", str(plat.claude_dir())))
        src = Path(link["source"].replace("${HOME}/.claude", str(plat.claude_dir())))
        if dry_run:
            results.append((dst.name, f"WOULD-MATERIALIZE from {src}"))
            continue
        results.append((dst.name, _materialize_one(src, dst)))
    return results


# Vendored / dependency trees that carry their own (gitignored) symlinks and are
# NOT part of the tracked skill surface: the upstream gstack clone, npm deps, and
# build output. A symlink inside any of these is not a workbench-owned symlink.
_SYMLINK_SCAN_SKIP = {"gstack", "node_modules", ".bin", "dist", ".git", "__pycache__"}


def find_symlinks(scope: Path | None = None) -> list[Path]:
    """Every symlink under the INSTALLED skill surface (excludes upstream/vendored
    trees — gstack clone internals, node_modules, dist — which the workbench never
    owns and which npm/upstream populate with their own symlinks)."""
    base = scope or (_ROOT / "skills")
    out: list[Path] = []
    if not base.exists():
        return out
    for p in base.rglob("*"):
        if _SYMLINK_SCAN_SKIP & set(p.parts):
            continue
        try:
            if p.is_symlink():
                out.append(p)
        except OSError:
            continue
    return out


if __name__ == "__main__":
    for name, status in materialize(dry_run=True):
        print(f"  {name:30s} {status}")
    syms = find_symlinks()
    print(f"installed-surface symlinks: {len(syms)}")
    for s in syms[:10]:
        print(f"  {s}")
