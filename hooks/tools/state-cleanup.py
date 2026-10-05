#!/usr/bin/env python3
"""state-cleanup.py — session-start exec link (async): bounded retention purge.

Best-effort, never raises, never blocks a session. Purges:
  telemetry/hook-fires-*.jsonl, telemetry/*.router-shadow.jsonl      > 14 d
  state/*.classification.json, state/*.router-manifest.json           > 24 h
  state/*.stack.json, state/persist-dedup/*.json                       > 14 d
  state/.tmp-*.swap  (orphaned atomic-write temps)                     > 1 d
  hooks/.state/*  (every extension, incl. .flag)                       > 7 d
  hooks/.state/taste-dials/*  (no writer left)                         > 7 d
  hooks/.state/index/*.flush-*.txt  (orphaned flush listings)          > 1 d
  hooks/.state/index/<key>.json whose repo_root is gone                > 1 d
  hooks/.telemetry/<session>.*.jsonl, <session>.suite-gate.json        > 14 d
  hooks/.telemetry/skill-effectiveness.jsonl   rotated when > 2 MB (keeps last 5,000 lines)
  plugins/cache/temp_git_*  dirs                                       > 1 d
  session-env/*  EMPTY dirs                                            > 1 d
  any *e2e-* file under state/, telemetry/, hooks/.state, hooks/.telemetry  (test residue)
  test-named sessions (audit-*, ma-{heavy,light}-{live,shadow}-*, t<N>-*, t-iso-*,
  dryrun-*, isg-*, t-<32 hex>) in those four dirs                       > 1 d
  state/{go,vite,wt}-<8 hex>.stack.json  (fixture-repo stack caches)    > 1 d
state/model-modes is never touched. Honors CLAUDE_HOOK_DOCTOR (no-op). Reads and
ignores stdin; prints {}. Each run that removed anything appends one JSON line
{ts, total, purged: {family: n}} to state/state-cleanup.log.
"""

from __future__ import annotations

import json
import os
import re
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


# Test residue names start a name segment with `e2e-` (t-e2e-…, x-e2e-1.json, e2e-repo).
# A bare `*e2e-*` glob also hit real session UUIDs (…-8e2e-5446…) and deleted their
# gate evidence at age 0 (Santa H1): `e2e-` after a hex digit is never residue.
_E2E_RESIDUE = re.compile(r"(?:^|[._-])e2e-")


def _purge_residue(directory: Path) -> int:
    removed = 0
    if not directory.is_dir():
        return 0
    for f in directory.glob("*e2e-*"):
        try:
            if f.is_file() and _E2E_RESIDUE.search(f.name):
                f.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def _purge_dead_index_states(index_dir: Path, max_age_s: float, now: float) -> int:
    """index-lifecycle state whose recorded repo_root no longer exists (removed
    worktrees, /tmp test repos). Unreadable or root-less files are left alone."""
    removed = 0
    if not index_dir.is_dir():
        return 0
    for f in index_dir.glob("*.json"):
        try:
            if now - f.stat().st_mtime <= max_age_s:
                continue
            root = json.loads(f.read_text(encoding="utf-8")).get("repo_root")
            if isinstance(root, str) and root and not os.path.isdir(root):
                f.unlink()
                removed += 1
        except (OSError, ValueError, AttributeError):
            pass
    return removed


def _rotate(path: Path) -> bool:
    """Keep only the last _ROTATE_KEEP_LINES lines once the file exceeds _ROTATE_BYTES.
    A file with no more lines than that is left alone: rewriting it unchanged cost a
    5 MB write per session start (audit J-04)."""
    try:
        if not path.is_file() or path.stat().st_size <= _ROTATE_BYTES:
            return False
        tail = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        if len(tail) <= _ROTATE_KEEP_LINES:
            return False
        tmp = path.with_name(path.name + ".rotate.tmp")
        tmp.write_text("".join(tail[-_ROTATE_KEEP_LINES:]), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


# Test sessions never carry a real session UUID (8-4-4-4-12 hex): their ids are named by the
# test that made them. Matched on the id before the first dot, so `<id>.router-manifest.json`,
# `<id>.pushed-skills.jsonl`, `<id>.suite-gate.json` all go; one day is longer than any test.
_TEST_NAMES = tuple((fam, re.compile(rx)) for fam, rx in (
    ("test-session:audit", r"^audit-"),
    ("test-session:ma", r"^ma-(?:heavy|light)-(?:live|shadow)-"),
    ("test-session:t11", r"^t\d+-"),
    ("test-session:t-iso", r"^t-iso-"),
    ("test-session:dryrun", r"^dryrun-"),
    ("test-session:isg", r"^isg-"),
    ("test-session:t-hex", r"^t-[0-9a-f]{32}$"),
    # stack caches of fixture repos (tmp dirs named go / vite / wt): `<name>-<sha1[:8]>.stack.json`
    ("stack:go", r"^go-[0-9a-f]{8}$"),
    ("stack:vite", r"^vite-[0-9a-f]{8}$"),
    ("stack:wt", r"^wt-[0-9a-f]{8}$"),
))
LOG_NAME = "state-cleanup.log"


def _purge_test_sessions(directory: Path, now: float, counts: dict) -> None:
    if not directory.is_dir():
        return
    for f in directory.iterdir():
        try:
            if not f.is_file() or now - f.stat().st_mtime <= _DAY:
                continue
            key = f.name.split(".", 1)[0]
            fam = next((n for n, rx in _TEST_NAMES if rx.match(key)), None)
            if fam:
                f.unlink()
                counts[fam] = counts.get(fam, 0) + 1
        except OSError:
            pass


def _log_counts(base: Path, counts: dict, now: float) -> None:
    """One JSON line per run that purged something: counts per family (observable cleanup)."""
    total = sum(counts.values())
    if not total:
        return
    try:
        log = base / "state" / LOG_NAME
        log.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": ts, "total": total, "purged": counts}, sort_keys=True) + "\n")
        _rotate(log)
    except OSError:
        pass


def run(base: Path, now: float | None = None, dotstate: Path | None = None) -> dict:
    """Purge aged state; returns {family: files removed} and logs it to state/state-cleanup.log."""
    now = time.time() if now is None else now
    hooks = base / "hooks"
    dot = dotstate or hooks / ".state"
    counts: dict = {}

    def add(family: str, n: int) -> None:
        if n:
            counts[family] = counts.get(family, 0) + n

    for d in (base / "state", base / "telemetry", dot, hooks / ".telemetry"):
        _purge_test_sessions(d, now, counts)
    add("hook-fires", _purge_files(base / "telemetry", ["hook-fires-*.jsonl", "*.router-shadow.jsonl"], 14 * _DAY, now))
    add("classification", _purge_files(base / "state", ["*.classification.json", "*.router-manifest.json"], _DAY, now))
    add("stack", _purge_files(base / "state", ["*.stack.json"], 14 * _DAY, now))
    add("persist-dedup", _purge_files(base / "state" / "persist-dedup", ["*.json"], 14 * _DAY, now))
    add("tmp-swap", _purge_files(base / "state", [".tmp-*.swap"], _DAY, now))
    add("dotstate", _purge_files(dot, ["*"], 7 * _DAY, now))
    add("taste-dials", _purge_files(dot / "taste-dials", ["*"], 7 * _DAY, now))
    add("index-flush", _purge_files(dot / "index", ["*.flush-*.txt"], _DAY, now))
    add("index-dead", _purge_dead_index_states(dot / "index", _DAY, now))
    add("telemetry-session", _purge_files(hooks / ".telemetry", ["*.*.jsonl", "*.suite-gate.json"], 14 * _DAY, now))
    _rotate(hooks / ".telemetry" / "skill-effectiveness.jsonl")
    add("plugin-temp", _purge_dirs(base / "plugins" / "cache", "temp_git_*", _DAY, now))
    add("session-env", _purge_dirs(base / "session-env", "*", _DAY, now, empty_only=True))
    for d in (base / "state", base / "telemetry", dot, hooks / ".telemetry"):
        add("e2e-residue", _purge_residue(d))
    _log_counts(base, counts, now)
    return counts


def main() -> int:
    try:
        try:
            sys.stdin.read()  # drain + ignore the hook payload
        except Exception:  # noqa: BLE001
            pass
        if not os.environ.get("CLAUDE_HOOK_DOCTOR"):
            dot = os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR")  # hooks/.state override
            run(_claude_dir(), dotstate=Path(dot) if dot else None)
    except Exception:  # noqa: BLE001 - cleanup must never brick session start
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
