"""weights.py — the one loader for skill_router_weights.json (audit C-16, D-05).

Used by the prompt router (select.py) and the write-time router (skill_router.py) so
the two can never disagree again. Learned weights may demote but never boost (their
input is test-polluted and frozen, audit C-01): values clamp to [0.1, 1.0]. Keys that
name no skill in the index (aliases, retired skills) are dropped.
"""

from __future__ import annotations

import json
from pathlib import Path

LOW, HIGH = 0.1, 1.0


def load(path: Path, known=None) -> dict[str, float]:
    """{skill: weight}; ``known`` (a set of skill names) filters dead keys. {} on error."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8")).get("weights") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items() if isinstance(raw, dict) else ():
        if not isinstance(k, str) or isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        if known is not None and k not in known:
            continue
        out[k] = max(LOW, min(HIGH, float(v)))
    return out


__all__ = ["load", "LOW", "HIGH"]
