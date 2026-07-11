#!/usr/bin/env python3
"""codebase-intel-router.py — task-aware jcodemunch + graphify directive injector.

Role: UserPromptSubmit sub-hook (invoked by token-stack-prompt-reminder.py).
Reads the hook payload on stdin, classifies the user's task, and emits a
task-specific directive naming the EXACT jcodemunch + graphify MCP calls to run
FIRST — before native Read/Grep/Glob or lean-ctx ctx_read on source files.

This is the recurring, phase-aware layer that the once-per-session jcodemunch
reminder and the arch-keyword-only graphify reminder do not cover. It is the
"use them in planning / auditing / coding / debugging — every time" enforcer.

Noise control: a given task-type's full directive is emitted at most ONCE per
session. Repeat turns of an already-seen type stay silent. Trivial/short prompts
stay silent. Fails OPEN: any error -> emit "{}" (no output).

Output contract: prints {"additionalContext": "<text>"} (the key the parent
wrapper merges) or "{}" when silent.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

HOME = Path.home()
INDEX_DIR = HOME / ".code-index"
STATE_DIR = Path(__file__).resolve().parent / ".state"

# --------------------------------------------------------------------------
# Task classification keywords (checked in priority order).
# --------------------------------------------------------------------------

AUDIT_KW = (
    "audit", "review", "dead code", "deadcode", "unused", "blast radius",
    "impact", "coupling", "hotspot", "hot spot", "tech debt", "technical debt",
    "debt", "complexity", "what breaks", "what would break", "safe to delete",
    "safe to remove", "safe to change", "cleanup", "clean up", "desloppify",
    "find all", "every place", "all call sites", "all usages", "all references",
    "security review", "smell", "duplicat", "consolidat",
)
DEBUG_KW = (
    "debug", "bug", "error", "failing", "fails", "broken", "not working",
    "doesn't work", "does not work", "traceback", "exception", "stack trace",
    "stacktrace", "reproduce", "regression", "crash", "panic", "why is",
    "why does", "root cause", "trace the", "trace through",
)
PLAN_KW = (
    "plan", "architect", "architecture", "design", "understand", "overview",
    "how does", "how do", "orient", "onboard", "where is", "where does",
    "structure", "big picture", "walk me through", "explain", "mental model",
    "roadmap", "approach", "strategy", "high level", "high-level", "map out",
    "data flow", "request flow", "control flow", "entry point", "wired",
)
IMPLEMENT_KW = (
    "add", "implement", "build", "create", "write", "endpoint", "component",
    "feature", "integrate", "wire up", "hook up", "function", "route",
    "migration", "schema", "handler", "controller", "service", "rename",
    "refactor", "extend", "support for", "new ", "change the", "update the",
    "modify", "fix the",
)

# Conversational / trivial openers that should never trigger a directive.
TRIVIAL_EXACT = {
    "yes", "no", "ok", "okay", "go", "go ahead", "continue", "proceed",
    "do it", "yep", "yeah", "sure", "thanks", "thank you", "stop", "wait",
    "nice", "good", "great", "perfect", "next", "done",
}


def _read_payload() -> dict:
    raw = sys.stdin.read() or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _extract_prompt(payload: dict) -> str:
    prompt = payload.get("prompt", "")
    if isinstance(prompt, dict):
        content = prompt.get("content", "")
        if isinstance(content, list):
            return " ".join(
                p.get("text", "") for p in content if isinstance(p, dict)
            )
        return str(content)
    if isinstance(prompt, list):
        return " ".join(p.get("text", "") for p in prompt if isinstance(p, dict))
    return str(prompt or payload.get("user_message") or "")


def _find_git_root(start: Path) -> Path | None:
    cur = start if start.is_dir() else start.parent
    for _ in range(25):
        if (cur / ".git").exists():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def _workspace_root(payload: dict) -> Path | None:
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots:
        p = Path(str(roots[0]))
        if p.is_dir():
            return _find_git_root(p) or p
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return _find_git_root(Path(cwd))


def _jcodemunch_index_present(root: Path) -> bool:
    try:
        h = hashlib.sha1(str(root).encode()).hexdigest()[:8]
        candidates = [
            INDEX_DIR / f"local-{root.name}-{h}.db",
            INDEX_DIR / f"AjayIrkal23-{root.name}.db",
        ]
        return any(c.is_file() for c in candidates)
    except Exception:
        return False


def _graphify_graph_present(root: Path) -> bool:
    return (root / "graphify-out" / "graph.json").is_file()


def _classify(text: str) -> str:
    t = text.lower().strip()
    if not t or t in TRIVIAL_EXACT or len(t.split()) < 3:
        return "trivial"
    # Priority order: audit > debug > plan > implement.
    if any(k in t for k in AUDIT_KW):
        return "audit"
    if any(k in t for k in DEBUG_KW):
        return "debug"
    if any(k in t for k in PLAN_KW):
        return "plan"
    if any(k in t for k in IMPLEMENT_KW):
        return "implement"
    return "explore"


# --------------------------------------------------------------------------
# Per-session state (emit each task-type's directive at most once).
# --------------------------------------------------------------------------


def _state_path(session_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    return STATE_DIR / f"{safe}.intel-router.json"


def _load_emitted(session_id: str) -> set[str]:
    try:
        data = json.loads(_state_path(session_id).read_text(encoding="utf-8"))
        seen = data.get("emitted_types", [])
        return set(seen) if isinstance(seen, list) else set()
    except Exception:
        return set()


def _mark_emitted(session_id: str, seen: set[str]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state_path(session_id).write_text(
            json.dumps({"emitted_types": sorted(seen)}), encoding="utf-8"
        )
    except Exception:
        pass


# --------------------------------------------------------------------------
# Directive bodies.
# --------------------------------------------------------------------------

_TAIL = (
    "Run these FIRST — before native Read/Grep/Glob or lean-ctx ctx_read/ctx_search "
    "on source. READ code via get_symbol_source / get_file_outline / "
    "assemble_task_context / get_context_bundle — not ctx_read. Reserve ctx_read for "
    "the exact files these tools surface, and for docs/config/markdown. One "
    "graph/index call replaces dozens of file reads."
)

DIRECTIVES = {
    "plan": (
        "### Codebase-intel first — PLANNING\n"
        "Build your mental model from the pre-computed graph + symbol index, not by reading files blind:\n"
        "- `mcp__graphify__graph_stats` then `mcp__graphify__god_nodes` — entry points / most-connected modules\n"
        "- `mcp__graphify__query_graph \"<your question>\"` — natural-language structure query\n"
        "- `mcp__graphify__get_community <id>` — modules that cluster together\n"
        "- `mcp__jcodemunch__get_repo_map` / `get_repo_outline` / `get_tectonic_map` — high-level layout\n"
        "- `mcp__jcodemunch__assemble_task_context` / `get_context_bundle` / `plan_turn` — relevant code + a change plan in one shot\n"
        "- `mcp__jcodemunch__search_symbols \"<name>\"` + `get_symbol_source` — pinpoint specifics\n"
        + _TAIL
    ),
    "audit": (
        "### Codebase-intel first — AUDIT / REVIEW\n"
        "Use the index + graph for complete, ranked results — manual greps miss cross-module edges:\n"
        "- `mcp__jcodemunch__find_dead_code` / `get_dead_code_v2` / `find_unused_paths` — unreachable code\n"
        "- `mcp__jcodemunch__get_blast_radius \"<symbol>\"` — what a change ripples into\n"
        "- `mcp__jcodemunch__get_coupling_metrics` / `get_hotspots` / `get_churn_rate` — risk + churn\n"
        "- `mcp__jcodemunch__get_file_risk` / `get_repo_health` / `get_pr_risk_profile` — quantified risk\n"
        "- `mcp__jcodemunch__get_symbol_complexity` / `get_untested_symbols` / `get_extraction_candidates` — debt\n"
        "- `mcp__jcodemunch__find_references` / `find_importers \"<symbol>\"` — every call site\n"
        "- `mcp__graphify__god_nodes` + `mcp__graphify__get_neighbors \"<node>\"` + `mcp__graphify__query_graph`\n"
        + _TAIL
    ),
    "implement": (
        "### Codebase-intel first — IMPLEMENT / CHANGE\n"
        "Locate and scope before editing so you don't miss call sites:\n"
        "- `mcp__jcodemunch__plan_turn` / `assemble_task_context` — assemble the whole change slice in one call\n"
        "- `mcp__jcodemunch__search_symbols \"<name>\"` + `mcp__jcodemunch__get_symbol_source` — pinpoint the code\n"
        "- `mcp__jcodemunch__find_references` / `find_importers` — ALL callers before you change a signature\n"
        "- `mcp__jcodemunch__get_blast_radius` / `get_impact_preview \"<symbol>\"` — before touching anything shared\n"
        "- `mcp__jcodemunch__check_rename_safe` / `check_delete_safe` — before a rename or delete\n"
        "- `mcp__graphify__get_neighbors \"<file>\"` — who depends on what you're about to change\n"
        "Note: blind source reads (native Read/Grep AND lean-ctx ctx_read/ctx_search) are gated until jcodemunch is consulted.\n"
        + _TAIL
    ),
    "debug": (
        "### Codebase-intel first — DEBUG\n"
        "Trace through the graph + call index, not blind grep:\n"
        "- `mcp__jcodemunch__get_call_hierarchy \"<fn>\"` — callers + callees\n"
        "- `mcp__jcodemunch__find_references` / `find_implementations` — where it's wired\n"
        "- `mcp__jcodemunch__get_signal_chains` / `find_hot_paths` — data/control flow chains\n"
        "- `mcp__jcodemunch__get_related_symbols` — what else moves with this code\n"
        "- `mcp__graphify__shortest_path \"<A>\" \"<B>\"` — how two symbols connect\n"
        + _TAIL
    ),
    "explore": (
        "Codebase-intel tip: before broad Read/grep OR ctx_read on source, try "
        "`mcp__jcodemunch__assemble_task_context` / `get_context_bundle`, "
        "`mcp__jcodemunch__search_symbols \"<name>\"`, or `mcp__graphify__query_graph \"<question>\"` "
        "— one call, ~95% fewer tokens than file sweeps."
    ),
}

MISSING_DIRECTIVE = (
    "### Codebase-intel: index/graph NOT built for this project yet\n"
    "Before broad exploration, build them (cheap, local, no LLM):\n"
    "- jcodemunch: `mcp__jcodemunch__index_folder({{\"path\": \"{root}\"}})`\n"
    "- graphify: run `graphify update {root}` via Bash\n"
    "Then use `mcp__jcodemunch__search_symbols` / `mcp__graphify__query_graph` instead of Read/grep."
)


def main() -> int:
    try:
        payload = _read_payload()
        session_id = (
            payload.get("session_id")
            or payload.get("conversation_id")
            or "unknown"
        )
        text = _extract_prompt(payload)
        task = _classify(text)
        if task == "trivial":
            print("{}")
            return 0

        root = _workspace_root(payload)
        if root is None:
            print("{}")
            return 0

        seen = _load_emitted(session_id)

        has_index = _jcodemunch_index_present(root)
        has_graph = _graphify_graph_present(root)

        # Index/graph missing -> emit build directive once.
        if not has_index and not has_graph:
            if "missing" in seen:
                print("{}")
                return 0
            seen.add("missing")
            _mark_emitted(session_id, seen)
            print(json.dumps({"additionalContext": MISSING_DIRECTIVE.format(root=root)}))
            return 0

        # Already emitted this task-type's directive this session -> stay silent.
        if task in seen:
            print("{}")
            return 0

        body = DIRECTIVES.get(task)
        if not body:
            print("{}")
            return 0

        seen.add(task)
        _mark_emitted(session_id, seen)

        fresh_bits = []
        if has_graph:
            fresh_bits.append("graph")
        if has_index:
            fresh_bits.append("symbol index")
        if fresh_bits:
            body = body + f"\n(Ready: {' + '.join(fresh_bits)} present for `{root.name}`; kept fresh event-driven by index-lifecycle.)"

        print(json.dumps({"additionalContext": body}))
        return 0
    except Exception:
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
