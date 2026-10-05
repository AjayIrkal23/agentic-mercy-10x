"""backups.py — bounded, dated backups of a rendered file (audit 2026-10-05 A-09, J-11).

``backup(path)`` copies ``path`` to ``<name>.bak-<UTC stamp>`` (mode 600), keeps the
newest ``keep`` DATED backups by mtime (a name can lie about its date; the mtime is what
happened) and points ``<name>.bak-latest`` at the newest one. Named backups without a
date (``.bak``, ``.bak-wp11``) are hand-made and never pruned. ``prune`` alone also
drops a ``-latest`` pointer whose target is gone. Pure stdlib.
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

KEEP = 3


def _dated(path: Path) -> re.Pattern:
    return re.compile(rf"^{re.escape(path.name)}\.bak[-.]\d{{8}}")


def dated_backups(path: Path) -> list[Path]:
    """Dated backups of ``path``, newest first (by mtime)."""
    path = Path(path)
    pat = _dated(path)
    found = [p for p in path.parent.glob(f"{path.name}.bak*") if p.is_file() and pat.match(p.name)]
    return sorted(found, key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)


def _latest(path: Path) -> Path:
    return path.with_name(f"{path.name}.bak-latest")


def prune(path: Path, keep: int = KEEP) -> list[Path]:
    """Delete dated backups beyond the newest ``keep``; repoint or drop ``-latest``.
    Returns the removed files."""
    path = Path(path)
    dated = dated_backups(path)
    removed = []
    for old in dated[keep:]:
        try:
            old.unlink()
            removed.append(old)
        except OSError:
            pass
    pointer, newest = _latest(path), (dated[:keep] or [None])[0]
    if newest is not None:
        pointer.write_text(str(newest) + "\n", encoding="utf-8")
        os.chmod(pointer, 0o600)
    elif pointer.exists():
        pointer.unlink()
    return removed


def backup(path: Path, keep: int = KEEP, stamp: str | None = None) -> Path:
    """Copy ``path`` to a dated backup (600), prune to ``keep``; returns the backup."""
    path = Path(path)
    stamp = stamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, dest)
    os.chmod(dest, 0o600)
    os.utime(dest, None)  # retention is by mtime: the backup is the newest event
    prune(path, keep)
    return dest
