"""uiux.py — S3 delegate for the UI/UX stack orchestrator (P1-T4).

Wraps, in-process, the ORIGINAL hook's payload-taking function (no logic copied):
  ui-ux-stack-orchestrator.py  handle_before_submit(payload, cfg)

This is the one legacy injector that already takes a payload, so the delegate
calls it directly and extracts additionalContext. NO ui_keyword is pruned; the
orchestrator's own gating decides emission. Id ``route:ui`` supersedes the
router's built-in lightweight UI line with the orchestrator's exact output.
"""
from __future__ import annotations

from prompt_router.modules import _base as B


def items(payload: dict, ctx: dict) -> list[dict]:
    ac = B.call_payload_fn("ui-ux-stack-orchestrator.py", "handle_before_submit",
                           payload, cfg_loader="_load_config")
    if ac:
        return [B.item("route:ui", 2, "ROUTING", ac)]
    return []


__all__ = ["items"]
