"""Regrowth guard for the always-on context (docs/TOKEN-BUDGET.md holds the measured numbers).

Honours DIRECTIVES_ROOT like tests/test_directives.py (drafts replace root files before
integrate applies them). Sentinel rule for test_agent_descriptions_under_1200: it skips with
"agents-skills not applied yet (no agent carries maxTurns)" while no agent frontmatter has a
`maxTurns:` line, and is strict as soon as one does (agents-skills owns agents/*.md).
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _td():
    spec = importlib.util.spec_from_file_location("test_directives_cb", _ROOT / "tests" / "test_directives.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


td = _td()
DRAFTS = td._drafts()


def _read(p: Path | None) -> str:
    return p.read_text(encoding="utf-8") if p is not None else ""


def _has_paths(text: str) -> bool:
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---", 4)
    return end > 0 and re.search(r"^paths:", text[4:end], re.M) is not None


def _rules_text() -> int:
    names = {p.name for p in (_ROOT / "rules").glob("*.md")}
    if DRAFTS is not None:
        names |= {p.name[: -len(".draft")] for p in (DRAFTS / "rules").glob("*.md.draft")}
    total = 0
    for n in names:
        t = _read(td.resolve(_ROOT, f"rules/{n}", DRAFTS))
        total += 0 if _has_paths(t) else len(t)
    return total


def _frontmatter(path: Path) -> str:
    m = re.match(r"^---\s*\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S)
    return m.group(1) if m else ""


def _description(fm: str) -> str:
    """The `description:` value, folded continuation lines included."""
    lines = fm.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("description:"):
            parts = [ln[len("description:"):].strip()]
            for nxt in lines[i + 1:]:
                if nxt[:1] in (" ", "\t"):
                    parts.append(nxt.strip())
                else:
                    break
            return " ".join(p for p in parts if p not in ("|", ">", "|-", ">-")).strip().strip('"').strip("'")
    return ""


def _agents() -> list[Path]:
    return [p for p in sorted((_ROOT / "agents").glob("*.md")) if p.stem not in ("README", "team-lead")]


def test_doctrine_under_20k():
    claude = len(_read(td.resolve(_ROOT, "CLAUDE.md", DRAFTS)))
    machines = len(td.machines_text(_ROOT))
    total = claude + machines + _rules_text()
    assert total <= 20000, f"doctrine {total:,} chars (CLAUDE.md {claude:,}, machines {machines:,})"


def test_claude_md_under_4k():
    n = len(_read(td.resolve(_ROOT, "CLAUDE.md", DRAFTS)))
    assert n <= 4000, f"CLAUDE.md {n:,} chars"


def test_aggregator_sample_under_5500():
    sample = td.aggregator_sample(_ROOT)
    if not sample:
        pytest.skip("aggregator produced no sample in this environment")
    assert len(sample) <= 5500


@pytest.mark.parametrize("agent_type", ["implementation-engineer", "qa-verifier"])
def test_subagent_context_under_3000(agent_type):
    script = _ROOT / "hooks" / "subagent-context.py"
    if not script.is_file():
        pytest.skip("hooks/subagent-context.py missing")
    r = subprocess.run([sys.executable, str(script)], capture_output=True, encoding="utf-8", timeout=10,
                       input=json.dumps({"agent_id": "m", "agent_type": agent_type, "cwd": str(_ROOT)}),
                       env={**os.environ, "CLAUDE_HOOK_DOCTOR": "1"})
    data = json.loads(r.stdout or "{}")
    ctx = data.get("additionalContext") or (data.get("hookSpecificOutput") or {}).get("additionalContext") or ""
    assert len(ctx) <= 3000, f"{agent_type}: {len(ctx)} chars"  # B-06: repo ids + one ToolSearch line


def test_agent_descriptions_under_1200():
    agents = _agents()
    if not any(re.search(r"^maxTurns:", _frontmatter(p), re.M) for p in agents):
        pytest.skip("agents-skills not applied yet (no agent carries maxTurns)")
    over = {p.name: len(_description(_frontmatter(p))) for p in agents}
    over = {k: v for k, v in over.items() if v > 1200}
    assert over == {}, over


def test_agent_descriptions_total_under_10000():
    """FIX-r2 T4: `/context` loads every agent description; keep the set under 10k chars, 600 each."""
    sizes = {p.name: len(_description(_frontmatter(p))) for p in _agents()}
    assert sum(sizes.values()) <= 10000, sum(sizes.values())
    assert {k: v for k, v in sizes.items() if v > 600} == {}


def test_manifest_always_load():
    servers = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))["mcp_servers"]
    eager = [s.get("name") for s in servers if s.get("alwaysLoad") is True]
    # 2026-10-31 (owner): tool use over token cost; the mandated MCPs load eagerly, nothing beyond them
    assert set(eager) <= {"sequential-thinking", "jcodemunch", "jdocmunch", "graphify", "memory", "context7",
                          "semgrep", "playwright", "lightpanda"}, eager


def test_library_not_autoloaded():
    lib = _ROOT / "library"
    if not lib.is_dir():
        pytest.skip("library/ absent")
    lib = lib.resolve()
    for d in ("skills", "rules"):
        for entry in (_ROOT / d).iterdir() if (_ROOT / d).is_dir() else []:
            assert lib not in entry.resolve().parents and entry.resolve() != lib, entry
    assert not (lib / "rules").exists()


def test_output_style_bounded():
    p = _ROOT / "output-styles" / "caveman.md"
    text = p.read_text(encoding="utf-8")
    assert len(text) <= 1800, len(text)
    fm = _frontmatter(p)
    assert re.search(r"^name: caveman$", fm, re.M)
    assert re.search(r"^keep-coding-instructions: true$", fm, re.M)


def test_core_skill_set_has_no_full_entry():
    data = json.loads((_ROOT / "hooks" / "core-skill-set.json").read_text(encoding="utf-8"))
    assert [e for e in data["always"] if e.get("mode") == "full"] == []
