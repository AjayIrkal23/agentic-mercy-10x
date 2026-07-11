"""guards.py — S3 delegate for the TDD + dox prompt-mode guards (P1-T4).

Wraps, in-process, the ORIGINAL hooks (no logic copied):
  tdd-guard-init-guard.py  run_prompt()  -> TDD auto-init / advisory
  dox-tree-guard.py        run_prompt()  -> dox root bootstrap / read-first nudge

Both are fail-open advisories (never gates). Ids match the router's built-in
tier-0 gate ids so the hook's exact text supersedes the approximation.
"""
from __future__ import annotations

from prompt_router.modules import _base as B


def items(payload: dict, ctx: dict) -> list[dict]:
    out: list[dict] = []
    ac = B.run_stdin_hook("tdd-guard-init-guard.py", "run_prompt", payload)
    if ac:
        out.append(B.item("gate:tdd", 0, "GATES", ac))
    ac = B.run_stdin_hook("dox-tree-guard.py", "run_prompt", payload)
    if ac:
        out.append(B.item("gate:dox", 0, "GATES", ac))
    return out


__all__ = ["items"]
