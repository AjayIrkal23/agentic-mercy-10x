"""A generic error envelope must defer to the project's own contract (audit 2026-10-05 D-02/F-01).

site-sync-vista mandates a flat `{success:false, message, code}`; three skills and
rules/backend.md prescribed a nested `error:{code,message}` with no precedence clause,
so a model following them would "fix" a working contract.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUSE = "project contract wins"
NESTED = re.compile(r'"error"\s*:\s*\{|error:\s*\{\s*code')


def _files():
    yield from sorted((ROOT / "skills").glob("*/SKILL.md"))
    yield ROOT / "rules" / "backend.md"


def test_nested_envelope_prescriptions_defer_to_the_project():
    missing = [str(p.relative_to(ROOT)) for p in _files()
               if NESTED.search(p.read_text(encoding="utf-8"))
               and CLAUSE not in p.read_text(encoding="utf-8").lower()]
    assert not missing, f"add the '{CLAUSE}' clause to: {missing}"
