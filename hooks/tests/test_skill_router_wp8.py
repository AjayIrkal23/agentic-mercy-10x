"""skill_router (fullstack reminder's selector) rule hygiene — audit 2026-10-05 NEW-07.

Broad path rules (`server/`, `/components/`, `.tsx`) sat before the specific and
default rules, so every generic server file got the user-invoked tech-debt-audit
as MUST-READ, every component the landing-page design-taste-frontend, and App.tsx
code-review-and-quality. Runnable: `python3 -m pytest hooks/tests/test_skill_router_wp8.py -q`.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

import skill_router as R   # noqa: E402

REPO = "/repo/app/"
INDEX = json.loads((HOOKS / "skills-index.json").read_text(encoding="utf-8"))["skills"]
CFG = json.loads((HOOKS / "skill_router.config.json").read_text(encoding="utf-8"))


def _primary(fp: str, surface: str) -> list:
    return [e["name"] for e in R.select_skills(REPO + fp, surface, is_first_write=True)
            if e["priority"] != "CROSS-CUT"]


def _user_only(name: str) -> bool:
    meta = INDEX.get(name) or {}
    text = f"{meta.get('description', '')} {meta.get('when_to_use', '')}".lower()
    return bool(meta.get("hidden")) or "user-invoked" in text or "does not auto-fire" in text


@pytest.mark.parametrize("fp", ["server/src/index.ts", "server/src/jobs/cleanup.job.ts",
                                "internal/store/db.go"])
def test_generic_server_file_gets_the_backend_baseline_first(fp):
    picks = _primary(fp, "backend")
    assert picks[0] in ("backend-standards-always-follow", "golang-patterns"), picks
    assert "tech-debt-audit" not in picks and "code-review-and-quality" not in picks


def test_errors_module_gets_error_handling_not_debugging():
    picks = _primary("server/src/utils/errors.ts", "backend")
    assert picks[0] == "backend-error-handling" and "debug-investigation" not in picks, picks


@pytest.mark.parametrize("fp", ["src/components/Home/StatCard.tsx", "src/pages/Index.tsx",
                                "src/App.tsx"])
def test_component_write_gets_the_frontend_baseline_first(fp):
    picks = _primary(fp, "frontend")
    assert picks[0] == "frontend-standards-always-follow", picks
    assert "design-taste-frontend" not in picks and "code-review-and-quality" not in picks


def test_no_rule_names_a_user_invoked_skill():
    bad = [(r.get("id"), s) for key in ("frontend_rules", "backend_rules")
           for r in CFG.get(key, []) for s in r.get("skills", []) if _user_only(s)]
    assert bad == []


def test_hidden_skills_are_never_selected(monkeypatch):
    monkeypatch.setattr(R, "_HIDDEN", frozenset({"backend-standards-always-follow"}))
    assert "backend-standards-always-follow" not in _primary("server/src/a.controller.ts", "backend")
