"""R3.2: the router points big or multi-act prompts at a saved workflow; small tasks stay inline."""
from __future__ import annotations

import json
import pathlib
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from prompt_router import classify as C                 # noqa: E402
from prompt_router import router as R                   # noqa: E402
from prompt_router.modules import workflow_routes as W  # noqa: E402

_ALL_ACTS = ["audit", "spec", "plan", "debug", "test", "impl", "refactor", "design", "clean",
             "security", "review", "docs", "verify"]
INDEX = [
    {"name": "invoke", "file": "invoke.js", "triggers": [], "acts": _ALL_ACTS, "min_size": "S",
     "phases": [], "args_schema": {}},
    {"name": "review", "file": "review.js", "triggers": ["review", "code review"], "acts": ["review"],
     "min_size": "S", "phases": [], "args_schema": {}},
    {"name": "audit", "file": "audit.js", "triggers": ["audit", "tech debt", "health check"], "acts": ["audit"],
     "min_size": "M", "phases": [], "args_schema": {}},
    {"name": "research", "file": "research.js", "triggers": ["research", "compare the docs", "literature"],
     "acts": [], "min_size": "M", "phases": [], "args_schema": {}},
    # min_size M, not L: the migrate test prompt does not reach size L on this floor (STEPS 11b)
    {"name": "migrate", "file": "migrate.js", "triggers": ["migrate", "port", "merge the harness"], "acts": [],
     "min_size": "M", "phases": [], "args_schema": {}},
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    (tmp_path / "workflows").mkdir()
    (tmp_path / "workflows" / "index.json").write_text(json.dumps(INDEX), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(W, "_escalation", lambda text, cwd: None)
    W._index.cache_clear()
    yield tmp_path
    W._index.cache_clear()


def _args(text: str) -> dict:
    return json.loads(text.split("with args ", 1)[1].rsplit(" (", 1)[0])


def _items(prompt, cwd="/nonexistent-dir", **kw):
    prof = C.classify({"prompt": prompt, "cwd": cwd})
    return W.items(prof, {"payload": {"prompt": prompt, "cwd": cwd}, "repo": None, "config": R._config(), **kw})


def test_two_acts_route_to_invoke_in_canonical_order(home):
    it = _items("plan the retry queue, then implement it and write the tests")
    assert len(it) == 1 and it[0]["text"].startswith("WORKFLOW: run saved workflow invoke with args ")
    args = _args(it[0]["text"])
    assert args["acts"][:2] == ["plan", "impl"] or args["acts"] == ["plan", "impl", "test"]
    assert args["run"].startswith("/nonexistent-dir/.claude/runs/") and args["slug"] and "tier_hint" not in args
    assert it[0]["id"].startswith("route:workflow:invoke:")
    assert it[0]["section"] == "ROUTING" and it[0]["tier"] == 2


def test_run_dir_is_absolute_utc_under_the_repo_root(home):
    class Repo:
        root = "/srv/repo"
    it = _items("plan the retry queue, then implement it and write the tests", cwd="/srv/repo/pkg/sub", repo=Repo())
    run = _args(it[0]["text"])["run"]
    assert run.startswith("/srv/repo/.claude/runs/") and re.fullmatch(r"\d{8}T\d{4}", run.rsplit("/", 1)[1].split("-", 1)[0])
    now = datetime.now(timezone.utc)
    assert run.rsplit("/", 1)[1][:8] in {now.strftime("%Y%m%d"), (now - timedelta(minutes=1)).strftime("%Y%m%d")}


def test_size_l_single_act_routes_to_invoke(home):
    it = _items("refactor the whole system across the codebase, multi-service, from scratch")
    assert it and "invoke" in it[0]["text"] and "size L" in it[0]["text"]


def test_one_small_act_stays_inline(home):
    assert _items("fix the typo in the login button label") == []


def test_missing_index_emits_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    W._index.cache_clear()
    try:
        assert _items("plan the retry queue, then implement it and write the tests") == []
    finally:
        W._index.cache_clear()


def test_review_needs_three_changed_files(home, monkeypatch):
    monkeypatch.setattr(W, "_changed_files", lambda root: 1)
    assert _items("review my changes") == []
    monkeypatch.setattr(W, "_changed_files", lambda root: 4)
    it = _items("review my changes")
    assert it and "review" in it[0]["text"]
    monkeypatch.setattr(W, "_changed_files", lambda root: 0)
    it = _items("review src/a.py src/b.py src/c.py for races")    # prompt paths count too
    assert it and "review" in it[0]["text"]


def test_audit_research_migrate_need_a_named_corpus(home):
    assert _items("do a tech debt audit") == []                      # no corpus
    assert _items("do a tech debt audit of this repo")                # named corpus
    assert _items("research the docs at https://example.com/api and compare the docs")
    assert _items("migrate the harness and merge the harness from ~/CODE_FILES/ECC into this repo")


def test_tier_hint_when_escalation_applies(home, monkeypatch):
    monkeypatch.setattr(W, "_escalation", lambda text, cwd: "previous attempt failed")
    it = _items("plan the retry queue, then implement it")
    assert _args(it[0]["text"])["tier_hint"] == "escalate"


def test_router_drops_per_act_dispatch_lines_when_a_workflow_fires(home):
    prof = C.classify({"prompt": "plan the retry queue, then implement it and write the tests",
                       "cwd": "/nonexistent-dir"})
    items = R._gather_items(prof, {"config": R._config(), "payload": {"prompt": prof.text, "cwd": "/nonexistent-dir"},
                                   "repo": None})
    ids = [it["id"] for it in items]
    assert any(i.startswith("route:workflow:") for i in ids)
    assert not any(i in ("route:plan", "route:impl", "route:test") for i in ids)


def test_two_weak_acts_on_a_small_task_stay_inline(home):
    """REVIEW2 Fix 4: two score-1 intents at size S are not a workflow."""
    prompt = "fix the failing test"
    assert _items(prompt) == []
    prof = C.classify({"prompt": prompt, "cwd": "/nonexistent-dir"})
    ids = [it["id"] for it in R._gather_items(
        prof, {"config": R._config(), "payload": {"prompt": prompt, "cwd": "/nonexistent-dir"}, "repo": None})]
    assert not any(i.startswith("route:workflow:") for i in ids)
    assert {"route:debug", "route:test"} <= set(ids), ids


def test_plan_and_implement_at_size_m_routes_to_invoke(home):
    it = _items("plan and implement the dark mode toggle across the settings pages")
    assert it and it[0]["text"].startswith("WORKFLOW: run saved workflow invoke")
    assert {"plan", "impl"} <= set(_args(it[0]["text"])["acts"])


def test_two_strong_acts_route_even_at_size_s(home, monkeypatch):
    prof = C.classify({"prompt": "fix the failing test", "cwd": "/nonexistent-dir"})
    prof.intents.update({"DEBUG": 3, "TEST": 3})
    it = W.items(prof, {"payload": {"prompt": "fix the failing test", "cwd": "/nonexistent-dir"},
                        "repo": None, "config": R._config()})
    assert it and _args(it[0]["text"])["acts"] == ["debug", "test"]


def test_workflow_text_never_tells_the_user_to_type_a_command(home):
    it = _items("plan the retry queue, then implement it and write the tests")
    assert "/workflow" not in it[0]["text"] and "run `" not in it[0]["text"]
