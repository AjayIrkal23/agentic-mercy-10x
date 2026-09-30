"""Prompt-router v3 regression suite: word-boundary classification, FE/BE/API
surface detection (prompt paths + vocab, cwd, repo stack fingerprint), skill
ranking precision (aliases collapsed, phantoms dropped, top-5 above the floor,
surface-routed IMPLEMENT agent), MCP route availability/guards, and the floor
builder's argv + zero-bucket guards.

Every routing assertion here is one of the audit's real misroutes (A02 B5/B6):
"Create a new REST endpoint" -> REVIEW via `cr`, "online/offline" -> DEBUG via
`off`, "Build a three.js scene" -> DESIGN via `ui` in "build". Tmp repos are
built on the fly so nothing depends on this machine's checkouts.

Runnable: `python3 -m pytest hooks/tests/test_router_surface.py -q`.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import classify as C                  # noqa: E402
from prompt_router import select as S                    # noqa: E402
from prompt_router.modules import mcp_routes as MR       # noqa: E402
from prompt_router.modules import surface as SF          # noqa: E402


# --------------------------------------------------------------------------- #
# fixtures: tmp repos with a stack fingerprint
# --------------------------------------------------------------------------- #
def _repo(tmp_path: pathlib.Path, name: str, *, react=False, go=False, three=False,
          sub: str | None = None) -> pathlib.Path:
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    if react or three:
        deps = {"react": "^19", "vite": "^7"}
        if three:
            deps.update({"three": "^0.170", "@react-three/fiber": "^9"})
        (root / "package.json").write_text(json.dumps({"dependencies": deps}), encoding="utf-8")
        (root / "vite.config.ts").write_text("export default {}", encoding="utf-8")
    if go:
        (root / "go.mod").write_text("module example\n\ngo 1.22\n", encoding="utf-8")
    if sub:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(autouse=True)
def _isolate_stack_cache(tmp_path, monkeypatch):
    cache = tmp_path / "state"
    cache.mkdir()
    monkeypatch.setattr(SF, "_cache_dir", lambda: cache)
    yield


def _classify(prompt: str, cwd: str) -> C.TaskProfile:
    return C.classify({"prompt": prompt, "cwd": cwd, "session_id": "t-surface"})


# --------------------------------------------------------------------------- #
# word-boundary classification (the A02-B5 misroutes)
# --------------------------------------------------------------------------- #
def test_create_is_not_review_and_offline_is_not_debug(tmp_path):
    root = _repo(tmp_path, "go", go=True)
    p = _classify("Create a new REST endpoint GET /api/v1/locos/:id/history with pagination and filtering", str(root))
    assert "REVIEW" not in p.intents, p.intents          # `cr` no longer matches "create"
    assert "IMPLEMENT" in p.intents
    q = _classify("Add a StatusBadge React component that shows online/offline with a tooltip", str(root))
    assert "DEBUG" not in q.intents, q.intents           # `off` no longer matches "offline"


def test_build_does_not_trigger_design_via_ui_substring(tmp_path):
    root = _repo(tmp_path, "go", go=True)
    p = _classify("Build the retry worker for the ingest queue", str(root))
    assert "DESIGN" not in p.intents
    assert not p.is_ui


def test_short_keywords_are_filtered_unless_allowlisted():
    assert not C.keyword_ok("cr")
    assert not C.keyword_ok("off")
    assert not C.keyword_ok("odd")
    assert C.keyword_ok("api") and C.keyword_ok("sql") and C.keyword_ok("glb")
    assert C.keyword_ok("implement")


def test_keyword_matcher_credits_each_keyword_once_including_subphrases():
    m = C.KeywordMatcher({"REVIEW": ["review", "review my changes", "before i merge", "merge"]})
    hits = m.hits("review my changes before i merge")
    # every keyword credited once: the sub-phrases inside longer matches too
    assert set(hits["REVIEW"]) == {"review", "review my changes", "before i merge", "merge"}
    assert m.hits("emerge from the merger") == {}      # word boundaries hold


def test_vague_ui_word_alone_is_not_a_ui_task(tmp_path):
    root = _repo(tmp_path, "fs", react=True, go=True)
    p = _classify("The login page returns 500 after deploy, figure out why", str(root))
    assert not p.is_ui                                   # "page" (0.4) alone is not UI
    assert "DEBUG" in p.intents


# --------------------------------------------------------------------------- #
# surface detection
# --------------------------------------------------------------------------- #
def test_prompt_vocab_frontend_wins_over_fullstack_repo(tmp_path):
    root = _repo(tmp_path, "fs", react=True, go=True)
    p = _classify("Add a StatusBadge React component to the loco table with a tooltip", str(root))
    assert "frontend" in p.surfaces and "backend" not in p.surfaces
    assert p.surface_source == "prompt"
    assert "go" not in p.surfaces                        # stack tag stays out of a FE prompt


def test_prompt_vocab_backend_with_api_tag(tmp_path):
    root = _repo(tmp_path, "fs", react=True, go=True)
    p = _classify("Create a new REST endpoint GET /api/v1/locos/:id/history with pagination", str(root))
    assert {"backend", "api"} <= p.surfaces
    assert "frontend" not in p.surfaces
    assert "go" in p.surfaces and "go" in p.weak_surfaces  # stack-inferred -> weak


def test_go_service_prompt_gets_backend_go_clickhouse(tmp_path):
    root = _repo(tmp_path, "go", go=True)
    p = _classify("Write a Go service that consumes UDP packets and batches inserts into ClickHouse with retries", str(root))
    assert {"backend", "go", "clickhouse"} <= p.surfaces
    assert "go" not in p.weak_surfaces                   # named in the prompt -> strong


def test_three_js_prompt_is_frontend_with_three_tag(tmp_path):
    root = _repo(tmp_path, "r3f", three=True)
    p = _classify("Build a three.js scene with a rotating GLB model using react-three-fiber", str(root))
    assert {"frontend", "three"} <= p.surfaces
    assert "three.js" not in p.paths                     # library name, not a file path


def test_cwd_decides_when_prompt_is_neutral(tmp_path):
    root = _repo(tmp_path, "fs", react=True, go=True, sub="server/internal")
    (root / "client" / "src").mkdir(parents=True)
    be = _classify("fix the retry loop", str(root / "server" / "internal"))
    fe = _classify("fix the retry loop", str(root / "client" / "src"))
    assert be.surfaces & {"backend"} and "frontend" not in be.surfaces and be.surface_source == "cwd"
    assert fe.surfaces & {"frontend"} and "backend" not in fe.surfaces and fe.surface_source == "cwd"


def test_stack_fallback_is_weak_and_fullstack(tmp_path):
    root = _repo(tmp_path, "fs", react=True, go=True)
    p = _classify("write a python script to rename photos by exif date", str(root))
    assert p.surface_source == "stack"
    assert {"frontend", "backend", "fullstack"} <= p.weak_surfaces


def test_stack_fingerprint_is_cached_on_marker_mtimes(tmp_path):
    root = _repo(tmp_path, "vite", react=True)
    from lib import repo_context as RC
    repo = RC.active_repo({"cwd": str(root)})
    fp1 = SF.stack_fingerprint(repo)
    cache = next(SF._cache_dir().glob("*.stack.json"))
    assert fp1["surfaces"] == ["frontend"]
    assert json.loads(cache.read_text(encoding="utf-8"))["surfaces"] == ["frontend"]
    fp2 = SF.stack_fingerprint(repo)                     # cache hit: identical result
    assert fp2 == fp1


def test_prompt_paths_extract_and_classify():
    toks = SF.prompt_paths("edit src/components/Hero.tsx and server/internal/handlers.go, not three.js")
    assert "src/components/hero.tsx" in toks and "server/internal/handlers.go" in toks
    assert "three.js" not in toks


def test_ui_excludes_suppress_ui():
    p = C.classify({"prompt": "backend only: add a pagination cursor to the list endpoint", "session_id": "x"})
    assert not p.is_ui


# --------------------------------------------------------------------------- #
# ranking precision
# --------------------------------------------------------------------------- #
def _ranked(prompt: str, cwd: str) -> list[str]:
    return [n for n, _ in S.rank_skills(_classify(prompt, cwd))]


def test_api_endpoint_ranks_backend_api_skills(tmp_path):
    root = _repo(tmp_path, "go", go=True)
    top = _ranked("Create a new REST endpoint GET /api/v1/locos/:id/history with pagination and filtering", str(root))
    assert len(top) <= 5
    assert {"backend-api-standards", "api-contract-standards"} <= set(top), top
    assert "frontend-standards-always-follow" not in top
    assert "frontend-response-handling" not in top


def test_status_badge_in_vite_repo_ranks_frontend_baseline(tmp_path):
    root = _repo(tmp_path, "vite", react=True)
    p = _classify("Add a StatusBadge React component to the loco table that shows online/offline with a tooltip", str(root))
    assert p.surfaces & {"frontend"} and "backend" not in p.surfaces
    top = [n for n, _ in S.rank_skills(p)]
    assert "frontend-standards-always-follow" in top, top
    assert not any(n.startswith("backend") or n.startswith("golang") for n in top)


def test_go_clickhouse_service_ranks_golang_patterns(tmp_path):
    root = _repo(tmp_path, "go", go=True)
    top = _ranked("Write a Go service that consumes UDP packets and batches inserts into ClickHouse with retries", str(root))
    assert "golang-patterns" in top, top
    assert "backend-standards-always-follow" in top
    if S.skill_exists("clickhouse:clickhouse-best-practices"):
        assert "clickhouse:clickhouse-best-practices" in top


def test_landing_page_ranks_design_authority_and_scrollcraft(tmp_path):
    root = _repo(tmp_path, "vite", react=True)
    top = _ranked("Make a landing page for our SaaS with a hero section, pricing and testimonials", str(root))
    assert "design-taste-frontend" in top, top
    if S.skill_exists("nateherk-design:scroll-craft"):
        assert "nateherk-design:scroll-craft" in top


def test_neutral_prompt_in_fullstack_repo_pushes_nothing(tmp_path):
    root = _repo(tmp_path, "fs", react=True, go=True)
    assert _ranked("write a python script to rename photos by exif date", str(root)) == []


def test_ranking_caps_at_five_above_floor(tmp_path):
    root = _repo(tmp_path, "fs", react=True, go=True)
    ranked = S.rank_skills(_classify("implement the full CSV import: endpoint, migration, react table, tests, docs", str(root)))
    assert len(ranked) <= 5
    assert all(score >= S.DEFAULT_MIN_SCORE for _, score in ranked)


def test_aliases_collapse_and_phantoms_drop():
    assert S.canonical("diagnose") == "debug-investigation"
    assert S.canonical("tdd") == "test-driven-development"
    merged = S._merge_canonical({"diagnose": 2.0, "debug-investigation": 3.0, "tdd": 1.0})
    assert merged == {"debug-investigation": 3.0, "test-driven-development": 1.0}
    assert not S.skill_exists("design-consultation")     # never pushed as a dead Skill() call
    assert S.skill_exists("debug-investigation")


def test_core_skill_set_is_never_re_pushed(tmp_path):
    core = S.core_skills()
    assert "codebase-intel-first" in core
    root = _repo(tmp_path, "fs", react=True, go=True)
    for prompt in ("Review my changes before I merge", "implement the CSV import endpoint"):
        assert not (set(_ranked(prompt, str(root))) & core)


def test_implement_agent_is_surface_routed():
    prof = C.TaskProfile(surfaces={"frontend"})
    assert S.implement_agent(prof) == "frontend-implementor-specialist"
    prof = C.TaskProfile(surfaces={"backend", "go"})
    assert S.implement_agent(prof) == "backend-implementor-specialist"
    prof = C.TaskProfile(surfaces={"frontend", "backend", "fullstack"})
    assert S.implement_agent(prof).startswith("backend-implementor-specialist then frontend-implementor-specialist")
    assert S.implement_agent(C.TaskProfile()) == "implementation-engineer"


def test_docs_and_verify_are_routable_acts():
    assert C.ACT_MAP["DOCS"] == "docs" and C.ACT_MAP["VERIFY"] == "verify"
    tiers = S.dispatch_tiers(C.TaskProfile(intents={"DOCS": 3, "VERIFY": 1}))
    by_cat = {t["category"]: t for t in tiers}
    assert by_cat["DOCS"]["kind"] == "agent" and by_cat["DOCS"]["agent"] == "docs-sync-agent"
    assert by_cat["VERIFY"]["agent"] == "qa-verifier"


# --------------------------------------------------------------------------- #
# MCP routes
# --------------------------------------------------------------------------- #
def test_mcp_route_skips_unavailable_and_needs_auth_servers(monkeypatch):
    monkeypatch.setattr(MR, "available_servers", lambda: {"semgrep", "plugin:clickhouse", "memory"})
    monkeypatch.setattr(MR, "needs_auth", lambda: {"plugin:clickhouse:clickhouse"})
    assert MR.server_available(["semgrep"]) == "semgrep"
    assert MR.server_available(["plugin:clickhouse"]) is None       # waiting on OAuth
    assert MR.server_available(["figma", "gbrain"]) is None         # not registered


def test_mcp_routes_fire_by_intent_regex_and_guard(monkeypatch):
    monkeypatch.setattr(MR, "available_servers", lambda: {"semgrep", "memory", "playwright", "higgsfield"})
    monkeypatch.setattr(MR, "needs_auth", lambda: set())
    prof = C.TaskProfile(text="remember that we always use rtk query going forward", intents={"SECURITY": 1})
    ids = {it["id"] for it in MR.items(prof, {})}
    assert "mcp:semgrep" in ids and "mcp:memory" in ids
    # browser route needs a listening dev server — none: silent
    monkeypatch.setattr(MR, "dev_server_port", lambda: None)
    prof = C.TaskProfile(text="take a screenshot, it looks wrong in the browser", intents={"QA": 2})
    assert not any(it["id"] == "mcp:browser" for it in MR.items(prof, {}))
    monkeypatch.setattr(MR, "dev_server_port", lambda: 5173)
    items = MR.items(prof, {})
    assert any(it["id"] == "mcp:browser" and ":5173" in it["text"] for it in items)


def test_mcp_routes_cap_and_frontend_asset_gate(monkeypatch):
    monkeypatch.setattr(MR, "available_servers", lambda: {"semgrep", "memory", "higgsfield", "github", "context7"})
    monkeypatch.setattr(MR, "needs_auth", lambda: set())
    prof = C.TaskProfile(text="remember that the hero image must be generated; see github.com/a/b/pull/12; "
                              "how do i use three.js drei", intents={"SECURITY": 1}, surfaces={"frontend"})
    items = MR.items(prof, {}, max_routes=3)
    assert len(items) == 3
    be = C.TaskProfile(text="generate the hero image for the endpoint docs", surfaces={"backend"})
    assert not any(it["id"] == "mcp:higgsfield" for it in MR.items(be, {}))


def test_semgrep_route_demands_explicit_config():
    # semgrep >=1.178 MCP: config=auto raises when SEMGREP_SEND_METRICS=off
    sem = next(r for r in MR.routes() if r["id"] == "semgrep")
    assert "explicit config" in sem["text"] and "p/default" in sem["text"]


def test_dev_server_port_parses_ss_and_ignores_companion(monkeypatch):
    class CP:
        stdout = ("State Recv-Q Send-Q Local Address:Port Peer Address:Port\n"
                  "LISTEN 0 4096 127.0.0.1:631 0.0.0.0:*\n"
                  "LISTEN 0 511 127.0.0.1:3025 0.0.0.0:*\n"
                  "LISTEN 0 511 *:5173 *:*\n")
    monkeypatch.setattr(MR.subprocess, "run", lambda *a, **k: CP())
    MR.dev_server_port.cache_clear()
    assert MR.dev_server_port() == 5173
    MR.dev_server_port.cache_clear()


# --------------------------------------------------------------------------- #
# floor builder guards
# --------------------------------------------------------------------------- #
def test_floor_builder_refuses_unknown_argv_without_writing():
    floor = _HOOKS / "trigger-floor.json"
    before = floor.stat().st_mtime_ns
    cp = subprocess.run([sys.executable, str(_HOOKS / "build-trigger-floor.py"), "--bogus"],
                        capture_output=True, text=True, check=False)
    assert cp.returncode == 2
    assert floor.stat().st_mtime_ns == before


def test_floor_has_ui_vocabulary_and_no_short_noise():
    meta = json.loads((_HOOKS / "trigger-floor.json").read_text(encoding="utf-8"))
    counts = meta["_meta"]["source_counts"]
    assert counts["ui.keywords"] >= 380, counts
    assert all(n > 0 for n in counts.values()), counts
    assert "v2" in meta["_meta"].get("charter", "")
    kws = [e["value"] for e in meta["entries"] if e["kind"] in ("act_keyword", "ui_keyword")]
    assert "cr" not in kws and "off" not in kws and "odd" not in kws
    assert "ui" in kws and "bug" in kws  # allow-listed short words survive


def test_floor_check_fails_on_zero_bucket(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("btf", _HOOKS / "build-trigger-floor.py")
    btf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(btf)  # type: ignore[union-attr]
    empty = tmp_path / "ui-keywords.json"
    empty.write_text(json.dumps({"ui_keywords": [], "ui_path_suffixes": [], "exclude_keywords": []}))
    monkeypatch.setitem(btf._SOURCES, "ui-keywords.json", empty)
    assert btf.check(quiet=True) == 1


# --------------------------------------------------------------------------- #
# e2e: routing table for the three headline prompts through the real hook
# --------------------------------------------------------------------------- #
def _hook(prompt: str, cwd: str) -> str:
    cp = subprocess.run([sys.executable, str(_HOOKS / "prompt_router" / "router.py")],
                        input=json.dumps({"prompt": prompt, "cwd": cwd,
                                          "session_id": f"t-e2e-{os.getpid()}-{abs(hash(prompt)) % 10**8}"}),
                        text=True, capture_output=True, timeout=30, check=False)
    return json.loads(cp.stdout.strip().splitlines()[-1]).get("hookSpecificOutput", {}).get("additionalContext", "")


def test_e2e_go_repo_endpoint_prompt(tmp_path):
    root = _repo(tmp_path, "go", go=True)
    body = _hook("Create a new REST endpoint GET /api/v1/locos/:id/history with pagination and filtering", str(root))
    assert body.startswith("<!-- prompt-router v3 -->")
    assert "backend-api-standards" in body and "api-contract-standards" in body
    assert "/invoke review" not in body
    assert "TDD:" in body                                    # backend surface -> tdd gate
    assert len(body) <= 3600


def test_e2e_vite_repo_component_prompt(tmp_path):
    root = _repo(tmp_path, "vite", react=True)
    body = _hook("Add a StatusBadge React component to the loco table that shows online/offline with a tooltip", str(root))
    assert "frontend-standards-always-follow" in body
    assert "/invoke debug" not in body
    assert "TDD:" not in body                                # no backend surface, no TEST intent


# --------------------------------------------------------------------------- #
# model-mode phrases, harness prompts, claude-infra surface (2026-09-28 regressions)
# --------------------------------------------------------------------------- #
def test_model_mode_phrase_is_explicit_only():
    from prompt_router import router as R
    cases = {
        "Continue the stopped ones": None,
        "use opus for this": None,                          # per-turn, not per-project
        "call all sonnet agents now": None,
        'The phrase "back to normal" clears it': None,      # quoted mention
        "Agent report: we restored smart routing. " * 20: None,  # long prose
        "<task-notification>back to normal": None,
        "use opus for this project": "opus",
        "All sonnet": "sonnet",
        "cheap mode please": "sonnet",
        "switch to fable in this repo": "fable",
        "back to normal": "clear",
    }
    for prompt, want in cases.items():
        assert R.parse_mode_phrase(prompt) == want, prompt


def test_model_mode_phrase_ignores_questions_and_embedded_mentions():
    """Santa A2: only a whole-message directive may change the per-project mode."""
    from prompt_router import router as R
    for prompt in ("is cheap mode still a thing?",
                   "why does smart routing send the reviewer to sonnet?",
                   "the page goes back to normal after refresh, fix it",
                   "use opus for this project?",
                   "we should use opus for this project because the reviewer is weak",
                   "all sonnet agents failed, why"):
        assert R.parse_mode_phrase(prompt) is None, prompt
    for prompt, want in (("Use opus for this project.", "opus"),
                         ("please use sonnet for this repo", "sonnet"),
                         ("all fable", "fable"), ("cheap mode", "sonnet"),
                         ("smart routing", "clear"), ("Back to normal!", "clear")):
        assert R.parse_mode_phrase(prompt) == want, prompt


def test_task_notification_is_not_routed():
    assert C.is_trivial_ack("<task-notification>\n<result>REST endpoint pagination</result>")


def test_claude_config_dir_is_claude_infra_not_backend():
    cwd = str(_HOOKS)  # the hooks dir lives in the Claude config repo
    prof = _classify("Fix the dispatch hook in opus-guard.py", cwd)
    assert "claude-infra" in prof.surfaces
    assert not prof.surfaces & {"backend", "frontend"}


def test_short_chatter_in_claude_dir_emits_nothing():
    assert _hook("Continue the stopped ones", str(_HOOKS)) == ""
