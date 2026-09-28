#!/usr/bin/env python3
"""memory-load-on-start.py — SessionStart advisory (D9).

Reads the Memory MCP jsonl store DIRECTLY — no subprocess, no nested `claude`
(the old `claude --print` bridge never worked and would have recursed into this
same SessionStart chain).

  path = ~/.claude.json -> mcpServers.memory.env.MEMORY_FILE_PATH
         else <claude_dir>/memory/memory.jsonl
Entities whose name contains the active repo's name, or starts with
``pref::global``, are emitted: <=5 entities x <=3 (latest) observations,
<=1,200 chars. {} when the file is absent or nothing matches. Fail-open.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
try:
    from lib import platform as _plat
    from lib import repo_context as _rc
except Exception:  # noqa: BLE001
    _plat = None  # type: ignore
    _rc = None  # type: ignore

MAX_ENTITIES = 5
MAX_OBS = 3
MAX_CHARS = 1200


def _claude_dir() -> Path:
    if _plat is not None:
        return _plat.claude_dir()
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path("~/.claude").expanduser()


def memory_path() -> Path:
    try:
        cfg = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
        env = ((cfg.get("mcpServers") or {}).get("memory") or {}).get("env") or {}
        p = env.get("MEMORY_FILE_PATH")
        if isinstance(p, str) and p:
            return Path(p).expanduser()
    except Exception:  # noqa: BLE001
        pass
    return _claude_dir() / "memory" / "memory.jsonl"


def load_entities(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and rec.get("type") == "entity" and isinstance(rec.get("name"), str):
                    out.append(rec)
    except OSError:
        return []
    return out


def select(entities: list[dict], repo_name: str) -> list[dict]:
    needle = (repo_name or "").lower()
    picked = [e for e in entities
              if e["name"].lower().startswith("pref::global")
              or (needle and needle in e["name"].lower())]
    return picked[:MAX_ENTITIES]


def render(picked: list[dict]) -> str:
    lines = ["## Stored project memory (Memory MCP)"]
    for ent in picked:
        lines.append(f"- {ent['name']} [{ent.get('entityType', '')}]")
        obs = [str(o) for o in (ent.get("observations") or [])][-MAX_OBS:]
        lines.extend(f"  - {o[:200]}" for o in obs)
    return "\n".join(lines)[:MAX_CHARS]


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip().startswith("{") else {}
    except Exception:  # noqa: BLE001
        payload = {}
    try:
        repo = _rc.active_repo(payload) if _rc is not None else None
        repo_name = repo.name if repo else Path(payload.get("cwd") or os.getcwd()).name
        path = memory_path()
        picked = select(load_entities(path), repo_name) if path.is_file() else []
        parts = [render(picked)] if picked else []
        directive = search_directive(repo.name if repo else "", str(payload.get("source") or ""))
        if directive:
            parts.append(directive)
        if not parts:
            print("{}")
            return 0
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(parts),
        }}))
    except Exception:  # noqa: BLE001
        print("{}")
    return 0


def memory_server_configured() -> bool:
    try:
        cfg = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
        return "memory" in (cfg.get("mcpServers") or {})
    except Exception:  # noqa: BLE001
        return False


def search_directive(repo_name: str, source: str) -> str:
    """One-line "call memory search now" for project work (a git repo, not $HOME).
    Skipped after a compaction (the handoff already carries context)."""
    if not repo_name or source == "compact" or not memory_server_configured():
        return ""
    safe = "".join(c for c in repo_name if c.isalnum() or c in "-_. ")[:60]
    return (f"MCP: before project work call mcp__memory__search_nodes(\"{safe}\") "
            "(then \"<repo> <topic>\" per task); on \"remember / going forward / we decided\" "
            "→ add_observations.")


if __name__ == "__main__":
    raise SystemExit(main())
