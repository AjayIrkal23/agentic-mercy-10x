"""lib.gate_state: the one per-session gate state helper (PKG hooks-hygiene-mod step 3)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import gate_state as gs  # noqa: E402


def test_safe_cid_and_path(tmp_path, monkeypatch):
    assert gs.safe_cid("a/b c.d") == "a_b_c_d"
    monkeypatch.setenv("CLAUDE_HOOK_DOTSTATE_DIR", str(tmp_path))
    assert gs.state_path("s1", "completion-gate") == tmp_path / "s1.completion-gate.json"
    assert gs.state_path("s1", "suite-gate", base=tmp_path / "tel") == tmp_path / "tel" / "s1.suite-gate.json"


def test_load_defaults_and_locked_save(tmp_path):
    p = tmp_path / "s.completion-gate.json"
    assert gs.load_json(p) == {} and gs.load_json(p, default={"a": 1}) == {"a": 1}
    p.write_text("{not json", encoding="utf-8")
    assert gs.load_json(p) == {}
    assert gs.save_json(p, {"turn_key": "t", "blocked_this_turn": True}) is True
    assert json.loads(p.read_text(encoding="utf-8"))["turn_key"] == "t" and (tmp_path / "s.completion-gate.json.lock").exists()


def test_update_json_is_a_locked_rmw(tmp_path):
    p = tmp_path / "x.json"
    out = gs.update_json(p, lambda d: {**d, "n": d.get("n", 0) + 1})
    out = gs.update_json(p, lambda d: {**d, "n": d.get("n", 0) + 1})
    assert out["n"] == 2 == json.loads(p.read_text(encoding="utf-8"))["n"]


def test_empty_cid_never_touches_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_DOTSTATE_DIR", str(tmp_path))
    assert gs.state_path("", "x") is None and gs.load_state("", "x") == {}
    assert gs.save_state("", "x", {"a": 1}) is False
    assert list(tmp_path.iterdir()) == []


def test_non_dict_json_reads_as_default(tmp_path):
    p = tmp_path / "l.json"
    p.write_text("[1, 2]", encoding="utf-8")
    assert gs.load_json(p, default={"d": 1}) == {"d": 1}
