"""basetools.py — the fresh-machine part of the install pass (called by ``selfheal``).

``before_deps``: on Linux, apt OS tools (root or `sudo -n` only; otherwise the one sudo command is
handed back for the final checklist), then node / claude / uv / gh into ``~/.local``; on Windows,
``wintools`` (git with bash, node, claude, uv, gh into the per-user tools dir: no apt, no admin).
Returns the re-detected env (the new claude / npm / uv are on PATH) and the pending sudo command.
``after_deps``: ollama + the models the code indexes use. ``AGENTIC_MERCY_SKIP_BASE_TOOLS=1``
(offline machines, the test suite) skips both. ``ensure_gitleaks``: the pinned gitleaks release
(layer 1 of scripts/golive.py's secrets scan) into ``~/.local/bin``, Linux only, no sudo.
"""
from __future__ import annotations

import os
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import detect  # noqa: E402
import ollama_setup  # noqa: E402
import ostools  # noqa: E402
import userspace  # noqa: E402
import wintools  # noqa: E402
from lib import platform as plat  # noqa: E402
from safe_fetch import download as _download, extract_prefix as _extract_prefix  # noqa: E402


def skipped() -> bool:
    return bool(os.environ.get("AGENTIC_MERCY_SKIP_BASE_TOOLS"))


def _os_arch():  # seam for tests
    return userspace.os_arch()


def ensure_gitleaks(manifest: dict, *, ci: bool, dry_run: bool, download: Callable = _download,
                    which: Callable | None = None) -> tuple[str, str]:
    """gitleaks (layer 1 of the go-live secrets scan) from the pinned release tarball into ~/.local/bin,
    sha256-checked (manifest.user_space.gitleaks: version, download template, sha256 per arch). No sudo.
    The release tarball is flat (``gitleaks`` at the root): only that one vetted member is extracted."""
    cfg = (manifest.get("user_space") or {}).get("gitleaks")
    if not cfg:
        return "gitleaks", "SKIP(no manifest entry)"
    if plat.IS_WINDOWS:
        return "gitleaks", "SKIP(windows)"
    if (which or shutil.which)("gitleaks"):  # looked up at call time: a test's patch of shutil.which applies
        return "gitleaks", "PRESENT"
    if ci or dry_run:
        return "gitleaks", f"WOULD-INSTALL gitleaks v{cfg['version']}"
    os_tag, arch = _os_arch()
    if os_tag != "linux" or arch not in (cfg.get("sha256") or {}):
        return "gitleaks", f"SKIP({os_tag}-{arch}: no pinned asset)"
    try:
        url = cfg["download"].format(version=cfg["version"], arch=arch)
        with userspace.scratch() as tmp:
            tgz = Path(tmp) / "gitleaks.tar.gz"
            download(url, tgz, timeout=600, sha256=cfg["sha256"][arch])
            with tarfile.open(tgz, "r:gz") as tf:
                _extract_prefix(tf, Path.home() / ".local" / "bin", strip=0, skip_top_files=False,
                                only=lambda p: p == "gitleaks")
        binary = Path.home() / ".local" / "bin" / "gitleaks"
        if not binary.is_file():
            return "gitleaks", "WARN(archive had no gitleaks binary)"
        binary.chmod(0o755)
        userspace.ensure_path()
        return "gitleaks", f"INSTALLED gitleaks v{cfg['version']}"
    except Exception as exc:  # noqa: BLE001  install is best effort; golive re-checks `which gitleaks`
        return "gitleaks", f"WARN({type(exc).__name__}: {str(exc)[:80]})"


def ensure_base_tools(env, manifest: dict, *, ci: bool = False, dry_run: bool = False) -> list[tuple[str, str]]:
    """The OS's no-admin installer for node / claude / uv / gh (+ git on Windows)."""
    ensure = wintools.ensure_wintools if plat.IS_WINDOWS else userspace.ensure_userspace
    return ensure(env, manifest, ci=ci, dry_run=dry_run)


def before_deps(env, manifest: dict, ci: bool, emit):
    if skipped():
        return env, None
    sudo_cmd = None
    if not plat.IS_WINDOWS:
        rows, sudo_cmd = ostools.install_os_tools(manifest, ci=ci, dry_run=ci,
                                                  say=lambda line: emit("base", "apt", line.strip()))
        for name, s in rows:
            emit("base", name, s)
    for name, s in ensure_base_tools(env, manifest, ci=ci, dry_run=ci):
        emit("base", name, s)
    g = ensure_gitleaks(manifest, ci=ci, dry_run=ci)
    if not g[1].startswith("SKIP"):  # Windows / no manifest entry: nothing to report
        emit("base", *g)
    return (env if ci else detect.detect()), sudo_cmd


def after_deps(manifest: dict, ci: bool, emit) -> None:
    if not skipped():
        for name, s in ollama_setup.setup_ollama(manifest, ci=ci, dry_run=ci):
            emit("base", name, s)
