"""code_files.py — the ONE "is this a code file?" classifier + HOME-guarded root.

Seven hooks used to carry their own (disagreeing) extension lists and eight
carried private ``.git`` walkers that ignored the ``$HOME`` ceiling. Every gate
imports from here instead:

  is_code_file(path)  -> bool   union of the old extension sets, minus skip segments
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

# Path fragments (matched case-insensitively against the "/"-normalised path)
# that mark a write as NOT application code: infra, scratch, deps, docs, config.
SKIP_SEGMENTS = (
    "/tmp/",
    "scratchpad/",
    ".claude/hooks/",    # hooks are infra, not application code
    ".claude/scripts/",
    "node_modules/",
    ".state/",
    ".telemetry/",
    ".planning/",
    ".git/",
    "/dist/",
    "/build/",
    "__pycache__/",
    "/vendor/",
    "server_docs/",
    "frontend_docs/",
    "docs/",
    "migrations/",       # procedural, not orientation-requiring
    ".env",
    ".config.",
    "package.json",
    "tsconfig",
    "eslint",
    "jest.config",
    "vite.config",
    "tailwind.config",
    "postcss.config",
)


def is_code_file(path: "str | os.PathLike | None") -> bool:
    """True iff ``path`` has a code extension and no skip segment. Never raises."""
    if not path:
        return False
    try:
        fp = str(path).replace("\\", "/")
    except Exception:
        return False
    low = fp.lower()
    if any(seg in low for seg in SKIP_SEGMENTS):
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


__all__ = ["CODE_EXTENSIONS", "SKIP_SEGMENTS", "is_code_file", "git_root", "is_home"]
