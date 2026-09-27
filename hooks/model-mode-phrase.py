#!/usr/bin/env python3
"""UserPromptSubmit hook: turn "only fable" / "sonnet only" / etc. into a
PER-PROJECT model-mode automatically — no manual command, no global flag.

The user says a terse mode command in chat and this sets the mode for the CURRENT
git repo only (via lib/model_mode.py), so concurrent sessions on other projects
are untouched. Deterministic (fires regardless of what the agent is doing).

Detection is deliberately conservative: it only fires when the WHOLE prompt is a
short mode command (<=60 chars, full-match), so ordinary prose that happens to
mention "opus"/"fable"/"sonnet" never flips a mode. Fail-open everywhere.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOK_DIR))
try:
    from lib import model_mode as mm
except Exception:  # pragma: no cover - never break a prompt
    mm = None

_M = r"(fable|opus|sonnet)"
_FOR = r"(?:\s+for\s+(?:this\s+)?(?:project|repo|repository|dir|folder|codebase))?"
_MODE = r"(?:\s+mode)?"
_SET = [
    re.compile(rf"^only\s+{_M}{_MODE}{_FOR}$"),
    re.compile(rf"^{_M}\s+only{_MODE}{_FOR}$"),
    re.compile(rf"^(?:use|switch\s+to|set|make\s+it|lock(?:\s+to)?|change\s+to|go|run)"
               rf"\s+(?:only\s+)?{_M}(?:\s+only)?{_MODE}{_FOR}$"),
    re.compile(rf"^(?:all|everything)\s+{_M}{_FOR}$"),
]
_CHEAP = re.compile(rf"^cheap{_MODE}{_FOR}$")  # -> sonnet (legacy alias)
_CLEAR = re.compile(
    rf"^(?:smart(?:\s+routing|\s+model)?|mixed(?:\s+models?)?|auto(?:\s+model)?|"
    rf"normal(?:\s+routing)?|back\s+to\s+normal|clear(?:\s+the)?\s+model(?:\s+mode|\s+lock)?|"
    rf"no\s+model\s+lock|unlock\s+model|reset\s+model(?:\s+mode)?|default\s+model|"
    rf"model\s+smart\s+routing){_FOR}$"
)


def _detect(prompt: str):
    p = re.sub(r"\s+", " ", (prompt or "").strip().lower()).strip(" .!?,")
    if not p or len(p) > 60:  # commands are terse; long prompts are discussion
        return (None, None)
    if _CLEAR.match(p):
        return ("clear", None)
    if _CHEAP.match(p):
        return ("set", "sonnet")
    for rx in _SET:
        m = rx.match(p)
        if m:
            return ("set", m.group(1))
    return (None, None)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("{}")
        return 0
    if not isinstance(payload, dict) or mm is None:
        print("{}")
        return 0
    action, model = _detect(payload.get("prompt") or "")
    if action is None:
        print("{}")
        return 0
    try:
        key = mm.project_key(payload)
        d = mm.STATE / "model-modes"
        d.mkdir(parents=True, exist_ok=True)
        pm = d / key
        if action == "set":
            pm.write_text(model + "\n", encoding="utf-8")
            msg = (f"**{model}-only set for THIS project** (`{key}`). Applies to "
                   f"subagents/workflows here only — other sessions/projects are "
                   f"unaffected. Say “smart routing” to clear.")
        else:
            existed = pm.is_file()
            try:
                pm.unlink()
            except FileNotFoundError:
                pass
            msg = (f"cleared for THIS project (`{key}`) — back to smart routing."
                   if existed else
                   f"already smart routing for THIS project (`{key}`).")
        print(json.dumps({"additionalContext": "[model-mode] " + msg}))
    except Exception:
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
