"""F1 (a 16 GB laptop, 2026-10-30): node was already present under ~/.local/opt/node-v24.22.1-linux-x64
with only node/npm/npx linked into ~/.local/bin. `npm install -g` put lean-ctx, tdd-guard, pyright,
pyright-langserver and mmx in <prefix>/bin, off PATH: _link_bins (which-based) linked nothing, the lean-ctx
MCP failed with ENOENT and every run reinstalled all four. Links now come from npm's own prefix."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "installer", ROOT / "hooks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import deps  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX npm prefix layout and symlinks")

ENV = SimpleNamespace(os_name="posix", python="python3", node="node", real_dir=None)


@pytest.fixture
def prefix(tmp_path, monkeypatch):
    """A node prefix off PATH, the way the laptop had it."""
    home = tmp_path / "home"
    pre = home / ".local" / "opt" / "node-v24.22.1-linux-x64"
    (pre / "lib" / "node_modules").mkdir(parents=True)
    (pre / "bin").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(deps, "_NPM_ROOT_G", [pre / "lib" / "node_modules"])
    monkeypatch.setattr(deps.plat, "IS_WINDOWS", False)
    return home, pre


def _cli(pre: Path, name: str) -> Path:
    p = pre / "bin" / name
    p.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    p.chmod(0o755)
    return p


def test_npm_bin_dir_is_the_prefix_bin(prefix):
    _, pre = prefix
    assert deps.npm_bin_dir() == pre / "bin"
    assert deps.npm_bin("lean-ctx") is None
    _cli(pre, "lean-ctx")
    assert deps.npm_bin("lean-ctx") == pre / "bin" / "lean-ctx"


def test_windows_shims_sit_in_the_prefix_itself(tmp_path, monkeypatch):
    root = tmp_path / "npm" / "node_modules"
    root.mkdir(parents=True)
    (tmp_path / "npm" / "lean-ctx.cmd").write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr(deps, "_NPM_ROOT_G", [root])
    monkeypatch.setattr(deps.plat, "IS_WINDOWS", True)
    assert deps.npm_bin_dir() == tmp_path / "npm"
    assert deps.npm_bin("lean-ctx") == tmp_path / "npm" / "lean-ctx.cmd"


def test_a_failed_npm_root_is_not_memoised(monkeypatch):
    calls: list = []
    monkeypatch.setattr(deps, "_NPM_ROOT_G", [])
    monkeypatch.setattr(deps.plat, "run", lambda argv, **k: calls.append(argv) or subprocess.CompletedProcess(argv, 127, "", ""))
    assert deps.npm_root_g() is None and deps.npm_root_g() is None and len(calls) == 2


def test_link_bins_takes_the_source_from_the_npm_prefix(prefix):
    home, pre = prefix
    for n in ("lean-ctx", "pyright", "pyright-langserver"):
        _cli(pre, n)
    out = deps._link_bins(["lean-ctx", "pyright", "pyright-langserver"], ENV, False)
    assert out == " (linked lean-ctx, linked pyright, linked pyright-langserver)"
    assert os.readlink(home / ".local" / "bin" / "lean-ctx") == str(pre / "bin" / "lean-ctx")
    assert deps._link_bins(["lean-ctx"], ENV, False) == ""  # idempotent


def test_a_dangling_link_from_an_old_node_is_replaced(prefix):
    home, pre = prefix
    lb = home / ".local" / "bin"
    lb.mkdir(parents=True)
    (lb / "tdd-guard").symlink_to(home / ".local" / "opt" / "node-v24.0.0-linux-x64" / "bin" / "tdd-guard")
    _cli(pre, "tdd-guard")
    assert deps._link_bins(["tdd-guard"], ENV, False) == " (linked tdd-guard)"
    assert (lb / "tdd-guard").resolve() == (pre / "bin" / "tdd-guard").resolve()


def test_a_users_own_file_is_never_replaced(prefix):
    home, pre = prefix
    lb = home / ".local" / "bin"
    lb.mkdir(parents=True)
    (lb / "mmx").write_text("#!/bin/sh\n", encoding="utf-8")
    _cli(pre, "mmx")
    assert deps._link_bins(["mmx"], ENV, False) == "" and not (lb / "mmx").is_symlink()


def test_every_npm_cli_dep_is_in_the_linked_set():
    """lean-ctx, tdd-guard and mmx-cli had no link_bins: nothing put them on PATH."""
    names = {n for d in deps._load_manifest()["deps"] for n in deps._bins_for(d)}
    assert {"lean-ctx", "tdd-guard", "pyright", "pyright-langserver", "mmx"} <= names
    assert deps._bins_for({"id": "semgrep", "which": "semgrep", "install": ["uv", "tool", "install", "semgrep"]}) == []


def test_present_in_the_npm_prefix_is_not_reinstalled_and_gets_linked(prefix, monkeypatch):
    _, pre = prefix
    _cli(pre, "tdd-guard")
    calls: list = []
    monkeypatch.setattr(deps, "_run_install", lambda argv: calls.append(argv))
    monkeypatch.setattr(deps, "_load_manifest", lambda: {"deps": [
        {"id": "tdd-guard", "which": "tdd-guard", "install": ["npm", "install", "-g", "tdd-guard@1.7.0"]}]})
    assert deps.install_deps(ENV) == [("tdd-guard", "PRESENT (linked tdd-guard)")]
    assert calls == []
    assert deps.npm_installed_bins(deps._load_manifest()) == ["tdd-guard"]
