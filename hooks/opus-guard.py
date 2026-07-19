#!/usr/bin/env python3
"""
opus-guard.py — PreToolUse hook for the Agent tool: the SINGLE source of truth for
subagent model routing.

Goal (per user policy): Sonnet is the default for EVERY subagent. Opus is reserved
for HEAVY/complex work or UI/UX work only. Fable runs ONLY when the user explicitly
asks for it (label [fable] / model:"fable" / fable-only-mode flag) — it is never an
automatic choice. Everything else — small, medium, even "a bit complex" — runs on
Sonnet.

Why this hook must PIN the model explicitly:
  The main session runs on Opus. The Agent tool, when `model` is unset, makes the
  subagent INHERIT the parent model (= Opus). So leaving `model` unset would silently
  send every subagent to Opus. This router therefore ALWAYS writes an explicit
  `model` ("sonnet" or "opus"); it never leaves the choice to inheritance.

Resolution order (first match wins) -> the required model:
  1. sonnet-only-mode flag  -> sonnet   (kill-switch; overrides everything)
  2. opus-only-mode flag     -> opus     (force-opus session)
  3. fable-only-mode flag    -> fable    (force-fable session)
  4. subagent_type is an OPUS-only agent (frontend-uiux-designer) -> opus  (UI/UX)
  5. subagent_type is a SONNET-only agent (Explore, claude-code-guide) -> sonnet
  6. explicit model:"opus"/"sonnet"/"fable" param -> honor it (deliberate choice)
  7. description label [opus]/[sonnet]/[fable]     -> use the label (explicit signal)
  8. nothing specified                              -> sonnet (the cheap default)

Then it pins `model` to the resolved value AND aligns the visible
[sonnet]/[opus]/[fable] label so the label never lies about what runs.

The main model should STILL write the [sonnet]/[opus] prefix on every Agent call
(see the "Agent tool" rule in ~/.claude/CLAUDE.md) so routing stays explicit — this
hook is the safety net + the thing that makes the label real.

Protocol:
  stdin:  {"tool_name":"Agent","tool_input":{"description":"...","model":"...","subagent_type":"..."}}
  stdout: {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow",
           "updatedInput":{...},"additionalContext":"..."}}  to normalize + allow,
          or {} to allow unchanged.
  exit:   always 0 (fail-open).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PREFIX_RE = re.compile(r"^\[(sonnet|opus|fable)\]\s", re.IGNORECASE)

# --- read-then-write protocol appended to every subagent prompt (2026-07-19) ----
# Subagents get a fresh context and inherit none of the parent's rules. Without this
# they hit the broken native Edit and improvise a shell write. The marker keeps the
# append idempotent if a prompt is ever recycled through the guard twice.
_WRITE_PROTOCOL_MARKER = "<!-- opus-guard:write-protocol -->"

_WRITE_PROTOCOL = f"""

---
{_WRITE_PROTOCOL_MARKER}
## FILE ACCESS PROTOCOL (injected — applies to everything below)

**READ BEFORE YOU WRITE. Never edit a file you have not read.**

READ
  - source code  -> jcodemunch: `get_symbol_source`, `get_file_outline`,
                    `get_file_content`, `assemble_task_context`. It returns the
                    content itself — do NOT re-read the same file through another tool.
  - non-code     -> `ctx_read` (inside the project root)
  - docs/md sets -> jdocmunch: `search_sections` / `get_section`

WRITE
  - edit an existing file      -> `ctx_patch(op="replace_all", path, find, replace)`
  - text that is not unique    -> `ctx_read(mode="anchored")` then
                                  `ctx_patch(op="replace_lines", ...)` with the anchors
  - create a new file          -> `Write`, or `ctx_patch(op="create")`
  - path OUTSIDE project root  -> `Write` (ctx_patch is path-jailed to the root)

DO NOT WRITE FILES THROUGH THE SHELL. Not blocked — trusted to you:
  `sed -i` · `perl -i` · `python3 - <<EOF` · `python3 -c`/`node -e` writes ·
  `cat > file <<EOF` · `tee file` · `echo > file`
These bypass every write gate and leave no reviewable edit. `Edit`, `Write`, and
`ctx_patch` all work — there is no situation where a shell write is your only
option, and "it was fewer calls" is not a reason. N separate edits is the correct
cost.

Bash IS correct for builds, tests, linters, git, package managers, and read-only
inspection (`grep`, `sed` without `-i`, `python3 -c` that only prints).

If a tool is denied, that is a ROUTE, not an obstacle: switch to the sanctioned tool
above rather than reimplementing its job in Bash. If no sanctioned path exists, STOP
and say so instead of improvising around it.
"""
# -------------------------------------------------------------------------------

# --- model-policy.json: the single model truth (P2). ---------------------------
# opus-guard consumes it for the flag dir/names, the agent pins, and the valid-model
# set. It FAILS OPEN to these literals if the file is missing/corrupt so the guard is
# never disabled by a bad policy file. The Agent tool has no TaskProfile, so opus-guard
# does NOT consult `task_matrix` (that step is a no-op at this boundary) — its decisions
# are byte-identical to the pre-policy literals below whenever the policy matches them.
POLICY_PATH = Path(__file__).resolve().parent / "model-policy.json"

_DEFAULT_FLAG_DIR = "state"
_DEFAULT_FLAG_NAMES = {
    "sonnet": "sonnet-only-mode",
    "opus": "opus-only-mode",
    "fable": "fable-only-mode",
}
_DEFAULT_FLAG_PRECEDENCE = ["sonnet", "opus", "fable"]
_DEFAULT_SONNET_ONLY_AGENTS = {"explore", "claude-code-guide"}
_DEFAULT_OPUS_ONLY_AGENTS = {"frontend-uiux-designer", "implementation-engineer"}
_DEFAULT_VALID_MODELS = {"sonnet", "opus", "fable"}
_DEFAULT_MODEL = "sonnet"

_POLICY_CACHE: dict | None = None


def _load_policy() -> dict:
    """Read model-policy.json once (cached). Fail-open to {} on any error."""
    global _POLICY_CACHE
    if _POLICY_CACHE is None:
        try:
            with open(POLICY_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _POLICY_CACHE = data if isinstance(data, dict) else {}
        except Exception:
            _POLICY_CACHE = {}
    return _POLICY_CACHE


def _agent_sets() -> tuple[set[str], set[str], set[str]]:
    """(sonnet_only, opus_only, fable_only) agent sets from policy, fail-open to literals.
    An empty opus list in policy is RESPECTED; only a missing/invalid list falls back
    to the literals. (2026-07-19: the 2026-07-18 fable-everything directive was removed
    at user request — agent_pins.fable no longer exists and Fable is opt-in only.)"""
    pins = _load_policy().get("agent_pins")
    pins = pins if isinstance(pins, dict) else {}
    opus = pins.get("opus")
    sonnet = pins.get("sonnet")
    fable = pins.get("fable")
    opus_set = {str(a).lower() for a in opus} if isinstance(opus, list) else set(_DEFAULT_OPUS_ONLY_AGENTS)
    sonnet_set = {str(a).lower() for a in sonnet} if isinstance(sonnet, list) else set(_DEFAULT_SONNET_ONLY_AGENTS)
    fable_set = {str(a).lower() for a in fable} if isinstance(fable, list) else set()
    return sonnet_set, opus_set, fable_set


def _flag_paths() -> dict[str, Path]:
    """{model: flag_path} under ~/.claude/<dir>/, from policy, fail-open to literals."""
    sf = _load_policy().get("session_flags")
    sf = sf if isinstance(sf, dict) else {}
    fdir = sf.get("dir") if isinstance(sf.get("dir"), str) and sf.get("dir") else _DEFAULT_FLAG_DIR
    base = Path.home() / ".claude" / fdir
    out: dict[str, Path] = {}
    for key, default_name in _DEFAULT_FLAG_NAMES.items():
        name = sf.get(key)
        out[key] = base / (name if isinstance(name, str) and name else default_name)
    return out


def _flag_precedence() -> list[str]:
    prec = _load_policy().get("session_flags")
    prec = prec.get("precedence") if isinstance(prec, dict) else None
    if isinstance(prec, list) and all(p in _DEFAULT_FLAG_NAMES for p in prec) and prec:
        return prec
    return list(_DEFAULT_FLAG_PRECEDENCE)


def _valid_models() -> set[str]:
    ids = _load_policy().get("model_ids")
    return set(ids) if isinstance(ids, dict) and ids else set(_DEFAULT_VALID_MODELS)


def _default_model() -> str:
    d = _load_policy().get("default")
    return d if isinstance(d, str) and d else _DEFAULT_MODEL


def _allow_unchanged() -> int:
    print("{}")
    return 0


NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MODEL_SUFFIX_RE = re.compile(r"[-_](sonnet|opus|fable|haiku)$", re.I)
NAME_MAX = 64


def _normalize_name(name: str, required: str) -> str | None:
    """Append the resolved model as a trailing bare segment: impl-crud -> impl-crud-opus.

    `name` is validated by the Agent tool against ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$, so a
    bracketed [opus] label is ILLEGAL here (that form belongs in `description`). Returns
    None when there is nothing to change or the result would be invalid — idempotent, so
    re-running never stacks suffixes.
    """
    if not name:
        return None
    base = MODEL_SUFFIX_RE.sub("", name)
    if len(base) + len(required) + 1 > NAME_MAX:
        base = base[: NAME_MAX - len(required) - 1].rstrip("-_")
    candidate = f"{base}-{required}"
    if candidate == name or not NAME_RE.match(candidate):
        return None
    return candidate


def _resolve_required(subagent_type: str, model: str, description: str) -> tuple[str, str]:
    """Return (required_model, reason). Resolution order (unchanged from the literals,
    now sourced from model-policy.json with fail-open):
      session_flags -> agent_pins -> explicit model param -> [label] prefix -> default.
    (task_matrix is intentionally skipped: the Agent tool carries no TaskProfile.)
    """
    flag_paths = _flag_paths()
    for mdl in _flag_precedence():
        fp = flag_paths.get(mdl)
        if fp is not None and fp.is_file():
            return mdl, f"{mdl}-only-mode active"
    sonnet_agents, opus_agents, fable_agents = _agent_sets()
    if subagent_type in fable_agents:
        return "fable", f"'{subagent_type}' is a pinned fable agent"
    if subagent_type in opus_agents:
        return "opus", f"'{subagent_type}' is a pinned opus agent"
    if subagent_type in sonnet_agents:
        return "sonnet", f"'{subagent_type}' is a pinned sonnet agent"
    if model in _valid_models():
        return model, "explicit model param"
    m = PREFIX_RE.match(description)
    if m:
        return m.group(1).lower(), "description label"
    return _default_model(), "default (no opus/fable signal)"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        return _allow_unchanged()

    if not isinstance(payload, dict) or payload.get("tool_name") != "Agent":
        return _allow_unchanged()

    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return _allow_unchanged()

    description = tool_input.get("description", "") or ""
    model = (tool_input.get("model") or "").lower()
    subagent_type = (tool_input.get("subagent_type") or "").lower()

    required, reason = _resolve_required(subagent_type, model, description)

    # Align the visible label.
    m = PREFIX_RE.match(description)
    current_prefix = m.group(1).lower() if m else None
    body = description[m.end():] if m else description

    updated: dict[str, object] = {}
    if current_prefix != required:
        updated["description"] = f"[{required}] {body}"
    # ALWAYS pin the model explicitly so an unset model never inherits the Opus parent.
    if model != required:
        updated["model"] = required
    # Align the agent NAME too — it is what the agent list/sidebar renders, and nothing
    # else writes it. Bracket labels are invalid in `name`, so the model goes in as a
    # trailing segment.
    new_name = _normalize_name(tool_input.get("name", "") or "", required)
    if new_name:
        updated["name"] = new_name

    # Hand every subagent the read-then-write protocol (2026-07-19).
    # A subagent starts in a FRESH context: it does not inherit this conversation's
    # rules, and no agent definition carries them (0 of 58 mentioned ctx_patch). So it
    # discovers the write path by trial and error — finds native Edit broken, and falls
    # back to `python3 - <<EOF` / `sed -i`, which is how shell writes kept appearing.
    # This is the one place every Agent call passes through, so it is injected here
    # instead of being copied into 58 agent files that would drift.
    prompt = tool_input.get("prompt", "")
    if isinstance(prompt, str) and prompt and _WRITE_PROTOCOL_MARKER not in prompt:
        updated["prompt"] = prompt + _WRITE_PROTOCOL

    if not updated:
        return _allow_unchanged()

    # Emit the FULL tool_input with overrides applied (some harness versions REPLACE
    # tool_input with updatedInput instead of merging — returning only changed keys
    # would drop required params and fail schema validation).
    full_input = dict(tool_input)
    full_input.update(updated)

    note = (
        f"opus-guard: subagent routed to [{required}] — {reason}. "
        "Sonnet is the default; Opus is reserved for heavy/complex or UI/UX subagent "
        "tasks; Fable runs only when YOU explicitly ask ([fable] / model:fable / "
        "fable-only-mode). Write the [sonnet]/[opus]/[fable] prefix yourself to keep "
        "routing explicit."
    )
    if "name" in updated:
        note += (
            f" Agent name normalized to '{updated['name']}' so the model is visible in "
            "the agent list; if the agent is addressable, use THAT name."
        )

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": full_input,
            "additionalContext": note,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
