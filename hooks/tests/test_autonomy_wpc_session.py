"""WP-C (autonomy 2026-10-05) item 4: session-start notices.

(a) the mercy mod is switched off by Claude Code's remote rollout flag -> one line;
(b) the daily self-heal left a summary (state/selfheal-daily.json, reported:false) -> one line,
    then reported:true so it is said once.
Runs the aggregator in-process with its subprocess jobs stubbed out; HOME and the state dir
are temp dirs, so nothing touches the live ~/.claude.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
MOD_OFF = ("mercy mod is off this session (Claude Code's remote rollout switch); every gate still "
           "runs in Python; the UI deck returns when the switch does")


@pytest.fixture
def agg(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("ssa_wpc", _HOOKS / "session-start-aggregator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k in ("MERCY_MOD_SESSION", "MERCY_MOD_LOADED", "CLAUDE_HOOK_DOCTOR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "home" / ".claude"))
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "dot")
    monkeypatch.setattr(mod, "INDEX_LIFECYCLE", tmp_path / "none.py")
    monkeypatch.setattr(mod, "TDD_INIT_GUARD", tmp_path / "none.py")
    return mod


def _home(tmp_path, flag=None, mods=("mercy",)) -> None:
    home = tmp_path / "home"
    (home / ".claude" / "installer").mkdir(parents=True, exist_ok=True)
    feats = {} if flag is None else {"cachedGrowthBookFeatures": {"tengu_plugin_hooks_modules": flag,
                                                                   "other_secret_flag": "do-not-print"}}
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {}, **feats}), encoding="utf-8")
    (home / ".claude" / "installer" / "manifest.json").write_text(
        json.dumps({"mods": {"enabled": list(mods)}}), encoding="utf-8")


def _run(mod, monkeypatch, source="startup") -> str:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"source": source, "cwd": "/tmp"})))
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    return json.loads(buf.getvalue()).get("additionalContext", "")


# --------------------------------------------------------------------------- (a) mod off
def test_mod_off_line_when_enabled_session_lacks_the_mod_and_flag_is_false(agg, monkeypatch, tmp_path):
    _home(tmp_path, flag=False)
    ctx = _run(agg, monkeypatch)
    assert MOD_OFF in ctx
    assert "other_secret_flag" not in ctx and "do-not-print" not in ctx


@pytest.mark.parametrize("flag,mods,session", [
    (True, ("mercy",), ""), (None, ("mercy",), ""), (False, (), ""), (False, ("mercy",), "sess-1"),
])
def test_mod_off_line_silent_otherwise(agg, monkeypatch, tmp_path, flag, mods, session):
    _home(tmp_path, flag=flag, mods=mods)
    if session:
        monkeypatch.setenv("MERCY_MOD_SESSION", session)
    assert MOD_OFF not in _run(agg, monkeypatch)


def test_mod_loaded_marker_silences_a_stale_false_flag(agg, monkeypatch, tmp_path):
    """SANTA-autonomy: with `bridge: off` the mod claims no links (no MERCY_MOD_SESSION), and a
    cached flag lagging at false must not print "mod off" while the mod runs."""
    _home(tmp_path, flag=False)
    monkeypatch.setenv("MERCY_MOD_LOADED", "1")
    assert MOD_OFF not in _run(agg, monkeypatch)


def test_mod_off_line_only_on_startup_and_clear(agg, monkeypatch, tmp_path):
    _home(tmp_path, flag=False)
    assert _run(agg, monkeypatch, source="resume") == ""
    assert MOD_OFF in _run(agg, monkeypatch, source="clear")


def test_mod_off_line_fails_open_on_unreadable_files(agg, monkeypatch, tmp_path):
    (tmp_path / "home" / ".claude" / "installer").mkdir(parents=True)
    (tmp_path / "home" / ".claude.json").write_text("{not json", encoding="utf-8")
    assert MOD_OFF not in _run(agg, monkeypatch)


# --------------------------------------------------------------------------- (b) self-heal
def _heal(tmp_path, **kw) -> Path:
    p = tmp_path / "state" / "selfheal-daily.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"at": "2026-10-05T00:00:00Z", "changed": [], "errors": [],
                             "reported": False, **kw}), encoding="utf-8")
    return p


def _reported(p: Path) -> bool:
    return json.loads(p.read_text(encoding="utf-8"))["reported"]


def test_selfheal_line_injected_once_then_marked_reported(agg, monkeypatch, tmp_path):
    p = _heal(tmp_path, changed=["re-pinned context7 to 2.1.0", "installed ffmpeg"],
              errors=["github MCP: token missing"])
    ctx = _run(agg, monkeypatch)
    line = next(ln for ln in ctx.splitlines() if "re-pinned context7" in ln)
    assert "installed ffmpeg" in line and "token missing" in line and len(line) <= 400
    assert _reported(p) is True
    assert "re-pinned context7" not in _run(agg, monkeypatch)  # said once


def test_selfheal_with_nothing_to_say_is_only_marked_reported(agg, monkeypatch, tmp_path):
    p = _heal(tmp_path)
    assert "self-heal" not in _run(agg, monkeypatch)
    assert _reported(p) is True


def test_selfheal_resume_doctor_missing_and_corrupt_never_break(agg, monkeypatch, tmp_path):
    assert "self-heal" not in _run(agg, monkeypatch)  # missing
    p = _heal(tmp_path, changed=["x"])
    assert _run(agg, monkeypatch, source="resume") == ""
    assert _reported(p) is False  # resume never consumes it
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    assert "self-heal" not in _run(agg, monkeypatch)       # a dry-fire never consumes it
    assert _reported(p) is False
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR")
    p.write_text("{not json", encoding="utf-8")
    assert "self-heal" not in _run(agg, monkeypatch)
