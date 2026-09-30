#!/usr/bin/env python3
"""router.py — the single-process unified prompt router (v3, 2026-09-27).

This module IS the UserPromptSubmit handler (settings.json). One process per
prompt; ~800 tokens median output; fail-open at every layer.

Pipeline:
  S0  ingest stdin payload; trivial fast-exit ONLY on an exact-match ack.
  S1  ONE classification pass -> TaskProfile (classify.py: word-boundary keyword
      matching over the trigger floor + FE/BE/API/docs surfaces from prompt paths,
      prompt vocabulary, cwd and the repo stack fingerprint — modules/surface.py).
  S2  ranked skill selection (select.py): <= 5 skills above the score floor,
      aliases collapsed, plugin skills included, core-skill-set never re-pushed;
      rank 1 = MUST-READ, ranks 2-5 = SHOULD-READ; at most ONE deep-injected body.
  S3  substrate precedence (jcodemunch for code, jdocmunch for docs, graphify for
      architecture) + indexed symbols for the prompt (modules/code_intel.py).
  S4  routing: UI signal, availability-aware MCP routes (modules/mcp_routes.py),
      /invoke act or specialist dispatch (IMPLEMENT surface-routed), per-project
      model-mode phrase, heavy-task model advice (modules/model_advice.py).
  S5  session-manifest dedup (never suppresses a first fire) -> tier-ordered emit
      as {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
      "additionalContext": "<!-- prompt-router v3 -->\\n..."}}.

Side effects: state/<sid>.router-manifest.json, hooks/.telemetry/<sid>.pushed-skills.jsonl
(rank-1 MUST-READ for invoke-suite-gate), telemetry record prompt_router.live.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import budget as _budget       # noqa: E402
from prompt_router import classify as _classify   # noqa: E402
from prompt_router import manifest as _manifest    # noqa: E402
from prompt_router import select as _select        # noqa: E402

try:
    from lib import hook_telemetry as _tel
    from lib import repo_context as _repo
except Exception:  # noqa: BLE001
    _tel = _repo = None  # type: ignore

MARKER = "<!-- prompt-router v3 -->"


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def _config() -> dict:
    try:
        return json.loads((_HOOKS / "prompt_router" / "router.config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_DOC_KEYWORDS = ("readme", "docs", "documentation", "changelog", ".md", "adr")


def _graph_exists(repo) -> bool:
    try:
        return repo is not None and (repo.path / "graphify-out" / "graph.json").is_file()
    except Exception:  # noqa: BLE001
        return False


def _doc_index_exists(repo) -> bool:
    if repo is None:
        return False
    try:
        base = Path.home() / ".doc-index" / "local"
        names = {repo.name}
        try:
            from lib.repo_context import sanitize_name
            names.add(sanitize_name(repo.name))
        except Exception:  # noqa: BLE001
            pass
        return any((base / f"{n}.json").is_file() for n in names if n)
    except Exception:  # noqa: BLE001
        return False


def _skill_excerpt(name: str, max_chars: int = 3000) -> str:
    """First section of a skill body (frontmatter stripped), for deep injection.
    Works for local skills and ``plugin:skill`` names."""
    try:
        p = _select.skill_path(name) or (Path.home() / ".claude" / "skills" / name / "SKILL.md")
        raw = p.read_text(encoding="utf-8", errors="replace")
        if raw.startswith("---"):
            end = raw.find("\n---", 3)
            if end != -1:
                raw = raw[end + 4:]
        raw = raw.strip()
        return raw[:max_chars] + ("\n…(truncated — full body: Skill tool)" if len(raw) > max_chars else "")
    except Exception:  # noqa: BLE001
        return ""


def _code_intent(profile) -> bool:
    return bool(profile.paths) or profile.is_arch or bool(
        {"IMPLEMENT", "DEBUG", "REVIEW", "AUDIT", "CLEANUP", "SPEC", "PLAN", "REFACTOR", "TEST"}
        & set(profile.intents))


# --------------------------------------------------------------------------- #
# Item builders — item := {id, tier, section, text}
# --------------------------------------------------------------------------- #
def _gate_items(profile, ctx: dict) -> list[dict]:
    items: list[dict] = []
    in_repo = ctx.get("repo") is not None
    if profile.first_write_candidate or profile.paths:
        items.append({
            "id": "firstwrite:baseline", "tier": 0, "section": "GATES",
            "text": ("First substantive change this session: orient with codebase-intel-first + "
                     "project-reference-linkage, then run dead-code-and-change-audit on your changes."),
        })
    strong_backend = "backend" in profile.surfaces and "backend" not in profile.weak_surfaces
    if in_repo and (strong_backend or "TEST" in profile.intents):
        items.append({
            "id": "gate:tdd", "tier": 0, "section": "GATES",
            "text": ("TDD: write the failing test first, then implement "
                     "(tdd-guard is advisory — treat it as a directive)."),
        })
    return items


# Per-intent jcodemunch "call now" directive (first matching intent wins).
_JCM_BY_INTENT = (
    ("DEBUG", "get_call_hierarchy / get_signal_chains on the failing path, then find_references"),
    ("REVIEW", "get_changed_symbols, then get_blast_radius / find_references per changed symbol"),
    ("AUDIT", "find_dead_code / get_hotspots / get_coupling_metrics, get_blast_radius per finding"),
    ("REFACTOR", "check_rename_safe / find_references, then get_blast_radius before any move"),
    ("PLAN", "plan_turn (or get_context_bundle) for the task slice"),
    ("SPEC", "plan_turn (or get_context_bundle) for the task slice"),
    ("IMPLEMENT", "get_context_bundle for the slice; get_blast_radius / find_references before editing a shared symbol"),
    ("CLEANUP", "get_blast_radius / check_delete_safe before each removal"),
    ("TEST", "get_symbol_source + get_untested_symbols for the code under test"),
)
# "how is X wired" / dependency questions the floor's arch keywords can miss.
_ARCH_RX = re.compile(
    r"\b(how (?:is|are|does|do) [\w./-]+(?: [\w./-]+){0,3} (?:wired|connected|hooked up|fit together)"
    r"|who (?:depends on|imports|calls)|what (?:depends on|calls|imports)|depend(?:s|encies) (?:of|on)"
    r"|call graph|data flow|architecture)\b")
# Floor explore keywords too generic to mean "architecture question" ("search component").
_WEAK_ARCH = frozenset({"search", "find", "look", "look for", "explore", "where is", "locate"})


def _mcp_ok(server: str) -> bool:
    """Availability check shared with mcp_routes (fail-open to True on import error)."""
    try:
        from prompt_router.modules import mcp_routes as _mcp  # noqa: PLC0415
        return _mcp.server_available([server]) is not None
    except Exception:  # noqa: BLE001
        return True


def _substrate_items(profile, ctx: dict) -> list[dict]:
    """Availability-aware "call X now" lines for the code/doc/graph substrate."""
    items: list[dict] = []
    repo = ctx.get("repo")
    if (_code_intent(profile) or profile.surfaces & {"frontend", "backend"}) and _mcp_ok("jcodemunch"):
        intent, tools = next(((i, t) for i, t in _JCM_BY_INTENT if i in profile.intents),
                             ("CODE", "search_symbols / get_symbol_source (or get_context_bundle)"))
        items.append({
            "id": f"substrate:jcodemunch:{intent}", "tier": 1, "section": "SUBSTRATE",
            "text": f"Code work → call jcodemunch {tools} now — before any Read/Grep of source.",
        })
    if ("docs" in profile.surfaces or any(k in profile.text for k in _DOC_KEYWORDS)) and _mcp_ok("jdocmunch"):
        if _doc_index_exists(repo):
            txt = "Docs work → call jdocmunch search_sections / get_toc now, then get_section (not whole-file reads)."
        else:
            txt = ("Docs work → jdocmunch search_sections / get_toc when indexed; this repo is not "
                   "doc-indexed yet (index-lifecycle builds it on writes) — `Read` meanwhile.")
        items.append({"id": "substrate:jdocmunch", "tier": 1, "section": "SUBSTRATE", "text": txt})
    strong_arch = any(h not in _WEAK_ARCH for h in (profile.arch_hit or []))
    if (strong_arch or _ARCH_RX.search(profile.text or "")) and _mcp_ok("graphify"):
        if _graph_exists(repo):
            txt = ("Architecture/dependency question → call graphify query_graph / god_nodes / "
                   "get_neighbors / shortest_path now, instead of grep or Explore.")
        else:
            root = repo.root if repo is not None else "<repo-root>"
            txt = (f"Architecture/dependency question → no graphify graph yet: `graphify update {root}`, "
                   "then query_graph / god_nodes; meanwhile jcodemunch get_dependency_graph.")
        items.append({"id": "substrate:graphify", "tier": 1, "section": "SUBSTRATE", "text": txt})
    return items


def _intel_items(profile, ctx: dict) -> list[dict]:
    """Indexed symbols for the prompt — only for code-shaped prompts in a repo."""
    if ctx.get("repo") is None:
        return []
    top = max(profile.intents.values()) if profile.intents else 0
    if not (profile.surfaces & {"frontend", "backend"}) and top < 3:
        return []
    try:
        from prompt_router.modules import code_intel as _ci  # noqa: PLC0415
        it = _ci.build_item(profile, ctx)
        return [it] if it else []
    except Exception:  # noqa: BLE001
        return []


def _skill_items(profile, ctx: dict) -> list[dict]:
    cfg = ctx.get("config", {})
    threshold = int(cfg.get("auto_dispatch_threshold", _select.DEFAULT_AUTO_DISPATCH_THRESHOLD))
    top_n = int(cfg.get("max_skill_pushes", _select.DEFAULT_TOP_N))
    min_score = float(cfg.get("min_skill_score", _select.DEFAULT_MIN_SCORE))
    ranked = _select.rank_skills(profile, top_n=top_n, min_score=min_score)
    ctx["_ranked"] = ranked
    meta = _select.index_meta()
    top_intent = max(profile.intents, key=profile.intents.get) if profile.intents else "GEN"
    surf_salt = "+".join(sorted(s for s in profile.surfaces if s in ("frontend", "backend", "docs"))) or "any"
    items: list[dict] = []
    for i, (name, score) in enumerate(ranked):
        label = "MUST-READ" if i == 0 else "SHOULD-READ"
        desc = " ".join(((meta.get(name) or {}).get("description") or "").split())
        if len(desc) > 120:
            desc = desc[:117].rstrip() + "..."
        tail = f" — {desc}" if desc else ""
        action = f"ACTION: Skill(\"{name}\") before the related work."
        # A `paths:`-scoped skill is not in the Skill tool's listing until a matching
        # file is touched ("Unknown skill"), so name the file; a Read counts as loaded.
        path = _select.skill_path(name) if (meta.get(name) or {}).get("paths") else None
        if path:
            action += f" Path-scoped: if the Skill tool does not list it yet, Read {path}."
        items.append({
            "id": f"skill:{name}:{top_intent}:{surf_salt}", "tier": 2, "section": "SKILLS",
            "text": f"- **{name}** ({label}){tail}\n  {action}",
            "score": round(score, 2),
        })

    # deep injection: ONE body, rank 1 only, clearly ahead of rank 2, confident intent
    deep: list[str] = []
    if ranked and profile.intents and max(profile.intents.values()) >= threshold:
        name, s1 = ranked[0]
        s2 = ranked[1][1] if len(ranked) > 1 else 0.0
        ratio = float(cfg.get("deep_inject_ratio", 1.5))
        if s1 >= ratio * s2 and name not in _select.core_skills():
            body = _skill_excerpt(name, int(cfg.get("deep_inject_chars", 3000)))
            if body:
                deep.append(name)
                items.append({"id": f"deep:{name}", "tier": 1, "section": "SKILLS",
                              "text": f"[inlined skill: {name}]\n{body}"})
    ctx["_must_read"] = [ranked[0][0]] if ranked and ranked[0][0] not in deep else []
    return items


def _routing_items(profile, ctx: dict) -> list[dict]:
    cfg = ctx.get("config", {})
    items: list[dict] = []
    if profile.is_ui:
        items.append({
            "id": "route:ui", "tier": 2, "section": "ROUTING",
            "text": ("UI signal → design-taste-frontend is the visual authority; assets via Higgsfield "
                     "(OpenArt when the project says so); scroll motion → nateherk-design:scroll-craft."),
        })
    try:
        from prompt_router.modules import mcp_routes as _mcp  # noqa: PLC0415
        items.extend(_mcp.items(profile, ctx, max_routes=int(cfg.get("max_mcp_routes", 3))))
    except Exception:  # noqa: BLE001
        pass
    threshold = int(cfg.get("auto_dispatch_threshold", _select.DEFAULT_AUTO_DISPATCH_THRESHOLD))
    max_lines = int(cfg.get("max_route_lines", 3))
    for d in _select.dispatch_tiers(profile, threshold=threshold)[:max_lines]:
        if d["kind"] == "agent" and d["agent"]:
            txt = (f"Intent {d['category']} (score {d['score']}): dispatch {d['agent']} "
                   f"via /invoke {d['act']}.")
        else:
            txt = f"Intent {d['category']} (score {d['score']}): consider /invoke {d['act']}."
        items.append({"id": f"route:{d['act']}", "tier": 3, "section": "ROUTING", "text": txt})
    items.extend(_model_mode_items(profile, ctx))
    return items


# Per-project model-mode directives. The WHOLE message must be the directive (short,
# no '?'): a question or a sentence that merely mentions "cheap mode" / "back to
# normal" must never flip or clear a repo's mode — the pin persists and overrides
# every subagent's model (Santa A2).
# "use opus for this" (no "project") is a per-TURN override the model honors itself.
_MODE_MAX_CHARS = 60
_POLITE = r"(?:(?:ok(?:ay)?|please)[,\s]+)?"
_MODE_SET = re.compile(
    rf"^{_POLITE}(?:(?:use|switch to)\s+(opus|sonnet|fable)\s+(?:for|in|on)\s+(?:this|the)\s+"
    r"(?:project|repo(?:sitory)?)"
    r"|all\s+(opus|sonnet|fable)(?:\s+mode)?"
    r"|(cheap)\s+mode)(?:[,\s]+please)?\s*[.!]*$",
    re.IGNORECASE)
_MODE_CLEAR = re.compile(
    rf"^{_POLITE}(?:back to normal|smart routing|normal routing)(?:[,\s]+please)?\s*[.!]*$",
    re.IGNORECASE)


def parse_mode_phrase(prompt: str) -> str | None:
    """'opus' | 'sonnet' | 'fable' | 'clear' | None for an explicit per-project directive."""
    text = (prompt or "").strip()
    if not text or len(text) > _MODE_MAX_CHARS or "?" in text or "\n" in text:
        return None
    m = _MODE_SET.match(text)
    if m:
        model = next(g for g in m.groups() if g).lower()
        return "sonnet" if model == "cheap" else model
    return "clear" if _MODE_CLEAR.match(text) else None


def _model_mode_items(profile, ctx: dict) -> list[dict]:
    """Per-project model-mode phrase ("use opus for this project" / "back to normal")."""
    try:
        payload = ctx.get("payload") or {}
        want = parse_mode_phrase(str(payload.get("prompt") or ""))
        if not want:
            return []
        from lib import model_mode as _mm  # noqa: PLC0415
        cwd = str(payload.get("cwd") or "")
        if want == "clear":
            # only report a clear when a pin actually existed
            if _mm.forced_mode(cwd) is None or not _mm.set_mode(cwd, None):
                return []
        elif not _mm.set_mode(cwd, want):
            return []
        repo = ctx.get("repo")
        where = repo.name if repo is not None else "this project"
        text = (f"Per-project model mode cleared for {where}; smart routing restored."
                if want == "clear" else
                f"Per-project model mode set to {want} for {where}; subagents will be "
                "pinned. Say 'back to normal' to clear.")
        return [{"id": f"route:model-mode:{want}", "tier": 3, "section": "ROUTING", "text": text}]
    except Exception:  # noqa: BLE001
        return []


def _model_items(profile) -> list[dict]:
    try:
        from prompt_router.modules import model_advice as _ma  # noqa: PLC0415
        advice = _ma.advise(profile)
        if advice:
            return [{"id": "model:advice", "tier": 3, "section": "MODEL", "text": advice}]
    except Exception:  # noqa: BLE001
        pass
    return []


def _builtin_items(profile, ctx: dict) -> list[dict]:
    items = _gate_items(profile, ctx)
    items += _substrate_items(profile, ctx)
    items += _intel_items(profile, ctx)
    items += _skill_items(profile, ctx)
    items += _routing_items(profile, ctx)
    items += _model_items(profile)
    return items


def _gather_items(profile, ctx: dict) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for it in _builtin_items(profile, ctx):
        iid = it.get("id")
        if iid and iid in seen:
            continue
        if iid:
            seen.add(iid)
        merged.append(it)
    return merged


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
_SECTION_ORDER = ["GATES", "SUBSTRATE", "INTEL", "SKILLS", "ROUTING", "MODEL"]
_SECTION_TITLE = {
    "GATES": "Critical directives",
    "SUBSTRATE": "Tool precedence",
    "INTEL": "Indexed symbols",
    "SKILLS": "Skills for this task",
    "ROUTING": "Suggested routing",
    "MODEL": "Model",
}


def _render(items: list[dict]) -> str:
    by_section: dict[str, list[str]] = {}
    for it in items:
        by_section.setdefault(it.get("section", "ROUTING"), []).append(it.get("text", ""))
    chunks: list[str] = []
    for sec in _SECTION_ORDER:
        lines = by_section.get(sec)
        if lines:
            chunks.append(f"[{_SECTION_TITLE.get(sec, sec)}]\n" + "\n".join(lines))
    return "\n\n".join(chunks).strip()


# --------------------------------------------------------------------------- #
# Entry
# --------------------------------------------------------------------------- #
def _read_payload() -> dict:
    try:
        raw = sys.stdin.read() or "{}"
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _sid(payload: dict) -> str:
    for k in ("session_id", "sessionId", "session"):
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v
    return "nosession"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(argv: list[str]) -> int:  # noqa: ARG001 - argv kept for the CLI shape
    payload = _read_payload()
    sid = _sid(payload)
    cfg = _config()

    profile = _classify.classify(payload)
    if profile.trivial_ack:
        _emit_empty()
        return 0

    ctx = {
        "sid": sid,
        "config": cfg,
        "payload": payload,
        "profile": profile,
        "repo": _repo.active_repo(payload) if _repo is not None else None,
    }

    items = _gather_items(profile, ctx)
    emitted_ids = _manifest.load(sid)
    kept, suppressed = _manifest.dedup(items, emitted_ids)
    included, _dropped = _budget.apply(kept)
    body = _render(included)

    _manifest.commit(sid, emitted_ids, included)
    _record_pushed_skills(sid, ctx, included, profile)
    if _tel is not None:
        _tel.record("UserPromptSubmit", "prompt_router.live", session=sid, chars_out=len(body),
                    intents=profile.intents, surfaces=sorted(profile.surfaces),
                    surface_source=profile.surface_source, size=profile.size, risk=profile.risk,
                    n_items=len(items), n_included=len(included), n_suppressed=len(suppressed),
                    emitted_ids=[it.get("id") for it in included],
                    skills=[n for n, _ in (ctx.get("_ranked") or [])])
    if body:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": MARKER + "\n" + body,
        }}))
    else:
        _emit_empty()
    return 0


def _record_pushed_skills(sid: str, ctx: dict, included: list, profile) -> None:
    """Enforcement bridge: the rank-1 MUST-READ that actually got emitted is
    recorded for invoke-suite-gate (source=router, enforce=hard). A deep-injected
    skill is excluded — its content was delivered inline."""
    try:
        must = [n for n in (ctx.get("_must_read") or [])
                if any((it.get("id") or "").startswith(f"skill:{n}:") for it in included)]
        if not must:
            return
        tel_dir = _HOOKS / ".telemetry"
        tel_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (sid or "unknown"))
        rec = {"ts": _utc_now(), "skills": must,
               "categories": sorted(profile.intents or []), "source": "router", "enforce": "hard"}
        with open(tel_dir / f"{safe}.pushed-skills.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _emit_empty() -> None:
    try:
        print(json.dumps({}))
    except Exception:  # noqa: BLE001
        sys.stdout.write("{}")


def main(argv: list[str]) -> int:
    try:
        return run(argv)
    except Exception as exc:  # noqa: BLE001 - router must be fail-open
        try:
            if _tel is not None:
                _tel.record("UserPromptSubmit", "prompt_router.fail_open", error=str(exc)[:300])
        except Exception:  # noqa: BLE001
            pass
        _emit_empty()
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
