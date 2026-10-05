"""User-space prerequisite installs (node, claude, uv, gh) for a fresh machine.

Nothing here touches the network or the real HOME: downloads, subprocesses and the
home dir are injected / sandboxed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import userspace  # noqa: E402

MANIFEST = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))

INDEX = [
    {"version": "v24.1.0", "lts": "Krypton", "files": ["linux-x64", "linux-arm64", "osx-arm64-tar"]},
    {"version": "v22.9.0", "lts": False, "files": ["linux-x64"]},
    {"version": "v22.8.0", "lts": "Jod", "files": ["linux-x64", "linux-arm64", "osx-x64-tar", "osx-arm64-tar"]},
    {"version": "v22.7.0", "lts": "Jod", "files": ["linux-x64"]},
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    return h


def _node_tarball(version: str) -> bytes:
    buf = io.BytesIO()
    top = f"node-{version}-linux-x64"
    with tarfile.open(fileobj=buf, mode="w:xz") as tf:
        for name, data in (("bin/node", b"#!/bin/sh\necho node\n"), ("README.md", b"docs"),
                           ("CHANGELOG.md", b"log"), ("lib/node_modules/npm/package.json", b"{}")):
            ti = tarfile.TarInfo(f"{top}/{name}")
            ti.size, ti.mode = len(data), 0o755
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def _fake_net(tarball: bytes, version: str, good_sum: bool = True):
    name = f"node-{version}-linux-x64.tar.xz"
    sums = f"{hashlib.sha256(tarball).hexdigest() if good_sum else '0' * 64}  {name}\n"

    def fetch(url, timeout=60):
        if url.endswith("index.json"):
            return json.dumps(INDEX).encode()
        if url.endswith("SHASUMS256.txt"):
            return sums.encode()
        raise AssertionError(url)

    def download(url, dest, timeout=900):
        assert url.endswith(name), url
        Path(dest).write_bytes(tarball)
    return fetch, download


def test_node_asset_picks_newest_lts_of_the_pinned_major():
    assert userspace.node_asset(INDEX, 22, "linux", "x64") == ("v22.8.0", "node-v22.8.0-linux-x64.tar.xz")


def test_node_asset_none_when_the_platform_has_no_build():
    assert userspace.node_asset(INDEX, 22, "linux", "armv7l") is None


def test_ensure_path_prepends_local_bin_once(home):
    userspace.ensure_path()
    userspace.ensure_path()
    parts = os.environ["PATH"].split(os.pathsep)
    assert parts[0] == str(home / ".local" / "bin") and parts.count(parts[0]) == 1


@pytest.fixture
def linux(monkeypatch):
    """The node install path is POSIX-only (Windows uses install.ps1); test its logic anywhere."""
    monkeypatch.setattr(userspace, "os_arch", lambda: ("linux", "x64"))


def test_install_node_extracts_into_local_prefix_and_skips_top_docs(home, linux):
    fetch, download = _fake_net(_node_tarball("v22.8.0"), "v22.8.0")
    status = userspace.install_node({"major": 22}, fetch=fetch, download=download)
    assert status.startswith("INSTALLED")
    assert (home / ".local" / "bin" / "node").is_file()
    assert (home / ".local" / "lib" / "node_modules" / "npm" / "package.json").is_file()
    assert not (home / ".local" / "README.md").exists()


def test_install_node_refuses_a_checksum_mismatch(home, linux):
    fetch, download = _fake_net(_node_tarball("v22.8.0"), "v22.8.0", good_sum=False)
    status = userspace.install_node({"major": 22}, fetch=fetch, download=download)
    assert status.startswith("WARN") and "checksum" in status
    assert not (home / ".local" / "bin" / "node").exists()


def test_install_node_network_failure_is_a_warn_not_a_raise(home, linux):
    def boom(*_a, **_k):
        raise OSError("blocked")
    assert userspace.install_node({"major": 22}, fetch=boom, download=boom).startswith("WARN")


def test_claude_installer_runs_with_the_manifest_mods_version(home):
    calls = []

    def run(argv, **kw):
        calls.append([str(a) for a in argv])
        return subprocess.CompletedProcess(argv, 0, "", "")
    status = userspace.install_claude("2.1.288", run=run, fetch=lambda u, timeout=60: b"#!/bin/bash\n")
    assert status.startswith("INSTALLED")
    assert calls[0][0] == "bash" and calls[0][-1] == "2.1.288"


def test_claude_installer_failure_falls_back_to_npm(home):
    calls = []

    def run(argv, **kw):
        calls.append([str(a) for a in argv])
        return subprocess.CompletedProcess(argv, 1 if argv[0] == "bash" else 0, "", "")
    status = userspace.install_claude("2.1.288", run=run, fetch=lambda u, timeout=60: b"x",
                                      has_npm=True)
    assert calls[-1][:3] == ["npm", "install", "-g"] and "@anthropic-ai/claude-code@2.1.288" in calls[-1]
    assert status.startswith("INSTALLED")


def test_ensure_userspace_ci_only_plans(home, monkeypatch):
    monkeypatch.setattr(userspace.shutil, "which", lambda n: None)
    monkeypatch.setattr(userspace, "_node_ok", lambda min_major: False)
    env = SimpleNamespace(os_name="posix")
    rows = userspace.ensure_userspace(env, MANIFEST, ci=True, dry_run=True)
    names = {n for n, _ in rows}
    assert {"node", "claude", "uv", "gh"} <= names
    assert all(s.startswith("WOULD-") for _, s in rows)
    assert not (home / ".local").exists()


def test_ensure_userspace_skips_present_tools(home, monkeypatch):
    monkeypatch.setattr(userspace.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(userspace, "_node_ok", lambda min_major: True)
    rows = dict(userspace.ensure_userspace(SimpleNamespace(os_name="posix"), MANIFEST, ci=False, dry_run=False))
    assert set(rows.values()) == {"PRESENT"}


def test_userspace_declines_windows_and_basetools_routes_it_to_wintools(home, monkeypatch):
    """userspace is POSIX-only; node / git / claude / uv / gh on Windows come from wintools."""
    assert userspace.ensure_userspace(SimpleNamespace(os_name="windows"), MANIFEST, ci=False, dry_run=False) == []
    import basetools
    import wintools
    seen: list = []
    monkeypatch.setattr(basetools.plat, "IS_WINDOWS", True)
    monkeypatch.setattr(wintools, "ensure_wintools", lambda *a, **k: seen.append("wintools") or [])
    basetools.ensure_base_tools(SimpleNamespace(os_name="windows"), MANIFEST, ci=False, dry_run=False)
    assert seen == ["wintools"]


def test_downloads_refuse_non_http_schemes(tmp_path):
    """urllib also opens file:// and ftp://; a manifest or API value must never read local files."""
    for bad in ("file:///etc/passwd", "ftp://h/x"):
        with pytest.raises(ValueError):
            userspace.fetch(bad)
        with pytest.raises(ValueError):
            userspace.download(bad, tmp_path / "x")


def test_graphify_serve_venv_pins_mcp():
    """An unpinned `mcp` resolved to 2.x, whose mcp.types lost AnyUrl: the graphify MCP server
    died on import on every fresh install (host venv runs mcp 1.28.1)."""
    dep = next(d for d in MANIFEST["deps"] if d["id"] == "graphify-serve-venv")
    cmd = " ".join(dep["install_posix"])
    assert "graphifyy==0.9.18" in cmd and "mcp==1.28.1" in cmd


def test_manifest_declares_user_space_contract():
    us = MANIFEST["user_space"]
    assert us["node"]["major"] >= 18
    assert us["claude"]["installer"].startswith("https://claude.ai/")
    assert {t["bin"] for t in us["os_tools"]} >= {"canberra-gtk-play", "notify-send", "ss", "pw-play"}
    assert us["ollama"]["models"][0] == "all-minilm"
