#!/usr/bin/env python3
"""graphify-enforce.py — Nudge graphify usage for architecture/dependency work.

Modes (sys.argv[1]):
  prompt-submit   → UserPromptSubmit: keyword-triggered graphify reminder
  pre-tool-use    → PreToolUse on Agent|Bash: nudge before broad exploration

The reminder names the reachable graphify MCP tools AND a CLI/file fallback
(`graphify query`, GRAPH_REPORT.md), so it stays actionable whether or not the
graphify MCP server is connected this session. It also flags a STALE graph
(older than the latest commit) with a one-line rebuild directive — the
query-time freshness signal that complements index-lifecycle's rebuild engine.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tool_compat import is_agent_tool, is_shell_tool, tool_name as compat_tool_name

HOOKS_DIR = Path(__file__).parent
CONFIG_PATH = HOOKS_DIR / "graphify-enforce.config.json"
STATE_DIR = HOOKS_DIR / ".state"


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


# --------------------------------------------------------------------------- #
# Graph resolution + freshness (open-repo scoped, git-root aware)
# --------------------------------------------------------------------------- #
def _graph_root_and_path() -> tuple[Path | None, Path | None]:
    """Return (repo_root, graph.json) for the OPEN repo, walking up to the git
    root so a subdir cwd still resolves the repo-root graph. ``graph`` is None
    when the repo has no built graph. Fail-open."""
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    root = None
    try:
        from lib.repo_context import git_root
        root = git_root(cwd)
    except Exception:
        root = None
    if root is None:
        root = Path(cwd)
    g = Path(root) / "graphify-out" / "graph.json"
    return (Path(root), g if g.is_file() else None)


def _graph_stale(root: Path, graph: Path) -> bool:
    """Cheap staleness hint: graph older than the latest git commit. Fail-open → False.

    Complements index-lifecycle (which rebuilds on working-tree writes); this
    catches the 'committed since the graph was built' case at query time."""
    try:
        cp = subprocess.run(
            ["git", "-C", str(root), "log", "-1", "--format=%ct"],
            capture_output=True, text=True, timeout=3,
        )
        if cp.returncode != 0:
            return False
        last_commit = int((cp.stdout or "0").strip() or "0")
        return graph.stat().st_mtime < last_commit
    except Exception:
        return False


def _reminder(root: Path, graph: Path, *, compact: bool = False) -> str:
    lines = ["[Graphify] Architecture/dependency graph is available for this repo."]
    if _graph_stale(root, graph):
        lines.append(f"  ⚠️ Graph looks STALE (older than the latest commit) — refresh: `graphify update {root}`")
    lines.append("  Use graphify BEFORE broad exploration / Explore agents:")
    lines.append('    MCP: mcp__graphify__query_graph "<q>" · get_neighbors "<node>" · god_nodes · shortest_path "<A>" "<B>" · graph_stats')
    lines.append("    Fallback if graphify MCP tools are not listed this session:")
    lines.append(f'      `graphify query "<q>"` · read {root}/graphify-out/GRAPH_REPORT.md')
    if not compact:
        lines.append("  One graph call answers most structural questions vs dozens of grep/Read.")
    return "\n".join(lines)


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

    root, graph = _graph_root_and_path()
    if graph is None:
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
            _emit(_reminder(root, graph), "UserPromptSubmit")
            return

        _save_state(session_id, state)

    json.dump({"continue": True}, sys.stdout)


def handle_pre_tool_use():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        json.dump({"continue": True}, sys.stdout)
        return

    root, graph = _graph_root_and_path()
    if graph is None:
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
            _emit(_reminder(root, graph, compact=True), "PreToolUse")
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
                _emit(_reminder(root, graph, compact=True), "PreToolUse")
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
