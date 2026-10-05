"""npm_pack.py — install an npm global from a tarball whose path hides the package name.

``lean-ctx-bin``'s preinstall runs ``pkill -f lean-ctx``. That matches the ``npm install -g
lean-ctx-bin@…`` process running it, so npm dies with SIGTERM (rc 1), rolls the package back
and leaves dangling bin links. ``npm pack`` runs no install scripts, so it is safe; the tarball
is then installed from ``<tmp>/pkg.tgz``, a command line without the name. Pure stdlib.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402

_SELF_KILLING = ("lean-ctx",)


def needs_pack(cmd: list) -> bool:
    return list(cmd[:3]) == ["npm", "install", "-g"] and any(
        any(name in str(a) for name in _SELF_KILLING) for a in cmd[3:])


def _drop_dangling_links() -> None:
    bin_dir = Path.home() / ".local" / "bin"
    if not bin_dir.is_dir():
        return
    for p in bin_dir.iterdir():  # only links into the lean-ctx install: other dangling links are the user's
        try:
            if p.is_symlink() and not p.exists() and any(n in os.readlink(p) for n in _SELF_KILLING):
                p.unlink()
        except OSError:
            pass


def install(cmd: list, run: Callable = plat.run) -> subprocess.CompletedProcess:
    _drop_dangling_links()
    spec = [str(a) for a in cmd[3:] if not str(a).startswith("-")]
    with tempfile.TemporaryDirectory() as tmp:
        cp = run(["npm", "pack", *spec, "--pack-destination", tmp, "--silent"], timeout=300, stdin_devnull=True)
        packed = sorted(Path(tmp).glob("*.tgz"))
        if cp.returncode != 0 or not packed:
            return cp if cp.returncode != 0 else subprocess.CompletedProcess(cmd, 1, "", "npm pack produced nothing")
        pkg = Path(tmp) / "pkg.tgz"  # a command line without the package name
        packed[0].rename(pkg)
        return run(["npm", "install", "-g", str(pkg)], timeout=600, stdin_devnull=True)
