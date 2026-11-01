"""EGM Step 6: goldfish reviewers get a lean SubagentStart block and pass the read gates."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import agent_kinds  # noqa: E402


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, HOOKS / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_membership():
    assert agent_kinds.is_goldfish("egm:egm-zoom-out") and agent_kinds.is_goldfish("EGM:EGM-STYLE")
    assert not agent_kinds.is_goldfish("egm:egm-synthesizer")
    assert agent_kinds.is_egm_lean("egm:egm-synthesizer")
    assert not agent_kinds.is_egm_lean("egm:egm-bootstrap-orchestrator")
    for junk in (None, 3, "", "general-purpose", ["egm:egm-style"]):
        assert not agent_kinds.is_goldfish(junk) and not agent_kinds.is_egm_lean(junk)


@pytest.mark.parametrize("agent_type", ["egm:egm-zoom-out", "egm:egm-synthesizer"])
def test_lean_subagent_block(agent_type):
    sc = _load("sc_kinds", "subagent-context.py")
    text = sc.build({"agent_id": "a", "agent_type": agent_type, "cwd": "/nonexistent"})
    assert "DELIVERY" in text and sc._UNTRUSTED in text
    assert "MCP PROTOCOL" not in text and "Surface skills" not in text and "FILE ACCESS" not in text


def test_bootstrap_keeps_the_full_block():
    sc = _load("sc_kinds2", "subagent-context.py")
    text = sc.build({"agent_id": "a", "agent_type": "egm:egm-bootstrap-orchestrator", "cwd": "/nonexistent"})
    assert "MCP PROTOCOL" in text and text.endswith(sc._SKILLS)


def _fire(mod, fn, payload, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    fn()
    out = buf.getvalue().strip()
    return json.loads(out) if out else {}


def test_goldfish_passes_both_read_gates(tmp_path, monkeypatch):
    jcm = _load("jcm_kinds", "jcodemunch-enforce.py")
    monkeypatch.setattr(jcm, "STATE_DIR", tmp_path / "s")
    monkeypatch.setattr(jcm, "_is_exempt", lambda t, c: False)
    monkeypatch.setattr(jcm, "_check_index_exists", lambda t: True)
    base = {"session_id": "s", "agent_id": "g", "tool_name": "Read",
            "tool_input": {"file_path": str(tmp_path / "src" / "a.py")}}
    assert _fire(jcm, jcm.pre_tool_use, base, monkeypatch).get("permissionDecision") == "deny"  # control
    gold = {**base, "agent_id": "g2", "agent_type": "egm:egm-design"}
    assert _fire(jcm, jcm.pre_tool_use, gold, monkeypatch) == {}

    jde = _load("jde_kinds", "jdocmunch-enforce.py")
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    idx = tmp_path / "idx"
    idx.mkdir()
    (idx / "repo.json").write_text("{}", encoding="utf-8")
    (repo / "docs" / "g.md").write_text("x" * 5000, encoding="utf-8")
    monkeypatch.setattr(jde, "INDEX_DIR", idx)
    monkeypatch.setattr(jde, "STATE_DIR", tmp_path / "s2")
    monkeypatch.setattr(jde, "_repo_root", lambda payload=None: repo)
    doc = {"session_id": "s", "agent_id": "g3", "tool_name": "Read",
           "tool_input": {"file_path": str(repo / "docs" / "g.md")}}
    assert _fire(jde, jde.handle_pre_tool_use, doc, monkeypatch).get("permissionDecision") == "deny"
    assert _fire(jde, jde.handle_pre_tool_use, {**doc, "agent_id": "g4", "agent_type": "egm:egm-synthesizer"},
                 monkeypatch) == {}
