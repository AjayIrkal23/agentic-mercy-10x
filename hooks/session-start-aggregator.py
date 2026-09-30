#!/usr/bin/env python3
"""
SessionStart aggregator — one advisory link that merges:

  * prior-session gate-override warning (breadcrumb state),
  * the pre-compact handoff snapshot (if one exists for this session),
  * index-lifecycle session-start probe + tdd-guard init (subprocesses, parallel),
  * the always-active core skill digests (hooks/core-skill-set.json),
  * the superpowers bootstrap pointer and the configured MCP roster.

``payload.source`` shapes the output:
  startup | clear  -> everything above
  compact          -> only the pre-compact handoff
  resume           -> handoff + a one-line "resumed" note

stdin:  SessionStart payload (cwd, source, session_id, ...).
stdout: {"additionalContext": "..."} or {}. Always exit 0.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HOME = Path.home()
HOOK_DIR = Path(__file__).resolve().parent  # this checkout, not $HOME (CI runs elsewhere)
STATE_DIR = HOOK_DIR / ".state"
STATE_MAX_AGE_SECONDS = 86400  # 24 hours
UNKNOWN_MAX_AGE_SECONDS = 3600  # 1 hour — unknown.*.json (session id was missing)
MCP_JSON = HOME / ".claude.json"
MCP_USAGE_SKILL = HOOK_DIR.parent / "skills" / "mcp-usage-standards" / "SKILL.md"
INDEX_LIFECYCLE = HOOK_DIR / "index-lifecycle.py"
TDD_INIT_GUARD = HOOK_DIR / "tdd-guard-init-guard.py"
PLUGINS_ROOT = HOOK_DIR.parent / "plugins"
# Claude Code persists a hook's additionalContext over 8,000 chars to a file and shows
# the model a ~2 KB preview. dispatch.py merges every session-start link into one
# output, so this link keeps to 5,500 and leaves room for the memory directive,
# the breadcrumb and the style directive (see test_session_start_budget.py).
MAX_AGGREGATED_CHARS = 5500

if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))


def _cleanup_stale_state() -> None:
    """Drop .state/*.json older than 24h (unknown.*.json after 1h)."""
    try:
        if not STATE_DIR.is_dir():
            return
        now = time.time()
        for f in STATE_DIR.iterdir():
            if f.suffix != ".json":
                continue
            try:
                ttl = UNKNOWN_MAX_AGE_SECONDS if f.name.startswith("unknown.") else STATE_MAX_AGE_SECONDS
                if now - f.stat().st_mtime > ttl:
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
    line = ", ".join(sorted(srv.keys()))
    if len(line) > 260:
        line = line[:257] + "…"
    return (
        "### Configured MCP servers (this machine)\n\n"
        f"**Names:** {line}\n\n"
        f"Routing: `{MCP_USAGE_SKILL}`"
    )


def _precompact_handoff_context(payload: dict) -> str:
    """Inject {session}.precompact-handoff.json (written by session-lifecycle
    pre-compact) when it is recent (≤2 h)."""
    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        return ""
    safe_cid = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(cid))
    handoff_path = STATE_DIR / f"{safe_cid}.precompact-handoff.json"
    try:
        if time.time() - handoff_path.stat().st_mtime > 7200:
            return ""
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(handoff, dict):
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
        lines.append(f"  active_phase: {str(handoff['active_phase'])[:200]}")
    return "\n".join(lines)


def _run_hook_subprocess(cmd: list[str], payload_txt: str, timeout: int) -> str:
    try:
        proc = subprocess.run(cmd, input=payload_txt, capture_output=True,
                              text=True, timeout=timeout)
        if proc.returncode == 0 and proc.stdout.strip():
            blob = json.loads(proc.stdout)
            if isinstance(blob, dict):
                hso = blob.get("hookSpecificOutput")
                chunk = (hso.get("additionalContext") if isinstance(hso, dict) else None) \
                    or blob.get("additionalContext") or blob.get("additional_context")
                if isinstance(chunk, str):
                    return chunk
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return ""


def _prior_gate_override_context(workspace: Path) -> str:
    """Read the prior session's breadcrumb and warn if gates were overridden."""
    try:
        bkey = hashlib.sha1(str(workspace).encode()).hexdigest()[:12]
        bfile = STATE_DIR / f"{bkey}.breadcrumb.json"
        if not bfile.exists():
            return ""
        gate = json.loads(bfile.read_text(encoding="utf-8")).get("gate_outcomes", {})
        deny_count = gate.get("deny_count", 0)
        still_failing = gate.get("override_still_failing", []) or []
        if deny_count > 0 and still_failing:
            return (
                "## Prior Session Gate Overrides (WARNING)\n"
                f"Last session ended with {deny_count} gate override(s).\n"
                f"Gates that were FORCED past without resolution: {', '.join(still_failing)}.\n"
                "Consider addressing these before adding new work."
            )
        if deny_count > 0:
            return (f"## Prior Session Gate Note\nLast session had {deny_count} gate "
                    "override(s); all resolved before completion.")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _canonical(name: str) -> str:
    try:
        from lib import skill_aliases
        return skill_aliases.canonical(name)
    except Exception:  # noqa: BLE001 - alias lib optional
        return name


def _core_skill_digests(budget: int = MAX_AGGREGATED_CHARS) -> str:
    """Always-active core skill set (hooks/core-skill-set.json), within ``budget`` chars.
    Every skill starts as a one-line pointer; `mode: full` entries are upgraded to
    their body, in config order, only while the whole block still fits."""
    try:
        cfg = json.loads((HOOK_DIR / "core-skill-set.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return ""
    idx = {}
    try:
        idx = json.loads((HOOK_DIR / "skills-index.json").read_text(encoding="utf-8")).get("skills") or {}
    except Exception:  # noqa: BLE001
        pass
    header = ("[Always-active core skills] — load a pointer with the Skill tool when it "
              "applies, or Read the SKILL.md it names")
    lines: list[str] = []
    bodies: list[str | None] = []
    seen: set[str] = set()
    for ent in cfg.get("always", []):
        name = _canonical(ent.get("skill") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        desc = " ".join(((idx.get(name) or {}).get("description") or "").split())
        sk = HOOK_DIR.parent / "skills" / name / "SKILL.md"
        # `paths:`-scoped skills are "Unknown skill" to the Skill tool until a matching
        # file is read; the path goes before the description so truncation keeps it.
        hint = f" (Read {sk.as_posix()})" if (idx.get(name) or {}).get("paths") else ""
        lines.append(f"- {name}{hint} — {desc[:150]}")
        body = None
        if ent.get("mode") == "full" and sk.is_file():
            try:
                raw = sk.read_text(encoding="utf-8", errors="replace")
                if raw.startswith("---"):
                    end = raw.find("\n---", 3)
                    if end != -1:
                        raw = raw[end + 4:]
                body = f"### skill: {name}\n{raw.strip()[: int(ent.get('max_chars', 5000))]}"
            except OSError:
                body = None
        bodies.append(body)
    if not lines:
        return ""

    def render(parts: list[str]) -> str:
        return "\n\n".join([header, "\n".join(p for p in parts if p.startswith("- ")),
                            *(p for p in parts if not p.startswith("- "))]).strip()

    for i, body in enumerate(bodies):
        if body:
            trial = lines[:i] + [body] + lines[i + 1:]
            if len(render(trial)) <= budget:
                lines = trial
    block = render(lines)
    if len(block) > budget:  # too tight even for pointers: keep names + Read paths
        block = render([p.split(" — ", 1)[0] if p.startswith("- ") else p for p in lines])
    return block[:budget]


def _full_context(payload: dict, payload_txt: str) -> str:
    aggregated = ""
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        aggregated = _merge_additional_context(aggregated, _prior_gate_override_context(Path(cwd)))
    aggregated = _merge_additional_context(aggregated, _precompact_handoff_context(payload))

    hook_jobs: list[tuple[list[str], int]] = []
    if not os.environ.get("CLAUDE_HOOK_DOCTOR"):  # doctor/test dry-fire: both write to disk
        if INDEX_LIFECYCLE.is_file():
            hook_jobs.append(([sys.executable, str(INDEX_LIFECYCLE), "session-start"], 8))
        if TDD_INIT_GUARD.is_file():
            hook_jobs.append(([sys.executable, str(TDD_INIT_GUARD), "session"], 8))
    if hook_jobs:
        with ThreadPoolExecutor(max_workers=len(hook_jobs)) as pool:
            futures = [pool.submit(_run_hook_subprocess, cmd, payload_txt, t) for cmd, t in hook_jobs]
            for fut in futures:  # submission order -> deterministic merge
                aggregated = _merge_additional_context(aggregated, fut.result())

    tail = [_superpowers_session_context(), _configured_mcp_context()]
    sep = len("\n\n---\n\n")
    room = MAX_AGGREGATED_CHARS - len(aggregated) - sum(len(t) + sep for t in tail if t.strip()) - sep
    for chunk in (_core_skill_digests(max(room, 0)), *tail):
        aggregated = _merge_additional_context(aggregated, chunk)
    return aggregated


def main() -> int:
    _cleanup_stale_state()
    raw_in = sys.stdin.read()
    payload_txt = raw_in if raw_in.strip() else "{}"
    try:
        payload = json.loads(payload_txt)
        payload = payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        payload = {}

    source = str(payload.get("source") or "startup")
    if source == "compact":
        aggregated = _precompact_handoff_context(payload)
    elif source == "resume":
        aggregated = _merge_additional_context(
            "Session resumed — prior context restored by the harness.",
            _precompact_handoff_context(payload))
    else:
        aggregated = _full_context(payload, payload_txt)

    if len(aggregated) > MAX_AGGREGATED_CHARS:
        aggregated = aggregated[:MAX_AGGREGATED_CHARS - 30] + "\n…(aggregator trimmed)"
    if not aggregated.strip():
        print("{}")
        return 0
    print(json.dumps({"additionalContext": aggregated}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - fail open
        print("{}")
        raise SystemExit(0)
