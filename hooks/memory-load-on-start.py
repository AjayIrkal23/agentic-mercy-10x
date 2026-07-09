#!/usr/bin/env python3
"""
memory-load-on-start.py — SessionStart hook

Queries the Memory MCP server for project-relevant entities and injects
the top-5 as "MEMORY: ..." lines into additionalContext.

Design principles:
  - Bulletproof: any failure exits 0 silently (never blocks session startup)
  - MCP calls via claude CLI subprocess (avoids direct HTTP to MCP socket)
  - Cap output at MAX_CHARS to avoid bloating session context
  - Two search passes: project-name query + workspace-path query
  - Deduplicates results before formatting
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

MAX_ENTITIES = 5        # max entities to inject
MAX_CHARS = 800         # hard cap on injected additionalContext text
MCP_TIMEOUT = 8         # seconds to wait for MCP subprocess

# Name of the memory MCP server as registered in settings.json
# Check your settings.json mcpServers key if this differs
MCP_SERVER_NAME = "memory"

# ── MCP Query Helpers ──────────────────────────────────────────────────────────

def _query_memory_mcp(query: str) -> list[dict]:
    """
    Call mcp__memory__search_nodes via claude CLI subprocess.

    Returns list of entity dicts: [{name, entityType, observations: [str]}]
    Returns [] on any failure (MCP unavailable, timeout, parse error).

    The Memory MCP `search_nodes` tool returns:
      {entities: [{name, entityType, observations: [...]}]}
    """
    try:
        # Use the claude CLI to invoke an MCP tool call
        # This approach works without knowing the MCP socket path directly
        cmd = [
            "claude",
            "--print",
            "--output-format", "json",
            "--no-verbose",
            f"Call mcp__{MCP_SERVER_NAME}__search_nodes with query: {query!r}. "
            f"Return only the raw JSON result, no explanation."
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=MCP_TIMEOUT,
        )
        if result.returncode != 0:
            return []

        stdout = result.stdout.strip()
        if not stdout:
            return []

        # Try to parse as JSON — claude --output-format json wraps in {type, result}
        try:
            outer = json.loads(stdout)
            # The result may be nested under various keys depending on claude CLI version
            if isinstance(outer, dict):
                # Try common wrappers
                inner = outer.get("result") or outer.get("content") or outer.get("entities") or outer
                if isinstance(inner, str):
                    inner = json.loads(inner)
                if isinstance(inner, dict):
                    entities = inner.get("entities", [])
                elif isinstance(inner, list):
                    entities = inner
                else:
                    entities = []
            elif isinstance(outer, list):
                entities = outer
            else:
                entities = []
        except (json.JSONDecodeError, TypeError):
            entities = []

        return entities[:MAX_ENTITIES * 2]  # fetch more, deduplicate later

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    except Exception:
        return []


def _query_memory_direct(query: str) -> list[dict]:
    """
    Fallback: read memory.jsonl directly and do simple text search.
    Used when claude CLI is unavailable or fails.
    Returns [] if memory file not found.
    """
    memory_paths = [
        Path.home() / "mcp-data" / "memory.jsonl",
        Path.home() / ".config" / "memory" / "memory.jsonl",
    ]
    for mp in memory_paths:
        if mp.is_file():
            break
    else:
        return []

    entities = []
    query_lower = query.lower()
    try:
        with open(mp, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # memory.jsonl format: {type, name, entityType, observations, ...}
                    if entry.get("type") not in ("entity",):
                        # Also accept lines that look like entity records
                        if "name" not in entry and "entityType" not in entry:
                            continue
                    name = entry.get("name", "")
                    obs = entry.get("observations", [])
                    # Simple relevance: query terms appear in name or any observation
                    text = (name + " " + " ".join(obs)).lower()
                    if any(term in text for term in query_lower.split()):
                        entities.append({
                            "name": name,
                            "entityType": entry.get("entityType", "unknown"),
                            "observations": obs,
                        })
                except (json.JSONDecodeError, TypeError):
                    continue
        return entities
    except OSError:
        return []


def deduplicate(entities: list[dict]) -> list[dict]:
    """Remove duplicate entities by name."""
    seen = set()
    out = []
    for e in entities:
        name = e.get("name", "")
        if name and name not in seen:
            seen.add(name)
            out.append(e)
    return out


def format_entity(entity: dict) -> str:
    """Format one entity as a compact MEMORY: line."""
    name = entity.get("name", "unknown")
    entity_type = entity.get("entityType", "")
    observations = entity.get("observations", [])

    # First observation is most important; cap length
    if observations:
        obs_text = observations[0][:200]
        if len(observations) > 1:
            obs_text += f" [+{len(observations)-1} more]"
    else:
        obs_text = "(no observations)"

    type_tag = f"[{entity_type}] " if entity_type and entity_type != "unknown" else ""
    return f"MEMORY: {type_tag}{name} — {obs_text}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # Always exit 0 — any failure is silent
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)
        payload = json.loads(raw)
    except Exception:
        sys.exit(0)

    # Extract workspace and project name
    try:
        workspace_roots = payload.get("workspace_roots") or []
        if workspace_roots:
            workspace = workspace_roots[0]
        else:
            workspace = payload.get("cwd") or os.getcwd()

        project_name = Path(workspace).name if workspace else ""
        workspace_norm = workspace.replace("/", " ").replace("-", " ").replace("_", " ")

        if not project_name:
            sys.exit(0)
    except Exception:
        sys.exit(0)

    # Build search queries
    queries = []
    if project_name:
        queries.append(project_name)
    if workspace_norm and workspace_norm != project_name:
        # Add cleaned path fragments as additional search terms
        parts = [p for p in workspace_norm.split() if len(p) > 3][-3:]
        if parts:
            queries.append(" ".join(parts))

    # Query MCP (try CLI first, then direct file fallback)
    all_entities: list[dict] = []
    for q in queries:
        entities = _query_memory_mcp(q)
        if not entities:
            # Fallback to direct file read
            entities = _query_memory_direct(q)
        all_entities.extend(entities)

    # Deduplicate and limit
    unique = deduplicate(all_entities)[:MAX_ENTITIES]

    if not unique:
        # No memory found — exit silently (do not emit empty context block)
        sys.exit(0)

    # Format output
    lines = [format_entity(e) for e in unique]
    context_block = (
        "## Stored Project Memory (auto-loaded from Memory MCP)\n"
        + "\n".join(lines)
        + "\n"
    )

    # Hard cap at MAX_CHARS
    if len(context_block) > MAX_CHARS:
        context_block = context_block[:MAX_CHARS - 3] + "..."

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context_block,
        }
    }
    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()
    sys.exit(0)


if __name__ == "__main__":
    main()
