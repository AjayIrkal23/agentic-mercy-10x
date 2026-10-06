#!/usr/bin/env python3
"""wintools.py — the Windows twin of userspace.py: git, node, Claude Code, uv, gh, no admin.

Everything lands in one per-user tools dir (``winpath.tools_dir``: ``<tools>\\{git,node,npm-global,
bin,gh,ollama,cache}``), from pinned URLs + SHA-256 (``manifest.user_space.windows``), through
``safe_fetch.download`` / ``extract_zip_prefix``. What counts as already installed is ``winprobe``'s
call. Each tool is a status row, never an exception; downloads, processes, the registry and ``which``
are injected. One install at a time per tools dir (``winlock``): a second run reports "another install
is running" and changes nothing. A verified archive is deleted only after the install worked (a failed
extraction keeps it, the retry reuses it without downloading again); a leftover that cannot be deleted
is not a failure. The npm global prefix is an idempotent step of its own, so a failed first attempt is
repaired on the next run. Pure stdlib; ``winreg`` only inside ``winpath.WinRegistry``.
"""
from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from lib import platform as plat  # noqa: E402
from safe_fetch import download, extract_zip_prefix  # noqa: E402
import winpath  # noqa: E402
from winlock import BUSY, InstallLock  # noqa: E402
from winprobe import Probe  # noqa: E402
from winutil import (COMPLETE, GIT_BASH_VAR, drop, free_bytes, guard, same_path, sha256_ok,  # noqa: E402
                     signature_problem, which as safe_which, within)

CLAUDE_SIGNER = "Anthropic, PBC"  # the certificate name of downloads.claude.ai/.../claude.exe (observed)
_MIN_FREE = 1 << 30
_PREFIX_WARN = "WARN(npm config set prefix failed: `npm install -g` would write to %APPDATA%\\npm, which is not on PATH)"


class _Box(Probe):
    def __init__(self, manifest, run, download_fn, which, disk_free, environ, registry):
        super().__init__(manifest, run, which, environ, registry)
        self.download_fn, self.disk_free = download_fn, disk_free

    # --- install -------------------------------------------------------------------------- #
    def get(self, name: str) -> Path:
        """The pinned archive in ``<tools>\\cache``: reused when a failed run left it and its SHA-256 still
        matches the pin, else downloaded (the download verifies it again)."""
        cfg = self.cfg[name]
        url = cfg["url"].format(version=cfg["version"], tag=cfg.get("tag", ""), arch=cfg["arch"][self.arch])
        dest = self.tools / "cache" / url.rsplit("/", 1)[-1]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not sha256_ok(dest, cfg["sha256"][self.arch]):
            self.download_fn(url, dest, timeout=1800, sha256=cfg["sha256"][self.arch], require_hash=True)
        return dest

    def unzip(self, name: str, dest: Path, exe: str) -> str:
        z = self.get(name)
        with zipfile.ZipFile(z) as zf:
            extract_zip_prefix(zf, dest, strip=int(self.cfg[name].get("strip", 0)))
        if not (dest / exe).is_file():
            return f"WARN({exe} missing after extraction)"
        drop(z)  # only now: a failed extraction keeps the verified archive for the retry
        return f"INSTALLED {name} {self.cfg[name]['version']}"

    def install(self, name: str) -> str:
        if self.disk_free(self.tools) < _MIN_FREE:
            return f"WARN(less than 1 GB free for {self.tools})"
        return getattr(self, f"install_{name}")()

    def install_git(self) -> str:
        g, exe = self.tools / "git", self.get("git")
        try:  # an executable installer is never left in the cache, whatever happened
            if bad := signature_problem(exe, self.run, self.environ):  # signer not documented: bad ones only
                return bad
            rc = self.run([str(exe), "-y", f"-o{g}"], timeout=1800, stdin_devnull=True).returncode
        finally:
            drop(exe)
        if rc != 0 or not (g / "bin" / "bash.exe").is_file():
            return f"WARN(PortableGit extraction failed rc={rc})"
        (g / COMPLETE).write_text(self.cfg["git"]["version"], encoding="utf-8")
        return f"INSTALLED git {self.cfg['git']['version']} (with bash)"

    def install_node(self) -> str:
        return self.unzip("node", self.tools / "node", "node.exe")

    def ensure_npm_prefix(self) -> str | None:
        """Our node's global prefix is ``<tools>\\npm-global`` (A5v2-03): checked on every run, so a failed
        or interrupted first attempt is repaired. None = already right (or not our node)."""
        npm, want = self.tools / "node" / "npm.cmd", self.tools / "npm-global"
        if not npm.is_file():
            return None
        cp = self.run([str(npm), "config", "get", "prefix"], timeout=60, stdin_devnull=True)
        if cp.returncode == 0 and same_path((cp.stdout or "").strip(), want):
            return None
        want.mkdir(parents=True, exist_ok=True)
        cp = self.run([str(npm), "config", "set", "prefix", str(want)], timeout=60, stdin_devnull=True)
        return None if cp.returncode == 0 else _PREFIX_WARN

    def install_claude(self) -> str:
        if winpath.sandboxed(self.environ):  # the native installer writes the real user PATH
            return "SKIP(sandbox: `claude.exe install` edits the real user PATH; rehearse with --ci)"
        exe = self.get("claude")
        try:
            if bad := signature_problem(exe, self.run, self.environ, (CLAUDE_SIGNER,)):
                return bad
            rc = self.run([str(exe), "install", self.cfg["claude"]["version"]], timeout=900,
                          stdin_devnull=True).returncode
        finally:
            drop(exe)
        if rc != 0 or not (self.local_bin / "claude.exe").is_file():
            return f"WARN(claude.exe install rc={rc})"
        return f"INSTALLED claude {self.cfg['claude']['version']}"

    def install_uv(self) -> str:
        return self.unzip("uv", self.tools / "bin", "uv.exe")

    def install_gh(self) -> str:
        return self.unzip("gh", self.tools / "gh", "bin/gh.exe")

    # --- PATH + environment, once at the end ------------------------------------------------ #
    def finish(self) -> None:
        t, registry = self.tools, self.registry
        user_git = self.which("git") and not within(self.which("git"), t / "git")
        dirs = []
        if (t / "bin" / "uv.exe").is_file():
            dirs.append(t / "bin")
        if (t / "node" / "node.exe").is_file():
            dirs += [t / "node", t / "npm-global"]
        if self.git_complete() and not user_git:  # a user's git keeps its PATH order
            dirs.append(t / "git" / "cmd")
        elif not user_git:  # reused through CLAUDE_CODE_GIT_BASH_PATH but off PATH ("Git Bash only")
            dirs += [c for v in self.bash_values() if v and Path(v).is_file()
                     for c in [Path(v).parent.parent / "cmd"] if (c / "git.exe").is_file()][:1]
        if (t / "gh" / "bin" / "gh.exe").is_file():
            dirs.append(t / "gh" / "bin")
        if (self.local_bin / "claude.exe").is_file() or (t / "bin" / "uv.exe").is_file():
            dirs.append(self.local_bin)  # claude, and where `uv tool install` puts its shims
        if dirs:
            winpath.add_user_path(dirs, registry, self.environ)
        # only for OUR git, and never over a variable that already names an existing file (the user's)
        if self.git_complete() and not any(Path(v).is_file() for v in self.bash_values() if v):
            winpath.set_user_env(GIT_BASH_VAR, str(t / "git" / "bin" / "bash.exe"), registry, self.environ)


def ensure_wintools(env, manifest: dict, *, ci: bool, dry_run: bool, run: Callable = plat.run,
                    download_fn: Callable = download, which: Callable = safe_which, registry=None,
                    disk_free: Callable = free_bytes, environ=None) -> list[tuple[str, str]]:
    """git -> node -> claude -> uv -> gh: PRESENT, WOULD-INSTALL (plan modes) or the install status;
    then our npm prefix is checked, the tools dirs go on the user PATH (registry + this process) and,
    for our git, the ``CLAUDE_CODE_GIT_BASH_PATH`` variable is set when nothing valid names a bash yet.
    ``AGENTIC_MERCY_SKIP_BASE_TOOLS`` skips it all; another install holding the tools-dir lock turns
    every write step into a ``SKIP(another install is running ...)`` row."""
    environ = os.environ if environ is None else environ
    if env.os_name != "windows" or environ.get("AGENTIC_MERCY_SKIP_BASE_TOOLS"):
        return []
    try:
        box = _Box(manifest, run, download_fn, which, disk_free, environ,
                   winpath.WinRegistry() if registry is None else registry)
    except Exception as exc:  # noqa: BLE001  (no profile dir at all: fail closed, never crash the pass)
        return [("base-tools", f"WARN({type(exc).__name__}: {str(exc)[:90]})")]
    plan = ci or dry_run
    rows: list[tuple[str, str]] = []
    lock = InstallLock(box.tools)  # taken lazily: a run that finds everything PRESENT never creates the dir
    try:
        for name in ("git", "node", "claude", "uv", "gh"):
            if getattr(box, f"{name}_present")():
                rows.append((name, "PRESENT"))
            elif plan:
                rows.append((name, f"WOULD-INSTALL(user-space, no admin) {name}"))
            else:
                rows.append((name, guard(lambda n=name: box.install(n)) if lock.take() else BUSY))
        if not plan and lock.take(create=False):
            if fix := guard(box.ensure_npm_prefix):
                rows.append(("npm-prefix", fix))
            if status := guard(lambda: box.finish() or None):
                rows.append(("path", status))
        elif not plan and not any(s == BUSY for _, s in rows):
            rows.append(("base-tools", BUSY))
    finally:
        lock.release()
    if winpath.outside_profile(box.tools, environ):
        rows.append(("tools-dir", f"WARN({winpath.TOOLS_ENV}={box.tools} is outside your profile: other local users "
                                  "may be able to replace the tools there, and they go first on your PATH)"))
    return rows
