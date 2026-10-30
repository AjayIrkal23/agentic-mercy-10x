"""doctor_oomguard.py — OOM guard doctor rows ``(name, status, detail)`` for installer/doctor.py.

  oom-policy       DefaultOOMPolicy=continue AND this process's own scope continue (FAIL on stop)
  memwatch-unit    claude-memwatch.service installed, active, ExecStart = this tree's hooks/tools/memwatch.py
  restore-unit     claude-restore enabled iff oomguard.local.json restore_enabled
  claude-launcher  zsh / bash resolve `claude` to ~/.claude/bin/claude
  launch-caps      a launch through bin/claude in the last 24 h
  attach-live      no running claude session left in a stop scope

Every probe is wrapped (an error is a WARN row), every subprocess capped at 2 s. Windows, no user
manager or ``ci=True``: SKIP rows. Design: docs/OOM-GUARD.md.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import oomguard_setup  # noqa: E402
from lib import oomguard_config as ogc  # noqa: E402
from lib import platform as plat  # noqa: E402

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
NAMES = ("oom-policy", "memwatch-unit", "restore-unit", "claude-launcher", "launch-caps", "attach-live")
TIMEOUT = 2


def _show(run, *args) -> str:
    out = getattr(run(["systemctl", "--user", "show", *args], timeout=TIMEOUT), "stdout", "") or ""
    return out.strip().partition("=")[2].strip()


def _verb(run, *args) -> str:
    return (getattr(run(["systemctl", "--user", *args], timeout=TIMEOUT), "stdout", "") or "").strip()


def _oom_policy(run, proc_root):
    default = _show(run, "-p", "DefaultOOMPolicy")
    if default != "continue":
        return FAIL, f"DefaultOOMPolicy={default or '?'} (run installer/oomguard_setup.py --apply)"
    scope = plat.cgroup_of(os.getpid(), proc_root)
    own = _show(run, scope, "-p", "OOMPolicy") if scope else ""
    if scope and own and own != "continue":
        return WARN, f"live scope predates the reload; attach_live could not move it ({scope} OOMPolicy={own})"
    return PASS, f"DefaultOOMPolicy=continue; this scope {own or 'n/a'}"


def _memwatch_unit(run, home, root):
    unit = home / ".config" / "systemd" / "user" / "claude-memwatch.service"
    if not unit.is_file():
        return FAIL, "unit missing (run installer/oomguard_setup.py --apply)"
    active = _verb(run, "is-active", "claude-memwatch")
    if active != "active":
        return FAIL, f"claude-memwatch {active or 'unknown'}"
    text = unit.read_text(encoding="utf-8", errors="replace")
    want = str(Path(root) / "hooks") + "/tools/memwatch.py"
    exec_line = next((ln for ln in text.splitlines() if ln.startswith("ExecStart=")), "")
    if want not in exec_line:
        return WARN, (f"ExecStart runs {exec_line.partition('=')[2] or '?'}, not {want} (run {Path(root)}/installer/"
                      "oomguard_setup.py --apply, then systemctl --user try-restart claude-memwatch)")
    return PASS, f"active, {_verb(run, 'is-enabled', 'claude-memwatch') or '?'}"


def _restore_unit(run, home, root):
    if not (root / "scripts" / "restore_sessions.py").exists():
        return SKIP, "scripts/restore_sessions.py absent"
    want = ogc.restore_enabled(home / ".claude" / "oomguard.local.json")
    state = _verb(run, "is-enabled", "claude-restore") or "unknown"
    if want and state == "enabled":
        return PASS, "enabled"
    if not want and state != "enabled":
        return PASS, "disabled by oomguard.local.json"
    return WARN, f"restore_enabled={str(want).lower()} but claude-restore is {state}"


def _launcher(run, which):
    probes = [(s, c) for s, c in (("zsh", "whence -p claude"), ("bash", "type -P claude")) if which(s)]
    if not probes:
        return SKIP, "no zsh or bash"
    bad = []
    for shell, cmd in probes:
        cp = run([shell, "-ic", cmd], timeout=TIMEOUT)
        if getattr(cp, "returncode", 1) == 124:
            bad.append(f"{shell}: shell took > {TIMEOUT} s")
            continue
        lines = (getattr(cp, "stdout", "") or "").strip().splitlines()
        got = lines[-1].strip() if lines else ""
        if not got.endswith("/.claude/bin/claude"):
            bad.append(f"{shell} resolves claude to {got or 'nothing'}")
    return (WARN, "; ".join(bad)) if bad else (PASS, " and ".join(s for s, _ in probes) + " -> ~/.claude/bin/claude")


def _launch_caps(now):
    files = sorted((plat.state_dir() / "launch-caps").glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not files or now - files[-1].stat().st_mtime > 86400:
        return WARN, "no launch through bin/claude yet (last 24 h)"
    try:
        d = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    age = int((now - files[-1].stat().st_mtime) // 60)
    return PASS, f"wf{d.get('workflow_agents', '?')} sub{d.get('subagents', '?')} {d.get('size_guideline', '?')} ({age} min ago)"


def _attach(run, proc_root, bus, uid):
    rows = oomguard_setup.attach_live(True, run=run, proc_root=proc_root, bus=bus, uid=uid)
    pending = [r for r in rows if "WOULD-" in r]
    done = [r for r in rows if "SKIP(already continue)" in r]
    if pending:
        return WARN, f"{len(pending)} live claude session(s) still in a stop scope; {len(done)} protected"
    return PASS, f"{len(done)} live session(s) in continue scopes"


def rows(root=".", *, run=None, which=None, home=None, bus=..., proc_root="/proc", ci=False, uid=None,
         now=None) -> list[tuple[str, str, str]]:
    root, home = Path(root).resolve(), Path(home or Path.home())
    run, which = run or plat.run, which or shutil.which
    bus = plat.systemd_user_bus() if bus is ... else bus
    if ci:
        return [(n, SKIP, "ci") for n in NAMES]
    if plat.IS_WINDOWS or bus is None or not which("systemctl"):
        return [(n, SKIP, "no systemd user manager") for n in NAMES]
    probes = (("oom-policy", lambda: _oom_policy(run, proc_root)), ("memwatch-unit", lambda: _memwatch_unit(run, home, root)),
              ("restore-unit", lambda: _restore_unit(run, home, root)), ("claude-launcher", lambda: _launcher(run, which)),
              ("launch-caps", lambda: _launch_caps(time.time() if now is None else now)),
              ("attach-live", lambda: _attach(run, proc_root, bus, uid)))
    out = []
    for name, fn in probes:
        try:
            status, detail = fn()
        except Exception as exc:  # noqa: BLE001 - a doctor probe never raises
            status, detail = WARN, f"{type(exc).__name__}: {exc}"
        out.append((name, status, detail))
    return out


if __name__ == "__main__":
    for r in rows(Path(__file__).resolve().parents[1]):
        print(r)
