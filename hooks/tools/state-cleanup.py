#!/usr/bin/env python3
"""state-cleanup.py — session-start exec link (async): bounded retention purge.

Best-effort, never raises, never blocks a session. ONE retention table drives the
purge (``RETENTION``); this block is what ``state-cleanup.py --table`` prints, and a
test compares the two so they cannot drift. Paths are relative to ~/.claude;
``<dotstate>`` is hooks/.state (or CLAUDE_HOOK_DOTSTATE_DIR).

  family             where                   patterns                                                age  kind
  hook-fires         telemetry               hook-fires-*.jsonl, *.router-shadow.jsonl              14 d  files
  classification     state                   *.classification.json, *.router-manifest.json           1 d  files
  stack              state                   *.stack.json                                           14 d  files
  persist-dedup      state/persist-dedup     *.json                                                 14 d  files
  tmp-swap           state                   .tmp-*.swap                                             1 d  files
  dotstate           <dotstate>              *                                                       7 d  files
  taste-dials        <dotstate>/taste-dials  *                                                       7 d  files
  index-flush        <dotstate>/index        *.flush-*.txt                                           1 d  files
  telemetry-session  hooks/.telemetry        *.*.jsonl, *.suite-gate.json, *.suite-gate.json.lock   14 d  files
  session-bridge     state/session-bridge    *.json                                                  1 d  files
  resume-lock        state/resume-lock       *                                                       1 d  files
  mod-flag           state/mercy-mod.active.d *.json                                                  1 d  files
  mod-flag-legacy    state                   mercy-mod.active                                        1 d  files
  launch-caps        state/launch-caps       *.json                                                  1 d  files
  launch-settings    state                   launch-settings-*.json                                  1 d  files
  advisory-queue     state/advisory-queue    *.jsonl                                                 7 d  files
  ponytail-legacy    ponytail-modes          *                                                       7 d  ponytail
  live-sessions      state/live-sessions     *.json                                                  7 d  ledger
  teams              teams                   session-*                                              14 d  teams
  plugin-temp        plugins/cache           temp_git_*                                              1 d  dirs
  session-env        session-env             *                                                       1 d  empty-dirs
  learning           state/learning          */observations.jsonl                                   30 d  jsonl-rows

Kinds: files = files matching a pattern older than the age; dirs = whole dirs;
empty-dirs = empty dirs only; ponytail = files whose name is not a 64-hex sha256
(the plugin's legacy UUID keys); ledger = dead (pid gone or ``ended``) AND older
than the age, unreadable left alone; teams = dirs older than the age unless
``config.json``'s ``leadSessionId`` has a live ledger; jsonl-rows = rows whose
numeric ``ts`` (seconds) is older than the age are dropped (rows without one stay).

Special purges (predicates, not rows):
  test-session  test-named sessions (audit-*, ma-*, t<N>-*, t-iso-*, dryrun-*, isg-*,
                t-<32 hex>, fixture stack caches go/vite/wt-<8 hex>) in state/,
                telemetry/, <dotstate>, hooks/.telemetry                 > 1 d
  index-dead    <dotstate>/index/<key>.json whose repo_root is gone      > 1 d
  orphan-lock   *.json.lock / *.jsonl.lock whose data file is gone       > 1 d
  e2e-residue   any *e2e-* test residue file in the four dirs             now
  rotate        hooks/.telemetry/skill-effectiveness.jsonl, state/oomguard.events:
                > 2 MB → last 5,000 lines

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

# family, relative dir, glob patterns, max age days, kind
RETENTION = (
    ("hook-fires", "telemetry", ("hook-fires-*.jsonl", "*.router-shadow.jsonl"), 14, "files"),
    ("classification", "state", ("*.classification.json", "*.router-manifest.json"), 1, "files"),
    ("stack", "state", ("*.stack.json",), 14, "files"),
    ("persist-dedup", "state/persist-dedup", ("*.json",), 14, "files"),
    ("tmp-swap", "state", (".tmp-*.swap",), 1, "files"),
    ("dotstate", "<dotstate>", ("*",), 7, "files"),
    ("taste-dials", "<dotstate>/taste-dials", ("*",), 7, "files"),
    ("index-flush", "<dotstate>/index", ("*.flush-*.txt",), 1, "files"),
    ("telemetry-session", "hooks/.telemetry", ("*.*.jsonl", "*.suite-gate.json", "*.suite-gate.json.lock"), 14, "files"),
    ("session-bridge", "state/session-bridge", ("*.json",), 1, "files"),
    ("resume-lock", "state/resume-lock", ("*",), 1, "files"),
    ("mod-flag", "state/mercy-mod.active.d", ("*.json",), 1, "files"),
    ("mod-flag-legacy", "state", ("mercy-mod.active",), 1, "files"),
    ("launch-caps", "state/launch-caps", ("*.json",), 1, "files"),
    ("launch-settings", "state", ("launch-settings-*.json",), 1, "files"),
    ("advisory-queue", "state/advisory-queue", ("*.jsonl",), 7, "files"),
    ("ponytail-legacy", "ponytail-modes", ("*",), 7, "ponytail"),
    ("live-sessions", "state/live-sessions", ("*.json",), 7, "ledger"),
    ("teams", "teams", ("session-*",), 14, "teams"),
    ("plugin-temp", "plugins/cache", ("temp_git_*",), 1, "dirs"),
    ("session-env", "session-env", ("*",), 1, "empty-dirs"),
    ("learning", "state/learning", ("*/observations.jsonl",), 30, "jsonl-rows"),
)
ROTATE = ("hooks/.telemetry/skill-effectiveness.jsonl", "state/oomguard.events")
_SHA256_NAME = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[\w.-]+$")


def table_text() -> str:
    """The retention table as a fixed-width block (embedded verbatim in the docstring)."""
    rows = [f"  {'family':<18} {'where':<23} {'patterns':<54} {'age':>4}  kind"]
    for fam, rel, pats, days, kind in RETENTION:
        rows.append(f"  {fam:<18} {rel:<23} {', '.join(pats):<54} {str(days) + ' d':>4}  {kind}")
    return "\n".join(rows)


def _claude_dir() -> Path:
    if _plat is not None:
        return _plat.claude_dir()
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path("~/.claude").expanduser()


def _old(p: Path, max_age_s: float, now: float) -> bool:
    return now - p.stat().st_mtime > max_age_s


def _purge_files(directory: Path, patterns, max_age_s: float, now: float) -> int:
    removed = 0
    if not directory.is_dir():
        return 0
    for pat in patterns:
        for f in directory.glob(pat):
            try:
                if f.is_file() and _old(f, max_age_s, now):
                    f.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


def _purge_orphan_locks(directory: Path, max_age_s: float, now: float) -> int:
    """`<data>.json.lock` / `<data>.jsonl.lock` sidecars (platform.locked_update / append_line)
    whose data file is gone. A lock beside a live file, or a fixed lock such as
    `selfheal-daily.lock`, is never touched."""
    removed = 0
    if not directory.is_dir():
        return 0
    for f in [*directory.glob("*.json.lock"), *directory.glob("*.jsonl.lock")]:
        try:
            if not f.with_suffix("").exists() and _old(f, max_age_s, now):
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
            if not d.is_dir() or not _old(d, max_age_s, now):
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


def _purge_ponytail(directory: Path, patterns, max_age_s: float, now: float) -> int:
    """Legacy UUID-named mode files the ponytail plugin no longer reads (current keys are sha256)."""
    removed = 0
    if not directory.is_dir():
        return 0
    for pat in patterns:
        for f in directory.glob(pat):
            try:
                if f.is_file() and not _SHA256_NAME.match(f.name) and _old(f, max_age_s, now):
                    f.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


def _ledger_dead(f: Path) -> bool | None:
    """True dead, False alive, None unreadable/unknown. Needs lib.platform.pid_alive."""
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or _plat is None:
        return None
    if d.get("ended"):
        return True
    pid = d.get("pid")
    if isinstance(pid, int) and not isinstance(pid, bool):
        return not _plat.pid_alive(pid)
    return None


def _purge_dead_ledgers(directory: Path, patterns, max_age_s: float, now: float) -> int:
    removed = 0
    if _plat is None or not directory.is_dir():
        return 0
    for pat in patterns:
        for f in directory.glob(pat):
            try:
                if f.is_file() and _old(f, max_age_s, now) and _ledger_dead(f) is True:
                    f.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


def _purge_teams(directory: Path, patterns, max_age_s: float, now: float, base: Path) -> int:
    """Agent-team dirs older than the age, unless the lead session's ledger is live."""
    removed = 0
    if not directory.is_dir():
        return 0
    ledgers = base / "state" / "live-sessions"
    for pat in patterns:
        for d in directory.glob(pat):
            try:
                if not d.is_dir() or not _old(d, max_age_s, now):
                    continue
                try:
                    lead = json.loads((d / "config.json").read_text(encoding="utf-8")).get("leadSessionId")
                except (OSError, ValueError, AttributeError):
                    lead = None
                if isinstance(lead, str) and _SAFE_ID.match(lead):
                    led = ledgers / f"{lead}.json"
                    if led.is_file() and _ledger_dead(led) is False:
                        continue
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
            except OSError:
                pass
    return removed


def _trim_rows(path: Path, max_age_s: float, now: float) -> int:
    """Drop JSONL rows whose numeric ``ts`` is older than the age; rewrite (tmp + replace)
    only when something was dropped. Rows without a numeric ts stay. Returns rows dropped."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    except OSError:
        return 0
    keep, dropped, cutoff = [], 0, now - max_age_s
    for line in lines:
        try:
            ts = json.loads(line).get("ts")
        except (ValueError, AttributeError):
            ts = None
        if isinstance(ts, (int, float)) and not isinstance(ts, bool) and ts < cutoff:
            dropped += 1
            continue
        keep.append(line)
    if dropped:
        try:
            tmp = path.with_name(path.name + ".trim.tmp")
            tmp.write_text("".join(keep), encoding="utf-8", newline="")
            os.replace(tmp, path)
        except OSError:
            return 0
    return dropped


def _purge_rows(directory: Path, patterns, max_age_s: float, now: float) -> int:
    if not directory.is_dir():
        return 0
    return sum(_trim_rows(f, max_age_s, now) for pat in patterns for f in directory.glob(pat) if f.is_file())


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
            if not _old(f, max_age_s, now):
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


def _resolve(base: Path, dot: Path, rel: str) -> Path:
    if rel.startswith("<dotstate>"):
        return dot / rel[len("<dotstate>"):].lstrip("/")
    return base / rel


def _run_row(row, base: Path, dot: Path, now: float) -> int:
    fam, rel, pats, days, kind = row
    d, age = _resolve(base, dot, rel), days * _DAY
    if kind == "files":
        return _purge_files(d, pats, age, now)
    if kind in ("dirs", "empty-dirs"):
        return sum(_purge_dirs(d, p, age, now, empty_only=kind == "empty-dirs") for p in pats)
    if kind == "ponytail":
        return _purge_ponytail(d, pats, age, now)
    if kind == "ledger":
        return _purge_dead_ledgers(d, pats, age, now)
    if kind == "teams":
        return _purge_teams(d, pats, age, now, base)
    if kind == "jsonl-rows":
        return _purge_rows(d, pats, age, now)
    return 0


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
    for row in RETENTION:
        try:
            add(row[0], _run_row(row, base, dot, now))
        except Exception:  # noqa: BLE001 - one family never stops the others
            pass
    add("index-dead", _purge_dead_index_states(dot / "index", _DAY, now))
    for rel in ROTATE:
        _rotate(base / rel)
    for d in (base / "state", base / "state" / "advisory-queue", base / "state" / "live-sessions",
              base / "state" / "session-bridge", base / "telemetry", hooks / ".telemetry"):
        add("orphan-lock", _purge_orphan_locks(d, _DAY, now))
    for d in (base / "state", base / "telemetry", dot, hooks / ".telemetry"):
        add("e2e-residue", _purge_residue(d))
    _log_counts(base, counts, now)
    return counts


def main() -> int:
    if "--table" in sys.argv[1:]:
        print(table_text())
        return 0
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
