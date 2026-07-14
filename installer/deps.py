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
    expands). PYTHON/NODE may be multi-word (e.g. 'py -3').

    Every ``{CLAUDE_DIR}/...`` the installer *executes* (post-step scripts, the
    graphify launcher) is a REPO-LOCAL file. When installing FROM a checkout that
    is not yet ~/.claude — a fresh `git clone` elsewhere, or the CI runner where
    `actions/checkout` lands the repo in the workspace and ~/.claude is the empty
    runner home — those files live under the installer's own repo root (``_ROOT``),
    not under the real ~/.claude. Resolve them against ``_ROOT`` whenever the two
    differ so install-from-checkout works anywhere; when the repo already IS
    ~/.claude (``_ROOT == real``) this is byte-identical to the old behavior."""
    real = env.real_dir or str(plat.claude_dir())
    claude_dir = str(_ROOT) if str(_ROOT) != real else real
    return {"PYTHON": env.python, "NODE": env.node, "CLAUDE_DIR": claude_dir}


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


def _importable(module: str, env) -> bool:
    """True when ``import <module>`` succeeds under the target interpreter.
    Used for Python-library deps (e.g. PyYAML) that have no ``which`` CLI."""
    cp = plat.run(_sub(["{PYTHON}", "-c", f"import {module}"], _exec_tokens(env)), timeout=30)
    return cp.returncode == 0


def install_deps(env, *, ci: bool = False, dry_run: bool = False) -> list[tuple[str, str]]:
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    for dep in manifest.get("deps", []):
        did = dep["id"]
        which = dep.get("which")
        if which and shutil.which(which):
            results.append((did, "PRESENT"))
            continue
        imp = dep.get("import")
        if imp and _importable(imp, env):
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


def check_prereqs(env) -> list[tuple[str, str]]:
    """Report REQUIRED prerequisites that the installer does NOT auto-install
    (python3/node/git/claude). A MISSING required prereq blocks a full setup —
    the user must install it (per-OS command included) and re-run. Never mutates."""
    manifest = _load_manifest()
    results: list[tuple[str, str]] = []
    for p in manifest.get("prereqs", []):
        pid = p["id"]
        if shutil.which(p.get("which", pid)):
            results.append((pid, "PRESENT"))
            continue
        hint = p.get(f"install_{env.os_name}") or p.get("install_posix") or "see README prereqs"
        tag = "MISSING" if p.get("required") else "MISSING(optional)"
        results.append((pid, f"{tag} -> {hint}"))
    return results


def _present(root: Path, pat: str) -> bool:
    """True if a path (glob or literal) exists under root — detects local installs
    (e.g. GSD's engine dir + materialized gsd-* agents/skills) for idempotency."""
    if any(c in pat for c in "*?["):
        return any(root.glob(pat))
    return (root / pat).exists()


def install_plugins(env, *, ci: bool = False, dry_run: bool = False) -> list[tuple[str, str]]:
    """Add plugin marketplaces + install the workbench plugins (via the claude
    CLI), THEN install any local/manual packages that ship their own installer
    (e.g. GSD via `npx get-shit-done-cc`). Idempotent: an already-present local
    install is left untouched. Fail-open: a bad step WARNs, never crashes."""
    manifest = _load_manifest()
    plugins = manifest.get("plugins", {})
    results: list[tuple[str, str]] = []
    tokens = _exec_tokens(env)
    target = Path(env.real_dir or str(plat.claude_dir()))

    # --- marketplace + CLI-installed plugins (need the claude CLI) ---
    if not env.claude_cli:
        results.append(("marketplace-plugins", "SKIP(no-claude-cli)"))
    elif ci:
        results.append(("marketplace-plugins", "SKIP(ci-stub)"))
    else:
        listed = ""
        lm = plat.run(["claude", "plugin", "marketplace", "list"], timeout=30)
        if lm.returncode == 0:
            listed = lm.stdout or ""
        for mk in plugins.get("marketplaces", []):
            mid = mk["id"]
            if mid in listed:
                results.append((f"mkt:{mid}", "PRESENT"))
                continue
            if dry_run:
                results.append((f"mkt:{mid}", f"WOULD-ADD: {' '.join(mk['add'][-1:])}"))
                continue
            cp = plat.run(_sub(mk["add"], tokens), timeout=90)
            results.append((f"mkt:{mid}", "ADDED" if cp.returncode == 0 else f"WARN(rc={cp.returncode})"))

        plisted = ""
        lp = plat.run(["claude", "plugin", "list"], timeout=30)
        if lp.returncode == 0:
            plisted = lp.stdout or ""
        for pl in plugins.get("install", []):
            pid = pl["id"]
            if pid in plisted:
                results.append((f"plugin:{pid}", "PRESENT"))
                continue
            if dry_run:
                results.append((f"plugin:{pid}", f"WOULD-INSTALL: {pl['add'][-1]}"))
                continue
            cp = plat.run(_sub(pl["add"], tokens), timeout=180)
            results.append((f"plugin:{pid}", "INSTALLED" if cp.returncode == 0 else f"WARN(rc={cp.returncode})"))

    # --- local/manual installs (own installer, e.g. GSD via npx) — need node, NOT the claude CLI ---
    for man in plugins.get("manual", []):
        mid = man["id"]
        if any(_present(target, p) for p in man.get("detect_paths", [])):
            results.append((f"local:{mid}", "PRESENT (already installed)"))
            continue
        cmd = man.get("install_cmd")
        if not cmd:
            results.append((f"manual:{mid}", f"MANUAL -> {man.get('note', '')[:70]}"))
            continue
        if ci:
            results.append((f"local:{mid}", "SKIP(ci-stub)"))
            continue
        if not env.node:
            results.append((f"local:{mid}", f"SKIP(needs node/npm) -> {' '.join(cmd)}"))
            continue
        if dry_run:
            results.append((f"local:{mid}", f"WOULD-INSTALL: {' '.join(cmd)}"))
            continue
        # possibly-interactive third-party installer: close stdin + bound the wait.
        cp = plat.run(_sub(cmd, tokens), timeout=int(man.get("install_timeout", 420)),
                      stdin_devnull=True)
        results.append((f"local:{mid}", "INSTALLED"
                        if cp.returncode == 0
                        else f"WARN(rc={cp.returncode}) — run manually: {' '.join(cmd)}"))
    return results


if __name__ == "__main__":
    from detect import detect  # type: ignore

    e = detect()
    for label, rows in [("prereqs", check_prereqs(e)),
                        ("deps", install_deps(e, dry_run=True)),
                        ("mcp", register_mcps(e, dry_run=True)),
                        ("plugins", install_plugins(e, dry_run=True)),
                        ("post", run_post_steps(e, dry_run=True))]:
        print(f"== {label} ==")
        for name, status in rows:
            print(f"  {name:22s} {status}")
