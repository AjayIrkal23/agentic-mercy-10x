"""Decouple the suite from the interpreter that rendered the live ``settings.json`` (A7v2-03).

``statusLine.command`` pins an absolute python.exe (``detect._python_exe``: the interpreter running the
render). A test that renders or runs the doctor against the checkout's own ``settings.json`` then fails
under any other Python (the CI Windows leg runs 3.12, the file says 3.14). ``pin`` makes the render
compute the interpreter the live file already holds, or an injected one; everything else is still compared.
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "installer") not in sys.path:
    sys.path.insert(0, str(_ROOT / "installer"))


def live_interpreter() -> str | None:
    """First word of the live ``statusLine.command``; None without a settings.json (fresh checkout / CI)."""
    try:
        command = json.loads((_ROOT / "settings.json").read_text(encoding="utf-8"))["statusLine"]["command"]
        return shlex.split(command, posix=True)[0]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def pin(monkeypatch, exe: str | None = None) -> None:
    """Make ``detect._python_exe`` answer ``exe`` (default: the live file's interpreter)."""
    exe = exe or live_interpreter()
    if exe:
        import detect  # type: ignore
        monkeypatch.setattr(detect, "_python_exe", lambda: exe)
