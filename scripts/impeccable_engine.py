#!/usr/bin/env python3
"""impeccable_engine.py — fetch the vendored Impeccable skill's engine at install time (2026-11-03).

The design act and the ui-quality-autorun hook run Impeccable's ``detect``; the hook only uses an engine
that is already cached and verified, so a fresh machine would stay silent until the first design run.
This script runs the vendored launcher once (``engine-probe``): the launcher downloads the engine pinned
in ``skills/impeccable/scripts/VERSION`` from the GitHub release and checks it against the vendored
``engine-checksums.txt`` before it writes the ``.verified`` stamp. Nothing else is installed.

  impeccable_engine.py            ensure: OK(cached) | INSTALLED | SKIP(<reason>) (exit 3 = SKIP)
  impeccable_engine.py --check    exit 0 when the verified engine is cached, else 1 (never downloads)
  impeccable_engine.py --dry-run  WOULD-FETCH when missing (never downloads)

Run by the installer (manifest post-step ``impeccable-engine``) and the daily self-heal.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import impeccable_engine as eng  # noqa: E402
from lib import platform as plat  # noqa: E402

TIMEOUT_S = 300  # the engine is ~21 MB


def ensure(dry: bool = False) -> tuple[int, str]:
    ver = eng.version()
    if not ver:
        return 3, "SKIP(impeccable skill not vendored)"
    if eng.cached_binary():
        return 0, f"OK(cached {ver})"
    if dry:
        return 0, f"WOULD-FETCH(engine {ver})"
    argv = eng.launcher_argv()
    if not argv:
        return 3, "SKIP(launcher missing)"
    cp = plat.run([*argv, "engine-probe"], timeout=TIMEOUT_S, stdin_devnull=True)
    if cp.returncode == 0 and eng.cached_binary():
        return 0, f"INSTALLED(engine {ver})"
    why = ((cp.stderr or cp.stdout or "").strip().splitlines() or [f"rc={cp.returncode}"])[-1][:160]
    return 3, f"SKIP(engine fetch failed: {why}; the first design run retries)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.check:
        ok = eng.cached_binary() is not None
        print(f"impeccable-engine: {'OK' if ok else 'MISSING'} ({eng.version() or 'no skill'})")
        return 0 if ok else 1
    rc, line = ensure(dry=a.dry_run)
    print(f"impeccable-engine: {line}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
