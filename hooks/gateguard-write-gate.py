#!/usr/bin/env python3
"""GateGuard: PreToolUse hook on Write/Edit — blast radius awareness.

When the target file is imported by >= THRESHOLD other files, emit
permissionDecision:"ask" so the user gets a yes/no prompt with a detailed
impact report (every importing file, the actual import line, exported
symbols of the target). Once acknowledged for a file in a conversation,
subsequent writes pass through.

Skips: new files, test files, docs, config, state files, lock files.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tool_compat import is_write_tool, tool_name

THRESHOLD = 5  # files referencing target -> trigger prompt
MAX_IMPORTERS_LISTED = 40
MAX_LINES_PER_IMPORTER = 2
MAX_EXPORTS_LISTED = 20

SKIP_PATTERNS = (
    "_test.go", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx",
    "test_", "tests/", "__tests__/",
    ".md", ".mdx", ".json", ".yaml", ".yml", ".toml", ".env",
    ".lock", "lock.json", "node_modules/", ".state/",
    "server_docs/", "frontend_docs/", "docs/",
    "plan-", ".css", ".svg", ".png", ".jpg",
)

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR / ".state"


def _should_skip(file_path: str) -> bool:
    if not file_path:
        return True
    fp_lower = file_path.lower()
    for pat in SKIP_PATTERNS:
        if pat in fp_lower:
            return True
    if not os.path.isfile(file_path):
        return True
    return False


def _find_project_root(file_path: str) -> str:
    current = os.path.dirname(file_path)
    for _ in range(15):
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.dirname(file_path)


def _grep_pattern_for(file_path: str) -> tuple[str, list[str]]:
    """Return (regex_pattern, include_flags) for files that import this target."""
    basename = os.path.basename(file_path)
    stem = os.path.splitext(basename)[0]
    ext = os.path.splitext(basename)[1].lower()

    if ext == ".go":
        pattern = f'".*/{re.escape(stem)}"|package {re.escape(stem)}'
        includes = ["--include=*.go"]
    else:
        pattern = "from.*/" + re.escape(stem) + "|require.*/" + re.escape(stem)
        includes = [
            "--include=*.ts", "--include=*.tsx",
            "--include=*.js", "--include=*.jsx",
        ]
    return pattern, includes


def _gather_importers(file_path: str, search_root: str) -> list[dict]:
    """Return [{path, lines: [{lineno, text}]}] for files that import this target."""
    basename = os.path.basename(file_path)
    stem = os.path.splitext(basename)[0]
    _SHORT_STEMS = {"app", "main", "index", "types", "routes", "gorm", "db", "api", "lib", "util"}
    if not stem or len(stem) < 6 or stem.lower() in _SHORT_STEMS:
        return []

    pattern, includes = _grep_pattern_for(file_path)

    try:
        cmd = ["grep", "-rn"] + includes + [
            "--exclude-dir=node_modules", "--exclude-dir=.git",
            "--exclude-dir=dist", "--exclude-dir=build",
            "-E", pattern, search_root,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if result.returncode not in (0, 1):
            return []
    except (subprocess.TimeoutExpired, OSError):
        return []

    by_file: dict[str, list[dict]] = {}
    self_abs = os.path.abspath(file_path)
    for raw in result.stdout.splitlines():
        # Format: <path>:<lineno>:<text>
        parts = raw.split(":", 2)
        if len(parts) < 3:
            continue
        path, lineno_str, text = parts
        if not path or os.path.abspath(path) == self_abs:
            continue
        try:
            lineno = int(lineno_str)
        except ValueError:
            continue
        by_file.setdefault(path, []).append({"lineno": lineno, "text": text})

    return [{"path": p, "lines": lines} for p, lines in sorted(by_file.items())]


def _extract_exports(file_path: str) -> list[str]:
    """Cheap export-symbol extraction. Best effort, no AST."""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return []

    names: list[str] = []
    if ext in (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"):
        patterns = [
            r"^export\s+(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"^export\s+(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"^export\s+class\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"^export\s+interface\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"^export\s+type\s+([A-Za-z_][A-Za-z0-9_]*)",
            r"^export\s+enum\s+([A-Za-z_][A-Za-z0-9_]*)",
        ]
        for pat in patterns:
            for m in re.finditer(pat, content, flags=re.MULTILINE):
                names.append(m.group(1))
        if re.search(r"^export\s+default\b", content, flags=re.MULTILINE):
            names.append("default")
    elif ext == ".go":
        for m in re.finditer(
            r"^(?:func\s+(?:\([^)]*\)\s+)?|type\s+|const\s+|var\s+)([A-Z][A-Za-z0-9_]*)",
            content,
            flags=re.MULTILINE,
        ):
            names.append(m.group(1))

    # Dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _build_impact_report(file_path: str, importers: list[dict]) -> str:
    basename = os.path.basename(file_path)
    search_root = _find_project_root(file_path)
    exports = _extract_exports(file_path)

    lines: list[str] = []
    lines.append(f"GATEGUARD — high-blast-radius write to `{basename}`")
    lines.append("")
    lines.append(f"Target: {file_path}")
    lines.append(f"Imported by: {len(importers)} file(s)")
    if exports:
        shown = ", ".join(exports[:MAX_EXPORTS_LISTED])
        suffix = f" (+{len(exports) - MAX_EXPORTS_LISTED} more)" if len(exports) > MAX_EXPORTS_LISTED else ""
        lines.append(f"Exports detected: {shown}{suffix}")
    lines.append("")
    lines.append("Files that import this module:")

    for entry in importers[:MAX_IMPORTERS_LISTED]:
        try:
            rel = os.path.relpath(entry["path"], search_root)
        except ValueError:
            rel = entry["path"]
        lines.append(f"  - {rel}")
        for ln in entry["lines"][:MAX_LINES_PER_IMPORTER]:
            snippet = ln["text"].strip()
            if len(snippet) > 140:
                snippet = snippet[:140] + "…"
            lines.append(f"      L{ln['lineno']}: {snippet}")
        extra = len(entry["lines"]) - MAX_LINES_PER_IMPORTER
        if extra > 0:
            lines.append(f"      …+{extra} more reference(s) in this file")

    if len(importers) > MAX_IMPORTERS_LISTED:
        lines.append(f"  …+{len(importers) - MAX_IMPORTERS_LISTED} more importer(s) not shown")

    lines.append("")
    lines.append("Risks to confirm before approving:")
    lines.append(f"  1. Will all {len(importers)} importing files still compile after this change?")
    lines.append("  2. Are any exported signatures changing? Every caller above will need updating if so.")
    lines.append("  3. Is downstream runtime behavior preserved (props, return shapes, side effects)?")
    lines.append("")
    lines.append("Approve = proceed with this write (and future writes to this file this session).")
    lines.append("Deny    = back out so the change can be re-scoped.")
    return "\n".join(lines)


def _get_conversation_state(cid: str) -> dict:
    if not cid:
        return {}
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    state_file = STATE_DIR / f"{safe}.gateguard.json"
    if state_file.is_file():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_conversation_state(cid: str, state: dict) -> None:
    if not cid:
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    state_file = STATE_DIR / f"{safe}.gateguard.json"
    state_file.write_text(json.dumps(state), encoding="utf-8")


# ---------------------------------------------------------------------------
# Blast-radius bypass — typed, session-sticky
#
# Primary UX: the user types "blast-bypass" anywhere in chat. From that point
# on, gateguard stops prompting on high-blast-radius writes for the REST of
# that session and lets every edit through like any other file. It resets
# automatically in the next session (new transcript / conversation).
#
# Once detected, the sticky state is cached on the conversation state file so
# later writes don't rescan the transcript.
#
# Extra (optional, non-typed) overrides also honored:
#   - Env var  BLAST_BYPASS / CLAUDE_BLAST_BYPASS / GATEGUARD_BYPASS = truthy
#   - Marker   ~/.claude/.blast-bypass exists (manual global on/off)
# ---------------------------------------------------------------------------
BYPASS_TOKEN = "blast-bypass"
_BYPASS_ENV_VARS = ("BLAST_BYPASS", "CLAUDE_BLAST_BYPASS", "GATEGUARD_BYPASS")
_TRUTHY = {"1", "true", "yes", "on", "y"}
_BYPASS_MARKER = SCRIPT_DIR.parent / ".blast-bypass"  # ~/.claude/.blast-bypass
_TRANSCRIPT_SCAN_LINES = 4000  # how far back to look for the typed token


def _entry_text(entry: dict) -> str:
    """Best-effort text extraction from a transcript JSONL entry (flat or nested)."""
    content = entry.get("content")
    if content is None and isinstance(entry.get("message"), dict):
        content = entry["message"].get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""


def _transcript_has_token(transcript_path: str) -> bool:
    """True if BYPASS_TOKEN appears in any recent *user-typed* message.

    Only genuine user text counts — tool_result blocks (also role "user")
    carry no "text" field, so _entry_text ignores them and command output
    that merely echoes the word can't flip the flag.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return False
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-_TRANSCRIPT_SCAN_LINES:]
    except OSError:
        return False
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        role = entry.get("role") or entry.get("type") or ""
        if role != "user" and isinstance(entry.get("message"), dict):
            role = entry["message"].get("role", role)
        if role != "user":
            continue
        if BYPASS_TOKEN in _entry_text(entry).lower():
            return True
    return False


def _bypass_active(payload: dict, cid: str, state: dict) -> bool:
    """Return True if blast-radius prompting should be skipped for this write."""
    # Optional non-typed overrides.
    for var in _BYPASS_ENV_VARS:
        if os.environ.get(var, "").strip().lower() in _TRUTHY:
            return True
    try:
        if _BYPASS_MARKER.exists():
            return True
    except OSError:
        pass

    # Sticky: already turned on earlier this session.
    if state.get("blast_bypass") is True:
        return True

    # Typed this session -> turn sticky on and persist for the rest of it.
    if _transcript_has_token(payload.get("transcript_path", "")):
        state["blast_bypass"] = True
        _save_conversation_state(cid, state)
        return True

    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0

    name = tool_name(payload)
    if not is_write_tool(name):
        print("{}")
        return 0

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if _should_skip(file_path):
        print("{}")
        return 0

    cid = (payload.get("conversation_id") or payload.get("session_id") or "")
    state = _get_conversation_state(cid)

    # blast-bypass: once the user types "blast-bypass" this session, stay
    # bypassed for the rest of it (resets next session). Also honors the
    # optional env var / manual marker overrides.
    if _bypass_active(payload, cid, state):
        print("{}")
        return 0

    acked_files = state.get("acked_files") or state.get("warned_files") or []

    if file_path in acked_files:
        print("{}")
        return 0

    abs_path = os.path.abspath(file_path)
    search_root = _find_project_root(file_path)

    importer_cache = state.get("importer_cache", {})
    if isinstance(importer_cache, dict) and abs_path in importer_cache:
        importers = importer_cache[abs_path]
    else:
        importers = _gather_importers(file_path, search_root)
        if not isinstance(importer_cache, dict):
            importer_cache = {}
        importer_cache[abs_path] = importers
        state["importer_cache"] = importer_cache

    ref_count = len(importers)
    if ref_count >= THRESHOLD:
        acked_files.append(file_path)
        state["acked_files"] = acked_files
        _save_conversation_state(cid, state)

        basename = os.path.basename(file_path)
        full_report = _build_impact_report(file_path, importers)

        report_path = Path(os.path.expanduser("~/.claude/.gateguard-last-impact.md"))
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(full_report + "\n", encoding="utf-8")
        except OSError:
            pass

        print(full_report, file=sys.stderr)

        first_five = []
        for entry in importers[:5]:
            try:
                first_five.append(os.path.relpath(entry["path"], search_root))
            except ValueError:
                first_five.append(entry["path"])
        importers_preview = ", ".join(first_five)
        if len(importers) > 5:
            importers_preview += f", +{len(importers) - 5} more"

        short_reason = (
            f"`{basename}` is imported by {ref_count} other file(s): "
            f"{importers_preview}. "
            f"Full impact report (every importer + import line + exports detected) "
            f"saved to {report_path} and printed to hook stderr. "
            f"Approve to proceed with this write; deny to re-scope."
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": short_reason,
            }
        }))
    else:
        _save_conversation_state(cid, state)
        print("{}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
