"""cues.py — refinements applied to the raw keyword hits (audit 2026-10-05 C-04, C-12).

* Negation: a keyword preceded within 3 words by "no need for/to", "don't", "do not"
  or "without" is not a task word ("no need for a security review" is not SECURITY).
* Phrase intents the flat keyword list cannot express: "write <x> tests" -> TEST.
* LARGE needs a scale phrase; a lone noun ("websocket", "streaming", "sse") is a
  topic, not a size, and used to put "consider /model opus" on small bug fixes.

Plural stemming lives in ``classify.KeywordMatcher`` (an optional s/es suffix).
Pure stdlib; callers wrap it fail-open.
"""

from __future__ import annotations

import re

_NEG = re.compile(r"(?:\bno need (?:for|to)|\bdon[’']?t|\bdo not|\bwithout)(?:\W+\w+){0,3}\W*$")
_PHRASES = {
    "TEST": re.compile(r"\b(?:write|add|create) (?:\w+ ){1,3}?tests?\b"),
}
# Single nouns in the LARGE list: they name a topic, not the size of the change.
LARGE_NOUNS = frozenset({"websocket", "sse", "streaming", "real-time", "microservices",
                         "everything", "everywhere"})


def negated(text: str, start: int) -> bool:
    """True when the 3 words before ``start`` hold a negation phrase."""
    return bool(_NEG.search(text[max(0, start - 60):start]))


def _all_negated(text: str, kw: str) -> bool:
    pat = re.compile(r"(?<!\w)" + re.escape(kw) + r"(?:e?s)?(?!\w)")
    starts = [m.start() for m in pat.finditer(text)]
    return bool(starts) and all(negated(text, s) for s in starts)


def refine(hits: dict[str, list[str]], text: str) -> dict[str, list[str]]:
    """Drop negated act keywords, add phrase intents, demote noun-only LARGE."""
    out: dict[str, list[str]] = {}
    for g, kws in hits.items():
        if g.startswith("act:"):
            kws = [k for k in kws if not _all_negated(text, k)]
        if kws:
            out[g] = list(kws)
    for cat, rx in _PHRASES.items():
        for m in rx.finditer(text):
            if not negated(text, m.start()):
                g = out.setdefault(f"act:{cat}", [])
                if m.group(0) not in g:
                    g.append(m.group(0))
    large = out.get("act:LARGE")
    if large and all(k in LARGE_NOUNS for k in large):
        out.pop("act:LARGE")
    return out


__all__ = ["refine", "negated", "LARGE_NOUNS"]
