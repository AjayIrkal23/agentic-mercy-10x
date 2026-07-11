"""intel.py — S3 delegate for the codebase-intelligence injectors (P1-T4).

Wraps, in-process, the ORIGINAL hooks (no logic copied):
  codebase-intel-router.py  main()                -> jcodemunch/graphify precedence
  jcodemunch-enforce.py      prompt_submit()       -> blind-read gate nudge
  graphify-enforce.py        handle_prompt_submit() -> arch/graph precedence

Item ids match the router's built-in substrate ids so a delegate emission
SUPERSEDES the built-in approximation with the hook's exact text (byte-parity).
"""
from __future__ import annotations

from prompt_router.modules import _base as B


def items(payload: dict, ctx: dict) -> list[dict]:
    out: list[dict] = []
    ac = B.run_stdin_hook("codebase-intel-router.py", "main", payload)
    if ac:
        out.append(B.item("substrate:jcodemunch", 1, "SUBSTRATE", ac))
    ac = B.run_stdin_hook("graphify-enforce.py", "handle_prompt_submit", payload)
    if ac:
        out.append(B.item("substrate:graphify", 1, "SUBSTRATE", ac))
    ac = B.run_stdin_hook("jcodemunch-enforce.py", "prompt_submit", payload)
    if ac:
        out.append(B.item("gate:jcm-enforce", 1, "SUBSTRATE", ac))
    return out


__all__ = ["items"]
