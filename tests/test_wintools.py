"""ensure_wintools: git -> node -> claude -> uv -> gh into a per-user tools dir, no admin (A5-02/05/08).

Windows branch rehearsed on any OS: ``plat.IS_WINDOWS`` patched, downloads / processes / the
registry / ``which`` injected (``winfakes.World``). The profile has a space and non-ASCII in its path.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import wintools  # noqa: E402
from lib import platform as plat  # noqa: E402
from winfakes import ENV, World, short_limit  # noqa: E402, F401  (autouse: A7v2-02)

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
NAMES = ["git", "node", "claude", "uv", "gh"]
GIT_VAR = "CLAUDE_CODE_GIT_BASH_PATH"


@pytest.fixture
def w(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    return World(tmp_path, M)


def _path_value(w) -> list[str]:
    return w.registry.values[(ENV, "Path")][0].split(";")


def test_order_is_git_node_claude_uv_gh_and_a_fresh_box_installs_all(w):
    rows = w.ensure()
    assert [n for n, _ in rows] == NAMES
    assert all(s.startswith("INSTALLED") for _, s in rows), rows


def test_layout_under_the_tools_dir(w):
    w.ensure()
    t = w.tools
    for rel in ("node/node.exe", "node/npm.cmd", "gh/bin/gh.exe", "bin/uv.exe", "git/bin/bash.exe",
                "git/.agentic-mercy-complete"):
        assert (t / rel).is_file(), rel
    assert (w.home / ".local" / "bin" / "claude.exe").is_file()
    assert not (t / "node" / "node-vV").exists()  # wrapper dir stripped
    assert not [p for p in (t / "cache").glob("*") if p.is_file()]  # downloads removed


def test_path_gets_the_tool_dirs_in_the_registry_and_this_process(w):
    w.ensure()
    t = w.tools
    want = {str(t / "bin"), str(t / "node"), str(t / "npm-global"), str(t / "git" / "cmd"),
            str(t / "gh" / "bin"), str(w.home / ".local" / "bin")}
    assert set(_path_value(w)) == want
    assert w.registry.values[(ENV, "Path")][1] == "REG_EXPAND_SZ"
    assert want <= set(w.env["PATH"].split(os.pathsep))
    assert [c[0] for c in w.registry.calls if c[0] != "get"][-2:] == ["set", "broadcast"]


def test_git_runs_the_sfx_silently_and_sets_the_git_bash_variable(w):
    w.ensure()
    sfx = next(c for c in w.run.calls if "-y" in c)
    assert sfx[0].endswith("PortableGit-2.56.0-64-bit.7z.exe") and sfx[1:] == ["-y", f"-o{w.tools / 'git'}"]
    assert w.registry.values[(ENV, GIT_VAR)] == (str(w.tools / "git" / "bin" / "bash.exe"), "REG_SZ")
    assert w.env[GIT_VAR] == str(w.tools / "git" / "bin" / "bash.exe")


def test_node_sets_the_npm_prefix_inside_the_tools_dir(w):
    w.ensure()
    call = next(c for c in w.run.calls if c[1:4] == ["config", "set", "prefix"])
    assert call[0].endswith("npm.cmd") and call[4] == str(w.tools / "npm-global")
    assert (w.tools / "npm-global").is_dir()


def test_claude_is_the_pinned_exe_then_its_own_installer_at_the_pinned_version(w):
    w.ensure()
    url = next(u for u in w.urls if u.endswith("claude.exe"))
    assert url == "https://downloads.claude.ai/claude-code-releases/2.1.288/win32-x64/claude.exe"
    call = next(c for c in w.run.calls if c[1:2] == ["install"])
    assert call[2] == "2.1.288" and "cache" in call[0]
    assert M["user_space"]["windows"]["claude"]["version"] == M["mods"]["claude_version"]


def test_ci_and_dry_run_only_plan(w):
    for kw in ({"ci": True}, {"dry_run": True}):
        rows = w.ensure(**kw)
        assert [n for n, _ in rows] == NAMES
        assert all(s.startswith("WOULD-INSTALL(user-space, no admin)") for _, s in rows), rows
    assert not w.tools.exists() and w.urls == [] and w.registry.sets() == []
    assert not [c for c in w.run.calls if c[1:2] == ["install"] or "-y" in c]


def test_usable_tools_on_the_path_are_present_and_nothing_is_touched(w, tmp_path):
    g = tmp_path / "Git"
    for rel in ("cmd/git.exe", "bin/bash.exe"):
        (g / rel).parent.mkdir(parents=True, exist_ok=True)
        (g / rel).write_bytes(b"x")
    w.found = {"git": str(g / "cmd" / "git.exe"), "node": "/n/node.exe", "npm": "/n/npm.cmd",
               "claude": "/c/claude.exe", "uv": "/u/uv.exe", "gh": "/g/gh.exe"}
    w.runs(out={"node": "v22.9.0", "claude": "2.1.289 (Claude Code)"})
    rows = dict(w.ensure())
    assert set(rows.values()) == {"PRESENT"}, rows
    assert w.urls == [] and w.registry.sets() == [] and not w.tools.exists()


def test_a_rerun_after_an_install_is_all_present_and_writes_nothing_more(w):
    w.ensure()
    sets, urls = len(w.registry.sets()), len(w.urls)
    rows = dict(w.ensure())
    assert set(rows.values()) == {"PRESENT"}, rows
    assert len(w.registry.sets()) == sets and len(w.urls) == urls


def test_git_without_bash_is_not_present_and_only_the_variable_is_set(w, tmp_path):
    g = tmp_path / "MinGit" / "cmd" / "git.exe"
    g.parent.mkdir(parents=True)
    g.write_bytes(b"x")
    w.found["git"] = str(g)
    assert dict(w.ensure())["git"].startswith("INSTALLED")
    assert not any(p.endswith(str(Path("git") / "cmd")) for p in _path_value(w))  # their PATH order stays theirs
    assert w.registry.values[(ENV, GIT_VAR)][0] == str(w.tools / "git" / "bin" / "bash.exe")


def test_a_half_extracted_portable_git_is_repaired_not_present(w):
    for rel in ("bin/bash.exe", "cmd/git.exe"):  # extracted, but no completion marker
        (w.tools / "git" / rel).parent.mkdir(parents=True, exist_ok=True)
        (w.tools / "git" / rel).write_bytes(b"x")
    w.env["PATH"] = str(w.tools / "git" / "cmd")
    assert dict(w.ensure())["git"].startswith("INSTALLED")
    assert (w.tools / "git" / ".agentic-mercy-complete").is_file()


@pytest.mark.parametrize("node,npm,out", [
    ("X:\\u\\AppData\\Local\\Microsoft\\WindowsApps\\node.exe", "/n/npm.cmd", "v22.9.0"),  # Store shim
    ("/n/node.exe", "/n/npm.cmd", "v16.20.0"),  # below user_space.node.min
    ("/n/node.exe", None, "v22.9.0"),  # no npm beside it
])
def test_node_that_is_a_store_shim_too_old_or_without_npm_is_installed(w, node, npm, out):
    w.found.update(node=node, npm=npm)
    w.runs(out={"node": out})
    assert dict(w.ensure())["node"].startswith("INSTALLED")
    assert (w.tools / "node" / "node.exe").is_file()


@pytest.mark.parametrize("ver,present", [("2.0.9", False), ("2.1.285", True), ("2.2.0", True)])
def test_claude_is_reused_from_the_pinned_minor_up(w, ver, present):
    w.found["claude"] = "/c/claude.exe"
    w.runs(out={"claude": f"{ver} (Claude Code)"})
    assert dict(w.ensure())["claude"].startswith("PRESENT" if present else "INSTALLED")


def test_claude_whose_installer_leaves_nothing_is_a_warn(w):
    w.run.effect = None
    assert dict(w.ensure())["claude"].startswith("WARN")


def test_a_bad_hash_is_refused_and_nothing_is_extracted(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    bad = World(tmp_path, M, real_hashes=True)
    rows = dict(bad.ensure())
    assert all(s == "WARN(checksum mismatch — refused)" for s in rows.values()), rows
    assert not (bad.tools / "node").exists() and not (bad.tools / "git").exists()
    assert not (bad.tools / "bin" / "uv.exe").exists() and not (bad.tools / "gh").exists()


def test_a_network_error_is_a_warn_row_and_later_tools_still_run(w):
    def boom(url, dest, **_k):
        raise ConnectionError("blocked")
    rows = dict(w.ensure(download_fn=boom))
    assert list(rows) == NAMES and all(s.startswith("WARN(ConnectionError") for s in rows.values())


def test_arm64_picks_the_arm_assets_and_their_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    a = World(tmp_path, M, arch="ARM64")
    a.ensure()
    win = a.manifest["user_space"]["windows"]
    assert any("arm64" in u for u in a.urls if "node" in u) and any("aarch64" in u for u in a.urls)
    assert win["node"]["sha256"]["arm64"] in a.shas and win["uv"]["sha256"]["arm64"] in a.shas


def test_skip_switch_and_non_windows_env_do_nothing(w):
    assert w.ensure(environ={**w.env, "AGENTIC_MERCY_SKIP_BASE_TOOLS": "1"}) == []
    assert wintools.ensure_wintools(SimpleNamespace(os_name="posix"), w.manifest, ci=False, dry_run=False) == []
    assert w.urls == []
