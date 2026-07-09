"""Shared refcounted start/stop for the graphify/jcodemunch systemd watch daemons.

One session_id = one ref. acquire() starts the daemon on the first ref for a
project; release() stops it once the last ref is gone. Used by
graphify-index-guard.py / jcodemunch-index-guard.py (SessionStart, acquire)
and watch-daemon-session-end.py (SessionEnd, release).

ponytail: refs aren't PID-validated, so a session that ends ungracefully
(kill -9, crashed terminal) without firing SessionEnd leaks its ref and the
daemon for that one project keeps running until the last graceful session
releases it or the machine reboots (services are no longer boot-enabled, so
a reboot always clears them). Upgrade to PID-liveness checks if leaks become
a recurring problem in practice.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REF_ROOT = Path(__file__).resolve().parent / ".state" / "watch-refs"


def _escape_path(path: Path) -> str:
    try:
        result = subprocess.run(
            ["systemd-escape", "--path", str(path)],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return str(path).strip("/").replace("/", "-")


def service_name(prefix: str, source_root: Path) -> str:
    return f"{prefix}-watch@{_escape_path(source_root)}.service"


def acquire(prefix: str, source_root: Path, session_id: str) -> str:
    """Register this session's interest and start the daemon if not already running."""
    svc = service_name(prefix, source_root)
    if session_id:
        ref_dir = REF_ROOT / svc
        try:
            ref_dir.mkdir(parents=True, exist_ok=True)
            (ref_dir / session_id).touch()
        except OSError:
            pass
    try:
        subprocess.run(
            ["systemctl", "--user", "start", svc],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        pass
    return svc


def release(prefix: str, source_root: Path, session_id: str) -> None:
    """Drop this session's interest; stop the daemon once no session still wants it."""
    if not session_id:
        return
    svc = service_name(prefix, source_root)
    ref_dir = REF_ROOT / svc
    try:
        (ref_dir / session_id).unlink(missing_ok=True)
    except OSError:
        pass
    try:
        remaining = ref_dir.is_dir() and any(ref_dir.iterdir())
    except OSError:
        remaining = True  # can't tell -> don't kill someone else's watcher
    if remaining:
        return
    try:
        subprocess.run(
            ["systemctl", "--user", "stop", svc],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        pass
    try:
        ref_dir.rmdir()
    except OSError:
        pass
