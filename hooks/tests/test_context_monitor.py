"""context-monitor.py (PostToolUse advisory): loop, scope and compaction nudge.

Replaces ECC's ecc-context-monitor.js, ecc-metrics-bridge.js, suggest-compact.js and
lib/transcript-context.js. Every output of this file is checked for a slash command
(the nudge says "let auto-compact run", never "run /compact").
"""
from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
_SLASH = re.compile(r"(?<![\w/])/[a-z][\w-]+")


@pytest.fixture
def mod(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("ctxmon_t", _HOOKS / "context-monitor.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "home" / ".claude").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "home" / ".claude"))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    monkeypatch.setattr(m, "_mod_active", lambda sid: False)
    return m


def _payload(tool, inp, sid="s1", transcript=None, agent_id=None) -> dict:
    p = {"session_id": sid, "tool_name": tool, "tool_input": inp, "hook_event_name": "PostToolUse"}
    if transcript:
        p["transcript_path"] = str(transcript)
    if agent_id:
        p["agent_id"] = agent_id
    return p


def _call(m, monkeypatch, payload) -> dict:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    buf = io.StringIO()
    with redirect_stdout(buf):
        m.main()
    return json.loads(buf.getvalue())


def _ctx(out: dict) -> str:
    ctx = (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
    assert _SLASH.search(ctx) is None, ctx
    return ctx


def _transcript(tmp_path, used_tokens, model="claude-opus-5-20260301", name="t.jsonl") -> Path:
    p = tmp_path / name
    rows = [{"type": "user", "message": {"role": "user", "content": "go"}},
            {"type": "assistant", "message": {"model": model, "content": [], "usage": {
                "input_tokens": used_tokens - 100, "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 0, "output_tokens": 5}}}]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_loop_warns_once_after_five_identical_calls_and_rearms(mod, monkeypatch):
    ls = _payload("Bash", {"command": "ls"})
    for _ in range(4):
        assert _ctx(_call(mod, monkeypatch, ls)) == ""
    ctx = _ctx(_call(mod, monkeypatch, ls))
    assert "[loop]" in ctx and "Bash" in ctx and "5" in ctx
    assert _ctx(_call(mod, monkeypatch, ls)) == ""
    assert _ctx(_call(mod, monkeypatch, _payload("Bash", {"command": "pwd"}))) == ""
    outs = [_ctx(_call(mod, monkeypatch, ls)) for _ in range(5)]
    assert outs[:4] == [""] * 4 and "[loop]" in outs[4]


def test_five_calls_with_different_input_do_not_warn(mod, monkeypatch):
    for i in range(5):
        assert _ctx(_call(mod, monkeypatch, _payload("Read", {"file_path": f"/r/{i}.py"}))) == ""


def test_scope_warns_once_at_twenty_unique_files(mod, monkeypatch):
    for i in range(19):
        assert _ctx(_call(mod, monkeypatch, _payload("Edit", {"file_path": f"/r/{i}.py"}))) == ""
    ctx = _ctx(_call(mod, monkeypatch, _payload("Edit", {"file_path": "/r/19.py"})))
    assert "[scope]" in ctx and "20" in ctx
    for i in range(20):
        assert _ctx(_call(mod, monkeypatch, _payload("Edit", {"file_path": f"/r/{i}.py"}))) == ""
    # MultiEdit edits[].file_path counts, Read does not
    for i in range(30):
        _call(mod, monkeypatch, _payload("Read", {"file_path": f"/x/{i}.py"}, sid="s2"))
    assert not json.loads((Path(mod.plat.state_dir()) / "s2.toolring.json").read_text(encoding="utf-8"))["files"]
    edits = [{"file_path": f"/m/{i}.py"} for i in range(20)]
    assert "[scope]" in _ctx(_call(mod, monkeypatch, _payload("MultiEdit", {"edits": edits}, sid="s3")))


def test_nudge_fires_at_60_percent_then_every_60k_and_never_names_a_slash_command(mod, monkeypatch, tmp_path):
    def at(tokens, i):
        tr = _transcript(tmp_path, tokens, name=f"t{i}.jsonl")
        return _ctx(_call(mod, monkeypatch, _payload("Read", {"file_path": f"/r/{i}"}, transcript=tr)))
    assert at(500_000, 0) == ""
    ctx = at(600_000, 1)
    assert "[context]" in ctx and "600k/1M" in ctx and "let auto-compact run" in ctx
    assert at(620_000, 2) == ""
    assert "[context]" in at(660_000, 3)


def test_nudge_rearms_after_a_compaction(mod, monkeypatch, tmp_path):
    """Fix 2: usage falling (a compaction ran) lowers the stored bucket, so the next climb nudges."""
    def at(tokens, i):
        tr = _transcript(tmp_path, tokens, model="claude-opus-5-5", name=f"r{i}.jsonl")
        return _ctx(_call(mod, monkeypatch, _payload("Read", {"file_path": f"/q/{i}"}, transcript=tr)))
    state = lambda: json.loads(mod._state_path("s1", None).read_text(encoding="utf-8"))
    assert "[context]" in at(600_000, 0)
    old = state()["nudge_bucket"]
    assert at(100_000, 1) == ""
    assert state()["nudge_bucket"] < old
    assert "[context]" in at(610_000, 2)


def test_nudge_is_silent_when_the_mod_owns_compaction(mod, monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "_mod_active", lambda sid: True)
    tr = _transcript(tmp_path, 700_000)
    outs = [_ctx(_call(mod, monkeypatch, _payload("Bash", {"command": "ls"}, transcript=tr))) for _ in range(5)]
    assert all("[context]" not in o for o in outs)
    assert "[loop]" in outs[4]


def test_window_resolution(mod, tmp_path):
    assert mod._window(650_000, "claude-sonnet-4-5") == 1_000_000
    assert mod._window(50_000, "claude-opus-4-1[1m]") == 1_000_000
    assert mod._window(50_000, "claude-fable-5-1") == 1_000_000
    assert mod._window(50_000, "claude-fable-5-mini") == 200_000
    assert mod._window(50_000, "claude-sonnet-4-5") == 200_000
    (tmp_path / "home" / ".claude" / "settings.json").write_text(
        json.dumps({"autoCompactWindow": 900000}), encoding="utf-8")
    assert mod._window(50_000, "x") == 1_000_000


def _bridge(tmp_path, pct, age=0.0):
    b = tmp_path / "state" / "session-bridge" / "s1.json"
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(json.dumps({"context_pct": pct, "ts": time.time() - age}), encoding="utf-8")


def test_bridge_fallback_when_the_transcript_has_no_usage(mod, monkeypatch, tmp_path):
    tr = tmp_path / "u.jsonl"
    tr.write_text(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n", encoding="utf-8")
    (tmp_path / "home" / ".claude" / "settings.json").write_text(
        json.dumps({"autoCompactWindow": 900000}), encoding="utf-8")
    _bridge(tmp_path, 65, age=500)
    assert _ctx(_call(mod, monkeypatch, _payload("Read", {"file_path": "/a"}, transcript=tr))) == ""
    _bridge(tmp_path, 65)
    ctx = _ctx(_call(mod, monkeypatch, _payload("Read", {"file_path": "/b"}, transcript=tr)))
    assert "[context]" in ctx and "650k/1M" in ctx


def test_subagent_calls_track_their_own_ring_and_skip_the_nudge(mod, monkeypatch, tmp_path):
    tr = _transcript(tmp_path, 700_000)
    outs = [_ctx(_call(mod, monkeypatch, _payload("Bash", {"command": "ls"}, transcript=tr, agent_id="a1")))
            for _ in range(5)]
    assert all("[context]" not in o for o in outs) and "[loop]" in outs[4]
    state = tmp_path / "state"
    assert not (state / "s1.toolring.json").exists()
    assert (state / "s1.a1.toolring.json").exists()


def test_doctor_and_bad_payload_print_empty_and_write_nothing(mod, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    assert _call(mod, monkeypatch, _payload("Bash", {"command": "ls"})) == {}
    state = tmp_path / "state"
    assert not state.exists() or not any(state.rglob("*.json"))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR")
    assert _call(mod, monkeypatch, "not json") == {}
    assert _call(mod, monkeypatch, {"tool_name": "Bash", "tool_input": {"command": "ls"}}) == {}


def test_output_is_at_most_two_lines(mod, monkeypatch, tmp_path):
    inp = {"file_path": "/r/new.py"}
    fp = mod._fingerprint("Edit", inp)
    seed = {"ring": [fp] * 4, "files": [f"/r/{i}.py" for i in range(19)]}
    path = mod._state_path("s1", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seed), encoding="utf-8")
    tr = _transcript(tmp_path, 700_000)
    ctx = _ctx(_call(mod, monkeypatch, _payload("Edit", inp, transcript=tr)))
    assert ctx.count("\n") <= 1
    assert ctx.startswith("[context]")
