"""classify.py — S1: build one TaskProfile from the trigger floor.

Classification happens EXACTLY ONCE per prompt (Charter §1). It consumes
``trigger-floor.json`` (the verbatim legacy superset) so every legacy keyword
still fires. Matching mirrors the legacy hooks: case-insensitive substring
match of a keyword against the concatenated prompt + attachment paths + tool
input strings.

Pure stdlib; never raises (a classify failure yields an empty profile -> the
router falls open to no injection rather than crashing the prompt).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
_FLOOR_PATH = _HOOKS / "trigger-floor.json"

# category -> act name (only these categories are "acts"; the rest are intents/size)
ACT_MAP = {
    "AUDIT": "audit", "SPEC": "spec", "PLAN": "plan", "IMPLEMENT": "impl",
    "DESIGN": "design", "DEBUG": "debug", "CLEANUP": "clean", "SECURITY": "security",
}
# priority order for emitting acts (mirrors autonomous category_priority)
_ACT_PRIORITY = ["DEBUG", "SECURITY", "SHIP", "SPEC", "PLAN", "AUDIT",
                 "IMPLEMENT", "DESIGN", "CLEANUP", "REVIEW", "QA", "TEST",
                 "RESUME", "LARGE", "MEDIUM", "SMALL", "TRIVIAL"]

# exact-match acknowledgement allowlist — the ONLY trivial fast-exit (Charter §1;
# the legacy "<12 chars" heuristic is DROPPED as trigger-unsafe).
ACK_ALLOWLIST = frozenset({
    "yes", "ok", "okay", "continue", "go ahead", "proceed", "thanks", "thank you",
    "yep", "yeah", "sure", "go", "do it", "sounds good", "lgtm", "y",
})

# Heavy-scale language signals — feed size/risk inference ONLY (not the keyword
# trigger surface). A text-only architecture prompt carries no paths, so scale is
# read from the words. Used by model_advice (opus task_matrix + heavy_qualifiers).
_HEAVY_SIGNALS = (
    "multi-service", "multi service", "microservice", "microservices",
    "multiple services", "many modules", "several modules", "distributed",
    "pipeline", "event pipeline", "event-driven", "across fe", "across the stack",
    "fe+be", "frontend and backend", "front end and back end", "end-to-end",
    "end to end", "whole system", "entire system", "cross-surface", "cross surface",
    "cross-service", "across many", "greenfield", "from scratch", "new system",
    "new architecture", "system design", "across the codebase", "multi-module",
    "infra", "orchestration", "state machine", "many interdependent",
)


@dataclass
class TaskProfile:
    text: str = ""
    paths: list[str] = field(default_factory=list)
    intents: dict[str, int] = field(default_factory=dict)   # category -> hit score
    acts: list[str] = field(default_factory=list)           # ordered act names
    surfaces: set[str] = field(default_factory=set)         # frontend/backend/docs
    is_ui: bool = False
    is_arch: bool = False
    is_reasoning: bool = False
    size: str = "M"                                         # S / M / L
    risk: int = 0                                           # 0..3
    keywords_hit: list[str] = field(default_factory=list)
    ui_hit: list[str] = field(default_factory=list)
    arch_hit: list[str] = field(default_factory=list)
    path_suffixes: list[str] = field(default_factory=list)
    trivial_ack: bool = False
    first_write_candidate: bool = False

    def intent_score(self, category: str) -> int:
        return self.intents.get(category, 0)


@lru_cache(maxsize=1)
def _floor_index() -> dict:
    """Load + index the trigger floor once per process."""
    idx = {
        "act": {},          # category -> [keyword,...]
        "ui": [],           # (keyword, weight)
        "ui_exclude": [],
        "ui_suffix": [],
        "arch": [],
        "explore": [],
        "path_route": [],   # rule dicts
        "path_segment": {"frontend_path_segments": [], "backend_path_segments": [],
                         "documentation_path_segments": []},
    }
    try:
        data = json.loads(_FLOOR_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return idx
    for e in data.get("entries", []):
        kind = e.get("kind")
        val = e.get("value")
        w = e.get("weight", 1.0)
        if kind == "act_keyword":
            cat = e.get("source_key", "").split(".", 1)[-1]
            idx["act"].setdefault(cat, []).append((str(val).lower(), w))
        elif kind == "ui_keyword":
            idx["ui"].append((str(val).lower(), w))
        elif kind == "ui_exclude":
            idx["ui_exclude"].append(str(val).lower())
        elif kind == "ui_suffix":
            idx["ui_suffix"].append(str(val).lower())
        elif kind == "arch_keyword":
            idx["arch"].append((str(val).lower(), w))
        elif kind == "explore_keyword":
            idx["explore"].append((str(val).lower(), w))
        elif kind == "path_route":
            idx["path_route"].append(val)
        elif kind == "path_segment":
            idx["path_segment"].setdefault(e.get("source_key", ""), []).append(str(val).lower())
    return idx


def _norm_path(p: str) -> str:
    return p.replace("\\", "/").lower()


def collect_text(payload: dict) -> tuple[str, list[str]]:
    """Return (search_text_lower, paths_lower) from the hook payload."""
    parts: list[str] = []
    paths: list[str] = []
    p = payload.get("prompt")
    if isinstance(p, str):
        parts.append(p)
    att = payload.get("attachments")
    if isinstance(att, list):
        for a in att:
            if isinstance(a, dict):
                fp = a.get("file_path")
                if isinstance(fp, str):
                    parts.append(fp)
                    paths.append(_norm_path(fp))
    ti = payload.get("tool_input")
    if isinstance(ti, dict):
        for k in ("path", "file_path", "target_file", "file"):
            v = ti.get(k)
            if isinstance(v, str) and v.strip():
                paths.append(_norm_path(v))
        _flatten(ti, parts)
    text = " \n ".join(parts)
    return text.lower(), paths


def _flatten(obj, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flatten(v, out)


def is_trivial_ack(prompt: str) -> bool:
    return prompt.strip().lower().rstrip(".!") in ACK_ALLOWLIST


def classify(payload: dict) -> TaskProfile:
    """Single classification pass. Never raises."""
    try:
        return _classify_impl(payload)
    except Exception:  # noqa: BLE001 - classify must be fail-open
        prompt = payload.get("prompt") if isinstance(payload, dict) else ""
        return TaskProfile(text=str(prompt or "").lower(),
                           trivial_ack=is_trivial_ack(str(prompt or "")))


def _classify_impl(payload: dict) -> TaskProfile:
    prompt = str(payload.get("prompt") or "")
    text, paths = collect_text(payload)
    idx = _floor_index()

    prof = TaskProfile(text=text, paths=paths, trivial_ack=is_trivial_ack(prompt))
    if prof.trivial_ack:
        return prof

    # --- act keyword hits per category ---
    for cat, kws in idx["act"].items():
        score = 0
        for kw, _w in kws:
            if kw and kw in text:
                score += 1
                prof.keywords_hit.append(kw)
        if score:
            prof.intents[cat] = score

    # --- ui detection (with excludes) ---
    excluded = any(x in text for x in idx["ui_exclude"])
    if not excluded:
        for kw, _w in idx["ui"]:
            if kw and kw in text:
                prof.ui_hit.append(kw)
    prof.is_ui = bool(prof.ui_hit)

    # --- arch / explore ---
    for kw, _w in idx["arch"] + idx["explore"]:
        if kw and kw in text:
            prof.arch_hit.append(kw)
    prof.is_arch = bool(prof.arch_hit)

    # --- surfaces from path segments + path routes ---
    seg = idx["path_segment"]
    for pth in paths:
        for s in seg.get("frontend_path_segments", []):
            if s in pth:
                prof.surfaces.add("frontend")
        for s in seg.get("backend_path_segments", []):
            if s in pth:
                prof.surfaces.add("backend")
        for s in seg.get("documentation_path_segments", []):
            if s in pth:
                prof.surfaces.add("docs")
        for suf in idx["ui_suffix"]:
            if pth.endswith(suf):
                prof.path_suffixes.append(suf)
                prof.surfaces.add("frontend")
    if prof.is_ui:
        prof.surfaces.add("frontend")

    # --- heavy signal scan (text-only prompts have no paths, so infer scale
    #     from language; feeds size/risk ONLY — never the keyword trigger surface) ---
    heavy_count = sum(1 for s in _HEAVY_SIGNALS if s in text)

    # --- size ---
    if "LARGE" in prof.intents or heavy_count >= 2:
        prof.size = "L"
    elif "MEDIUM" in prof.intents:
        prof.size = "M"
    elif "SMALL" in prof.intents or "TRIVIAL" in prof.intents:
        prof.size = "S"
    else:
        prof.size = "M"

    # --- reasoning-shaped (drives sequential-thinking directive) ---
    reasoning_cats = {"DEBUG", "DESIGN", "PLAN", "AUDIT", "SPEC", "SECURITY", "REVIEW"}
    prof.is_reasoning = bool(reasoning_cats & set(prof.intents)) or prof.is_arch

    # --- acts (priority-ordered) ---
    prof.acts = [ACT_MAP[c] for c in _ACT_PRIORITY if c in prof.intents and c in ACT_MAP]

    # --- first-write candidate (implementation/edit shaped) ---
    prof.first_write_candidate = bool(
        {"IMPLEMENT", "SPEC", "PLAN", "SMALL", "MEDIUM", "LARGE"} & set(prof.intents)
        or paths
    )

    # --- risk 0..3 ---
    risk = 0
    if "SECURITY" in prof.intents:
        risk += 1
    if "DEBUG" in prof.intents:
        risk += 1
    if prof.size == "L":
        risk += 1
    if "IMPLEMENT" in prof.intents and len(prof.surfaces) >= 2:
        risk += 1
    if heavy_count >= 2:
        risk += 1
    prof.risk = min(risk, 3)

    return prof


__all__ = ["TaskProfile", "classify", "is_trivial_ack", "ACK_ALLOWLIST", "ACT_MAP"]
