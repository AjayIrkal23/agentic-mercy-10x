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
    # dispatch truncates at budgets.chars (7,800), so length alone always passes. The
    # style directive merges last (priority 2): if it survives, nothing was cut.
    assert "ALWAYS-ON STYLE" in ctx, ctx[-300:]
    assert len(ctx) < 7800, len(ctx)


def test_new_lines_fit(monkeypatch, tmp_path):
    """OOM-guard, worktree and instinct notices (oom-sentinel, session-stop, learning) are clipped by
    CAPS['notices'] and never push the style block out of the cap."""
    agg = _load_aggregator()
    sn = agg._notices_module()
    monkeypatch.setattr(sn, "memwatch_line", lambda *a, **k: "M" * 300, raising=False)
    monkeypatch.setattr(sn, "worktree_line", lambda *a, **k: "W" * 200, raising=False)
    monkeypatch.setattr(sn, "instinct_lines", lambda *a, **k: ["I" * 90] * 3, raising=False)
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    payload = {"hook_event_name": "SessionStart", "session_id": "budget-new-lines", "source": "startup",
               "cwd": str(tmp_path)}
    ctx = agg._full_context(payload, json.dumps(payload))
    assert "M" * 50 in ctx                     # the stubs reached the notices block
    assert "ALWAYS-ON STYLE" in ctx
    assert len(ctx) <= 5500          # room for the 1,500-char breadcrumb + memory line under 7,800 (dispatch merges them)
