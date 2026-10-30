#!/usr/bin/env python3
"""worktree_audit.py: read-only, one-line audit of a repo's git worktrees.

``one_line(cwd, budget_ms=400)`` -> "" when the repo has only its main worktree or
nothing is flagged, else e.g.
``worktrees: 4 (1 dirty, 1 stale >7d, 1 predicted conflict with main: feat-x)``.

Per linked worktree on a branch other than the base: dirty (``status --porcelain
--untracked-files=no``), stale (clean, ahead of base, last commit older than 7 days),
predicted conflict (clean, ahead, ``git merge-tree --write-tree`` exits 1; git 2.38+;
it writes objects only, never an index, tree or ref). Adopted from ECC's
worktree-lifecycle.js; never removes, prunes or writes anything else.

lib/session_notices.worktree_line() executes this file as a fresh module (not
``__main__``), so the hooks dir goes on sys.path here and the CLI stays under the
``__main__`` guard. Windows: "" (not supported yet). Any error: "".
CLI: ``python3 worktree_audit.py [dir]`` prints the line when non-empty, exits 0.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:  # session_notices exec()s this file
    sys.path.insert(0, str(_HOOKS))

from lib import platform as plat  # noqa: E402

STALE_DAYS = 7
LINE_MAX = 200
GIT_T = 0.15
_GIT_ENV_DROP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX")


class _Out(Exception):
    """The time budget ran out."""


def _hermetic_env() -> dict:
    """os.environ minus the variables that would point git at another repo (a hook run
    from inside a git hook inherits them)."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_DROP}


def _git(args, cwd, timeout=None):
    return plat.run(["git", *args], cwd=cwd, timeout=GIT_T if timeout is None else timeout, env=_hermetic_env())


def _git_version() -> tuple:
    try:
        out = _git(["--version"], None).stdout or ""
        nums = out.strip().split()[2].split(".")
        return int(nums[0]), int(nums[1])
    except Exception:  # noqa: BLE001
        return (0, 0)


def _worktrees(text: str) -> list:
    entries, cur = [], {}
    for line in (text or "").splitlines() + [""]:
        if not line.strip():
            if cur:
                entries.append(cur)
            cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur["path"] = val
        elif key == "branch":
            cur["branch"] = val[len("refs/heads/"):] if val.startswith("refs/heads/") else val
        elif key in ("bare", "detached", "prunable"):
            cur[key] = True
    return entries


def _audit(cwd: str, budget_ms: float) -> str:
    deadline = time.monotonic() + budget_ms / 1000.0

    def git(args, where):
        left = deadline - time.monotonic()
        if left < 0.03:
            raise _Out()
        return _git(args, where, timeout=min(GIT_T, left))

    try:
        cp = git(["rev-parse", "--show-toplevel"], cwd)
        if cp.returncode != 0 or not cp.stdout.strip():
            return ""
        root = Path(cp.stdout.strip())
        cp = git(["rev-parse", "--git-common-dir"], str(root))
        if cp.returncode != 0 or not cp.stdout.strip():
            return ""
        common = Path(cp.stdout.strip())
        main_root = (common if common.is_absolute() else root / common).resolve().parent
        cp = git(["worktree", "list", "--porcelain"], str(main_root))
        entries = _worktrees(cp.stdout) if cp.returncode == 0 else []
        if len(entries) <= 1:
            return ""
        cp = git(["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], str(main_root))
        base = cp.stdout.strip().split("/", 1)[-1] if cp.returncode == 0 and cp.stdout.strip() else ""
        if not base:
            for cand in ("main", "master"):
                if git(["show-ref", "--verify", "-q", f"refs/heads/{cand}"], str(main_root)).returncode == 0:
                    base = cand
                    break
    except _Out:
        return ""

    dirty = stale = 0
    conflicts: list = []
    partial = old_git = False
    ver = None
    for e in entries:
        branch, path = e.get("branch"), e.get("path") or ""
        if (e.get("bare") or e.get("detached") or not branch or branch == base
                or Path(path).resolve() == main_root):
            continue
        try:
            st = git(["status", "--porcelain", "--untracked-files=no"], path)
            is_dirty = st.returncode == 0 and bool(st.stdout.strip())
            if is_dirty:
                dirty += 1
                continue
            if st.returncode != 0 or not base:  # prunable / missing dir, or no base to compare
                continue
            cp = git(["rev-list", "--count", f"{base}..{branch}"], str(main_root))
            ahead = int(cp.stdout.strip()) if cp.returncode == 0 and cp.stdout.strip().isdigit() else 0
            if ahead <= 0:
                continue
            cp = git(["log", "-1", "--format=%ct", branch], str(main_root))
            if cp.returncode == 0 and cp.stdout.strip().isdigit():
                if (time.time() - int(cp.stdout.strip())) / 86400 > STALE_DAYS:
                    stale += 1
            ver = _git_version() if ver is None else ver
            if ver < (2, 38):
                old_git = True
                continue
            cp = git(["merge-tree", "--write-tree", "--name-only", base, branch], str(main_root))
            if cp.returncode == 1:
                conflicts.append(branch)
        except _Out:
            partial = True
            break

    if not (dirty or stale or conflicts):
        return ""
    parts = []
    if dirty:
        parts.append(f"{dirty} dirty")
    if stale:
        parts.append(f"{stale} stale >{STALE_DAYS}d")
    if conflicts:
        c = len(conflicts)
        parts.append(f"{c} predicted conflict{'s' if c != 1 else ''} with {base}: {', '.join(conflicts[:3])}")
    line = f"worktrees: {len(entries)} ({', '.join(parts)})"
    if partial:
        line += " (partial)"
    if old_git:
        line += "; conflict check needs git 2.38+"
    if len(line) > LINE_MAX:
        line = line[:LINE_MAX - 1] + "…"
    return line


def one_line(cwd, budget_ms: float = 400) -> str:
    """The audit line for the repo holding ``cwd`` ("" when clean, on Windows or on error)."""
    try:
        if plat.IS_WINDOWS or not cwd:
            return ""
        return _audit(str(cwd), budget_ms)
    except Exception:  # noqa: BLE001
        return ""


if __name__ == "__main__":
    out = one_line(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    if out:
        print(out)
    sys.exit(0)
