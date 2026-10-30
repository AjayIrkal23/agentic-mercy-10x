#!/usr/bin/env python3
"""restore_sessions.py — bring killed Claude Code sessions back, gated (MERGE-PLAN 1.3 L4).

Encodes the manual runbook from the memory notes `restore-sessions-after-crash` and
`oom-kills-terminal-scope`: one tmux session `claude`, one window per session,
`claude --resume <sid>` with the harness and lean-ctx env stripped, and a stagger between
launches so the restored sessions do not all build their MCP servers at once.

Candidates come from the session ledger (hooks/session-ledger.py): an entry whose pid is
dead (or from an earlier boot) and whose `ended` is null is a killed session; it is
eligible while `max(started, seen)` is younger than --max-age.

Storm guards, all on every run:
  * restore flag   --flag-file, else ~/.claude/oomguard.local.json `restore_enabled`
                   (absent = on); off -> stopped_reason "flag_off"
  * memory tier    state/mem-pressure.json re-read before EVERY launch; warn/crit stops
                   the run ("tier <level> after <n>"); missing or stale > 30 s = ok
  * caps           --max per run, the same number per rolling hour (state/restore.cursor)
  * stagger        --per-window launches, then sleep --stagger seconds
  * locks          state/restore.lock (one run at a time) and state/resume-lock/<sid>
                   (shared with the mod's resume-after-limit path); stale > 600 s retaken
Contract: ledger-matched, young, tier ok, --per-window per window, at most --max an hour.

Called by `claude-restore.service` (`--only-if-ok --max-age 7200 --max 6 --per-window 2`)
and by memwatch after a ledger-matched kill. Every run then also resumes sessions that stopped
on a usage limit (state/<sid>.stop-failure.json) unless the mod owns that resume (a fresh
state/mercy-mod.active.d/<sid>.json) or the ledger says the session is still alive; `--resume-after-limit` runs that resume pass alone.
The tmux server is born under `systemd-run --user --scope` when the user bus exists, so it
outlives the caller's cgroup. Each launch appends a {"kind": "restore"} row to
state/oomguard.events.
Windows: unsupported (tmux), reported as stopped_reason "unsupported".
Exit 0 always; prints one JSON summary on stdout.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
from lib import platform as plat  # noqa: E402

_spec = importlib.util.spec_from_file_location("session_ledger", ROOT / "hooks" / "session-ledger.py")
_sl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sl)

ENV_STRIP = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT", "CLAUDE_CONFIG_DIR_SESSION",
             "LEAN_CTX_AGENT", "BASH_ENV", "MCP_TIMEOUT", "NoDefaultCurrentDirectoryInExePath",
             "MERCY_MOD_SESSION", "MERCY_MOD_LOADED", "MERCY_MOD_OWNED", "MERCY_MOD_BEAT", "TMUX", "TMUX_PANE")
ENV_STRIP_PREFIXES = ("CLAUDE_CODE_", "LEAN_CTX_", "CLAUDE_WORKBENCH_")  # subprocess env only
CONTINUE_PROMPT = ("Session restored automatically after a crash or OOM kill. Background tasks, agents and "
                   "workflows from before are gone. Check real state first (git status, files on disk), "
                   "then continue the last step.")
LIMIT_PROMPT = "continue"
LOCK_STALE_S = 600
TIER_STALE_S = 30
HOUR_S = 3600
MOD_FRESH_S = 60
_TIERS = ("ok", "warn", "crit")
# Claude Code session ids are UUIDs; `claude --resume` of anything else cannot resume (fixture / verifier ids, O6).
_SID_OK = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _now() -> float:
    return time.time()


def _sleep(s: float) -> None:
    time.sleep(s)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Restore killed Claude Code sessions into tmux, gated.")
    p.add_argument("--dry-run", action="store_true", help="plan only; write nothing, launch nothing")
    p.add_argument("--max", type=int, default=6, help="launches per run and per rolling hour (6)")
    p.add_argument("--max-age", type=int, default=7200, help="eligible while started/seen is younger (s)")
    p.add_argument("--per-window", type=int, default=2, help="launches before each stagger sleep (2)")
    p.add_argument("--stagger", type=float, default=15, help="seconds between launch windows (15)")
    p.add_argument("--only-if-ok", action="store_true",
                   help="launch only at memory tier ok (always enforced; documents the unit's intent)")
    p.add_argument("--tmux-session", default="claude", help="tmux session name (claude)")
    p.add_argument("--resume-after-limit", action="store_true",
                   help="resume sessions stopped on a usage limit (state/<sid>.stop-failure.json)")
    p.add_argument("--state-dir", help="state dir (overrides CLAUDE_HOOK_STATE_DIR)")
    p.add_argument("--flag-file", help="JSON with restore_enabled (default ~/.claude/oomguard.local.json)")
    p.add_argument("--claude-bin", help="claude binary (default ~/.claude/bin/claude, else claude on PATH)")
    return p


def _read_json(path: Path):
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def restore_enabled(flag_file) -> bool:
    if flag_file:
        d = _read_json(Path(flag_file))
        return True if d is None else bool(d.get("restore_enabled", True))
    try:
        from lib import oomguard_config  # oom-sentinel; optional
        fn = getattr(oomguard_config, "restore_enabled", None)
        if callable(fn):
            return bool(fn())
    except Exception:  # noqa: BLE001
        pass
    d = _read_json(plat.claude_dir() / "oomguard.local.json")
    return True if d is None else bool(d.get("restore_enabled", True))


def read_tier(state: Path) -> str:
    d = _read_json(state / "mem-pressure.json")
    if not d or d.get("level") not in _TIERS:
        return "ok"
    try:
        if _now() - float(d.get("ts", 0)) > TIER_STALE_S:
            return "ok"
    except (TypeError, ValueError):
        return "ok"
    return d["level"]


def take_lock(path: Path, owner: str) -> bool:
    """O_EXCL lock file {owner, pid, ts}; a stale one (older than LOCK_STALE_S, or for
    restore.lock a dead pid) is removed and retaken once."""
    for attempt in range(2):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if attempt:
                return False
            d = _read_json(path) or {}
            try:
                old = _now() - float(d.get("ts", 0)) > LOCK_STALE_S
            except (TypeError, ValueError):
                old = True
            pid = d.get("pid")
            dead = path.name == "restore.lock" and not (isinstance(pid, int) and plat.pid_alive(pid))
            if not (old or dead):
                return False
            try:
                path.unlink()
            except OSError:
                return False
            continue
        except OSError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"owner": owner, "pid": os.getpid(), "ts": int(_now())}))
        return True
    return False


def classify_ledger(max_age: int) -> dict:
    return _sl.classify(max_age, now=_now())


def claude_bin(override) -> str:
    if override:
        return str(override)
    wrapper = plat.claude_dir() / "bin" / "claude"
    return str(wrapper) if wrapper.is_file() and os.access(wrapper, os.X_OK) else "claude"


def pane_command(entry: dict, prompt: str, bin_: str) -> str:
    argv = ["env"]
    for v in ENV_STRIP:
        argv += ["-u", v]
    # ${SHELL:-sh} stays unquoted, so it goes after shlex.join
    return shlex.join(argv + [bin_, "--resume", entry["sid"], prompt]) + "; exec ${SHELL:-sh} -i"


def clean_env() -> dict:
    return {k: v for k, v in os.environ.items()
            if k not in ENV_STRIP and not k.startswith(ENV_STRIP_PREFIXES)}


def _scope_prefix() -> list:
    """systemd-run --scope argv for the tmux server's birth, so it lives in its own cgroup and not in
    the caller's (a oneshot unit's control group dies with the unit; memwatch has MemoryMax). [] on
    Windows, without systemd-run, or without the user bus (same check as index-lifecycle._scoped)."""
    bus = Path(os.environ.get("XDG_RUNTIME_DIR", "/nonexistent")) / "bus"
    if plat.IS_WINDOWS or not shutil.which("systemd-run") or not bus.exists():
        return []
    return ["systemd-run", "--user", "--scope", "--quiet", "--collect",
            "--unit", f"claude-tmux-{int(_now())}-{os.getpid()}"]


def tmux(args: list, env: dict, *, scoped: bool = False):
    pre = _scope_prefix() if scoped else []
    return plat.run(pre + ["tmux"] + list(args), timeout=10, env=env)


def _cwd(entry: dict) -> str:
    cwd = entry.get("cwd")
    return cwd if cwd and Path(cwd).is_dir() else str(Path.home())


def _window_name(entry: dict) -> str:
    return str(entry.get("title") or entry["sid"])[:20].replace(" ", "-")


def ensure_session(name: str, first_entry: dict, prompt: str, bin_: str, env: dict):
    """True when the session exists; "created" when it was created with first_entry's
    window (the caller must not open a second window for it); False on failure."""
    if tmux(["has-session", "-t", "=" + name], env).returncode == 0:  # "=": exact name, no prefix match
        return True
    cp = tmux(["new-session", "-d", "-s", name, "-c", _cwd(first_entry), "-n", _window_name(first_entry),
               pane_command(first_entry, prompt, bin_)], env, scoped=True)  # only here is a server born
    return "created" if cp.returncode == 0 else False


def launch(entry: dict, prompt: str, args, bin_: str, env: dict) -> bool:
    cp = tmux(["new-window", "-t", f"={args.tmux_session}:", "-n", _window_name(entry), "-c", _cwd(entry),
               pane_command(entry, prompt, bin_)], env)
    return cp.returncode == 0


def _prune(launches, now: float) -> list:
    out = []
    for t in launches or []:
        try:
            if float(t) >= now - HOUR_S:
                out.append(t)
        except (TypeError, ValueError):
            continue
    return out


def record_launch(state: Path) -> None:
    now = _now()

    def fn(d: dict) -> dict:
        d["launches"] = _prune(d.get("launches"), now) + [int(now)]
        return d

    plat.locked_update(state / "restore.cursor", fn)


def hourly_count(state: Path) -> int:
    d = _read_json(state / "restore.cursor") or {}
    return len(_prune(d.get("launches"), _now()))


def plan_entry(sid, action: str, reason: str) -> dict:
    return {"sid": sid, "action": action, "reason": reason}


class _Launcher:
    """One tmux session per run: the first launch makes sure it exists."""

    def __init__(self, args, env: dict, bin_: str):
        self.args, self.env, self.bin, self.ready = args, env, bin_, False

    def __call__(self, entry: dict, prompt: str) -> bool:
        if not self.ready:
            created = ensure_session(self.args.tmux_session, entry, prompt, self.bin, self.env)
            if not created:
                return False
            self.ready = True
            if created == "created":
                return True
        return launch(entry, prompt, self.args, self.bin, self.env)


def _gate(args, out: dict, state: Path, planned: int) -> bool:
    """False (and stopped_reason set) when the caps or the memory tier say stop."""
    if out["launched"] + planned >= args.max:
        out["stopped_reason"] = f"max {args.max}"
        return False
    if hourly_count(state) + planned >= args.max:
        out["stopped_reason"] = f"hourly cap {args.max}"
        return False
    level = read_tier(state)
    if level != "ok":
        out["stopped_reason"] = f"tier {level} after {out['launched']}"
        return False
    return True


def _restore_event(sid: str, ok: bool) -> None:
    """One {"kind": "restore"} row in state/oomguard.events (read by session_notices.memwatch_line)."""
    ev = {"kind": "restore", "sid": sid, "ok": bool(ok), "ts": round(_now(), 3)}
    try:
        from lib import memwatch_state as mws
        if mws.append_event(ev):
            return
    except Exception:  # noqa: BLE001
        pass
    try:
        plat.append_line(plat.state_dir() / "oomguard.events", (json.dumps(ev) + "\n").encode("utf-8"))
    except Exception:  # noqa: BLE001
        pass


def _ledger_live(entry: dict) -> bool:
    """The ledger's own liveness rule (session-ledger.classify): not ended, same boot, pid alive."""
    pid = entry.get("pid")
    if entry.get("ended") is not None or not isinstance(pid, int) or isinstance(pid, bool):
        return False
    boot = _sl.current_boot_id()
    if entry.get("boot_id") and boot and entry["boot_id"] != boot:
        return False
    return plat.pid_alive(pid)


def _launch_one(e: dict, prompt: str, out: dict, state: Path, launcher) -> bool:
    sid = e["sid"]
    if not take_lock(state / "resume-lock" / sid, "python"):
        out["skipped"]["locked"] += 1
        out["plan"].append(plan_entry(sid, "skip", "resume lock held"))
        return False
    ok = launcher(e, prompt)
    _restore_event(sid, ok)
    note ="cwd missing" if not (e.get("cwd") and Path(e["cwd"]).is_dir()) else ""
    out["plan"].append(plan_entry(sid, "launch" if ok else "failed", note or ("ok" if ok else "tmux error")))
    if ok:
        out["launched"] += 1
        _sl.mark_restored(sid)
        record_launch(state)
    return ok


def _restore(args, out: dict, state: Path) -> dict:
    groups = classify_ledger(args.max_age)
    out["skipped"]["stale"] = len(groups["stale"])
    out["skipped"]["ended"] = len(groups["ended"])
    out["plan"] += [plan_entry(e["sid"], "skip", "stale") for e in groups["stale"]]
    out["plan"] += [plan_entry(e["sid"], "skip", "ended") for e in groups["ended"]]
    launcher = _Launcher(args, clean_env(), claude_bin(args.claude_bin))
    eligible = [e for e in groups["eligible"]]
    planned = in_window = 0
    for i, e in enumerate(eligible):
        sid = str(e.get("sid") or "")
        if not _SID_OK.match(sid):
            out["plan"].append(plan_entry(sid, "skip", "bad sid"))
            continue
        if e.get("restored") and float(e.get("restored_at") or 0) > float(e.get("seen") or 0):
            # the resume never reached SessionStart (it refreshes `seen`): a retry fails the same way
            out["plan"].append(plan_entry(sid, "skip", "restore failed"))
            continue
        if not _gate(args, out, state, planned):
            break
        if args.dry_run:
            planned += 1
            out["plan"].append(plan_entry(sid, "launch", "dry-run"))
            continue
        if _launch_one(e, CONTINUE_PROMPT, out, state, launcher):
            in_window += 1
        if in_window >= args.per_window and i < len(eligible) - 1:
            _sleep(args.stagger)
            in_window = 0
    return out


def _safe(s) -> str:
    """A session id as a file name, the same rule as hooks/lib/session_notices._safe."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))[:80]


def _mod_owns(state: Path, sid: str) -> bool:
    p = state / "mercy-mod.active.d" / f"{_safe(sid)}.json"
    d = _read_json(p)
    if not d or d.get("sid") != sid:
        return False
    try:
        if "ts" in d:
            return _now() - float(d["ts"]) < MOD_FRESH_S
        return time.time() - p.stat().st_mtime < MOD_FRESH_S
    except (OSError, TypeError, ValueError):
        return False


def _resume_after_limit(args, out: dict, state: Path) -> dict:
    launcher = _Launcher(args, clean_env(), claude_bin(args.claude_bin))
    planned = 0
    for f in sorted(state.glob("*.stop-failure.json")):
        d = _read_json(f) or {}
        sid = str(d.get("sid") or f.name[: -len(".stop-failure.json")])
        if not _SID_OK.match(sid):
            out["plan"].append(plan_entry(sid, "skip", "bad sid"))
            continue
        if _mod_owns(state, sid):
            out["skipped"]["locked"] += 1
            out["plan"].append(plan_entry(sid, "skip", "mod owns resume"))
            continue
        entry = _sl.read_entry(sid) or {"sid": sid}
        entry["sid"] = sid
        if _ledger_live(entry):  # still running: resuming it would open a second copy
            out["plan"].append(plan_entry(sid, "skip", "live"))
            continue
        if not _gate(args, out, state, planned):
            break
        if args.dry_run:
            planned += 1
            out["plan"].append(plan_entry(sid, "launch", "dry-run"))
            continue
        if _launch_one(entry, LIMIT_PROMPT, out, state, launcher):
            try:
                f.unlink()
            except OSError:
                pass
    return out


def run(args) -> dict:
    out = {"launched": 0, "skipped": {"stale": 0, "ended": 0, "locked": 0, "flag_off": 0},
           "stopped_reason": None, "dry_run": bool(args.dry_run), "plan": [], "tmux_session": args.tmux_session}
    if not restore_enabled(args.flag_file):
        out["skipped"]["flag_off"] = 1
        out["stopped_reason"] = "flag_off"
        return out
    if plat.IS_WINDOWS:
        out["stopped_reason"] = "unsupported"
        return out
    if not args.dry_run and not shutil.which("tmux"):  # a dry run never calls tmux
        out["stopped_reason"] = "no tmux"
        return out
    state = plat.state_dir()
    lock = state / "restore.lock"
    if not args.dry_run and not take_lock(lock, "restore"):
        out["stopped_reason"] = "locked"
        return out
    try:
        if args.resume_after_limit:  # resume pass only (the mod and the tests)
            return _resume_after_limit(args, out, state)
        _restore(args, out, state)
        if out["stopped_reason"]:  # a cap or the tier stopped the run: the resume pass would too
            return out
        return _resume_after_limit(args, out, state)  # shares `out`, so the caps hold across both passes
    finally:
        if not args.dry_run:
            try:
                lock.unlink()
            except OSError:
                pass


def main(argv=None) -> int:
    out = {"launched": 0, "skipped": {"stale": 0, "ended": 0, "locked": 0, "flag_off": 0},
           "stopped_reason": None, "dry_run": False, "plan": []}
    try:
        args = build_parser().parse_args(argv)
        out["dry_run"] = bool(args.dry_run)
        if args.state_dir:
            os.environ["CLAUDE_HOOK_STATE_DIR"] = str(Path(args.state_dir).resolve())
        out = run(args)
    except SystemExit as exc:  # --help or a bad flag: argparse already printed
        if exc.code in (0, None):
            return 0
        out["stopped_reason"] = "error: usage"
    except Exception as exc:  # noqa: BLE001
        out["stopped_reason"] = f"error: {type(exc).__name__}"
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
