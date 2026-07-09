#!/usr/bin/env python3
"""SessionStart sub-script: strict graphify graph freshness guard.

Detects whether the active workspace has a graphify graph and whether it is
stale (graph.json mtime older than the latest git commit).  Emits MANDATORY
directives when the graph is missing or stale, and checks whether the systemd
watch daemon is running.

Called by session-start-aggregator.py.  Receives the hook JSON on stdin.
Outputs {"additional_context": "..."} on stdout.  Fails open on any error.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _watch_refcount import acquire  # noqa: E402

GRAPHIFY_BIN = Path.home() / ".local" / "bin" / "graphify"


def _find_workspace_root(payload: dict) -> Path | None:
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots:
        p = Path(str(roots[0]))
        if p.is_dir():
            return p

    cwd = Path(os.getcwd())
    if (cwd / ".git").exists():
        return cwd

    cur = cwd
    for _ in range(20):
        parent = cur.parent
        if parent == cur:
            break
        if (parent / ".git").exists():
            return parent
        cur = parent

    return None


def _graph_json_path(source_root: Path) -> Path:
    return source_root / "graphify-out" / "graph.json"


def _check_update_needed(source_root: Path) -> tuple[bool, str]:
    """Use graphify's native check-update probe. Returns (needs_update, detail)."""
    try:
        result = subprocess.run(
            ["graphify", "check-update", str(source_root)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return True, result.stdout.strip() or result.stderr.strip() or "check-update failed"
        output = result.stdout.strip()
        if output:
            return True, output
        return False, ""
    except FileNotFoundError:
        return _check_update_mtime_fallback(source_root)
    except Exception:
        return False, ""


def _check_update_mtime_fallback(source_root: Path) -> tuple[bool, str]:
    """Fallback when graphify binary is unavailable: compare mtime vs git HEAD."""
    try:
        graph_mtime = (source_root / "graphify-out" / "graph.json").stat().st_mtime
        result = subprocess.run(
            ["git", "-C", str(source_root), "log", "-1", "--format=%ct", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            commit_time = float(result.stdout.strip())
            if commit_time > graph_mtime:
                hours = (commit_time - graph_mtime) / 3600
                return True, f"{hours:.1f} hours behind latest commit"
        return False, ""
    except Exception:
        return False, ""


def _get_current_head(source_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _directive_missing(source_root: Path) -> str:
    return (
        "### MANDATORY: graphify graph MISSING for this project\n\n"
        f"Project: `{source_root}`\n"
        f"Expected: `{source_root}/graphify-out/graph.json` — **DOES NOT EXIST**\n\n"
        "**YOU MUST BUILD THE GRAPH BEFORE BROAD CODEBASE EXPLORATION:**\n\n"
        "Run via Bash:\n"
        f"```\ngraphify update {source_root}\n```\n\n"
        "This is a cheap local parse (no LLM calls). Wait for completion, "
        "then consult `graphify-out/GRAPH_REPORT.md` for architecture orientation."
    )


def _directive_stale(source_root: Path, detail: str, head: str) -> str:
    is_non_code = "non-code" in detail.lower()
    if is_non_code:
        action = (
            f"For code-only refresh: `graphify update {source_root}`\n"
            f"For full rebuild (includes docs/configs, needs LLM): "
            f"invoke the `/graphify` skill from within the project."
        )
    else:
        action = (
            "Run via Bash:\n"
            f"```\ngraphify update {source_root}\n```\n\n"
            "This is a cheap incremental update (code parsing only, no LLM)."
        )
    return (
        "### URGENT: graphify graph is STALE for this project\n\n"
        f"Project: `{source_root}`\n"
        f"Detail: {detail} (HEAD `{head}`)\n\n"
        f"**REFRESH THE GRAPH BEFORE BROAD EXPLORATION:**\n\n{action}"
    )




def main() -> int:
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw if raw.strip() else "{}")
    except Exception:
        payload = {}

    try:
        source_root = _find_workspace_root(payload)
        if source_root is None:
            print("{}")
            return 0

        graph_path = _graph_json_path(source_root)
        parts: list[str] = []

        if not graph_path.is_file():
            parts.append(_directive_missing(source_root))
        else:
            needs_update, detail = _check_update_needed(source_root)
            head = _get_current_head(source_root) or "unknown"

            if needs_update:
                parts.append(_directive_stale(source_root, detail, head))
            else:
                parts.append(
                    f"graphify graph: FRESH — `{source_root.name}` "
                    f"(HEAD `{head}`)"
                )

        cid = payload.get("conversation_id") or payload.get("session_id") or ""
        svc = acquire("graphify", source_root, cid)
        parts.append(f"graphify watch: active for this session (`{svc}`)")

        if not parts:
            print("{}")
            return 0

        ctx = "\n\n".join(parts)
        print(json.dumps({"additionalContext": ctx}))

    except Exception:
        print("{}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
