#!/usr/bin/env python3
"""
Design quality gate — PostToolUse(Write) hook.

Enforces that the UI/UX design pipeline was consulted before UI files are
written. Fires on Write tool calls; reads design-context state markers set by
ui-ux-stack-orchestrator.py.

State file per conversation:
  ~/.claude/hooks/.state/{conversation_id}.uiux-stack.json

Relevant markers written by the orchestrator:
  before_submit_full_sent   — orchestrator sent the full stack checklist
  post_ui_write_sent        — orchestrator sent post-write advisory
  design_system_searched    — UI/UX Pro Max design-system search was run
  impeccable_context_loaded — impeccable load-context.mjs was executed

This hook additionally tracks:
  ui_write_count            — number of UI file writes in this conversation

Behaviour (enforcement_mode = "progressive"):
  - ui_write_count <= block_threshold AND design context missing
      → hard-block:  {"additional_context": "BLOCKED: ..."}
  - ui_write_count >  block_threshold AND design context missing
      → advisory:    {"additional_context": "[Design Gate] Advisory: ..."}
  - design context present (any marker)
      → pass:        {}

Fails OPEN: any unhandled error → print "{}", exit 0.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_PATH = Path(__file__).resolve()
HOOK_DIR = SCRIPT_PATH.parent
CONFIG_PATH = HOOK_DIR / "design-quality-gate.config.json"
STATE_DIR = HOOK_DIR / ".state"

IMPECCABLE_LOAD_CMD = "node ~/.claude/skills/impeccable/scripts/load-context.mjs"
TRIGGER_HINT = (
    "Trigger: mention 'design', 'ui', or 'component' in your next prompt to "
    "auto-load context, or manually run: " + IMPECCABLE_LOAD_CMD
)
BLOCK_MSG = (
    "BLOCKED: Design preflight not loaded. Before writing UI files the design "
    "stack must be consulted. " + TRIGGER_HINT
)
ADVISORY_MSG = (
    "[Design Gate] Advisory: design preflight was skipped. Consider running "
    "/impeccable audit before shipping."
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def _load_config() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "ui_extensions": [
            ".tsx", ".jsx", ".css", ".scss", ".sass", ".less",
            ".vue", ".svelte", ".html", ".astro",
        ],
        "enforcement_mode": "progressive",
        "block_threshold": 3,
        "enabled": True,
    }
    if CONFIG_PATH.is_file():
        try:
            merged = {**defaults, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------


def _state_path(conversation_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in conversation_id)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{safe}.uiux-stack.json"


def _load_state(cid: str) -> dict:
    p = _state_path(cid)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(cid: str, data: dict) -> None:
    try:
        _state_path(cid).write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# File-path extraction
# ---------------------------------------------------------------------------


def _extract_file_path(tool_input: Any) -> str:
    """Return the first non-empty path found in the tool_input dict."""
    if not isinstance(tool_input, dict):
        return ""
    for key in ("file_path", "path", "target_file", "file"):
        v = tool_input.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# Paths that are always logic, not design — never block these.
_LOGIC_PATH_PATTERNS = (
    "/api/",
    "/hooks/",
    "/store/",
    "/types/",
    "/lib/",
    "/utils/",
    ".test.tsx",
    ".spec.tsx",
)


def _is_logic_path(file_path: str) -> bool:
    """Return True if the file is a logic/utility path that should skip design gating."""
    p = file_path.replace("\\", "/").lower()
    return any(pat.lower() in p for pat in _LOGIC_PATH_PATTERNS)


def _is_ui_file(file_path: str, extensions: list[str]) -> bool:
    p = file_path.lower()
    for ext in extensions:
        s = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        if p.endswith(s):
            return True
    return False


# ---------------------------------------------------------------------------
# Design-context detection
# ---------------------------------------------------------------------------

# Any one of these markers means the design pipeline was consulted.
_DESIGN_MARKERS = (
    "design_system_searched",
    "impeccable_context_loaded",
    "before_submit_full_sent",   # orchestrator sent full checklist = context was shown
)


def _design_context_present(state: dict) -> bool:
    return any(state.get(m) for m in _DESIGN_MARKERS)


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handle(payload: dict, cfg: dict) -> dict:
    if not cfg.get("enabled", True):
        return {}

    cid: str = payload.get("conversation_id") or payload.get("session_id") or ""
    tool_input: Any = payload.get("tool_input") or {}

    file_path = _extract_file_path(tool_input)
    if not file_path:
        return {}

    extensions: list[str] = cfg.get("ui_extensions") or []
    if not _is_ui_file(file_path, extensions):
        return {}

    # Logic/utility paths are never subject to design gating even if they are .tsx.
    if _is_logic_path(file_path):
        return {}

    # It is a UI file — load + update state.
    st = _load_state(cid) if cid else {}
    count: int = int(st.get("ui_write_count") or 0) + 1
    st["ui_write_count"] = count
    if cid:
        _save_state(cid, st)

    threshold: int = int(cfg.get("block_threshold") or 3)

    if _design_context_present(st):
        # Design stack was consulted — pass through silently.
        return {}

    if count <= threshold:
        return {
            "additionalContext": BLOCK_MSG,
        }

    return {
        "additionalContext": ADVISORY_MSG,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, OSError):
        print("{}")
        return 0

    if not isinstance(payload, dict):
        print("{}")
        return 0

    try:
        cfg = _load_config()
        out = handle(payload, cfg)
    except Exception:
        # Fail open — never block the agent due to hook errors.
        print("{}")
        return 0

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
