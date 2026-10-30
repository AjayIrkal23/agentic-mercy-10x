"""MCP route regexes in tool-intelligence.json (audit 2026-10-05 C-08).

The context7 route fired on any library noun (a `prisma/` stack marker in a long spec
pushed "Library API question (prisma)") and on the word "go" ("make this page go
faster"). A library token now needs an API-question cue and must not be a path.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]


def _route(rid: str) -> re.Pattern:
    data = json.loads((HOOKS / "tool-intelligence.json").read_text(encoding="utf-8"))
    found = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("id") == rid:
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    return re.compile(found[0]["when"]["regex"])


@pytest.mark.parametrize("prompt", [
    "how do I use zod refine for a password confirm field?",
    "what is the fastify api for onRequest hooks",
    "upgrade to tailwind v4 config syntax",
    "show me a vitest example for mocking timers",
])
def test_library_api_questions_route(prompt):
    assert _route("context7").search(prompt)


def test_long_single_line_stays_linear():
    """santa-diff S3: an unanchored lookahead made the route O(L^2); a pasted 8k-char
    log line took 1.2-3.9 s (20k: past the 15 s UserPromptSubmit timeout)."""
    import time
    rx = _route("context7")

    def best(text, runs=3):
        out = float("inf")
        for _ in range(runs):
            t0 = time.perf_counter()
            rx.search(text)
            out = min(out, time.perf_counter() - t0)
        return out

    # Scaling, not a wall-clock budget (A7-07): 4x the input must cost about 4x (linear), never 16x
    # (quadratic). Both sizes are timed here and now, so box load cancels; the slack absorbs
    # scheduler noise on the millisecond-scale linear timings.
    for tail in ("", " api"):
        small = best("x " * 4000 + tail)
        big = best("x " * 16000 + tail)
        assert big < 8 * small + 0.05, f"route regex scales badly: 8k={small:.4f}s 32k={big:.4f}s"


@pytest.mark.parametrize("prompt", [
    "stack markers present (package.json, prisma/, go.mod) plus the test commands",
    "how do i make this page go faster",
    "add a component using the shadcn Badge in the header",
])
def test_stack_nouns_and_go_do_not_route(prompt):
    assert not _route("context7").search(prompt)


def test_dead_sections_are_gone_and_higgsfield_names_the_connector():
    data = json.loads((HOOKS / "tool-intelligence.json").read_text(encoding="utf-8"))
    assert not ({"engines", "cross_cutting", "handoff_pipeline"} & set(data))
    assert "mirror" not in data["_meta"] and "rules/references/tool-intelligence.md" not in json.dumps(data)
    hf = next(r for r in data["mcp_routes"] if r["id"] == "higgsfield")
    assert hf["server"] == ["claude_ai_higgsfield", "higgsfield"]
    assert "mcp__claude_ai_higgsfield__" in hf["text_by_server"]["claude_ai_higgsfield"]
    assert data.get("connectors") == ["claude_ai_higgsfield"]


def test_consumers_named_in_meta_exist():
    data = json.loads((HOOKS / "tool-intelligence.json").read_text(encoding="utf-8"))
    for ref in data["_meta"]["consumed_by"]:
        assert (HOOKS.parent / ref.split(" ", 1)[0]).exists(), ref


def test_browser_route_needs_intent_and_phrase():
    data = json.loads((HOOKS / "tool-intelligence.json").read_text(encoding="utf-8"))
    br = next(r for r in data["mcp_routes"] if r["id"] == "browser")
    assert br["when"].get("all") is True
    assert not _route("browser").search("it should be visually properly understanding")


def test_dev_server_port_is_repo_scoped(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(HOOKS))
    from prompt_router.modules import mcp_routes as M
    root = tmp_path / "repo"
    (root / "web").mkdir(parents=True)
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setattr(M, "_listeners", lambda: [(8080, 1)])
    try:
        M.dev_server_port.cache_clear()
        assert M.dev_server_port(None) is None
        monkeypatch.setattr(M, "_pid_cwd", lambda pid: str(other))
        M.dev_server_port.cache_clear()
        assert M.dev_server_port(str(root)) is None
        monkeypatch.setattr(M, "_pid_cwd", lambda pid: str(root / "web"))
        M.dev_server_port.cache_clear()
        assert M.dev_server_port(str(root)) == 8080
    finally:
        M.dev_server_port.cache_clear()
