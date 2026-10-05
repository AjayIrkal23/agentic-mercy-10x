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
    for text in ("x " * 4000, "x " * 4000 + " api"):
        t0 = time.perf_counter()
        rx.search(text)
        assert time.perf_counter() - t0 < 0.2


@pytest.mark.parametrize("prompt", [
    "stack markers present (package.json, prisma/, go.mod) plus the test commands",
    "how do i make this page go faster",
    "add a component using the shadcn Badge in the header",
])
def test_stack_nouns_and_go_do_not_route(prompt):
    assert not _route("context7").search(prompt)
