#!/usr/bin/env python3
"""memwatch.py — the OOM / memory-pressure sentinel (claude-memwatch.service). Stdlib only.

Every interval: probe /proc, decide the tier with hysteresis, write state/mem-pressure.json, append
tier/kill/shed events to state/oomguard.events, run the kill ladder, follow two journal readers for
kernel/oomd/user-manager kills, announce once per tier change (`notify-send`; a live mod toasts in-pane
as well), nudge restore after a ledger-matched kill. ``--once`` does one pass and exits (tests,
acceptance); ``--dry-run`` signals nothing. A ``--proc-root`` other than /proc is a fixture tree: its
pids are not this machine's, so no signal, systemctl, notification or restore spawn is ever sent for
it unless a test passes its own seam; ``--journal-cmd`` replays history, so it raises no desktop toast.
Windows: prints ``unsupported``, writes that state, exits 0.
Design and runbook: docs/OOM-GUARD.md.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from lib import memwatch_state as mws  # noqa: E402
from lib import oomguard_config as ogc  # noqa: E402
from lib import platform as plat  # noqa: E402

try:
    from lib import hook_telemetry as _tele
except Exception:  # noqa: BLE001
    _tele = None

_ROOT = _HOOKS.parent
CONFIG_PATH = _HOOKS / "memwatch.config.json"
JOURNAL_CMD_TIMEOUT = 10.0
RANK = {"ok": 0, "warn": 1, "crit": 2}
LOWER = {"crit": "warn", "warn": "ok"}

# Fallbacks when memwatch.config.json is missing; identical to the shipped file.
VICTIM_COMMS = ["Isolated Web Co", "Web Content", "WebExtensions", "WebKitWebProcess", "WebKitNetworkProcess"]
BROWSER_PARENTS = ["firefox", "firefox-bin", "chrome", "chromium", "chromium-browser", "brave", "electron", "code",
                   "msedge"]
BUILD_RE = r"(^|/)(tsserver|tsc|vitest|jest|esbuild|vite|webpack|cargo|rustc|gradle|gopls)(\.m?js|\.cjs)?(\s|$)"
CHILD_TYPE_RE = re.compile(r"--type=(renderer|gpu-process|utility)\b")
OWN_SCOPE_RE = re.compile(r"^claude(-safe)?-[^/]*\.scope$")  # scopes bin/claude made; stage 3 stops only these
PROTECTED = ["claude", "tmux", "tmux: server", "gnome-shell", "mutter", "Xwayland", "pipewire", "wireplumber",
             "ptyxis", "ptyxis-agent", "gnome-terminal-", "kitty", "alacritty", "sshd", "systemd", "(sd-pam)",
             "dbus-daemon", "dbus-broker", "ollama"]
DEFAULT_CFG = {
    "interval_s": 5,
    "tiers": {"warn": {"mem_available_mb": 8192, "psi": 10, "swap_free_pct": 5, "swap_mem_available_mb": 12288},
              "crit": {"mem_available_mb": 3072, "psi": 25}},
    "hysteresis": {"margin_mb": 1024, "holdoff_s": 60},
    "top_n": 8,
    "state_stale_s": 30,
    "notify": {"quiet_hours": "", "mod_flag_fresh_s": 60},
    "kill_policy": {"enabled": True, "stage_holdoff_s": 20, "emergency_mb": 1500, "idle_min": 10,
                    "victim_interval_s": 10, "stage3_after_s": 40, "victims": VICTIM_COMMS,
                    "victim_cmd_re": BUILD_RE, "browser_parents": BROWSER_PARENTS, "protected": PROTECTED},
    "stuck": {"scan_s": 60, "pending_bash_s": 1800},
    "restore": {"ok_hold_s": 60, "lock_stale_s": 600,
                "args": ["--only-if-ok", "--max-age", "7200", "--max", "6", "--per-window", "2"]},
}


def _err(msg: str) -> None:
    try:
        print(f"memwatch: {msg}", file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001
        pass


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        elif not str(k).startswith("_"):
            out[k] = v
    return out


def load_config(path=None) -> dict:
    """DEFAULT_CFG deep-updated by the file; a missing or bad file gives the defaults."""
    try:
        data = json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
        return _merge(DEFAULT_CFG, data) if isinstance(data, dict) else copy.deepcopy(DEFAULT_CFG)
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULT_CFG)


# --------------------------------------------------------------------------- #
# Sampling
# --------------------------------------------------------------------------- #
def read_procs(proc_root="/proc") -> list[dict]:
    """One row per user process with RSS: pid, name, ppid, rss_mb, unit, uid. Reads ``status`` and
    ``cgroup`` only (cmdline is read lazily for ladder candidates)."""
    out = []
    try:
        entries = [e.name for e in os.scandir(proc_root) if e.name.isdigit()]
    except OSError:
        return out
    for name in entries:
        pid = int(name)
        fields = {}
        try:
            with open(os.path.join(proc_root, name, "status"), encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    key, _, val = line.partition(":")
                    if key in ("Name", "PPid", "VmRSS", "Uid"):
                        fields[key] = val.strip()
        except OSError:
            continue
        if "VmRSS" not in fields:
            continue  # kernel thread
        try:
            rss_mb = int(fields["VmRSS"].split()[0]) // 1024
            ppid = int(fields.get("PPid", "0").split()[0] or 0)
            uid = int(fields.get("Uid", "-1").split()[0])
        except (ValueError, IndexError):
            continue
        out.append({"pid": pid, "name": fields.get("Name", "?"), "ppid": ppid, "rss_mb": rss_mb,
                    "unit": plat.cgroup_of(pid, proc_root), "uid": uid})
    return out


def cmdline_of(pid: int, proc_root="/proc") -> str:
    """The pid's command line, NULs as spaces; "" when unreadable."""
    try:
        with open(os.path.join(proc_root, str(pid), "cmdline"), "rb") as fh:
            raw = fh.read(4096)
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()


def top_by_name(procs: list[dict], n: int = 8) -> list[dict]:
    groups: dict = {}
    for p in procs:
        key = (p["name"], p.get("unit"))
        g = groups.setdefault(key, {"name": p["name"], "pid": p["pid"], "rss_mb": 0, "unit": p.get("unit"), "_m": 0})
        g["rss_mb"] += p["rss_mb"]
        if p["rss_mb"] > g["_m"]:
            g["_m"], g["pid"] = p["rss_mb"], p["pid"]
    rows = sorted(groups.values(), key=lambda g: -g["rss_mb"])[:n]
    return [{k: v for k, v in g.items() if k != "_m"} for g in rows]


def sample(proc_root="/proc", top_n: int = 8) -> dict | None:
    s = plat.mem_probe(proc_root)
    if s is None:
        return None
    procs = read_procs(proc_root)
    s["procs"] = procs
    s["top"] = top_by_name(procs, top_n)
    return s


def _enter_level(s: dict, cfg: dict) -> str:
    t = cfg["tiers"]
    mem = s["mem_available_mb"]
    psi = s.get("psi_some_avg10") or 0.0
    sw = s.get("swap_free_pct")
    if mem < t["crit"]["mem_available_mb"] or psi > t["crit"]["psi"]:
        return "crit"
    if (mem < t["warn"]["mem_available_mb"] or psi > t["warn"]["psi"]
            or (sw is not None and sw < t["warn"]["swap_free_pct"] and mem < t["warn"]["swap_mem_available_mb"])):
        return "warn"
    return "ok"


def decide_level(s: dict, prev: str, prev_change_ts: float, cfg: dict, now: float) -> str:
    """Rising is immediate. Falling waits ``holdoff_s`` after the last change and then steps down one
    tier at a time while the sample clears that tier's enter line by ``margin_mb`` and psi is under
    half its enter psi. Pure."""
    prev = prev if prev in RANK else "ok"
    target = _enter_level(s, cfg)
    if RANK[target] >= RANK[prev]:
        return target
    hy = cfg["hysteresis"]
    if now - (prev_change_ts or 0) < hy["holdoff_s"]:
        return prev
    mem = s["mem_available_mb"]
    psi = s.get("psi_some_avg10") or 0.0
    level = prev
    while RANK[level] > RANK[target]:
        line = cfg["tiers"][level]
        if mem >= line["mem_available_mb"] + hy["margin_mb"] and psi < line["psi"] / 2:
            level = LOWER[level]
        else:
            break
    return level


# --------------------------------------------------------------------------- #
# Journal (kernel, systemd-oomd, the user manager)
# --------------------------------------------------------------------------- #
# "Out of memory: Killed process" (global) and "Memory cgroup out of memory: Killed process" (a capped scope)
_KERNEL_RE = re.compile(r"[Oo]ut of memory: Killed process (\d+) \((.+)\) total-vm:\d+kB, anon-rss:(\d+)kB")
_OOMD_RE = re.compile(r"Killed (/\S+) due to memory (pressure|used)")
_UM_RE = re.compile(r"^(\S+?): (?:The kernel OOM killer killed some processes in this unit"
                    r"|A process of this unit has been killed by the OOM killer)")
_STOPPED_RE = re.compile(r"^Stopped (\S+\.scope)\.?")
CMD_SYSTEM = ["journalctl", "-f", "-n0", "-o", "json", "_TRANSPORT=kernel", "+", "_SYSTEMD_UNIT=systemd-oomd.service"]
CMD_USER = ["journalctl", "--user", "-f", "-n0", "-o", "json", "-g", "OOM killer|oom-kill|Stopped .*\\.scope"]


def parse_journal_line(obj) -> dict | None:
    if not isinstance(obj, dict):
        return None
    msg = str(obj.get("MESSAGE") or "")
    if obj.get("_TRANSPORT") == "kernel" or obj.get("SYSLOG_IDENTIFIER") == "kernel":
        m = _KERNEL_RE.search(msg)
        if not m:
            return None
        return {"kind": "kill", "source": "kernel", "pid": int(m[1]), "victim": m[2], "rss_mb": int(m[3]) // 1024,
                "unit": None}
    ident = obj.get("SYSLOG_IDENTIFIER")
    if ident == "systemd-oomd":
        m = _OOMD_RE.search(msg)
        if not m:
            return None
        return {"kind": "kill", "source": "oomd", "unit": m[1].rstrip("/").rsplit("/", 1)[-1], "victim": None,
                "pid": None, "rss_mb": None, "reason": m[2]}
    if ident == "systemd":
        m = _UM_RE.match(msg)
        if m:
            return {"kind": "kill", "source": "user-manager", "unit": obj.get("USER_UNIT") or m[1], "victim": None,
                    "pid": None, "rss_mb": None}
        m = _STOPPED_RE.match(msg)
        if m:
            return {"kind": "stopped", "unit": obj.get("USER_UNIT") or m[1]}
    return None


def parse_journal_text(text: str) -> list[dict]:
    out = []
    for line in (text or "").splitlines():
        try:
            ev = parse_journal_line(json.loads(line))
        except ValueError:
            continue
        if ev:
            out.append(ev)
    return out


class JournalReader(threading.Thread):
    """Follows one ``journalctl -f -o json`` and queues parsed events; restarts with backoff (5 s doubling
    to 60 s). A dead reader never touches the tier loop, which drains the queue with get_nowait()."""

    def __init__(self, cmd: list[str], out: queue.Queue):
        super().__init__(daemon=True, name="memwatch-" + ("user" if "--user" in cmd else "system"))
        self.cmd, self.out, self._stop, self._proc = cmd, out, threading.Event(), None

    def run(self) -> None:
        backoff = 5.0
        while not self._stop.is_set():
            try:
                self._proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                              encoding="utf-8", errors="replace")
                for line in self._proc.stdout:
                    try:
                        ev = parse_journal_line(json.loads(line))
                    except ValueError:
                        continue
                    if ev:
                        self.out.put(ev)
                    backoff = 5.0
            except Exception as exc:  # noqa: BLE001
                _err(f"reader {self.name}: {type(exc).__name__}: {exc}")
            if self._stop.wait(backoff):
                break
            backoff = min(60.0, backoff * 2)

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._proc is not None:
                self._proc.terminate()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# Ledger and transcripts (state/live-sessions/<sid>.json, written by hooks/session-ledger.py)
# --------------------------------------------------------------------------- #
def load_ledger(ledger_dir=None) -> list[dict]:
    d = Path(ledger_dir or mws.paths()["ledger_dir"])
    out = []
    try:
        files = sorted(d.glob("*.json"))
    except OSError:
        return out
    for f in files:
        try:
            e = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(e, dict) and e.get("ended") in (None, False) and isinstance(e.get("pid"), int):
            e.setdefault("sid", f.stem)
            out.append(e)
    return out


def _ts_of(v) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v) / 1000 if v > 1e11 else float(v)
    if isinstance(v, str) and v:
        try:
            from datetime import datetime
            return datetime.fromisoformat(v.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def pending_bash_since(transcript, max_bytes: int = 262144) -> float | None:
    """Oldest timestamp of a Bash ``tool_use`` in the transcript tail without a ``tool_result``; None when
    every Bash call has its result (0.0 when one is pending but has no timestamp)."""
    try:
        with open(transcript, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            fh.seek(max(0, size - max_bytes))
            blob = fh.read()
    except (OSError, TypeError):
        return None
    pending: dict = {}
    for raw in blob.split(b"\n"):
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        msg = obj.get("message") if isinstance(obj, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use" and item.get("name") == "Bash" and item.get("id"):
                pending[item["id"]] = _ts_of(obj.get("timestamp")) or 0.0
            elif item.get("type") == "tool_result":
                pending.pop(item.get("tool_use_id"), None)
    return min(pending.values()) if pending else None


def _mtime(path) -> float:
    try:
        return os.stat(path).st_mtime
    except (OSError, TypeError, ValueError):
        return 0.0


def idle_session(ledger: list[dict], now: float, idle_min: float, by_pid: dict, fg_pid: int | None = None):
    """(sid, pid, scope) of the most idle live ledger session, or None. Never the foreground one (newest
    activity, or the pid owning the tmux pane in focus), never one with a Bash call still running."""
    live = [e for e in ledger if e.get("pid") in by_pid]
    if not live:
        return None
    last = {e["sid"]: max(_mtime(e.get("transcript")), float(e.get("seen") or 0)) for e in live}
    fg = max(live, key=lambda e: last[e["sid"]])["sid"]
    cands = []
    for e in live:
        focused = bool(fg_pid) and fg_pid in _chain(e["pid"], by_pid)  # pane_pid is the shell; claude sits below it
        if e["sid"] == fg or focused or now - last[e["sid"]] < idle_min * 60:
            continue
        if pending_bash_since(e.get("transcript")) is not None:
            continue
        cands.append(e)
    if not cands:
        return None
    pick = min(cands, key=lambda e: float(e.get("seen") or 0))
    return pick["sid"], pick["pid"], pick.get("scope") or by_pid[pick["pid"]].get("unit")


def stuck_scan(ledger: list[dict], now: float, pending_s: float = 1800) -> list[dict]:
    out = []
    for e in ledger:
        since = pending_bash_since(e.get("transcript"))
        if since is not None and since > 0 and now - since >= pending_s:
            out.append({"sid": e["sid"], "since": since})
    return out


def _chain(pid, by_pid: dict) -> list[int]:
    out, cur = [], pid
    while cur in by_pid and cur not in out and len(out) < 64:
        out.append(cur)
        cur = by_pid[cur].get("ppid")
    return out


# --------------------------------------------------------------------------- #
# Kill ladder
# --------------------------------------------------------------------------- #
class Ladder:
    """Stage 0 ok/warn; stage 1 stop own claude-index-* scopes; stage 2 kill the biggest browser renderer
    or stray build outside every claude tree (one per victim_interval_s); stage 3 stop the most idle
    ledger session (the restore brings it back). Decisions are pure; ``Ctx.act`` executes them."""

    def __init__(self, cfg: dict, proc_root="/proc", local_cfg=None):
        kp = cfg["kill_policy"]
        self.cfg = cfg
        self.proc_root = proc_root
        # fixture trees carry fake uids; only a live /proc filters victims by this account's uid
        live = os.path.realpath(str(proc_root)) == "/proc" and hasattr(os, "getuid")
        self.uid = os.getuid() if live else None
        local_kp = ogc.load(local_cfg).get("kill_policy")  # only keys the local file sets override the shipped ones
        local_kp = {k: v for k, v in ogc.kill_policy(local_cfg).items() if k in local_kp} \
            if isinstance(local_kp, dict) else {}
        self.kp = {**kp, **local_kp}
        self.shed_mode = ogc.shed_mode(local_cfg)
        extra_prot = set(ogc.protected_extra(local_cfg))
        self.protected = set(kp.get("protected") or PROTECTED) | extra_prot
        self.victims_extra = set(ogc.victims_extra(local_cfg)) - extra_prot
        self.victims = set(kp.get("victims") or VICTIM_COMMS)
        self.parents = set(kp.get("browser_parents") or BROWSER_PARENTS)
        try:
            self.victim_re = re.compile(kp.get("victim_cmd_re") or BUILD_RE)
        except re.error:
            self.victim_re = re.compile(BUILD_RE)
        self.shed_done: set = set()
        self.killed: dict = {}
        self.stopped_sids: set = set()
        self._cmd: dict = {}

    def cmd(self, pid: int) -> str:
        if pid not in self._cmd:
            self._cmd[pid] = cmdline_of(pid, self.proc_root)
        return self._cmd[pid]

    def in_claude_tree(self, p: dict, by_pid: dict) -> bool:
        if str(p.get("unit") or "").startswith("claude-"):
            return True
        return any(by_pid[a]["name"] == "claude" for a in _chain(p.get("ppid"), by_pid))

    def classify(self, p: dict, by_pid: dict) -> str:
        name = p["name"]
        if name in self.protected or name.startswith("systemd") or self.in_claude_tree(p, by_pid):
            return "protected"
        if name in self.victims_extra:
            return "victim"
        cmd = self.cmd(p["pid"])
        is_child = bool(CHILD_TYPE_RE.search(cmd)) or "-contentproc" in cmd
        if name in self.parents:
            return "victim" if is_child else "protected"  # a parent kill closes every window
        if name in self.victims or self.victim_re.search(cmd):
            return "victim"
        return "other"

    def _heavy(self, p: dict, by_pid: dict) -> bool:
        cmd = self.cmd(p["pid"])
        if p["name"] in ("chrome", "chromium", "chromium-browser") and "--headless" in cmd:
            return True
        return "vitest" in cmd and self.in_claude_tree(p, by_pid)

    def step(self, now: float, level: str, s: dict, procs: list[dict], ledger: list[dict], prev_kp: dict,
             fg_pid: int | None = None):
        self._cmd = {}
        prev_kp = prev_kp if isinstance(prev_kp, dict) else {}
        kp = {"stage": 0, "crit_since": None, "stage2_since": None, "last_kill_ts": prev_kp.get("last_kill_ts")}
        actions: list = []
        if level != "crit":
            self.shed_done.clear()
            self.stopped_sids.clear()
            return kp, actions
        kp["crit_since"] = prev_kp.get("crit_since") or now
        if not self.kp.get("enabled", True):
            return kp, actions
        by_pid = {p["pid"]: p for p in procs}
        kp["stage"] = 1
        if self.shed_mode != "none":
            for p in procs:
                unit = str(p.get("unit") or "")
                if unit.startswith("claude-index-") and unit not in self.shed_done:
                    self.shed_done.add(unit)
                    actions.append(("shed", unit))
                elif (self.shed_mode == "known-heavy" and ("pid", p["pid"]) not in self.shed_done
                      and self._heavy(p, by_pid)):
                    self.shed_done.add(("pid", p["pid"]))
                    actions.append(("kill", p, 1))
        # Stages 2-3 follow the sample, not the hysteresis-held tier: memory back above the crit enter line
        # must not keep killing. Leaving crit restarts the stage-3 clock.
        if _enter_level(s, self.cfg) != "crit":
            return kp, actions
        emergency = s["mem_available_mb"] < float(self.kp.get("emergency_mb", 1500))
        if not (emergency or now - kp["crit_since"] >= float(self.kp.get("stage_holdoff_s", 20))):
            return kp, actions
        kp["stage"] = 2
        kp["stage2_since"] = prev_kp.get("stage2_since") or now
        self.killed = {pid: t for pid, t in self.killed.items() if now - t < 60}
        children: dict = {}
        for p in procs:
            children.setdefault(p.get("ppid"), []).append(p["pid"])

        def shelters_claude(pid: int) -> bool:  # a pty host / extension host with a claude below it
            seen, stack = set(), list(children.get(pid, ()))
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                if by_pid.get(cur, {}).get("name") == "claude":
                    return True
                stack.extend(children.get(cur, ()))
            return False

        cands = sorted((p for p in procs if p["pid"] not in self.killed
                        and (self.uid is None or p.get("uid") == self.uid)
                        and self.classify(p, by_pid) == "victim" and not shelters_claude(p["pid"])),
                       key=lambda p: -p["rss_mb"])
        ready = now - float(kp["last_kill_ts"] or 0) >= float(self.kp.get("victim_interval_s", 10))
        if cands and ready:
            self.killed[cands[0]["pid"]] = now
            kp["last_kill_ts"] = now
            actions.append(("kill", cands[0], 2))
            return kp, actions
        if now - kp["stage2_since"] >= float(self.kp.get("stage3_after_s", 40)) or (emergency and not cands):
            kp["stage"] = 3
            if not ready:
                return kp, actions
            live = [e for e in ledger if e.get("sid") not in self.stopped_sids]
            pick = idle_session(live, now, float(self.kp.get("idle_min", 10)), by_pid, fg_pid)
            if pick is None:
                _err("stage3: no idle session")
            else:
                self.stopped_sids.add(pick[0])
                kp["last_kill_ts"] = now
                actions.append(("stop-session",) + tuple(pick))
        return kp, actions


# --------------------------------------------------------------------------- #
# Announce, restore nudge
# --------------------------------------------------------------------------- #
def mod_owns_toasts(now: float, path, fresh_s: float = 60.0) -> bool:
    """True when any state/mercy-mod.active.d/<sid>.json is younger than fresh_s (a mod is showing in-pane toasts)."""
    try:
        files = list(Path(path).glob("*.json"))
    except OSError:
        return False
    for f in files:
        try:
            ts = json.loads(f.read_text(encoding="utf-8")).get("ts")
        except Exception:  # noqa: BLE001
            continue
        if isinstance(ts, (int, float)) and 0 <= now - ts < fresh_s:
            return True
    return False


def in_quiet_hours(now: float, spec: str) -> bool:
    """``"HH:MM-HH:MM"`` local time, wrapping midnight; "" or a bad spec is never quiet."""
    try:
        a, b = (int(h) * 60 + int(m) for h, m in (x.strip().split(":") for x in str(spec).split("-")))
    except (ValueError, TypeError):
        return False
    t = time.localtime(now)
    cur = t.tm_hour * 60 + t.tm_min
    return (a <= cur < b) if a <= b else (cur >= a or cur < b)


def matches_ledger(ev: dict, ledger: list[dict], by_pid: dict | None = None) -> dict | None:
    """The ledger entry a kill hit: same scope, same pid, or a pid that descended from its pid in the last
    process table (the victim itself is gone from /proc by now)."""
    by_pid = by_pid or {}
    for e in ledger:
        if ev.get("unit") and ev["unit"] == e.get("scope"):
            return e
        pid = ev.get("pid")
        if pid and (pid == e.get("pid") or e.get("pid") in _chain(pid, by_pid)):
            return e
    return None


class Ctx:
    """Everything one sentinel run carries between passes; the seams (run, kill, spawn, notify, root,
    local_cfg, ledger_dir) keep tests off the live machine."""

    def __init__(self, args, cfg: dict, *, run=None, kill=None, spawn=None, notify=None, root=None,
                 local_cfg=None, ledger_dir=None):
        self.args, self.cfg = args, cfg
        self.proc_root = str(args.proc_root)
        self.live = os.path.realpath(self.proc_root) == "/proc"
        self.dry = bool(args.dry_run)
        self.once = bool(args.once)
        self.state_path = Path(args.state) if args.state else mws.paths()["state"]
        self.events_path = Path(args.events) if args.events else mws.paths()["events"]
        self.ledger_dir = ledger_dir
        self.local_cfg = local_cfg
        self.root = Path(root or _ROOT)
        quiet = (lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))
        self.run = run or (plat.run if self.live else quiet)
        self.kill = kill or (os.kill if self.live else (lambda pid, sig: None))
        self.spawn = spawn or (plat.spawn_detached if self.live else (lambda cmd: None))
        replay = bool(getattr(args, "journal_cmd", None))  # replayed journal lines are history: no toasts
        self.notify = notify or (plat.notify if self.live and not replay else (lambda *a, **k: False))
        prev = mws.read(path=self.state_path, stale_s=10 ** 9)
        self.level = prev.raw_level if prev.ts else "ok"
        self.level_ts = prev.ts or 0.0
        # kill timers from an old state file would skip the holdoff after a restart: keep them only when fresh
        fresh = bool(prev.ts) and time.time() - prev.ts <= float(cfg.get("state_stale_s", 30))
        self.kp = dict(prev.kill_policy) if fresh else {}
        self.restore_pending = prev.restore_pending
        self.restore_spawned_ts: float | None = None
        self.stuck = list(prev.stuck)
        self.ladder = Ladder(cfg, self.proc_root, local_cfg)
        self.ladder.shed_done = {u for u in prev.shed if isinstance(u, str)} if fresh and self.level == "crit" else set()
        self.notify_owner = "memwatch"
        self.ok_since = (prev.ts or None) if self.level == "ok" else None
        self.queue: queue.Queue = queue.Queue()
        self.readers: list = []
        self.recent_kills: list = []
        self.seen_keys: dict = {}
        self.by_pid: dict = {}
        self.last_unit: dict = {}  # pid -> unit over the last two samples (a kernel victim is gone by ingest time)
        self.next_stuck_scan = 0.0
        self.iterations = 0
        self.stopping = False
        self._slow_logged = 0.0

    # -- events -------------------------------------------------------------
    def event(self, ev: dict) -> None:
        mws.append_event(ev, path=self.events_path)

    def announce(self, kind: str, text: str, urgency: str, now: float) -> None:
        _err(text)  # the unit's stderr is the journal
        ncfg = self.cfg.get("notify") or {}
        # notify_owner = who shows the in-pane toast; the desktop notification is always this daemon's (one per machine)
        self.notify_owner = "mod" if mod_owns_toasts(now, mws.paths()["mod_active"],
                                                     float(ncfg.get("mod_flag_fresh_s", 60))) else "memwatch"
        if kind == "warn" and in_quiet_hours(now, ncfg.get("quiet_hours") or ""):
            return
        try:
            self.notify("Claude memory " + ("kill" if kind == "kill" else kind), text, urgency)
        except Exception as exc:  # noqa: BLE001
            _err(f"notify: {exc}")

    def _restore_allowed(self) -> bool:
        return ogc.restore_enabled(self.local_cfg) and (self.root / "scripts" / "restore_sessions.py").is_file()

    def ingest(self, events: list[dict], now: float, ledger: list[dict] | None = None) -> None:
        ledger = load_ledger(self.ledger_dir) if ledger is None else ledger
        self.recent_kills = [k for k in self.recent_kills if now - k["ts"] < 60]
        self.seen_keys = {k: t for k, t in self.seen_keys.items() if now - t < 5}
        for ev in events:
            if str(ev.get("unit") or "").startswith("claude-test-"):
                continue  # a test's sacrificial scope (tests/test_oomguard_integration.py, golive guard-checks): never a kill row
            if ev.get("kind") == "stopped":
                # A Stopped line is a kill only when a recent kill hit that unit; each kill is consumed once.
                unit = ev.get("unit")
                hit = next((k for k in reversed(self.recent_kills) if not k.get("_used") and k.get("unit") == unit),
                           None)
                if hit is None:
                    hit = next((k for k in reversed(self.recent_kills)
                                if not k.get("_used") and k.get("source") == "kernel" and not k.get("unit")
                                and k.get("_last_unit") == unit), None)
                if hit is None:
                    continue
                hit["_used"] = True
                key = ("user-manager", unit)
                if key in self.seen_keys:
                    continue
                self.seen_keys[key] = now
                ev = {**{k: v for k, v in hit.items() if k != "ts" and not k.startswith("_")}, "kind": "kill",
                      "source": "user-manager", "unit": unit, "note": "scope stopped after kill"}
            elif ev.get("kind") == "kill":
                key = (ev.get("source"), ev.get("pid") or ev.get("unit"))
                if key in self.seen_keys:
                    continue
                self.seen_keys[key] = now
            else:
                continue
            ev = {**ev, "ts": round(now, 3)}
            self.event(ev)
            # a converted event never feeds another conversion (that was the storm)
            self.recent_kills.append({**ev, "_last_unit": self.last_unit.get(ev.get("pid")),
                                      "_used": ev.get("note") == "scope stopped after kill"})
            if _tele is not None:
                try:
                    _tele.record("memwatch", "kill", **{k: v for k, v in ev.items() if k != "ts"})
                except Exception:  # noqa: BLE001
                    pass
            who = ev.get("victim") or ev.get("unit") or "a process"
            self.announce("kill", f"{ev.get('source')} killed {who}", "critical", now)
            if matches_ledger(ev, ledger, self.by_pid) and self._restore_allowed():
                self.restore_pending = True

    def poll_journal(self) -> list[dict]:
        out: list = []
        cmd = getattr(self.args, "journal_cmd", None)
        if cmd:
            cp = plat.run(shlex.split(cmd), timeout=JOURNAL_CMD_TIMEOUT)
            if cp.returncode != 0:
                _err(f"journal-cmd rc={cp.returncode}")
            else:
                out = parse_journal_text(cp.stdout or "")
            return out
        while True:
            try:
                out.append(self.queue.get_nowait())
            except queue.Empty:
                break
            except Exception as exc:  # noqa: BLE001 - a broken queue must not stop the tier loop
                _err(f"journal queue: {type(exc).__name__}")
                break
        return out

    # -- ladder actions ------------------------------------------------------
    def act(self, actions: list, now: float) -> None:
        for a in actions:
            try:
                if a[0] == "shed":
                    self.event({"kind": "shed", "unit": a[1], "dry_run": self.dry, "ts": round(now, 3)})
                    if not self.dry:
                        self.run(["systemctl", "--user", "stop", a[1]], timeout=10)
                elif a[0] == "kill":
                    p, stage = a[1], a[2]
                    ok = True if self.dry else self._signal(p["pid"], 3.0)
                    self.event({"kind": "kill", "victim": p["name"], "pid": p["pid"], "rss_mb": p["rss_mb"],
                                "unit": p.get("unit"), "source": "memwatch", "stage": stage,
                                "cmd": self.ladder.cmd(p["pid"])[:100], "signal": "SIGTERM", "dry_run": self.dry,
                                "ok": ok, "ts": round(now, 3)})
                    if ok:
                        self.announce("kill", f"OOM guard stage {stage}: killed {p['name']} ({p['rss_mb']} MB)",
                                      "critical", now)
                    elif stage == 2:  # a refused signal must not spend the kill slot
                        self.ladder.killed.pop(p["pid"], None)
                        if isinstance(self.kp, dict):
                            self.kp["last_kill_ts"] = None
                elif a[0] == "stop-session":
                    _, sid, pid, scope = a
                    p = self.by_pid.get(pid, {})
                    self.event({"kind": "kill", "victim": p.get("name", "claude"), "sid": sid, "pid": pid,
                                "rss_mb": p.get("rss_mb"), "unit": scope, "source": "memwatch", "stage": 3,
                                "cmd": self.ladder.cmd(pid)[:100], "signal": "SIGTERM", "dry_run": self.dry,
                                "scope_stopped": bool(scope and OWN_SCOPE_RE.match(scope)), "ts": round(now, 3)})
                    if self._restore_allowed():
                        self.restore_pending = True
                    if not self.dry:
                        self._stop_session(pid, scope)
                    self.announce("kill", f"OOM guard stage 3: stopped idle session {sid[:8]} (restored later)",
                                  "critical", now)
            except Exception as exc:  # noqa: BLE001
                _err(f"act {a[0]}: {type(exc).__name__}: {exc}")

    def _signal(self, pid: int, grace: float) -> bool:
        """SIGTERM now, SIGKILL after ``grace`` (live loop only); True when SIGTERM was delivered."""
        try:
            self.kill(pid, signal.SIGTERM)
        except OSError as exc:
            _err(f"SIGTERM {pid}: {exc}")
            return False
        if self.once or not self.live:
            return True
        sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)

        def _later():
            if plat.pid_alive(pid):
                try:
                    self.kill(pid, sigkill)
                except OSError:
                    pass
        threading.Timer(grace, _later).start()

    def _stop_session(self, pid: int, scope: str | None) -> None:
        """SIGTERM the session pid; stop its scope too only when bin/claude made it (``claude-*.scope``).
        A terminal or editor scope (app-kitty-*, vscode-*) holds other tabs: the pid signal is the whole action."""
        self._signal(pid, 3.0)  # SIGTERM flushes the transcript
        if scope and OWN_SCOPE_RE.match(scope) and not self.once and self.live:
            threading.Timer(5.0, lambda: self.run(["systemctl", "--user", "stop", scope], timeout=10)).start()

    def fg_pid(self) -> int | None:
        """The pid of the tmux pane in focus (best effort, live loop only)."""
        if self.once or not self.live or not shutil.which("tmux"):
            return None
        cp = self.run(["tmux", "display-message", "-p", "#{pane_pid}"], timeout=2)
        out = (getattr(cp, "stdout", "") or "").strip()
        return int(out) if out.isdigit() else None


def maybe_restore(ctx: Ctx, now: float) -> bool:
    """Spawn scripts/restore_sessions.py once the tier has been ok for ok_hold_s after a ledger-matched
    kill. ``state/restore.spawned`` (O_EXCL) debounces spawns; one older than lock_stale_s is replaced.
    ``restore.lock`` belongs to restore_sessions.py: memwatch never takes it (the child would see it held
    by this live daemon and exit "locked"). ``restore_pending`` stays set until settle_restore clears it."""
    rcfg = ctx.cfg.get("restore") or {}
    if not ctx.restore_pending or ctx.level != "ok" or ctx.ok_since is None:
        return False
    if now - ctx.ok_since < float(rcfg.get("ok_hold_s", 60)) or not ogc.restore_enabled(ctx.local_cfg):
        return False
    script = ctx.root / "scripts" / "restore_sessions.py"
    if not script.is_file():
        return False
    debounce = plat.state_dir() / "restore.spawned"
    for _ in range(2):
        try:
            debounce.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(debounce), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.write(fd, json.dumps({"pid": os.getpid(), "ts": now}).encode())
            os.close(fd)
            break
        except FileExistsError:
            if now - _mtime(debounce) < float(rcfg.get("lock_stale_s", 600)):
                return False
            try:
                os.unlink(debounce)
            except OSError:
                return False
        except OSError:
            return False
    else:
        return False
    ctx.spawn([plat.python_exe(), str(script), *[str(a) for a in rcfg.get("args") or []]])
    ctx.restore_spawned_ts = now
    return True


def settle_restore(ctx: Ctx, now: float) -> None:
    """Clear ``restore_pending`` once a ``{"kind": "restore"}`` row newer than the spawn lands in the events
    file (ok not false), or give up after lock_stale_s. Without a recorded spawn there is nothing to settle."""
    if not ctx.restore_pending or not ctx.restore_spawned_ts:
        return
    since = ctx.restore_spawned_ts
    done = any(e.get("kind") == "restore" and e.get("ok") is not False and _num(e.get("ts")) > since
               for e in mws.tail_events(path=ctx.events_path))
    if not done and now - since <= float((ctx.cfg.get("restore") or {}).get("lock_stale_s", 600)):
        return
    if not done:
        _err("restore: no restore row after the spawn; giving up")
    ctx.restore_pending, ctx.restore_spawned_ts = False, None


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------- #
# One pass, the loop, the CLI
# --------------------------------------------------------------------------- #
def write_state(ctx: Ctx, now: float, s: dict | None) -> None:
    st = mws.State(level=ctx.level, ts=round(now, 3), stuck=ctx.stuck, notify_owner=ctx.notify_owner,
                   kill_policy=ctx.kp, restore_pending=ctx.restore_pending,
                   shed=sorted(u for u in ctx.ladder.shed_done if isinstance(u, str)))
    if s is not None:
        st.mem_available_mb, st.swap_free_pct = s["mem_available_mb"], s["swap_free_pct"]
        st.psi_some_avg10, st.top = s["psi_some_avg10"], s["top"]
    mws.write_atomic(st, path=ctx.state_path)


def pass_once(ctx: Ctx, now: float) -> None:
    s = None
    try:
        s = sample(ctx.proc_root, int(ctx.cfg.get("top_n", 8)))
        if s is None:
            _err("probe failed; keeping the previous level")
        else:
            prev_units = {pid: p.get("unit") for pid, p in ctx.by_pid.items()}
            ctx.by_pid = {p["pid"]: p for p in s["procs"]}
            ctx.last_unit = {**prev_units, **{pid: p.get("unit") for pid, p in ctx.by_pid.items()}}
            new = decide_level(s, ctx.level, ctx.level_ts, ctx.cfg, now)
            if new != ctx.level:
                ctx.event({"kind": "tier", "from": ctx.level, "to": new, "mem_available_mb": s["mem_available_mb"],
                           "psi_some_avg10": s["psi_some_avg10"], "swap_free_pct": s["swap_free_pct"],
                           "ts": round(now, 3)})
                if new != "ok":
                    sw = 100 - (s["swap_free_pct"] if s["swap_free_pct"] is not None else 100)
                    ctx.announce(new, f"memory {new}: {s['mem_available_mb'] / 1024:.1f} GB free, swap {sw:.0f} % "
                                      "used", "critical" if new == "crit" else "normal", now)
                ctx.level, ctx.level_ts = new, now
            ctx.ok_since = (ctx.ok_since or now) if ctx.level == "ok" else None
        ledger = load_ledger(ctx.ledger_dir)
        ctx.ingest(ctx.poll_journal(), now, ledger)
        if s is not None:
            ctx.kp, actions = ctx.ladder.step(now, ctx.level, s, s["procs"], ledger, ctx.kp, ctx.fg_pid())
            ctx.act(actions, now)
        if now >= ctx.next_stuck_scan:
            st = ctx.cfg.get("stuck") or {}
            ctx.stuck = stuck_scan(ledger, now, float(st.get("pending_bash_s", 1800)))
            ctx.next_stuck_scan = now + float(st.get("scan_s", 60))
        settle_restore(ctx, now)
        maybe_restore(ctx, now)
    except Exception as exc:  # noqa: BLE001 - the sentinel never dies of one bad pass
        _err(f"pass: {type(exc).__name__}: {exc}")
    finally:
        ctx.iterations += 1
        write_state(ctx, now, s)


def run_once(ctx: Ctx, now: float | None = None) -> int:
    pass_once(ctx, time.time() if now is None else now)
    return 0


def open_psi_trigger(proc_root: str):
    """A PSI trigger on /proc/pressure/memory (150 ms stall in a 2 s window) that poll() wakes on; None
    when the kernel or the account refuses (plain sleep then)."""
    try:
        import select
        fh = open(os.path.join(proc_root, "pressure", "memory"), "r+b", buffering=0)  # noqa: SIM115
        fh.write(b"some 150000 2000000\0")
        poller = select.poll()
        poller.register(fh.fileno(), select.POLLPRI)
        return fh, poller
    except (OSError, AttributeError, ImportError):
        return None


def start_readers(ctx: Ctx) -> list:
    if getattr(ctx.args, "journal_cmd", None) or not ctx.live or not shutil.which("journalctl"):
        return []
    readers = [JournalReader(CMD_SYSTEM, ctx.queue), JournalReader(CMD_USER, ctx.queue)]
    for r in readers:
        r.start()
    return readers


def run_loop(ctx: Ctx, *, max_iterations: int | None = None, clock=time.time, sleep=time.sleep) -> int:
    ctx.readers = start_readers(ctx)
    trigger = open_psi_trigger(ctx.proc_root) if ctx.live and max_iterations is None else None
    interval = float(ctx.cfg.get("interval_s", 5))
    try:
        while not ctx.stopping:
            t0 = clock()
            pass_once(ctx, t0)
            took = clock() - t0
            if took > 2 and t0 - ctx._slow_logged > 60:
                ctx._slow_logged = t0
                _err(f"slow pass: {took:.1f} s")
            if max_iterations is not None and ctx.iterations >= max_iterations:
                break
            if trigger is not None:
                try:
                    trigger[1].poll(int(interval * 1000))
                except OSError:
                    sleep(interval)
            else:
                sleep(interval)
    finally:
        for r in ctx.readers:
            r.stop()
    return 0


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Claude Code memory-pressure sentinel (docs/OOM-GUARD.md)")
    ap.add_argument("--once", action="store_true", help="one pass, then exit")
    ap.add_argument("--dry-run", action="store_true", help="record actions, signal nothing")
    ap.add_argument("--proc-root", default="/proc")
    ap.add_argument("--config", default=str(CONFIG_PATH))
    ap.add_argument("--journal-cmd", help="read journal JSON lines from this command once per pass")
    ap.add_argument("--events")
    ap.add_argument("--state")
    ap.add_argument("--interval", type=float)
    return ap


def main(argv=None, **seams) -> int:
    args = _parser().parse_args(argv)
    try:
        if plat.IS_WINDOWS or plat.mem_probe(args.proc_root) is None:
            st = mws.State(level="ok", unsupported=True, ts=round(time.time(), 3))
            mws.write_atomic(st, path=Path(args.state) if args.state else None)
            print("unsupported")
            return 0
        cfg = load_config(args.config)
        if args.interval:
            cfg["interval_s"] = args.interval
        ctx = Ctx(args, cfg, **seams)
        if args.once:
            return run_once(ctx)
        try:  # the mod's flag dir ($.fs has no mkdir); the daemon only, never a --once rehearsal
            mws.paths()["mod_active"].mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        def _stop(*_):
            ctx.stopping = True
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, _stop)
        return run_loop(ctx)
    except Exception as exc:  # noqa: BLE001
        _err(f"fatal: {type(exc).__name__}: {exc}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
