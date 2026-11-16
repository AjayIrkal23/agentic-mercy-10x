#!/usr/bin/env python3
"""openmontage_engine.py — the pinned OpenMontage checkout behind the `openmontage` skill (2026-11-16).

OpenMontage (OpenMontageInc/OpenMontage, AGPL-3.0, ~2,300 files, its own Python venv and Remotion
node_modules) is an app the agent works inside, so it stays out of this repo: a shallow checkout of PIN
at ``${OPENMONTAGE_HOME:-~/.local/share/openmontage}`` (OpenMontage keeps its own clip cache in
~/.openmontage, hence not there), then its own ``make setup`` once (.venv, requirements.txt,
remotion-composer npm install, piper-tts, .env from .env.example). A ``.setup-ok`` stamp holds the pin
that set up cleanly. A checkout with local edits to tracked files is never reset.

  openmontage_engine.py            ensure: OK(<sha>) | INSTALLED(<sha>) | SKIP(<reason>) (exit 3 = SKIP)
  openmontage_engine.py --check    exit 0 when the checkout is at PIN and set up (never fetches)
  openmontage_engine.py --dry-run  WOULD-INSTALL when missing (never fetches)
  openmontage_engine.py --path     print the checkout path

Run by the installer (manifest post-step ``openmontage``) and the daily self-heal.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import platform as plat  # noqa: E402

REPO = "https://github.com/OpenMontageInc/OpenMontage.git"
PIN = "fecb9a1e3cc23ef84de30b272059457a427f16f8"  # 2026-11-08, reviewed 2026-11-16
STAMP = ".setup-ok"
SETUP_TIMEOUT_S = 1500  # pip requirements + Remotion npm install on a cold cache


def home() -> Path:
    return Path(os.environ.get("OPENMONTAGE_HOME") or Path.home() / ".local" / "share" / "openmontage")


def _git(*args: str, cwd: Path, timeout: float = 300):
    return plat.run(["git", *args], cwd=cwd, timeout=timeout, stdin_devnull=True)


def head(path: Path) -> str:
    if not (path / ".git").is_dir():
        return ""
    cp = _git("rev-parse", "HEAD", cwd=path, timeout=30)
    return (cp.stdout or "").strip() if cp.returncode == 0 else ""


def ready(path: Path | None = None) -> bool:
    """Checkout at PIN and ``make setup`` finished for it."""
    path = path or home()
    try:
        stamped = (path / STAMP).read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return stamped == PIN and head(path) == PIN


def _last(cp) -> str:
    lines = ((cp.stderr or "") + "\n" + (cp.stdout or "")).strip().splitlines()
    return (lines[-1] if lines else f"rc={cp.returncode}")[:160]


def _dirty(path: Path) -> list[str]:
    """Tracked files with local edits (git diff --name-only)."""
    cp = _git("diff", "--name-only", cwd=path, timeout=60)
    return (cp.stdout or "").splitlines() if cp.returncode == 0 else []


def _checkout(path: Path) -> str | None:
    """Put ``path`` at PIN; returns a SKIP reason or None."""
    if path.exists() and not (path / ".git").is_dir():
        return f"{path} exists and is not a git checkout"
    if not path.exists():
        path.mkdir(parents=True)
        for args in (("init", "-q"), ("remote", "add", "origin", REPO)):
            if _git(*args, cwd=path).returncode:
                return f"git {args[0]} failed"
    if head(path) == PIN:
        return None
    dirty = _git("status", "--porcelain", "--untracked-files=no", cwd=path, timeout=60)
    if (dirty.stdout or "").strip():
        return f"{path} has local edits to tracked files; left as is"
    cp = _git("fetch", "-q", "--depth", "1", "origin", PIN, cwd=path, timeout=600)
    if cp.returncode:
        return f"fetch failed: {_last(cp)}"
    cp = _git("checkout", "-q", "--detach", PIN, cwd=path)
    return f"checkout failed: {_last(cp)}" if cp.returncode else None


def ensure(dry: bool = False) -> tuple[int, str]:
    path = home()
    if ready(path):
        return 0, f"OK({PIN[:12]})"
    if dry:
        return 0, f"WOULD-INSTALL({PIN[:12]} -> {path})"
    missing = [t for t in ("git", "make", "npm") if not shutil.which(t)]
    if missing:
        return 3, f"SKIP(needs {', '.join(missing)}; on Windows run OpenMontage under WSL)"
    why = _checkout(path)
    if why:
        return 3, f"SKIP({why})"
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "CONDA_PREFIX")}  # its own .venv
    before = set(_dirty(path))
    cp = plat.run(["make", "setup"], cwd=path, env=env, timeout=SETUP_TIMEOUT_S, stdin_devnull=True)
    if cp.returncode:
        return 3, f"SKIP(make setup failed: {_last(cp)}; the daily self-heal retries)"
    # npm install rewrites remotion-composer/package-lock.json; left dirty, the next pin bump would SKIP
    # forever as "local edits". Restore only what setup itself touched.
    touched = [f for f in _dirty(path) if f not in before]
    if touched:
        _git("checkout", "-q", "--", *touched, cwd=path, timeout=60)
    (path / STAMP).write_text(PIN + "\n", encoding="utf-8")
    return 0, f"INSTALLED({PIN[:12]})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[1])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--path", action="store_true")
    a = ap.parse_args(argv)
    if a.path:
        print(home())
        return 0
    if a.check:
        ok = ready()
        print(f"openmontage: {'OK' if ok else 'MISSING'} ({home()})")
        return 0 if ok else 1
    rc, line = ensure(dry=a.dry_run)
    print(f"openmontage: {line}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
