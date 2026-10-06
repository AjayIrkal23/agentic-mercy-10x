"""Doctor rows ``hook-command`` and ``statusline``: the RENDERED commands actually run.

link-doctor starts every dispatch link with ``sys.executable``; nothing else ever runs the
string Claude Code runs (``py -3 <dir>/hooks/dispatch.py pre-tool-use`` on Windows). One run,
the way Claude Code runs it (Git Bash on Windows: ``CLAUDE_CODE_GIT_BASH_PATH``, else the bash
beside git; ``sh -c`` on POSIX; cmd.exe only on a Windows box with no Git Bash at all), a synthetic payload, ``CLAUDE_HOOK_DOCTOR=1`` and every state dir redirected
to a temp dir, must exit 0 with JSON on stdout. ``statusline`` does the same for
``statusLine.command`` (it pins an absolute interpreter, so a moved or removed Python blanks the
status line while the ``py -3`` hooks keep working): exit 0 and a non-empty line. Both SKIP before
the first render and run under ``--ci`` whenever a rendered ``settings.json`` exists (the CI
rehearsal renders one). Pure stdlib; the runner is injectable.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
PAYLOAD = {"hook_event_name": "PreToolUse", "session_id": "hook-command-doctor",
           "tool_name": "Bash", "tool_input": {"command": "true"}}


def _git_bash() -> str:
    """The bash Claude Code runs hooks under on Windows: ``CLAUDE_CODE_GIT_BASH_PATH``, else the Git for
    Windows bash beside git (``<git>/../../bin/bash.exe``, as ``doctor_basetools`` finds it); "" when
    there is none (the row then runs the command under cmd.exe) and always "" off Windows (``sh -c``)."""
    if not plat.IS_WINDOWS:
        return ""
    named = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH", "")
    if named and Path(named).is_file():
        return named
    git = shutil.which("git")
    beside = Path(git).parent.parent / "bin" / "bash.exe" if git else None
    return str(beside) if beside and beside.is_file() else ""


def _shell(command: str, payload: str, env: dict) -> tuple[int, str]:
    bash = _git_bash()
    argv = [bash, "-c", command] if bash else command
    try:
        cp = subprocess.run(argv, shell=isinstance(argv, str), input=payload, capture_output=True,
                            encoding="utf-8", errors="replace", timeout=30, env=env, check=False)
        return cp.returncode, cp.stdout or ""
    except subprocess.TimeoutExpired:
        return 124, ""
    except (OSError, ValueError):
        return 127, ""


def check_hook_command(root: Path, ci: bool, run: Callable = _shell) -> tuple[str, str]:
    settings = Path(root) / "settings.json"
    if not settings.is_file():
        return SKIP, "settings.json not rendered yet"
    try:
        command = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return FAIL, "settings.json has no hooks.PreToolUse[0].hooks[0].command"
    with tempfile.TemporaryDirectory(prefix="hook-command-") as scratch:
        env = dict(os.environ, CLAUDE_HOOK_DOCTOR="1")
        for var in ("CLAUDE_HOOK_STATE_DIR", "CLAUDE_HOOK_TELEMETRY_DIR", "CLAUDE_HOOK_DOTSTATE_DIR"):
            env[var] = os.path.join(scratch, var.lower())
        rc, out = run(command, json.dumps(PAYLOAD), env)
    if rc != 0:
        return FAIL, f"`{command.split()[0]} ...` exited {rc} (127 = interpreter not found on the hook shell's PATH)"
    try:
        json.loads(out)
    except ValueError:
        return FAIL, f"`{command.split()[0]} ...` exited 0 but printed no JSON: {out.strip()[:80]!r}"
    return PASS, f"rendered PreToolUse command runs (`{command.split()[0]} ...`: exit 0, JSON out)"


def check_statusline(root: Path, ci: bool, run: Callable = _shell) -> tuple[str, str]:
    """Run the rendered ``statusLine.command`` once, as Claude Code does, with a small sample payload.
    A pinned interpreter that moved or was uninstalled exits 127 with no output: the status line goes
    blank and no hook error says so (A3v2-02). The cache dir and cwd are throwaway."""
    settings = Path(root) / "settings.json"
    if not settings.is_file():
        return SKIP, "settings.json not rendered yet"
    try:
        command = json.loads(settings.read_text(encoding="utf-8"))["statusLine"]["command"]
        head = command.split()[0]
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
        return FAIL, "settings.json has no statusLine.command"
    with tempfile.TemporaryDirectory(prefix="statusline-") as scratch:
        payload = {"session_id": "statusline-doctor", "cwd": scratch, "model": {"display_name": "doctor"},
                   "workspace": {"current_dir": scratch}}
        rc, out = run(command, json.dumps(payload), dict(os.environ, CLAUDE_STATUSLINE_CACHE_DIR=os.path.join(scratch, "cache")))
    if rc != 0:
        why = "interpreter not found: the installer re-renders settings.json" if rc == 127 else "the installer re-renders settings.json"
        return FAIL, f"statusLine `{head} ...` exited {rc} ({why})"
    if not out.strip():
        return FAIL, f"statusLine `{head} ...` exited 0 but printed nothing: the status line would be blank (re-render settings.json)"
    return PASS, f"rendered statusLine command runs (`{head} ...`: exit 0, {len(out.strip())} chars)"
