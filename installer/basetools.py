"""basetools.py — the fresh-machine part of the install pass (called by ``selfheal``).

``before_deps``: apt OS tools (root or `sudo -n` only; otherwise the one sudo command is handed
back for the final checklist), then node / claude / uv / gh into ``~/.local``; returns the
re-detected env (the new claude / npm / uv are on PATH) and the pending sudo command.
``after_deps``: ollama + the models the code indexes use. ``AGENTIC_MERCY_SKIP_BASE_TOOLS=1``
(offline machines, the test suite) skips both. Linux only in effect; Windows is untouched.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detect  # noqa: E402
import ollama_setup  # noqa: E402
import ostools  # noqa: E402
import userspace  # noqa: E402


def skipped() -> bool:
    return bool(os.environ.get("AGENTIC_MERCY_SKIP_BASE_TOOLS"))


def before_deps(env, manifest: dict, ci: bool, emit):
    if skipped():
        return env, None
    rows, sudo_cmd = ostools.install_os_tools(manifest, ci=ci, dry_run=ci,
                                              say=lambda line: emit("base", "apt", line.strip()))
    for name, s in rows:
        emit("base", name, s)
    for name, s in userspace.ensure_userspace(env, manifest, ci=ci, dry_run=ci):
        emit("base", name, s)
    return (env if ci else detect.detect()), sudo_cmd


def after_deps(manifest: dict, ci: bool, emit) -> None:
    if not skipped():
        for name, s in ollama_setup.setup_ollama(manifest, ci=ci, dry_run=ci):
            emit("base", name, s)
