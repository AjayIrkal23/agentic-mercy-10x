"""Router audit fixes (workflow-audit 2026-10-31, surface A: A-01..A-12 + harness hand-backs).

Every test is one misroute the audit reproduced. Prompts are paraphrased (the repo is public).
Runnable: `python3 -m pytest hooks/tests/test_router_audit_fixes.py -q`.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import classify as C  # noqa: E402
from prompt_router import select as S  # noqa: E402
from prompt_router.modules import surface as SF  # noqa: E402

_CLAUDE = _HOOKS.parent


@pytest.fixture(autouse=True)
def _isolate_stack_cache(tmp_path, monkeypatch):
    cache = tmp_path / "state"
    cache.mkdir()
    monkeypatch.setattr(SF, "_cache_dir", lambda: cache)


def _prof(prompt: str, cwd: str = "/nonexistent-dir") -> C.TaskProfile:
    return C.classify({"prompt": prompt, "cwd": cwd, "session_id": "t-audit"})


def _ranked(prompt: str, cwd: str = "/nonexistent-dir") -> dict[str, float]:
    return dict(S.rank_all(_prof(prompt, cwd)))


# --------------------------------------------------------------------------- #
# A-02: `use()` collapses to "use"; bare hook(s) keywords
# --------------------------------------------------------------------------- #
def test_keyword_ok_judges_the_tokenized_form():
    assert not C.keyword_ok("use()")          # tokenizes to "use": 3 chars, not allow-listed
    assert not C.keyword_ok("()")             # no tokens at all
    assert C.keyword_ok("api") and C.keyword_ok("react hook") and C.keyword_ok("go")


def test_use_the_index_is_not_a_react_hooks_task():
    ranked = _ranked("use the jcodemunch index to find dead code in the repo")
    assert "react-hooks-patterns" not in ranked, ranked.get("react-hooks-patterns")


def test_bare_hooks_word_does_not_credit_react_hooks():
    meta = S.index_meta()["react-hooks-patterns"]
    assert "hook" not in meta["keywords"] and "hooks" not in meta["keywords"] and "use()" not in meta["keywords"]


def test_floor_builder_applies_the_same_keyword_rule():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_btf", _HOOKS / "build-trigger-floor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert not mod.keyword_ok("use()") and mod.keyword_ok("react hook")


# --------------------------------------------------------------------------- #
# A-01: "tokens" is not a UI word; claude-infra vetoes a UI false positive
# --------------------------------------------------------------------------- #
SAVE_TOKENS = "we should save tokens less and be more thorough with every answer"
INFRA_TOKENS = ("we should save tokens less and be more thorough, skills and hooks do not trigger "
                "properly for front end, back end, apis and infra work")


def test_bare_tokens_is_not_ui():
    p = _prof(SAVE_TOKENS, "/nonexistent-dir")
    assert not p.is_ui and not ({"frontend", "ui"} & p.surfaces), (p.surfaces, p.ui_hit)


def test_design_tokens_is_still_ui():
    p = _prof("extract the design tokens from the figma file into the theme", "/nonexistent-dir")
    assert p.is_ui


def test_infra_prompt_never_pushes_frontend_skills():
    p = _prof(INFRA_TOKENS, "/nonexistent-dir")
    assert "claude-infra" in p.surfaces and not p.is_ui and not ({"frontend", "ui"} & p.surfaces)
    ranked = _ranked(INFRA_TOKENS, "/nonexistent-dir")
    for bad in ("react-hooks-patterns", "design-taste-frontend", "frontend-standards-always-follow"):
        assert ranked.get(bad, 0) < 3.0, (bad, ranked.get(bad))


def test_claude_infra_vetoes_ui_without_frontend_vocabulary():
    p = _prof("why do the skills and hooks ignore design tokens", "/nonexistent-dir")
    assert "claude-infra" in p.surfaces and not p.is_ui and "frontend" not in p.surfaces


def test_claude_infra_keeps_ui_when_the_prompt_names_the_frontend():
    p = _prof("the hooks should load the design tokens into the react components", "/nonexistent-dir")
    assert p.is_ui


# --------------------------------------------------------------------------- #
# A-04: "front end" / "back end" as two words are surfaces
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("prompt,surface", [
    ("fix the front end login page, the submit button does nothing", "frontend"),
    ("the back end returns a wrong total for the invoice", "backend"),
    ("fix the frontend login page, the submit button does nothing", "frontend"),
])
def test_front_and_back_end_spellings(prompt, surface):
    p = _prof(prompt)
    assert surface in p.surfaces and p.surface_source == "prompt", (p.surfaces, p.surface_source)


# --------------------------------------------------------------------------- #
# A-03: index intents are router category names
# --------------------------------------------------------------------------- #
def _categories() -> set[str]:
    auton = json.loads((_HOOKS / "autonomous-skill-router.config.json").read_text(encoding="utf-8"))
    add = json.loads((_HOOKS / "prompt_router" / "router.config.json").read_text(encoding="utf-8"))["additions"]
    return set(auton["categories"]) | set(add["intents"])


def test_every_index_intent_is_a_router_category():
    idx = json.loads((_HOOKS / "skills-index.json").read_text(encoding="utf-8"))["skills"]
    cats = _categories()
    bad = {n: m["intents"] for n, m in idx.items() if set(m.get("intents", [])) - cats}
    assert not bad, bad
    for n in ("tech-debt-audit", "codebase-intel-first"):
        assert "AUDIT" in idx[n]["intents"], (n, idx[n]["intents"])


def test_intent_alias_normalizer():
    sys.path.insert(0, str(_CLAUDE / "scripts"))
    import build_skills_index as B
    cats = _categories()
    assert B.normalize_intents(["impl", "review", "planning", "general", "design", "REVIEW"], cats) == \
        ["DESIGN", "IMPLEMENT", "PLAN", "REVIEW"]
    assert B.normalize_intents(["frontend", "intel"], cats) == []


def test_audit_prompt_ranks_the_audit_skill():
    ranked = _ranked("audit this repo for tech debt and tell me what to clean up")
    assert ranked.get("tech-debt-audit", 0) >= 3.0, ranked.get("tech-debt-audit")


# --------------------------------------------------------------------------- #
# harness messages are not user prompts
# --------------------------------------------------------------------------- #
MACHINE = [
    "[Subagent hand-back]\nIMPL-REPORT written. Frontend skills, hooks and a review workflow.",
    "  \n[Subagent hand-back] done",
    "<system-reminder>\nnote\n</system-reminder>\n[Subagent hand-back]\nreport",
    '<system-reminder foo="1">[Subagent hand-back] done',
    '<system-reminder>x</system-reminder><agent-message from="impl">done</agent-message>',
    '<agent-message from="reader-1">here are the findings</agent-message>',
    "Another Claude session sent a message: please review",
    "<system-reminder>\nctx\n</system-reminder>\nAnother Claude session sent a message (uds:/x): hi",
]
HUMAN = [
    'why does the router treat "[Subagent hand-back]" as a task? fix the react component',
    "the string Another Claude session sent a message is in classify.py, is that right?",
    "fix the <agent-message from= parser in the docs",
    "add a test where a prompt mentions [Subagent hand-back] mid sentence",
]


@pytest.mark.parametrize("prompt", MACHINE)
def test_harness_messages_are_machine_text(prompt):
    assert C.is_trivial_ack(prompt), prompt
    assert _prof(prompt).trivial_ack


@pytest.mark.parametrize("prompt", HUMAN)
def test_human_prompts_that_mention_the_markers_are_routed(prompt):
    assert not C.is_trivial_ack(prompt), prompt


def test_not_human_lists_stay_in_step():
    turns = (_HOOKS / "lib" / "turns.py").read_text(encoding="utf-8")
    ts = (_CLAUDE / "mods" / "mercy" / "hooks" / "lib" / "nothuman.ts").read_text(encoding="utf-8")
    for marker in ("[Subagent hand-back]", "<agent-message from=", "Another Claude session sent a message"):
        assert marker in turns, ("lib/turns.py", marker)
        assert marker in ts, ("lib/nothuman.ts", marker)
    from lib import turns as T
    for prompt in MACHINE:
        entry = {"type": "user", "message": {"role": "user", "content": prompt}}
        assert T._prompt_text(entry) is None, prompt
    for prompt in HUMAN:
        entry = {"type": "user", "message": {"role": "user", "content": prompt}}
        assert T._prompt_text(entry) == prompt, prompt


# --------------------------------------------------------------------------- #
# A-05: plugin skills reach the cut-off through curated triggers
# --------------------------------------------------------------------------- #
def test_plugin_overlay_gives_full_weight_triggers():
    sys.path.insert(0, str(_CLAUDE / "scripts"))
    import build_skills_index as B
    entries = {
        "superpowers:systematic-debugging": {"source": "plugin-description", "keywords": ["bug"], "intents": [], "surfaces": []},
        "superpowers:using-superpowers": {"source": "plugin-description", "keywords": ["how"], "intents": [], "surfaces": []},
        "local-skill": {"source": "metadata", "keywords": ["x"], "intents": [], "surfaces": []},
    }
    overlay = {"skills": {"superpowers:systematic-debugging": {"keywords": ["Root Cause"], "intents": ["debug", "frontend"]},
                          "local-skill": {"keywords": ["never"]}}}
    bare = B.apply_plugin_overlay(entries, overlay, {"DEBUG"})
    e = entries["superpowers:systematic-debugging"]
    assert e["source"] == "plugin" and e["keywords"] == ["root cause"] and e["intents"] == ["DEBUG"]
    assert entries["local-skill"]["keywords"] == ["x"]            # overlay never touches a local skill
    assert bare == ["superpowers:using-superpowers"]               # visible, not silent


def _need_plugin(name: str):
    if name not in S.index_meta():
        pytest.skip(f"{name} not installed on this machine")


@pytest.mark.parametrize("prompt,want", [
    ("why does this test fail intermittently, it is flaky", "superpowers:systematic-debugging"),
    ("audit this repo for bloat and tell me what can i delete", "ponytail:ponytail-audit"),
])
def test_plugin_skills_can_be_pushed(prompt, want):
    _need_plugin(want)
    assert _ranked(prompt).get(want, 0) >= 3.0, _ranked(prompt).get(want)


# --------------------------------------------------------------------------- #
# A-06: claude-infra prompts map to infra skills (harness skills included)
# --------------------------------------------------------------------------- #
def _top(prompt: str, cwd: str = "/nonexistent-dir", n: int = 5) -> list[str]:
    return [k for k, v in S.rank_skills(_prof(prompt, cwd), top_n=n)]


def test_skills_and_hooks_prompt_gets_the_linkage_skill():
    assert "skill-linkage-story" in _top("the skills and hooks do not trigger properly for my prompts")


def test_repo_rule_prompt_gets_hookify():
    assert "hookify-rules" in _top("add a repo rule in the hooks that blocks force push in this repo")


def test_harness_skills_are_valid_candidates():
    assert S.skill_exists("update-config") and S.skill_exists("plugin-authoring")
    assert not S.skill_exists("no-such-skill-anywhere")
    assert "update-config" in _top("change settings.json to add a permission allow rule for the hooks")


# --------------------------------------------------------------------------- #
# A-07: the repo stack pre-selects stack skills
# --------------------------------------------------------------------------- #
def _stack_repo(tmp_path: pathlib.Path, name: str, deps: dict, dev: dict | None = None) -> str:
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": deps, "devDependencies": dev or {}}), encoding="utf-8")
    return str(root)


def test_fastify_mongoose_repo_preselects_stack_skills(tmp_path):
    cwd = _stack_repo(tmp_path, "svc", {"fastify": "4.28.0", "mongoose": "8.5.0"})
    top = _top("add an endpoint that returns invoices sorted by date with an index on the date field", cwd)
    assert "mongoose-patterns" in top and "fastify-patterns" in top, top
    assert "postgres-patterns" not in top, top               # a Mongo repo's "index on" is not Postgres


def test_frontend_prompt_in_a_mongoose_repo_gets_no_backend_stack_skill(tmp_path):
    cwd = _stack_repo(tmp_path, "full", {"react": "19.0.0", "vite": "7.0.0", "mongoose": "8.5.0"})
    ranked = _ranked("add a tooltip to the sidebar button in the react component", cwd)
    assert ranked.get("mongoose-patterns", 0) < 3.0 and "fastify-patterns" not in ranked


def test_vitest_repo_test_prompt_gets_vitest_rtl(tmp_path):
    cwd = _stack_repo(tmp_path, "web", {"react": "19.0.0"}, {"vitest": "2.0.0"})
    assert "vitest-rtl" in _top("write tests for the invoice table component", cwd)


def test_stack_indicators_cover_the_new_tags():
    cfg = json.loads((_HOOKS / "prompt_router" / "router.config.json").read_text(encoding="utf-8"))
    tags = {s["tag"] for s in cfg["additions"]["stack_indicators"]["stacks"]}
    assert {"mongo", "fastify", "express", "vitest", "expo"} <= tags


# --------------------------------------------------------------------------- #
# A-08: caps and floors; the report numbers the caps
# --------------------------------------------------------------------------- #
def test_shipped_caps():
    cfg = json.loads((_HOOKS / "prompt_router" / "router.config.json").read_text(encoding="utf-8"))
    assert cfg["max_skill_pushes"] == 5 and cfg["min_skill_score"] == 3.0
    assert cfg["min_skill_score_tail"] == 2.5 and cfg["tail_from_rank"] == 3
    assert cfg["max_mcp_routes"] == 6 and cfg["max_routing_lines"] == 8
    assert cfg["code_intel"]["max_symbols"] == 8


def test_tail_ranks_use_the_lower_floor(monkeypatch):
    monkeypatch.setattr(S, "rank_all", lambda p: [("a", 5.0), ("b", 4.0), ("c", 3.2), ("d", 2.7), ("e", 2.6), ("f", 2.4)])
    got = S.rank_skills(object(), top_n=5, min_score=3.0, tail_min=2.5, tail_from=3)
    assert [n for n, _ in got] == ["a", "b", "c", "d", "e"]
    got = S.rank_skills(object(), top_n=5, min_score=3.0)
    assert [n for n, _ in got] == ["a", "b", "c"]


def test_at_most_five_skill_lines_and_rank_one_must_read(monkeypatch):
    from prompt_router import router as R
    names = [f"s{i}" for i in range(8)]
    monkeypatch.setattr(S, "rank_skills", lambda p, top_n=4, **k: [(n, 9.0 - i) for i, n in enumerate(names)][:top_n])
    monkeypatch.setattr(S, "skill_exists", lambda n: True)
    cfg = json.loads((_HOOKS / "prompt_router" / "router.config.json").read_text(encoding="utf-8"))
    prof = C.TaskProfile(text="review the auth security", intents={"SECURITY": 4}, surfaces=set())
    items = [it for it in R._skill_items(prof, {"config": cfg}) if it["id"].startswith("skill:")]
    assert len(items) == 5 and "(MUST-READ)" in items[0]["text"]
    assert all("(SHOULD-READ)" in it["text"] for it in items[1:])


# --------------------------------------------------------------------------- #
# A-11: cross-cutting skills are visible without a matching file
# --------------------------------------------------------------------------- #
def test_cross_cutting_skills_carry_no_paths_scope():
    idx = json.loads((_HOOKS / "skills-index.json").read_text(encoding="utf-8"))["skills"]
    for name in ("owasp-security", "test-driven-development", "update-docs", "webapp-testing",
                 "skill-linkage-story", "mcp-builder", "domain-modeling", "ci-cd-and-automation"):
        if name in idx:
            assert not idx[name].get("paths"), (name, idx[name]["paths"])
