#!/usr/bin/env python3
"""winollama.py — ollama on Windows: the pinned release zip into ``<tools>\\ollama``, no admin.

The zip (``ollama.exe`` + ``lib\\ollama``, 1.4 GB, ~3.3 GB while extracting) replaces the 1.6 GB
``OllamaSetup.exe`` (tray app, its own autostart). A binary counts as installed only with its
``.agentic-mercy-complete`` marker (an interrupted extraction leaves ``ollama.exe`` without its
libs and is repaired on the next run); the user's own ollama, or any server already answering on
11434, is left alone. Autostart is one ``HKCU\\...\\Run`` value (``conhost.exe --headless ... serve``:
no console flash, no admin) created right after OUR install and only when nothing answers yet.
Called by ``ollama_setup.install_ollama`` on Windows; every seam is injected. Pure stdlib.
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
from safe_fetch import download as _download, extract_zip_prefix  # noqa: E402
import winpath  # noqa: E402
from winlock import BUSY, InstallLock  # noqa: E402
from winutil import COMPLETE, drop, free_bytes, guard, sha256_ok, which as safe_which, win_arch, within  # noqa: E402

RUN_VALUE = "agentic-mercy-ollama"


def install(cfg: dict, *, ci: bool, dry_run: bool, which: Callable = safe_which,
            download: Callable = _download, registry=None, disk_free: Callable = free_bytes,
            environ=None, probe: Callable = lambda: None) -> str:
    """PRESENT / WOULD-INSTALL / INSTALLED ... / WARN(...) for ollama on Windows."""
    environ = os.environ if environ is None else environ
    odir = winpath.tools_dir(environ) / "ollama"
    exe, found = odir / "ollama.exe", which("ollama")
    if found and not within(found, odir):
        return "PRESENT"  # the user's own ollama: trusted
    if exe.is_file() and (odir / COMPLETE).is_file():
        return "PRESENT"
    if not found and probe() is not None:
        return "PRESENT"  # a server answers (the desktop app, a service): nothing to install
    arch = win_arch(environ)
    url = cfg["url"].format(version=cfg["version"], arch=cfg["arch"][arch])
    if ci or dry_run:
        return f"WOULD-INSTALL(user-space, no admin): {url}"
    return guard(lambda: _install(cfg, url, arch, odir, download, registry, disk_free, environ, probe))


def _install(cfg, url, arch, odir, download, registry, disk_free, environ, probe) -> str:
    need = int(cfg.get("min_free_gb", 4))
    free = disk_free(odir)
    if free < need << 30:
        return f"WARN(need at least {need} GB free for ollama in {odir.parent}, have {free / (1 << 30):.1f} GB)"
    lock = InstallLock(odir.parent)  # one install at a time per tools dir (A5v2-04)
    try:
        return _unpack(cfg, url, arch, odir, download, registry, environ, probe) if lock.take() else BUSY
    finally:
        lock.release()


def _unpack(cfg, url, arch, odir, download, registry, environ, probe) -> str:
    zpath = odir.parent / "cache" / url.rsplit("/", 1)[-1]
    zpath.parent.mkdir(parents=True, exist_ok=True)
    if not sha256_ok(zpath, cfg["sha256"][arch]):  # a failed run keeps the verified 1.4 GB zip for the retry
        download(url, zpath, timeout=3600, sha256=cfg["sha256"][arch], require_hash=True)
    with zipfile.ZipFile(zpath) as zf:
        extract_zip_prefix(zf, odir, strip=0)
    if not (odir / "ollama.exe").is_file():  # the verified zip stays for the retry
        return "WARN(ollama.exe missing after extraction)"
    drop(zpath)  # only after the extraction worked; a scanner still holding it is not a failure
    (odir / COMPLETE).write_text(cfg["version"], encoding="utf-8")
    registry = winpath.WinRegistry() if registry is None else registry
    winpath.add_user_path([odir], registry, environ)
    auto = ""
    if probe() is None and winpath.set_run_value(
            RUN_VALUE, f'conhost.exe --headless "{odir / "ollama.exe"}" serve', registry, environ):
        auto = " (autostart: HKCU Run)"
    return f"INSTALLED ollama {cfg['version']} -> {odir}{auto}"
