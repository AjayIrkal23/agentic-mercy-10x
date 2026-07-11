"""invoke_suite.py — S3 delegate for the /invoke suite manifest (P1-T4).

Wraps, in-process, the ORIGINAL hook (no logic copied):
  invoke-suite-manifest.py  main()  -> active /invoke suite context + suite_push

Emits a tier-3 routing item. Id ``suite:manifest`` (additive — no built-in
equivalent). suite_push.py is consumed by invoke-suite-manifest itself.
"""
from __future__ import annotations

from prompt_router.modules import _base as B


def items(payload: dict, ctx: dict) -> list[dict]:
    ac = B.run_stdin_hook("invoke-suite-manifest.py", "main", payload)
    if ac:
        return [B.item("suite:manifest", 3, "ROUTING", ac)]
    return []


__all__ = ["items"]
