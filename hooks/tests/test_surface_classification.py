#!/usr/bin/env python3
"""Surface classification regression suite (2026-07-19, Phase 1).

WHY THIS EXISTS
---------------
`fullstack-skills-reminder.config.json` used to hardcode ONE project's layout
(`["UDP_PLATFORM/client", "client/"]`) and substring-match it against both the
path AND the serialized tool_input blob. Two failures resulted, both silent:

  1. A write to `src/components/Hero.tsx` (Vite) or `app/page.tsx` (Next app
     router) classified as NOTHING -> the entire 37-skill frontend mandatory
     system, the first-write gate, and the fullstack-start block all went dark
     on any project not named `client/`.
  2. A write to a markdown PLAN file whose *text* contained the string
     "client/" classified as a FRONTEND write.

Both were invisible — no warning, no telemetry. This suite exists so that
never recurs. If you change `_classify`/`_surface_of_path`, these must pass.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location(
        "fsr", HOOKS / "fullstack-skills-reminder.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["fsr"] = m
    spec.loader.exec_module(m)
    return m


FSR = _mod()
# The shipped config segments, so tests exercise the real override path too.
# _load_config() -> (frontend_segments, backend_segments, documentation_segments)
FE_SEGS, BE_SEGS, _DOC_SEGS = FSR._load_config()


def classify(file_path: str):
    """-> (frontend: bool, backend: bool) for a Write to file_path."""
    return FSR._classify({"file_path": file_path}, [], FE_SEGS, BE_SEGS)


# --- frontend layouts that MUST fire ----------------------------------------

@pytest.mark.parametrize("path", [
    # Vite / CRA
    "/repo/src/components/Hero.tsx",
    "/repo/src/components/ui/Button.tsx",
    "/repo/src/App.jsx",
    "/repo/src/styles/globals.css",
    # Next.js app router
    "/repo/app/page.tsx",
    "/repo/app/(marketing)/pricing/page.tsx",
    "/repo/app/layout.tsx",
    # Next.js pages router
    "/repo/pages/index.tsx",
    # SvelteKit / Vue / Astro
    "/repo/src/routes/+page.svelte",
    "/repo/src/components/Card.vue",
    "/repo/src/pages/index.astro",
    # monorepo variants
    "/repo/apps/web/src/components/Nav.tsx",
    "/repo/packages/ui/src/Button.tsx",
    # the original hardcoded layout must KEEP working
    "/repo/client/src/components/Hero.tsx",
    "/repo/UDP_PLATFORM/client/src/App.tsx",
    # stylesheets anywhere
    "/repo/assets/theme.scss",
])
def test_frontend_paths_classify_frontend(path):
    fe, _be = classify(path)
    assert fe, f"{path} must classify as FRONTEND (this is the bug that made the stack inert)"


# --- backend layouts --------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/repo/server/internal/handler/user.go",
    "/repo/cmd/api/main.go",
    "/repo/internal/service/billing.go",
    "/repo/pkg/store/postgres.go",
    "/repo/backend/controllers/auth.go",
    "/repo/UDP_PLATFORM/server/internal/x.go",
])
def test_backend_paths_classify_backend(path):
    _fe, be = classify(path)
    assert be, f"{path} must classify as BACKEND"


# --- the false-positive that fired on a markdown plan -----------------------

def test_markdown_content_mentioning_client_does_not_classify_frontend():
    """A doc whose TEXT contains 'client/' is not a frontend write.

    This exact payload fired the full 37-skill frontend block on a plan file.
    """
    ti = {
        "file_path": "/repo/.claude/plans/plan-design.md",
        "content": "| `client/src/components/Hero.tsx` | full 37-skill block |\n"
                   "server/internal/handler.go is the backend counterpart",
    }
    fe, be = FSR._classify(ti, [], FE_SEGS, BE_SEGS)
    assert not fe, "markdown content mentioning 'client/' must NOT be a frontend write"
    assert not be, "markdown content mentioning 'server/internal/' must NOT be a backend write"


@pytest.mark.parametrize("path", [
    "/repo/README.md",
    "/repo/docs/architecture.md",
    "/repo/.github/workflows/ci.yml",
    "/repo/Makefile",
    "/repo/go.mod",
])
def test_neutral_files_classify_as_neither(path):
    fe, be = classify(path)
    assert not fe and not be, f"{path} should be neither surface"


# --- blob fallback is preserved ONLY when there is no path ------------------

def test_blob_fallback_still_works_when_no_path_present():
    """Tool calls carrying no file path keep the old blob behavior — that case
    was legitimate; matching content *in addition to* a real path was not."""
    fe, _be = FSR._classify({"command": "vite build in client/"}, [], FE_SEGS, BE_SEGS)
    assert fe, "with no path, the blob fallback should still classify"


# --- ambiguous extensions resolve by path token -----------------------------

def test_ambiguous_ts_resolves_by_path_token():
    fe, _ = classify("/repo/src/components/useThing.ts")
    assert fe, ".ts under /components/ should resolve to frontend via path token"


def test_ambiguous_ts_in_backend_path_is_backend():
    _, be = classify("/repo/internal/api/router.ts")
    assert be, ".ts under /internal/ should resolve to backend"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
