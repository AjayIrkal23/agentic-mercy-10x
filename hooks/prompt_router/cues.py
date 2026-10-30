"""cues.py — refinements applied to the raw keyword hits (audit 2026-10-05 C-04, C-12).

* Negation: a keyword preceded within 3 words by "no need for/to", "don't", "do not"
  or "without" is not a task word ("no need for a security review" is not SECURITY).
* Phrase intents the flat keyword list cannot express: "write <x> tests" -> TEST; "port X from A
  to B" -> IMPLEMENT, unless the prompt is a question.
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
    # "migrate|port|convert|rewrite|move|switch <thing> from A to B": an implementation, whatever A/B are
    "IMPLEMENT": re.compile(r"\b(?:migrat(?:e|ing)|port(?:ing)?|convert(?:ing)?|rewrit(?:e|ing)|mov(?:e|ing)"
                            r"|switch(?:ing)?)\b(?:\W+\w+){0,8}?\W+from\W+(?:\w+\W+){1,4}?to\b"),
    "LARGE": re.compile(r"\b(?:migrate|port|convert|rewrite) the (?:whole|entire|complete) \w+"),
}
# a question ("how do I convert this date from UTC to IST", "why did the port change from 3000 to 3001?")
# asks, it does not order an implementation: the IMPLEMENT phrase cue skips it
_QUESTION_RE = re.compile(r"^\s*(?:how|why|what|when|where|which|who|should|can|could|would|is|are|does|do|did)\b"
                          r"|\?\s*$", re.I)
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
        if cat == "IMPLEMENT" and _QUESTION_RE.search(text):
            continue
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
