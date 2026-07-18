#!/usr/bin/env python3
"""
sessionStart aggregator: merges plan-mode-gate reminder, optional workspace
documentation-lifecycle reminder (when `.claude/documentation-lifecycle.md` exists),
optional MCP roster parsed from ~/.claude.json, and an excerpt of
~/.claude/rules/agent-lifecycle-routing.md.

Also surfaces prior-session gate override warnings from breadcrumb state.

stdin: Cursor hook JSON (workspace_roots, ...).
stdout: JSON { continue, additional_context }

Workspace documentation reminders are injected by ~/.claude/hooks/documentation_lifecycle_hook.py
(marker file under the active workspace root) so projects do not need their own hooks for the same cue.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import time

HOME = Path.home()
HOOK_DIR = HOME / ".claude" / "hooks"
STATE_DIR = HOOK_DIR / ".state"
STATE_MAX_AGE_SECONDS = 86400  # 24 hours
CLAUDE_HOOK_DIR = HOME / ".claude" / "hooks"
CLAUDE_STATE_DIR = CLAUDE_HOOK_DIR / ".state"
UNKNOWN_MAX_AGE_SECONDS = 3600  # 1 hour — for unknown.*.json files
MCP_JSON = HOME / ".claude.json"
USER_MCP_RULE = HOME / ".claude" / "rules" / "user-mcp-inventory.mdc"
MCP_USAGE_SKILL = HOME / ".claude" / "skills" / "mcp-usage-standards" / "SKILL.md"
SESSION_GATE = HOOK_DIR / "session-plan-gate-hint.py"
DOC_LIFECYCLE = HOOK_DIR / "documentation_lifecycle_hook.py"
# index-lifecycle.py session-start REPLACES the four separate guard fan-outs at
# SessionStart (P3-T5). INDEX_GUARD / GRAPHIFY_GUARD / JDOC_GUARD / DOX_GUARD
# (session mode) stay defined + on disk, UNWIRED, retained for flip-back until
# P7-T4; the interim wiring is re-homed into dispatch.py by P4-T7.
INDEX_LIFECYCLE = HOOK_DIR / "index-lifecycle.py"
INDEX_GUARD = HOOK_DIR / "jcodemunch-index-guard.py"
GRAPHIFY_GUARD = HOOK_DIR / "graphify-index-guard.py"
JDOC_GUARD = HOOK_DIR / "jdocmunch-index-guard.py"
TDD_INIT_GUARD = HOOK_DIR / "tdd-guard-init-guard.py"
DOX_GUARD = HOOK_DIR / "dox-tree-guard.py"
ROUTING_MD = HOME / ".claude" / "rules/agent-lifecycle-routing.md"
PLUGINS_ROOT = HOME / ".claude" / "plugins"
MAX_AGGREGATED_CHARS = 60000


def _cleanup_stale_state() -> None:
    """Remove state files older than 24h and clear model override flags on session start."""
    try:
        # Clean cursor hooks state directory
        if STATE_DIR.is_dir():
            now = time.time()
            for f in STATE_DIR.iterdir():
                if f.suffix == ".json" and (now - f.stat().st_mtime) > STATE_MAX_AGE_SECONDS:
                    f.unlink(missing_ok=True)
    except OSError:
        pass

    try:
        # Clean claude hooks state directory (was never cleaned before)
        if CLAUDE_STATE_DIR.is_dir():
            now = time.time()
            for f in CLAUDE_STATE_DIR.iterdir():
                if f.suffix != ".json":
                    continue
                try:
                    age = now - f.stat().st_mtime
                    # unknown.*.json: 1-hour TTL (session ID was missing)
                    if f.name.startswith("unknown."):
                        if age > UNKNOWN_MAX_AGE_SECONDS:
                            f.unlink(missing_ok=True)
                    # All other .json files: 24-hour TTL
                    elif age > STATE_MAX_AGE_SECONDS:
                        f.unlink(missing_ok=True)
                except OSError:
                    continue
    except OSError:
        pass

def _merge_additional_context(existing: str, add: str) -> str:
    add_st = add.strip()
    if not add_st:
        return existing
    if not existing.strip():
        return add_st
    return f"{existing.rstrip()}\n\n---\n\n{add_st}"


def _discover_superpowers_skills_dir() -> Path | None:
    try:
        for super_dir in PLUGINS_ROOT.glob("**/superpowers"):
            if not super_dir.is_dir():
                continue
            for child in sorted(super_dir.iterdir(), reverse=True):
                if child.is_dir() and (child / "skills").is_dir():
                    return child / "skills"
    except OSError:
        pass
    return None


def _superpowers_session_context() -> str:
    sp_dir = _discover_superpowers_skills_dir()
    if not sp_dir:
        return ""
    using = sp_dir / "using-superpowers" / "SKILL.md"
    if not using.is_file():
        return ""
    skill_names = []
    try:
        for d in sorted(sp_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").is_file():
                skill_names.append(d.name)
    except OSError:
        pass
    return (
        "### Superpowers plugin (active)\n\n"
        f"Bootstrap: `{using.resolve()}`\n"
        f"Skills: {', '.join(skill_names)}\n"
        "Phase routing: Plan→`writing-plans`,`brainstorming` | "
        "Build→`executing-plans`,`subagent-driven-development` | "
        "Test→`test-driven-development` | Debug→`systematic-debugging` | "
        "Ship→`verification-before-completion`,`finishing-a-development-branch` | "
        "Review→`requesting-code-review`,`receiving-code-review` | "
        "Parallel→`dispatching-parallel-agents`,`using-git-worktrees`"
    )


def _configured_mcp_context() -> str:
    """Names-only roster from ~/.claude.json mcpServers; empty on parse errors."""
    try:
        blob = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return ""
    srv = blob.get("mcpServers")
    if not isinstance(srv, dict) or not srv:
        return ""
    keys = sorted(srv.keys())
    line = ", ".join(keys)
    if len(line) > 260:
        line = line[:257] + "…"
    rule_ref = (
        f"`{USER_MCP_RULE.resolve()}`"
        if USER_MCP_RULE.is_file()
        else "`~/.claude/rules/user-mcp-inventory.md`"
    )
    skill_ref = (
        f"`{MCP_USAGE_SKILL.resolve()}`"
        if MCP_USAGE_SKILL.is_file()
        else "`~/.claude/skills/mcp-usage-standards/SKILL.md`"
    )
    return (
        "### Configured MCP servers (this machine)\n\n"
        f"**Names:** {line}\n\n"
        f"Routing: {rule_ref} — {skill_ref}"
    )


def _precompact_handoff_context(payload_txt: str) -> str:
    """If a pre-compact handoff file exists for this conversation, inject it.

    The pre-compact hook writes {cid}.precompact-handoff.json when auto-compaction
    is triggered. At the next session start (or post-compaction turn), this function
    reads and injects it as additionalContext so state survives the compaction boundary.
    """
    try:
        payload = json.loads(payload_txt) if payload_txt.strip() else {}
    except json.JSONDecodeError:
        return ""

    cid = (payload.get("conversation_id") or payload.get("session_id") or "")
    if not cid:
        return ""

    safe_cid = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    handoff_path = CLAUDE_STATE_DIR / f"{safe_cid}.precompact-handoff.json"

    if not handoff_path.is_file():
        return ""

    try:
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""

    # Only inject if the handoff is recent (within 2 hours — avoids stale injection
    # if the same cid is re-used in a later session by coincidence).
    import time as _time
    try:
        mtime = handoff_path.stat().st_mtime
        if (_time.time() - mtime) > 7200:
            return ""
    except OSError:
        return ""

    lines = [
        "RESUMED FROM PRE-COMPACT SNAPSHOT:",
        f"  write_count at compaction: {handoff.get('write_count', 0)}",
        f"  skills reminded before compaction: {handoff.get('last_skill_reminders', [])}",
        f"  frontend_start_sent: {handoff.get('frontend_start_sent', False)}",
        f"  backend_start_sent: {handoff.get('backend_start_sent', False)}",
        f"  gate_states: {handoff.get('gate_states', {})}",
        f"  semgrep_ran: {handoff.get('semgrep_ran', False)}",
    ]
    if handoff.get("active_phase"):
        lines.append(f"  active_phase: {handoff['active_phase'][:200]}")

    return "\n".join(lines)


def _run_hook_subprocess(cmd: list[str], payload_txt: str, timeout: int) -> str:
    try:
        proc = subprocess.run(
            cmd,
            input=payload_txt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            blob = json.loads(proc.stdout)
            if isinstance(blob, dict):
                chunk = blob.get("additionalContext") or blob.get("additional_context")
                if isinstance(chunk, str):
                    return chunk
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return ""


def _prior_gate_override_context(workspace: Path) -> str:
    """Read prior session's breadcrumb and emit a warning if gates were overridden."""
    try:
        bkey = hashlib.sha1(str(workspace).encode()).hexdigest()[:12]
        bfile = CLAUDE_STATE_DIR / f"{bkey}.breadcrumb.json"
        if not bfile.exists():
            return ""
        data = json.loads(bfile.read_text(encoding="utf-8"))
        gate = data.get("gate_outcomes", {})
        deny_count = gate.get("deny_count", 0)
        still_failing = gate.get("override_still_failing", []) or []
        if deny_count > 0 and still_failing:
            return (
                "## Prior Session Gate Overrides (WARNING)\n"
                f"Last session ended with {deny_count} gate override(s).\n"
                f"Gates that were FORCED past without resolution: "
                f"{', '.join(still_failing)}.\n"
                "Consider addressing these before adding new work.\n\n"
            )
        if deny_count > 0:
            return (
                f"## Prior Session Gate Note\n"
                f"Last session had {deny_count} gate override(s); "
                "all resolved before completion.\n\n"
            )
    except Exception:
        pass
    return ""




def _core_skill_digests() -> str:
    """Always-active core skill set (2026-07-18): inject real skill content at
    session start instead of name whispers. Config: hooks/core-skill-set.json."""
    try:
        cfg = json.loads((HOOK_DIR / "core-skill-set.json").read_text(encoding="utf-8"))
    except Exception:
        return ""
    idx = {}
    try:
        idx = json.loads((HOOK_DIR / "skills-index.json").read_text(encoding="utf-8")).get("skills") or {}
    except Exception:
        pass
    out = ["[Always-active core skills]"]
    for ent in cfg.get("always", []):
        name = ent.get("skill") or ""
        sk = Path.home() / ".claude" / "skills" / name / "SKILL.md"
        if ent.get("mode") == "full" and sk.is_file():
            try:
                raw = sk.read_text(encoding="utf-8", errors="replace")
                if raw.startswith("---"):
                    end = raw.find("\n---", 3)
                    if end != -1:
                        raw = raw[end + 4:]
                raw = raw.strip()[: int(ent.get("max_chars", 5000))]
                out.append(f"### skill: {name}\n{raw}")
            except OSError:
                continue
        else:
            desc = ((idx.get(name) or {}).get("description") or "").strip()
            out.append(f"- {name} (on demand via Skill tool) — {desc[:180]}")
    return "\n\n".join(out) if len(out) > 1 else ""

def main() -> int:
    _cleanup_stale_state()

    raw_in = sys.stdin.read()
    payload_txt = raw_in if raw_in.strip() else "{}"

    aggregated = ""

    # Prior gate override warning (highest priority — surface before other context)
    try:
        payload_for_gate = json.loads(payload_txt)
        roots = payload_for_gate.get("workspace_roots", [])
        workspace_for_gate = Path(roots[0]) if roots else None
        if workspace_for_gate:
            gate_ctx = _prior_gate_override_context(workspace_for_gate)
            if gate_ctx:
                aggregated = _merge_additional_context(aggregated, gate_ctx)
    except Exception:
        pass

    # Pre-compact handoff injection (inject after gate warnings)
    precompact_ctx = _precompact_handoff_context(payload_txt)
    if precompact_ctx:
        aggregated = _merge_additional_context(aggregated, precompact_ctx)

    hook_jobs: list[tuple[list[str], int]] = []
    if SESSION_GATE.is_file():
        hook_jobs.append((["python3", str(SESSION_GATE)], 10))
    if DOC_LIFECYCLE.is_file():
        hook_jobs.append((["python3", str(DOC_LIFECYCLE), "session-start"], 8))
    # ONE lifecycle probe replaces the jcodemunch/graphify/jdocmunch index
    # guards + the dox session sweep: it probes all four surfaces in parallel
    # and auto-spawns detached background builders for MISSING/STALE ones
    # (STALE/MISSING still VISIBLY reported; the build is spawned automatically
    # instead of demanded of the agent — Charter §7).
    if INDEX_LIFECYCLE.is_file():
        hook_jobs.append((["python3", str(INDEX_LIFECYCLE), "session-start"], 8))
    if TDD_INIT_GUARD.is_file():
        hook_jobs.append((["python3", str(TDD_INIT_GUARD), "session"], 8))

    if hook_jobs:
        with ThreadPoolExecutor(max_workers=min(5, len(hook_jobs))) as pool:
            futures = {
                pool.submit(_run_hook_subprocess, cmd, payload_txt, timeout): cmd
                for cmd, timeout in hook_jobs
            }
            for fut in as_completed(futures):
                chunk = fut.result()
                if chunk:
                    aggregated = _merge_additional_context(aggregated, chunk)

    # Legacy sequential block removed — parallelized above

    # Single reference line (routing MD is in always-on rules — no excerpt needed)
    if ROUTING_MD.is_file():
        route_ctx = f"Lifecycle routing: `{ROUTING_MD.resolve()}`"
        aggregated = _merge_additional_context(aggregated, route_ctx)

    core_ctx = _core_skill_digests()
    if core_ctx.strip():
        aggregated = _merge_additional_context(aggregated, core_ctx)

    sp_ctx = _superpowers_session_context()
    if sp_ctx.strip():
        aggregated = _merge_additional_context(aggregated, sp_ctx)

    mcp_ctx = _configured_mcp_context()
    if mcp_ctx.strip():
        aggregated = _merge_additional_context(aggregated, mcp_ctx)

    # Hard cap: trim to MAX_AGGREGATED_CHARS to prevent runaway output
    if len(aggregated) > MAX_AGGREGATED_CHARS:
        aggregated = aggregated[:MAX_AGGREGATED_CHARS - 30] + "\n…(aggregator trimmed)"

    if not aggregated.strip():
        print("{}")
        return 0

    print(json.dumps({
        "additionalContext": aggregated,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
