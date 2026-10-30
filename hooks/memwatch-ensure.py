#!/usr/bin/env python3
"""memwatch-ensure.py — SessionStart exec (async): make sure claude-memwatch.service runs.

active -> nothing; inactive with the unit file installed -> ``oomguard_setup.start_unit()``; unit file missing ->
``installer/oomguard_setup.ensure(False)`` under ``state/oomguard-ensure.lock``. Never spawns a scope, never
backgrounds anything, never names the unit manager itself (hooks/*.py grep gate in test_index_lifecycle.py): every
unit verb lives in installer/oomguard_setup.py. Ends when those calls return (< 2 s normally, 5 s cap per call).
Skips under a doctor dry-fire, the link-doctor probe, pytest (unless MEMWATCH_ENSURE_ALLOW_TEST=1), Windows and
hosts without a systemd user manager. Always prints ``{}`` and exits 0.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
_ROOT = _HOOKS.parent
for _p in (_HOOKS, _HOOKS / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib import platform as plat  # noqa: E402

TIMEOUT = 5.0


def _setup():
    """installer.oomguard_setup, imported lazily (a test seam: replace this attribute)."""
    if str(_ROOT / "installer") not in sys.path:
        sys.path.insert(0, str(_ROOT / "installer"))
    import oomguard_setup  # noqa: PLC0415
    return oomguard_setup


def ensure_fn(dry: bool):
    """installer/oomguard_setup.ensure (a test seam: replace the module attribute)."""
    return _setup().ensure(dry)


def _read_stdin() -> dict:
    try:
        d = json.loads(sys.stdin.read() or "{}")
        return d if isinstance(d, dict) else {}
    except (ValueError, OSError):
        return {}


def _done() -> int:
    print("{}")
    return 0


def main() -> int:
    try:
        payload = _read_stdin()
        if os.environ.get("CLAUDE_HOOK_DOCTOR") or payload.get("session_id") == "link-doctor":
            return _done()
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("MEMWATCH_ENSURE_ALLOW_TEST"):
            return _done()
        if plat.IS_WINDOWS or plat.systemd_user_bus() is None:
            return _done()
        ogs = _setup()
        if ogs.unit_state(timeout=TIMEOUT) != "inactive":
            return _done()  # active, or unknown (hung / missing manager tool): never install or start on it
        if ogs.unit_file().is_file():
            ogs.start_unit(timeout=TIMEOUT)
            return _done()
        from daily_lock import try_lock  # noqa: PLC0415
        with try_lock(plat.state_dir() / "oomguard-ensure.lock") as got:
            if got:
                ensure_fn(False)
    except Exception:  # noqa: BLE001 - SessionStart must never fail on the guard
        pass
    return _done()


if __name__ == "__main__":
    sys.exit(main())
