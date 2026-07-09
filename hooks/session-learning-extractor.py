#!/usr/bin/env python3
"""Stop hook: extract durable learnings from the completed session.

Fires on Stop (status: completed, stopped, or interrupted).
When code_writes >= 3, emits a followup_message prompting the model
to surface 1-3 durable learnings and write them to CODEX.md.

Also checks if CODEX.md exceeds 600 lines and trims oldest "Patterns We Use"
entries when the limit is exceeded.

Outputs:
  1. {workspace}/CODEX.md   — living per-project decision document
  2. ~/.gstack/projects/{slug}/learnings.jsonl  — via gstack-learnings-log binary
  3. ~/.claude/hooks/.telemetry/learnings.jsonl — local fallback (always)

Environment:
  DRY_RUN=1   Print what would be written, write nothing.

stdin:  Claude Code Stop JSON payload
stdout: JSON { followup_message: "..." } or {}
exit:   always 0 (fail open)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOOK_DIR      = Path(__file__).resolve().parent
STATE_DIR     = HOOK_DIR / ".state"
TELEMETRY_DIR = HOOK_DIR / ".telemetry"

# CODEX.md trim settings
CODEX_MAX_LINES     = 600
CODEX_TRIM_SECTION  = "Patterns We Use"  # oldest entries in this section are trimmed
CODEX_TRIM_KEEP_MIN = 5   # always keep at least 5 entries in the section after trim

# Minimum writes to trigger learning extraction
MIN_WRITES_FOR_LEARNING = 3

DRY_RUN = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes")


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _code_writes(cid: str) -> int:
    safe = _safe_cid(cid)
    p = STATE_DIR / f"{safe}.desloppify.json"
    if not p.is_file():
        return 0
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get("code_writes", 0))
    except Exception:
        return 0


def _workspace_from_payload(payload: dict) -> Path | None:
    roots = payload.get("workspace_roots") or []
    if isinstance(roots, list) and roots:
        p = Path(roots[0])
        if p.is_dir():
            return p
    # Fallback: try cwd
    cwd = Path(os.getcwd())
    if cwd != Path.home():
        return cwd
    return None


def _project_slug(workspace: Path | None) -> str:
    """Convert workspace path to a URL-safe slug for gstack project directory."""
    if not workspace:
        return "unknown"
    # e.g. /path/to/site-sync-vista → site-sync-vista
    return re.sub(r"[^a-zA-Z0-9_-]", "-", workspace.name).strip("-") or "unknown"


def _read_codex(codex_path: Path) -> str:
    if not codex_path.is_file():
        return ""
    try:
        return codex_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _codex_needs_trim(content: str) -> bool:
    return len(content.splitlines()) > CODEX_MAX_LINES


def _trim_codex(content: str) -> str:
    """Remove oldest entries from the '## Patterns We Use' section.

    Strategy: find the section, find list items (lines starting with `- `),
    remove the earliest (top) ones until line count drops below CODEX_MAX_LINES.
    Never removes the section header or other sections.
    """
    lines = content.splitlines(keepends=True)
    if len(lines) <= CODEX_MAX_LINES:
        return content

    # Find section start
    section_header_re = re.compile(
        r"^#{1,3}\s+" + re.escape(CODEX_TRIM_SECTION), re.IGNORECASE
    )
    section_start = None
    section_end   = None
    next_section_re = re.compile(r"^#{1,3}\s+", re.IGNORECASE)

    for i, line in enumerate(lines):
        if section_start is None and section_header_re.match(line):
            section_start = i
        elif section_start is not None and section_end is None:
            if i > section_start and next_section_re.match(line):
                section_end = i
                break

    if section_start is None:
        # Section not found — cannot trim safely
        return content

    if section_end is None:
        section_end = len(lines)

    # Find list items within section
    item_indices = [
        i for i in range(section_start + 1, section_end)
        if lines[i].lstrip().startswith("- ")
    ]

    if len(item_indices) <= CODEX_TRIM_KEEP_MIN:
        return content  # Not enough items to safely trim

    # Remove oldest items (from the top of the section) until within limit
    to_remove: set[int] = set()
    current_len = len(lines)
    for idx in item_indices:
        if current_len <= CODEX_MAX_LINES:
            break
        if len(item_indices) - len(to_remove) <= CODEX_TRIM_KEEP_MIN:
            break
        to_remove.add(idx)
        current_len -= 1

    trimmed = [line for i, line in enumerate(lines) if i not in to_remove]
    return "".join(trimmed)


def _write_codex(codex_path: Path, content: str) -> None:
    if DRY_RUN:
        print(f"[DRY_RUN] Would write CODEX.md ({len(content.splitlines())} lines): {codex_path}",
              file=sys.stderr)
        return
    try:
        codex_path.parent.mkdir(parents=True, exist_ok=True)
        codex_path.write_text(content, encoding="utf-8")
    except OSError as e:
        print(f"Warning: could not write CODEX.md: {e}", file=sys.stderr)


def _append_telemetry_learning(record: dict) -> None:
    if DRY_RUN:
        print(f"[DRY_RUN] Would append to telemetry learnings.jsonl: {record}", file=sys.stderr)
        return
    try:
        TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        p = TELEMETRY_DIR / "learnings.jsonl"
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
    except OSError as e:
        print(f"Warning: could not write telemetry learnings.jsonl: {e}", file=sys.stderr)


def _call_gstack_learnings_log(slug: str, record: dict) -> bool:
    """Attempt to call gstack-learnings-log binary. Returns True on success."""
    binary = shutil.which("gstack-learnings-log")
    if not binary:
        # Also try common install locations
        candidates = [
            Path.home() / ".gstack" / "bin" / "gstack-learnings-log",
            Path.home() / ".claude" / "skills" / "gstack" / "bin" / "gstack-learnings-log",
            Path("/usr/local/bin/gstack-learnings-log"),
        ]
        for c in candidates:
            if c.is_file() and os.access(c, os.X_OK):
                binary = str(c)
                break

    if not binary:
        return False

    if DRY_RUN:
        print(f"[DRY_RUN] Would call: {binary} '{json.dumps(record)}'", file=sys.stderr)
        return True

    try:
        result = subprocess.run(
            [binary, json.dumps(record)],
            timeout=8,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _bootstrap_codex_if_absent(codex_path: Path, workspace: Path) -> str:
    """Create a minimal CODEX.md skeleton if it does not exist."""
    template = f"""# CODEX — {workspace.name}

Project decision document. Maintained by Claude Code at session end.
Read this BEFORE any source files. It contains prior decisions and known pitfalls.

---

## Architecture Decisions

<!-- Add key architectural choices here: framework selections, auth patterns, DB schema rationale -->

## Patterns We Use

<!-- List accepted patterns with rationale. e.g. "- Use RTK Query for all API calls (not axios directly) — keeps cache invalidation consistent" -->

## Things We Tried That Failed

<!-- Negative knowledge is as valuable as positive. e.g. "- Zustand for auth slice: abandoned because SSR hydration caused race conditions" -->

## Known Fragile Areas

<!-- Files / modules that frequently break or require extra care -->

## Naming Conventions

<!-- e.g. "- Event handlers: handleVerbNoun (not onVerbNoun)" -->

---
*Last updated: {_now_iso()}*
"""
    return template


# ── GSD LEARNINGS.md bridge ───────────────────────────────────────────────────

def _find_recent_learnings_md(workspace: Path, cid: str) -> list[Path]:
    """Find .planning/phases/*/LEARNINGS.md files modified in the last 24 hours.

    We use mtime as a proxy for "written this session" — reliable enough since
    sessions are typically < 2 hours, and 24h gives comfortable margin.
    """
    planning_dir = workspace / ".planning" / "phases"
    if not planning_dir.is_dir():
        return []

    import time
    cutoff = time.time() - 86400  # 24 hours ago

    found: list[Path] = []
    try:
        for phase_dir in planning_dir.iterdir():
            if not phase_dir.is_dir():
                continue
            candidate = phase_dir / "LEARNINGS.md"
            if candidate.is_file():
                try:
                    if candidate.stat().st_mtime >= cutoff:
                        found.append(candidate)
                except OSError:
                    continue
    except OSError:
        pass

    return found


def _parse_learnings_md(path: Path) -> list[dict]:
    """Parse a LEARNINGS.md file into structured learning records.

    Expected format (from gsd-extract-learnings):
      ## Key Decisions
      - Decision text here
      - Another decision

      ## Lessons Learned
      - Lesson text here

      ## Patterns
      - Pattern text here

    Returns list of dicts with keys: type, key, insight, source, phase
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    records: list[dict] = []
    phase_name = path.parent.name  # e.g. "phase-01-auth"

    # Section → type mapping
    section_types: dict[str, str] = {
        "key decisions":    "decision",
        "decisions":        "decision",
        "lessons learned":  "lesson",
        "lessons":          "lesson",
        "patterns":         "pattern",
        "surprises":        "lesson",
        "open questions":   "question",
    }

    current_type = "lesson"
    section_re = re.compile(r"^#{1,3}\s+(.+)$")
    item_re    = re.compile(r"^[-*]\s+(.+)$")

    for line in content.splitlines():
        line = line.rstrip()
        section_match = section_re.match(line)
        if section_match:
            title = section_match.group(1).strip().lower()
            for key, t in section_types.items():
                if key in title:
                    current_type = t
                    break
            continue

        item_match = item_re.match(line)
        if item_match:
            text = item_match.group(1).strip()
            if not text or len(text) < 10:
                continue
            # Build a stable key from the first 40 chars
            key = re.sub(r"[^a-z0-9]", "-", text[:40].lower()).strip("-")
            records.append({
                "type":    current_type,
                "key":     key,
                "insight": text,
                "source":  "phase-artifact",
                "phase":   phase_name,
            })

    return records


def _write_gstack_learnings(slug: str, records: list[dict]) -> int:
    """Write parsed learning records to gstack JSONL and via binary.

    Returns count of records written.
    """
    if not records:
        return 0

    written = 0
    gstack_dir = Path.home() / ".gstack" / "projects" / slug
    jsonl_path = gstack_dir / "learnings.jsonl"

    for rec in records:
        full_record = {
            "skill":      "gsd-learnings-bridge",
            "type":       rec.get("type", "lesson"),
            "key":        rec.get("key", "unknown"),
            "insight":    rec.get("insight", ""),
            "confidence": 7,  # phase artifacts are high-confidence
            "source":     rec.get("source", "phase-artifact"),
            "phase":      rec.get("phase", ""),
            "ts":         _now_iso(),
        }

        # Write to gstack JSONL directly (create directory if needed)
        if DRY_RUN:
            print(f"[DRY_RUN] Would append to {jsonl_path}: {full_record}", file=sys.stderr)
        else:
            try:
                gstack_dir.mkdir(parents=True, exist_ok=True)
                with jsonl_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(full_record, ensure_ascii=False) + "\n")
                    fh.flush()
            except OSError as e:
                print(f"Warning: could not write {jsonl_path}: {e}", file=sys.stderr)
                continue

        # Also call gstack-learnings-log binary for cross-system sync
        binary_record = {
            "skill":      full_record["skill"],
            "type":       full_record["type"],
            "key":        full_record["key"],
            "insight":    full_record["insight"],
            "confidence": full_record["confidence"],
            "source":     full_record["source"],
        }
        _call_gstack_learnings_log(slug, binary_record)  # failure is silent

        # Append to local telemetry fallback
        _append_telemetry_learning(full_record)

        written += 1

    return written


def _run_gsd_learnings_bridge(workspace: Path | None, slug: str, cid: str) -> int:
    """Detect recent LEARNINGS.md files and bridge them to gstack. Returns record count."""
    if not workspace:
        return 0

    learnings_files = _find_recent_learnings_md(workspace, cid)
    if not learnings_files:
        return 0

    total_written = 0
    for lf in learnings_files:
        records = _parse_learnings_md(lf)
        written = _write_gstack_learnings(slug, records)
        total_written += written

    return total_written


def _build_followup_message(
    workspace: Path | None,
    codex_path: Path,
    code_writes: int,
    codex_exists: bool,
) -> str:
    codex_ref = str(codex_path) if workspace else "project CODEX.md"
    action = "updating" if codex_exists else "creating"

    return (
        f"[Session Learning Extractor]\n"
        f"This session wrote {code_writes} code file(s). "
        f"Before completing, surface 1–3 durable learnings:\n\n"
        f"1. Any new pattern adopted (why it was chosen over alternatives)?\n"
        f"2. Any architectural decision made (constraints, tradeoffs)?\n"
        f"3. Any known fragile area discovered?\n\n"
        f"If yes, append each learning to `{codex_ref}` under the matching section "
        f"({action} the file if needed). "
        f"Format: `- [LEARNING] <concise statement> — <1-line rationale>`\n\n"
        f"If no durable learnings from this session, skip CODEX.md update. "
        f"This message fires once per session."
    )


def main() -> int:
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw)
    except Exception:
        sys.stdout.write("{}\n")
        return 0

    # Gate: only fire on completed/stopped/interrupted sessions
    status = (payload.get("status") or "").strip()
    if status not in ("completed", "stopped", "interrupted"):
        sys.stdout.write("{}\n")
        return 0

    cid = (payload.get("conversation_id") or payload.get("session_id") or "").strip()
    if not cid:
        sys.stdout.write("{}\n")
        return 0

    # Gate: only fire when enough code was written
    writes = _code_writes(cid)
    if writes < MIN_WRITES_FOR_LEARNING:
        sys.stdout.write("{}\n")
        return 0

    # Gate: only fire once per session (check state)
    safe = _safe_cid(cid)
    state_path = STATE_DIR / f"{safe}.learning-extractor.json"
    if state_path.is_file():
        sys.stdout.write("{}\n")
        return 0

    workspace = _workspace_from_payload(payload)
    codex_path = workspace / "CODEX.md" if workspace else None
    slug = _project_slug(workspace)

    # Read existing CODEX.md (or bootstrap skeleton)
    codex_content = ""
    codex_exists = False
    if codex_path:
        codex_content = _read_codex(codex_path)
        codex_exists = bool(codex_content.strip())
        if not codex_exists:
            codex_content = _bootstrap_codex_if_absent(codex_path, workspace)
            _write_codex(codex_path, codex_content)
        elif _codex_needs_trim(codex_content):
            trimmed = _trim_codex(codex_content)
            _write_codex(codex_path, trimmed)

    # Write telemetry record (session-level metadata)
    telemetry_record = {
        "ts":          _now_iso(),
        "cid":         cid,
        "slug":        slug,
        "code_writes": writes,
        "event":       "learning_prompt_emitted",
    }
    _append_telemetry_learning(telemetry_record)

    # Attempt gstack-learnings-log call (fires an event; actual content is model-driven)
    gstack_record = {
        "skill":      "session-learning-extractor",
        "type":       "session-end",
        "key":        f"session-end-{cid[:8]}",
        "insight":    f"Session ended: {writes} code writes on {slug}. Learning prompt emitted.",
        "confidence": 5,
        "source":     "session-hook",
    }
    _call_gstack_learnings_log(slug, gstack_record)

    # ── GSD bridge: if LEARNINGS.md was written this session, bridge it ────────
    if workspace:
        bridge_count = _run_gsd_learnings_bridge(workspace, slug, cid)
        if bridge_count > 0 and not DRY_RUN:
            # Update telemetry record to note the bridge fired
            _append_telemetry_learning({
                "ts":             _now_iso(),
                "cid":            cid,
                "slug":           slug,
                "event":          "gsd_bridge_fired",
                "records_bridged": bridge_count,
            })
    # ───────────────────────────────────────────────────────────────────────────

    # Mark as fired for this session
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"fired": True, "ts": _now_iso(), "writes": writes}),
            encoding="utf-8",
        )
    except OSError:
        pass

    # Emit the learning prompt
    followup = _build_followup_message(workspace, codex_path, writes, codex_exists)
    sys.stdout.write(json.dumps({"followup_message": followup}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
