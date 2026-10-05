#!/usr/bin/env python3
"""userspace.py — install the base tools a brand-new Linux/macOS user lacks, with no sudo.

node (+npm/npx) from the official tarball, the Claude Code CLI from Anthropic's own
installer, uv from astral's installer and gh from the GitHub release tarball — all into
``~/.local`` (``~/.local/bin`` goes on this process's PATH). Downloads use ``urllib`` so
only python3 is assumed; node tarballs are checked against the published SHASUMS256.
Every function is idempotent and returns a status string (never raises): a failed or
blocked download is a ``WARN(...)`` row, so the doctor and the end-of-run checklist say
what is still missing. Windows is untouched (``install.ps1`` / winget own it). Pure stdlib.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform as _pf
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from lib import platform as plat  # noqa: E402
from safe_fetch import download, extract_prefix, fetch  # noqa: E402,F401 (re-exported: ollama_setup, tests)

NODE_DIST = "https://nodejs.org/dist"
_ARCH = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}


def local_bin() -> Path:
    return Path.home() / ".local" / "bin"


def ensure_path() -> None:
    """Put ~/.local/bin first on THIS process's PATH (children inherit it)."""
    lb = str(local_bin())
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p and p != lb]
    os.environ["PATH"] = os.pathsep.join([lb, *parts])


def os_arch() -> tuple[str, str]:
    """('linux'|'darwin'|'', 'x64'|'arm64'|machine) from the stdlib platform module."""
    system = _pf.system().lower()
    return (system if system in ("linux", "darwin") else ""), _ARCH.get(_pf.machine().lower(), _pf.machine().lower())


def node_asset(index: list, major: int, os_tag: str, arch: str) -> tuple[str, str] | None:
    """Newest LTS release of ``major`` that ships a build for this platform."""
    key = f"linux-{arch}" if os_tag == "linux" else f"osx-{arch}-tar"
    for rel in index:
        v = str(rel.get("version", ""))
        if v.startswith(f"v{major}.") and rel.get("lts") and key in rel.get("files", []):
            return v, f"node-{v}-{os_tag}-{arch}.tar.xz"
    return None


def _node_ok(min_major: int) -> bool:
    cp = plat.run(["node", "--version"], timeout=15, stdin_devnull=True)
    try:
        return cp.returncode == 0 and int((cp.stdout or "").strip().lstrip("v").split(".")[0]) >= min_major
    except ValueError:
        return False


def install_node(cfg: dict, *, fetch: Callable = fetch, download: Callable = download) -> str:
    os_tag, arch = os_arch()
    if not os_tag:
        return "SKIP(unsupported-os)"
    try:
        asset = node_asset(json.loads(fetch(f"{NODE_DIST}/index.json")), int(cfg.get("major", 22)), os_tag, arch)
        if not asset:
            return f"WARN(no node build for {os_tag}-{arch})"
        version, name = asset
        sums = fetch(f"{NODE_DIST}/{version}/SHASUMS256.txt").decode("utf-8", "replace")
        want = next((ln.split()[0] for ln in sums.splitlines() if ln.endswith(" " + name)), "")
        with tempfile.TemporaryDirectory() as tmp:
            tgz = Path(tmp) / name
            download(f"{NODE_DIST}/{version}/{name}", tgz)
            if hashlib.sha256(tgz.read_bytes()).hexdigest() != want:
                return "WARN(checksum mismatch — refused)"
            prefix = Path.home() / ".local"
            with tarfile.open(tgz, "r:xz") as tf:
                extract_prefix(tf, prefix)
        ensure_path()
        return f"INSTALLED node {version} -> ~/.local"
    except Exception as exc:  # noqa: BLE001 - blocked network etc. is a row, not a crash
        return f"WARN({type(exc).__name__}: {str(exc)[:80]})"


def fix_npm_prefix(run: Callable = plat.run) -> str:
    """A system node (apt) has a root-owned -g prefix: point npm at ~/.local (user .npmrc)."""
    cp = run(["npm", "config", "get", "prefix"], timeout=30, stdin_devnull=True)
    prefix = (cp.stdout or "").strip()
    if cp.returncode != 0 or not prefix or os.access(prefix, os.W_OK):
        return ""
    run(["npm", "config", "set", "prefix", str(Path.home() / ".local")], timeout=30, stdin_devnull=True)
    return " (npm -g prefix -> ~/.local)"


def _script_run(url: str, args: list[str], shell: str, run: Callable, fetch: Callable, timeout: int) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "install.sh"
        script.write_bytes(fetch(url))
        return run([shell, str(script), *args], timeout=timeout, stdin_devnull=True).returncode


def install_claude(version: str, *, run: Callable = plat.run, fetch: Callable = fetch,
                   url: str = "https://claude.ai/install.sh", has_npm: bool | None = None) -> str:
    """Anthropic's native installer (-> ~/.local/bin/claude), pinned to ``version``;
    npm fallback when the script cannot run."""
    try:
        if _script_run(url, [version] if version else [], "bash", run, fetch, 600) == 0:
            ensure_path()
            return f"INSTALLED claude {version or 'latest'} (official installer)"
    except Exception:  # noqa: BLE001
        pass
    if has_npm is None:
        has_npm = shutil.which("npm") is not None
    if has_npm:
        spec = "@anthropic-ai/claude-code" + (f"@{version}" if version else "")
        if run(["npm", "install", "-g", spec], timeout=600, stdin_devnull=True).returncode == 0:
            return f"INSTALLED claude {version or 'latest'} (npm)"
    return "WARN(claude installer failed — https://claude.ai/install.sh)"


def install_uv(*, run: Callable = plat.run, fetch: Callable = fetch) -> str:
    try:
        if _script_run("https://astral.sh/uv/install.sh", [], "sh", run, fetch, 300) == 0:
            ensure_path()
            return "INSTALLED uv (astral installer)"
    except Exception as exc:  # noqa: BLE001
        return f"WARN({type(exc).__name__}: {str(exc)[:80]})"
    return "WARN(uv installer failed)"


def scratch() -> tempfile.TemporaryDirectory:
    """Temp dir under ~/.cache (a tmpfs /tmp is RAM, and the ollama archive is 1.4 GB)."""
    base = Path.home() / ".cache" / "agentic-mercy"
    base.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base)


def install_gh(cfg: dict, *, fetch: Callable = fetch, download: Callable = download) -> str:
    """The pinned gh release (``manifest.user_space.gh``: version + SHA-256 per arch)."""
    os_tag, arch = os_arch()
    if os_tag != "linux":
        return "SKIP(brew install gh)"
    gh_arch = "amd64" if arch == "x64" else arch
    try:
        url = cfg["download"].format(version=cfg["version"], arch=gh_arch)
        with scratch() as tmp:
            tgz = Path(tmp) / "gh.tar.gz"
            download(url, tgz, timeout=600, sha256=cfg["sha256"][gh_arch])
            with tarfile.open(tgz, "r:gz") as tf:
                extract_prefix(tf, Path.home() / ".local", skip_top_files=False,
                               only=lambda p: p == "bin/gh")
        ensure_path()
        return f"INSTALLED gh v{cfg['version']}"
    except Exception as exc:  # noqa: BLE001
        return f"WARN({type(exc).__name__}: {str(exc)[:80]})"


def ensure_userspace(env, manifest: dict, *, ci: bool, dry_run: bool, run: Callable = plat.run,
                     fetch_fn: Callable = fetch, download_fn: Callable = download) -> list[tuple[str, str]]:
    """node -> claude -> uv -> gh: PRESENT, WOULD-INSTALL (plan modes) or the install status."""
    if env.os_name != "posix":
        return []
    cfg = manifest.get("user_space") or {}
    ensure_path()
    plan = ci or dry_run
    node_cfg = cfg.get("node", {})
    claude_v = (manifest.get("mods") or {}).get("claude_version", "")
    steps = [
        ("node", lambda: _node_ok(int(node_cfg.get("min", 18))) and shutil.which("npm") is not None,
         lambda: install_node(node_cfg, fetch=fetch_fn, download=download_fn)),
        ("claude", lambda: shutil.which("claude") is not None,
         lambda: install_claude(claude_v, run=run, fetch=fetch_fn, url=(cfg.get("claude") or {}).get(
             "installer", "https://claude.ai/install.sh"))),
        ("uv", lambda: shutil.which("uv") is not None, lambda: install_uv(run=run, fetch=fetch_fn)),
        ("gh", lambda: shutil.which("gh") is not None,
         lambda: install_gh(cfg.get("gh") or {}, fetch=fetch_fn, download=download_fn)),
    ]
    rows: list[tuple[str, str]] = []
    for name, present, do in steps:
        if present():
            note = fix_npm_prefix(run) if name == "node" and not plan else ""
            rows.append((name, "PRESENT" + note))
        elif plan:
            rows.append((name, f"WOULD-INSTALL(user-space, no sudo) {name}"))
        else:
            rows.append((name, do()))
    return rows
