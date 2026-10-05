"""policy.py — what the router emits, and how hard (audit 2026-10-05).

C-05  ``enforce_level``: a rank-1 push is recorded ``enforce:"hard"`` (invoke-suite-gate
      blocks Stop on it) only when it clears ``enforce_hard.min_score``, beats rank 2 by
      ``enforce_hard.margin`` and its index intents/surfaces match the prompt.
C-10  ``dev_signal`` / ``write_gates`` / ``code_shaped``: chat, pure questions and
      trivial one-liners get no substrate, symbols, first-write or TDD lines.
C-11  ``skill_line``: the Skill tool already lists every skill's description, so a
      push is the name plus a bare action (``Skill("x")``, or the absolute SKILL.md to
      Read for a ``paths:``-scoped skill) — no description, no boilerplate.
C-12  ``session_model``: the model this session runs (payload, else transcript tail).
C-14  ``ui_line``: names only the asset servers that are available.
C-17  ``cap_section``: one total cap on ROUTING lines.
Pure stdlib; every caller wraps it fail-open.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_SIZE_ONLY = {"SMALL", "MEDIUM", "LARGE", "TRIVIAL"}
_CODE_INTENTS = {"IMPLEMENT", "DEBUG", "REVIEW", "REFACTOR", "TEST", "AUDIT", "CLEANUP"}
_WRITE_INTENTS = {"IMPLEMENT", "DEBUG", "TEST", "REFACTOR"}
_QUESTION = re.compile(r"^\s*(?:what|why|where|which|who|how|when|is|are|does|do|can you explain|explain)\b")
_IDENT = re.compile(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b|\w+\(\)")
_MODEL_RX = re.compile(r'"model"\s*:\s*"([^"]+)"')


# --------------------------------------------------------------------------- C-05
def enforce_level(ranked, profile, meta: dict, cfg: dict | None = None) -> str:
    cfg = cfg or {}
    if not ranked:
        return "soft"
    name, s1 = ranked[0]
    s2 = ranked[1][1] if len(ranked) > 1 else 0.0
    if s1 < float(cfg.get("min_score", 6.0)) or s1 < float(cfg.get("margin", 1.5)) * s2:
        return "soft"
    m = meta.get(name) or {}
    intents = {str(i).upper() for i in (m.get("intents") or [])}
    strong = set(profile.surfaces) - set(getattr(profile, "weak_surfaces", set()) or set())
    if intents & set(profile.intents) or strong & set(m.get("surfaces") or []):
        return "hard"
    return "soft"


# --------------------------------------------------------------------------- C-10
def _dev_intents(profile) -> set:
    return set(profile.intents) - _SIZE_ONLY


def dev_signal(profile) -> bool:
    """Anything that makes this a software task (not chat)."""
    return bool(_dev_intents(profile) or profile.paths or profile.is_arch or profile.is_ui
                or profile.surface_source in ("prompt", "cwd"))


def _trivial_only(profile) -> bool:
    return "TRIVIAL" in profile.intents and not (_WRITE_INTENTS & set(profile.intents))


def write_gates(profile) -> bool:
    """First-write / TDD lines only for prompts that will write real code."""
    if _trivial_only(profile):
        return False
    if _QUESTION.search(profile.text or "") and "IMPLEMENT" not in profile.intents:
        return False
    return True


# Floor explore keywords too generic to mean "architecture question" ("search component",
# "rename the label in InventoryTable" — 'inventory' is a domain noun in many apps).
WEAK_ARCH = frozenset({"search", "find", "look", "look for", "explore", "where is", "locate",
                       "inventory"})


def strong_arch(profile) -> bool:
    return any(h not in WEAK_ARCH for h in (getattr(profile, "arch_hit", None) or []))


# "how is X wired" / dependency questions the floor's arch keywords can miss.
ARCH_RX = re.compile(
    r"\b(how (?:is|are|does|do) [\w./-]+(?: [\w./-]+){0,3} (?:wired|connected|hooked up|fit together)"
    r"|who (?:depends on|imports|calls)|what (?:depends on|calls|imports)|depend(?:s|encies) (?:of|on)"
    r"|call graph|data flow|architecture)\b")


def code_shaped(profile) -> bool:
    """Indexed symbols help only when the prompt points at code: a path, an
    identifier, a structural question, or a code intent on a prompt-named surface."""
    if _trivial_only(profile):
        return False
    return bool(profile.paths or _IDENT.search(profile.text or "") or ARCH_RX.search(profile.text or "")
                or (_CODE_INTENTS & set(profile.intents) and profile.surface_source == "prompt"))


# --------------------------------------------------------------------------- C-11
def skill_line(name: str, label: str, read_path: str | None) -> str:
    """Two short lines; the ``ACTION:`` line is parsed by the mercy governor and tests."""
    action = f"Read {read_path}" if read_path else f'Skill("{name}")'
    return f"- **{name}** ({label})\n  ACTION: {action}"


# --------------------------------------------------------------------------- C-12
def session_model(payload: dict) -> str:
    m = payload.get("model")
    if isinstance(m, dict):
        m = m.get("id") or m.get("display_name")
    if isinstance(m, str) and m:
        return m
    try:
        p = Path(str(payload.get("transcript_path") or ""))
        if not p.is_file():
            return ""
        with p.open("rb") as f:
            f.seek(max(0, p.stat().st_size - 262144))
            tail = f.read().decode("utf-8", "replace")
        found = _MODEL_RX.findall(tail)
        return found[-1] if found else ""
    except (OSError, ValueError, json.JSONDecodeError):
        return ""


# --------------------------------------------------------------------------- C-14
def ui_line(available) -> str:
    """``available(name) -> bool`` decides which asset servers are named."""
    text = "UI signal → design-taste-frontend is the visual authority"
    if available("higgsfield"):
        text += "; assets via Higgsfield"
        if available("openart"):
            text += " (OpenArt when the project says so)"
    elif available("openart"):
        text += "; assets via OpenArt"
    return text + "; scroll motion → nateherk-design:scroll-craft."


# --------------------------------------------------------------------------- C-17
def cap_section(items: list[dict], section: str, n: int) -> list[dict]:
    out, seen = [], 0
    for it in items:
        if it.get("section") == section:
            seen += 1
            if seen > n:
                continue
        out.append(it)
    return out


__all__ = ["enforce_level", "dev_signal", "write_gates", "code_shaped", "strong_arch", "skill_line",
           "session_model", "ui_line", "cap_section"]
