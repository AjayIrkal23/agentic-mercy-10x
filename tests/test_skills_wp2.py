"""Skills catalog + path-scoped rules (audit 2026-10-05 WP2: D-01, D-04, D-06, D-07,
D-08, F-08, C-13; the rest in test_skills_wp2_refs.py).

Each test names the finding it pins. Path tables use representative files from the
audited project (Vite web in src/, Fastify server in server/, Expo app in
sitesync-mobile-native/) and from ~/.claude itself.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
sys.path.insert(0, str(ROOT / "scripts"))
import skills_lib as sl  # noqa: E402
from build_skills_index import skill_meta  # noqa: E402

LOCKED = {k for k in json.loads((ROOT / "hooks/skills-sources.json").read_text(encoding="utf-8")) if not k.startswith("_")}
NEW_SKILLS = ["ensure-repo-docs", "agentation-react", "mongoose-patterns", "fastify-patterns",
              "expo-react-native", "vitest-rtl", "docker-compose"]
# Filler and catch-all words: as a lone keyword they match almost any prompt.
GENERIC = set("""
a an the and or of to in on for with without by from into this that these those it its
use used using uses user users want wants asks ask need needs needed must should will
would could can have has had make making made get see read first start starting step
time right small large big every always never other current existing new old main
code file files project repo repository system skill skills agent agents model mode
task tasks work working change changes changing feature features implementation
implementing implement planning plan review reviewing standard standards quality
behavior context data issue issues writing write creating create update updating
setting setup build test tests fix fixing api apis backend frontend server design
interface patterns pattern development driven trigger help support rules section
example examples including include structure layer layers phase phases
""".split())


def _fm(name: str) -> tuple[dict, str]:
    fm, body, ok = sl.read_frontmatter(SKILLS / name / "SKILL.md")
    assert ok, f"{name}: unreadable frontmatter"
    return fm, body


def _keywords(fm: dict) -> list[str]:
    meta = skill_meta(fm)
    trig = meta.get("triggers") if isinstance(meta.get("triggers"), dict) else {}
    return [str(k) for k in (trig.get("keywords") or meta.get("keywords") or [])]


def _glob_re(g: str) -> re.Pattern:
    out, i = "", 0
    while i < len(g):
        if g.startswith("**/", i):
            out, i = out + r"(?:.*/)?", i + 3
            continue
        if g.startswith("**", i):
            out, i = out + r".*", i + 2
            continue
        c = g[i]
        if c == "*":
            out += r"[^/]*"
        elif c == "?":
            out += r"[^/]"
        elif c == "{":
            j = g.index("}", i)
            alts = [re.escape(x).replace(r"\*", "[^/]*") for x in g[i + 1:j].split(",")]
            out, i = out + "(?:" + "|".join(alts) + ")", j
        elif c == "[":
            j = g.index("]", i)
            out, i = out + g[i:j + 1], j
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$")


def _matches(globs, path: str) -> bool:
    return any(_glob_re(g).match(path) for g in globs)


def _paths(fm: dict) -> list[str]:
    p = fm.get("paths") or []
    return [p] if isinstance(p, str) else list(p)


# --------------------------------------------------------------------------- D-01 / D-08
@pytest.mark.parametrize("name", NEW_SKILLS)
def test_new_skill_has_routable_frontmatter(name):
    fm, body = _fm(name)
    assert fm.get("name") == name
    desc = str(fm.get("description", ""))
    assert 40 <= len(desc) <= 300 and desc.count(". ") == 0, f"{name}: one short sentence"
    assert str(fm.get("when_to_use", "")).strip(), f"{name}: when_to_use missing"
    kws = _keywords(fm)
    assert 3 <= len(kws) <= 20, f"{name}: {len(kws)} keywords"
    assert not [k for k in kws if k.lower() in GENERIC], f"{name}: generic keywords"
    assert len((SKILLS / name / "SKILL.md").read_text(encoding="utf-8").splitlines()) <= 250
    assert "disable-model-invocation" not in fm, f"{name}: must stay model-invocable"


# --------------------------------------------------------------------------- D-04 / C-13
def test_curated_keywords_are_phrases_not_prose_tokens():
    bad = {}
    for d in sl.skill_dirs():
        if d.name in LOCKED or d.name.startswith("invoke"):
            continue
        fm, _ = _fm(d.name)
        kws = _keywords(fm)
        problems = [k for k in kws if k.lower() in GENERIC or ("/" in k and k.endswith(".md"))]
        if len(kws) > 20 or problems:
            bad[d.name] = (len(kws), problems[:6])
    assert not bad, f"rewrite keywords as trigger phrases: {bad}"


RECALL = [
    ("the expenses endpoint takes 4 seconds, find the slow query and profile it", "performance-optimization"),
    ("profile why the page re-renders so much, check core web vitals", "performance-optimization"),
    ("set up a github actions workflow that runs lint on every pull request", "ci-cd-and-automation"),
    ("write a docker compose file with a mongo service and a healthcheck", "docker-compose"),
    ("add an index to the mongoose schema and use lean with a projection", "mongoose-patterns"),
    ("add a fastify route with a json schema and a prehandler for auth", "fastify-patterns"),
    ("build a new expo router screen in the react native app", "expo-react-native"),
    ("add vitest tests with react testing library for the ExpenseCard component", "vitest-rtl"),
    ("simplify this function, it is too complex and hard to read", "code-simplification"),
    ("upgrade the dependency to the next major version and migrate the deprecated apis", "deprecation-and-migration"),
    # Router side (lead, C-13): `go cli`/`go program` count as Go vocabulary, and an explicit
    # "official docs" phrase boosts source-driven-development over its x0.5 demotion.
    ("write a small go cli that reads a csv", "golang-patterns"),
    ("check the official docs before using this library api", "source-driven-development"),
    ("write the failing test first, red green refactor", "test-driven-development"),
    ("check that the agentation overlay is still mounted in dev", "agentation-react"),
    ("make sure the repo docs exist and are fresh before coding", "ensure-repo-docs"),
]


def _rank(prompt: str, tmp: Path) -> list[str]:
    sys.path.insert(0, str(ROOT / "hooks"))
    from prompt_router import classify, select
    prof = classify.classify({"prompt": prompt, "cwd": str(tmp), "session_id": "wp2-recall"})
    return [n for n, _ in select.rank_all(prof)[:3]]


@pytest.mark.parametrize("prompt,skill", RECALL)
def test_recall_holes_rank_in_top3(prompt, skill, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    assert skill in _rank(prompt, tmp_path)


# --------------------------------------------------------------------------- D-06
def _aggregator():
    spec = importlib.util.spec_from_file_location("ssa_wp2", ROOT / "hooks/session-start-aggregator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_core_full_bodies_fit_the_session_start_budget(monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    m = _aggregator()
    tail = [t for t in (m._superpowers_session_context(), m._configured_mcp_context()) if t.strip()]
    sep = len("\n\n---\n\n")
    room = m.MAX_AGGREGATED_CHARS - sum(len(t) + sep for t in tail) - sep
    block = m._core_skill_digests(room)
    cfg = json.loads((ROOT / "hooks/core-skill-set.json").read_text(encoding="utf-8"))
    full = [e["skill"] for e in cfg["always"] if e.get("mode") == "full"]
    missing = [s for s in full if f"### skill: {s}" not in block]
    assert not missing, f"configured full but only a pointer arrives: {missing}"
    pointers = [e["skill"] for e in cfg["always"] if e.get("mode") != "full"]
    liars = [s for s in pointers if "core-skill-set.json, full" in (SKILLS / s / "SKILL.md").read_text(encoding="utf-8")]
    assert not liars, f"skill text claims full injection: {liars}"


# --------------------------------------------------------------------------- D-07 / F-08
def _rule_paths(name: str) -> list[str]:
    fm, _, ok = sl.read_frontmatter(ROOT / "rules" / f"{name}.md")
    assert ok
    return _paths(fm)


INFRA = ["hooks/dispatch.py", ".claude/hooks/dispatch.py", "scripts/validate_skills.py",
         ".claude/hooks/prompt_router/select.py", "installer/render.py"]


@pytest.mark.parametrize("rule", ["backend", "frontend"])
def test_surface_rules_skip_claude_infra(rule):
    hit = [p for p in INFRA if _matches(_rule_paths(rule), p)]
    assert not hit, f"rules/{rule}.md loads on infra files: {hit}"


def test_backend_rule_matches_backend_code_only():
    g = _rule_paths("backend")
    for p in ["server/src/routes/projects.routes.ts", "server/src/app.ts", "cmd/api/main.go",
              "db/migrations/001_init.sql", "api/app/main.py"]:
        assert _matches(g, p), p
    for p in ["src/api/projects/index.ts", "server/.env.example", "server/src/routes/AGENTS.md",
              "sitesync-mobile-native/apis/expenses/index.ts"]:
        assert not _matches(g, p), p


@pytest.mark.parametrize("doc", ["rules/frontend.md", "skills/frontend-standards-always-follow/SKILL.md",
                                 "skills/frontend-ui-engineering/SKILL.md"])
def test_web_frontend_docs_name_the_react_native_exemption(doc):
    """Their globs match Expo `.tsx` too (paths: has no negation); the body must redirect."""
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert "React Native" in text and "expo-react-native" in text


SKILL_PATHS = {  # skill: (must match, must not match)
    "threejs-r3f": (["src/scene/Hero.tsx"], ["server/src/models/projects.model.ts"]),
    "react-hooks-patterns": (["src/hooks/useProjectFilters.ts", "src/components/X/useThing.tsx"],
                             ["server/src/models/users.model.ts"]),
    "backend-standards-always-follow": (["server/src/app.ts", "cmd/api/main.go"],
                                        ["server/.env.example", "server/src/routes/AGENTS.md"]),
    "frontend-response-handling": (["src/api/projects/index.ts"], ["server/src/services/projects/getProject.ts"]),
    "backend-performance-standards": (["server/src/models/projects.model.ts", "db/q.sql"],
                                      ["sitesync-mobile-native/store/index.ts"]),
    "api-contract-standards": (["server/src/schemas/projects/get.schema.ts"], ["src/types/projects/index.ts"]),
    "test-driven-development": (["src/hooks/__tests__/useX.test.ts", "server/src/a/__tests__/b.test.ts"], []),
    "agent-development": ([".claude/agents/x.md", "agents/x.md"], ["src/agents/x.ts"]),
    "command-development": ([".claude/commands/x.md", "commands/x.md"], ["hooks/dispatch.py"]),
}


@pytest.mark.parametrize("skill", sorted(SKILL_PATHS))
def test_skill_paths_match_their_content(skill):
    fm, _ = _fm(skill)
    g = _paths(fm)
    yes, no = SKILL_PATHS[skill]
    assert [p for p in yes if not _matches(g, p)] == []
    assert [p for p in no if _matches(g, p)] == []

# D-09 / D-10 / D-11 / D-12 / D-13 / D-14 / D-15 / F-05 tests: test_skills_wp2_refs.py
# (250-line file limit).
