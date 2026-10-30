"""F1 doctor row `cli-on-path`: every command Claude Code starts by name (stdio MCP servers, the npm CLIs
the installer links, pyright-langserver for the pyright-lsp plugin) resolves on the shell's PATH. The
laptop install reported 0 FAIL while the lean-ctx MCP could not start (ENOENT)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "installer", ROOT / "hooks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import doctor_paths  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "posix", reason="exec bits and a bash/zsh probe")

MAN = {"mcp_servers": [{"name": "lean-ctx", "add": []}, {"name": "memory", "add": []}], "deps": []}


def _exe(d: Path, name: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("#!/bin/sh\n", encoding="utf-8")
    p.chmod(0o755)
    return p


def test_a_manifest_mcp_command_off_path_fails(tmp_path):
    ok = tmp_path / "ok"
    _exe(ok, "npx")
    live = {"lean-ctx": {"command": "lean-ctx", "args": []},
            "memory": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory@2026.8.31"]},
            "openart": {"type": "http", "url": "https://mcp.openart.ai/mcp"}}
    st, det = doctor_paths.status(doctor_paths.targets(live, MAN, []), str(ok))
    assert st == "FAIL" and "lean-ctx" in det and "memory" not in det and "openart" not in det


def test_a_server_the_manifest_does_not_declare_is_a_warn(tmp_path):
    st, det = doctor_paths.status(doctor_paths.targets({"mine": {"command": "my-mcp"}}, MAN, []), str(tmp_path))
    assert st == "WARN" and "my-mcp" in det


def test_npm_clis_are_checked_too(tmp_path):
    items = doctor_paths.targets({}, MAN, ["pyright-langserver"])
    st, det = doctor_paths.status(items, str(tmp_path))
    assert st == "FAIL" and "pyright-langserver" in det
    _exe(tmp_path, "pyright-langserver")
    assert doctor_paths.status(items, str(tmp_path))[0] == "PASS"


def test_absolute_commands_and_cmd_c_wrappers(tmp_path):
    abs_cmd = _exe(tmp_path / "abs", "jcodemunch-mcp")
    live = {"lean-ctx": {"command": "cmd", "args": ["/c", "lean-ctx"]}, "memory": {"command": str(abs_cmd)}}
    items = doctor_paths.targets(live, MAN, [])
    assert ("mcp lean-ctx", "lean-ctx", True) in items
    st, det = doctor_paths.status(items, str(tmp_path / "empty"))
    assert st == "FAIL" and "lean-ctx" in det and "jcodemunch" not in det


def test_shell_path_reads_the_marker_line():
    def run(argv, **_k):
        assert argv[0] == "/bin/zsh" and argv[1] == "-lic"
        return subprocess.CompletedProcess(argv, 0, "motd noise\n__AM_PATH__=/a:/b\n", "")
    assert doctor_paths.shell_path(run, "/bin/zsh") == "/a:/b"
    assert doctor_paths.shell_path(lambda a, **k: subprocess.CompletedProcess(a, 124, "", ""), "/bin/bash") is None
    seen: list = []
    doctor_paths.shell_path(lambda a, **k: seen.append(a) or subprocess.CompletedProcess(a, 1, "", ""), "/usr/bin/fish")
    assert seen[0][0] == "bash"  # another login shell: bash syntax, bash probe


def test_check_skips_in_ci(tmp_path):
    assert doctor_paths.check(True, MAN, tmp_path / "none.json")[0] == "SKIP"


def test_check_falls_back_to_the_process_path_and_says_so(tmp_path):
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"lean-ctx": {"command": "lean-ctx"}}}), encoding="utf-8")
    _exe(tmp_path / "bin", "lean-ctx")
    st, det = doctor_paths.check(False, MAN, cfg, run=lambda a, **k: subprocess.CompletedProcess(a, 127, "", ""),
                                 environ={"PATH": str(tmp_path / "bin"), "SHELL": "/bin/bash"}, npm_bins=[])
    assert st == "PASS" and "process" in det


def test_a_fail_routes_to_the_deps_step(monkeypatch):
    import deps  # noqa: PLC0415
    import selfheal  # noqa: PLC0415
    seen: list = []
    monkeypatch.setattr(deps, "install_deps", lambda env, **k: [("lean-ctx", "PRESENT (linked lean-ctx)"),
                                                                ("uv", "PRESENT")])
    selfheal._repair(Path("."), {"cli-on-path"}, object(), lambda *a: seen.append(a))
    assert seen == [("repair", "lean-ctx", "PRESENT (linked lean-ctx)")]
