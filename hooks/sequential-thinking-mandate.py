#!/usr/bin/env python3
"""UserPromptSubmit: mandate mcp__sequential-thinking__sequentialthinking for any
reasoning/planning/spec/audit/design/debug/decision-shaped prompt.

Strict by default: FIRES unless the prompt is clearly trivial (greeting, tiny
single-fact lookup). Injection is the realistic enforcement ceiling for thinking
turns — a PreToolUse deny-gate can't catch a pure-text reasoning turn that calls
no tool, so we inject a hard directive into context instead.

# ponytail: context-injection nudge, not a deny-gate. Upgrade to a PreToolUse gate
# on Edit/Write/ExitPlanMode-until-sequentialthinking only if the nudge proves weak.
"""
from __future__ import annotations

import json
import re
import sys

TOOL = "mcp__sequential-thinking__sequentialthinking"

# Trivial turns where forced step-thinking is pure overhead — the only skips.
_SKIP = re.compile(
    r"^\s*(hi|hey|hello|thanks|thank you|ok|okay|yes|no|yep|nope|cool|nice|"
    r"got it|ls|pwd|/\w+)\b[\s!.?]*$",
    re.IGNORECASE,
)
# Words that guarantee a fire even on a short prompt.
_THINK = re.compile(
    r"\b(plan|spec|specif|audit|design|architect|decide|decision|choose|"
    r"compare|trade.?off|why|should i|approach|strateg|refactor|debug|"
    r"diagnose|root cause|investigat|reason|think|analyz|evaluat|review|"
    r"break ?down|figure out|how (do|should|can|to)|options?)\b",
    re.IGNORECASE,
)


def main() -> None:
    raw = sys.stdin.read() or "{}"
    try:
        prompt = (json.loads(raw).get("prompt") or "").strip()
    except (json.JSONDecodeError, AttributeError):
        prompt = ""

    if not prompt:
        return

    trivial = _SKIP.match(prompt) is not None
    forced = _THINK.search(prompt) is not None
    # Fire when: a thinking word is present, OR the prompt is substantive
    # (>60 chars) and not a trivial one-liner.
    if not forced and (trivial or len(prompt) <= 60):
        return

    msg = (
        "### MANDATE — sequential-thinking (strict, this turn)\n\n"
        f"This prompt requires reasoning. You **MUST** call `{TOOL}` to externalize "
        "your thinking BEFORE you decide, plan, spec, audit, design, debug, or answer.\n\n"
        "- Use it to decompose the problem, weigh options, and surface assumptions — "
        "one thought per step, branch/revise as needed.\n"
        "- This is a standing user directive for **all reasoning, planning, spec, "
        "audit, and design work** (see `~/.claude/rules/sequential-thinking-doctrine.md`).\n"
        "- Skip ONLY for a truly trivial one-line factual reply.\n"
    )
    print(json.dumps({"additionalContext": msg}))


if __name__ == "__main__":
    main()
