"""settings_install.seed_machine_overlay: per-machine keys a tracked template cannot know
(OLLAMA_HOST, the RAM-sized tool memory limit and agent floors, the first-install permission mode) go into
settings.user.json (mode 600), only when absent (FI-1, FI-3, DU-17, SP-1)."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installer"))
import settings_install as SI  # noqa: E402

HOST = "http://192.0.2.5:11434"


def _seed(tmp, **kw):
    rows = []
    kw.setdefault("environ", {})
    kw.setdefault("mem_total_mb", 0)  # no RAM reading: the tool-cap row stays out of the other tests
    kw.setdefault("system", "Linux")
    out = SI.seed_machine_overlay(tmp, lambda *r: rows.append(r), **kw)
    return out, rows


def _overlay(tmp) -> dict:
    return json.loads((tmp / "settings.user.json").read_text(encoding="utf-8"))


def test_ollama_host_is_seeded_mode_600(tmp_path):
    out, rows = _seed(tmp_path, environ={"OLLAMA_HOST": HOST})
    assert out == ["OLLAMA_HOST"] and _overlay(tmp_path)["env"]["OLLAMA_HOST"] == HOST
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "settings.user.json").stat().st_mode) == 0o600
    assert any("OK(seeded OLLAMA_HOST)" in r[2] for r in rows)


def test_existing_host_kept_and_empty_env_writes_nothing(tmp_path):
    (tmp_path / "settings.user.json").write_text(json.dumps({"env": {"OLLAMA_HOST": "http://a:1"}}), encoding="utf-8")
    assert _seed(tmp_path, environ={"OLLAMA_HOST": HOST})[0] == []
    assert _overlay(tmp_path)["env"]["OLLAMA_HOST"] == "http://a:1"
    other = tmp_path / "o"
    other.mkdir()
    assert _seed(other, environ={"OLLAMA_HOST": ""})[0] == []
    assert not (other / "settings.user.json").exists()


@pytest.mark.parametrize("mem,cap,sub,wf", [(15650, "11554M", "3", "2"),   # the 16 GB laptop
                                            (16384, "12288M", "3", "2"),
                                            (30669, "26573M", "5", "4"),   # this PC
                                            (8192, "4096M", "2", "1"),
                                            (6144, "3072M", "2", "1")])
def test_machine_sizes_follow_ram(tmp_path, mem, cap, sub, wf):
    """F7 (user, 2026-10-30: "keep 12gb or 14gb on 16gb ram system"): the machine-wide tool cap is MemTotal
    minus 4 GiB, never below half: ONE cgroup (app.slice/claude-code-bash) serves every session's tool
    commands (REVERIFY R5). F6: the agent floors for launches bin/claude does not size (-p, --bare, nested,
    no user bus) scale with RAM. The template keeps its floors; the overlay sizes them."""
    assert _seed(tmp_path, mem_total_mb=mem)[0] == ["CLAUDE_CODE_TOOL_MEMORY_LIMIT",
                                                   "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS",
                                                   "CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS"]
    env = _overlay(tmp_path)["env"]
    assert (env["CLAUDE_CODE_TOOL_MEMORY_LIMIT"], env["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"],
            env["CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS"]) == (cap, sub, wf)
    from lib import oomguard_config as ogc  # noqa: PLC0415  (settings_install put hooks/ on sys.path)
    assert cap == f"{ogc.memory_cap_mb(mem)}M"


@pytest.mark.parametrize("mem,system", [(0, "Linux"), (30669, "Windows"), (30669, "Darwin")])
def test_unknown_ram_or_another_os_seeds_nothing(tmp_path, mem, system):
    assert _seed(tmp_path, mem_total_mb=mem, system=system)[0] == []
    assert not (tmp_path / "settings.user.json").exists()


def test_a_value_already_in_the_overlay_is_kept(tmp_path):
    (tmp_path / "settings.user.json").write_text(
        json.dumps({"env": {"CLAUDE_CODE_TOOL_MEMORY_LIMIT": "12G"}}), encoding="utf-8")
    assert _seed(tmp_path, mem_total_mb=15650)[0] == ["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS",
                                                     "CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS"]
    assert _overlay(tmp_path)["env"]["CLAUDE_CODE_TOOL_MEMORY_LIMIT"] == "12G"


def test_fresh_install_gets_accept_edits(tmp_path, monkeypatch):
    out, _ = _seed(tmp_path, fresh=True)
    ov = _overlay(tmp_path)
    assert "permissions.defaultMode" in out
    assert ov["permissions"]["defaultMode"] == "acceptEdits" and ov["remoteControlAtStartup"] is False


def test_fresh_install_honours_the_env_mode(tmp_path):
    _seed(tmp_path, fresh=True, environ={"AGENTIC_MERCY_PERMISSION_MODE": "bypassPermissions"})
    ov = _overlay(tmp_path)
    assert ov["permissions"]["defaultMode"] == "bypassPermissions" and ov["remoteControlAtStartup"] is True


def test_not_fresh_or_existing_permissions_untouched(tmp_path):
    assert "permissions.defaultMode" not in _seed(tmp_path, fresh=False)[0]
    assert not (tmp_path / "settings.user.json").exists()
    (tmp_path / "settings.user.json").write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}}), encoding="utf-8")
    assert _seed(tmp_path, fresh=True)[0] == []
    assert _overlay(tmp_path) == {"permissions": {"allow": ["Bash(ls)"]}}


def test_render_carries_the_seeded_keys(tmp_path):
    import render  # noqa: PLC0415
    _seed(tmp_path, environ={"OLLAMA_HOST": HOST}, mem_total_mb=15900, fresh=True)
    out = json.loads(render.render(user_path=tmp_path / "settings.user.json"))
    assert out["env"]["OLLAMA_HOST"] == HOST and out["env"]["CLAUDE_CODE_TOOL_MEMORY_LIMIT"] == "11804M"
    assert out["env"]["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"] == "3"
    assert out["permissions"]["defaultMode"] == "acceptEdits"


@pytest.mark.parametrize("raw", ["{bad", "[1]"])
def test_unreadable_overlay_is_not_touched(tmp_path, raw):
    (tmp_path / "settings.user.json").write_text(raw, encoding="utf-8")
    out, rows = _seed(tmp_path, environ={"OLLAMA_HOST": HOST})
    assert out == [] and (tmp_path / "settings.user.json").read_text(encoding="utf-8") == raw
    assert any("WARN" in r[2] for r in rows)


def test_example_overlay_ships_and_is_tracked():
    ex = json.loads((ROOT / "settings.user.example.json").read_text(encoding="utf-8"))
    assert "OLLAMA_HOST" in ex["env"]
