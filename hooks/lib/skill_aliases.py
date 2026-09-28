"""skill_aliases — runtime alias -> canonical resolution for skill names.

Single consumer of ``hooks/skill-aliases.json``. Alias stub skill directories no
longer exist on disk; any old name (``tdd``, ``diagnose``, ``zoom-out`` ...) is
resolved here by every hook that emits or ranks skill names.

Pure stdlib. Never raises: a missing/corrupt map degrades to identity.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

_ALIASES_PATH = Path(__file__).resolve().parents[1] / "skill-aliases.json"


@lru_cache(maxsize=1)
def load() -> dict[str, str]:
    """alias -> canonical (``_``-prefixed meta keys dropped)."""
    try:
        data = json.loads(_ALIASES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items()
            if isinstance(k, str) and not k.startswith("_") and isinstance(v, str)}


def canonical(name: str) -> str:
    """Resolve an alias (transitively, cycle-safe) to its canonical skill name."""
    aliases = load()
    seen: set[str] = set()
    cur = name
    while cur in aliases and cur not in seen:
        seen.add(cur)
        cur = aliases[cur]
    return cur


def collapse(names: Iterable[str]) -> list[str]:
    """Canonicalize and dedupe, preserving first-seen order."""
    return list(dict.fromkeys(canonical(n) for n in names if isinstance(n, str) and n))


if __name__ == "__main__":  # self-check
    assert canonical("tdd") == "test-driven-development"
    assert canonical("not-an-alias") == "not-an-alias"
    assert collapse(["tdd", "test-driven-development", "zoom-out", "codebase-intel-first"]) == [
        "test-driven-development", "codebase-intel-first"]
    print(f"skill_aliases OK ({len(load())} aliases)")
