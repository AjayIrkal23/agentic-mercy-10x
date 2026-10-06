#!/usr/bin/env python3
"""ostools.py — optional OS packages (apt) and the end-of-run human checklist.

The UI deck (sound, desktop notifications, the ports card) uses ``canberra-gtk-play``,
``notify-send``, ``ss`` and ``pw-play``; ``curl`` is what uv's and Claude Code's own
installers use. They need root, so the installer TRIES: directly when it runs as root
(containers), through ``sudo -n`` (passwordless sudo only, never a prompt), and otherwise
returns ONE batched ``sudo apt-get install -y …`` line for the final checklist. A missing
package never fails the install; the deck degrades gracefully without them. Linux/apt only.
"""
from __future__ import annotations

import os
import platform as _pf
import shutil
import sys
from pathlib import Path
from typing import Callable

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402


def missing_tools(manifest: dict, which: Callable = shutil.which) -> list[dict]:
    return [t for t in (manifest.get("user_space") or {}).get("os_tools", []) if not which(t["bin"])]


def _geteuid() -> int:
    return os.geteuid() if hasattr(os, "geteuid") else 1


def install_os_tools(manifest: dict, *, ci: bool, dry_run: bool, run: Callable = plat.run,
                     which: Callable = shutil.which, euid: int | None = None,
                     system: str | None = None, say: Callable = print) -> tuple[list[tuple[str, str]], str | None]:
    """([(row name, status)], sudo_command_or_None). ``sudo_command`` is set only when the
    packages are still missing and could not be installed without a password."""
    if (system or _pf.system()) != "Linux":
        return [("os-tools", "SKIP(not-linux)")], None
    missing = missing_tools(manifest, which)
    if not missing:
        return [("os-tools", "PRESENT")], None
    if not which("apt-get"):
        return [("os-tools", "SKIP(no-apt) — optional: " + ", ".join(t["bin"] for t in missing))], None
    pkgs = sorted({p for t in missing for p in t["apt"]})
    cmd = "sudo apt-get install -y " + " ".join(pkgs)
    if ci or dry_run:
        return [("os-tools", f"WOULD-INSTALL (needs root or sudo): {cmd}")], None
    root = (_geteuid() if euid is None else euid) == 0
    prefix: list[str] = []
    if not root:
        if not which("sudo") or run(["sudo", "-n", "true"], timeout=20, stdin_devnull=True).returncode != 0:
            return [("os-tools", "NEEDS-SUDO (optional, UI deck degrades without): " + ", ".join(pkgs))], cmd
        prefix = ["sudo", "-n"]
    # sudo resets the environment: DEBIAN_FRONTEND rides through `env`. argv only, no shell; the
    # packages are the manifest's fixed list. The user sees the exact command before it runs.
    pre = [*prefix, "env", "DEBIAN_FRONTEND=noninteractive"] if prefix else []
    update, install = [*pre, "apt-get", "update"], [*pre, "apt-get", "install", "-y", *pkgs]
    say(f"  running as root: {' '.join(update)}")
    run(update, timeout=300, stdin_devnull=True)  # best effort
    say(f"  running as root: {' '.join(install)}")
    cp = run(install, timeout=900, stdin_devnull=True)
    if cp.returncode == 0:
        return [("os-tools", "INSTALLED " + " ".join(pkgs))], None
    return [("os-tools", f"NEEDS-SUDO (apt rc={cp.returncode}, optional): " + ", ".join(pkgs))], cmd


def path_hint(environ=None) -> str:
    """The end-of-run PATH line: Windows put the tools on the registry PATH (a NEW terminal sees it,
    plus the Git Bash variable when we set it), POSIX can also export it."""
    if plat.IS_WINDOWS:
        bash = (os.environ if environ is None else environ).get("CLAUDE_CODE_GIT_BASH_PATH")
        return ("Open a new terminal so the updated PATH applies (claude, node, git, uv, gh)."
                + (f" Git Bash for Claude Code: CLAUDE_CODE_GIT_BASH_PATH={bash}" if bash else ""))
    return 'Open a new terminal (or `export PATH="$HOME/.local/bin:$PATH"`) so `claude` is on PATH.'


def checklist(manifest: dict, sudo_cmd: str | None, extra: list[str] | None = None) -> list[str]:
    """The ONE batched message printed after the install: the sudo line (if any), then the
    steps only a human can do (on Windows, first: open a new terminal)."""
    lines: list[str] = []
    if sudo_cmd:
        lines += ["Optional OS tools need sudo (the UI deck degrades without them). One command:",
                  f"    {sudo_cmd}"]
    steps = [*([path_hint()] if plat.IS_WINDOWS else []),
             *(manifest.get("user_space") or {}).get("human_only", []), *(extra or [])]
    lines += ["Human-only steps (cannot be automated):", *[f"  [ ] {s}" for s in steps]]
    return lines
