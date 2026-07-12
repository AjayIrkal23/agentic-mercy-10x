#!/usr/bin/env python3
"""deps.py — idempotent dependency + MCP-server installation (P6-T5).

Reads ``installer/manifest.json``. Every step is idempotent: a present tool is
SKIPPED (never reinstalled), a registered MCP server is SKIPPED. Under ``--ci``
every ``ci_stub`` step is skipped (CI has no network / no ``claude`` CLI; the
manifest is the contract the doctor asserts). Pure stdlib; all OS branching via
``hooks/lib/platform.py``. Nothing here raises — a failed optional step is a WARN.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_HOOKS = _ROOT / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402

MANIFEST = _ROOT / "installer" / "manifest.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _exec_tokens(env) -> dict:
    """Tokens for the installer's OWN subprocess commands — CLAUDE_DIR is the
    REAL path (not the ${HOME}/.claude render token, which only Claude Code
    expands). PYTHON/NODE may be multi-word (e.g. 'py -3')."""
    return {"PYTHON": env.python, "NODE": env.node, "CLAUDE_DIR": env.real_dir or str(plat.claude_dir())}


def _sub(cmd: list, tokens: dict) -> list:
    """Materialize a command template into argv, splitting a whole-element
    interpreter token (``{PYTHON}`` -> 'py -3' -> ['py','-3']) but doing a plain
    in-place replace for embedded path tokens (``{CLAUDE_DIR}/x.py``)."""
    out: list[str] = []
    for part in cmd:
        s = str(part)
        whole_token_hit = None
        for k, v in tokens.items():
            tok = "{" + k + "}"
            if s == tok:
                whole_token_hit = v
                break
        if whole_token_hit is not None:
            out.extend(str(whole_token_hit).split())
            continue
        for k, v in tokens.items():
            s = s.replace("{" + k + "}", str(v))
        out.append(s)
    return out


def install_deps(env, *, ci: bool = False, dry_run: bool = False) -> list[tuple[str, str]]:
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    for dep in manifest.get("deps", []):
        did = dep["id"]
        which = dep.get("which")
        if which and shutil.which(which):
            results.append((did, "PRESENT"))
            continue
        if ci and dep.get("ci_stub"):
            results.append((did, "SKIP(ci-stub)"))
            continue
        install_cmd = dep.get(f"install_{env.os_name}") or dep.get("install")
        if not install_cmd:
            results.append((did, "MISSING(no-installer)" if not dep.get("optional") else "SKIP(optional-absent)"))
            continue
        if dry_run:
            results.append((did, f"WOULD-INSTALL: {' '.join(install_cmd)}"))
            continue
        cp = plat.run(_sub(install_cmd, _exec_tokens(env)), timeout=600)
        results.append((did, "INSTALLED" if cp.returncode == 0 else f"WARN(rc={cp.returncode})"))
    return results


def register_mcps(env, *, ci: bool = False, dry_run: bool = False) -> list[tuple[str, str]]:
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    if not env.claude_cli:
        return [(s["name"], "SKIP(no-claude-cli)") for s in manifest.get("mcp_servers", [])]
    # one listing to decide presence
    listed = ""
    lc = plat.run(["claude", "mcp", "list"], timeout=30)
    if lc.returncode == 0:
        listed = lc.stdout or ""
    for srv in manifest.get("mcp_servers", []):
        name = srv["name"]
        if name in listed:
            results.append((name, "PRESENT"))
            continue
        if ci and srv.get("ci_stub"):
            results.append((name, "SKIP(ci-stub)"))
            continue
        cmd = _sub(srv["add"], _exec_tokens(env))
        if dry_run:
            results.append((name, f"WOULD-ADD: {' '.join(cmd)}"))
            continue
        cp = plat.run(cmd, timeout=60)
        results.append((name, "ADDED" if cp.returncode == 0 else f"WARN(rc={cp.returncode})"))
    return results


def run_post_steps(env, *, ci: bool = False, dry_run: bool = False) -> list[tuple[str, str]]:
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    for step in manifest.get("post_steps", []):
        sid = step["id"]
        cmd = _sub(step["cmd"], _exec_tokens(env))
        target = Path(cmd[1]) if len(cmd) > 1 else None
        if target and not target.exists():
            results.append((sid, "SKIP(script-absent)" if step.get("optional") else "MISSING(script)"))
            continue
        if dry_run:
            results.append((sid, f"WOULD-RUN: {' '.join(cmd)}"))
            continue
        cp = plat.run(cmd, timeout=300)
        ok = cp.returncode == 0
        results.append((sid, "OK" if ok else (f"WARN(rc={cp.returncode})" if step.get("optional") else f"FAIL(rc={cp.returncode})")))
    return results


if __name__ == "__main__":
    from detect import detect  # type: ignore

    e = detect()
    for label, rows in [("deps", install_deps(e, dry_run=True)),
                        ("mcp", register_mcps(e, dry_run=True)),
                        ("post", run_post_steps(e, dry_run=True))]:
        print(f"== {label} ==")
        for name, status in rows:
            print(f"  {name:22s} {status}")
