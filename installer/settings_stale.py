"""A rendered settings.json that names an interpreter which no longer exists (A3v2-02).

``statusLine.command`` pins an absolute python.exe; hooks may pin a node or python path. When that file
is moved, upgraded or uninstalled the status line goes blank and nothing says so, so ``selfheal._stale``
(the install pass and the daily self-heal) re-renders. Pure stdlib.
"""
from __future__ import annotations

import json
import os
import shlex
from pathlib import Path


def _commands(node) -> list[str]:
    if isinstance(node, dict):
        own = [node["command"]] if isinstance(node.get("command"), str) else []
        return own + [c for v in node.values() for c in _commands(v)]
    if isinstance(node, list):
        return [c for v in node for c in _commands(v)]
    return []


def interpreter_gone(settings: Path) -> bool:
    """A command of ``statusLine`` or ``hooks`` starts with an ABSOLUTE path that is not a file. Bare
    names (`py -3`, `python3`) never count; an unparseable file is not this function's problem."""
    try:
        data = json.loads(Path(settings).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    for command in _commands({k: data.get(k) for k in ("statusLine", "hooks")}):
        try:
            words = shlex.split(command, posix=True)
        except ValueError:
            words = command.split()
        if words and os.path.isabs(words[0]) and not os.path.isfile(words[0]):
            return True
    return False
