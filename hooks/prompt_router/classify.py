"""classify.py — S1: build one TaskProfile from the trigger floor + surfaces.

Classification happens EXACTLY ONCE per prompt. It consumes ``trigger-floor.json``
(v2 floor, 2026-09-27) and ``modules/surface.py``.

Matching (v3, 2026-09-27): WORD-BOUNDARY, not substring. One lookaround-bounded
alternation is compiled per keyword group (``(?<!\\w)(?:kw1|kw2|…)(?!\\w)``,
alternatives longest-first) so ``cr`` never fires on "create", ``ui`` never fires
on "build", ``off`` never fires on "offline". A keyword is credited at most once
per prompt (the pre-v3 semantics thresholds were tuned against), including when
it is a whole-word part of a longer matched phrase ("review" inside "review my
changes"). Keywords of <= 3 chars are dropped unless in ``_SHORT_ALLOW`` — the
floor builder applies the same filter at build time; this is the runtime belt.

Pure stdlib; never raises (a classify failure yields an empty profile -> the
router falls open to no injection rather than crashing the prompt).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
_FLOOR_PATH = _HOOKS / "trigger-floor.json"
_AUTON_CONFIG = _HOOKS / "autonomous-skill-router.config.json"

# Short tokens (<= 3 chars) that are unambiguous enough to keep as keywords.
_SHORT_ALLOW = frozenset({
    "api", "ui", "ux", "sql", "css", "tdd", "e2e", "a11y", "seo", "glb", "r3f",
    "ci", "cd", "go", "tsx", "3d",
    # high-precision whole words (word-boundary matched): without "bug"/"fix",
    # "fix the login bug" routed to nothing
    "bug", "fix", "404", "xss", "jwt", "csp", "pii", "tls", "ssl", "adr", "prd", "rfc", "uat",
})

# category -> act name. Derived from autonomous-skill-router.config.json
# (``categories.<CAT>.act``, added by the /invoke rebuild) with these literals as
# the fallback so the router never depends on another WP landing first.
_ACT_FALLBACK = {
    "AUDIT": "audit", "SPEC": "spec", "PLAN": "plan", "IMPLEMENT": "impl",
    "DESIGN": "design", "DEBUG": "debug", "CLEANUP": "clean", "SECURITY": "security",
    "REVIEW": "review", "TEST": "test", "REFACTOR": "refactor",
    "DOCS": "docs", "VERIFY": "verify",
}
# priority order for emitting acts (mirrors autonomous category_priority)
_ACT_PRIORITY = ["DEBUG", "SECURITY", "SHIP", "SPEC", "PLAN", "AUDIT",
                 "IMPLEMENT", "REFACTOR", "DESIGN", "CLEANUP", "REVIEW", "QA", "TEST",
                 "DOCS", "VERIFY", "RESUME", "LARGE", "MEDIUM", "SMALL", "TRIVIAL"]

# exact-match acknowledgement allowlist — the ONLY trivial fast-exit
ACK_ALLOWLIST = frozenset({
    "yes", "ok", "okay", "continue", "go ahead", "proceed", "thanks", "thank you",
    "yep", "yeah", "sure", "go", "do it", "sounds good", "lgtm", "y",
})

# Heavy-scale language signals — feed size/risk inference ONLY (not the keyword
# trigger surface). Used by model_advice (opus task_matrix + heavy_qualifiers).
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


def _auton_categories() -> dict:
    try:
        data = json.loads(_AUTON_CONFIG.read_text(encoding="utf-8"))
        cats = data.get("categories")
        return cats if isinstance(cats, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _build_act_map() -> dict[str, str]:
    out = dict(_ACT_FALLBACK)
    for cat, spec in _auton_categories().items():
        if isinstance(spec, dict) and isinstance(spec.get("act"), str) and spec["act"]:
            out[cat] = spec["act"]
    return out


ACT_MAP = _build_act_map()


@dataclass
class TaskProfile:
    text: str = ""
    paths: list[str] = field(default_factory=list)
    intents: dict[str, int] = field(default_factory=dict)   # category -> hit score
    acts: list[str] = field(default_factory=list)           # ordered act names
    surfaces: set[str] = field(default_factory=set)         # frontend/backend/fullstack/docs + tags (go, sql, api, three, ...)
    surface_source: str = ""                                # prompt | cwd | stack | ""
    weak_surfaces: set[str] = field(default_factory=set)    # subset of `surfaces` inferred from the repo stack only
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


# --------------------------------------------------------------------------- #
# Word-boundary keyword matching
# --------------------------------------------------------------------------- #
_WORD = re.compile(r"\w+")


def keyword_ok(kw: str) -> bool:
    """Keep a keyword only if it is > 3 chars or explicitly allow-listed."""
    k = (kw or "").strip().lower()
    return bool(k) and (len(k) > 3 or k in _SHORT_ALLOW)


def words(s: str) -> tuple[str, ...]:
    return tuple(_WORD.findall((s or "").lower()))


def ngrams(text: str, max_n: int = 6) -> set[tuple[str, ...]]:
    """All word n-grams (n <= max_n) of ``text`` — exact word-boundary membership
    for the many-small-keyword case (skills index) where compiling one regex per
    skill would cost more than the match itself."""
    w = words(text)
    out: set[tuple[str, ...]] = set()
    for i in range(len(w)):
        for j in range(i + 1, min(i + max_n, len(w)) + 1):
            out.add(tuple(w[i:j]))
    return out


def _contains(seq: tuple[str, ...], sub: tuple[str, ...]) -> bool:
    n = len(sub)
    if n == 0 or n > len(seq):
        return False
    return any(seq[i:i + n] == sub for i in range(len(seq) - n + 1))


class KeywordMatcher:
    """One compiled alternation per group; ``hits(text)`` -> {group: [keywords]}.

    Each keyword is credited once when it (a) is a matched phrase or (b) is a
    whole-word sub-phrase of a matched phrase. Longest alternatives are tried
    first so "create a new" wins over "create" at the same position.
    """

    def __init__(self, groups: dict[str, list[str]]):
        self._pat: dict[str, re.Pattern] = {}
        self._kws: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
        for g, kws in groups.items():
            clean = sorted({k.strip().lower() for k in kws if keyword_ok(k)},
                           key=len, reverse=True)
            if not clean:
                continue
            self._kws[g] = [(k, words(k)) for k in clean]
            self._pat[g] = re.compile(
                r"(?<!\w)(?:" + "|".join(re.escape(k) for k in clean) + r")(?!\w)",
                re.IGNORECASE)

    def groups(self) -> list[str]:
        return list(self._pat)

    def hits(self, text: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for g, pat in self._pat.items():
            phrases = {m.group(0).lower() for m in pat.finditer(text)}
            if not phrases:
                continue
            pw = [words(p) for p in phrases]
            hit = [k for k, kw in self._kws[g]
                   if k in phrases or any(_contains(w, kw) for w in pw)]
            if hit:
                out[g] = hit
        return out


@lru_cache(maxsize=1)
def _floor_index() -> dict:
    """Load + index the trigger floor once per process."""
    idx = {
        "act": {},          # category -> [keyword,...]
        "ui": [],
        "ui_w": {},         # ui keyword -> weight (vague words are 0.4)
        "ui_exclude": [],
        "ui_suffix": [],
        "arch": [],
        "path_route": [],   # rule dicts
        "path_segment": {"frontend_path_segments": [], "backend_path_segments": [],
                         "documentation_path_segments": []},
        "cross_cutting": {},  # group -> [skills]
    }
    try:
        data = json.loads(_FLOOR_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return idx
    for e in data.get("entries", []):
        kind = e.get("kind")
        val = e.get("value")
        if kind == "act_keyword":
            cat = e.get("source_key", "").split(".", 1)[-1]
            idx["act"].setdefault(cat, []).append(str(val).lower())
        elif kind == "ui_keyword":
            idx["ui"].append(str(val).lower())
            idx["ui_w"][str(val).lower()] = float(e.get("weight", 1.0) or 1.0)
        elif kind == "ui_exclude":
            idx["ui_exclude"].append(str(val).lower())
        elif kind == "ui_suffix":
            idx["ui_suffix"].append(str(val).lower())
        elif kind in ("arch_keyword", "explore_keyword"):
            idx["arch"].append(str(val).lower())
        elif kind == "path_route":
            idx["path_route"].append(val)
        elif kind == "path_segment":
            idx["path_segment"].setdefault(e.get("source_key", ""), []).append(str(val).lower())
        elif kind == "cross_cutting" and isinstance(val, dict):
            idx["cross_cutting"][val.get("group", "")] = list(val.get("skills") or [])
    return idx


def _router_additions() -> dict:
    """``router.config.json`` -> ``additions`` (router-only trigger ADDITIONS atop the floor)."""
    try:
        cfg = json.loads((_HOOKS / "prompt_router" / "router.config.json").read_text(encoding="utf-8"))
        add = cfg.get("additions")
        return add if isinstance(add, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def _matcher() -> KeywordMatcher:
    idx = _floor_index()
    groups: dict[str, list[str]] = {f"act:{c}": list(kws) for c, kws in idx["act"].items()}
    for cat, kws in (_router_additions().get("intents") or {}).items():
        if isinstance(kws, list):
            groups.setdefault(f"act:{cat}", []).extend(str(k).lower() for k in kws)
    groups["ui"] = idx["ui"]
    groups["ui_exclude"] = idx["ui_exclude"]
    groups["arch"] = idx["arch"]
    return KeywordMatcher(groups)


# --------------------------------------------------------------------------- #
# Text / path collection
# --------------------------------------------------------------------------- #
def _norm_path(p: str) -> str:
    return p.replace("\\", "/").lower()


def collect_text(payload: dict) -> tuple[str, list[str]]:
    """Return (search_text_lower, paths_lower) from the hook payload.

    Paths come from attachments / tool_input (when a caller supplies them) AND
    from path-like tokens in the prompt itself (``surface.prompt_paths``) — a
    UserPromptSubmit payload carries no attachments, so the prompt is the only
    real source of paths.
    """
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
    text = " \n ".join(parts).lower()
    try:
        from prompt_router.modules import surface as _surface  # noqa: PLC0415
        for tok in _surface.prompt_paths(text):
            n = _norm_path(tok)
            if n not in paths:
                paths.append(n)
    except Exception:  # noqa: BLE001
        pass
    return text, paths


def _flatten(obj, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flatten(v, out)


# Harness-generated "prompts" (background-agent results, local command output) are
# not user tasks: routing skills onto an agent's report is pure noise.
_MACHINE_PREFIXES = ("<task-notification>", "<local-command-stdout>", "<local-command-stderr>")


def is_trivial_ack(prompt: str) -> bool:
    p = prompt.strip()
    return p.lower().rstrip(".!") in ACK_ALLOWLIST or p.startswith(_MACHINE_PREFIXES)


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

    hits = _matcher().hits(text)

    # --- act keyword hits per category (each keyword credited once) ---
    for g, kws in hits.items():
        if g.startswith("act:"):
            prof.intents[g[4:]] = len(kws)
            prof.keywords_hit.extend(kws)

    # --- arch / explore ---
    prof.arch_hit = list(hits.get("arch", []))
    prof.is_arch = bool(prof.arch_hit)

    # --- surfaces: prompt paths + vocab, cwd, repo stack (modules/surface.py) ---
    try:
        from prompt_router.modules import surface as _surface  # noqa: PLC0415
        surfs, source, weak = _surface.detect(payload, text=text)
        prof.surfaces |= surfs
        prof.surface_source = source
        prof.weak_surfaces = set(weak)
    except Exception:  # noqa: BLE001
        pass

    # --- ui detection (with excludes) ---
    # A UI signal needs real weight (one non-vague keyword, or several vague ones:
    # "page"/"table"/"form" alone are not a UI task) and must not contradict a
    # prompt that is explicitly backend-only ("endpoint … with pagination").
    if not hits.get("ui_exclude"):
        prof.ui_hit = list(hits.get("ui", []))
    ui_weight = sum(idx["ui_w"].get(k, 1.0) for k in prof.ui_hit)
    backend_only = (prof.surface_source == "prompt" and "backend" in prof.surfaces
                    and "frontend" not in prof.surfaces)
    prof.is_ui = bool(prof.ui_hit) and ui_weight >= 1.0 and not backend_only

    # legacy path-segment / ui-suffix rules on any collected paths
    seg = idx["path_segment"]
    infra = "claude-infra" in prof.surfaces
    for pth in ([] if infra else paths):
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
        prof.surfaces.update({"frontend", "ui"})
        if not prof.surface_source:
            prof.surface_source = "prompt"
    if {"frontend", "backend"} <= prof.surfaces:
        prof.surfaces.add("fullstack")

    # --- heavy signal scan (size/risk ONLY — never the keyword trigger surface) ---
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

    # --- reasoning-shaped (kept for profile consumers; no directive is emitted) ---
    reasoning_cats = {"DEBUG", "DESIGN", "PLAN", "AUDIT", "SPEC", "SECURITY",
                      "REVIEW", "IMPLEMENT", "CLEANUP"}
    prof.is_reasoning = bool(reasoning_cats & set(prof.intents)) or prof.is_arch or bool(prof.paths)

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
    if "IMPLEMENT" in prof.intents and "fullstack" in prof.surfaces:
        risk += 1
    if heavy_count >= 2:
        risk += 1
    prof.risk = min(risk, 3)

    return prof


__all__ = ["TaskProfile", "classify", "is_trivial_ack", "ACK_ALLOWLIST", "ACT_MAP",
           "KeywordMatcher", "keyword_ok", "ngrams", "words", "_SHORT_ALLOW"]
