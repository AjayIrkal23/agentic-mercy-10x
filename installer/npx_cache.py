"""npx cache self-heal for the MCP servers that start with ``npx -y <pkg>@<pin>``.

Right after a pin reconcile the first session starts several cold ``npx -y`` servers at once;
they race on the shared ``<npm cache>/_npx/<hash>`` entry and one can be left half-written
(``node_modules`` but no ``package.json``), after which that package fails every start with
CONNECTION_CLOSED. Two cache-only repairs, on every OS: :func:`prune_npx_cache` deletes such
entries, :func:`warm_npx` starts each re-pinned package once, one at a time. Both are driven by
``deps.reconcile_mcp_pins`` (daily self-heal, install pass, the ``mcp-roster`` repair).
Pure stdlib; the command runner is injectable: ``run(argv, timeout) -> (rc, stdout)``.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402


def _run(argv: list[str], timeout: float) -> tuple[int, str]:
    """(returncode, stdout when it succeeded). Stdin is closed so an MCP server started by the
    warm-up sees EOF and exits. Runs from the home directory: the hook's cwd is the project, and
    its ``.npmrc`` (``cache=``, ``registry=``) must not steer npm or the pinned ``npx -y`` (SEC1-05).
    Never raises."""
    cp = plat.run(argv, timeout=timeout, stdin_devnull=True, cwd=str(Path.home()))
    return cp.returncode, cp.stdout if cp.returncode == 0 and isinstance(cp.stdout, str) else ""


def npm_cache_root(run=None) -> Path:
    """npm's cache dir: ``npm config get cache``, else %LOCALAPPDATA%\\npm-cache (Windows) / ~/.npm."""
    rc, out = (run or _run)(["npm", "config", "get", "cache"], 30)
    line = out.strip().splitlines()[-1].strip() if rc == 0 and out.strip() else ""
    if line and line != "undefined":
        return Path(line)
    if plat.IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "npm-cache"
    return Path.home() / ".npm"


def _newest_mtime(d: Path) -> float:
    """The entry's newest mtime: the directory, ``node_modules`` and its direct children (npm fills
    ``node_modules`` and writes ``package.json`` last without touching the entry directory)."""
    nm = d / "node_modules"
    newest = max(d.stat().st_mtime, nm.stat().st_mtime)
    with os.scandir(nm) as it:
        for child in it:
            newest = max(newest, child.stat(follow_symlinks=False).st_mtime)
    return newest


def prune_npx_cache(cache_root, min_age_s: float = 600.0) -> list[str]:
    """Delete ``<cache_root>/_npx/<hash>`` entries that hold ``node_modules`` but no
    ``package.json``. Touches nothing outside ``_npx``; an entry whose newest mtime (see
    ``_newest_mtime``) is under ``min_age_s`` (10 min: a slow cold install, e.g. a postinstall that
    downloads a binary) is left alone, another session's npx may still be installing it.
    Returns the names removed."""
    removed: list[str] = []
    try:
        entries = sorted((Path(cache_root) / "_npx").iterdir())
    except OSError:
        return removed
    for d in entries:
        try:
            half = (d.is_dir() and not d.is_symlink() and (d / "node_modules").is_dir()
                    and not (d / "package.json").exists() and time.time() - _newest_mtime(d) >= min_age_s)
        except OSError:
            continue
        if half:
            shutil.rmtree(d, ignore_errors=True)
            if not d.exists():
                removed.append(d.name)
    return removed


def warm_npx(specs: list[str], run=None, timeout: float = 90) -> list[tuple[str, str]]:
    """Start each package once, ONE AT A TIME. A failure is tolerated: the point is the cached
    install, not the exit code. [(spec, WARMED | NOT-WARMED(rc=N))]."""
    run = run or _run
    out = []
    for spec in specs:
        rc, _ = run(["npx", "-y", spec, "--version"], timeout)
        out.append((spec, "WARMED" if rc == 0 else f"NOT-WARMED(rc={rc})"))
    return out


def maintenance(changed: list[tuple[str, str]], run=None) -> list[tuple[str, str]]:
    """Prune, then warm the packages whose pin just changed. ``changed`` = [(server, spec)];
    rows = [("npx-cache", "PRUNED n: [...]")] + [(server, "WARMED <spec>")]."""
    pruned = prune_npx_cache(npm_cache_root(run))
    rows = [("npx-cache", f"PRUNED {len(pruned)}: {pruned}")] if pruned else []
    warmed = warm_npx([spec for _, spec in changed], run)
    return rows + [(name, f"{status} {spec}") for (name, _), (spec, status) in zip(changed, warmed)]
