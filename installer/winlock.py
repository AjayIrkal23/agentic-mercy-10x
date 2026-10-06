"""winlock.py — one install at a time per tools dir (A5v2-04).

Two ``install.cmd`` runs, the UI plus a headless run, or the installer while Claude Code's first
SessionStart starts the daily self-heal used to race on the same ``<name>.part`` / ``<dest>.tmp-*``
dirs and on the read-modify-write of the user PATH. ``InstallLock`` is ``<tools>\\.install.lock``: a
non-blocking exclusive file lock like ``hooks/tools/daily_lock.try_lock`` (``msvcrt`` / ``fcntl``; the OS
drops it when its holder dies, so a crash never wedges the next run). It picks the module by what
exists, not by ``plat.IS_WINDOWS``, so the tests that flip that flag on Linux still lock for real.
``take()`` is lazy: a run that only finds everything PRESENT never creates the tools dir. A refused
lock means "another install is running": the caller reports ``BUSY`` and changes nothing. Pure stdlib.
"""
from __future__ import annotations

from pathlib import Path

LOCK_NAME = ".install.lock"
BUSY = "SKIP(another install is running; nothing was changed)"


def _lock(fh) -> bool:
    """A non-blocking exclusive lock on ``fh``: False when another handle or process holds it."""
    try:
        import fcntl
    except ImportError:  # Windows: a byte-range lock on the first byte
        import msvcrt
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


class InstallLock:
    def __init__(self, tools):
        self.tools, self.busy, self._fh = Path(tools), False, None

    def take(self, create: bool = True) -> bool:
        """True once this process holds the lock; False when another install holds it. With
        ``create=False`` and no tools dir yet there is nothing to protect: True, nothing locked."""
        if self._fh is not None:
            return True
        if self.busy:
            return False
        if not create and not self.tools.is_dir():
            return True
        try:
            self.tools.mkdir(parents=True, exist_ok=True)
            fh = open(self.tools / LOCK_NAME, "a+")
        except OSError:
            return True  # no tools dir / lock file to be had: the install step reports its own error
        if _lock(fh):
            self._fh = fh
            return True
        fh.close()
        self.busy = True
        return False

    def release(self) -> None:
        if self._fh is not None:
            self._fh.close()  # closing the handle drops the lock
            self._fh = None
