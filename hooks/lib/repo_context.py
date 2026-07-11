"""repo_context.py — the ONLY active-repo resolver in the system.

Structural guarantee: every hook that needs "which repo is the agent working
in" imports ``active_repo()`` from here. There is exactly one walk-up-.git
implementation, so no hook can accidentally target a non-active repo (Spec B
active-repo-ONLY mandate).

Resolution order (Spec A/B §3.1):
  1. explicit ``cwd`` argument, else
  2. ``payload["workspace_roots"][0]`` (Claude Code UserPromptSubmit payload), else
  3. ``payload["cwd"]``, else
  4. ``os.getcwd()``.
Then walk UP at most 20 levels looking for a ``.git`` entry (dir or file — the
file form supports git worktrees/submodules). Return ``RepoCtx`` or ``None``.

``RepoCtx.key`` is ``<dirname>-<sha1(abspath)[:8]>`` — stable per checkout,
collision-resistant, filesystem-safe (reused for per-repo state filenames).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_MAX_WALK_UP = 20


@dataclass(frozen=True)
class RepoCtx:
    root: str          # absolute path to the repo root (the dir containing .git)
    key: str           # stable per-checkout key: "<name>-<sha1[:8]>"
    name: str          # repo directory name

    @property
    def path(self) -> Path:
        return Path(self.root)


def _repo_key(root: Path) -> str:
    ap = str(root.resolve())
    digest = hashlib.sha1(ap.encode("utf-8", "replace")).hexdigest()[:8]
    name = root.name or "root"
    return f"{name}-{digest}"


def _start_dir(payload: Mapping[str, Any] | None, cwd: str | os.PathLike | None) -> Path | None:
    """Choose the starting directory per the documented resolution order."""
    if cwd:
        return Path(cwd)
    if payload:
        roots = payload.get("workspace_roots")
        if isinstance(roots, (list, tuple)) and roots:
            first = roots[0]
            if isinstance(first, str) and first:
                return Path(first)
        p_cwd = payload.get("cwd")
        if isinstance(p_cwd, str) and p_cwd:
            return Path(p_cwd)
    try:
        return Path(os.getcwd())
    except OSError:
        return None


def active_repo(
    payload: Mapping[str, Any] | None = None,
    *,
    cwd: str | os.PathLike | None = None,
) -> RepoCtx | None:
    """Return the active-repo context, or None when not inside a git repo.

    Never raises — any filesystem error yields None (fail-open).
    """
    start = _start_dir(payload, cwd)
    if start is None:
        return None
    try:
        cur = start.expanduser().resolve()
    except (OSError, RuntimeError):
        try:
            cur = Path(os.path.abspath(str(start)))
        except OSError:
            return None

    for _ in range(_MAX_WALK_UP + 1):
        try:
            if (cur / ".git").exists():
                return RepoCtx(root=str(cur), key=_repo_key(cur), name=cur.name or "root")
        except OSError:
            return None
        if cur.parent == cur:  # filesystem root reached
            break
        cur = cur.parent
    return None


def is_inside(repo: RepoCtx | None, path: str | os.PathLike) -> bool:
    """True iff ``path`` is contained within ``repo.root`` (path-containment).

    Used by the index journal so no write outside the active repo is ever
    recorded. Never raises.
    """
    if repo is None:
        return False
    try:
        root = Path(repo.root).resolve()
        target = Path(path).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    try:
        target.relative_to(root)
        return True
    except ValueError:
        return False


__all__ = ["RepoCtx", "active_repo", "is_inside"]
