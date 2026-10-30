"""doctor_oomguard.py — OOM guard doctor rows ``(name, status, detail)`` for installer/doctor.py.

  oom-policy       DefaultOOMPolicy=continue AND this process's own scope continue (FAIL on stop)
  memwatch-unit    claude-memwatch.service installed, active, ExecStart = this tree's hooks/tools/memwatch.py
  memwatch-code    the running daemon is newer than memwatch.py / its config / libs (WARN: self-heal restarts it)
  restore-unit     claude-restore enabled iff oomguard.local.json restore_enabled (WARN: enabled, no tmux)
  claude-launcher  zsh -i / bash -i / bash -l resolve `claude` to ~/.claude/bin/claude, and the wrapper
                   finds the real binary (FAIL when it does not: ~/.local/bin missing from PATH)
  launcher-model   bin/claude passes --model <plan-tier main>, or a --model / ANTHROPIC_MODEL / saved /model pick wins
  launch-caps      a launch through bin/claude in the last 24 h
  attach-live      no running claude session left in a stop scope
  linger           /var/lib/systemd/linger/<user> exists (FAIL when the guard is installed without it),
                   or oomguard.local.json "linger": false

Every probe is wrapped (an error is a WARN row), every subprocess capped at 2 s. Windows, no user
manager, a sandbox (foreign HOME on the real bus, or AGENTIC_MERCY_SANDBOX=1) or ``ci=True``: SKIP rows.
Design: docs/OOM-GUARD.md.
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
NAMES = ("oom-policy", "memwatch-unit", "memwatch-code", "restore-unit", "claude-launcher", "launcher-model",
         "launch-caps", "attach-live", "linger")
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


def _restore_unit(run, home, root, which=shutil.which):
    if not (root / "scripts" / "restore_sessions.py").exists():
        return SKIP, "scripts/restore_sessions.py absent"
    want = ogc.restore_enabled(home / ".claude" / "oomguard.local.json")
    state = _verb(run, "is-enabled", "claude-restore") or "unknown"
    if want and state == "enabled" and not which("tmux"):  # restore_sessions.py relaunches into tmux (FI-5)
        return WARN, "tmux missing: restore cannot run (sudo apt-get install -y tmux)"
    if want and state == "enabled":
        return PASS, "enabled"
    if not want and state != "enabled":
        return PASS, "disabled by oomguard.local.json"
    return WARN, f"restore_enabled={str(want).lower()} but claude-restore is {state}"


def _launcher(run, which):
    probes = [(label, flag, c) for label, flag, c in (("zsh", "-ic", "whence -p claude"),
                                                       ("bash", "-ic", "type -P claude"),
                                                       ("bash -l", "-lc", "type -P claude"))
              if which(label.split()[0])]
    if not probes:
        return SKIP, "no zsh or bash"
    bad = []
    for label, flag, cmd in probes:
        cp = run([label.split()[0], flag, cmd], timeout=TIMEOUT)
        if getattr(cp, "returncode", 1) == 124:
            bad.append(f"{label}: shell took > {TIMEOUT} s")
            continue
        lines = (getattr(cp, "stdout", "") or "").strip().splitlines()
        got = lines[-1].strip() if lines else ""
        if not got.endswith("/.claude/bin/claude"):
            bad.append(f"{label} resolves claude to {got or 'nothing'}")
    if which("bash"):  # the wrapper resolves, but can it find the real binary? (FI-11)
        cp = run(["bash", "-ic", "CLAUDE_LAUNCHER_PRINT_ARGV=1 claude"], timeout=TIMEOUT)
        text = (getattr(cp, "stdout", "") or "") + (getattr(cp, "stderr", "") or "")
        if getattr(cp, "returncode", 0) == 127 or "real binary not found" in text:
            return FAIL, "wrapper on PATH, real claude missing: add ~/.local/bin to PATH"
    labels = [p[0] for p in probes]
    joined = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]
    return (WARN, "; ".join(bad)) if bad else (PASS, joined + " -> ~/.claude/bin/claude")


def _launcher_model(run, root, home):
    """bin/claude passes the tier's main model unless --model, ANTHROPIC_MODEL or a saved /model pick
    chose one (docs/MODEL-ROUTING.md §6). Probe: CLAUDE_LAUNCHER_PRINT_ARGV=1 in a terminal-like env."""
    from lib import plan_tier  # noqa: PLC0415
    main = plan_tier.read().get("main")
    if not main:
        return WARN, "plan-tier.json has no `main` yet (the next session start refreshes it)"
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_WORKBENCH_SCOPE")}
    env.update(CLAUDE_LAUNCHER_PRINT_ARGV="1", HOME=str(home))
    cp = run(["bash", str(root / "bin" / "claude"), "--version"], timeout=TIMEOUT, env=env)
    argv = (getattr(cp, "stdout", "") or "").strip().splitlines()
    if "--model" in argv[:-1]:
        got = argv[argv.index("--model") + 1]
        return (PASS, f"--model {got} (tier main)") if got == main else (WARN, f"--model {got}, tier main is {main}")
    if os.environ.get("ANTHROPIC_MODEL"):
        return PASS, "ANTHROPIC_MODEL set"
    cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR") or home / ".claude") / "settings.json"
    try:
        saved = json.loads(cfg.read_text(encoding="utf-8")).get("model")
    except (OSError, ValueError, AttributeError):
        saved = None
    if saved:
        return PASS, f"settings.json model={saved} (your /model choice)"
    return WARN, f"launcher adds no --model (tier main {main}); is bin/claude current?"


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


def _linger_row(home, linger_dir):
    """Lingering on (FI-2): memwatch runs from boot and survives logout. FAIL when the guard is
    installed but the user manager only starts at login."""
    if not ogc.linger_wanted(home / ".claude" / "oomguard.local.json"):
        return PASS, "opted out (oomguard.local.json)"
    user = oomguard_setup._user()
    if (Path(linger_dir) / user).exists():
        return PASS, "Linger=yes"
    if (home / ".config" / "systemd" / "user" / "claude-memwatch.service").exists():
        return FAIL, f"memwatch only runs while you are logged in (run: loginctl enable-linger {user})"
    return WARN, "not enabled yet (installer/oomguard_setup.py --apply enables it)"


def _memwatch_code(run, root, proc_root):
    capped = lambda cmd, timeout=None, **_: run(cmd, timeout=TIMEOUT)  # noqa: E731 - every probe capped at 2 s
    stale = oomguard_setup.code_newer_than_daemon(capped, root, proc_root)
    if stale is None:
        return SKIP, "claude-memwatch not running (memwatch-unit covers it)"
    if stale:
        return WARN, "daemon older than hooks/tools/memwatch.py or its config; self-heal restarts it"
    return PASS, "daemon runs the code on disk"


def rows(root=".", *, run=None, which=None, home=None, bus=..., proc_root="/proc", ci=False, uid=None,
         now=None, linger_dir=None) -> list[tuple[str, str, str]]:
    root, home = Path(root).resolve(), Path(home or Path.home())
    run, which = run or plat.run, which or shutil.which
    injected = bus is not ...
    bus = plat.systemd_user_bus() if bus is ... else bus
    if ci:
        return [(n, SKIP, "ci") for n in NAMES]
    if oomguard_setup._sandboxed(home, injected):  # a sandbox HOME must not report the live machine's units (I11)
        return [(n, SKIP, "sandbox: foreign HOME or AGENTIC_MERCY_SANDBOX=1") for n in NAMES]
    if plat.IS_WINDOWS or bus is None or not which("systemctl"):
        return [(n, SKIP, "no systemd user manager") for n in NAMES]
    probes = (("oom-policy", lambda: _oom_policy(run, proc_root)), ("memwatch-unit", lambda: _memwatch_unit(run, home, root)),
              ("memwatch-code", lambda: _memwatch_code(run, root, proc_root)),
              ("restore-unit", lambda: _restore_unit(run, home, root, which)),
              ("claude-launcher", lambda: _launcher(run, which)),
              ("launcher-model", lambda: _launcher_model(run, root, home)),
              ("launch-caps", lambda: _launch_caps(time.time() if now is None else now)),
              ("attach-live", lambda: _attach(run, proc_root, bus, uid)),
              ("linger", lambda: _linger_row(home, linger_dir or oomguard_setup.LINGER_DIR)))
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
