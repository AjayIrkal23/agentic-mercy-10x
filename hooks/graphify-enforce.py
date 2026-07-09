#!/usr/bin/env python3
"""graphify-enforce.py — Nudge graphify MCP usage for architecture/dependency work.

Modes (sys.argv[1]):
  prompt-submit   → UserPromptSubmit: keyword-triggered graphify reminder
  pre-tool-use    → PreToolUse on Agent|Bash: nudge before broad exploration
"""

import json, os, re, sys
from pathlib import Path

from tool_compat import is_agent_tool, is_shell_tool, tool_name as compat_tool_name

HOOKS_DIR = Path(__file__).parent
CONFIG_PATH = HOOKS_DIR / "graphify-enforce.config.json"
STATE_DIR = HOOKS_DIR / ".state"

GRAPHIFY_REMINDER = (
    "[Graphify] Architecture graph is available. Use graphify MCP tools BEFORE broad exploration or Explore agents:\n"
    "  - mcp__graphify__query_graph \"<question>\" — search dependency graph (natural language)\n"
    "  - mcp__graphify__get_neighbors \"<node>\" — who imports/depends on a module\n"
    "  - mcp__graphify__god_nodes — find hotspots (most-connected files)\n"
    "  - mcp__graphify__shortest_path \"<A>\" \"<B>\" — trace dependency path\n"
    "  - mcp__graphify__get_community <id> — modules that cluster together\n"
    "  - mcp__graphify__graph_stats — overall graph statistics\n"
    "Graphify gives you the dependency/architecture map in ONE call vs dozens of grep/Read. Use it."
)

AGENT_NUDGE = (
    "[Graphify] Before spawning Explore agents for architecture/dependency questions, "
    "query mcp__graphify__query_graph or mcp__graphify__god_nodes first — "
    "the graph has pre-computed dependency and community data that answers most "
    "structural questions in a single call."
)

BASH_NUDGE = (
    "[Graphify] This looks like a broad codebase search. Consider mcp__graphify__query_graph "
    "or mcp__graphify__get_neighbors instead — the graph has pre-indexed dependencies."
)


def _load_config():
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {
            "arch_keywords": ["architecture", "dependency", "coupling", "hotspot", "impact", "refactor"],
            "explore_keywords": ["find", "search", "explore", "grep across"],
            "remind_every_n_matches": 2,
            "max_reminders_per_session": 8,
            "graph_json_relative": "graphify-out/graph.json",
        }


def _state_path(cid: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{cid}.graphify-enforce.json"


def _load_state(cid: str) -> dict:
    sp = _state_path(cid)
    try:
        return json.loads(sp.read_text())
    except Exception:
        return {"match_count": 0, "remind_count": 0}


def _save_state(cid: str, state: dict):
    _state_path(cid).write_text(json.dumps(state))


def _graph_exists() -> bool:
    cwd = os.environ.get("CURSOR_PROJECT_DIR", os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    return (Path(cwd) / "graphify-out" / "graph.json").exists()


def _has_keywords(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    for kw in keywords:
        if ".*" in kw:
            if re.search(kw, text_lower):
                return True
        elif kw in text_lower:
            return True
    return False


def _emit(ctx: str, event: str = "UserPromptSubmit"):
    json.dump({
        "continue": True,
        "additionalContext": ctx,
    }, sys.stdout)


def handle_prompt_submit():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        json.dump({"continue": True}, sys.stdout)
        return

    if not _graph_exists():
        json.dump({"continue": True}, sys.stdout)
        return

    user_msg = ""
    session_id = hook_input.get("session_id", "unknown")
    try:
        prompt = hook_input.get("prompt", {})
        if isinstance(prompt, dict):
            user_msg = prompt.get("content", "")
            if isinstance(user_msg, list):
                user_msg = " ".join(
                    p.get("text", "") for p in user_msg if isinstance(p, dict)
                )
        elif isinstance(prompt, str):
            user_msg = prompt
    except Exception:
        pass

    config = _load_config()
    state = _load_state(session_id)

    if state["remind_count"] >= config.get("max_reminders_per_session", 8):
        json.dump({"continue": True}, sys.stdout)
        return

    if _has_keywords(user_msg, config["arch_keywords"]):
        state["match_count"] += 1
        n = config.get("remind_every_n_matches", 2)
        if state["match_count"] >= n:
            state["match_count"] = 0
            state["remind_count"] += 1
            _save_state(session_id, state)
            _emit(GRAPHIFY_REMINDER, "UserPromptSubmit")
            return

        _save_state(session_id, state)

    json.dump({"continue": True}, sys.stdout)


def handle_pre_tool_use():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        json.dump({"continue": True}, sys.stdout)
        return

    if not _graph_exists():
        json.dump({"continue": True}, sys.stdout)
        return

    tool_name = compat_tool_name(hook_input)
    tool_input = hook_input.get("tool_input", {})

    if is_agent_tool(tool_name):
        subagent_type = tool_input.get("subagent_type", "")
        prompt = tool_input.get("prompt", "")
        description = tool_input.get("description", "")
        combined = f"{prompt} {description}".lower()

        config = _load_config()
        all_keywords = config["arch_keywords"] + config["explore_keywords"]

        if subagent_type in ("Explore", "explore") or _has_keywords(combined, all_keywords):
            _emit(AGENT_NUDGE, "PreToolUse")
            return

    elif is_shell_tool(tool_name):
        command = tool_input.get("command", "")
        broad_patterns = [
            r"grep\s+-r",
            r"grep\s+-rn",
            r"grep\s+-rl",
            r"grep\s+--include",
            r"grep\s+--recursive",
            r"find\s+\.\s+",
            r"find\s+\.\s*-type",
            r"find\s+\.\s*-name",
            r"find\s+UDP_PLATFORM",
            r"find\s+src/",
            r"find\s+internal/",
            r"\brg\s+",
            r"\bag\s+",
            r"\bfd\s+",
            r"\bfzf\b",
            r"tree\s+",
            r"wc\s+-l.*find",
            r"find.*\|.*wc",
            r"find.*\|.*grep",
            r"ls\s+-R",
            r"ls\s+--recursive",
        ]
        if any(re.search(p, command) for p in broad_patterns):
            config = _load_config()
            if _has_keywords(command, config.get("explore_keywords", [])):
                _emit(BASH_NUDGE, "PreToolUse")
                return

    json.dump({"continue": True}, sys.stdout)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if mode == "prompt-submit":
            handle_prompt_submit()
        elif mode == "pre-tool-use":
            handle_pre_tool_use()
        else:
            json.dump({"continue": True}, sys.stdout)
    except Exception:
        json.dump({"continue": True}, sys.stdout)
