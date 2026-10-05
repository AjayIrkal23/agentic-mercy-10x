"""memory_gate.py — Stop gate 7: a "remember this" prompt must end with a saved memory.

Autonomy plan 2026-10-05 (WP-C item 2). Saving a durable fact used to depend on the model
remembering CLAUDE.md section 7. Now, when the human prompt of THIS turn carried a cue
(remember / going forward / we decided / from now on / always use ... / never use ...) and
the turn saved nothing, ``hard-completion-gate.py`` blocks once (its once-per-human-turn
budget; its consent clauses and ``stop_hook_active`` exit first).

"Saved" is read from the transcript tail the gates already read (``lib.turns``): a Memory
MCP ``add_observations`` / ``create_entities`` (or the mercy ``remember`` tool, or a
``memory-codex`` dispatch), or a Write/Edit of a file under ``projects/*/memory/`` or a
``CODEX.md``. The cue is the router's own memory route regex (``tool-intelligence.json``)
plus bare "remember" (not in a question) and ``always|never <verb>``. Pure stdlib; fail-open:
anything unreadable passes.
"""
from __future__ import annotations

import json
import re
from collections import deque
from functools import lru_cache
from pathlib import Path

try:
    from lib import turns as _turns
except Exception:  # pragma: no cover - fail-open
    _turns = None

LABEL = "Gate 7 (memory save)"
_TOOLMAP = Path(__file__).resolve().parents[1] / "tool-intelligence.json"
# code (fenced or inline) and quoted text never carry a cue: they quote, they don't instruct
_FENCE = re.compile(r"```.*?```|`[^`\n]*`|\"[^\"\n]*\"|“[^”\n]*”", re.S)
_SENTENCE = re.compile(r"[^.!?;\n]+[.!?;]?")
# cues count only as commands at the start of a sentence (SANTA-autonomy: "I don't remember
# which file…", "the old code would never touch…" are not requests to save anything)
_EXTRA = re.compile(
    r"^(?:please\s+)?(?:always|never)\s+(?:use|do|run|call|prefer|write|add|commit|ask|start|put|"
    r"keep|treat|assume|touch|edit|delete|install|skip|include)\b", re.I)
_REMEMBER = re.compile(r"^(?:please\s+)?remember\b(?!\s+(?:the|how|which|where|when|what|why|me)\b)", re.I)
_MEM_PATH = re.compile(r"/\.claude/projects/[^/]+/memory/")
_SAVE_TOOLS = ("memory__add_observations", "memory__create_entities", "mercy__remember")
_MAX_SCAN = 4000


@lru_cache(maxsize=1)
def _route_rx() -> "re.Pattern | None":
    """The router's own memory-cue regex, so the gate and the route never drift apart."""
    try:
        for r in json.loads(_TOOLMAP.read_text(encoding="utf-8")).get("mcp_routes", []):
            if isinstance(r, dict) and r.get("id") == "memory":
                return re.compile(str((r.get("when") or {}).get("regex") or ""), re.I)
    except Exception:  # noqa: BLE001
        pass
    return None


def prompt_cue(prompt: str | None) -> bool:
    """True when the prompt asks to keep a fact or decision (code fences ignored)."""
    text = _FENCE.sub(" ", prompt or "")[:_MAX_SCAN]
    rx = _route_rx()
    for raw in _SENTENCE.findall(text):
        s = raw.strip()
        if not s or s.endswith("?"):  # a question asks, it does not instruct
            continue
        if (rx is not None and rx.pattern and rx.search(s)) or _EXTRA.search(s) or _REMEMBER.search(s):
            return True
    return False


def _turn_tool_uses(transcript) -> "list | None":
    """(name, input) of every tool_use since the last real user prompt; None if unreadable."""
    if _turns is None or not transcript:
        return None
    try:
        with Path(str(transcript)).open(encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=_turns.TAIL_LINES)
    except Exception:  # noqa: BLE001
        return None
    uses: list = []
    for line in tail:
        try:
            entry = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(entry, dict):
            continue
        if _turns._prompt_text(entry) is not None:
            uses = []  # a new human turn starts
            continue
        msg = entry.get("message")
        for b in (msg.get("content") if isinstance(msg, dict) else None) or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                uses.append((str(b.get("name") or ""), b.get("input") if isinstance(b.get("input"), dict) else {}))
    return uses


def _is_save(name: str, inp: dict) -> bool:
    if name.endswith(_SAVE_TOOLS):
        return True
    if name in ("Agent", "Task") and inp.get("subagent_type") == "memory-codex":
        return True
    if name in (_turns.WRITE_TOOLS if _turns is not None else ()):
        fp = str(inp.get("file_path") or inp.get("notebook_path") or "").replace("\\", "/")
        return bool(_MEM_PATH.search(fp)) or fp.rsplit("/", 1)[-1].lower() == "codex.md"
    return False


def turn_saved_memory(transcript) -> "bool | None":
    uses = _turn_tool_uses(transcript)
    return None if uses is None else any(_is_save(n, i) for n, i in uses)


def gate7_memory(transcript, prompt: str | None) -> tuple:
    """(ok, label, detail) in the shape of the other completion gates."""
    try:
        if prompt_cue(prompt) and turn_saved_memory(transcript) is False:
            return False, LABEL, (
                "Your prompt asked to keep a fact or decision and nothing was saved this turn. "
                "Fix: save it now: mcp__memory__add_observations (decision::<repo>::<topic>) "
                "or the auto-memory file, then finish.")
    except Exception:  # noqa: BLE001 - never block on an exception
        pass
    return True, LABEL, ""


__all__ = ["LABEL", "prompt_cue", "turn_saved_memory", "gate7_memory"]
