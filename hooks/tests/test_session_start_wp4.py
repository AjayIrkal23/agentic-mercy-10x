"""WP4 (audit 2026-10-05): session-start-aggregator.py.

B2-07  the core-skill bodies no longer depend on how much the other session-start
       parts printed: the same bodies arrive whatever the hook output, and overflow
       drops the harness-duplicate tail blocks first, then degrades to pointers.
NEW-03 resume / compact add nothing (the transcript, or session-lifecycle's handoff,
       already carries it).
"""
from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]


@pytest.fixture
def agg(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("ssa_wp4b", _HOOKS / "session-start-aggregator.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    return mod


def _run(mod, payload: dict, monkeypatch) -> str:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    return json.loads(buf.getvalue()).get("additionalContext", "")


def _bodies(ctx: str) -> list:
    return re.findall(r"^### skill: (\S+)", ctx, re.M)


def test_core_bodies_do_not_depend_on_hook_output(agg, monkeypatch, tmp_path):
    monkeypatch.setattr(agg, "INDEX_LIFECYCLE", tmp_path / "x.py")
    (tmp_path / "x.py").write_text("")
    monkeypatch.setattr(agg, "TDD_INIT_GUARD", tmp_path / "missing.py")
    seen = []
    for n in (0, 300, 700):
        monkeypatch.setattr(agg, "_run_hook_subprocess", lambda *a, n=n: "i" * n)
        ctx = _run(agg, {"cwd": str(tmp_path), "source": "startup"}, monkeypatch)
        assert len(ctx) <= agg.MAX_AGGREGATED_CHARS
        seen.append(_bodies(ctx))
    assert seen[0] == seen[1] == seen[2], seen


def test_overflow_drops_tail_then_degrades_to_pointers(agg, monkeypatch, tmp_path):
    monkeypatch.setattr(agg, "INDEX_LIFECYCLE", tmp_path / "x.py")
    (tmp_path / "x.py").write_text("")
    monkeypatch.setattr(agg, "TDD_INIT_GUARD", tmp_path / "missing.py")
    monkeypatch.setattr(agg, "_run_hook_subprocess", lambda *a: "i" * 4000)
    ctx = _run(agg, {"cwd": str(tmp_path), "source": "startup"}, monkeypatch)
    assert len(ctx) <= agg.MAX_AGGREGATED_CHARS
    assert ctx.startswith("i" * 4000)          # the hook status is never trimmed away
    assert "[Always-active core skills]" in ctx and not _bodies(ctx)
    assert "### Superpowers plugin" not in ctx


@pytest.mark.parametrize("source", ["resume", "compact"])
def test_resume_and_compact_print_nothing(agg, monkeypatch, source):
    assert _run(agg, {"session_id": "s", "source": source}, monkeypatch) == ""


def test_memory_block_is_not_repeated_on_resume(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("mlos_wp4", _HOOKS / "memory-load-on-start.py")
    mem = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mem)
    store = tmp_path / "memory.jsonl"
    store.write_text(json.dumps({"type": "entity", "name": "fragile::proj::x", "entityType": "fragile_area",
                                 "observations": ["[2026-10-04] keep"]}) + "\n", encoding="utf-8")
    monkeypatch.setattr(mem, "memory_path", lambda: store)
    (tmp_path / "proj").mkdir()

    def run(source: str) -> str:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cwd": str(tmp_path / "proj"),
                                                                  "source": source})))
        buf = io.StringIO()
        with redirect_stdout(buf):
            mem.main()
        return buf.getvalue()

    assert "fragile::proj::x" in run("startup")
    assert json.loads(run("resume")) == {}
