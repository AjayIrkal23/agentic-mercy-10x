#!/usr/bin/env python3
"""intel-router.py — the tri-tool code/doc-intelligence router (smartness layer).

UserPromptSubmit: classify the prompt into the ONE intelligence surface that fits
and emit a single directive naming the exact tool to reach for first — instead of
three overlapping, siloed nudges. Surfaces:

  code structure  → jcodemunch  (symbols, callers, refs, blast radius, dead code)
  architecture    → graphify    (dependency / community / path / hotspot)  [needs a graph]
  documentation   → jdocmunch   (section index)                            [needs a doc index]

Availability-aware: never routes to graphify without a built graph, or to
jdocmunch without a doc index — it falls back to the next best available surface
(and, for the top pick, adds a one-line "build it" directive). Advisory,
fail-open, throttled. The per-surface read gates still ENFORCE their own reads;
this only decides WHICH surface fits the prompt.

Mode (sys.argv[1]): prompt-submit (default) → UserPromptSubmit.
"""

import json
import os
import sys
from pathlib import Path

HOME = Path.home()
HOOKS_DIR = Path(__file__).parent
CONFIG_PATH = HOOKS_DIR / "intel-router.config.json"
STATE_DIR = HOOKS_DIR / ".state"
DOC_INDEX_DIR = HOME / ".doc-index" / "local"

DEFAULT_CONFIG = {
    "max_directives_per_session": 12,
    "tie_break": ["graphify", "jdocmunch", "jcodemunch"],
    "surfaces": {
        "jcodemunch": {
            "label": "code-structure",
            "keywords": [
                "symbol", "function", "method", "class ", "caller", "who calls",
                "references to", "find references", "where is", "where's",
                "definition of", "blast radius", "impact of changing", "dead code",
                "unused", "rename", "call hierarchy", "importers", "who imports",
                "implementation of", "signature", "find the function", "trace the call",
            ],
            "call": 'mcp__jcodemunch__search_symbols · get_symbol_source · find_references · get_blast_radius',
        },
        "graphify": {
            "label": "architecture/dependency",
            "keywords": [
                "architecture", "architectural", "dependency", "dependencies",
                "coupling", "hotspot", "god node", "shortest path", "dependency graph",
                "call graph", "module structure", "module graph", "data flow",
                "control flow", "how is it wired", "wired together", "depends on",
                "connected to", "how are they connected", "overall structure",
                "high-level structure", "community", "clusters",
            ],
            "call": 'mcp__graphify__query_graph "<q>" · god_nodes · get_neighbors · shortest_path',
        },
        "jdocmunch": {
            "label": "documentation",
            "keywords": [
                "documentation", "the docs", "readme", "how-to", "howto",
                "tutorial", "getting started", "api reference", "reference docs",
                "changelog", "per the docs", "in the docs", "user guide",
                "explain the concept", "what does the doc", "guide for",
            ],
            "call": 'mcp__jdocmunch__search_sections "<q>" · get_toc · get_section',
        },
    },
}


def _load_config() -> dict:
    try:
        user = json.loads(CONFIG_PATH.read_text())
        cfg = dict(DEFAULT_CONFIG)
        cfg.update({k: v for k, v in user.items() if k != "surfaces"})
        if isinstance(user.get("surfaces"), dict):
            surfaces = dict(DEFAULT_CONFIG["surfaces"])
            surfaces.update(user["surfaces"])
            cfg["surfaces"] = surfaces
        return cfg
    except Exception:
        return DEFAULT_CONFIG


def _state_path(cid: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{cid}.intel-router.json"


def _load_state(cid: str) -> dict:
    try:
        return json.loads(_state_path(cid).read_text())
    except Exception:
        return {"directive_count": 0}


def _save_state(cid: str, state: dict):
    try:
        _state_path(cid).write_text(json.dumps(state))
    except Exception:
        pass


def _repo_root() -> Path:
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        from lib.repo_context import git_root
        r = git_root(cwd)
        if r is not None:
            return r
    except Exception:
        pass
    return Path(cwd)


def _graph_exists(root: Path) -> bool:
    return (root / "graphify-out" / "graph.json").is_file()


def _doc_index_exists(root: Path) -> bool:
    name = root.name
    cands = [f"{name}.json"]
    try:
        from lib.repo_context import sanitize_name
        s = sanitize_name(name)
        if s and s != name:
            cands.append(f"{s}.json")
    except Exception:
        pass
    return any((DOC_INDEX_DIR / c).is_file() for c in cands)


def _available(name: str, root: Path) -> bool:
    if name == "graphify":
        return _graph_exists(root)
    if name == "jdocmunch":
        return _doc_index_exists(root)
    return True  # jcodemunch is index-guarded; treat as always reachable


def _extract_prompt(hook_input: dict) -> str:
    prompt = hook_input.get("prompt", "")
    if isinstance(prompt, dict):
        content = prompt.get("content", "")
        if isinstance(content, list):
            return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        return content if isinstance(content, str) else ""
    return prompt if isinstance(prompt, str) else ""


def _score(text: str, keywords: list) -> int:
    return sum(1 for k in keywords if k in text)


def _ranked(text: str, cfg: dict) -> list:
    """Surfaces with score > 0, best first; ties broken by cfg['tie_break'] order."""
    surfaces = cfg["surfaces"]
    scored = {name: _score(text, s.get("keywords", [])) for name, s in surfaces.items()}
    order = cfg.get("tie_break", list(surfaces.keys()))
    ranked = [n for n in surfaces if scored.get(n, 0) > 0]
    ranked.sort(key=lambda n: (-scored[n], order.index(n) if n in order else 99))
    return ranked


def handle_prompt_submit():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        json.dump({"continue": True}, sys.stdout)
        return

    cfg = _load_config()
    session_id = hook_input.get("session_id", "unknown")
    text = _extract_prompt(hook_input).lower()
    if not text:
        json.dump({"continue": True}, sys.stdout)
        return

    ranked = _ranked(text, cfg)
    if not ranked:
        json.dump({"continue": True}, sys.stdout)
        return

    state = _load_state(session_id)
    if state.get("directive_count", 0) >= cfg.get("max_directives_per_session", 12):
        json.dump({"continue": True}, sys.stdout)
        return

    root = _repo_root()
    surfaces = cfg["surfaces"]

    # Pick the best AVAILABLE surface; remember the top pick for a build hint.
    top = ranked[0]
    pick = next((n for n in ranked if _available(n, root)), None)

    if pick is None:
        # Top-scoring surface is unavailable and nothing else scored: route to the
        # top pick anyway with a one-line "build it" directive (freshness parity).
        s = surfaces[top]
        if top == "graphify":
            ctx = (f"[Intel router] This looks like a {s['label']} question → graphify, "
                   f"but no graph exists yet for this repo. Build it: `graphify update {root}`, "
                   f"then use {s['call']}.")
        elif top == "jdocmunch":
            ctx = (f"[Intel router] This looks like a {s['label']} question → jDocMunch, "
                   f"but this repo's docs aren't indexed yet. Index them "
                   f"(`jdocmunch-mcp index-local --path {root} --name {root.name}`), "
                   f"then use {s['call']}.")
        else:
            ctx = f"[Intel router] {s['label']} question → use {s['call']} first."
    else:
        s = surfaces[pick]
        ctx = f"[Intel router] This looks like a {s['label']} question → use {pick} first: {s['call']}."
        if pick != top and not _available(top, root):
            ts = surfaces[top]
            ctx += (f"  ({ts['label']} would fit too — build that surface to use it: "
                    + ("`graphify update {}`".format(root) if top == "graphify" else "index the docs")
                    + ".)")

    state["directive_count"] = state.get("directive_count", 0) + 1
    _save_state(session_id, state)
    json.dump({"continue": True, "additionalContext": ctx}, sys.stdout)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt-submit"
    try:
        if mode == "prompt-submit":
            handle_prompt_submit()
        else:
            json.dump({"continue": True}, sys.stdout)
    except Exception:
        json.dump({"continue": True}, sys.stdout)
