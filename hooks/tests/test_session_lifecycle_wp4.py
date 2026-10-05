"""WP4 (audit 2026-10-05): session-lifecycle.py.

B2-10  the breadcrumb is keyed by git root; no global fallback leaks another repo's
       context into a session.
B2-09  PreCompact prints nothing (its output never reaches the model); the handoff
       carries only fields some writer fills; the breadcrumb never claims gates were
       "resolved" when the last Stop forced past them.
B2-11  subagent-stop writes nothing. B2-12 post-compact prints {}.
NEW-03 on resume / compact the start mode adds nothing the transcript already holds.
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


@pytest.fixture
def sl(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("sl_wp4", _HOOKS / "session-lifecycle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    state = tmp_path / "state"
    monkeypatch.setattr(mod, "STATE_DIR", state)
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    return mod, state


def _run(mod, mode: str, payload: dict, monkeypatch) -> dict:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "argv", ["session-lifecycle.py", mode])
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.run(mode)
    out = buf.getvalue().strip()
    return json.loads(out) if out else {}


def _ctx(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("additionalContext", "")


def _repo(tmp_path: Path, name: str) -> Path:
    r = tmp_path / name
    (r / ".git").mkdir(parents=True)
    (r / "src").mkdir()
    return r


def test_breadcrumb_never_leaks_to_another_repo(sl, tmp_path, monkeypatch):
    mod, state = sl
    a, b = _repo(tmp_path, "repo-a"), _repo(tmp_path, "repo-b")
    _run(mod, "stop", {"session_id": "s1", "cwd": str(a)}, monkeypatch)
    assert not (state / "session-breadcrumb.json").exists()
    assert _run(mod, "session-start", {"session_id": "s2", "cwd": str(b), "source": "startup"},
                monkeypatch) == {}
    # same repo from a sub-directory: keyed by git root, so it still finds it
    got = _ctx(_run(mod, "session-start", {"session_id": "s3", "cwd": str(a / "src"),
                                           "source": "startup"}, monkeypatch))
    assert "LAST SESSION CONTEXT" in got and str(a) in got


@pytest.mark.parametrize("source", ["resume", "compact"])
def test_resume_and_compact_add_no_breadcrumb(sl, tmp_path, monkeypatch, source):
    mod, _ = sl
    a = _repo(tmp_path, "repo-a")
    _run(mod, "stop", {"session_id": "s1", "cwd": str(a)}, monkeypatch)
    (a / ".continue-here.md").write_text("resume here")
    assert _run(mod, "session-start", {"session_id": "s1", "cwd": str(a), "source": source},
                monkeypatch) == {}


def test_compact_injects_the_handoff_once(sl, tmp_path, monkeypatch):
    """session-lifecycle is the single injector; the aggregator adds nothing on compact."""
    mod, state = sl
    state.mkdir(parents=True, exist_ok=True)
    (state / "s1.desloppify.json").write_text(json.dumps({"code_writes": 2}))
    _run(mod, "pre-compact", {"session_id": "s1"}, monkeypatch)
    got = _ctx(_run(mod, "session-start", {"session_id": "s1", "source": "compact"}, monkeypatch))
    assert "PRE-COMPACT SNAPSHOT" in got and "write_count: 2" in got
    spec = importlib.util.spec_from_file_location("ssa_wp4", _HOOKS / "session-start-aggregator.py")
    agg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agg)
    monkeypatch.setattr(agg, "STATE_DIR", state)
    for source in ("compact", "resume"):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"session_id": "s1", "source": source})))
        buf = io.StringIO()
        with redirect_stdout(buf):
            agg.main()
        assert json.loads(buf.getvalue()) == {}, source


def test_forced_gates_are_reported_as_forced_never_resolved(sl, tmp_path, monkeypatch):
    mod, state = sl
    a = _repo(tmp_path, "repo-a")
    state.mkdir(parents=True, exist_ok=True)
    gate = state / "s1.completion-gate.json"
    # hcg after block → override: failed_gates kept, override_ts set
    gate.write_text(json.dumps({"turn_key": "t", "blocked_this_turn": True,
                                "failed_gates": ["Gate 4 (santa)"], "override_ts": "x"}))
    _run(mod, "stop", {"session_id": "s1", "cwd": str(a)}, monkeypatch)
    got = _ctx(_run(mod, "session-start", {"session_id": "s2", "cwd": str(a)}, monkeypatch))
    assert "Gate 4 (santa)" in got and "resolved" not in got
    # the next Stop passed → hcg cleared failed_gates → no gate line at all
    gate.write_text(json.dumps({"turn_key": "t2", "blocked_this_turn": False, "failed_gates": []}))
    _run(mod, "stop", {"session_id": "s1", "cwd": str(a)}, monkeypatch)
    got = _ctx(_run(mod, "session-start", {"session_id": "s2", "cwd": str(a)}, monkeypatch))
    assert "Gate" not in got


def test_pre_compact_writes_live_fields_and_prints_nothing(sl, monkeypatch):
    mod, state = sl
    state.mkdir(parents=True, exist_ok=True)
    (state / "s1.desloppify.json").write_text(json.dumps({"code_writes": 4}))
    (state / "s1.completion-gate.json").write_text(json.dumps({"failed_gates": ["Gate 5 (dead code)"]}))
    assert _run(mod, "pre-compact", {"session_id": "s1"}, monkeypatch) == {}
    handoff = json.loads((state / "s1.precompact-handoff.json").read_text(encoding="utf-8"))
    assert handoff["write_count"] == 4
    assert handoff["failed_gates"] == ["Gate 5 (dead code)"]
    dead = {"deny_count", "doc_gate_cleared", "santa_gate_cleared", "last_skill_reminders", "gate_states"}
    assert not dead & set(handoff)


@pytest.mark.parametrize("mode", ["subagent-stop", "post-compact"])
def test_dead_modes_print_empty_and_write_nothing(sl, monkeypatch, mode):
    mod, state = sl
    assert _run(mod, mode, {"session_id": "s1", "agent_id": "a"}, monkeypatch) == {}
    assert not state.exists() or not any(state.iterdir())
