"""Agent frontmatter and body contracts (ECC merge, package agents-skills, 2026-10-29).

Every agent is capped (`maxTurns`), cheap to list (description <= 1,200 chars, one example),
runs on the `tiers.max20` model column, and does not restate the boilerplate that the
SubagentStart block already injects."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"
POLICY = json.loads((ROOT / "hooks" / "model-policy.json").read_text(encoding="utf-8"))
TURNS = POLICY["turn_caps"]["agents"]  # the one cap table (hooks/model-policy.json turn_caps)
REPORT_AGENTS = {"santa-reviewer", "spec-architect", "planning-director", "audit-specialist",
                 "debug-detective", "qa-verifier", "security-sentinel"}
OMIT = {"deadcode-reaper", "qa-verifier", "memory-codex"}
COMPACT = {"qa-verifier", "test-author"}
MEMORY_LOCAL = {"audit-specialist", "debug-detective", "santa-reviewer", "security-sentinel"}
IMPLEMENTOR_CLASS = {"implementation-engineer", "backend-implementor-specialist",
                     "frontend-implementor-specialist", "refactor-specialist", "integrator-specialist"}
_FM = re.compile(r"---\n(.*?)\n---\n?(.*)", re.S)


def _parse(text: str) -> tuple[dict, str, str]:
    m = _FM.match(text)
    if not m:
        return {}, "", text
    fm: dict = {}
    for key, val in re.findall(r"^(\w+):\s*(.+?)\s*$", m.group(1), re.M):
        fm.setdefault(key, val)  # first hit wins; example lines inside description come later
    return fm, m.group(1), m.group(2)


def _agents() -> dict[str, tuple[dict, str]]:
    out = {}
    for p in sorted(AGENTS.glob("*.md")):
        if p.stem in ("README", "CLAUDE", "AGENTS"):
            continue
        fm, raw, body = _parse(p.read_text(encoding="utf-8"))
        if fm:
            out[p.stem] = (fm, body, raw)
    return out


def _desc(fm_text: str) -> str:
    """The unquoted `description:` value (one double-quoted line with \\n escapes)."""
    m = re.search(r'^description:\s*(".*")\s*$', fm_text, re.M)
    assert m, "description must be one double-quoted YAML line"
    return json.loads(m.group(1))


AGENT_MAP = _agents()
_EDIT_DISALLOWED = {n for n, (fm, _, _) in AGENT_MAP.items() if "Edit" in str(fm.get("disallowedTools", ""))}


def test_every_agent_has_maxturns():
    expected = TURNS
    assert set(AGENT_MAP) == set(expected) and len(expected) == 17
    for name, (fm, _, _) in AGENT_MAP.items():
        assert int(fm["maxTurns"]) == expected[name], name


def test_report_agents_carry_the_turn_budget_protocol():
    for name in REPORT_AGENTS:
        fm, body, _ = AGENT_MAP[name]
        assert "## Turn budget" in body, name
        assert f"{fm['maxTurns']} turns" in body, name  # the body states its own cap
        assert "INCOMPLETE" in body and "StructuredOutput" in body, name
        assert "notes file your prompt names" in body, name  # parallel runs never share one artifact
    for name in set(AGENT_MAP) - REPORT_AGENTS:
        assert "## Turn budget" not in AGENT_MAP[name][1], name  # executors keep their own contracts


def test_omit_claude_md_exactly_three():
    assert {n for n, (fm, _, _) in AGENT_MAP.items() if fm.get("omitClaudeMd") == "true"} == OMIT
    for name in ("docs-sync-agent", "test-author"):
        assert "omitClaudeMd" not in AGENT_MAP[name][0]


def test_autocompact_only_on_haiku_log_readers():
    for name, (fm, _, _) in AGENT_MAP.items():
        if name in COMPACT:
            assert fm.get("autoCompactWindow") == "120000", name
        else:
            assert "autoCompactWindow" not in fm, name


def test_model_is_the_max20_column():
    col = POLICY["tiers"]["max20"]["roles"]
    for name, (fm, _, _) in AGENT_MAP.items():
        assert fm["model"] == col[POLICY["roles"]["agents"].get(name, "default")], name


def test_description_budget_and_one_example():
    total = 0
    for name, (_, _, raw) in AGENT_MAP.items():
        desc = _desc(raw)
        total += len(desc)
        assert len(desc) <= 1200, (name, len(desc))
        assert desc.count("<example>") == 1, name
    assert total <= 17 * 1000, total


def test_memory_local_agents_name_the_gitignore_line():
    for name, (fm, body, _) in AGENT_MAP.items():
        if name in MEMORY_LOCAL:
            assert fm.get("memory") == "local", name
            assert ".claude/agent-memory-local/" in body and "gitignore" in body, name
            if name in _EDIT_DISALLOWED:  # santa-reviewer, audit-specialist, security-sentinel
                assert "with Edit" not in body and "memory not gitignored" in body, name
            else:  # debug-detective can Edit, so it adds the line itself
                assert "add the line with Edit" in body, name
        else:
            assert "memory" not in fm, name


def test_boilerplate_is_not_pasted_per_agent():
    for name, (_, body, _) in AGENT_MAP.items():
        assert "No commits** (CLAUDE.md §2)" not in body, name
        assert "No file may exceed 250 lines" not in body, name
        if name in IMPLEMENTOR_CLASS:
            assert "SubagentStart block" in body, name


def test_implementor_class_states_the_250_cap():
    for name in IMPLEMENTOR_CLASS:
        body = AGENT_MAP[name][1]
        assert re.search(r"no file >\s?250 lines", body), name  # the cap is a hard rule in the body
        assert "the 250-line file cap and MCP-first are not restated here" not in body, name


def test_subagent_block_is_not_credited_with_the_cap():
    hook = (ROOT / "hooks" / "subagent-context.py").read_text(encoding="utf-8")
    if "250" in hook:  # the block may carry the cap later; then the claim is true
        return
    gen = (ROOT / "hooks" / "gen-agent-skill-blocks.py").read_text(encoding="utf-8")
    readme = (AGENTS / "README.md").read_text(encoding="utf-8")
    for text, where in ((gen, "gen-agent-skill-blocks.py"), (readme, "agents/README.md")):
        assert not re.search(r"250-line cap[^.]*SubagentStart block", text), where
        assert not re.search(r"\(write protocol, no commits, no servers, the 250-line cap", text), where


def test_santa_reviewer_review_quality_rules():
    body = AGENT_MAP["santa-reviewer"][1]
    for needle in ("Pre-report gate", ">= 80", "CRITICAL", "false-positive", "Dedupe",
                   "defaults to refuted", "never yields APPROVE", "| CRITICAL |", "| LOW |"):
        assert needle in body, needle


def test_implementation_engineer_build_resolver_discipline():
    body = AGENT_MAP["implementation-engineer"][1]
    for needle in ("three attempts", "never `rm -rf`", "never start", "never commit"):
        assert needle in body, needle


def test_team_lead_contract_and_cascade():
    text = (AGENTS / "team-lead.md").read_text(encoding="utf-8")
    for needle in ("Delegation completion contract", "cascade", "minimum viable parallelism"):
        assert needle in text, needle
    sys.path.insert(0, str(ROOT / "hooks"))
    from lib.invoke_templates import RUN_JSON  # noqa: PLC0415
    assert RUN_JSON in text


def test_readme_counts_and_tables():
    text = (AGENTS / "README.md").read_text(encoding="utf-8")
    routing = text.split("## Routing table", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `([\w-]+)` \|", routing, re.M)
    assert sorted(rows) == sorted(AGENT_MAP), rows  # exactly one row per agent
    for needle in ("omitClaudeMd", "maxTurns", "autoCompactWindow", "## Plan tiers", "## ECC equivalents"):
        assert needle in text, needle
    tier_header = next((ln for ln in text.splitlines() if ln.startswith("|") and "max20" in ln and "pro" in ln), "")
    assert "max5 / api" in tier_header, tier_header
    ecc = text.split("## ECC equivalents", 1)[1]
    for name in ("architect", "planner", "doc-updater", "e2e-runner", "refactor-cleaner",
                 "security-reviewer", "tdd-guide", "code-reviewer", "build-error-resolver"):
        assert re.search(rf"^\| `?{re.escape(name)}`?[ (|]", ecc, re.M), name
    assert "17 specialists + `team-lead`" not in text
    assert "`memory: user`" not in text
