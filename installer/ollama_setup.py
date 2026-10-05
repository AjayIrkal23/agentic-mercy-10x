#!/usr/bin/env python3
"""ollama_setup.py — a no-sudo ollama plus the models the code indexes use.

jcodemunch / jdocmunch read embeddings from a local ollama (``all-minilm``) and
jcodemunch's AI summaries from ``qwen2.5-coder:3b`` (manifest ``user_space.ollama``).
The official ``install.sh`` needs root and a system service, so this unpacks the release
tarball into ``~/.local`` (``bin/ollama`` + ``lib/ollama``), starts a ``systemctl --user``
unit when there is a user manager (else one detached ``ollama serve``), and pulls the
models that are missing. Linux only (macOS: the app / brew). Everything is a status row;
a blocked download or no zstd is a WARN, never a failure. Pure stdlib.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import userspace  # noqa: E402
from lib import platform as plat  # noqa: E402

TAGS_URL = "http://127.0.0.1:11434/api/tags"
_UNIT = """[Unit]
Description=ollama (user-space, agentic-mercy)

[Service]
ExecStart={exe} serve
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
"""


COMPLETE = ".agentic-mercy-complete"  # written into ~/.local/lib/ollama after a verified extraction


def _pin_key(os_tag: str, arch: str) -> str:
    return f"{os_tag}-{'amd64' if arch == 'x64' else arch}"


def asset_url(cfg: dict, os_tag: str, arch: str) -> str | None:
    if os_tag != "linux":
        return None
    return cfg["download"].format(os=os_tag, arch="amd64" if arch == "x64" else arch,
                                  version=cfg.get("version", ""))


def _stdlib_zstd() -> bool:
    try:
        import compression.zstd  # noqa: F401  (python >= 3.14)
        return True
    except ImportError:
        return False


def pick_extractor(which: Callable = shutil.which, stdlib_zstd: bool | None = None) -> str | None:
    if _stdlib_zstd() if stdlib_zstd is None else stdlib_zstd:
        return "stdlib"
    if which("zstd"):
        return "zstd"
    return "uv" if which("uv") else None


def extract_zst(archive, dest, which: Callable = shutil.which) -> None:
    """Unpack an ollama .tar.zst (no wrapper dir) into the ``dest`` prefix."""
    how = pick_extractor(which)
    if how is None:
        raise RuntimeError("no zstd decoder (python>=3.14, the zstd binary or uv)")
    if how == "uv":
        cp = plat.run(["uv", "run", "--no-project", "--with", "zstandard", "python",
                       str(_HERE / "zst_untar.py"), str(archive), str(dest)], timeout=1800)
        if cp.returncode != 0:
            raise RuntimeError(f"uv zstandard extract failed rc={cp.returncode}")
        return
    if how == "stdlib":
        from compression import zstd  # type: ignore
        with zstd.open(archive, "rb") as fh, tarfile.open(fileobj=fh, mode="r|") as tf:
            userspace.extract_prefix(tf, Path(dest), strip=0, skip_top_files=False)
        return
    proc = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)  # noqa: S603,S607
    with tarfile.open(fileobj=proc.stdout, mode="r|") as tf:
        userspace.extract_prefix(tf, Path(dest), strip=0, skip_top_files=False)
    if proc.wait() != 0:
        raise RuntimeError("zstd -d failed")


def _local_bin() -> Path:
    return Path.home() / ".local" / "bin"


def installed(which: Callable = shutil.which) -> bool:
    """An ollama binary that works. One the installer put in ~/.local/bin counts only when its
    libs are there too (bin/ollama is the archive's FIRST member: a failed or interrupted extraction
    leaves a binary without them); an ollama anywhere else is the user's and is trusted."""
    exe = which("ollama")
    if not exe:
        return False
    if Path(exe).parent != _local_bin():
        return True
    return (Path.home() / ".local" / "lib" / "ollama" / COMPLETE).is_file()


def install_ollama(cfg: dict, *, ci: bool, dry_run: bool, which: Callable = shutil.which,
                   download: Callable = userspace.download, extract: Callable = extract_zst,
                   system: tuple[str, str] | None = None) -> str:
    if installed(which):
        return "PRESENT"
    os_tag, arch = system or userspace.os_arch()
    url = asset_url(cfg, os_tag, arch)
    if not url:
        return "SKIP(install the ollama app or `brew install ollama`)"
    if ci or dry_run:
        return f"WOULD-INSTALL(user-space, no sudo): {url}"
    prefix = Path.home() / ".local"
    try:
        with userspace.scratch() as tmp:  # under ~/.cache: /tmp may be a RAM tmpfs
            archive = Path(tmp) / "ollama.tar.zst"
            download(url, archive, timeout=3600, sha256=(cfg.get("sha256") or {}).get(_pin_key(os_tag, arch)))
            try:
                extract(archive, prefix)
            except BaseException:  # interrupted or out of space: never leave a binary without its libs
                (_local_bin() / "ollama").unlink(missing_ok=True)
                raise
        (prefix / "lib" / "ollama").mkdir(parents=True, exist_ok=True)
        (prefix / "lib" / "ollama" / COMPLETE).write_text(cfg.get("version", ""), encoding="utf-8")
        userspace.ensure_path()
        return "INSTALLED ollama -> ~/.local"
    except Exception as exc:  # noqa: BLE001
        return f"WARN({type(exc).__name__}: {str(exc)[:90]})"


def probe(url: str = TAGS_URL) -> set | None:
    """Model names the local server has, or None when no server answers."""
    try:
        return {m.get("name", "") for m in json.loads(userspace.fetch(url, 3)).get("models", [])}
    except Exception:  # noqa: BLE001
        return None


def _user_unit(exe: str, run: Callable) -> bool:
    unit = Path.home() / ".config" / "systemd" / "user" / "ollama.service"
    try:
        if not unit.exists():
            unit.parent.mkdir(parents=True, exist_ok=True)
            unit.write_text(_UNIT.format(exe=exe), encoding="utf-8")
            run(["systemctl", "--user", "daemon-reload"], timeout=30)
            return run(["systemctl", "--user", "enable", "--now", "ollama"], timeout=60).returncode == 0
        if "agentic-mercy" not in unit.read_text(encoding="utf-8", errors="replace"):
            return False  # the user's own unit: never touched
        if (run(["systemctl", "--user", "is-enabled", "ollama"], timeout=15).stdout or "").strip() != "enabled":
            return False  # they disabled ours on purpose
        return run(["systemctl", "--user", "start", "ollama"], timeout=60).returncode == 0
    except OSError:
        return False


def ensure_server(*, probe: Callable = probe, spawn: Callable = plat.spawn_detached, run: Callable = plat.run,
                  which: Callable = shutil.which, sleep: Callable = time.sleep, wait_s: int = 60) -> bool:
    """A server answering on 11434 (any kind, a system service included) is left alone. Otherwise a
    ``systemctl --user`` unit is created ONLY when none exists and ollama is the binary the installer
    put in ~/.local/bin; a unit the user owns is never rewritten, and our own one the user disabled is
    never re-enabled. Everything else gets one detached ``ollama serve`` (the models need a server)."""
    if probe() is not None:
        return True
    exe = which("ollama")
    started = False
    if (exe and Path(exe).parent == _local_bin() and which("systemctl")
            and run(["systemctl", "--user", "show-environment"], timeout=15).returncode == 0):
        started = _user_unit(exe, run)
    if not started:
        spawn(["ollama", "serve"])
    for _ in range(max(1, wait_s)):
        if probe() is not None:
            return True
        sleep(1)
    return False


def pull_models(models: list[str], *, run: Callable = plat.run, probe: Callable = probe,
                ensure_server: Callable = ensure_server) -> list[tuple[str, str]]:
    if not ensure_server():
        return [(f"ollama:{m}", "WARN(no ollama server — run `ollama serve`, then `ollama pull " + m + "`)")
                for m in models]
    have = probe() or set()
    base = {n.split(":")[0] for n in have}
    rows = []
    for m in models:
        if (m in have) if ":" in m else (m in base):
            rows.append((f"ollama:{m}", "PRESENT"))
            continue
        cp = run(["ollama", "pull", m], timeout=3600, stdin_devnull=True)
        rows.append((f"ollama:{m}", "INSTALLED" if cp.returncode == 0 else f"WARN(rc={cp.returncode})"))
    return rows


def setup_ollama(manifest: dict, *, ci: bool, dry_run: bool) -> list[tuple[str, str]]:
    cfg = (manifest.get("user_space") or {}).get("ollama")
    if not cfg:
        return []
    status = install_ollama(cfg, ci=ci, dry_run=dry_run)
    rows = [("ollama", status)]
    if ci or dry_run:
        return rows + [(f"ollama:{m}", "WOULD-PULL") for m in cfg.get("models", [])]
    if status.startswith(("WARN", "SKIP")):
        return rows
    return rows + pull_models(cfg.get("models", []))
