"""W6b hook robustness on Windows, part 2b: `locked_update` with a bounded lock wait (A4-12), split out of
``test_win_platform_locks.py`` (250-line cap). Windows is simulated with ``plat.IS_WINDOWS`` plus a stub
``msvcrt``; the one ``skipif`` test contends a real msvcrt byte-range lock.

The waits are asserted on a simulated clock (A7v2-05): a real-time bound flaked under load.
"""
from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
import types

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from lib import platform as plat  # noqa: E402


def _os(monkeypatch, windows: bool):
    monkeypatch.setattr(plat, "IS_WINDOWS", windows)


def _msvcrt(monkeypatch, locking):
    stub = types.SimpleNamespace(LK_LOCK=1, LK_NBLCK=2, LK_UNLCK=0, locking=locking)
    monkeypatch.setitem(sys.modules, "msvcrt", stub)
    return stub


def _held(fd, mode, n):
    raise OSError(36, "locked")


class _Clock:
    """`plat.time` stand-in: `sleep` advances `monotonic`, so a lock wait takes no real time and "gave up after
    about its timeout" is asserted on the simulated clock."""
    now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def __getattr__(self, name):
        return getattr(time, name)


def test_lock_on_windows_polls_msvcrt_non_blocking(monkeypatch, tmp_path):
    modes: list = []
    _msvcrt(monkeypatch, lambda fd, mode, n: modes.append(mode))
    _os(monkeypatch, True)
    with open(tmp_path / "x.lock", "a+") as fh:
        plat._lock(fh)
    assert modes == [2]  # LK_NBLCK, not the 10 s LK_LOCK


def test_lock_on_windows_raises_after_the_timeout(monkeypatch, tmp_path):
    _msvcrt(monkeypatch, _held)
    _os(monkeypatch, True)
    clock = _Clock()
    monkeypatch.setattr(plat, "time", clock)
    with open(tmp_path / "x.lock", "a+") as fh, pytest.raises(OSError):
        plat._lock(fh, timeout=0.1)
    assert 0.1 <= clock.now < 0.2  # gave up at ~its own timeout, not at the 10 s default


def test_lock_default_wait_outlasts_ordinary_contention(monkeypatch, tmp_path):
    """A holder that lets go after ~0.3 s must not cost the update (test_lead_wp8 lost 1 of 150)."""
    left = [30]

    def busy_then_free(fd, mode, n):
        left[0] -= 1
        if left[0] >= 0:
            raise OSError(36, "locked")
    _msvcrt(monkeypatch, busy_then_free)
    _os(monkeypatch, True)
    assert plat._LOCK_WAIT_S >= 10
    with open(tmp_path / "x.lock", "a+") as fh:
        plat._lock(fh)
    assert left[0] == -1


def test_locked_update_returns_the_current_data_when_the_lock_is_stuck(monkeypatch, tmp_path):
    _msvcrt(monkeypatch, _held)
    _os(monkeypatch, True)
    monkeypatch.setattr(plat, "_LOCK_WAIT_S", 0.2)
    rows: list = []
    from lib import hook_telemetry
    monkeypatch.setattr(hook_telemetry, "record", lambda *a, **k: rows.append((a, k)))
    target = tmp_path / "s.json"
    target.write_text(json.dumps({"n": 5}), encoding="utf-8")
    clock = _Clock()
    monkeypatch.setattr(plat, "time", clock)
    data, ok = plat.locked_update_ok(target, lambda d: {**d, "n": 6})
    assert 0.2 <= clock.now < 0.4  # waited _LOCK_WAIT_S, no longer
    assert data == {"n": 5} and ok is False
    assert rows == [(("platform", "locked_update_timeout"), {"path": "s.json"})]
    assert json.loads(target.read_text(encoding="utf-8")) == {"n": 5}
    assert plat.locked_update(target, lambda d: {"n": 7}) == {"n": 5}


def test_locked_update_reports_a_failed_write(monkeypatch, tmp_path):
    _os(monkeypatch, False)
    monkeypatch.setattr(plat, "_lock", lambda fh, timeout=1.0: None)  # fcntl does not exist on Windows
    assert plat.locked_update_ok(tmp_path / "s.json", lambda d: {"a": 1}) == ({"a": 1}, True)
    monkeypatch.setattr(plat, "atomic_write", lambda *a, **k: False)
    assert plat.locked_update_ok(tmp_path / "s2.json", lambda d: {"a": 1}) == ({"a": 1}, False)


@pytest.mark.skipif(not plat.IS_WINDOWS, reason="msvcrt byte-range locks")
def test_locked_update_gives_up_on_a_really_held_lock(monkeypatch, tmp_path):
    import msvcrt
    monkeypatch.setattr(plat, "_LOCK_WAIT_S", 0.3)
    target = tmp_path / "s.json"
    target.write_text(json.dumps({"n": 1}), encoding="utf-8")
    release, ready = threading.Event(), threading.Event()

    def hold():
        with open(str(target) + ".lock", "a+") as fh:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            ready.set()
            release.wait(10)
    th = threading.Thread(target=hold)
    th.start()
    ready.wait(5)
    clock = _Clock()
    monkeypatch.setattr(plat, "time", clock)  # the real lock is contended; only the waiting is simulated
    try:
        out = plat.locked_update(target, lambda d: {"n": 2})
        assert 0.3 <= clock.now < 0.5 and out == {"n": 1} and not release.is_set()  # gave up, holder still in
    finally:
        release.set()
        th.join()
