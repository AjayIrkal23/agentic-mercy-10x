"""The router must never tell the model to Skill() a path-scoped skill.

Skills with `paths:` frontmatter are conditional: Claude Code lists them only after a
matching file is read, so `Skill("name")` fails with "Unknown skill" until then. For
those the router says to Read the SKILL.md (always works, and the invocation tracker
counts it as loaded)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
INDEX = json.loads((HOOKS / "skills-index.json").read_text(encoding="utf-8"))["skills"]


def _route(prompt: str) -> str:
    payload = {"session_id": f"t-{uuid.uuid4().hex}", "hook_event_name": "UserPromptSubmit",
               "prompt": prompt, "cwd": str(HOOKS.parent)}
    cp = subprocess.run([sys.executable, str(HOOKS / "prompt_router" / "router.py")],
                        input=json.dumps(payload), capture_output=True, text=True, timeout=60)
    return (json.loads(cp.stdout or "{}").get("hookSpecificOutput") or {}).get("additionalContext", "")


def test_path_scoped_skills_are_read_not_invoked():
    body = _route("add a paginated GET /products REST endpoint route handler with input validation")
    invoked = re.findall(r'Skill\("([^"]+)"\)', body)
    scoped = [n for n in invoked if (INDEX.get(n) or {}).get("paths")]
    assert not scoped, f"router pushes path-scoped skills via Skill(): {scoped}"
    assert "backend-api-standards/SKILL.md" in body


def test_listed_skills_still_use_the_skill_tool():
    body = _route("the checkout total is wrong intermittently, find the root cause")
    assert 'Skill("debug-investigation")' in body
