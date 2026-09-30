"""SessionStart must fit Claude Code's per-hook additionalContext cap.

Claude Code persists any hook's additionalContext over 8,000 characters to a file and
shows the model only a ~2 KB preview, so an oversized SessionStart loses the core
skills, the memory directive and the breadcrumb. dispatch.py merges every
session-start link into ONE hook output, so the merged text is what must fit."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
ROOT = HOOKS.parent
CC_CONTEXT_CAP = 8000


def _load_aggregator():
    spec = importlib.util.spec_from_file_location("ssa", HOOKS / "session-start-aggregator.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_every_dispatch_char_budget_fits_the_cap():
    budgets = json.loads((HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))["budgets"]
    over = {ev: b["chars"] for ev, b in budgets.items() if b.get("chars", 0) >= CC_CONTEXT_CAP}
    assert not over, over


def test_dispatched_session_start_fits_the_cap():
    fixture = (ROOT / "tests" / "fixtures" / "hook-events" / "session-start.json").read_text(encoding="utf-8")
    env = dict(os.environ, CLAUDE_HOOK_DOCTOR="1")
    cp = subprocess.run([sys.executable, str(HOOKS / "dispatch.py"), "session-start"], input=fixture,
                        capture_output=True, text=True, timeout=120, env=env)
    ctx = (json.loads(cp.stdout or "{}").get("hookSpecificOutput") or {}).get("additionalContext", "")
    assert len(ctx) < CC_CONTEXT_CAP, len(ctx)


def test_core_skills_degrade_to_pointers_and_keep_every_name():
    agg = _load_aggregator()
    names = [e["skill"] for e in json.loads((HOOKS / "core-skill-set.json").read_text(encoding="utf-8"))["always"]]
    block = agg._core_skill_digests(budget=1500)
    assert len(block) <= 1500
    assert all(agg._canonical(n) in block for n in names)


def test_core_skills_use_full_bodies_when_they_fit():
    agg = _load_aggregator()
    roomy = agg._core_skill_digests(budget=200000)
    tight = agg._core_skill_digests(budget=1500)
    assert len(roomy) > len(tight)
