#!/usr/bin/env python3
"""oomguard_setup.py — install the OOM guard at user level, idempotently, no sudo, no approval.

  L0  ~/.config/systemd/user.conf.d/10-oom.conf    DefaultOOMPolicy=continue for every new scope
  L3  ~/.config/systemd/user/claude-memwatch.service + claude-restore.service (rendered templates
      from hooks/tools/oomguard/), daemon-reload, enable; a changed memwatch unit under a running service
      is `try-restart`ed; the restore oneshot only needs the reload
  L1  a PATH block at the END of ~/.zshrc / ~/.bashrc (after lean-ctx's block) so $HOME/.claude/bin/claude
      resolves first; a missing rc file is never created
      attach_live(): today's running claude sessions move into claude-safe-<pid>.scope (OOMPolicy=continue)

Files we own carry the marker ``agentic-mercy oomguard``; a file without it is the user's and is kept.
``--dry-run`` (the default) prints WOULD-* rows and changes nothing (only read-only ``systemctl show``);
``--apply`` does it. Windows or no systemd user manager: one SKIP row. Called by render.py post_steps,
selfheal-daily and hooks/memwatch-ensure.py. Design: docs/OOM-GUARD.md.
unit_state() / start_unit() / unit_file(): the one-shot path hooks/memwatch-ensure.py calls (hooks/*.py
carry no unit-manager literal: hooks/tests/test_index_lifecycle.py grep gate).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (str(_HERE), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import oomguard_config as ogc  # noqa: E402
from lib import platform as plat  # noqa: E402

MARK = "agentic-mercy oomguard"
BEGIN = "# >>> claude-workbench >>>"
END = "# <<< claude-workbench <<<"
PATH_LINE = 'export PATH="$HOME/.claude/bin:$PATH"'
NO_MANAGER = "SKIP: no systemd user manager"
_CHANGED = ("CREATED", "UPDATED")


def _render(text: str, subs: dict) -> str:
    for k, v in subs.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def _subs(root: Path) -> dict:
    return {"PY": plat.python_exe(), "HOOKS": str(root / "hooks"), "CLAUDE_DIR": str(root)}


def _rc(cp, ok: str = "OK") -> str:
    rc = getattr(cp, "returncode", 1)
    return ok if rc == 0 else f"WARN(rc={rc})"


def _ensure_file(path: Path, wanted: str, dry: bool, label: str, kept: str) -> str:
    if path.exists():
        cur = path.read_text(encoding="utf-8", errors="replace")
        if cur == wanted:
            return f"{label}: PRESENT"
        if MARK not in cur:
            return f"{label}: KEPT ({kept})"
        if dry:
            return f"{label}: WOULD-UPDATE"
        return f"{label}: UPDATED" if plat.atomic_write(path, wanted) else f"{label}: WARN(write failed)"
    if dry:
        return f"{label}: WOULD-CREATE"
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"{label}: CREATED" if plat.atomic_write(path, wanted) else f"{label}: WARN(write failed)"


def path_block() -> str:
    """$HOME/.claude, not the repo root: the rc file travels with the user."""
    return f"\n{BEGIN}\n{PATH_LINE}\n{END}\n"


def _ensure_rc(rc: Path, dry: bool) -> str:
    if not rc.is_file():
        return f"{rc.name}: SKIP(absent)"
    text = rc.read_text(encoding="utf-8", errors="replace")
    if BEGIN in text and PATH_LINE in text:
        return f"{rc.name}: PRESENT"
    if dry:
        return f"{rc.name}: WOULD-APPEND PATH block"
    with open(rc, "a", encoding="utf-8") as fh:  # append only: a shell rc is never rewritten
        fh.write(("" if text.endswith("\n") or not text else "\n") + path_block())
    return f"{rc.name}: APPENDED PATH block"


def _verb(run, *args, timeout: float = 30) -> tuple[int, str]:
    cp = run(["systemctl", "--user", *args], timeout=timeout)
    return getattr(cp, "returncode", 1), (getattr(cp, "stdout", "") or "").strip()


UNIT = "claude-memwatch"
HOOK_TIMEOUT = 5.0


def unit_file(home=None) -> Path:
    """~/.config/systemd/user/claude-memwatch.service (the file ensure() renders)."""
    return Path(home or Path.home()) / ".config" / "systemd" / "user" / f"{UNIT}.service"


def unit_state(*, run=None, which=None, bus=..., timeout: float = HOOK_TIMEOUT) -> str:
    """'active' | 'inactive' | 'unknown' for claude-memwatch.

    unknown = Windows, no user bus, no systemctl on PATH, or a hung / unstartable systemctl (plat.run rc 124 / 127).
    unknown says nothing about the unit, so callers never install or start on it."""
    run = run or plat.run
    which = which or shutil.which
    bus = plat.systemd_user_bus() if bus is ... else bus
    if plat.IS_WINDOWS or bus is None or not which("systemctl"):
        return "unknown"
    rc, out = _verb(run, "is-active", UNIT, timeout=timeout)
    if rc in (124, 127):
        return "unknown"
    return "active" if out == "active" else "inactive"


def start_unit(*, run=None, timeout: float = HOOK_TIMEOUT) -> int:
    """systemctl --user start claude-memwatch; the rc (plat.run never raises)."""
    return _verb(run or plat.run, "start", UNIT, timeout=timeout)[0]


def _memwatch(run, dry: bool, changed: bool = False) -> str:
    """enable --now when not enabled+active; try-restart when the unit file changed under a running service."""
    enabled = _verb(run, "is-enabled", UNIT, timeout=10)[1] == "enabled"
    active = _verb(run, "is-active", UNIT, timeout=10)[1] == "active"
    if enabled and active:
        if not changed:
            return "claude-memwatch: OK"
        if dry:
            return "claude-memwatch: WOULD-RESTART"
        rc, _ = _verb(run, "try-restart", UNIT, timeout=60)
        return "claude-memwatch: " + ("RESTARTED" if rc == 0 else f"WARN(try-restart rc={rc})")
    if dry:
        return "claude-memwatch: WOULD-ENABLE"
    rc, _ = _verb(run, "enable", "--now", UNIT, timeout=60)
    return "claude-memwatch: " + ("ENABLED" if rc == 0 else "WARN(enable failed)")


def _restore(run, dry: bool, root: Path, local_cfg: Path) -> str:
    if not (root / "scripts" / "restore_sessions.py").exists():
        return "claude-restore: SKIP(restore_sessions.py absent)"
    enabled = _verb(run, "is-enabled", "claude-restore", timeout=10)[1] == "enabled"
    if ogc.restore_enabled(local_cfg):
        if enabled:
            return "claude-restore: OK"
        if dry:
            return "claude-restore: WOULD-ENABLE"
        return "claude-restore: " + ("ENABLED" if _verb(run, "enable", "claude-restore")[0] == 0 else "WARN(enable failed)")
    if not enabled:
        return "claude-restore: DISABLED"
    if dry:
        return "claude-restore: WOULD-DISABLE"
    rc, _ = _verb(run, "disable", "--now", "claude-restore")
    return "claude-restore: " + ("DISABLED" if rc == 0 else f"WARN(rc={rc})")


def ensure(dry: bool = False, *, home=None, run=None, which=None, bus=..., root=None, proc_root="/proc",
           uid=None) -> list[str]:
    """Bring L0/L1/L3 to the wanted state; one row per item. Never raises on a probe; never needs root."""
    home = Path(home or Path.home())
    run = run or plat.run
    which = which or shutil.which
    root = Path(root or _ROOT)
    bus = plat.systemd_user_bus() if bus is ... else bus
    if plat.IS_WINDOWS or bus is None or not which("systemctl"):
        return [NO_MANAGER]
    tmpl, subs = root / "hooks" / "tools" / "oomguard", _subs(root)
    rows = [_ensure_file(home / ".config" / "systemd" / "user.conf.d" / "10-oom.conf",
                         (tmpl / "10-oom.conf").read_text(encoding="utf-8"), dry, "drop-in 10-oom.conf",
                         "user file differs; wanted DefaultOOMPolicy=continue")]
    for unit in ("claude-memwatch.service", "claude-restore.service"):
        rows.append(_ensure_file(home / ".config" / "systemd" / "user" / unit,
                                 _render((tmpl / unit).read_text(encoding="utf-8"), subs), dry, f"unit {unit}",
                                 "user unit"))
    changed = any(r.rsplit(": ", 1)[-1] in _CHANGED for r in rows)
    if dry:
        rows.append("systemctl daemon-reload: " + ("WOULD-RUN" if any("WOULD-" in r for r in rows) else "OK"))
    elif changed:
        rows.append("systemctl daemon-reload: " + _rc(run(["systemctl", "--user", "daemon-reload"], timeout=30)))
    else:
        rows.append("systemctl daemon-reload: OK(nothing changed)")
    unit_changed = rows[1].rsplit(": ", 1)[-1] in _CHANGED + ("WOULD-CREATE", "WOULD-UPDATE")
    rows.append(_memwatch(run, dry, changed=unit_changed))  # after the reload: the new ExecStart must be loaded first
    rows.append(_restore(run, dry, root, home / ".claude" / "oomguard.local.json"))
    for rc in (home / ".zshrc", home / ".bashrc"):
        rows.append(_ensure_rc(rc, dry))
    rows += attach_live(dry, run=run, proc_root=proc_root, bus=bus, uid=uid)  # after the reload: item 15
    return rows


# --------------------------------------------------------------------------- #
# attach_live: move running sessions into continue-scopes
# --------------------------------------------------------------------------- #
def _status(proc_root: Path, pid: int) -> dict:
    out = {}
    try:
        with open(proc_root / str(pid) / "status", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                key, _, val = line.partition(":")
                if key in ("PPid", "Uid"):
                    out[key] = int(val.split()[0])
    except (OSError, ValueError, IndexError):
        pass
    return out


def _comm(proc_root: Path, pid: int) -> str:
    try:
        return (proc_root / str(pid) / "comm").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def live_roots(proc_root="/proc", uid=None) -> tuple[list[int], dict]:
    """(claude session root pids owned by ``uid``, children map). A claude whose ancestors hold another
    claude is part of that session, not a root."""
    root = Path(proc_root)
    uid = os.getuid() if uid is None and hasattr(os, "getuid") else uid
    try:
        pids = [int(e.name) for e in os.scandir(root) if e.name.isdigit()]
    except OSError:
        return [], {}
    ppid, children, claude = {}, {}, set()
    for pid in pids:
        st = _status(root, pid)
        ppid[pid] = st.get("PPid", 0)
        children.setdefault(ppid[pid], []).append(pid)
        if st.get("Uid") == uid and _comm(root, pid) == "claude":
            claude.add(pid)
    roots = []
    for pid in sorted(claude):
        cur, seen, nested = ppid.get(pid, 0), {pid}, False
        while cur > 1 and cur not in seen:
            if cur in claude:
                nested = True
                break
            seen.add(cur)
            cur = ppid.get(cur, 0)
        if not nested:
            roots.append(pid)
    return roots, children


def _tree(pid: int, children: dict) -> list[int]:
    out, todo = [], [pid]
    while todo:
        cur = todo.pop(0)
        if cur in out:
            continue
        out.append(cur)
        todo.extend(sorted(children.get(cur, [])))
    return out


def attach_live(dry: bool, *, run=None, proc_root="/proc", bus=..., uid=None) -> list[str]:
    run = run or plat.run
    bus = plat.systemd_user_bus() if bus is ... else bus
    if plat.IS_WINDOWS or bus is None:
        return [NO_MANAGER]
    roots, children = live_roots(proc_root, uid)
    rows = []
    for pid in roots:
        scope = plat.cgroup_of(pid, proc_root)
        if not scope:
            rows.append(f"attach pid {pid}: SKIP(no cgroup)")
            continue
        out = (getattr(run(["systemctl", "--user", "show", scope, "-p", "OOMPolicy"], timeout=5), "stdout", "") or "")
        if out.strip().partition("=")[2].strip() == "continue":
            rows.append(f"attach pid {pid}: SKIP(already continue)")
            continue
        pids = _tree(pid, children)
        if dry:
            rows.append(f"attach pid {pid}: WOULD-ATTACH ({len(pids)} pids)")
            continue
        cmd = ["busctl", "--user", "call", "org.freedesktop.systemd1", "/org/freedesktop/systemd1",
               "org.freedesktop.systemd1.Manager", "StartTransientUnit", "ssa(sv)a(sa(sv))",
               f"claude-safe-{pid}.scope", "fail", "3", "PIDs", "au", str(len(pids)), *[str(p) for p in pids],
               "OOMPolicy", "s", "continue", "ManagedOOMPreference", "s", "avoid", "0"]
        rc = getattr(run(cmd, timeout=10), "returncode", 1)
        rows.append(f"attach pid {pid}: " + (f"MOVED ({len(pids)} pids)" if rc == 0 else f"WARN(rc={rc})"))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Install the OOM guard at user level (docs/OOM-GUARD.md)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="make the changes")
    g.add_argument("--dry-run", action="store_true", help="print what would change (default)")
    args = ap.parse_args(argv)
    try:
        for row in ensure(dry=not args.apply):
            print(row)
    except Exception as exc:  # noqa: BLE001 - rows carry WARN; the installer never fails on the guard
        print(f"oomguard: WARN({type(exc).__name__}: {exc})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
