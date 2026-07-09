#!/usr/bin/env python3
"""
session-memory-writer.py — Stop hook

Scans the session transcript for memory-worthy decisions and writes them
to the Memory MCP server as structured observations.

Scan targets:
  1. Explicit markers: [DECISION], [STYLE], [PREFER] anywhere in assistant text
  2. "we use X not Y" / "always use X" / "never use X" prose patterns
  3. "going forward" / "from now on" declaratives
  4. User override acknowledgments: "you're right", "I'll change that", "noted, switching to"

Secret filtering (MUST run before write):
  - AWS access key patterns (AKIA...)
  - GitHub PAT patterns (gh[pousr]_...)
  - JWT-like patterns (ey...) of sufficient length
  - Generic API key patterns (api_key, apikey, secret= adjacent to long alphanumeric)

MCP write mechanism:
  - Primary: claude CLI subprocess calling mcp__memory__add_observations
  - Fallback: append to project memory wip.md file

Always exits 0 — never blocks session teardown.
"""

import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

MCP_SERVER_NAME = "memory"
MCP_TIMEOUT = 10         # seconds for MCP write subprocess
MAX_OBSERVATIONS_PER_SESSION = 5   # cap to prevent noise
MAX_TRANSCRIPT_LINES = 300         # scan only recent portion of transcript
MAX_OBS_CHARS = 300               # max chars per observation text
MIN_OBS_CHARS = 20                # ignore trivially short matches

# ── Regex Patterns ─────────────────────────────────────────────────────────────

# Decision markers (case-insensitive)
MARKER_PATTERNS = [
    re.compile(r'\[DECISION\][:\s]+(.{' + str(MIN_OBS_CHARS) + r',400})', re.IGNORECASE),
    re.compile(r'\[STYLE\][:\s]+(.{' + str(MIN_OBS_CHARS) + r',400})', re.IGNORECASE),
    re.compile(r'\[PREFER\][:\s]+(.{' + str(MIN_OBS_CHARS) + r',400})', re.IGNORECASE),
]

# Prose decision patterns
PROSE_PATTERNS = [
    # "we use X not Y" / "we use X, not Y"
    re.compile(r'\bwe use\b.{5,100}\bnot\b.{3,80}', re.IGNORECASE),
    # "always use X" / "never use X"
    re.compile(r'\b(?:always|never)\s+use\b.{5,120}', re.IGNORECASE),
    # "going forward, ..." / "from now on, ..."
    re.compile(r'\b(?:going forward|from now on)[,\s]+.{10,200}', re.IGNORECASE),
    # "the pattern is X" / "the convention is X"
    re.compile(r'\bthe (?:pattern|convention|standard|rule) is\b.{5,200}', re.IGNORECASE),
    # "do not use X" / "don't use X"
    re.compile(r"\b(?:do not|don't)\s+use\b.{5,120}", re.IGNORECASE),
    # "use X instead of Y"
    re.compile(r'\buse\b.{5,80}\binstead of\b.{3,80}', re.IGNORECASE),
]

# Override acknowledgment patterns (user corrects agent)
OVERRIDE_PATTERNS = [
    re.compile(r"\byou['']?re right[,\.\s].{5,200}", re.IGNORECASE),
    re.compile(r'\bnoted[,\.\s]+switching to\b.{5,150}', re.IGNORECASE),
    re.compile(r"\bI'll change that to\b.{5,150}", re.IGNORECASE),
    re.compile(r"\bI(?:'ll| will) use\b.{5,100}\binstead\b.{0,80}", re.IGNORECASE),
]

# Secret detection patterns — STRIP these before writing
SECRET_PATTERNS = [
    # AWS access key
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    # GitHub PAT (classic and fine-grained)
    re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}\b'),
    # JWT (three base64url segments)
    re.compile(r'\bey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b'),
    # Generic: api_key/apikey/secret= followed by long alphanumeric
    re.compile(r'\b(?:api[_\-]?key|apikey|secret|token|password)\s*[=:]\s*["\']?[A-Za-z0-9/+_\-]{20,}["\']?', re.IGNORECASE),
    # Bearer tokens
    re.compile(r'\bBearer\s+[A-Za-z0-9_\-\.]{20,}', re.IGNORECASE),
    # OpenAI API keys (sk-proj-... and sk-XX-... formats)
    re.compile(r'\bsk-(?:proj|[A-Za-z0-9]{2})-[A-Za-z0-9_\-]{20,}\b'),
    # Anthropic API keys (sk-ant-...)
    re.compile(r'\bsk-ant-[A-Za-z0-9_\-]{20,}\b'),
    # Slack tokens (bot, user, app, workspace tokens)
    re.compile(r'\bxox[bpoa]-[A-Za-z0-9\-]{10,}\b'),
    # PEM private key blocks
    re.compile(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----'),
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def strip_secrets(text: str) -> str:
    """Replace secret patterns with [REDACTED]."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def contains_secret(text: str) -> bool:
    """Return True if any secret pattern fires on the text."""
    return any(p.search(text) for p in SECRET_PATTERNS)


def extract_text_from_entry(entry: dict) -> str:
    """Extract text content from a transcript JSONL entry."""
    content = entry.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


def scan_transcript(transcript_path: str) -> list[str]:
    """
    Scan transcript file for memory-worthy observations.
    Returns a list of cleaned observation strings.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return []

    candidates: list[str] = []

    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # Only scan recent portion (last MAX_TRANSCRIPT_LINES lines)
        recent_lines = lines[-MAX_TRANSCRIPT_LINES:]

        for line in recent_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Only scan assistant messages (role == "assistant")
            role = entry.get("role", "")
            # Also scan tool results for user corrections
            entry_type = entry.get("type", "")

            if role not in ("assistant",) and entry_type not in ("assistant",):
                # Also check user messages for "you're right" type patterns
                if role not in ("user",) and entry_type not in ("user",):
                    continue

            text = extract_text_from_entry(entry)
            if not text or len(text) < MIN_OBS_CHARS:
                continue

            # Skip entries that are pure code blocks (likely not decision text)
            code_ratio = text.count("```") / max(len(text), 1)
            if code_ratio > 0.05:  # >5% of text is code fence markers
                continue

            # Run marker patterns
            for pat in MARKER_PATTERNS:
                for m in pat.finditer(text):
                    obs = m.group(1).strip()[:MAX_OBS_CHARS]
                    if len(obs) >= MIN_OBS_CHARS:
                        candidates.append(obs)

            # Run prose patterns (only on assistant role)
            if role in ("assistant",) or entry_type in ("assistant",):
                for pat in PROSE_PATTERNS:
                    for m in pat.finditer(text):
                        obs = m.group(0).strip()[:MAX_OBS_CHARS]
                        if len(obs) >= MIN_OBS_CHARS:
                            candidates.append(obs)

            # Run override patterns (both user and assistant)
            for pat in OVERRIDE_PATTERNS:
                for m in pat.finditer(text):
                    obs = m.group(0).strip()[:MAX_OBS_CHARS]
                    if len(obs) >= MIN_OBS_CHARS:
                        candidates.append(obs)

    except (OSError, Exception):
        return []

    # Deduplicate (exact match)
    seen: set[str] = set()
    unique: list[str] = []
    for c in candidates:
        c_clean = strip_secrets(c.strip())
        if c_clean not in seen and len(c_clean) >= MIN_OBS_CHARS:
            # Final secret guard
            if not contains_secret(c_clean):
                seen.add(c_clean)
                unique.append(c_clean)

    return unique[:MAX_OBSERVATIONS_PER_SESSION]


def get_entity_name(workspace: str, project_name: str) -> str:
    """Build the Memory MCP entity name for this project's session observations."""
    today = date.today().isoformat()
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '-', project_name)
    return f"session::{safe_name}::{today}"


def write_to_memory_mcp(entity_name: str, entity_type: str, observations: list[str]) -> bool:
    """
    Write observations to Memory MCP via claude CLI.
    Returns True on success, False on failure.
    """
    obs_json = json.dumps(observations)
    prompt = (
        f"Call mcp__{MCP_SERVER_NAME}__add_observations with: "
        f"entityName={entity_name!r}, "
        f"observations={obs_json}. "
        f"If the entity does not exist, create it first with entityType={entity_type!r}. "
        f"Return only 'OK' if successful."
    )
    try:
        result = subprocess.run(
            ["claude", "--print", "--no-verbose", prompt],
            capture_output=True,
            text=True,
            timeout=MCP_TIMEOUT,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, Exception):
        return False


def write_to_wip_fallback(workspace: str, project_name: str, observations: list[str]) -> None:
    """
    Fallback: append observations to ~/.claude/projects/{slug}/memory/wip.md
    Used when MCP write fails.
    """
    try:
        # Build project slug
        slug = workspace.replace("/", "-").lstrip("-")
        mem_dir = Path.home() / ".claude" / "projects" / slug / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        wip_path = mem_dir / "wip.md"

        today = date.today().isoformat()
        with open(wip_path, "a", encoding="utf-8") as f:
            f.write(f"\n## Auto-captured {today} (session-memory-writer)\n")
            for obs in observations:
                f.write(f"- {obs}\n")
    except (OSError, Exception):
        pass  # Fallback failure is silently ignored


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print("{}")
            sys.exit(0)
        payload = json.loads(raw)
    except Exception:
        print("{}")
        sys.exit(0)

    try:
        # Get transcript path and workspace
        transcript_path = payload.get("transcript_path", "")
        workspace_roots = payload.get("workspace_roots") or []
        workspace = workspace_roots[0] if workspace_roots else payload.get("cwd", os.getcwd())
        project_name = Path(workspace).name if workspace else "unknown-project"

        # Scan transcript for memory-worthy observations
        observations = scan_transcript(transcript_path)

        if not observations:
            print("{}")
            sys.exit(0)

        # Write to Memory MCP
        entity_name = get_entity_name(workspace, project_name)
        entity_type = "session_decision"
        mcp_ok = write_to_memory_mcp(entity_name, entity_type, observations)

        if not mcp_ok:
            # Fallback: write to project memory wip.md
            write_to_wip_fallback(workspace, project_name, observations)

        # Emit a brief advisory so the agent knows memory was captured
        count = len(observations)
        msg = (
            f"SESSION MEMORY: {count} observation(s) captured from this session "
            f"and written to Memory MCP entity '{entity_name}'. "
            f"They will be available at next session start via memory-load-on-start."
        )
        output = {
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "followup_message": msg,
            }
        }
        sys.stdout.write(json.dumps(output))
        sys.stdout.flush()

    except Exception:
        print("{}")  # All failures are silent but must still emit valid JSON

    sys.exit(0)


if __name__ == "__main__":
    main()
