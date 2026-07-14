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


# ---------------------------------------------------------------------------
# Git identity helpers (ported from jcodemunch-enforce.py, 2026-07-14).
# The canonical home so graphify validates a repo's identity the SAME way
# jcodemunch names its index db: after the git REMOTE ({owner}-{repo}), NOT the
# local folder — so a repo whose folder differs from its remote (e.g. folder
# "oracleradar" under owner "rahul70392") still validates correctly.
# NOTE: jcodemunch-enforce.py keeps an equivalent PRIVATE copy (its hard read
# gate); consolidating it onto these shared helpers is a deliberate follow-up so
# this change never touches that gate. Keep the two behaviourally identical.
# ---------------------------------------------------------------------------


def sanitize_name(name: str) -> str:
    """Non-alphanumerics → '-', collapsed, trimmed. Mirrors jcodemunch db-name
    sanitization ("VAIBHAV KATWE" → "VAIBHAV-KATWE")."""
    out: list[str] = []
    prev_dash = False
    for ch in name:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")


def git_root(path: str | os.PathLike) -> Path | None:
    """Walk up from ``path`` to the nearest dir containing a ``.git`` entry (dir
    or worktree pointer file). ``None`` when not inside a git repo. Never raises."""
    try:
        p = Path(path).expanduser()
        cur = p if p.is_dir() else p.parent
    except (OSError, RuntimeError):
        return None
    for _ in range(_MAX_WALK_UP + 10):
        try:
            if (cur / ".git").exists():
                return cur
        except OSError:
            return None
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def git_remote_identity(root: str | os.PathLike) -> str | None:
    """Reconstruct sanitized ``{owner}-{repo}`` from ``<root>/.git/config``'s
    remote url. Handles worktree/submodule pointer files and https/ssh urls.
    Fail-soft: any problem → ``None``."""
    try:
        root = Path(root)
        gitdir = root / ".git"
        cfg: Path | None = None
        if gitdir.is_dir():
            cfg = gitdir / "config"
        elif gitdir.is_file():
            for line in gitdir.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("gitdir:"):
                    real = Path(line.split(":", 1)[1].strip())
                    if not real.is_absolute():
                        real = (root / real).resolve()
                    cfg = real / "config"
                    break
        if not cfg or not cfg.is_file():
            return None
        url = None
        for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if s.startswith("url") and "=" in s:
                url = s.split("=", 1)[1].strip()
                break
        if not url:
            return None
        u = url[:-4] if url.endswith(".git") else url
        if "://" in u:                       # https://host/owner/repo
            u = u.split("://", 1)[1]
            u = u.split("/", 1)[1] if "/" in u else u
        elif ":" in u:                       # git@host:owner/repo (scp-like ssh)
            u = u.split(":", 1)[1]
        segs = [p for p in u.split("/") if p]
        if len(segs) < 2:
            return None
        owner, repo = segs[-2], segs[-1]
        return f"{sanitize_name(owner)}-{sanitize_name(repo)}"
    except Exception:
        return None


__all__ = [
    "RepoCtx",
    "active_repo",
    "is_inside",
    "sanitize_name",
    "git_root",
    "git_remote_identity",
]
