#!/usr/bin/env python3
"""Portable, fail-OPEN launcher for the graphify MCP server.

Replaces the bash pair ``graphify-mcp-launcher.sh`` + ``graphify-runner.sh``.
Two problems those had, fixed here:

  1. **Failed CLOSED.** The old launcher ran ``exit 1`` when no ``graph.json``
     existed for the active workspace, which took the WHOLE graphify MCP offline
     for any project without a graph. This launcher NEVER exits non-zero for a
     missing graph: it resolves the workspace graph if present, otherwise starts
     ``graphify.serve`` with no graph so the MCP comes up and reports
     "not built" (``graph_stats``) instead of a connection failure.
  2. **Not portable.** The old runner hardcoded ``/usr/bin/python3.13`` and a
     Cursor-era venv. This one discovers the serve interpreter (the graphify
     venv that has both ``graphify`` and ``mcp`` importable) and works on
     Windows and Ubuntu (all OS branching via lib/platform.py).

``graphify.serve`` is a module (there is no ``graphify serve`` CLI subcommand)
and needs the ``mcp`` package, so it runs under the graphify *serve venv*
(``~/.local/share/cursor-graphify-venv`` by default; override with
``GRAPHIFY_VENV`` / ``GRAPHIFY_PYTHON`` + ``GRAPHIFY_SITE_PACKAGES``), NOT the
uv-tool CLI interpreter (which lacks ``mcp``).

Any explicit ``*.json`` argument passed by the MCP client is respected untouched.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

try:
    from lib import platform as _plat  # noqa: E402
    _IS_WINDOWS = _plat.IS_WINDOWS
except Exception:  # pragma: no cover - launcher must never hard-crash on import
    _plat = None
    _IS_WINDOWS = os.name == "nt"  # platform.py owns OS detection; this is a fallback

HOME = Path.home()
DEFAULT_VENV = HOME / ".local" / "share" / "cursor-graphify-venv"


# --------------------------------------------------------------------------- #
# Serve interpreter discovery (must have graphify.serve AND mcp importable)
# --------------------------------------------------------------------------- #
def _venv_python(venv: Path) -> Path | None:
    cand = (venv / "Scripts" / "python.exe") if _IS_WINDOWS else (venv / "bin" / "python")
    return cand if cand.is_file() else None


def _serve_command(graph: str | None) -> tuple[list[str], dict]:
    """Return (argv, env) that runs ``python -m graphify.serve [graph]``.

    Resolution order for the interpreter:
      1. GRAPHIFY_PYTHON (+ optional GRAPHIFY_SITE_PACKAGES on PYTHONPATH),
      2. the graphify serve venv (GRAPHIFY_VENV or ~/.local/share/cursor-graphify-venv)
         used via its own bin/python (no PYTHONPATH juggling),
      3. last resort: this launcher's own interpreter (may lack graphify/mcp —
         serve then errors gracefully, still no exit-1-on-missing-graph).
    """
    env = dict(os.environ)
    env.pop("PYTHONEXECUTABLE", None)
    env.pop("PYTHONHOME", None)

    py: str | None = None
    explicit_py = os.environ.get("GRAPHIFY_PYTHON")
    if explicit_py and Path(explicit_py).exists():
        py = explicit_py
        sp = os.environ.get("GRAPHIFY_SITE_PACKAGES")
        if sp:
            env["PYTHONPATH"] = sp + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    if py is None:
        venv = Path(os.environ.get("GRAPHIFY_VENV") or DEFAULT_VENV)
        vpy = _venv_python(venv)
        if vpy is not None:
            py = str(vpy)

    if py is None:
        py = _plat.python_exe() if _plat is not None else (sys.executable or "python3")

    argv = [py, "-m", "graphify.serve"]
    if graph:
        argv.append(graph)
    return argv, env


# --------------------------------------------------------------------------- #
# Graph resolution (fail-open: None -> serve starts without a graph)
# --------------------------------------------------------------------------- #
def _graph_from_dir(d: Path) -> Path | None:
    g = d / "graphify-out" / "graph.json"
    return g if g.is_file() else None


def _resolve_graph(argv: list[str]) -> str | None:
    # 1) an explicit *.json arg from the MCP client wins.
    for a in argv:
        if a.endswith(".json") and Path(a).is_file():
            return a
    # 2) GRAPHIFY_GRAPH override.
    env_graph = os.environ.get("GRAPHIFY_GRAPH")
    if env_graph and Path(env_graph).is_file():
        return env_graph
    # 3) workspace env vars (Claude/Cursor set these).
    for var in ("CLAUDE_PROJECT_DIR", "CURSOR_PROJECT_DIR", "WORKSPACE_FOLDER_PATHS"):
        val = os.environ.get(var)
        if not val:
            continue
        cand = val
        if var == "WORKSPACE_FOLDER_PATHS" and val.lstrip().startswith("["):
            try:
                parsed = json.loads(val)
                cand = parsed[0] if isinstance(parsed, list) and parsed else ""
            except Exception:
                cand = ""
        if cand:
            g = _graph_from_dir(Path(cand))
            if g is not None:
                return str(g)
    # 4) walk up from CWD to the nearest graphify-out/graph.json.
    try:
        cur = Path(os.getcwd()).resolve()
    except OSError:
        cur = None
    for _ in range(40):
        if cur is None:
            break
        g = _graph_from_dir(cur)
        if g is not None:
            return str(g)
        if cur.parent == cur:
            break
        cur = cur.parent
    # 5) not found -> None; main() falls back to an empty placeholder graph.
    return None


def _placeholder_graph() -> str | None:
    """Ensure a minimal empty graph.json exists and return its path.

    ``graphify.serve`` itself fails CLOSED on a missing graph file, so the true
    fail-open path is to hand it a valid-but-empty graph: the MCP comes up and
    ``graph_stats`` reports an empty graph ("not built") instead of a connection
    failure. When index-lifecycle later builds the real graph, the next MCP
    start picks it up (serve does not hot-reload — same as before)."""
    try:
        base = (_plat.hooks_dir() if _plat is not None else _HOOKS) / ".state" / "graphify"
        base.mkdir(parents=True, exist_ok=True)
        gp = base / "empty-graph.json"
        if not gp.is_file():
            gp.write_text('{"nodes": [], "edges": []}', encoding="utf-8")
        return str(gp)
    except OSError:
        return None


def main() -> int:
    incoming = sys.argv[1:]
    graph = _resolve_graph(incoming) or _placeholder_graph()
    argv, env = _serve_command(graph)

    # Become the serve process so the MCP client's stdio talks to it directly.
    if not _IS_WINDOWS:
        try:
            os.execve(argv[0], argv, env)  # replaces this process image
        except OSError:
            pass  # fall through to subprocess (fail-open)
    import subprocess
    try:
        return subprocess.run(argv, env=env).returncode
    except Exception:  # noqa: BLE001 - never crash the MCP launch
        return 0


if __name__ == "__main__":
    sys.exit(main())
