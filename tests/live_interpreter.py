"""Decouple the suite from the interpreter that rendered the live ``settings.json`` (A7v2-03).

``statusLine.command`` pins an absolute python.exe (``detect._python_exe``: the interpreter running the
render). A test that renders or runs the doctor against the checkout's own ``settings.json`` then fails
under any other Python (the CI Windows leg runs 3.12, the file says 3.14). ``pin`` makes the render
compute the interpreter the live file already holds, or an injected one; everything else is still compared.
It also runs the doctor's `hook-command` / `statusline` rows with the real home: the POSIX render says
`${HOME}/.claude/...`, which a sandboxed HOME would point at an empty dir (exit 2).
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "installer") not in sys.path:
    sys.path.insert(0, str(_ROOT / "installer"))
_REAL_HOME = {k: os.environ[k] for k in ("HOME", "USERPROFILE") if k in os.environ}  # read at import, before any sandbox


def live_interpreter() -> str | None:
    """First word of the live ``statusLine.command``; None without a settings.json (fresh checkout / CI)."""
    try:
        command = json.loads((_ROOT / "settings.json").read_text(encoding="utf-8"))["statusLine"]["command"]
        return shlex.split(command, posix=True)[0]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def pin(monkeypatch, exe: str | None = None) -> None:
    """Make ``detect._python_exe`` answer ``exe`` (default: the live file's interpreter) and run the
    doctor's hook rows with the real home."""
    exe = exe or live_interpreter()
    if exe:
        import detect  # type: ignore
        monkeypatch.setattr(detect, "_python_exe", lambda: exe)
    import doctor_hook  # type: ignore
    shell = doctor_hook._shell
    monkeypatch.setattr(doctor_hook, "_shell", lambda command, payload, env: shell(command, payload, {**env, **_REAL_HOME}))
