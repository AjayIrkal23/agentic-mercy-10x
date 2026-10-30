#!/usr/bin/env python3
"""selfheal-daily.py — session-start async exec: the once-a-day self-heal (autonomy WP-D).

Detached (``async: true``): a session never waits. Once per 24 h (``at`` in
``state/selfheal-daily.json``), one copy at a time (non-blocking ``selfheal-daily.lock``).
Independent steps, one failing never stops the others: ``mcp`` (re-add a missing manifest
server, pin + env + alwaysLoad reconcile), ``deps`` (base tools node/claude/uv/gh in ~/.local, then absent
CLIs, never upgrade, then the lean-ctx config merge), ``plan-tier`` (re-detect the plan tier), ``settings`` (re-render when the
template/manifest is newer, a pinned interpreter path is gone or the tier's model keys changed),
``oomguard`` (``oomguard_setup.ensure``), ``machines-split`` (keep the imported machines file small),
``vendor`` (``vendor_skill.py --all`` only on DRIFT),
``workflows`` (render on drift), ``library`` (rebuild library/INDEX.json on drift), ``mcp-inventory``
(regenerate the inventory reference when registrations changed; POSIX only), ``ponytail-board`` (the ponytail band
import of past sessions), ``learning-evolve`` (``instincts.py evolve``, last: it may use 660 s). Summary {"at","changed","errors",
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
import re
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
WORKFLOWS = _ROOT / "scripts" / "build_workflows.py"
LIB_INDEX = _ROOT / "scripts" / "build_library_index.py"
SPLIT = _ROOT / "scripts" / "split_machines_file.py"
PLAN_TIER = _ROOT / "hooks" / "plan-tier-detect.py"
INSTINCTS = Path(__file__).resolve().parent / "instincts.py"
INVENTORY = _ROOT / "scripts" / "mcp_inventory.py"
INVENTORY_MD = _ROOT / "skills" / "mcp-usage-standards" / "references" / "mcp-inventory.md"
INTERVAL_S = 24 * 3600
BUDGET_S = 1800.0
_LOG_MAX = 200_000
_CHANGED = ("PINNED", "ENV-SET", "INSTALLED", "ADDED", "OK(rendered", "VENDORED", "CREATED", "UPDATED",
            "APPENDED", "ENABLED", "MOVED", "REBUILT", "EVOLVED", "ALWAYS-LOAD")
_ERRORS = ("WARN", "FAIL", "MISSING")


class Ctx:
    def __init__(self, dry: bool, target: Path, budget: float):
        self.dry, self.target = dry, target
        self.deadline = time.time() + budget
        self.steps_ok = 0  # steps that ran and reported no error row
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
            + [("mcp-env", n, s) for n, s in deps.reconcile_mcp_env(dry_run=ctx.dry)]
            + [("mcp-load", n, s) for n, s in deps.reconcile_mcp_always_load(dry_run=ctx.dry)])


def _deps(ctx: Ctx):
    import deps  # type: ignore
    rows: list = []
    if not os.environ.get("AGENTIC_MERCY_SKIP_BASE_TOOLS"):  # node / claude / uv / gh (+ git on Windows), no admin
        import basetools  # type: ignore
        rows += basetools.ensure_base_tools(ctx.env(), deps._load_manifest(), ci=False, dry_run=ctx.dry)
    # an absent optional dep is the user's choice (A4-16)
    rows += deps.install_deps(ctx.env(), ci=False, dry_run=ctx.dry, skip_optional=True)
    import selfheal  # type: ignore  # a lean-ctx install or run may rewrite its config (F2): merge it back
    return [("dep", n, s) for n, s in rows] + [("config", *selfheal._configure_lean_ctx(deps, ctx.dry))]


def _settings(ctx: Ctx):
    import selfheal  # type: ignore
    st = ctx.target / "settings.json"
    if st.exists() and not selfheal._stale(st):
        return []
    if ctx.dry:
        return [("settings", "settings.json", "WOULD-RENDER (missing, template/manifest newer, or a pinned interpreter is gone)")]
    out: list = []
    selfheal._ensure_settings(ctx.target, ctx.env(), lambda k, n, s: out.append((k, n, s)))
    return out


def _tail(cp, n: int = 80) -> str:
    return ((cp.stdout or cp.stderr or "").strip().splitlines() or ["no output"])[-1][:n]


def _oomguard(ctx: Ctx):
    import oomguard_setup  # type: ignore
    out = []
    for r in oomguard_setup.ensure(dry=ctx.dry):
        name, _, status = r.partition(":")
        out.append(("oomguard", name.strip(), status.strip() or name.strip()))
    return out


def _machines_split(ctx: Ctx):
    if not SPLIT.is_file():
        return []
    cmd = [plat.python_exe(), str(SPLIT), "--apply"] + (["--dry-run"] if ctx.dry else [])
    r = plat.run(cmd, timeout=20)
    last = _tail(r)
    if r.returncode != 0:  # rc 2 = REFUSED until .gitignore has the journal lines
        return [("machines-split", "apply", f"WARN(rc={r.returncode}: {last})")]
    if "unchanged" in last or "SKIP" in last:
        return []
    return [("machines-split", "apply", f"WOULD-SPLIT({last})" if ctx.dry else f"MOVED({last})")]


def _plan_tier(ctx: Ctx):
    if not PLAN_TIER.is_file():
        return []
    if ctx.dry:
        return [("plan-tier", "detect", "WOULD-DETECT")]
    r = plat.run([plat.python_exe(), str(PLAN_TIER)], timeout=10)  # no --quiet: read the JSON
    try:
        d = json.loads((r.stdout or "{}").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return [("plan-tier", "detect", f"WARN(rc={r.returncode})")]
    return [("plan-tier", "detect", f"UPDATED tier={d.get('tier')}")] if d.get("changed") else []


def _workflows(ctx: Ctx):
    cmd = [plat.python_exe(), str(WORKFLOWS)]
    check = plat.run([*cmd, "--check"], timeout=60)
    if check.returncode == 0:
        return []
    if ctx.dry:
        return [("workflows", "render", "WOULD-RENDER (drift or not rendered)")]
    rc = plat.run(cmd, timeout=120).returncode
    return [("workflows", "render", "OK(rendered)" if rc == 0 else f"WARN(rc={rc})")]


def _library(ctx: Ctx):
    if not LIB_INDEX.exists() or not (_ROOT / "library" / "ecc").exists():
        return [("library", "index", "SKIP(absent)")]
    check = plat.run([plat.python_exe(), str(LIB_INDEX), "--check"], timeout=120)
    if check.returncode == 0:
        return []
    if ctx.dry:
        return [("library", "index", "WOULD-REBUILD")]
    rc = plat.run([plat.python_exe(), str(LIB_INDEX)], timeout=300).returncode
    return [("library", "index", "REBUILT" if rc == 0 else f"WARN(rc={rc})")]


def _public(md: str) -> str:
    """The inventory is tracked in a public repo: home paths become ``~`` and project-scope rows
    (another repo's path on this machine) are dropped (G6, machine data). Every spelling of home
    is scrubbed (render tokens use forward slashes on Windows), and the summary is recounted."""
    home = str(Path.home())
    forms = sorted({home, home.replace("\\", "/"), home.replace("/", "\\")}, key=len, reverse=True)
    lines = []
    for ln in md.splitlines(keepends=True):
        for h in forms:
            ln = ln.replace(h, "~")
        if " | project:" not in ln:
            lines.append(ln)
    rows = [ln.split("|")[2].strip() for ln in lines if ln.startswith("| `") and ln.count("|") > 2]
    n_user = rows.count("user")
    return "".join(re.sub(r"^\d+ user-scope, \d+ project/plugin-scope servers\.",
                          f"{n_user} user-scope, {len(rows) - n_user} project/plugin-scope servers.", ln)
                   for ln in lines)


def _mcp_inventory(ctx: Ctx):
    """Regenerates the inventory reference from the live ~/.claude.json (the only writer of that file);
    the hand-written preamble (everything before the first table header) is kept. Skipped on Windows:
    the tracked file is written on the committing machine only, or the replica's pull would abort."""
    if plat.IS_WINDOWS:
        return [("mcp-inventory", "mcp-inventory.md", "SKIP(replica)")]
    if not INVENTORY.is_file() or ctx.dry:
        return []
    r = plat.run([plat.python_exe(), str(INVENTORY), "--md"], timeout=30)
    out = _public(r.stdout or "")
    if r.returncode != 0 or not out.strip():
        return [("mcp-inventory", "mcp-inventory.md", f"WARN(rc={r.returncode})")]
    try:
        cur = INVENTORY_MD.read_text(encoding="utf-8")
    except OSError:
        cur = ""
    head = cur.split("| Server |", 1)[0] if "| Server |" in cur else ""
    new = head + (out[out.index("| Server |"):] if "| Server |" in out else out)
    if new == cur:
        return []
    if not plat.atomic_write(INVENTORY_MD, new):
        return [("mcp-inventory", "mcp-inventory.md", "WARN(write failed)")]
    return [("mcp-inventory", "mcp-inventory.md", "UPDATED")]


def _learning_evolve(ctx: Ctx):
    """Daily instincts evolve (docs/LEARNING.md): ollama only; DEFERRED when the box is down (quiet, retried tomorrow)."""
    if not INSTINCTS.is_file():
        return []
    if ctx.dry:
        return [("learning", "evolve", "WOULD-EVOLVE every project with >= 20 new observations")]
    cp = plat.run([plat.python_exe(), str(INSTINCTS), "evolve", "--budget", "600"], timeout=660)
    if cp.returncode != 0:
        return [("learning", "evolve", f"WARN(rc={cp.returncode})")]
    rows = []
    for ln in (cp.stdout or "").splitlines():
        if ln.startswith("evolved "):
            key, _, rest = ln[len("evolved "):].partition(":")
            rows.append(("learning", key.strip(), "EVOLVED " + rest.strip()))
        elif ln.endswith(" promoted"):
            rows.append(("learning", "global", "EVOLVED " + ln.strip()))
    return rows  # SKIP / DEFERRED / busy lines are not reported (nothing changed)


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
    cp = plat.run(cmd, timeout=900)
    if cp.returncode == 0:
        return [("vendor", "--all", f"VENDORED{note}")]
    # a moved tag (RefMoved) prints "WARN <skill>: <repo>@<ref> moved a -> b; ..." and exits 1 (SP-7)
    warn = next((ln.strip() for ln in (cp.stdout or "").splitlines() if ln.startswith("WARN ")), "")
    return [("vendor", "--all", f"WARN(rc={cp.returncode}" + (f": {warn[5:]}" if warn else "") + ")")]


# The import never revisits a session it wrote, so a live transcript would stay half-counted (and a
# band row under another key would count it twice): hide transcripts written in the last 24 h.
# shortcut: patches fs.readdirSync of ponytail-band-import.js (5.3.2), drop it once upstream skips live sessions.
_IDLE_ONLY = (
    "const fs=require('fs'),path=require('path'),list=fs.readdirSync;"
    "const idle=(d,f)=>{try{return Date.now()-fs.statSync(path.join(d,f)).mtimeMs>864e5}catch(e){return false}};"
    "fs.readdirSync=(d,...a)=>list(d,...a).filter(f=>typeof f!=='string'||!f.endsWith('.jsonl')||idle(d,f));"
    "require(process.argv[1]).run()"
)


def _ponytail_board(ctx: Ctx):
    """Adds past sessions to the ponytail board (`/ponytail band import`, which nobody types here).
    The live band misses sessions that started with mods switched off; the import skips sessions
    the ledger already has (~20 s over 6 GB of transcripts)."""
    try:
        meta = json.loads((ctx.target / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        script = Path(meta["plugins"]["ponytail@ponytail"][0]["installPath"]) / "hooks" / "ponytail-band-import.js"
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return []
    node = plat.node_exe()
    if not node or not script.is_file():
        return []
    if ctx.dry:
        return [("ponytail-board", "import", "WOULD-IMPORT past sessions")]
    cp = plat.run([node, "-e", _IDLE_ONLY, str(script)], timeout=300)
    return [("ponytail-board", "import", "OK" if cp.returncode == 0 else f"WARN(rc={cp.returncode})")]


# plan-tier before settings: a tier change makes settings.json stale (selfheal._tier_drift), and the
# same run's settings step then renders the new tier's model keys
STEPS = [("mcp", _mcp), ("deps", _deps), ("plan-tier", _plan_tier), ("settings", _settings),
         ("oomguard", _oomguard), ("machines-split", _machines_split), ("vendor", _vendor),
         ("workflows", _workflows), ("library", _library), ("mcp-inventory", _mcp_inventory),
         ("ponytail-board", _ponytail_board), ("learning-evolve", _learning_evolve)]


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
        step_ok = True
        for kind, n, status in rows:
            line = _line(kind, n, status)
            if log:
                _log(log, f"{kind} {n} {status}")
            verdict = _classify(status)
            if verdict == "changed":
                changed.append(line)
            elif verdict == "error":
                errors.append(line)
                step_ok = False
            if verdict or status.startswith("WOULD"):
                plan.append(line)
        ctx.steps_ok += step_ok
    return changed, errors, plan


def _write_summary(path: Path, prev: dict, changed: list[str], errors: list[str], stamp: bool = True) -> None:
    """``stamp=False``: errors still reported, no ``at`` -> ``_fresh`` is false, retry next session."""
    if prev.get("reported") is False:  # the aggregator has not shown the last run yet
        changed = [c for c in prev.get("changed") or [] if c not in changed] + changed
        errors = [e for e in prev.get("errors") or [] if e not in errors] + errors
    summary = {"changed": changed, "errors": errors, "reported": not (changed or errors)}
    if stamp:
        summary = {"at": _now().isoformat(timespec="seconds"), **summary}
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
                    ctx = Ctx(False, target, args.budget)
                    changed, errors, _ = _run_steps(ctx, state / "selfheal-daily.log")
                    _write_summary(summary, prev, changed, errors, stamp=ctx.steps_ok > 0)
    except Exception:  # noqa: BLE001 - never block or fail a session
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
