"""WP1 router emission fixes (audit 2026-10-05 C-05, C-10, C-11, C-12, C-14, C-17, D-05).

Unit tests on prompt_router/policy.py with synthetic profiles and indexes (no
dependence on the live skills catalog), plus subprocess runs of router.py in a
tmp repo under a fake HOME.
Runnable: `python3 -m pytest hooks/tests/test_router_wp1_emit.py -q`.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from types import SimpleNamespace

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from prompt_router import policy as P   # noqa: E402
from prompt_router import router as R   # noqa: E402


def _prof(**kw):
    base = dict(text="", intents={}, surfaces=set(), weak_surfaces=set(), paths=[],
                is_arch=False, is_ui=False, arch_hit=[], ui_hit=[], size="M", risk=0,
                surface_source="")
    base.update(kw)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- C-05
META = {"debug-investigation": {"intents": ["debug"], "surfaces": ["backend"]},
        "update-docs": {"intents": ["DOCS"], "surfaces": []},
        "design-taste-frontend": {"intents": [], "surfaces": ["frontend"]}}


def test_hard_needs_score_margin_and_a_match():
    p = _prof(intents={"DEBUG": 2}, surfaces={"backend"})
    assert P.enforce_level([("debug-investigation", 7.3), ("x", 3.8)], p, META) == "hard"


def test_thin_margin_is_soft():
    p = _prof(intents={"DEBUG": 2})
    assert P.enforce_level([("debug-investigation", 6.4), ("x", 6.2)], p, META) == "soft"


def test_low_score_is_soft():
    p = _prof(intents={"DEBUG": 1})
    assert P.enforce_level([("debug-investigation", 4.6), ("x", 1.0)], p, META) == "soft"


def test_no_intent_or_strong_surface_match_is_soft():
    p = _prof(intents={"IMPLEMENT": 3}, surfaces={"frontend"}, weak_surfaces={"frontend"})
    assert P.enforce_level([("design-taste-frontend", 9.0)], p, META) == "soft"


def test_router_records_soft_push(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path))
    ctx = {"_must_read": ["update-docs"], "_enforce": "soft"}
    R._record_pushed_skills("t-c05", ctx, [{"id": "skill:update-docs:DOCS:any"}], _prof())
    rec = json.loads((tmp_path / "t-c05.pushed-skills.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["enforce"] == "soft" and rec["skills"] == ["update-docs"]


# --------------------------------------------------------------------------- D-05
def test_doctor_runs_without_override_dir_record_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_HOOK_TELEMETRY_DIR", raising=False)
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    monkeypatch.setattr(R, "_HOOKS", tmp_path)
    ctx = {"_must_read": ["update-docs"]}
    R._record_pushed_skills("t-d05", ctx, [{"id": "skill:update-docs:DOCS:any"}], _prof())
    assert not (tmp_path / ".telemetry").exists()


# --------------------------------------------------------------------------- C-11
def test_skill_tool_line_has_no_description_or_boilerplate():
    line = P.skill_line("santa-review", "MUST-READ", None)
    assert line == '- **santa-review** (MUST-READ)\n  ACTION: Skill("santa-review")'


def test_paths_scoped_skill_line_names_the_file():
    line = P.skill_line("frontend-standards-always-follow", "SHOULD-READ", "/x/SKILL.md")
    assert line == "- **frontend-standards-always-follow** (SHOULD-READ)\n  ACTION: Read /x/SKILL.md"


# --------------------------------------------------------------------------- C-14
def test_ui_line_omits_unavailable_asset_servers():
    txt = P.ui_line(lambda name: False)
    assert "Higgsfield" not in txt and "OpenArt" not in txt
    assert "design-taste-frontend" in txt


def test_ui_line_names_available_higgsfield():
    assert "Higgsfield" in P.ui_line(lambda name: name == "higgsfield")


# --------------------------------------------------------------------------- C-17
def test_routing_section_is_capped_in_order():
    items = [{"id": f"r{i}", "section": "ROUTING"} for i in range(7)] + [{"id": "s", "section": "SKILLS"}]
    kept = P.cap_section(items, "ROUTING", 4)
    assert [i["id"] for i in kept] == ["r0", "r1", "r2", "r3", "s"]


# --------------------------------------------------------------------------- C-10
def test_chat_prompt_has_no_dev_signal():
    assert not P.dev_signal(_prof(text="thanks, that makes sense. what should i have for lunch?",
                                  surfaces={"frontend", "backend"}, weak_surfaces={"frontend", "backend"},
                                  surface_source="stack"))


def test_code_prompt_has_dev_signal():
    assert P.dev_signal(_prof(intents={"DEBUG": 1}))
    assert P.dev_signal(_prof(paths=["src/a.tsx"]))
    assert P.dev_signal(_prof(surfaces={"backend"}, surface_source="prompt"))


@pytest.mark.parametrize("kw,expect", [
    (dict(intents={"TRIVIAL": 2, "SMALL": 1}, paths=["src/a.tsx"]), False),
    (dict(text="what does useprojectfilters return?", intents={"IMPLEMENT": 1}), True),
    (dict(text="what does useprojectfilters return?"), False),
    (dict(intents={"IMPLEMENT": 2, "SMALL": 1}), True),
])
def test_write_gates_only_for_write_shaped_prompts(kw, expect):
    assert P.write_gates(_prof(**kw)) is expect


def test_symbols_only_for_code_shaped_prompts():
    assert P.code_shaped(_prof(text="fix useprojectfilters in src/hooks", paths=["src/hooks"]))
    assert P.code_shaped(_prof(text="the get_user call returns null", intents={"DEBUG": 1}))
    assert P.code_shaped(_prof(text="the login call returns null", intents={"DEBUG": 1},
                               surface_source="prompt"))
    assert not P.code_shaped(_prof(text="plan offline mode for the app", intents={"PLAN": 1}))
    assert not P.code_shaped(_prof(text="rename the label", intents={"TRIVIAL": 1}, paths=["a.tsx"]))
    # "who calls it" questions want symbols; a lone weak explore word does not
    assert P.code_shaped(_prof(text="who calls the notifier", is_arch=True, arch_hit=["who calls"]))
    assert not P.code_shaped(_prof(text="search the list", is_arch=True, arch_hit=["search"]))


def test_domain_nouns_in_the_explore_list_are_not_architecture():
    """'inventory' (a domain word in many apps) put a graphify line on a label rename."""
    assert not P.strong_arch(_prof(arch_hit=["inventory"]))
    assert P.strong_arch(_prof(arch_hit=["dependency graph"]))


def test_symbol_summaries_are_short(monkeypatch):
    from prompt_router.modules import code_intel as CI
    hit = {"name": "makeStore", "kind": "function", "file": "src/a.ts", "line": 3, "summary": "x" * 300}
    monkeypatch.setattr(CI, "search", lambda *a, **k: [hit])
    item = CI.build_item(_prof(text="makestore"), {"repo": {"root": "/r"}, "config": {}})
    line = item["text"].splitlines()[1]
    assert len(line) <= 120, line


# --------------------------------------------------------------------------- C-12
def test_session_model_read_from_transcript_tail(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-opus-5-5"}}) + "\n")
    assert "opus" in P.session_model({"transcript_path": str(t)})
    assert P.session_model({"transcript_path": str(tmp_path / "none.jsonl")}) == ""
    assert P.session_model({"model": {"id": "claude-sonnet-4-6"}}) == "claude-sonnet-4-6"


def test_model_advice_skipped_on_an_opus_session(tmp_path, monkeypatch):
    from prompt_router.modules import model_advice as MA
    monkeypatch.setattr(MA, "advise", lambda p: "Heavy task: dispatch the planning-director agent (Opus)")
    t = tmp_path / "t.jsonl"
    t.write_text(json.dumps({"message": {"model": "claude-opus-5-5"}}) + "\n")
    assert R._model_items(_prof(), {"payload": {"transcript_path": str(t)}}) == []
    assert R._model_items(_prof(), {"payload": {"model": "claude-sonnet-4-6"}})


# --------------------------------------------------------------------------- end to end
@pytest.fixture()
def repo_home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {
        n: {} for n in ("jcodemunch", "jdocmunch", "graphify", "sequential-thinking")}}))
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"react": "^19", "fastify": "^5"}}))
    return home, root


def _ctx(prompt, home, root, sid):
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    cp = subprocess.run([sys.executable, str(HOOKS / "prompt_router" / "router.py")],
                        input=json.dumps({"prompt": prompt, "cwd": str(root), "session_id": sid}),
                        text=True, env=env, capture_output=True, timeout=30, check=False)
    return json.loads(cp.stdout.strip().splitlines()[-1])


def test_lunch_prompt_emits_nothing(repo_home):
    home, root = repo_home
    assert _ctx("thanks, that makes sense. what should I have for lunch?", home, root, "t-c10-lunch") == {}


def test_one_line_rename_has_no_write_gates(repo_home):
    home, root = repo_home
    out = _ctx("rename the label Qty to Quantity in src/components/Inventory/InventoryTable.tsx",
               home, root, "t-c10-rename")
    body = (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
    assert "First substantive change" not in body and "TDD:" not in body
