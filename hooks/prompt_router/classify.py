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
    "ci", "cd", "go", "tsx", "3d", "5x", "20x",
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
# whole-word match (M1): "infrastructure" no longer counts as "infra"
_HEAVY_RX = re.compile(r"(?<!\w)(?:" + "|".join(
    re.escape(s) for s in sorted(_HEAVY_SIGNALS, key=len, reverse=True)) + r")(?!\w)")

# R3.6 UI veto defaults (router.config.json additions.ui_veto overrides)
_VETO_DEFAULT = {
    "words": ["redesign", "design", "selector", "picker", "switcher", "restyle"],
    "ui_nouns": ["page", "pages", "component", "components", "screen", "screens", "layout", "button",
                 "buttons", "css", "form", "forms", "modal", "landing", "hero", "ui", "ux", "frontend",
                 "dashboard", "widget", "panel", "view", "menu", "navbar", "sidebar"],
    "window": 6,
}


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
_URL = re.compile(r"\b(?:https?|ftp)://\S+", re.IGNORECASE)


def keyword_ok(kw: str) -> bool:
    """Keep a keyword only if its tokenized form is > 3 chars or explicitly allow-listed.

    Judged on the tokens the matcher really compares: ``use()`` tokenizes to ``use``
    (3 chars) and used to pass on its raw length, crediting every prompt with "use" (A-02).
    """
    toks = words(kw)
    j = " ".join(toks)
    return bool(toks) and (len(j) > 3 or j in _SHORT_ALLOW)


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


def _singular(phrase: str) -> str:
    """Strip one plural suffix from the last word ("crashes" -> "crash")."""
    if phrase.endswith("es") and phrase[:-2].endswith(("sh", "ch", "ss", "x")):
        return phrase[:-2]
    return phrase[:-1] if phrase.endswith("s") and not phrase.endswith("ss") else phrase


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
            # intents only: optional s/es ("bugs", "crashes", "unit tests", audit C-04);
            # UI/arch lists carry their own plurals and `components/` is a path segment
            plural = r"(?:e?s)?" if g.startswith("act:") else ""
            self._pat[g] = re.compile(
                r"(?<!\w)(?:" + "|".join(re.escape(k) for k in clean) + r")" + plural + r"(?!\w)",
                re.IGNORECASE)

    def groups(self) -> list[str]:
        return list(self._pat)

    def hits(self, text: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for g, pat in self._pat.items():
            phrases = {m.group(0).lower() for m in pat.finditer(text)}
            if not phrases:
                continue
            phrases |= {_singular(p) for p in phrases}
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
    weak = _router_additions().get("model_routing_weak")
    groups["mr_weak"] = [str(k).lower() for k in weak] if isinstance(weak, list) else []
    return KeywordMatcher(groups)


@lru_cache(maxsize=1)
def _veto_cfg() -> tuple[frozenset, frozenset, int]:
    """(veto words, UI nouns, window) from ``additions.ui_veto`` (R3.6)."""
    v = _router_additions().get("ui_veto") or {}
    if not isinstance(v, dict):
        v = {}
    vw = frozenset(str(w).lower() for w in (v.get("words") or _VETO_DEFAULT["words"]))
    nouns = frozenset(str(n).lower() for n in (v.get("ui_nouns") or _VETO_DEFAULT["ui_nouns"]))
    try:
        win = int(v.get("window", _VETO_DEFAULT["window"]))
    except (TypeError, ValueError):
        win = _VETO_DEFAULT["window"]
    return vw, nouns, win


def _word_positions(text_words: tuple[str, ...], word: str) -> list[int]:
    """Start indexes of ``word`` (a phrase) in the prompt; the last word may carry s/es,
    as act keywords match plurals."""
    parts = words(word)
    if not parts:
        return []
    n, last = len(parts), parts[-1]
    forms = {last, last + "s", last + "es"}
    return [i for i in range(len(text_words) - n + 1)
            if text_words[i:i + n - 1] == parts[:-1] and text_words[i + n - 1] in forms]


def _noun_near(text_words: tuple[str, ...], positions: list[int], nouns, window: int) -> bool:
    return any(w in nouns for i in positions for w in text_words[max(0, i - window): i + window + 1])


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
    # URLs are not task words: `https`, `docs`, `migration` inside one misrouted
    # intents and skills (audit C-04)
    text = _URL.sub(" ", " \n ".join(parts)).lower()
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


_NO_UI = re.compile(r"\b(?:no|without|not an?)\s+(?:ui|gui|web ?page|front[- ]?end|html)\b"
                    r"|\bplain[- ]text\b|\b(?:cli|command[- ]line|terminal) (?:app|tool|program)\b")
_URL_RX = re.compile(r"https?://\S+")


# Harness-generated "prompts" (background-agent results, local command output, a peer
# session's message) are not user tasks: routing skills onto them is pure noise.
_MACHINE_PREFIXES = ("<task-notification>", "<local-command-stdout>", "<local-command-stderr>",
                     "<cross-session-message", "Another Claude session sent a message",
                     "[Subagent hand-back]", "<agent-message from=",
                     # scripts/restore_sessions.py CONTINUE_PROMPT (the crash-restore unit)
                     "Session restored automatically after a crash")


_SYS_REMINDER_OPEN = re.compile(r"\A(?:\s*<system-reminder\b[^>]*>)+")
# A subagent hand-back / agent relay / peer message reaches UserPromptSubmit as a prompt. The
# marker must open the text (after leading <system-reminder> tags) or open a line / follow a
# closing tag within the first 400 chars; a human sentence that merely quotes it mid-line is a task.
# Same markers in hooks/lib/turns.py _NOT_HUMAN and mods/mercy/hooks/features/prompts.ts NOT_HUMAN.
_MACHINE_MARKER = re.compile(
    r"(?:\A|\n|>)\s*(?:\[Subagent hand-back\]|<agent-message from=|Another Claude session sent a message)")
_MACHINE_SCAN = 400


def is_machine_text(prompt: str) -> bool:
    """Harness-written prompt (never typed by the user): a known prefix, or a hand-back marker."""
    p = (prompt or "").strip()
    if p.startswith(_MACHINE_PREFIXES):
        return True
    body = _SYS_REMINDER_OPEN.sub("", p, count=1).lstrip()
    return body.startswith(_MACHINE_PREFIXES) or bool(_MACHINE_MARKER.search(body[:_MACHINE_SCAN]))


def is_trivial_ack(prompt: str) -> bool:
    return prompt.strip().lower().rstrip(".!") in ACK_ALLOWLIST or is_machine_text(prompt)


def _machine_cwd(cwd) -> bool:
    """The double-shot-latte headless judge runs from <claude_dir>/double-shot-latte:
    its "prompts" are a transcript to grade, not a task."""
    if not cwd:
        return False
    try:
        from lib import platform as _plat  # noqa: PLC0415
        judge = (_plat.claude_dir() / "double-shot-latte").resolve()
        c = Path(str(cwd)).resolve()
        return c == judge or judge in c.parents
    except Exception:  # noqa: BLE001 - fail-open: route as usual
        return False


def classify(payload: dict) -> TaskProfile:
    """Single classification pass. Never raises."""
    try:
        return _classify_impl(payload)
    except Exception:  # noqa: BLE001 - classify must be fail-open
        prompt = payload.get("prompt") if isinstance(payload, dict) else ""
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        return TaskProfile(text=str(prompt or "").lower(),
                           trivial_ack=is_trivial_ack(str(prompt or "")) or _machine_cwd(cwd))


_SCAN_HEAD, _SCAN_TAIL = 6000, 2000


def _classify_impl(payload: dict) -> TaskProfile:
    prompt = str(payload.get("prompt") or "")
    if len(prompt) > _SCAN_HEAD + _SCAN_TAIL:
        # a pasted log or separator must not cost seconds of regex time (Santa A3);
        # the task words sit at the start and the end of a long prompt
        payload = {**payload, "prompt": prompt[:_SCAN_HEAD] + "\n" + prompt[-_SCAN_TAIL:]}
    text, paths = collect_text(payload)
    idx = _floor_index()

    prof = TaskProfile(text=text, paths=paths,
                       trivial_ack=is_trivial_ack(prompt) or _machine_cwd(payload.get("cwd")))
    if prof.trivial_ack:
        return prof

    hits = _matcher().hits(text)
    try:
        from prompt_router import cues as _cues  # noqa: PLC0415
        hits = _cues.refine(hits, text)
    except Exception:  # noqa: BLE001
        pass

    # --- act keyword hits per category (each keyword credited once) ---
    for g, kws in hits.items():
        if g.startswith("act:"):
            prof.intents[g[4:]] = len(kws)
            prof.keywords_hit.extend(kws)
    # a bare model name ("use opus for this: ...") is the override phrase, not routing
    # talk: weak tokens raise MODEL_ROUTING only in pairs (REVIEW2 Fix 1)
    weak = set(hits.get("mr_weak", []))
    mr_weak_only = "MODEL_ROUTING" not in prof.intents and len(weak) >= 2
    if mr_weak_only:
        prof.intents["MODEL_ROUTING"] = len(weak)
        prof.keywords_hit.extend(sorted(weak))

    # --- arch / explore ---
    prof.arch_hit = list(hits.get("arch", []))
    prof.is_arch = bool(prof.arch_hit)

    # --- surfaces: prompt paths + vocab, cwd, repo stack (modules/surface.py) ---
    named: set[str] = set()   # surfaces the prompt itself names ("react", a .tsx path)
    try:
        from prompt_router.modules import surface as _surface  # noqa: PLC0415
        surfs, source, weak = _surface.detect(payload, text=text)
        named = set(surfs) - set(weak) if source == "prompt" else set()
        prof.surfaces |= surfs
        prof.surface_source = source
        prof.weak_surfaces = set(weak)
    except Exception:  # noqa: BLE001
        pass

    # --- ui detection (with excludes) ---
    # A UI signal needs real weight (one non-vague keyword, or several vague ones:
    # "page"/"table"/"form" alone are not a UI task) and must not contradict a
    # prompt that is explicitly backend-only ("endpoint … with pagination").
    # R3.6 veto: "redesign"/"selector"/... score UI only with a UI noun within `window`
    # words; with a MODEL_ROUTING hit the same rule drops them from DESIGN too.
    vw, nouns, win = _veto_cfg()
    tw = words(text)
    mr = "MODEL_ROUTING" in prof.intents
    noun_anywhere = bool(nouns & set(tw))

    def _vetoed(kw: str) -> bool:
        return kw in vw and not _noun_near(tw, _word_positions(tw, kw), nouns, win)

    if mr:
        design = [k for k in hits.get("act:DESIGN", []) if not _vetoed(k)]
        if design:
            prof.intents["DESIGN"] = len(design)
        else:
            prof.intents.pop("DESIGN", None)
    if not hits.get("ui_exclude"):
        prof.ui_hit = [k for k in hits.get("ui", []) if not _vetoed(k)]
    ui_weight = sum(idx["ui_w"].get(k, 1.0) for k in prof.ui_hit)
    backend_only = (prof.surface_source == "prompt" and "backend" in prof.surfaces
                    and "frontend" not in prof.surfaces)
    # "no UI", "plain-text report", "a CLI tool": the prompt rules the frontend out (RT-3),
    # unless it still names the frontend once the negated phrases are gone
    no_ui = False
    if _NO_UI.search(text):
        try:
            s2, src2, w2 = _surface.detect(payload, text=_NO_UI.sub(" ", text))
            named2 = set(s2) - set(w2) if src2 == "prompt" else set()
        except Exception:  # noqa: BLE001
            named2 = named
        no_ui = "frontend" not in named2
    prof.is_ui = bool(prof.ui_hit) and ui_weight >= 1.0 and not backend_only and not no_ui
    # claude-infra work ("skills and hooks do not trigger ... design tokens") is not a UI task
    # unless the prompt itself names the frontend (A-01)
    if prof.is_ui and "claude-infra" in prof.surfaces and not _surface._FE_VOCAB.search(text):
        prof.is_ui = False

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
    if no_ui:
        fe = {"frontend", "ui", "fullstack"}
        prof.surfaces -= fe
        prof.weak_surfaces -= fe
        prof.path_suffixes = []
        prof.intents.pop("DESIGN", None)
    # a pasted URL with a question and no task is reading, not building: "API" in the
    # sentence is not a backend task (RT-3)
    if (prof.surface_source == "prompt" and _URL_RX.search(prompt) and not paths  # text drops URLs
            and not {"IMPLEMENT", "DEBUG", "TEST", "REFACTOR"} & set(prof.intents)):
        prof.surfaces -= {"backend", "frontend", "fullstack", "api"}
    # a cwd-only surface (server/) loses to a page the prompt names (RQ-10)
    if prof.surface_source == "cwd" and prof.is_ui:
        prof.weak_surfaces.add("backend")

    # --- model-routing talk is claude-infra work, not frontend (R3.6) ---
    if mr:
        prof.surfaces.add("claude-infra")
        # "use opus to build the checkout in react" stays frontend: the prompt named it;
        # so does a UI task that only names models ("opus or sonnet for the data table").
        # A routing noun ("subagent model routing") keeps the strict rule: "switch" there is a verb.
        if (not noun_anywhere and "frontend" not in named
                and not (mr_weak_only and prof.is_ui)):
            fe = {"frontend", "ui", "fullstack"}
            prof.surfaces -= fe
            prof.weak_surfaces -= fe
            prof.is_ui = False
            prof.path_suffixes = []
        if not prof.surface_source:
            prof.surface_source = "prompt"

    # --- heavy signal scan (size/risk ONLY — never the keyword trigger surface) ---
    heavy_count = len({m.group(0) for m in _HEAVY_RX.finditer(text)})

    # --- size ---
    if "LARGE" in prof.intents or heavy_count >= 2:
        prof.size = "L"
    elif "MEDIUM" in prof.intents:
        prof.size = "M"
    elif "SMALL" in prof.intents or "TRIVIAL" in prof.intents:
        prof.size = "S"
    else:
        prof.size = "M"
    if prof.size == "L":
        prof.intents.pop("SMALL", None)  # "update the docs" inside a size-L prompt is not a small task

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
