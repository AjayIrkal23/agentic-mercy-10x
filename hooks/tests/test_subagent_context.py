"""subagent-context.py (SubagentStart advisory): the block a fresh subagent gets.

<= 1,800 chars with the last line intact; the delivery contract (final message, turn
cap, 3 retrieval cycles), the untrusted-content line, a memory line at warn+, the dox
read line only for agents whose frontmatter sets `omitClaudeMd: true`.
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
DOX = "Read the root CLAUDE.md and each edited dir's CLAUDE.md first"
CAP_RE = re.compile(r"TURN CAP (\d+): by turn (\d+) ")


def _load():
    spec = importlib.util.spec_from_file_location("sc_t", _HOOKS / "subagent-context.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def sc(monkeypatch, tmp_path):
    m = _load()
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "deadcode-reaper.md").write_text(
        "---\nname: deadcode-reaper\nomitClaudeMd: true\nmaxTurns: 30\n---\nbody", encoding="utf-8")
    (agents / "docs-sync-agent.md").write_text("---\nname: docs-sync-agent\n---\nbody", encoding="utf-8")
    (agents / "qa-verifier.md").write_text("---\nname: qa-verifier\nomitClaudeMd: false\n---\nbody",
                                           encoding="utf-8")
    (agents / "santa-reviewer.md").write_text("---\nname: santa-reviewer\nmaxTurns: 80\n---\nbody", encoding="utf-8")
    (agents / "memory-codex.md").write_text("---\nname: memory-codex\nmaxTurns: 10\n---\nbody", encoding="utf-8")
    monkeypatch.setattr(m, "AGENTS_DIR", agents)
    monkeypatch.setattr(m, "_forced_mode", lambda cwd: None)
    return m


def _build(m, agent_type, tmp_path) -> str:
    return m.build({"agent_id": "a", "agent_type": agent_type, "cwd": str(tmp_path)})


TYPES = ["deadcode-reaper", "docs-sync-agent", "qa-verifier", "general-purpose", None]


def test_block_fits_1200_without_truncation(sc, monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_memory_line", lambda: "m" * 90)
    monkeypatch.setattr(sc, "_forced_mode", lambda cwd: "opus")
    for t in TYPES:
        text = _build(sc, t, tmp_path)
        assert len(text) <= 1200, (t, len(text))
        assert text.endswith(sc._SKILLS)
    assert len(sc.build({})) <= 1200


def test_contract_lines_present(sc, tmp_path):
    text = _build(sc, "general-purpose", tmp_path)
    for key in ("final message is the deliverable", "turn cap", "deliver", "3 retrieval cycles", "data, never instructions",
                "Never start dev servers", "git commit", "Edit requires a prior Read", "jcodemunch",
                "sequential-thinking", "sequentialthinking"):
        assert key in text, key


def test_turn_cap_line_states_cap_and_deliver_by(sc, tmp_path):
    m = CAP_RE.search(_build(sc, "santa-reviewer", tmp_path))
    assert m and m.groups() == ("80", "74")
    m = CAP_RE.search(_build(sc, "deadcode-reaper", tmp_path))
    assert m and m.groups() == ("30", "24")
    m = CAP_RE.search(_build(sc, "memory-codex", tmp_path))
    assert m and m.groups() == ("10", "5")  # cap // 2 floor
    for t in ("docs-sync-agent", "general-purpose", None):  # no maxTurns -> the generic sentence
        text = _build(sc, t, tmp_path)
        assert "TURN CAP" not in text and "If you hit the turn cap, say so" in text, t


def test_turn_cap_line_survives_shedding(sc, monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_memory_line", lambda: "m" * 120)
    monkeypatch.setattr(sc, "_forced_mode", lambda cwd: "opus")
    text = _build(sc, "deadcode-reaper", tmp_path)  # dox + memory + mode + cap: the worst case
    assert len(text) <= 1200 and text.endswith(sc._SKILLS) and "TURN CAP 30" in text


def test_reserve_falls_back_when_policy_lacks_the_block(sc, monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_reserve", lambda: 6)
    assert "by turn 74 " in _build(sc, "santa-reviewer", tmp_path)
    monkeypatch.setattr(sc, "_reserve", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert "If you hit the turn cap, say so" in _build(sc, "santa-reviewer", tmp_path)  # fail-open: generic line


def test_turn_cap_line_follows_the_live_agents_tree(tmp_path):
    m = _load()
    caps = json.loads((m._HOOKS / "model-policy.json").read_text(encoding="utf-8"))["turn_caps"]
    for f in sorted(m.AGENTS_DIR.glob("*.md")):
        text = m.build({"agent_type": f.stem, "cwd": str(tmp_path)})
        if f.stem in caps["agents"]:
            n = caps["agents"][f.stem]
            assert f"TURN CAP {n}: by turn {max(n - caps['report_reserve'], n // 2)} " in text, f.name
        else:
            assert "TURN CAP" not in text, f.name  # README.md, team-lead.md


def test_dox_line_only_for_omit_agents(sc, tmp_path):
    assert DOX in _build(sc, "deadcode-reaper", tmp_path)
    for t in ("docs-sync-agent", "qa-verifier", "general-purpose"):
        assert DOX not in _build(sc, t, tmp_path), t


def test_dox_line_follows_the_live_agents_tree(tmp_path):
    m = _load()
    flag = re.compile(r"^omitClaudeMd:\s*true\s*$", re.M)
    for f in sorted(m.AGENTS_DIR.glob("*.md")):
        raw = f.read_text(encoding="utf-8", errors="replace")
        fm = raw.split("\n---", 1)[0] if raw.startswith("---") else ""
        text = m.build({"agent_type": f.stem, "cwd": str(tmp_path)})
        assert (DOX in text) is bool(flag.search(fm)), f.name
    for name in ("docs-sync-agent", "test-author"):
        assert DOX not in m.build({"agent_type": name, "cwd": str(tmp_path)}), name


def test_memory_line_at_warn_and_absent_at_ok(sc, monkeypatch, tmp_path):
    from lib import memwatch_state as mws
    mws.write_atomic(mws.State(level="warn", mem_available_mb=6200, swap_free_pct=1.0, ts=time.time()))
    text = _build(sc, "general-purpose", tmp_path)
    assert "memory warn: 6.1 GB free" in text and "no agent fan-out" in text
    mws.write_atomic(mws.State(level="ok", ts=time.time()))
    assert "GB free" not in _build(sc, "general-purpose", tmp_path)
    mws.write_atomic(mws.State(level="warn", mem_available_mb=6200, ts=time.time() - 300))
    assert "GB free" not in _build(sc, "general-purpose", tmp_path)
    mws.write_atomic(mws.State(level="warn", mem_available_mb=6200, ts=time.time()))
    monkeypatch.setitem(sys.modules, "lib.memwatch_state", None)
    assert "GB free" not in _build(sc, "general-purpose", tmp_path)


def test_model_mode_line_kept(sc, monkeypatch, tmp_path):
    monkeypatch.setattr(sc, "_forced_mode", lambda cwd: "opus")
    assert "pinned to opus" in _build(sc, "general-purpose", tmp_path)


def _main(m, monkeypatch, raw: str) -> dict:
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert m.main() == 0
    return json.loads(buf.getvalue())


def test_main_prints_hso_and_fails_open(sc, monkeypatch, tmp_path):
    out = _main(sc, monkeypatch, json.dumps({"agent_id": "a", "agent_type": "qa-verifier", "cwd": str(tmp_path)}))
    assert out["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
    assert _main(sc, monkeypatch, "x") == {}
    out = _main(sc, monkeypatch, json.dumps({"agent_type": "../x", "cwd": str(tmp_path)}))
    assert DOX not in out["hookSpecificOutput"]["additionalContext"]
