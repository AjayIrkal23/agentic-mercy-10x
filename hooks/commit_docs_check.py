"""commit_docs_check.py — helpers for blocking-doc-enforcer.py (audit 2026-10-05 B1-10).

  git_commits(command, cwd)  -> (commits, add_seen)
      Every simple command whose git subcommand IS ``commit`` (``git -C dir commit``
      counts, ``git commit-tree`` and a ``-m "... --amend ..."`` message do not), as
      ``(args_after_commit, directory)``; ``add_seen`` when a ``git add`` runs in the
      same command line. Tokenised with shlex, so quoted text never looks like a flag.
  missing_docs(root, commit_args, add_seen) -> list[str]
      For a repo with ``server_docs/`` or ``frontend_docs/``: the doc trees the files
      going into this commit need but do not touch. Judged from git itself (staged
      files, plus working-tree changes for ``-a`` / a same-line ``git add``).

Pure stdlib; every failure returns "nothing to check" (fail open).
"""
from __future__ import annotations

import os
import shlex
import subprocess

_SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", ";;", "|&"}
_GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
_BE_DIRS = {"server", "backend", "api"}
_FE_DIRS = {"src", "client", "frontend", "web", "apps", "app"}
_CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs", ".java",
             ".kt", ".rb", ".php", ".vue", ".svelte", ".swift", ".cs"}
_GIT_TIMEOUT_S = 3


def _segments(command: str) -> list:
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    segs, cur = [], []
    for tok in lex:
        if tok in _SEPARATORS:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        segs.append(cur)
    return segs


def _join(base: str, target: str) -> str:
    target = os.path.expanduser(target)
    return os.path.normpath(target if os.path.isabs(target) else os.path.join(base, target))


def git_commits(command: str, cwd: str) -> tuple:
    try:
        segs = _segments(command)
    except ValueError:  # unbalanced quotes: nothing parseable
        return [], False
    commits, add_seen, here = [], False, cwd
    for seg in segs:
        head = os.path.basename(seg[0])
        if head == "cd" and len(seg) > 1:
            here = _join(here, seg[1])
            continue
        if head != "git":
            continue
        i, d = 1, here
        while i < len(seg) and seg[i].startswith("-"):
            opt = seg[i].split("=", 1)[0]
            if opt in _GIT_OPTS_WITH_VALUE and "=" not in seg[i]:
                if opt == "-C" and i + 1 < len(seg):
                    d = _join(d, seg[i + 1])
                i += 2
            else:
                i += 1
        sub = seg[i] if i < len(seg) else ""
        if sub == "commit":
            commits.append((seg[i + 1:], d))
        elif sub == "add":
            add_seen = True
    return commits, add_seen


def _git(root: str, *args: str) -> list:
    proc = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,  # noqa: S603
                          timeout=_GIT_TIMEOUT_S, check=False)
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip())
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


def repo_root(directory: str) -> str | None:
    try:
        out = _git(directory, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.SubprocessError):
        return None
    return out[0] if out else None


def _all_flag(args: list) -> bool:
    for a in args:
        if a in ("--all", "-a"):
            return True
        if a.startswith("-") and not a.startswith("--") and "a" in a[1:].split("m", 1)[0]:
            return True  # combined short flags: -am, -av
    return False


def missing_docs(root: str, commit_args: list, add_seen: bool) -> list:
    has_be = os.path.isdir(os.path.join(root, "server_docs"))
    has_fe = os.path.isdir(os.path.join(root, "frontend_docs"))
    if not (has_be or has_fe):
        return []
    try:
        files = set(_git(root, "diff", "--cached", "--name-only"))
        if add_seen or _all_flag(commit_args):
            files |= set(_git(root, "diff", "--name-only"))
        if add_seen:
            files |= set(_git(root, "ls-files", "--others", "--exclude-standard"))
    except (OSError, subprocess.SubprocessError):
        return []
    code = [f for f in files if os.path.splitext(f)[1].lower() in _CODE_EXT]
    be = has_be and any(f.split("/", 1)[0] in _BE_DIRS for f in code)
    fe = has_fe and any(f.split("/", 1)[0] in _FE_DIRS for f in code)
    missing = []
    if be and not any(f.startswith("server_docs/") for f in files):
        missing.append("- server_docs/ (backend code in this commit)")
    if fe and not any(f.startswith("frontend_docs/") for f in files):
        missing.append("- frontend_docs/ (frontend code in this commit)")
    if (be or fe) and os.path.isfile(os.path.join(root, "PROJECT_LINKAGES.md")) \
            and "PROJECT_LINKAGES.md" not in files:
        missing.append("- PROJECT_LINKAGES.md")
    return missing
