"""doctor_paths.py — doctor row ``cli-on-path``: every command Claude Code starts by name resolves on the
PATH your shell gives it.

F1 (a 16 GB laptop, 2026-10-30): node lived under ~/.local/opt/node-v24.22.1-linux-x64 with only node / npm
/ npx linked into ~/.local/bin, so `npm install -g` left lean-ctx, tdd-guard, pyright, pyright-langserver and
mmx off PATH. The lean-ctx MCP failed with ENOENT, the pyright-lsp plugin had no server, and both doctors
reported 0 FAIL. Checked here: the ``command`` of every user-scope stdio MCP server in ~/.claude.json
(``cmd /c <shim>`` unwrapped) and every npm-global CLI the installer links that npm installed
(``deps.npm_installed_bins``). PATH is what ``$SHELL -lic`` prints (bash or zsh, login + interactive: what a
terminal has), else this process's PATH, named in the detail. FAIL on a manifest server or a linked CLI
(``selfheal._repair`` re-runs the deps step, which links); WARN on a server the manifest does not declare,
and on Windows (no shell probe; the npm dir joins PATH only in a new terminal). Pure stdlib.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from lib import platform as plat  # noqa: E402

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
_MARK = "__AM_PATH__="
TIMEOUT = 5  # zsh -lic with nvm took 0.7 s on the owner's PC


def shell_path(run: Callable = plat.run, shell: str | None = None) -> str | None:
    """PATH as a login + interactive bash / zsh sets it (any other $SHELL: bash); None when the probe fails."""
    sh = shell or os.environ.get("SHELL") or "bash"
    if os.path.basename(sh) not in ("bash", "zsh"):
        sh = "bash"
    cp = run([sh, "-lic", f'printf "\\n{_MARK}%s\\n" "$PATH"'], timeout=TIMEOUT, stdin_devnull=True)
    if getattr(cp, "returncode", 1) != 0:
        return None
    for line in reversed((getattr(cp, "stdout", "") or "").splitlines()):
        if line.startswith(_MARK):
            return line[len(_MARK):]
    return None


def _resolve(cmd: str, path: str) -> str | None:
    if os.path.isabs(cmd) or "/" in cmd or "\\" in cmd:
        return cmd if os.path.isfile(cmd) and os.access(cmd, os.X_OK) else None
    return shutil.which(cmd, path=path)


def targets(live: dict, manifest: dict, npm_bins: list[str]) -> list[tuple[str, str, bool]]:
    """[(label, command, declared)]: the stdio MCP commands, then the linked npm CLIs (always declared)."""
    declared = {s.get("name") for s in manifest.get("mcp_servers", [])}
    out: list[tuple[str, str, bool]] = []
    for name, e in sorted((live or {}).items()):
        if not isinstance(e, dict) or e.get("url") or e.get("type") in ("http", "sse"):
            continue
        cmd, args = str(e.get("command") or ""), [str(a) for a in e.get("args") or []]
        if os.path.basename(cmd).lower() in ("cmd", "cmd.exe") and len(args) > 1 and args[0].lower() == "/c":
            cmd = args[1]
        if cmd:
            out.append((f"mcp {name}", cmd, name in declared))
    return out + [(n, n, True) for n in npm_bins]


def status(items: list[tuple[str, str, bool]], path: str, where: str = "your shell's PATH") -> tuple[str, str]:
    def name(label: str, cmd: str) -> str:
        return cmd if label == cmd else f"{label} ({cmd})"
    fail = [name(lb, c) for lb, c, decl in items if decl and not _resolve(c, path)]
    warn = [name(lb, c) for lb, c, decl in items if not decl and not _resolve(c, path)]
    if fail:
        return FAIL, (f"not on {where}: {', '.join(fail)} (the installer links npm globals into "
                      "~/.local/bin; the self-heal re-runs that step)")
    if warn:
        return WARN, f"not on {where} (servers the manifest does not declare): {', '.join(warn)}"
    return PASS, f"{len(items)} command(s) resolve on {where}"


def check(ci: bool, manifest: dict, config_file, *, run: Callable | None = None, environ=None,
          npm_bins: list[str] | None = None) -> tuple[str, str]:
    if ci:
        return SKIP, "ci"
    environ = os.environ if environ is None else environ
    try:
        live = json.loads(Path(config_file).read_text(encoding="utf-8")).get("mcpServers") or {}
    except (OSError, ValueError, AttributeError):
        live = {}
    if npm_bins is None:
        import deps  # noqa: PLC0415
        npm_bins = deps.npm_installed_bins(manifest)
    items = targets(live, manifest, npm_bins)
    if not items:
        return PASS, "no stdio MCP server or npm CLI to resolve"
    path = None if plat.IS_WINDOWS else shell_path(run or plat.run, environ.get("SHELL"))
    where = "your shell's PATH"
    if path is None:
        path = environ.get("PATH", "")
        where = "PATH" if plat.IS_WINDOWS else "this process's PATH (the shell probe failed)"
    st, det = status(items, path, where)
    return (WARN if plat.IS_WINDOWS and st == FAIL else st), det
