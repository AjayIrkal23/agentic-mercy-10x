"""code_files.py — the ONE "is this a code file?" classifier + HOME-guarded root.

Seven hooks used to carry their own (disagreeing) extension lists and eight
carried private ``.git`` walkers that ignored the ``$HOME`` ceiling. Every gate
imports from here instead:

  is_skipped(path, *, extra_dirs=(), extra_names=()) -> bool   the ONE anchored skip list
  is_code_file(path)  -> bool   union of the old extension sets, minus skipped paths
  git_root(path)      -> Path|None  (= lib.repo_context.git_root, HOME-guarded)
  is_home(root)       -> bool   True when ``root`` IS ``$HOME`` (a container, never a repo)

Pure stdlib, never raises.
"""
from __future__ import annotations

import os
from pathlib import Path

from .repo_context import git_root  # noqa: F401  (re-exported)

# Union of first-write-skill-gate / dox-write-gate / doc-update-enforcer /
# jcodemunch-enforce / dox_engine extension sets.
CODE_EXTENSIONS = frozenset({
    ".py", ".pyi",
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx",
    ".go", ".rs", ".java", ".kt", ".kts", ".scala",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cxx", ".hxx",
    ".rb", ".php", ".swift", ".m", ".mm",
    ".cs", ".fs", ".vb",
    ".lua", ".dart", ".ex", ".exs", ".erl", ".hs",
    ".sh", ".bash", ".zsh",
    ".vue", ".svelte",
})

# What marks a write as NOT application code: infra, scratch, deps, docs, config.
# Directory entries match WHOLE path components (``docs`` skips ``/r/docs/x`` but not
# ``/r/mydocs/x``); multi-component entries (``.claude/hooks``) match consecutive ones.
SKIP_DIRS = frozenset({
    "scratchpad", ".claude/hooks", ".claude/scripts", "node_modules", ".state", ".telemetry",
    ".planning", ".git", "dist", "build", "__pycache__", "vendor", "server_docs",
    "frontend_docs", "docs", "migrations",
})
# Anchored at the path start only (``/r/tmp/a.py`` is a repo dir, not scratch).
SKIP_ROOTS = ("/tmp/", "/private/tmp/")
# Substrings of the BASENAME only (a dir named ``.envs`` is not a dotenv file).
SKIP_NAMES = (".env", ".config.", "package.json", "tsconfig", "eslint", "jest.config",
              "vite.config", "tailwind.config", "postcss.config")
# Frozen view kept for old importers (read by nobody today).
SKIP_SEGMENTS = tuple(sorted(f"{d}/" for d in SKIP_DIRS)) + SKIP_NAMES


def _norm(path: "str | os.PathLike") -> str:
    return str(path).replace("\\", "/").lower()


def is_skipped(path: "str | os.PathLike | None", *, extra_dirs=(), extra_names=()) -> bool:
    """True when ``path`` sits under a skip dir/root or its basename carries a skip
    marker. ``extra_dirs`` / ``extra_names`` add a caller's own markers. Never raises."""
    if not path:
        return False
    try:
        low = _norm(path)
        if any(low.startswith(r) for r in SKIP_ROOTS):
            return True
        padded = "/" + low.strip("/") + "/"
        if any(f"/{str(d).lower().strip('/')}/" in padded for d in (*SKIP_DIRS, *extra_dirs)):
            return True
        base = low.rstrip("/").rsplit("/", 1)[-1]
        return any(str(m).lower() in base for m in (*SKIP_NAMES, *extra_names))
    except Exception:
        return False


def is_code_file(path: "str | os.PathLike | None") -> bool:
    """True iff ``path`` has a code extension and is not skipped. Never raises."""
    if not path:
        return False
    try:
        low = _norm(path)
    except Exception:
        return False
    if is_skipped(low):
        return False
    return os.path.splitext(low)[1] in CODE_EXTENSIONS


def is_home(root: "str | os.PathLike | None") -> bool:
    """True when ``root`` resolves to ``$HOME`` itself. Never raises."""
    if root is None:
        return False
    try:
        return Path(root).expanduser().resolve() == Path.home().resolve()
    except (OSError, RuntimeError):
        return False


def is_infra_root(root: "str | os.PathLike | None") -> bool:
    """True for the agent-infra roots that are never indexed or graphed: ``$HOME``,
    ``~/.claude``, ``~/.codex`` and this checkout. Mirrors ``index-lifecycle.NEVER_INDEX``
    (kept there for its no-libs fallback); every other hook asks this. Never raises."""
    if root is None:
        return False
    try:
        r, h = Path(root).expanduser().resolve(), Path.home().resolve()
        return r in (h, h / ".claude", h / ".codex", Path(__file__).resolve().parents[2])
    except (OSError, RuntimeError):
        return False


__all__ = ["CODE_EXTENSIONS", "SKIP_DIRS", "SKIP_ROOTS", "SKIP_NAMES", "SKIP_SEGMENTS",
           "is_skipped", "is_code_file", "git_root", "is_home", "is_infra_root"]
