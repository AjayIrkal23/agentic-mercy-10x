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
import re
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
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "pstate"))
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


# --------------------------------------------------------------------------- caps and handoff
_SLASH = re.compile(r"(?<![\w/])/[a-z][\w-]+")


def test_breadcrumb_text_is_capped_at_1500_and_decisions_at_400(sl, tmp_path, monkeypatch):
    mod, state = sl
    a = _repo(tmp_path, "repo-a")
    (a / "CODEX.md").write_text("\n".join(f"{i}" + "d" * 899 for i in range(10)), encoding="utf-8")
    _run(mod, "stop", {"session_id": "s1", "cwd": str(a)}, monkeypatch)
    bc = json.loads(mod._breadcrumb_path(a).read_text(encoding="utf-8"))
    assert len(bc["decisions_summary"]) <= 400 and bc["decisions_summary"].endswith("…")
    got = _ctx(_run(mod, "session-start", {"session_id": "s2", "cwd": str(a), "source": "startup"},
                    monkeypatch))
    block = got[got.index("LAST SESSION CONTEXT"):]
    assert len(block) <= mod.BREADCRUMB_MAX
    # an oversized breadcrumb is cut on a line boundary, the marker on its own last line
    lines = [f"line {i} " + "z" * 90 for i in range(40)]
    clipped = mod._clip_block("\n".join(lines), mod.BREADCRUMB_MAX)
    assert len(clipped) <= mod.BREADCRUMB_MAX
    kept = clipped.splitlines()
    assert kept[-1] == "...(clipped)" and all(ln in lines for ln in kept[:-1])


def test_continue_here_is_capped_wrapped_and_quoted_as_historical(sl, tmp_path, monkeypatch):
    mod, _ = sl
    a = _repo(tmp_path, "repo-a")
    raw = "next: run /invoke impl -- finish X\n" + "\n".join("step " + "w" * 60 for _ in range(70))
    assert len(raw) > 4000
    (a / ".continue-here.md").write_text(raw, encoding="utf-8")
    got = _ctx(_run(mod, "session-start", {"session_id": "s2", "cwd": str(a), "source": "startup"},
                    monkeypatch))
    body = raw[:mod.CONTINUE_MAX].strip()
    assert "HISTORICAL REFERENCE" in got and "verify against git" in got
    assert body in got and raw[:mod.CONTINUE_MAX + 1] not in got
    assert _SLASH.search(got.replace(body, "")) is None


@pytest.mark.parametrize("content", ["", "# Next steps\n\n", "[Session context goes here]", "TODO", "<fill in>"])
def test_placeholder_only_continue_here_is_rejected(sl, tmp_path, monkeypatch, content):
    mod, _ = sl
    a = _repo(tmp_path, "repo-a")
    (a / ".continue-here.md").write_text(content, encoding="utf-8")
    got = _ctx(_run(mod, "session-start", {"session_id": "s2", "cwd": str(a), "source": "startup"},
                    monkeypatch))
    assert "RESUME PROMPT" not in got


def test_real_continue_here_is_kept(sl, tmp_path, monkeypatch):
    mod, _ = sl
    a = _repo(tmp_path, "repo-a")
    (a / ".continue-here.md").write_text("next: fix the flaky test in a.py", encoding="utf-8")
    got = _ctx(_run(mod, "session-start", {"session_id": "s2", "cwd": str(a), "source": "startup"},
                    monkeypatch))
    assert "RESUME PROMPT" in got and "fix the flaky test" in got


def _tool(name: str, **inp) -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": name, "input": inp}]}}


def test_stop_writes_the_handoff_template(sl, tmp_path, monkeypatch):
    mod, state = sl
    a = _repo(tmp_path, "repo-a")
    tr = tmp_path / "t.jsonl"
    rows = [{"type": "user", "timestamp": "2026-10-29T10:00:00+00:00",
             "message": {"role": "user", "content": "add the helper"}},
            _tool("Edit", file_path="/r/a.ts"), _tool("Bash", command="pytest -q"), _tool("Bash", command="ls")]
    tr.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    state.mkdir(parents=True, exist_ok=True)
    (state / "s1.completion-gate.json").write_text(json.dumps({"failed_gates": ["Gate 4 (santa)"]}))
    pstate = tmp_path / "pstate"
    pstate.mkdir(parents=True, exist_ok=True)
    (pstate / "s1.typecheck.json").write_text(json.dumps({"result": "block"}))
    _run(mod, "stop", {"session_id": "s1", "cwd": str(a), "transcript_path": str(tr),
                       "last_assistant_message": "Added the helper; tests pass."}, monkeypatch)
    bc = json.loads(mod._breadcrumb_path(a).read_text(encoding="utf-8"))
    assert bc["handoff"] == {
        "worked": "Added the helper; tests pass.", "evidence": ["pytest -q"],
        "did_not_work": ["gates still failing: Gate 4 (santa)", "typecheck gate blocked the last Stop"],
        "not_tried": "not recorded (hooks cannot infer intent)", "next_step": "not recorded",
        "files": ["/r/a.ts"]}
    assert "summary" in bc and "gate_outcomes" in bc and "security_outcomes" in bc
    got = _ctx(_run(mod, "session-start", {"session_id": "s2", "cwd": str(a), "source": "startup"},
                    monkeypatch))
    keys = ["worked (evidence):", "did not work:", "not tried:", "next step:", "files:"]
    pos = [got.index(k) for k in keys]
    assert pos == sorted(pos)
    assert "verified by: pytest -q" in got and "a.ts" in got


def test_handoff_with_no_transcript_still_writes_the_breadcrumb(sl, tmp_path, monkeypatch):
    mod, _ = sl
    a = _repo(tmp_path, "repo-a")
    assert _run(mod, "stop", {"session_id": "s1", "cwd": str(a)}, monkeypatch) == {}
    h = json.loads(mod._breadcrumb_path(a).read_text(encoding="utf-8"))["handoff"]
    assert h["files"] == [] and h["evidence"] == [] and h["worked"] == "not recorded"


# --------------------------------------------------------------------------- REVIEW2 fixes
def test_breadcrumb_cap_keeps_the_warning_and_semgrep_note(sl):
    """Fix 1: a long handoff block is clipped on its own; the two safety lines survive."""
    mod, _ = sl
    bc = {"timestamp": "t", "workspace": "/r", "summary": "Worked on codebase (3 code files)",
          "decisions_summary": "d" * 400,
          "handoff": {"worked": "w" * 300, "evidence": [f"pytest {i} " + "e" * 110 for i in range(5)],
                      "did_not_work": ["none recorded"], "not_tried": "x", "next_step": "y",
                      "files": [f"/r/{i}.py" for i in range(12)]},
          "gate_outcomes": {"failed_gates": ["security", "santa"]},
          "security_outcomes": {"security_files_count": 3, "semgrep_ran": False}}
    text = mod._breadcrumb_text(bc)
    assert len(text) <= mod.BREADCRUMB_MAX
    assert "WARNING:" in text and "NOTE:" in text
    assert "did not work:" in text  # one overlong line no longer ends the block


def test_stop_clears_the_stop_failure_marker(sl, tmp_path, monkeypatch):
    """Fix 3: a normal Stop removes <sid>.stop-failure.json for that session only."""
    mod, _ = sl
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    spec = importlib.util.spec_from_file_location("sfl_wp4", _HOOKS / "stop-failure-log.py")
    sfl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sfl)
    for sid in ("abc-123", "other"):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"session_id": sid, "error": "rate_limit"})))
        with redirect_stdout(io.StringIO()):
            sfl.main()
    pstate = tmp_path / "pstate"
    assert (pstate / "abc-123.stop-failure.json").is_file()
    a = _repo(tmp_path, "repo-a")
    _run(mod, "stop", {"session_id": "abc-123", "cwd": str(a)}, monkeypatch)
    assert not (pstate / "abc-123.stop-failure.json").exists()
    assert (pstate / "other.stop-failure.json").is_file()


def test_handoff_lists_failed_evidence_as_did_not_work(sl, tmp_path, monkeypatch):
    """Fix 4: a test run whose tool_result is an error is not 'verified by'."""
    mod, _ = sl
    a = _repo(tmp_path, "repo-a")
    tr = tmp_path / "t.jsonl"
    rows = [{"type": "user", "message": {"role": "user", "content": "run the tests"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "tu1", "name": "Bash",
                 "input": {"command": "python3 -m pytest tests -q"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu1", "is_error": True, "content": "1 failed"}]}}]
    tr.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    _run(mod, "stop", {"session_id": "s1", "cwd": str(a), "transcript_path": str(tr)}, monkeypatch)
    got = _ctx(_run(mod, "session-start", {"session_id": "s2", "cwd": str(a), "source": "startup"},
                    monkeypatch))
    assert "verified by: none recorded" in got
    assert "did not work: python3 -m pytest tests -q: failed" in got
