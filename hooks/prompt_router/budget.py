"""budget.py — S5: priority-ordered ~24k token budget (Charter §1).

The win is DEDUP + SIGNAL QUALITY + priority ordering, NOT raw shrinkage. The
budget is a large per-prompt allowance (default 24,000 tokens). Items carry a
``tier`` (0 = gate-adjacent/critical, 3 = advisory) and an ``est_tokens``.
Emission order is tier-ascending, then original (rank) order within a tier.

HARD invariant: tier-0 items are ALWAYS emitted even if they exceed the budget
(gates and mandatory-trigger directives are never dropped — the char/token caps
are non-binding for critical trigger content). Only tier >= 1 items can be
dropped, and every drop is returned for telemetry logging.

Token estimation: ``len(text) // 4`` (deterministic, stdlib-only). Good enough
for ordering; the budget is deliberately generous.
"""

from __future__ import annotations

DEFAULT_MAX_TOKENS = 24000


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def apply(items: list[dict], max_tokens: int = DEFAULT_MAX_TOKENS) -> tuple[list[dict], list[dict]]:
    """Return (included, dropped). Stable, tier-ordered, tier-0 never dropped.

    Each item may pre-set ``est_tokens``; otherwise it is derived from ``text``.
    """
    # annotate est_tokens + stable original index
    for i, it in enumerate(items):
        it.setdefault("est_tokens", est_tokens(it.get("text", "")))
        it["_ord"] = i

    ordered = sorted(items, key=lambda it: (int(it.get("tier", 3)), it["_ord"]))

    included: list[dict] = []
    dropped: list[dict] = []
    used = 0
    for it in ordered:
        tier = int(it.get("tier", 3))
        cost = int(it.get("est_tokens", 1))
        if tier <= 0:
            included.append(it)   # tier-0: always in, even over budget
            used += cost
            continue
        if used + cost <= max_tokens:
            included.append(it)
            used += cost
        else:
            it["_drop_reason"] = f"budget: used={used} + cost={cost} > max={max_tokens}"
            dropped.append(it)

    for it in included + dropped:
        it.pop("_ord", None)
    return included, dropped


def total_tokens(items: list[dict]) -> int:
    return sum(int(it.get("est_tokens", est_tokens(it.get("text", "")))) for it in items)


__all__ = ["apply", "est_tokens", "total_tokens", "DEFAULT_MAX_TOKENS"]
