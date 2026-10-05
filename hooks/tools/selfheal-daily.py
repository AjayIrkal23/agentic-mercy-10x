#!/usr/bin/env python3
"""selfheal-daily.py — session-start async exec: the once-a-day self-heal (autonomy WP-D).

Detached (``async: true``): a session never waits. Once per 24 h (``at`` in
``state/selfheal-daily.json``), one copy at a time (non-blocking ``selfheal-daily.lock``).
Independent steps, one failing never stops the others: ``mcp`` (re-add a missing manifest
server, pin + env reconcile), ``deps`` (base tools node/claude/uv/gh in ~/.local, then absent
CLIs, never upgrade), ``settings`` (re-render when the template/manifest is newer),
``vendor`` (``vendor_skill.py --all`` only on DRIFT). Summary {"at","changed","errors",
"reported"} for the aggregator; names / specs / return codes to ``state/selfheal-daily.log``:
no env, no tokens. ``--dry-run`` prints the plan and writes nothing. No-op for
CLAUDE_HOOK_DOCTOR, link-doctor's probe payload and pytest (``PYTEST_CURRENT_TEST`` unless
``SELFHEAL_DAILY_ALLOW_TEST=1``: a test firing the session-start chain must never heal the
LIVE install). Prints ``{}``; never raises.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
_ROOT = _HOOKS.parent
for _p in (str(_HOOKS), str(_ROOT / "installer"), str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from daily_lock import try_lock as _try_lock  # noqa: E402
from lib import platform as plat  # noqa: E402

VENDOR = _ROOT / "scripts" / "vendor_skill.py"
INTERVAL_S = 24 * 3600
BUDGET_S = 1800.0
_LOG_MAX = 200_000
_CHANGED = ("PINNED", "ENV-SET", "INSTALLED", "ADDED", "OK(rendered", "VENDORED")
_ERRORS = ("WARN", "FAIL", "MISSING")


class Ctx:
    def __init__(self, dry: bool, target: Path, budget: float):
        self.dry, self.target = dry, target
        self.deadline = time.time() + budget
        self._env = None

    def env(self):
        if self._env is None:
            import detect  # type: ignore
            self._env = detect.detect()
        return self._env


# --------------------------------------------------------------------------- #
# steps: fn(ctx) -> [(kind, name, status)]
# --------------------------------------------------------------------------- #
def _mcp(ctx: Ctx):
    import deps  # type: ignore
    # missing manifest servers first (a failed restore leaves one unregistered), then pin + env
    return ([("mcp", n, s) for n, s in deps.register_mcps(ctx.env(), ci=False, dry_run=ctx.dry)
             if not s.startswith(("PRESENT", "SKIP"))]
            + [("mcp-pin", n, s) for n, s in deps.reconcile_mcp_pins(dry_run=ctx.dry)]
            + [("mcp-env", n, s) for n, s in deps.reconcile_mcp_env(dry_run=ctx.dry)])


def _deps(ctx: Ctx):
    import deps  # type: ignore
    rows: list = []
    if not os.environ.get("AGENTIC_MERCY_SKIP_BASE_TOOLS"):  # node / claude / uv / gh, no sudo
        import userspace  # type: ignore
        rows += userspace.ensure_userspace(ctx.env(), deps._load_manifest(), ci=False, dry_run=ctx.dry)
    rows += deps.install_deps(ctx.env(), ci=False, dry_run=ctx.dry)
    return [("dep", n, s) for n, s in rows]


def _settings(ctx: Ctx):
    import selfheal  # type: ignore
    st = ctx.target / "settings.json"
    if st.exists() and not selfheal._stale(st):
        return []
    if ctx.dry:
        return [("settings", "settings.json", "WOULD-RENDER (missing, or template/manifest newer)")]
    out: list = []
    selfheal._ensure_settings(ctx.target, ctx.env(), lambda k, n, s: out.append((k, n, s)))
    return out


def _vendor(ctx: Ctx):
    cmd = [plat.python_exe(), str(VENDOR), "--all"]
    check = plat.run([*cmd, "--check"], timeout=180)
    if check.returncode == 0:  # OK or BEHIND (information only)
        return []
    if check.returncode != 1:
        return [("vendor", "check", f"WARN(rc={check.returncode})")]
    drifted = [ln.split()[0] for ln in (check.stdout or "").splitlines()
               if ln.split() and ln.split()[-1].startswith("DRIFT")]
    note = f" (drift: {', '.join(drifted)})" if drifted else ""
    if ctx.dry:
        return [("vendor", "--all", f"WOULD-RE-VENDOR{note}")]
    rc = plat.run(cmd, timeout=900).returncode
    return [("vendor", "--all", f"VENDORED{note}" if rc == 0 else f"WARN(rc={rc})")]


STEPS = [("mcp", _mcp), ("deps", _deps), ("settings", _settings), ("vendor", _vendor)]


# --- plumbing ---------------------------------------------------------------- #
def _classify(status: str):
    if status.startswith(_CHANGED):
        return "changed"
    return "error" if status.startswith(_ERRORS) else None


def _line(kind: str, name: str, status: str) -> str:
    tail = " (restart to apply)" if kind == "mcp-pin" and status.startswith("PINNED") else ""
    return f"{kind} {name}: {status}{tail}"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _log(path: Path, text: str) -> None:
    try:
        if path.exists() and path.stat().st_size > _LOG_MAX:
            path.write_text("\n".join(path.read_text(encoding="utf-8").splitlines()[-400:]) + "\n",
                            encoding="utf-8")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{_now().isoformat(timespec='seconds')} {text}\n")
    except OSError:
        pass


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _is_probe() -> bool:
    """link-doctor fires every link with session_id 'link-doctor' (and does not always set
    CLAUDE_HOOK_DOCTOR): a probe must never touch the live registrations."""
    try:
        if sys.stdin.isatty():
            return False
        return json.loads(sys.stdin.read(65536) or "{}").get("session_id") == "link-doctor"
    except (OSError, ValueError, AttributeError):
        return False


def _blocked() -> bool:
    if os.environ.get("CLAUDE_HOOK_DOCTOR"):
        return True
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) and not os.environ.get("SELFHEAL_DAILY_ALLOW_TEST")


def _fresh(prev: dict) -> bool:
    try:
        age = (_now() - dt.datetime.fromisoformat(str(prev["at"]))).total_seconds()
    except (KeyError, ValueError, TypeError):
        return False
    return 0 <= age < INTERVAL_S


def _run_steps(ctx: Ctx, log: Path | None):
    """(changed lines, error lines, plan lines); one failing step never stops the rest."""
    changed: list[str] = []
    errors: list[str] = []
    plan: list[str] = []
    for name, fn in STEPS:
        if time.time() > ctx.deadline:
            errors.append(f"step {name} skipped: time budget used")
            continue
        try:
            rows = fn(ctx)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"step {name} failed: {type(exc).__name__}: {str(exc)[:120]}")
            if log:
                _log(log, errors[-1])
            continue
        for kind, n, status in rows:
            line = _line(kind, n, status)
            if log:
                _log(log, f"{kind} {n} {status}")
            verdict = _classify(status)
            if verdict == "changed":
                changed.append(line)
            elif verdict == "error":
                errors.append(line)
            if verdict or status.startswith("WOULD"):
                plan.append(line)
    return changed, errors, plan


def _write_summary(path: Path, prev: dict, changed: list[str], errors: list[str]) -> None:
    if prev.get("reported") is False:  # the aggregator has not shown the last run yet
        changed = [c for c in prev.get("changed") or [] if c not in changed] + changed
        errors = [e for e in prev.get("errors") or [] if e not in errors] + errors
    summary = {"at": _now().isoformat(timespec="seconds"), "changed": changed, "errors": errors,
               "reported": not (changed or errors)}
    plat.locked_update(path, lambda _old: summary)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="once-a-day async self-heal")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; change and write nothing")
    ap.add_argument("--budget", type=float, default=BUDGET_S, help="seconds before remaining steps are skipped")
    args = ap.parse_args(argv)
    target = plat.claude_dir()
    if args.dry_run:
        import selfheal  # type: ignore
        selfheal.pin_config_dir(target)
        _, _, plan = _run_steps(Ctx(True, target, args.budget), None)
        print("\n".join(f"plan: {p}" for p in plan) or "plan: nothing to change")
        return 0
    try:
        if not _blocked() and not _is_probe():
            state = plat.state_dir()
            summary = state / "selfheal-daily.json"
            with _try_lock(state / "selfheal-daily.lock") as got:
                prev = _read(summary)
                if got and not _fresh(prev):
                    import selfheal  # type: ignore
                    selfheal.pin_config_dir(target)  # never CLAUDE_CONFIG_DIR=~/.claude for the CLI
                    changed, errors, _ = _run_steps(Ctx(False, target, args.budget), state / "selfheal-daily.log")
                    _write_summary(summary, prev, changed, errors)
    except Exception:  # noqa: BLE001 - never block or fail a session
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
