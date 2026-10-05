"""winprobe.py — "is this tool already there, and does it work?" for the Windows base tools (split out of
``wintools``, which installs what this says is missing).

An existing tool is reused only when it really works: git with a ``bash.exe`` beside it (Claude Code's
Bash tool needs it), node >= the manifest minimum with npm, never a Microsoft Store ``WindowsApps``
shim, claude from the pinned minor up. A half-installed tool (no completion marker) is not present.
``which``, ``run`` and the registry are injected. Pure stdlib.
"""
from __future__ import annotations

from pathlib import Path

import winpath
from winutil import COMPLETE, bash_values, git_bash, store_stub, ver, win_arch, within


class Probe:
    def __init__(self, manifest, run, which, environ, registry):
        us = manifest.get("user_space") or {}
        self.cfg, self.run, self.which = us.get("windows") or {}, run, which
        self.environ, self.registry = environ, registry
        self.node_min = int((us.get("node") or {}).get("min", 18))
        self.claude_v = (self.cfg.get("claude") or {}).get("version") or (manifest.get("mods") or {}).get("claude_version", "")
        self.tools, self.arch = winpath.tools_dir(environ), win_arch(environ)
        self.home = Path(environ.get("USERPROFILE") or Path.home())
        self.local_bin = self.home / ".local" / "bin"

    def git_complete(self) -> bool:
        g = self.tools / "git"
        return (g / COMPLETE).is_file() and (g / "bin" / "bash.exe").is_file()

    def bash_values(self) -> list[str]:
        """``CLAUDE_CODE_GIT_BASH_PATH`` as this process, the user (HKCU) and the machine (HKLM) have it."""
        return bash_values(self.environ, self.registry)

    def git_present(self) -> bool:
        g = self.which("git")
        if g and within(g, self.tools / "git"):
            return self.git_complete()  # ours on PATH: only when the extraction finished
        if self.git_complete():
            return True
        return bool(git_bash(None if not g or store_stub(g) else g, self.bash_values()))

    def node_present(self) -> bool:
        n = self.tools / "node"
        if (n / "node.exe").is_file() and (n / "npm.cmd").is_file():
            return True
        exe, npm = self.which("node"), self.which("npm")
        if not exe or not npm or store_stub(exe) or store_stub(npm):
            return False
        cp = self.run([exe, "--version"], timeout=15, stdin_devnull=True)
        v = ver(cp.stdout) if cp.returncode == 0 else None
        return bool(v) and v[0] >= self.node_min

    def claude_present(self) -> bool:
        pin = ver(self.claude_v) or (0, 0)
        own = self.local_bin / "claude.exe"  # installed here, PATH not refreshed yet
        for c in (self.which("claude"), str(own) if own.is_file() else None):
            if not c or store_stub(c):
                continue
            cp = self.run([c, "--version"], timeout=30, stdin_devnull=True)
            v = ver(cp.stdout) if cp.returncode == 0 else None
            if v and v[:2] >= pin[:2]:
                return True
        return False

    def uv_present(self) -> bool:
        return bool(self.which("uv")) or (self.tools / "bin" / "uv.exe").is_file()

    def gh_present(self) -> bool:
        return bool(self.which("gh")) or (self.tools / "gh" / "bin" / "gh.exe").is_file()
