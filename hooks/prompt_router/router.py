#!/usr/bin/env python3
"""router.py — the single-process unified prompt router (P1-T2).

Pipeline (Charter v3 §1/§2):
  S0  ingest stdin payload + trivial fast-exit ONLY on an exact-match ack
      (yes/ok/continue/... — the legacy "<12 chars" heuristic is DROPPED).
  S1  ONE classification pass -> TaskProfile (classify.py, consumes trigger floor).
  S2  ranked skill selection (select.py) + suggest/dispatch tiering, with
      session-manifest dedup (never suppresses a first fire).
  S4  substrate precedence: jcodemunch>lean-ctx (code), jdocmunch>lean-ctx
      (docs), sequential-thinking, dox — ALL applicable directives (no cap-2).
  S5  priority-ordered budget: max 24,000 tokens, tier-0 first, drops logged.
  S6  ONE additionalContext emit + state/<sid>.router-manifest.json.

Modes:
  (default)   live inject: prints {"additionalContext": "..."} to stdout.
  --shadow    log-only: computes the SAME would-be injection, writes it to
              ~/.claude/telemetry/<sid>.router-shadow.jsonl, and emits NOTHING
              (legacy injectors still run alongside — Charter §2 migration).
  --stop      Stop-event stub (effectiveness record + flush hook) — filled by P4.

S3 delegate modules (P1-T4) are IMPORTED when present and their items merged
(delegate wins by id); until then the built-in item builders below keep the
router fully functional. Fail-open at module and router level: any exception
yields a valid empty emit so the prompt always flows.
"""

from __future__ import annotations

import json
import sys
import time
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
    from lib import platform as _plat
    from lib import repo_context as _repo
except Exception:  # noqa: BLE001
    _tel = _plat = _repo = None  # type: ignore


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def _config() -> dict:
    try:
        return json.loads((_HOOKS / "prompt_router" / "router.config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# --------------------------------------------------------------------------- #
# Built-in item builders (S4 substrate + tier-0 gates + S2 skills + routing)
# item := {id, tier, section, text}
# --------------------------------------------------------------------------- #
_DOC_KEYWORDS = ("readme", "docs", "documentation", "changelog", ".md", "guide", "adr")


def _builtin_items(profile, ctx: dict) -> list[dict]:
    items: list[dict] = []
    in_repo = ctx.get("repo") is not None
    has_code_paths = bool(profile.paths)
    cfg = ctx.get("config", {})
    threshold = int(cfg.get("auto_dispatch_threshold", _select.DEFAULT_AUTO_DISPATCH_THRESHOLD))

    # ---- tier 0: gate-adjacent directives ----
    if profile.first_write_candidate or has_code_paths:
        items.append({
            "id": "firstwrite:baseline", "tier": 0, "section": "GATES",
            "text": ("First substantive change this session — read the project map first: "
                     "project-structure-map, project-reference-linkage, codebase-start-point-guide; "
                     "and run the dead-code-and-change-audit on your changes."),
        })
    if in_repo and (has_code_paths or {"IMPLEMENT", "TEST"} & set(profile.intents)):
        items.append({
            "id": "gate:tdd", "tier": 0, "section": "GATES",
            "text": ("TDD doctrine: write the failing test first, then implement "
                     "(tdd-guard runs in warn mode — treat its advisory as a directive)."),
        })
    if in_repo and (has_code_paths or profile.first_write_candidate):
        items.append({
            "id": "gate:dox", "tier": 0, "section": "GATES",
            "text": "dox: read root->target CLAUDE.md before editing; update the local CLAUDE.md after.",
        })

    # ---- tier 1: substrate precedence (ALL applicable — no cap) ----
    code_intent = has_code_paths or profile.is_arch or bool(
        {"IMPLEMENT", "DEBUG", "REVIEW", "AUDIT", "CLEANUP", "SPEC", "PLAN"} & set(profile.intents))
    if code_intent:
        items.append({
            "id": "substrate:jcodemunch", "tier": 1, "section": "SUBSTRATE",
            "text": ("Code work: use jcodemunch FIRST for discovery AND reading "
                     "(search_symbols/get_symbol_source/assemble_task_context), "
                     "then graphify for blast-radius; lean-ctx only for residual non-code."),
        })
    docs_signal = ("docs" in profile.surfaces) or any(k in profile.text for k in _DOC_KEYWORDS)
    if docs_signal:
        items.append({
            "id": "substrate:jdocmunch", "tier": 1, "section": "SUBSTRATE",
            "text": ("Docs work: use jdocmunch (search_sections/get_toc/get_section) over "
                     "whole-file reads; lean-ctx only for single small non-doc files."),
        })
    if profile.is_reasoning:
        items.append({
            "id": "substrate:seqthink", "tier": 1, "section": "SUBSTRATE",
            "text": ("Reasoning-shaped task: externalize reasoning via sequential-thinking "
                     "before deciding/planning/auditing/debugging."),
        })
    if profile.is_arch:
        items.append({
            "id": "substrate:graphify", "tier": 1, "section": "SUBSTRATE",
            "text": ("Architecture/dependency question: use graphify (god_nodes/get_neighbors/"
                     "shortest_path/query_graph) for structure instead of manual grep."),
        })

    # ---- tier 2: ranked skill pushes (per-skill ids so a NEW skill always fires) ----
    ranked = _select.rank_skills(profile, top_n=int(cfg.get("max_skill_pushes", 8)))
    labels = ["MUST-READ", "SHOULD-READ", "REFERENCE"]
    for i, (name, score) in enumerate(ranked):
        label = labels[min(i, len(labels) - 1)] if i < 2 else "REFERENCE"
        items.append({
            "id": f"skill:{name}", "tier": 2, "section": "SKILLS",
            "text": f"- {name} ({label})",
            "score": round(score, 2),
        })

    # ---- UI-stack lightweight suggestion (single ui_keyword hit is enough; the
    #      EXPENSIVE stack dump is what gets gated, not the suggestion — P1-T6) ----
    if profile.is_ui:
        items.append({
            "id": "route:ui", "tier": 2, "section": "ROUTING",
            "text": ("UI/UX signal: use the craft stack (impeccable / taste-skill / "
                     "ui-ux-pro-max / huashu-design / frontend-ui-engineering) and source "
                     "every raster/video/3D/audio asset from Higgsfield (no placeholders/stock)."),
        })

    # ---- tier 3: routing (suggest vs dispatch) + model advice ----
    for d in _select.dispatch_tiers(profile, threshold=threshold):
        if d["kind"] == "agent" and d["agent"]:
            txt = (f"Intent {d['category']} (score {d['score']}): dispatch {d['agent']} "
                   f"via /invoke {d['act']} (score >= {threshold}).")
        else:
            txt = f"Intent {d['category']} (score {d['score']}): consider /invoke {d['act']}."
        items.append({"id": f"route:{d['act']}", "tier": 3, "section": "ROUTING", "text": txt})

    return items


def _delegate_items(profile, ctx: dict) -> list[dict]:
    """S3: import delegate modules (P1-T4) when present; each wraps an original
    injector hook. Merged into the built-in set (delegate wins by id). Fail-open."""
    try:
        from prompt_router import modules as _mods  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    collect = getattr(_mods, "collect", None)
    if not callable(collect):
        return []
    try:
        out = collect(profile, ctx)
        return out if isinstance(out, list) else []
    except Exception:  # noqa: BLE001 - a delegate crash must not break routing
        return []


def _gather_items(profile, ctx: dict) -> list[dict]:
    builtin = _builtin_items(profile, ctx)
    delegated = _delegate_items(profile, ctx)
    # delegate items first so they WIN on id collision; dedup preserves first
    merged: list[dict] = []
    seen: set[str] = set()
    for it in delegated + builtin:
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
_SECTION_ORDER = ["GATES", "SUBSTRATE", "SKILLS", "ROUTING", "MODEL"]
_SECTION_TITLE = {
    "GATES": "Critical directives",
    "SUBSTRATE": "Tool precedence",
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


def _shadow_log(sid: str, record: dict) -> None:
    if _plat is None:
        return
    try:
        path = _plat.telemetry_dir() / f"{sid}.router-shadow.jsonl"
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        import os as _os
        fd = _os.open(str(path), _os.O_WRONLY | _os.O_CREAT | _os.O_APPEND, 0o644)
        try:
            _os.write(fd, line.encode("utf-8", "replace"))
        finally:
            _os.close(fd)
    except OSError:
        pass


def run(argv: list[str]) -> int:
    shadow = "--shadow" in argv
    stop = "--stop" in argv
    payload = _read_payload()
    sid = _sid(payload)

    if stop:
        return _run_stop(payload, sid)

    prompt = str(payload.get("prompt") or "")
    cfg = _config()

    # S1 classify (fail-open inside classify)
    profile = _classify.classify(payload)

    # S0 trivial ack fast-exit (exact allowlist ONLY)
    if profile.trivial_ack:
        if shadow:
            _shadow_log(sid, {"ts": round(time.time(), 3), "prompt": prompt[:80],
                              "decision": "trivial_ack_exit", "emitted": []})
        _emit_empty()
        return 0

    ctx = {
        "sid": sid,
        "config": cfg,
        "repo": _repo.active_repo(payload) if _repo is not None else None,
        "mode": "shadow" if shadow else "live",
    }

    # gather -> dedup -> budget
    items = _gather_items(profile, ctx)
    emitted_ids = _manifest.load(sid)
    kept, suppressed = _manifest.dedup(items, emitted_ids)
    max_tokens = int(cfg.get("max_tokens_per_prompt", _budget.DEFAULT_MAX_TOKENS))
    included, dropped = _budget.apply(kept, max_tokens=max_tokens)

    body = _render(included)

    telem = {
        "session": sid, "intents": profile.intents, "surfaces": sorted(profile.surfaces),
        "size": profile.size, "risk": profile.risk,
        "n_items": len(items), "n_included": len(included),
        "n_suppressed": len(suppressed), "n_dropped": len(dropped),
        "emitted_ids": [it.get("id") for it in included],
        "dropped_ids": [it.get("id") for it in dropped],
    }
    if dropped and _tel is not None:
        for it in dropped:
            _tel.record("UserPromptSubmit", "prompt_router.budget_drop",
                        session=sid, item=it.get("id"), reason=it.get("_drop_reason"))

    if shadow:
        _shadow_log(sid, {"ts": round(time.time(), 3), "prompt": prompt[:120],
                          "would_emit": body, **telem})
        if _tel is not None:
            _tel.record("UserPromptSubmit", "prompt_router.shadow", **telem)
        _emit_empty()   # shadow NEVER injects — legacy stack still runs
        return 0

    # live: commit manifest + emit
    _manifest.commit(sid, emitted_ids, included)
    if _tel is not None:
        _tel.record("UserPromptSubmit", "prompt_router.live", chars_out=len(body), **telem)
    if body:
        print(json.dumps({"additionalContext": body}))
    else:
        _emit_empty()
    return 0


def _run_stop(payload: dict, sid: str) -> int:
    """--stop stub: effectiveness record + flush hook home (filled by P4-T9/P4).
    Fail-open no-op emit today so registering it is safe."""
    if _tel is not None:
        _tel.record("Stop", "prompt_router.stop", session=sid, decision="stub")
    _emit_empty()
    return 0


def _emit_empty() -> None:
    # A bare empty object is a valid no-op for UserPromptSubmit / Stop.
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
