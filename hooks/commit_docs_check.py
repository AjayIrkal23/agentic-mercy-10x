"""commit_docs_check.py — helpers for blocking-doc-enforcer.py (audit 2026-10-05 B1-10).

  git_commits(command, cwd)  -> (commits, add_seen)
      Every simple command whose git subcommand IS ``commit`` (``git -C dir commit``
      counts, ``git commit-tree`` and a ``-m "... --amend ..."`` message do not), as
      ``(args_after_commit, directory)``; ``add_seen`` when a ``git add`` runs in the
      same command line. Tokenised with shlex, so quoted text never looks like a flag.
      A newline, ``{`` and ``}`` end a command like ``;``; ``git.exe`` and a quoted path
      to it are git; ``cd`` / ``Set-Location`` / ``sl`` / ``pushd`` / ``Push-Location``
      move the directory; the payload of ``powershell -c`` / ``bash -c`` / ``cmd /c`` /
      ``iex`` / ``eval`` is scanned too (two levels). Backtick-newline is a continuation.
  missing_docs(root, commit_args, add_seen) -> list[str]
      For a repo with ``server_docs/`` or ``frontend_docs/``: the doc trees the files
      going into this commit need but do not touch. Judged from git itself (staged
      files, plus working-tree changes for ``-a`` / a same-line ``git add``).

Pure stdlib; every failure returns "nothing to check" (fail open).
"""
from __future__ import annotations

import ntpath
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
try:
    from lib import platform as plat
except Exception:  # noqa: BLE001 - the doc gate stays fail-open without the foundation lib
    plat = type("plat", (), {"IS_WINDOWS": False})

_PUNCT = ";()<>|&{}\n"  # shlex splits these out of words; a token made only of _SEP_CHARS ends a command
_SEP_CHARS = frozenset(";()&|{}\n")
_CONTINUATION = re.compile(r"`\r?\n|(?<=[ \t])\\\r?\n")  # Windows: `D:\x\` + newline is a path, not a continuation
_CONTINUATION_POSIX = re.compile(r"[`\\]\r?\n")
_DIR_COMMANDS = {"cd", "chdir", "sl", "set-location", "pushd", "push-location"}
_DASH_C_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
_GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
_BE_DIRS = {"server", "backend", "api"}
_FE_DIRS = {"src", "client", "frontend", "web", "apps", "app"}
_CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs", ".java",
             ".kt", ".rb", ".php", ".vue", ".svelte", ".swift", ".cs"}
_GIT_TIMEOUT_S = 3


def _segments(command: str) -> list:
    command = (_CONTINUATION if plat.IS_WINDOWS else _CONTINUATION_POSIX).sub(" ", command)
    if plat.IS_WINDOWS:  # POSIX shlex eats the backslashes of D:\Projects\x (A4-07); `x\ ` = tab completion
        command = re.sub(r"(?<![\\\"'])\\(?=[\w.\s-]|$)", "/", command)
    lex = shlex.shlex(command, posix=True, punctuation_chars=_PUNCT)
    lex.whitespace_split = True
    lex.whitespace = " \t\r"  # a newline is punctuation: it ends a command
    lex.commenters = ""  # a `#` must not swallow the newline (and the next command) behind it
    segs, cur = [], []
    for tok in lex:
        if tok and set(tok) <= _SEP_CHARS:
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
    if plat.IS_WINDOWS:
        msys = re.match(r"/([A-Za-z])(?:/|$)", target)  # Git Bash: /d/Projects/x -> D:/Projects/x
        if msys:
            target = msys.group(1).upper() + ":" + (target[2:] or "/")
        if re.match(r"[A-Za-z]:[\\/]", target):
            return ntpath.normpath(target).replace("\\", "/")
    return os.path.normpath(target if os.path.isabs(target) else os.path.join(base, target))


def _program(token: str) -> str:
    """`& "<dir>\\Git\\cmd\\git.exe"` -> `git`; `Set-Location` -> `set-location`."""
    return ntpath.basename(token).lower().removesuffix(".exe")


def _dir_arg(args: list) -> str | None:
    for i, a in enumerate(args[:-1]):
        if a.lower() in ("-path", "-literalpath"):  # `Set-Location -Path x`
            return args[i + 1]
    return next((a for a in args if not a.startswith("-") and a.lower() != "/d"), None)


def _payload(head: str, args: list):
    """The command a nested shell runs: a string to scan, a ready segment (cmd /c), or None."""
    low = [a.lower() for a in args]
    if head in ("powershell", "pwsh"):
        for i, a in enumerate(low):
            if len(a) > 1 and "-command".startswith(a) and a.startswith("-c"):
                return " ".join(args[i + 1:])
    elif head in _DASH_C_SHELLS:
        for i, a in enumerate(args[:-1]):
            if re.fullmatch(r"-[a-z]*c[a-z]*", a):
                return args[i + 1]
    elif head == "cmd":
        for i, a in enumerate(low):
            if a in ("/c", "/k", "//c", "//k"):
                return args[i + 1:]
    elif head in ("iex", "invoke-expression", "eval"):
        return " ".join(args)
    return None


def _scan(command: str, here: str, depth: int) -> tuple:
    """(commits, add_seen) of ``command``; a nested payload is scanned from the directory it starts in."""
    commits, add_seen = [], False
    for seg in _segments(command):
        found = _scan_segment(seg, here, depth)
        commits, add_seen = commits + found[0], add_seen or found[1]
        here = found[2]
    return commits, add_seen


def _scan_segment(seg: list, here: str, depth: int) -> tuple:
    head, args = _program(seg[0]), seg[1:]
    if head in _DIR_COMMANDS:
        target = _dir_arg(args)
        return [], False, _join(here, target) if target else here
    if head != "git":
        body = _payload(head, args) if depth < 2 else None
        if not body:
            return [], False, here
        if isinstance(body, list):  # cmd /c git commit ...: the rest of the line is one command
            return (*_scan_segment(body, here, depth + 1)[:2], here)
        return (*_scan(body, here, depth + 1), here)
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
    return ([(seg[i + 1:], d)] if sub == "commit" else []), sub == "add", here


def git_commits(command: str, cwd: str) -> tuple:
    try:
        return _scan(command, cwd, 0)
    except ValueError:  # unbalanced quotes: nothing parseable
        return [], False


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
