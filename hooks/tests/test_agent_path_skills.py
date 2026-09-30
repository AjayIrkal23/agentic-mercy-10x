"""Agent `skills:` preload silently skips `paths:`-scoped skills (Claude Code lists them
only after a matching file is read). gen-agent-skill-blocks.py therefore also writes a
body block telling the agent to Read those SKILL.md files before its first task."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]


def _gen():
    spec = importlib.util.spec_from_file_location("gasb", HOOKS / "gen-agent-skill-blocks.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["gasb"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_every_path_scoped_preload_is_named_in_the_agent_body():
    g = _gen()
    scoped = g._path_scoped()
    missing = {}
    for agent, raw in g.AGENT_SKILLS.items():
        text = (g.AGENTS / f"{agent}.md").read_text(encoding="utf-8")
        want = [s for s in g._collapse(raw, g._canon())[:g.MAX_SKILLS] if s in scoped]
        gone = [s for s in want if f"skills/{s}/SKILL.md" not in text]
        if gone:
            missing[agent] = gone
    assert not missing, missing


def test_path_block_is_idempotent_and_removable():
    g = _gen()
    body = "\nYou are an agent.\n"
    once = g._with_path_block(body, ["backend-api-standards"])
    assert "skills/backend-api-standards/SKILL.md" in once
    assert g._with_path_block(once, ["backend-api-standards"]) == once
    assert g._with_path_block(once, []) == body
