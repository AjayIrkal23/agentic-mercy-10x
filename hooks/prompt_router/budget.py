"""budget.py — S5: emission ordering (v3).

The 24k-token priority budget never bound (0 drops in 1,114 live prompts), so the
machinery is gone. Emission size is bounded by construction instead: <= 5 skill
lines, <= 1 deep body (``deep_inject_chars``), <= 5 indexed symbols, <= 3 route
lines, <= 2 gate lines. ``apply`` keeps the one invariant that mattered — items
are emitted tier-ascending (gates first), stable within a tier — and returns an
empty ``dropped`` list so callers keep their shape.
"""

from __future__ import annotations


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def apply(items: list[dict], max_tokens: int | None = None) -> tuple[list[dict], list[dict]]:
    """Return (ordered, dropped=[]). ``max_tokens`` is accepted for API
    compatibility and ignored — nothing is ever dropped here."""
    for i, it in enumerate(items):
        it.setdefault("est_tokens", est_tokens(it.get("text", "")))
        it["_ord"] = i
    ordered = sorted(items, key=lambda it: (int(it.get("tier", 3)), it["_ord"]))
    for it in ordered:
        it.pop("_ord", None)
    return ordered, []


def total_tokens(items: list[dict]) -> int:
    return sum(int(it.get("est_tokens", est_tokens(it.get("text", "")))) for it in items)


__all__ = ["apply", "est_tokens", "total_tokens"]
