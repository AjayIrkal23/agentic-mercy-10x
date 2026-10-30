"""library_routes.items: <= 2 LIBRARY lines (stack pack, REVIEW lane, >= 2 trigger hits); never raises."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import classify as C  # noqa: E402
from prompt_router.modules import library_routes as L  # noqa: E402

_SHA = "a" * 40


def _e(eid, kind, path, *, title="", triggers=(), stacks=(), surfaces=(), conflicts=()):
    return {"id": eid, "kind": kind, "path": path, "title": title or eid.split(":", 1)[1], "triggers": list(triggers),
            "stacks": list(stacks), "surfaces": list(surfaces), "conflicts": list(conflicts), "token_estimate": 10,
            "upstream": {"path": "x", "sha": _SHA, "extras": []}}


ENTRIES = [
    _e("rules:rust", "rules-pack", "library/ecc/rules/rust/", stacks=["rust"]),
    _e("rules:python", "rules-pack", "library/ecc/rules/python/", stacks=["python"]),
    _e("rules:common", "rules-pack", "library/ecc/rules/common/"),
    _e("agent:rust-reviewer", "agent", "library/ecc/agents/rust-reviewer.md", stacks=["rust"], surfaces=["review"]),
    _e("agent:python-reviewer", "agent", "library/ecc/agents/python-reviewer.md", stacks=["python"],
       surfaces=["review"]),
    _e("skill:clickhouse-io", "skill", "library/ecc/skills/clickhouse-io/SKILL.md",
       triggers=["clickhouse", "materialized view", "mergetree", "clickhouse-client"]),
    _e("skill:token-budget-advisor", "skill", "library/ecc/skills/token-budget-advisor/SKILL.md",
       triggers=["token budget", "context budget"], conflicts=["server"]),
    _e("digest:plan-canvas", "digest", "library/ecc/digests/plan-canvas.md",
       triggers=["plan canvas", "annotate", "approve plan"]),
    _e("skill:kotlin-ktor-patterns", "skill", "library/ecc/skills/kotlin-ktor-patterns/SKILL.md", stacks=["kotlin"],
       triggers=["kotlin", "ktor", "patterns", "auth", "authentication", "routing", "server"]),
    _e("skill:redis-patterns", "skill", "library/ecc/skills/redis-patterns/SKILL.md",
       triggers=["redis", "patterns", "caching", "limiting", "rate", "distributed lock"]),
]


def _write_index(p: pathlib.Path, entries=ENTRIES) -> None:
    p.write_text(json.dumps({"schema": 1, "upstream": {"sha": _SHA}, "count": len(entries), "entries": entries}),
                 encoding="utf-8")


@pytest.fixture
def index(tmp_path, monkeypatch):
    p = tmp_path / "INDEX.json"
    _write_index(p)
    cache = tmp_path / "cache.json"
    monkeypatch.setattr(L, "_INDEX_PATH", p)
    monkeypatch.setattr(L, "_cache_path", lambda: cache)
    L._load.cache_clear()
    L._MATCHERS.clear()
    yield p, cache
    L._load.cache_clear()
    L._MATCHERS.clear()


def _p(text="", surfaces=(), weak=(), intents=None):
    return C.TaskProfile(text=text, surfaces=set(surfaces), weak_surfaces=set(weak), intents=dict(intents or {}))


def _ids(items):
    return [i["id"] for i in items]


def test_stack_match_names_the_rules_pack(index):
    out = L.items(_p(surfaces={"rust"}, weak={"rust"}), "/tmp", set())
    assert _ids(out) == ["library:rules:rust"]
    t = out[0]["text"]
    assert t.startswith("LIBRARY: rust rules pack")
    assert "library/ecc/rules/rust/coding-style.md" in t and "library/ecc/rules/rust/patterns.md" in t
    assert out[0]["tier"] == 2


def test_review_lane_adds_reviewer_prompt(index):
    out = L.items(_p(surfaces={"python"}, intents={"REVIEW": 2}), "/tmp", set())
    assert _ids(out) == ["library:rules:python", "library:agent:python-reviewer"]
    assert "library/ecc/agents/python-reviewer.md" in out[1]["text"] and "general-purpose" in out[1]["text"]


def test_user_owned_stacks_never_route(index, tmp_path, monkeypatch):
    assert L.items(_p(surfaces={"typescript", "react", "go"}), "/tmp", set()) == []
    p = tmp_path / "react.json"
    _write_index(p, ENTRIES + [_e("agent:react-build-resolver", "agent", "library/ecc/agents/react-build-resolver.md",
                                  triggers=["react", "component", "build"], stacks=["react"])])
    monkeypatch.setattr(L, "_INDEX_PATH", p)
    assert L.items(_p("write a react component build"), "/tmp", set()) == []


def test_trigger_hits_need_two_distinct_phrases(index):
    assert _ids(L.items(_p("optimise the clickhouse mergetree table"), "/tmp", set())) == ["library:skill:clickhouse-io"]
    assert L.items(_p("a clickhouse question"), "/tmp", set()) == []


def test_stack_scoped_entry_needs_its_stack_in_text_or_surfaces(index):
    assert L.items(_p("add an endpoint to the express server with auth"), "/tmp", set()) == []
    assert _ids(L.items(_p("implement the kotlin ktor server auth plugin"), "/tmp", set())) == [
        "library:skill:kotlin-ktor-patterns"]
    assert _ids(L.items(_p("a ktor server with auth"), "/tmp", set())) == ["library:skill:kotlin-ktor-patterns"]
    prof = _p("add auth to the server routing", surfaces={"kotlin"}, weak={"kotlin"})
    assert "library:skill:kotlin-ktor-patterns" in _ids(L.items(prof, "/tmp", set()))


def test_stackless_entry_needs_a_name_word(index):
    assert L.items(_p("design an api with rate limiting and caching"), "/tmp", set()) == []
    assert _ids(L.items(_p("redis caching for the rate limiter"), "/tmp", set())) == ["library:skill:redis-patterns"]


def test_name_words_drop_generic_parts():
    assert L._name_words("skill:redis-patterns") == ["redis"]
    assert L._name_words("skill:clickhouse-io") == ["clickhouse"]
    assert L._name_words("agent:database-reviewer") == ["database"]
    assert L._name_words("skill:rust-testing") == ["rust", "testing"]
    assert L._name_words("skill:x-api") == ["x", "api"]


def test_head_word_is_the_first_name_part_and_review_names_need_review_intent(index, tmp_path, monkeypatch):
    p = tmp_path / "more.json"
    _write_index(p, ENTRIES + [
        _e("skill:x-api", "skill", "library/ecc/skills/x-api/SKILL.md", triggers=["api", "rate", "limiting", "posting"]),
        _e("command:flutter-review", "command", "library/ecc/commands/flutter-review.md",
           triggers=["flutter", "review", "widget", "testing"])])
    monkeypatch.setattr(L, "_INDEX_PATH", p)
    assert L.items(_p("design an api with rate limiting"), "/tmp", set()) == []
    assert L.items(_p("flutter widget testing"), "/tmp", set()) == []
    assert _ids(L.items(_p("review the flutter widget testing", intents={"REVIEW": 1}), "/tmp", set())) == [
        "library:command:flutter-review"]


def test_old_cache_version_is_rebuilt(index):
    p, cache = index
    st = p.stat()
    cache.write_text(json.dumps({"sig": f"{st.st_mtime_ns}:{st.st_size}", "packs": {}, "reviewers": {},
                                 "triggers": [["skill:redis-patterns", "x", "skill", "t", ["redis", "caching"]]]}),
                     encoding="utf-8")
    assert _ids(L.items(_p("redis caching for the rate limiter"), "/tmp", set())) == ["library:skill:redis-patterns"]
    assert json.loads(cache.read_text(encoding="utf-8"))["v"] == L._CACHE_V


def test_conflicting_entries_are_never_emitted(index):
    assert L.items(_p("what is my token budget and context budget"), "/tmp", set()) == []


def test_cap_two_and_order(index):
    prof = _p("review the clickhouse mergetree crate", surfaces={"rust"}, intents={"REVIEW": 2})
    assert _ids(L.items(prof, "/tmp", set())) == ["library:rules:rust", "library:agent:rust-reviewer"]


def test_emitted_ids_are_skipped(index):
    prof = _p("review the clickhouse mergetree crate", surfaces={"rust"}, intents={"REVIEW": 2})
    out = L.items(prof, "/tmp", {"library:rules:rust"})
    assert _ids(out) == ["library:agent:rust-reviewer", "library:skill:clickhouse-io"]


def test_prompt_named_stack_beats_weak_one(index):
    prof = _p(surfaces={"python", "rust"}, weak={"python"})
    assert _ids(L.items(prof, "/tmp", set()))[0] == "library:rules:rust"


def test_missing_or_broken_index_is_empty_and_fast(index, monkeypatch, tmp_path):
    monkeypatch.setattr(L, "_INDEX_PATH", tmp_path / "missing.json")
    t0 = time.perf_counter()
    assert L.items(_p(surfaces={"rust"}), "/tmp", set()) == []
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    monkeypatch.setattr(L, "_INDEX_PATH", broken)
    assert L.items(_p(surfaces={"rust"}), "/tmp", set()) == []
    assert time.perf_counter() - t0 < 0.05


def test_wrong_schema_is_empty(index):
    p, _ = index
    p.write_text(json.dumps({"schema": 2, "entries": ENTRIES}), encoding="utf-8")
    assert L.items(_p(surfaces={"rust"}), "/tmp", set()) == []


def test_cache_file_is_written_and_reused(index):
    p, cache = index
    L.items(_p(surfaces={"rust"}), "/tmp", set())
    st = p.stat()
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert data["sig"] == f"{st.st_mtime_ns}:{st.st_size}" and "rust" in data["packs"]
    cache.write_text("not json", encoding="utf-8")
    L._load.cache_clear()
    assert _ids(L.items(_p(surfaces={"rust"}), "/tmp", set())) == ["library:rules:rust"]
    assert json.loads(cache.read_text(encoding="utf-8"))["sig"] == f"{st.st_mtime_ns}:{st.st_size}"
    _write_index(p, [e for e in ENTRIES if e["id"] != "rules:rust"])
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    assert L.items(_p(surfaces={"rust"}), "/tmp", set()) == []
    assert "rust" not in json.loads(cache.read_text(encoding="utf-8"))["packs"]


def test_items_never_raise(index, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(L, "_match", boom)
    assert L.items(_p(surfaces={"rust"}), "/tmp", set()) == []
    assert L.items(None, None, None) == []


def test_windows_noop_paths(index, monkeypatch):
    posix = L.items(_p("optimise the clickhouse mergetree table", surfaces={"rust"}), "/tmp", set())
    if L._plat is not None:
        monkeypatch.setattr(L._plat, "IS_WINDOWS", True)
    assert L.items(_p("optimise the clickhouse mergetree table", surfaces={"rust"}), "/tmp", set()) == posix
