"""SANTA1C-03: an MCP entry cmd.exe cannot carry is skipped BEFORE `claude mcp remove`, never lost.

`claude` can be only an npm `.cmd` shim (npm-installed Claude Code). Its argv then goes through cmd.exe, which
cannot deliver `%`, `!` or an escaped `"` literally: the old `replace_entry` removed the server first and
both adds were refused, leaving it unregistered (and any env the user added by hand gone with it).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "installer", ROOT / "hooks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
from lib import platform as plat  # noqa: E402
import mcp_restore  # noqa: E402

OLD = {"type": "stdio", "command": "cmd", "args": ["/c", "npx", "-y", "pkg@1.0.0"], "env": {"API_KEY": "plain"}}
NEW = {**OLD, "args": ["/c", "npx", "-y", "pkg@1.0.1"]}
WARN = "WARN(cannot pass cmd.exe; left as is)"


@pytest.fixture()
def claude(monkeypatch):
    """Windows with `claude` = a `.cmd` shim only (a list argv cannot start; a shell line runs, rc 0)."""
    calls: list = []

    def fake_run(args, **kw):
        if isinstance(args, list):
            raise FileNotFoundError(2, "The system cannot find the file specified")
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    def setup(exe: bool = False):
        # forward slashes: on POSIX `D:\npm\claude.cmd` has dirname '' (= the cwd), and winutil.which
        # drops a cwd hit, so the Ubuntu legs saw no claude at all
        paths = {"claude": "D:/npm/claude.cmd"}
        if exe:
            paths = {"claude": "D:/bin/claude.exe", "claude.exe": "D:/bin/claude.exe"}

        def run_exe(args, **kw):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        monkeypatch.setattr(plat, "IS_WINDOWS", True)
        monkeypatch.setattr(plat.shutil, "which", lambda n, *a, **k: paths.get(n))
        monkeypatch.setattr(plat.subprocess, "run", run_exe if exe else fake_run)
        return calls
    return setup


@pytest.mark.parametrize("value", ["abc!def", "50%off", 'a"b'])  # json.dumps escapes a newline: that passes
def test_shim_with_an_unpassable_new_entry_is_left_alone(claude, value):
    calls = claude()
    status = mcp_restore.replace_entry("srv", {**NEW, "env": {"API_KEY": value}}, OLD, "PINNED x")
    assert status == WARN
    assert calls == []  # not even the remove ran


def test_shim_with_an_unpassable_old_entry_is_left_alone(claude):
    """The restore could not be carried either, so the swap must not start."""
    calls = claude()
    old = {**OLD, "env": {"API_KEY": "abc!def"}}
    assert mcp_restore.replace_entry("srv", NEW, old, "PINNED x") == WARN
    assert calls == []


def test_shim_with_plain_json_still_swaps(claude):
    calls = claude()
    assert mcp_restore.replace_entry("srv", NEW, OLD, "PINNED x") == "PINNED x"
    assert [c.split()[2] for c in calls] == ["remove", "add-json"]


def test_a_real_exe_carries_any_json(claude):
    calls = claude(exe=True)
    new = {**NEW, "env": {"API_KEY": 'a!b%c"d"'}}
    assert mcp_restore.replace_entry("srv", new, OLD, "PINNED x") == "PINNED x"
    assert len(calls) == 2 and all(isinstance(c, list) for c in calls)


def test_posix_never_refuses(monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", False)
    assert plat.passes_cmd_exe(["claude", "mcp", "add-json", "x", '{"a":"b!%"}'])


def test_deps_pin_reconcile_reports_the_skip_not_a_failure(claude, monkeypatch, tmp_path):
    """reconcile_mcp_pins surfaces the WARN row as is (no `PINNED`, so no npx warm-up either)."""
    import deps
    calls = claude()
    live = {**OLD, "env": {"API_KEY": "abc!def"}, "args": ["/c", "npx", "-y", "pkg@1.0.0"]}
    monkeypatch.setattr(deps, "user_config_file", lambda: _write_cfg(tmp_path, live))
    import doctor_mcp
    monkeypatch.setattr(doctor_mcp, "pin_drift", lambda manifest, live_: [("srv", "pkg@1.0.0", "pkg@1.0.1")])
    monkeypatch.setenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", "1")
    assert deps.reconcile_mcp_pins() == [("srv", WARN)]
    assert calls == []


def _write_cfg(tmp_path, entry):
    import json
    f = tmp_path / ".claude.json"
    f.write_text(json.dumps({"mcpServers": {"srv": entry}}), encoding="utf-8")
    return f
