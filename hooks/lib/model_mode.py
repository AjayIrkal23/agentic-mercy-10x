"""Per-project model-mode resolution — shared by opus-guard + workflow-model-guard.

The problem this fixes: the old `~/.claude/state/<mode>-only-mode` flags are
GLOBAL, so forcing (say) fable in one project's session leaks into every other
concurrent session. This resolves a mode scoped to the CURRENT project instead,
so multiple projects can each pin a different model without interfering.

Resolution order (first hit wins):
  1. per-project override : ~/.claude/state/model-modes/<project-key>
                            (file content = "sonnet" | "opus" | "fable")
  2. global flag (legacy/default) : ~/.claude/state/<mode>-only-mode
                            (presence; precedence sonnet > opus > fable)
  3. None -> smart routing

project-key = "<basename>-<sha1(realpath(git-root or cwd))[:12]>". The git root
is used (not bare cwd) so every subdir of a repo shares one mode. Everything is
fail-open: any error -> fall through, never break a hook.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

STATE = Path.home() / ".claude" / "state"
MODES = ("sonnet", "opus", "fable")
_PRECEDENCE = ("sonnet", "opus", "fable")


def _cwd_from(payload) -> str:
    """cwd from the hook payload if present, else the process cwd."""
    if isinstance(payload, dict):
        c = payload.get("cwd") or payload.get("cwd_path") or payload.get("workdir")
        if isinstance(c, str) and c:
            return c
    try:
        return os.getcwd()
    except OSError:
        return str(Path.home())


def project_key(payload=None, cwd: str | None = None) -> str:
    base_cwd = cwd or _cwd_from(payload)
    root = base_cwd
    try:
        r = subprocess.run(
            ["git", "-C", base_cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=3, check=False)
        if r.returncode == 0 and r.stdout.strip():
            root = r.stdout.strip()
    except Exception:
        pass
    try:
        root = os.path.realpath(root)
    except OSError:
        pass
    digest = hashlib.sha1(root.encode("utf-8", "replace")).hexdigest()[:12]
    name = os.path.basename(root.rstrip("/\\")) or "root"
    return f"{name}-{digest}"


def project_mode(payload=None, cwd: str | None = None) -> str | None:
    """This project's explicit override, or None."""
    try:
        pm = STATE / "model-modes" / project_key(payload, cwd)
        if pm.is_file():
            m = pm.read_text(encoding="utf-8").strip().lower()
            if m in MODES:
                return m
    except Exception:
        pass
    return None


def _global_mode(flag_paths=None, precedence=None) -> str | None:
    """Legacy/default global flag, or None. flag_paths/precedence let callers pass
    policy-derived values; defaults reproduce the historical behavior."""
    prec = precedence or _PRECEDENCE
    for m in prec:
        try:
            fp = None
            if isinstance(flag_paths, dict):
                fp = flag_paths.get(m)
            if fp is None:
                fp = STATE / f"{m}-only-mode"
            if Path(fp).is_file():
                return m
        except Exception:
            pass
    return None


def forced_mode(payload=None, cwd: str | None = None,
                flag_paths=None, precedence=None) -> tuple[str | None, str]:
    """Return (mode, scope). scope is 'project', 'global', or ''.
    Per-project override wins; the global flag is the legacy/default fallback."""
    m = project_mode(payload, cwd)
    if m:
        return m, "project"
    m = _global_mode(flag_paths, precedence)
    if m:
        return m, "global"
    return None, ""
