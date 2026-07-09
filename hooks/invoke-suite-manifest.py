#!/usr/bin/env python3
"""UserPromptSubmit hook: when the prompt fires a /invoke-* suite command, record the
exact skills it demands so the Stop gate (invoke-suite-gate.py) can verify they all
loaded via the Skill tool.

/invoke-* commands are slash-command bodies (not a hook), so nothing else captures
their expected set — this hook reads the command file(s) named in the prompt and
pushes their skill slugs to the shared sidecar with enforce=hard.

stdin:  UserPromptSubmit JSON payload
stdout: {} (pure side effect)
exit:   always 0 (fail open)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
COMMANDS_DIR = Path.home() / ".claude" / "commands"
SKILL_ROOT = Path.home() / ".claude" / "skills"

sys.path.insert(0, str(HOOK_DIR))
try:
    import suite_push
except Exception:
    suite_push = None

# a slash-command invocation in the prompt: /invoke-audit-spec-plan
_CMD = re.compile(r"(?:^|\s)/(invoke-[a-z-]+)\b")
# backtick skill bullet inside a command body:  - `frontend-api-standards`  /  `superpowers:x`
_BACKTICK = re.compile(r"`([a-z0-9](?:[a-z0-9_:-]*[a-z0-9])?)`")


def _looks_like_skill(tok: str) -> bool:
    if "/" in tok or "." in tok:
        return False
    return ("-" in tok or ":" in tok) or (SKILL_ROOT / tok / "SKILL.md").is_file()


def _skills_from_command(name: str) -> list[str]:
    f = COMMANDS_DIR / f"{name}.md"
    if not f.is_file():
        return []
    out: list[str] = []
    for m in _BACKTICK.finditer(f.read_text(encoding="utf-8")):
        if _looks_like_skill(m.group(1)):
            out.append(m.group(1))
    return out


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.stdout.write("{}\n"); return 0

    cid = (payload.get("conversation_id") or payload.get("session_id") or "").strip()
    prompt = payload.get("prompt") or payload.get("user_prompt") or ""
    if not isinstance(prompt, str):
        prompt = str(prompt)
    if not cid or not suite_push:
        sys.stdout.write("{}\n"); return 0

    skills: list[str] = []
    for m in _CMD.finditer(prompt):
        skills.extend(_skills_from_command(m.group(1)))

    if skills:
        suite_push.push(cid, skills, source="invoke-cmd", enforce="hard")
    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write("{}\n")
        sys.exit(0)
