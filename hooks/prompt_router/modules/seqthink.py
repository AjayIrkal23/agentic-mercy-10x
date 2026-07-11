"""seqthink.py — S3 delegate for the sequential-thinking mandate (P1-T4).

Wraps, in-process, the ORIGINAL hook (no logic copied):
  sequential-thinking-mandate.py  main()  -> externalize-reasoning directive

Id ``substrate:seqthink`` supersedes the router's built-in reasoning line with
the hook's exact text.
"""
from __future__ import annotations

from prompt_router.modules import _base as B


def items(payload: dict, ctx: dict) -> list[dict]:
    ac = B.run_stdin_hook("sequential-thinking-mandate.py", "main", payload)
    if ac:
        return [B.item("substrate:seqthink", 1, "SUBSTRATE", ac)]
    return []


__all__ = ["items"]
