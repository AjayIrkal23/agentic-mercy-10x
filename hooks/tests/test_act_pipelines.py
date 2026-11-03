"""Every /invoke act agent runs a fixed tool pipeline by itself and proves it in its artifact (2026-11-03).

Contract per agent body:
- one ``## <name> pipeline (automatic, every task)`` heading and the line "never hand them to the user";
- a table of at least 3 rows, step ids in order (``P1..Pn``; the designer keeps ``T1..Tn``);
- every row's Call cell holds a backticked call, and every call names something that exists:
  ``mcp__<server>__<tool>`` -> a manifest MCP server, ``Skill("<name>")`` -> a local skill, an
  installed-plugin skill or a harness built-in, ``~/.claude/<path>`` / ``$HOME/.claude/<path>`` -> a file
  in this checkout;
- the ARTIFACT contract names a ``## Pipeline`` section.
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "hooks"
AGENTS = ROOT / "agents"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


gate = _load("pipeline_evidence_gate_t", HOOKS / "pipeline-evidence-gate.py")
ACT_AGENTS = gate.ACT_AGENTS

MANIFEST = json.loads((ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
MCP_SERVERS = {s["name"] for s in MANIFEST["mcp_servers"]}
PLUGINS = {p["id"].split("@", 1)[0] for p in MANIFEST["plugins"]["install"] if isinstance(p, dict)}
BUILTIN_SKILLS = {"security-review", "code-review", "simplify"}

HEAD_RX = re.compile(r"^## [^\n]*pipeline \(automatic, every task\)[ \t]*$", re.M)
STEP_RX = re.compile(r"^([A-Z])(\d+)$")
SPAN_RX = re.compile(r"`([^`]+)`")
MCP_RX = re.compile(r"mcp__([A-Za-z0-9-]+)__([A-Za-z0-9_]+)")
SKILL_RX = re.compile(r'Skill\("([^"]+)"\)')
PATH_RX = re.compile(r"(?:~|\$HOME)/\.claude/([A-Za-z0-9_./-]+)")


def _cells(line: str) -> list[str]:
    """Table cells; a backslash-escaped pipe inside a cell is not a separator."""
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _rows(body: str) -> list[list[str]]:
    m = HEAD_RX.search(body)
    assert m, "no '## ... pipeline (automatic, every task)' heading"
    rows = []
    for line in body[m.end():].splitlines():
        if line.startswith("## "):
            break
        if line.startswith("|"):
            cells = _cells(line)
            if cells and STEP_RX.match(cells[0]):
                rows.append(cells)
    return rows


def _skill_exists(name: str) -> bool:
    if name in BUILTIN_SKILLS:
        return True
    if ":" in name:
        return name.split(":", 1)[0] in PLUGINS
    return (ROOT / "skills" / name / "SKILL.md").is_file()


def test_act_agent_map_matches_the_router():
    cfg = json.loads((HOOKS / "autonomous-skill-router.config.json").read_text(encoding="utf-8"))
    cats = cfg.get("categories", cfg)
    routed = {v["agent"] for v in cats.values() if isinstance(v, dict) and v.get("agent")}
    assert routed <= set(ACT_AGENTS), routed - set(ACT_AGENTS)
    assert all((AGENTS / f"{a}.md").is_file() for a in ACT_AGENTS)


@pytest.mark.parametrize("agent", sorted(ACT_AGENTS))
def test_agent_runs_its_pipeline_itself(agent):
    body = (AGENTS / f"{agent}.md").read_text(encoding="utf-8")
    assert len(HEAD_RX.findall(body)) == 1, "exactly one pipeline heading"
    assert "never hand them to the user" in body
    rows = _rows(body)
    assert len(rows) >= 3, f"{len(rows)} pipeline rows"
    letters = {STEP_RX.match(r[0]).group(1) for r in rows}
    assert len(letters) == 1, letters
    assert [int(STEP_RX.match(r[0]).group(2)) for r in rows] == list(range(1, len(rows) + 1))
    for r in rows:
        assert len(r) == 4, r
        spans = SPAN_RX.findall(r[2])
        assert spans, f"{r[0]}: no backticked call"
        for span in spans:
            for server, _tool in MCP_RX.findall(span):
                assert server in MCP_SERVERS, f"{r[0]}: unknown MCP server {server}"
            for skill in SKILL_RX.findall(span):
                assert _skill_exists(skill), f"{r[0]}: unknown skill {skill}"
            for rel in PATH_RX.findall(span):
                rel = rel.rstrip(".")
                assert (ROOT / rel).exists(), f"{r[0]}: missing ~/.claude/{rel}"
    art = body.split("## ARTIFACT", 1)[-1] if "## ARTIFACT" in body else body
    assert "## Pipeline" in art, "the ARTIFACT contract has no ## Pipeline section"
