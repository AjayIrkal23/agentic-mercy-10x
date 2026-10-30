#!/usr/bin/env python3
"""session-ledger.py — L4 live-session ledger (SessionStart / SessionEnd exec link).

Modes:
  start   SessionStart: write state/live-sessions/<sid>.json; on `source: startup`
          print {"hookSpecificOutput": {"hookEventName": "SessionStart",
          "sessionTitle": "<repo> <YYYY-MM-DD>"}}, else {}.
  end     SessionEnd: unlink the entry (one syscall: the SessionEnd budget is 1.5 s
          shared); when the unlink fails, mark `ended` instead.

Contract (extra keys allowed, these are mandatory):
  state/live-sessions/<sid>.json  {"sid","pid","cwd","transcript","tmux","scope",
                                   "started","seen","ended":null,"restored":false}
  extra: boot_id, source, title, restored_at.

SessionEnd does not run on SIGKILL, so an entry whose pid is dead and `ended` is null
is a killed session: `dead_entries(max_age)` lists the ones young enough to restore and
`mark_restored(sid)` records a restore (scripts/restore_sessions.py imports this file by
path). A different boot_id means the pid belongs to an earlier boot, so it is dead.

Windows: a no-op (prints {}, touches no file); the restore path is POSIX/tmux only.
Fail-open: any error prints {} and exits 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import platform as plat  # noqa: E402

try:
    from lib import repo_context as rc  # noqa: E402
except Exception:  # noqa: BLE001
    rc = None

_SID_RE = re.compile(r"[^A-Za-z0-9._-]")
# Claude Code session ids are UUIDs (`--session-id` requires one): fixture and verifier ids never enter the ledger (O6).
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _now() -> int:
    return int(time.time())


def ledger_dir() -> Path:
    d = plat.state_dir() / "live-sessions"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def entry_path(sid) -> Path | None:
    safe = _SID_RE.sub("_", str(sid or ""))[:128]
    return ledger_dir() / f"{safe}.json" if safe else None


def read_entry(sid) -> dict | None:
    p = entry_path(sid)
    if p is None:
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def write_entry(d: dict) -> bool:
    p = entry_path(d.get("sid"))
    return bool(p) and plat.atomic_write(p, json.dumps(d, indent=1))


def _unlink(path: Path) -> None:
    os.unlink(path)


def current_boot_id() -> str | None:
    if plat.IS_WINDOWS:
        return None
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _is_claude(comm: str, cmdline0: str) -> bool:
    return comm == "claude" or Path(cmdline0).name == "claude" or "/claude/versions/" in cmdline0


def _proc_info(pid: int, root: Path) -> tuple:
    """(ppid, comm, cmdline0) from <root>/<pid>; ppid None when unreadable."""
    d = root / str(pid)
    try:
        stat = (d / "stat").read_text(encoding="utf-8")
        ppid = int(stat[stat.rindex(")") + 1:].split()[1])  # comm may hold spaces and ')'
    except (OSError, ValueError, IndexError):
        return None, "", ""
    try:
        comm = (d / "comm").read_text(encoding="utf-8").strip()
    except OSError:
        comm = ""
    try:
        cmd0 = (d / "cmdline").read_bytes().split(b"\0")[0].decode("utf-8", "replace")
    except OSError:
        cmd0 = ""
    return ppid, comm, cmd0


def _claude_pid(start_pid: int, proc_root: Path = Path("/proc"), hops: int = 8) -> int | None:
    """Pid of the claude process above `start_pid` (hook -> dispatch -> claude). No match
    within `hops`: the grandparent of `start_pid` when known, else None."""
    chain_fn = getattr(plat, "proc_chain", None)  # [pid, ppid, ...] (oom-sentinel)
    if callable(chain_fn):
        try:
            chain = chain_fn(start_pid, proc_root=proc_root)
            ancestors = [int(p) for p in (chain or [])[1:hops + 1]]
            if ancestors:
                for pid in ancestors:
                    _, comm, cmd0 = _proc_info(pid, proc_root)
                    if _is_claude(comm, cmd0):
                        return pid
                return ancestors[1] if len(ancestors) > 1 else None
        except Exception:  # noqa: BLE001 - fall through to the inline walk
            pass
    ancestors = []
    pid = start_pid
    for _ in range(hops):
        ppid, _c, _m = _proc_info(pid, proc_root)
        if not ppid or ppid <= 0:
            break
        ancestors.append(ppid)
        _, comm, cmd0 = _proc_info(ppid, proc_root)
        if _is_claude(comm, cmd0):
            return ppid
        pid = ppid
    return ancestors[1] if len(ancestors) > 1 else None


def _scope() -> str | None:
    fn = getattr(plat, "scope_of", None)
    if callable(fn):
        try:
            return fn(os.getpid())
        except Exception:  # noqa: BLE001
            return None
    if plat.IS_WINDOWS:
        return None
    try:
        lines = Path("/proc/self/cgroup").read_text(encoding="utf-8").strip().splitlines()
        seg = lines[-1].rsplit("/", 1)[-1] if lines else ""
        return seg if seg.endswith((".scope", ".service")) else None
    except OSError:
        return None


def _tmux() -> str | None:
    fn = getattr(plat, "tmux_pane", None)
    if callable(fn):
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return None
    return os.environ.get("TMUX_PANE") or None


def _title(cwd) -> str:
    name = ""
    if rc is not None:
        try:
            root = rc.git_root(cwd)
            name = root.name if root else ""
        except Exception:  # noqa: BLE001
            name = ""
    name = name or Path(str(cwd)).name or "session"
    return f"{name} {time.strftime('%Y-%m-%d')}"


def _entries():
    try:
        files = sorted(ledger_dir().glob("*.json"))
    except OSError:
        return
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("sid"):
            yield d


def classify(max_age_s: float, now=None) -> dict:
    """{eligible, stale, ended, live}: lists of entries, each sorted by `started`."""
    now = _now() if now is None else now
    boot = current_boot_id()
    out: dict = {"eligible": [], "stale": [], "ended": [], "live": []}
    for e in _entries():
        if e.get("ended") is not None:
            out["ended"].append(e)
            continue
        pid = e.get("pid")
        if not isinstance(pid, int) or isinstance(pid, bool):
            out["stale"].append(e)
            continue
        if e.get("boot_id") and boot and e["boot_id"] != boot:
            dead = True
        else:
            dead = not plat.pid_alive(pid)
        if not dead:
            out["live"].append(e)
        elif max(e.get("started") or 0, e.get("seen") or 0) >= now - max_age_s:
            out["eligible"].append(e)
        else:
            out["stale"].append(e)
    for v in out.values():
        v.sort(key=lambda e: e.get("started") or 0)
    return out


def dead_entries(max_age_s: float, now=None) -> list:
    return classify(max_age_s, now)["eligible"]


def mark_restored(sid) -> bool:
    p = entry_path(sid)
    if p is None or not p.exists():
        return False

    def fn(d: dict) -> dict:
        d["restored"] = True
        d["restored_at"] = _now()
        return d

    plat.locked_update(p, fn)
    return True


def mode_start(payload: dict) -> int:
    if plat.IS_WINDOWS:
        print("{}")
        return 0
    sid = payload.get("session_id")
    if not sid or entry_path(sid) is None:
        print("{}")
        return 0
    if os.environ.get("CLAUDE_HOOK_DOCTOR") or not _UUID_RE.match(str(sid)):
        print("{}")  # doctor replays and fixture ids (doctor-fixture, verify-*) never enter the ledger
        return 0
    source = payload.get("source") or "startup"
    cwd = payload.get("cwd") or os.getcwd()
    now = _now()
    new = {"sid": sid, "pid": _claude_pid(os.getpid()), "cwd": cwd,
           "transcript": payload.get("transcript_path"), "tmux": _tmux(), "scope": _scope(),
           "started": now, "seen": now, "ended": None, "restored": False,
           "boot_id": current_boot_id(), "source": source}
    old = read_entry(sid) if source != "startup" else None
    if old:
        for k in ("started", "restored", "restored_at", "title"):
            if k in old:
                new[k] = old[k]
    new.setdefault("title", _title(cwd))
    try:  # the mercy mod writes state/mercy-mod.active.d/<sid>.json and has no mkdir
        (plat.state_dir() / "mercy-mod.active.d").mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    write_entry(new)
    if source == "startup":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "sessionTitle": new["title"]}}))
    else:
        print("{}")
    return 0


def mode_end(payload: dict) -> int:
    if plat.IS_WINDOWS:
        print("{}")
        return 0
    p = entry_path(payload.get("session_id"))
    if p is not None:
        try:
            _unlink(p)
        except FileNotFoundError:
            pass
        except OSError:
            if p.exists():
                def fn(d: dict) -> dict:
                    d["ended"] = _now()
                    return d
                plat.locked_update(p, fn)
    print("{}")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    mode = argv[0] if argv else "start"
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("payload")
    except Exception:  # noqa: BLE001
        print("{}")
        return 0
    try:
        return mode_end(payload) if mode == "end" else mode_start(payload)
    except Exception:  # noqa: BLE001
        print("{}")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        print("{}")
        raise SystemExit(0)
