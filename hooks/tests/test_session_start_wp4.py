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
    for k in ("MERCY_MOD_SESSION", "MERCY_MOD_LOADED"):
        monkeypatch.delenv(k, raising=False)
    (tmp_path / "home" / ".claude").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "home" / ".claude"))
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "pstate"))
    return mod


def _run(mod, payload: dict, monkeypatch, raw: list | None = None) -> str:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    if raw is not None:
        raw.append(buf.getvalue())
    return json.loads(buf.getvalue()).get("additionalContext", "")


def _no_hooks(agg, monkeypatch, tmp_path, out: str = "") -> None:
    monkeypatch.setattr(agg, "INDEX_LIFECYCLE", tmp_path / "x.py")
    (tmp_path / "x.py").write_text("")
    monkeypatch.setattr(agg, "TDD_INIT_GUARD", tmp_path / "missing.py")
    monkeypatch.setattr(agg, "_run_hook_subprocess", lambda *a: out)


def _longest_run(text: str, ch: str) -> int:
    text = re.sub(r"…\(\w+ trimmed\)", "", text)  # the markers' own letters do not count
    runs = re.findall(re.escape(ch) + "+", text)
    return max((len(r) for r in runs), default=0)


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


def test_hook_output_is_clipped_to_the_index_cap(agg, monkeypatch, tmp_path):
    _no_hooks(agg, monkeypatch, tmp_path, "i" * 4000)
    ctx = _run(agg, {"cwd": str(tmp_path), "source": "startup"}, monkeypatch)
    assert "i" * agg.CAPS["index"] + "…(index trimmed)" in ctx
    assert "i" * 4000 not in ctx
    assert len(ctx) <= agg.MAX_AGGREGATED_CHARS
    assert "[Always-active core skills]" in ctx


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


# --------------------------------------------------------------------------- style block
def test_style_block_present_once_and_moved_from_the_ponytail_guard(agg, monkeypatch, tmp_path):
    """The directive assertion formerly carried by ponytail-caveman-guard.py (integrate deletes it)."""
    _no_hooks(agg, monkeypatch, tmp_path)
    ctx = _run(agg, {"cwd": str(tmp_path), "source": "startup"}, monkeypatch)
    assert ctx.count("ALWAYS-ON STYLE") == 1
    for key in ("ponytail", "caveman", "no-ai-slop", "smallest complete change",
                "full technical accuracy", "every response"):
        assert key in ctx, key
    assert len(agg.STYLE_DIRECTIVE) <= agg.CAPS["style"]
    assert "—" not in agg.STYLE_DIRECTIVE


@pytest.mark.parametrize("style,dropped", [("caveman", True), ("default", False), (None, False)])
def test_style_block_drops_only_the_caveman_sentence_under_the_caveman_output_style(
        agg, monkeypatch, tmp_path, style, dropped):
    _no_hooks(agg, monkeypatch, tmp_path)
    if style is not None:
        (tmp_path / "home" / ".claude" / "settings.json").write_text(
            json.dumps({"outputStyle": style}), encoding="utf-8")
    ctx = _run(agg, {"cwd": str(tmp_path), "source": "startup"}, monkeypatch)
    assert "ALWAYS-ON STYLE" in ctx and "ponytail" in ctx and "no-ai-slop" in ctx
    assert (agg.STYLE_CAVEMAN not in ctx) is dropped


# --------------------------------------------------------------------------- caps
def test_each_source_respects_its_cap(agg, monkeypatch, tmp_path):
    _no_hooks(agg, monkeypatch, tmp_path, "i" * 2000)
    monkeypatch.setattr(agg, "_session_notices", lambda cwd="": "n" * 2000)
    monkeypatch.setattr(agg, "_superpowers_session_context", lambda: "s" * 2000)
    monkeypatch.setattr(agg, "_configured_mcp_context", lambda: "m" * 2000)
    raw: list = []
    ctx = _run(agg, {"cwd": str(tmp_path), "source": "startup"}, monkeypatch, raw)
    assert _longest_run(ctx, "n") <= agg.CAPS["notices"]
    assert _longest_run(ctx, "i") <= agg.CAPS["index"]
    tail = ctx.split(agg.SEP)[-1]
    assert _longest_run(tail, "s") + _longest_run(tail, "m") <= agg.CAPS["mcp"]
    core = ctx[ctx.index("[Always-active"):].split(agg.SEP)[0]
    assert len(core) <= agg.CAPS["core"]
    assert len(ctx) <= 5500
    assert len(json.dumps({"additionalContext": ctx})) <= 5500
    assert len(raw[0].encode("utf-8")) <= 5500


def test_memwatch_and_worktree_and_instinct_notices_arrive_through_getattr(agg, monkeypatch, tmp_path):
    _no_hooks(agg, monkeypatch, tmp_path)
    mod = agg._notices_module()
    oom = "OOM guard since last session: 1 kill (node 3.9 GB, kernel)"
    wt = "worktrees: 3 (1 dirty, 1 predicted conflict with main: feat-x)"
    inst = "instinct: run pytest -p no:cacheprovider here (0.8)"
    monkeypatch.setattr(mod, "memwatch_line", lambda: oom)
    monkeypatch.setattr(mod, "worktree_line", lambda cwd=None: wt)
    monkeypatch.setattr(mod, "instinct_lines", lambda cwd=None: [inst])
    ctx = _run(agg, {"cwd": str(tmp_path), "source": "startup"}, monkeypatch)
    assert oom in ctx and wt in ctx and inst in ctx

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(mod, "memwatch_line", boom)
    ctx = _run(agg, {"cwd": str(tmp_path), "source": "startup"}, monkeypatch)
    assert oom not in ctx and wt in ctx and inst in ctx
    monkeypatch.setattr(mod, "memwatch_line", lambda: oom)
    monkeypatch.delattr(mod, "worktree_line")
    ctx = _run(agg, {"cwd": str(tmp_path), "source": "startup"}, monkeypatch)
    assert oom in ctx and wt not in ctx and inst in ctx


def test_notices_block_is_clipped_on_whole_lines(agg):
    lines = [f"{i:02d}" + "x" * 88 for i in range(12)]
    block = agg._clip("\n".join(lines), agg.CAPS["notices"], "notices")
    assert len(block) <= 600
    kept = block.splitlines()
    for ln in kept[:-1]:
        assert ln in lines
    assert kept[-1] in lines or kept[-1] == "…(notices trimmed)"


def test_breadcrumb_survives_the_stale_sweep(agg, monkeypatch, tmp_path):
    import os
    import time
    _no_hooks(agg, monkeypatch, tmp_path)
    state = tmp_path / "state"
    old = time.time() - 3 * 86400

    def seed():
        state.mkdir(exist_ok=True)
        for name in ("abc.breadcrumb.json", "x.json", "unknown.y.json"):
            (state / name).write_text("{}", encoding="utf-8")
            os.utime(state / name, (old, old))

    seed()
    _run(agg, {"cwd": str(tmp_path), "source": "startup"}, monkeypatch)
    assert (state / "abc.breadcrumb.json").exists()
    assert not (state / "x.json").exists() and not (state / "unknown.y.json").exists()
    seed()
    _run(agg, {"cwd": str(tmp_path), "source": "resume"}, monkeypatch)
    assert all((state / n).exists() for n in ("abc.breadcrumb.json", "x.json", "unknown.y.json"))


def test_doctor_run_skips_subprocesses_worktree_and_stays_under_the_acceptance_byte_count(
        agg, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    calls: list = []

    def spawned(*a, **k):
        calls.append("hook")
        raise AssertionError("no subprocess under doctor")

    def worktree(cwd=None):
        calls.append("worktree")
        raise AssertionError("no git under doctor")
    monkeypatch.setattr(agg, "_run_hook_subprocess", spawned)
    monkeypatch.setattr(agg._notices_module(), "worktree_line", worktree)
    raw: list = []
    ctx = _run(agg, {"session_id": "t", "source": "startup", "cwd": "/tmp"}, monkeypatch, raw)
    assert calls == []
    assert len(raw[0].encode("utf-8")) <= 5500
    assert "ALWAYS-ON STYLE" in ctx and "[Always-active core skills]" in ctx
