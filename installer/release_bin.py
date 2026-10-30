"""release_bin.py — the native binary of a script-less npm package, from a pinned GitHub release (F2).

lean-ctx-bin's install scripts must never run: its preinstall `pkill -f lean-ctx`s every running lean-ctx
(other sessions' MCP servers too) and its postinstall downloads `releases/latest` (3.12.0 for the 3.10.5
package on 2026-10-30) and runs `lean-ctx onboard` (telemetry on, the [cloud] opt-outs dropped, 52
`lean-ctx` strings in settings.json, a `serve` daemon). The manifest installs it with
`npm install -g --ignore-scripts`; this module puts the pinned, sha256-checked release binary where the
package's own `bin/<exe>.js` shim looks for it (``manifest.user_space.<key>``: version, npm_pkg, exe,
download, assets{key: name, sha256}). An existing binary at the pin is left alone; one at another version
(3.12.0 from a postinstall that ran before the pin existed) is replaced. Never raises. Pure stdlib.
"""
from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import userspace  # noqa: E402
from lib import platform as plat  # noqa: E402
from safe_fetch import download as _download, extract_prefix, extract_zip_prefix  # noqa: E402


def arch_key() -> str:
    os_tag, arch = userspace.os_arch()
    return f"{'windows' if plat.IS_WINDOWS else os_tag}-{arch}"


def _binary_version(binary: Path) -> str:
    """`<binary> --version` as x.y.z; "" when it cannot run or prints no version."""
    try:
        out = plat.run([str(binary), "--version"], timeout=15).stdout or ""
    except Exception:  # noqa: BLE001
        return ""
    m = re.search(r"\d+\.\d+\.\d+", out)
    return m.group(0) if m else ""


def ensure(cfg: dict, pkg_dir: Path | None, *, dry_run: bool, download: Callable = _download,
           key: str | None = None, version: Callable[[Path], str] = _binary_version) -> tuple[bool, str]:
    """(ok, note to append to the row). ok is False only when a needed binary could not be placed.
    A binary already in the package that is not the pin (a postinstall's releases/latest) is replaced;
    a failed replacement puts the old one back, so the npm shim never ends up without a binary."""
    if not cfg or pkg_dir is None or not (Path(pkg_dir) / "package.json").is_file():
        return True, ""  # not npm-installed here (a hand-installed binary, CI, no npm): nothing to place
    exe = cfg["exe"] + (".exe" if plat.IS_WINDOWS else "")
    binary = Path(pkg_dir) / "bin" / exe
    old: Path | None = None
    have = ""
    if binary.is_file():
        have = version(binary)
        if have == cfg["version"]:
            return True, ""
        if dry_run:
            return True, f" (would replace {cfg['exe']} {have or '?'} with v{cfg['version']})"
    elif dry_run:
        return True, f" (would fetch {cfg['exe']} v{cfg['version']})"
    key = key or arch_key()
    asset = (cfg.get("assets") or {}).get(key)
    if not asset:
        return False, f"no pinned asset for {key}"
    if binary.is_file():
        old = binary.with_name(binary.name + ".old")
        try:  # rename, never overwrite: a running binary is ETXTBSY on Linux and locked on Windows
            if old.exists():
                old.unlink()
            binary.replace(old)
        except OSError as exc:
            return False, f"cannot move {cfg['exe']} {have or '?'} aside: {type(exc).__name__}"
    url = cfg["download"].format(version=cfg["version"], asset=asset["name"])
    err = ""
    try:
        with userspace.scratch() as tmp:
            arc = Path(tmp) / asset["name"]
            download(url, arc, timeout=600, sha256=asset["sha256"])
            if asset["name"].endswith(".zip"):
                with zipfile.ZipFile(arc) as zf:
                    extract_zip_prefix(zf, binary.parent, strip=0, only=lambda p: p == exe)
            else:
                with tarfile.open(arc, "r:gz") as tf:
                    extract_prefix(tf, binary.parent, strip=0, skip_top_files=False, only=lambda p: p == exe)
    except Exception as exc:  # noqa: BLE001 - a blocked or bad download is a row, not a crash
        err = f"{type(exc).__name__}: {str(exc)[:80]}"
    if not err and not binary.is_file():
        err = f"archive had no {exe}"
    if err:
        if old is not None:
            try:
                old.replace(binary)
            except OSError:
                pass
        return False, err
    if not plat.IS_WINDOWS:
        binary.chmod(0o755)
    if old is not None:
        try:
            old.unlink()  # POSIX: fine while it runs; a Windows binary in use stays and goes next run
        except OSError:
            pass
        return True, f" ({cfg['exe']} {have or '?'} replaced with v{cfg['version']} release binary, sha256 ok)"
    return True, f" ({cfg['exe']} v{cfg['version']} release binary, sha256 ok)"
