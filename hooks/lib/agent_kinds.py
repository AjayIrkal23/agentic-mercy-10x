"""Agent types that get special treatment from SubagentStart and the read gates (EGM plan Step 6).

The egm "goldfish" reviewers start deliberately blind (fresh context, no repo rules, no
MCP orientation) and must stay that way; the synthesizer only merges their reports.
Both get a lean SubagentStart block and pass the jcodemunch / jdocmunch read gates.
`egm:egm-bootstrap-orchestrator` is a normal agent and stays out. Explicit sets,
lowercase match, never raise.
"""
from __future__ import annotations

GOLDFISH = frozenset({
    "egm:egm-zoom-out", "egm:egm-comprehension", "egm:egm-design", "egm:egm-structural",
    "egm:egm-style", "egm:egm-implementation-readiness", "egm:egm-codebase-details",
})
EGM_LEAN = GOLDFISH | {"egm:egm-synthesizer"}


def _norm(agent_type) -> str:
    return agent_type.strip().lower() if isinstance(agent_type, str) else ""


def is_goldfish(agent_type) -> bool:
    return _norm(agent_type) in GOLDFISH


def is_egm_lean(agent_type) -> bool:
    return _norm(agent_type) in EGM_LEAN
