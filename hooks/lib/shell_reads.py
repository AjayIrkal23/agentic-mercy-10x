"""Which code file a shell read/search command stands for (audit 02 B-02).

``grep -rn foo src``, ``rg foo``, ``cat a.ts``, ``sed -n 1,40p a.ts``, ``head``/``tail``,
``find . -name '*.ts'``: the jcodemunch read gate judges these like the Read/Grep/Glob
tools. ``code_target(cmd, cwd)`` returns ``(target, hint)``: the file the command reads,
or ``<dir>/x.<ext>`` for a directory search (``x.py`` when no glob names the type), and
the symbol or file name to name in the deny. ``("", "")`` for anything else: git, package
managers, test runners, in-place edits, a search inside a non-code file. Never raises.
"""
from __future__ import annotations

import os
import re
import shlex

_SPLIT = re.compile(r"\|\||&&|[;\n]")      # commands; a pipeline stays one command
_PIPE = re.compile(r"(?<!\|)\|(?!\|)")      # its stages: only the first reads files, the rest read stdin
_RECURSIVE_BY_DEFAULT = {"rg", "ag", "ack"}
_READERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "cat", "bat", "head", "tail",
            "less", "more", "nl", "sed", "find", "fd"}
_SEARCHERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack"}
_WRAPPERS = {"sudo", "command", "nice", "time", "xargs"}
# grep/rg options that take a separate value (the value is not the pattern).
_VALUE_OPTS = {"-e", "-f", "-g", "--glob", "-t", "--type", "-A", "-B", "-C", "-m", "--include",
               "--exclude", "--exclude-dir", "--max-count", "--context"}


def _words(seg: str) -> list:
    try:
        return shlex.split(seg)
    except ValueError:
        return seg.split()


def _glob_ext(words: list) -> str:
    """The extension a ``--include=*.ts`` / ``-g '*.ts'`` / ``-name '*.ts'`` / ``-t ts`` names."""
    for i, w in enumerate(words):
        val = ""
        if "=" in w and w.split("=", 1)[0] in ("--include", "--glob", "--type"):
            val = w.split("=", 1)[1]
        elif w in ("--include", "-g", "--glob", "-name", "-iname", "-t", "--type") and i + 1 < len(words):
            val = words[i + 1]
        if val:
            ext = val.rsplit(".", 1)[-1].strip("*'\"{}") if "." in val else val
            if ext and ext.isalnum():
                return ext
    return ""


def _operands(head: str, args: list) -> tuple:
    """(pattern, paths) of a reader's arguments."""
    pattern, paths, skip, explicit = "", [], False, False
    for i, a in enumerate(args):
        if skip:
            skip = False
            if args[i - 1] == "-e":
                pattern, explicit = a, True
            continue
        if a.startswith("-") and a != "-":
            if a in _VALUE_OPTS and head != "find":
                skip = True
            if head == "find" and a in ("-name", "-iname", "-path", "-type", "-maxdepth", "-mindepth"):
                skip = True
            continue
        if head in _SEARCHERS and not pattern and not explicit:
            pattern = a
            continue
        if head == "sed" and not any(p for p in paths) and re.fullmatch(r"[\d,$]*p", a):
            continue  # the sed script `1,40p`
        if head in ("head", "tail") and a.isdigit():
            continue
        paths.append(a)
    return pattern, paths


def _segment(words: list, cwd: str) -> tuple:
    while words and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]) or words[0] in _WRAPPERS):
        words = words[1:]
    if not words:
        return "", ""
    head = os.path.basename(words[0])
    if head not in _READERS:
        return "", ""
    args = words[1:]
    if head == "sed" and ("-n" not in args or any(a.startswith("-i") or a == "--in-place" for a in args)):
        return "", ""
    pattern, paths = _operands(head, args)
    ext = _glob_ext(words)
    if not paths:
        # a plain `grep x` with no path reads stdin; rg/ag/ack and `grep -r` search the cwd tree
        recursive = head in _RECURSIVE_BY_DEFAULT or any(
            a == "--recursive" or (re.fullmatch(r"-[A-Za-z]+", a) and ("r" in a or "R" in a)) for a in args)
        if (head in _SEARCHERS and recursive) or head in ("find", "fd"):
            paths = ["."]
        else:
            return "", ""
    for p in paths:
        full = p if os.path.isabs(p) else os.path.join(cwd or ".", p)
        if os.path.isdir(full) or head in ("find", "fd"):
            # no glob: `<dir>/x` with no extension, so the code-path rule (src/, server/, ...) decides
            return os.path.join(os.path.normpath(full), f"x.{ext}" if ext else "x"), pattern[:80]
        return os.path.normpath(full), (pattern or os.path.basename(full))[:80]
    return "", ""


def code_target(cmd: str, cwd: str) -> tuple:
    try:
        here = cwd or ""
        for seg in _SPLIT.split(str(cmd or "")):
            words = _words(_PIPE.split(seg)[0].strip())
            if len(words) >= 2 and words[0] in ("cd", "pushd"):
                here = words[1] if os.path.isabs(words[1]) else os.path.join(here, words[1])
                continue
            target, hint = _segment(words, here)
            if target:
                return target, hint
    except Exception:  # noqa: BLE001
        pass
    return "", ""
