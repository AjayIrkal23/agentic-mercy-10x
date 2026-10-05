"""daily_lock.py — the non-blocking exclusive file lock behind ``selfheal-daily.py``."""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from lib import platform as plat  # noqa: E402


@contextlib.contextmanager
def try_lock(path: Path):
    """Non-blocking exclusive lock; yields False when another copy holds it."""
    try:
        fh = open(path, "a+")
    except OSError:
        yield False
        return
    try:
        if plat.IS_WINDOWS:
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        yield False
        return
    try:
        yield True
    finally:
        fh.close()
