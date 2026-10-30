#!/usr/bin/env python3
"""replica_sync.py — after go-live, bring the Windows replica up to date over key-only SSH (no passwords, no
prompts): git pull --ff-only, installer/render.py, and a `claude -p --bare` init check.

Host/user from CLAUDE_REPLICA_SSH (user@host) or the machines file bullet (`- **Dev PC #2**` or a bullet
naming the replica; backticked user@host tokens: the first is the host, the rest are fallbacks tried on a
connection error); the Windows profile dir from CLAUDE_REPLICA_HOME (forward slashes) or the same bullet.
The remote shell is cmd.exe: commands chain with `&&`, no quoting. Reports PASS/WARN/SKIP and exits 0 for
all three; exit 2 only on misuse (run on Windows). Never writes host or home into a tracked file.
  replica_sync.py [--machines PATH] [--host user@host] [--home C:/Users/<name>] [--dry-run]
  replica_sync.py --posix --host user@host [--dry-run]   # a Linux box: pull + render, then the doctor line
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
from lib import platform as plat  # noqa: E402

_LOGIN_RE = re.compile(r"\b[\w.-]+@(?:\d{1,3}\.){3}\d{1,3}\b|\b[\w.-]+@[\w-]+(?:\.[\w-]+)+\b")
_HOME_RE = re.compile(r"([A-Za-z]):\\Users\\([^\\`\s]+)\\\.claude")
_BULLET_RE = re.compile(r"^- \*\*")
_REPLICA_RE = re.compile(r"^- \*\*Dev PC #?2\*\*|^- \*\*.*replica", re.I)
_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


@dataclass
class Replica:
    host: str
    fallbacks: list[str] = field(default_factory=list)
    home_fwd: str = ""


@dataclass
class Step:
    name: str
    cmd: str
    timeout: int


def _block(text: str) -> str:
    lines, out, on = text.splitlines(), [], False
    for line in lines:
        if _BULLET_RE.match(line):
            if on:
                break
            on = bool(_REPLICA_RE.match(line))
        if on:
            out.append(line)
    return "\n".join(out)


def discover(environ, machines_path: Path | None) -> Replica | None:
    host, home = environ.get("CLAUDE_REPLICA_SSH", ""), environ.get("CLAUDE_REPLICA_HOME", "")
    fallbacks: list[str] = []
    block = ""
    if machines_path:
        try:
            block = _block(Path(machines_path).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            block = ""
    if block:
        logins: list[str] = []
        for span in re.findall(r"`([^`]+)`", block):
            for m in _LOGIN_RE.finditer(span):
                if m.group(0) not in logins:
                    logins.append(m.group(0))
        if not host and logins:
            host = logins[0]
        fallbacks = [x for x in logins if x != host]
        m = _HOME_RE.search(block)
        if m and not home:
            home = f"{m.group(1)}:/Users/{m.group(2)}"
    if not host or not home:
        return None
    return Replica(host=host, fallbacks=fallbacks, home_fwd=home.rstrip("/"))


def _prefix(home_fwd: str) -> str:
    h = home_fwd.replace("/", "\\")
    return ("set USERPROFILE=" + h + "&& set HOME=" + h + "&& set PYTHONUTF8=1&& set LOCALAPPDATA=" + h
            + "\\AppData\\Local&& set APPDATA=" + h + "\\AppData\\Roaming&& set PATH=" + h + "\\.local\\bin;%PATH%&& ")


def plan(rep: Replica) -> list[Step]:
    cdir = rep.home_fwd.replace("/", "\\") + "\\.claude"
    return [Step("pull", f"git -C {cdir} -c safe.directory=* pull --ff-only", 300),
            Step("render", f"py -3 {cdir}\\installer\\render.py", 600),
            Step("init", "claude -p --bare --output-format stream-json --verbose --max-turns 1 ok", 180)]


def ssh_argv(host: str, cmd: str, home_fwd: str) -> list[str]:
    return ["ssh", *_SSH_OPTS, host, _prefix(home_fwd) + cmd]


def _has_init(stdout: str) -> bool:
    for line in (stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict) and ev.get("type") == "system" and ev.get("subtype") == "init":
            return True
    return False


def run_step(step: Step, rep: Replica, *, run=plat.run) -> str:
    cp = None
    for host in [rep.host, *rep.fallbacks]:
        cp = run(ssh_argv(host, step.cmd, rep.home_fwd), timeout=step.timeout, stdin_devnull=True)
        if cp.returncode != 255:  # 255 = ssh could not connect; a remote rc is never retried
            break
    if cp.returncode == 124:
        return "WARN(timeout)"
    if cp.returncode != 0:
        return f"WARN(rc={cp.returncode})"
    if step.name == "init" and not _has_init(cp.stdout):
        return "WARN(no init event)"
    return "OK"


_POSIX_STEPS = (("pull", "git -C ~/.claude pull --ff-only && python3 ~/.claude/installer/render.py", 600),
                ("doctor", "python3 ~/.claude/installer/doctor.py | tail -1", 300))


def posix_main(host: str, dry: bool, *, run=plat.run) -> int:
    """A POSIX replica (another Linux box with a git ~/.claude): pull + render, then the doctor's
    summary line. Same PASS/WARN/SKIP semantics as the Windows path (FI-9)."""
    if not host:
        print("replica_sync: SKIP (no replica host: pass --host user@host or set CLAUDE_REPLICA_SSH)")
        return 0
    if dry:
        for _, cmd, _t in _POSIX_STEPS:
            print(f"plan ssh -o BatchMode=yes {host} {shlex.quote(cmd)}")
        return 0
    rows: list[tuple[str, str]] = []
    for name, cmd, timeout in _POSIX_STEPS:
        if name == "doctor" and rows and rows[0][1] != "OK":
            rows.append((name, "SKIP(pull failed)"))
            continue
        cp = run(["ssh", *_SSH_OPTS, host, cmd], timeout=timeout, stdin_devnull=True)
        status = ("WARN(timeout)" if cp.returncode == 124 else
                  f"WARN(rc={cp.returncode})" if cp.returncode != 0 else
                  "WARN(doctor FAIL)" if name == "doctor" and re.search(r"[1-9]\d* FAIL", cp.stdout or "") else "OK")
        rows.append((name, status))
    for name, status in rows:
        print(f"{name} {status}")
    _record(rows)
    print("replica_sync: " + ("PASS" if all(st == "OK" for _, st in rows) else "WARN"))
    return 0


def _record(rows: list[tuple[str, str]]) -> None:
    try:
        d = plat.state_dir() / "golive"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"replica-{time.strftime('%Y%m%dT%H%M')}.json").write_text(
            json.dumps([{"step": n, "status": s} for n, s in rows], indent=1) + "\n", encoding="utf-8", newline="\n")
    except OSError:
        pass


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="replica_sync.py", description=__doc__.split("\n")[0])
    ap.add_argument("--machines", default=None)
    ap.add_argument("--host", default=None)
    ap.add_argument("--home", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--posix", action="store_true", help="the replica is a Linux/macOS box (plain ssh, bash)")
    a = ap.parse_args(argv)
    if plat.IS_WINDOWS:
        print("replica_sync: refused: run replica_sync from the Linux workstation")
        return 2
    if a.posix:
        return posix_main(a.host or os.environ.get("CLAUDE_REPLICA_SSH", ""), a.dry_run)
    env = dict(os.environ)
    if a.host:
        env["CLAUDE_REPLICA_SSH"] = a.host
    if a.home:
        env["CLAUDE_REPLICA_HOME"] = a.home
    machines = Path(a.machines) if a.machines else plat.claude_dir() / "CLAUDE.machines.local.md"
    rep = discover(env, machines)
    if rep is None:
        print("replica_sync: SKIP (no replica host: set CLAUDE_REPLICA_SSH or add the Dev PC bullet to the "
              "machines file)")
        return 0
    steps = plan(rep)
    if a.dry_run:
        for s in steps:
            print(f"plan {s.name:<7} ssh {rep.host} <profile env>&& {s.cmd}")
        return 0
    rows: list[tuple[str, str]] = []
    for s in steps:
        if s.name == "render" and rows and rows[0][1] != "OK":
            rows.append((s.name, "SKIP(pull failed)"))  # a stale tree must not be rendered
            continue
        rows.append((s.name, run_step(s, rep)))
    for name, status in rows:
        print(f"{name} {status}")
    _record(rows)
    print("replica_sync: " + ("PASS" if all(st == "OK" for _, st in rows) else "WARN"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
