#!/usr/bin/env python3
"""state-cleanup.py — session-start exec link (async): bounded retention purge.

Best-effort, never raises, never blocks a session. Purges:
  telemetry/hook-fires-*.jsonl, telemetry/*.router-shadow.jsonl      > 14 d
  state/*.classification.json, state/*.router-manifest.json           > 24 h
  hooks/.state/*  (every extension, incl. .flag)                       > 7 d
  hooks/.telemetry/<session>.*.jsonl                                   > 14 d
  hooks/.telemetry/skill-effectiveness.jsonl   rotated when > 2 MB (keeps last 5,000 lines)
  plugins/cache/temp_git_*  dirs                                       > 1 d
  session-env/*  EMPTY dirs                                            > 1 d
  any *e2e-* file under state/, telemetry/, hooks/.state, hooks/.telemetry  (test residue)
state/model-modes is never touched. Honors CLAUDE_HOOK_DOCTOR (no-op). Reads and
ignores stdin; prints {}.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    _plat = None  # type: ignore

_DAY = 86400.0
_ROTATE_BYTES = 2 * 1024 * 1024
_ROTATE_KEEP_LINES = 5000


def _claude_dir() -> Path:
    if _plat is not None:
        return _plat.claude_dir()
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path("~/.claude").expanduser()


def _purge_files(directory: Path, patterns, max_age_s: float, now: float) -> int:
    removed = 0
    if not directory.is_dir():
        return 0
    for pat in patterns:
        for f in directory.glob(pat):
            try:
                if f.is_file() and now - f.stat().st_mtime > max_age_s:
                    f.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


def _purge_dirs(directory: Path, pattern: str, max_age_s: float, now: float,
                *, empty_only: bool = False) -> int:
    removed = 0
    if not directory.is_dir():
        return 0
    for d in directory.glob(pattern):
        try:
            if not d.is_dir() or now - d.stat().st_mtime <= max_age_s:
                continue
            if empty_only:
                if any(d.iterdir()):
                    continue
                d.rmdir()
            else:
                shutil.rmtree(d, ignore_errors=True)
            removed += 1
        except OSError:
            pass
    return removed


def _rotate(path: Path) -> bool:
    """Keep only the last _ROTATE_KEEP_LINES lines once the file exceeds _ROTATE_BYTES."""
    try:
        if not path.is_file() or path.stat().st_size <= _ROTATE_BYTES:
            return False
        tail = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        tmp = path.with_name(path.name + ".rotate.tmp")
        tmp.write_text("".join(tail[-_ROTATE_KEEP_LINES:]), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def run(base: Path, now: float | None = None) -> None:
    now = time.time() if now is None else now
    hooks = base / "hooks"
    _purge_files(base / "telemetry", ["hook-fires-*.jsonl", "*.router-shadow.jsonl"], 14 * _DAY, now)
    _purge_files(base / "state", ["*.classification.json", "*.router-manifest.json"], _DAY, now)
    _purge_files(hooks / ".state", ["*"], 7 * _DAY, now)
    _purge_files(hooks / ".telemetry", ["*.*.jsonl"], 14 * _DAY, now)
    _rotate(hooks / ".telemetry" / "skill-effectiveness.jsonl")
    _purge_dirs(base / "plugins" / "cache", "temp_git_*", _DAY, now)
    _purge_dirs(base / "session-env", "*", _DAY, now, empty_only=True)
    for d in (base / "state", base / "telemetry", hooks / ".state", hooks / ".telemetry"):
        _purge_files(d, ["*e2e-*"], 0.0, now)


def main() -> int:
    try:
        try:
            sys.stdin.read()  # drain + ignore the hook payload
        except Exception:  # noqa: BLE001
            pass
        if not os.environ.get("CLAUDE_HOOK_DOCTOR"):
            run(_claude_dir())
    except Exception:  # noqa: BLE001 - cleanup must never brick session start
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
