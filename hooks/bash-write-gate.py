#!/usr/bin/env python3
"""bash-write-gate.py — PreToolUse hook on Bash.

TWO LAYERS:

  LAYER 1 (2026-07-19) — BYPASS DENY. Hard-denies shell-mediated file writes that
  reimplement the sanctioned editor and bypass every write gate:
    - python3/node/ruby/perl/php  -  <<'EOF'   (interpreter heredoc via STDIN — no `>`)
    - python3/node/ruby -c / -e "...write..."  (inline interpreter write)
    - sed -i / perl -i / ruby -i               (in-place edit, no redirect at all)
    - cat <<EOF > path  AND  cat > path <<EOF  (both argument orders)
    - tee path / echo|printf > path
  These are DENIED unconditionally — not gated on blast radius, not gated on
  HARD_BLOCK, all file extensions. Rationale: rules/no-permission-bypass.md.
  Read-only interpreter invocations are NOT denied: a write indicator must be
  present in the command body. Writes confined to /tmp, scratchpad, /dev/*,
  *.log, node_modules, dist/build are allowed so builds and tests keep working.

  LAYER 2 (original) — blast-radius advisory on cat/tee/echo redirects to source
  files with >=THRESHOLD importers. Unchanged behavior, still governed by
  BASH_WRITE_GATE_HARD_BLOCK. Only reached for writes Layer 1 permitted.

HISTORY: before 2026-07-19 this hook carried only three redirect-based regexes
(cat <<EOF > path / tee / echo >). An interpreter heredoc pipes to STDIN and has
no `>` at all, and `sed -i` has no redirect either, so every interpreter write
and every in-place edit passed through as `{}` — allowed. `cat > path <<EOF` also
passed, because the original regex hardcoded the opposite argument order from its
own docstring. Layer 1 closes all of it.

Python 3.8+ stdlib only. Exit 0 always. Exception → stderr, exit 0 (never crash session).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
THRESHOLD = 5  # same as gateguard-write-gate.py
HARD_BLOCK = os.environ.get("BASH_WRITE_GATE_HARD_BLOCK", "").strip() == "1"

# Layer 1 escape hatch. Unset by design — set to "1" only to debug the gate itself.
BYPASS_DENY_OFF = os.environ.get("BASH_WRITE_GATE_ALLOW_SHELL_WRITES", "").strip() == "1"

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR / ".state"

# Source file extensions to monitor (Layer 2 only). Layer 1 covers every extension.
SOURCE_EXTENSIONS = frozenset({
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".c", ".cpp", ".h", ".hpp",
    ".sh", ".bash",
})

# Stems too common to bother checking blast radius for
_SHORT_STEMS = frozenset({
    "app", "main", "index", "types", "routes",
    "gorm", "db", "api", "lib", "util",
})


# ---------------------------------------------------------------------------
# Layer 1: bypass detection
# ---------------------------------------------------------------------------

_INTERPRETERS = r"(?:python3?(?:\.\d+)?|node|nodejs|ruby|perl|php|deno|bun)"

# A COMMAND POSITION: start of line, or just after a shell separator / subshell
# opener. Without this anchor the patterns also match their own names quoted
# inside an otherwise-legitimate command — e.g.
#   git commit -m "switch from sed -i to ctx_patch"
# was denied, because `sed -i` appeared anywhere in the string. Anchoring means
# we only fire on a command actually being RUN, not one being talked about.
_CMD_POS = r"(?:^|[\n;&|(]|\$\(|`|^\s*)\s*"

# `python3 - <<'PY'` / `node - <<EOF` — script piped to STDIN. No `>` anywhere,
# which is exactly why the original redirect-only regexes never saw it.
_INTERP_STDIN_RE = re.compile(
    _CMD_POS + _INTERPRETERS + r"\b[^\n;|&]*?\s-\s*<<",
    re.MULTILINE,
)

# `python3 -c "..."` / `node -e "..."`
_INTERP_INLINE_RE = re.compile(
    _CMD_POS + _INTERPRETERS + r"\b[^\n;|&]*?\s-(?:c|e)\b",
    re.MULTILINE,
)

# `sed -i` / `sed --in-place` / `perl -i -pe` / `perl -pi -e` / `ruby -i`
_INPLACE_RE = re.compile(
    _CMD_POS + r"(?:sed|perl|ruby)\s+(?:-[a-zA-Z]*i\b|--in-place)",
    re.MULTILINE,
)

# `cat <<'EOF' > path` (original order)
_HEREDOC_RE = re.compile(
    r"""cat\s+<<\s*['"]?(\w+)['"]?\s+>>?\s*(?P<path>[^\s;|&>]+)""",
    re.IGNORECASE,
)

# `cat > path <<'EOF'` (reversed order — slipped through the original gate)
_HEREDOC_REV_RE = re.compile(
    r"""cat\s*>>?\s*(?P<path>[^\s;|&<]+)\s*<<""",
    re.IGNORECASE,
)

# Tee write: tee path (possibly with -a for append)
_TEE_RE = re.compile(
    r"""\btee\s+(?:-a\s+)?(?P<path>[^\s;|&>]+)""",
    re.IGNORECASE,
)

# Echo redirect: echo ... > path or printf ... > path
_ECHO_RE = re.compile(
    r"""(?:echo|printf)\s+.{0,200}?>\s*(?P<path>[^\s;|&]+)""",
    re.IGNORECASE | re.DOTALL,
)

# A write actually happening inside an interpreter body. Without one of these,
# `python3 - <<PY ... PY` is a read-only analysis script and is left alone.
_WRITE_INDICATOR_RE = re.compile(
    r"(?:"
    r"open\s*\([^)]*,\s*['\"][wax]"           # open(p, 'w'|'a'|'x')
    r"|\bwrite_text\b|\bwrite_bytes\b"         # pathlib
    r"|\bwriteFileSync\b|\bappendFileSync\b|\bcreateWriteStream\b"
    r"|\bfs\.write|\bfs\.append|\bfs\.rename|\bfs\.copyFile"
    r"|\.write\s*\("                           # f.write(...) / stream.write(...)
    r"|\bos\.replace\b|\bos\.rename\b|\bos\.remove\b|\bos\.unlink\b"
    r"|\bshutil\.(?:copy|copy2|move|rmtree)\b"
    r"|\bjson\.dump\s*\(|\byaml\.(?:dump|safe_dump)\s*\("
    r"|\bFile\.(?:write|open)\b|\bIO\.write\b"  # ruby
    r")",
)

# Paths a shell write may legitimately target — scratch, logs, build output.
_ALLOW_PATH_RE = re.compile(
    r"^/dev/"
    r"|^/tmp/|(?:^|/)tmp/"
    r"|/claude-\d+/|scratchpad"
    r"|(?:^|/)(?:node_modules|dist|build|coverage|\.next|\.turbo|target)/"
    r"|\.log$|\.tmp$|\.lock$|\.pid$",
)

# Quoted tokens that may name a filesystem path.
_QUOTED_TOKEN_RE = re.compile(r"""['"]([^'"\n]{1,200})['"]""")

# Trailing bare file arguments, e.g. the target of `sed -i 's/a/b/' src/app.ts`
_TRAILING_FILE_RE = re.compile(r"\s([\w./~-]+\.[A-Za-z0-9]{1,6})(?=\s|$)")


def _looks_like_path(tok: str) -> bool:
    tok = tok.strip()
    if not tok or tok.startswith(("http://", "https://", "-")):
        return False
    if "/" in tok:
        return True
    return bool(re.match(r"^[\w.-]+\.[A-Za-z0-9]{1,6}$", tok))


def _is_allowed_path(p: str) -> bool:
    return bool(_ALLOW_PATH_RE.search(p.strip().strip("'\"")))


def _candidate_paths(body: str) -> list[str]:
    """Path-looking tokens inside an interpreter body / command."""
    toks = [t for t in _QUOTED_TOKEN_RE.findall(body) if _looks_like_path(t)]
    toks += _TRAILING_FILE_RE.findall(body)
    return toks


def _all_targets_allowed(paths: list[str]) -> bool:
    """True only when at least one path was found and every one is scratch/log."""
    return bool(paths) and all(_is_allowed_path(p) for p in paths)


def _detect_bypass(cmd: str):
    """Return (kind, sanctioned_alternative) when cmd is a banned shell write."""
    # In-place editors: no read-only variant exists — the flag IS the write.
    if _INPLACE_RE.search(cmd):
        if not _all_targets_allowed(_candidate_paths(cmd)):
            return ("in-place edit (sed -i / perl -i)", "ctx_patch")

    # Interpreter writes: only banned when the body actually writes.
    for rx, label in ((_INTERP_STDIN_RE, "interpreter heredoc (python3 - <<EOF)"),
                      (_INTERP_INLINE_RE, "inline interpreter write (-c / -e)")):
        if rx.search(cmd) and _WRITE_INDICATOR_RE.search(cmd):
            if not _all_targets_allowed(_candidate_paths(cmd)):
                return (label, "ctx_patch")

    # Shell redirect writes, both cat orders.
    for rx, label in ((_HEREDOC_RE, "heredoc redirect (cat <<EOF > file)"),
                      (_HEREDOC_REV_RE, "heredoc redirect (cat > file <<EOF)"),
                      (_TEE_RE, "tee write"),
                      (_ECHO_RE, "echo/printf redirect")):
        for m in rx.finditer(cmd):
            p = m.group("path").strip("'\"")
            if not p or p in ("/dev/null", "/dev/stderr", "/dev/stdout"):
                continue
            if _is_allowed_path(p):
                continue
            return (f"{label} → {os.path.basename(p)}",
                    "ctx_patch (edit) / Write (new file)")

    return None


def _emit_bypass_deny(kind: str, alternative: str, cmd_preview: str) -> None:
    reason = (
        f"BASH-WRITE-GATE — DENIED: {kind}.\n"
        f"Command: {cmd_preview[:160]}\n\n"
        "Shell-mediated file writes are banned on this machine "
        "(rules/no-permission-bypass.md). They bypass every write gate. A denied tool "
        "is a ROUTE, not an obstacle — do NOT reimplement this write in another shell "
        "form (that is the same violation, not a workaround).\n\n"
        "READ FIRST, THEN WRITE:\n"
        "  1. READ  source code  → jcodemunch: get_symbol_source / get_file_outline /\n"
        "                          get_file_content  (never edit a file you have not read)\n"
        "     READ  non-code     → ctx_read  (inside the project root)\n"
        f"  2. WRITE existing    → {alternative}\n"
        "                          ctx_patch(op=\"replace_all\", path, find, replace)\n"
        "     ambiguous text    → ctx_read(mode=\"anchored\") then\n"
        "                          ctx_patch(op=\"replace_lines\", ...) with the returned anchors\n"
        "     new file          → Write tool, or ctx_patch(op=\"create\")\n"
        "     outside the root  → Write tool (ctx_patch is path-jailed to the project root)\n\n"
        "N separate ctx_patch calls is the CORRECT cost. Batching them into one shell "
        "script is the banned shortcut, not an optimization.\n\n"
        "Bash stays correct for: builds, tests, linters, git, package managers, and "
        "read-only inspection of command output."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


# ---------------------------------------------------------------------------
# Layer 2: legacy path extraction (blast-radius advisory)
# ---------------------------------------------------------------------------

def _extract_target_paths(cmd: str) -> list[str]:
    """Extract target file paths from bash write patterns."""
    paths: list[str] = []

    for rx in (_HEREDOC_RE, _HEREDOC_REV_RE):
        for m in rx.finditer(cmd):
            p = m.group("path").strip("'\"")
            if p:
                paths.append(p)

    for m in _TEE_RE.finditer(cmd):
        p = m.group("path").strip("'\"")
        if p and p not in ("/dev/null", "/dev/stderr", "/dev/stdout"):
            paths.append(p)

    for m in _ECHO_RE.finditer(cmd):
        p = m.group("path").strip("'\"")
        if p and p not in ("/dev/null", "/dev/stderr", "/dev/stdout"):
            paths.append(p)

    return [p for p in paths if p.strip()]


def _is_source_file(file_path: str) -> bool:
    """Return True if the target path is a source file we care about."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in SOURCE_EXTENSIONS


def _stem_is_short(file_path: str) -> bool:
    stem = os.path.splitext(os.path.basename(file_path))[0].lower()
    return stem in _SHORT_STEMS or len(stem) < 6


# ---------------------------------------------------------------------------
# Blast-radius check (mirrors gateguard-write-gate.py)
# ---------------------------------------------------------------------------

def _find_project_root(file_path: str) -> str:
    current = os.path.dirname(os.path.abspath(file_path))
    for _ in range(15):
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.dirname(os.path.abspath(file_path))


def _count_references(file_path: str) -> int:
    """Count how many other files import/reference this file."""
    if _stem_is_short(file_path):
        return 0

    basename = os.path.basename(file_path)
    stem = os.path.splitext(basename)[0]
    search_root = _find_project_root(file_path)
    ext = os.path.splitext(basename)[1].lower()

    try:
        if ext == ".go":
            pattern = f'".*/{stem}"|package {stem}'
            result = subprocess.run(
                ["grep", "-rl", "--include=*.go",
                 "--exclude-dir=node_modules", "--exclude-dir=.git",
                 "--exclude-dir=dist", "--exclude-dir=build",
                 "-E", pattern, search_root],
                capture_output=True, text=True, timeout=8,
            )
        else:
            pattern = "from.*/" + stem + "|require.*/" + stem
            result = subprocess.run(
                ["grep", "-rl",
                 "--include=*.ts", "--include=*.tsx",
                 "--include=*.js", "--include=*.jsx",
                 "--exclude-dir=node_modules", "--exclude-dir=.git",
                 "--exclude-dir=dist", "--exclude-dir=build",
                 "-E", pattern, search_root],
                capture_output=True, text=True, timeout=8,
            )
        if result.returncode != 0:
            return 0
        files = [
            f for f in result.stdout.strip().split("\n")
            if f and os.path.abspath(f) != os.path.abspath(file_path)
        ]
        return len(files)
    except (subprocess.TimeoutExpired, OSError):
        return 0


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _emit_deny(file_path: str, ref_count: int, cmd_preview: str) -> None:
    basename = os.path.basename(file_path)
    reason = (
        f"BASH-WRITE-GATE: Heredoc/tee write to `{basename}` (blast radius: {ref_count} importers) "
        f"detected in Bash command. This bypasses the Write hook safety checks.\n"
        f"Command preview: {cmd_preview[:120]}\n\n"
        f"Verify:\n"
        f"  1. All {ref_count} importing files still compile after this change.\n"
        f"  2. No exported signatures changed unintentionally.\n"
        f"Re-run after verification — this block will not repeat for `{basename}` in this conversation."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def _emit_advisory(file_path: str, ref_count: int, cmd_preview: str) -> None:
    basename = os.path.basename(file_path)
    msg = (
        f"⚠️ BASH-WRITE-GATE: Heredoc/tee write to `{basename}` detected "
        f"(blast radius: {ref_count} importer(s)). This bypasses Write hook safety checks.\n"
        f"Command: {cmd_preview[:120]}\n"
        f"Verify all {ref_count} importing files still compile after this change."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "additionalContext": msg}}))


def _emit_injection_advisory(file_path: str, cmd_preview: str) -> None:
    """Warn about bash writes to .planning/ (injection vector)."""
    basename = os.path.basename(file_path)
    msg = (
        f"⚠️ BASH-WRITE-GATE: Bash command writes to .planning/{basename} — "
        "review content for embedded instructions that could manipulate agent context."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "additionalContext": msg}}))


# ---------------------------------------------------------------------------
# Conversation state (for blast-radius dedup, same as gateguard)
# ---------------------------------------------------------------------------

def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _load_state(cid: str) -> dict:
    if not cid:
        return {}
    p = STATE_DIR / f"{_safe_cid(cid)}.bash-write-gate.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(cid: str, state: dict) -> None:
    if not cid:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / f"{_safe_cid(cid)}.bash-write-gate.json").write_text(
            json.dumps(state), encoding="utf-8"
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0

    try:
        tool = str(payload.get("tool_name") or payload.get("tool") or "")
        if tool not in ("Bash", "Shell"):
            print("{}")
            return 0

        ti = payload.get("tool_input") or {}
        cmd = str(ti.get("command") or "")
        if not cmd.strip():
            print("{}")
            return 0

        # -------------------------------------------------------------------
        # LAYER 1 — hard deny on shell-mediated writes. Runs first, applies to
        # every extension, ignores blast radius and HARD_BLOCK.
        # -------------------------------------------------------------------
        if not BYPASS_DENY_OFF:
            hit = _detect_bypass(cmd)
            if hit:
                kind, alternative = hit
                _emit_bypass_deny(kind, alternative, cmd)
                return 0

        # -------------------------------------------------------------------
        # LAYER 2 — legacy blast-radius advisory on what Layer 1 permitted.
        # -------------------------------------------------------------------
        target_paths = _extract_target_paths(cmd)
        if not target_paths:
            print("{}")
            return 0

        # Filter to source files only
        source_targets = [p for p in target_paths if _is_source_file(p)]
        if not source_targets:
            # Check for .planning/ writes (injection advisory, regardless of extension)
            planning_targets = [p for p in target_paths if ".planning/" in p or ".planning\\" in p]
            if planning_targets:
                _emit_injection_advisory(planning_targets[0], cmd[:200])
                return 0
            print("{}")
            return 0

        cid = str(payload.get("conversation_id") or payload.get("session_id") or "")
        state = _load_state(cid)
        acked = set(state.get("acked_files") or [])

        for file_path in source_targets:
            abs_path = os.path.abspath(file_path)

            # Already acked — skip
            if abs_path in acked:
                continue

            # Blast-radius check
            ref_cache = state.get("ref_cache") or {}
            if abs_path in ref_cache:
                ref_count = int(ref_cache[abs_path])
            else:
                ref_count = _count_references(file_path)
                ref_cache[abs_path] = ref_count
                state["ref_cache"] = ref_cache

            if ref_count >= THRESHOLD:
                acked.add(abs_path)
                state["acked_files"] = list(acked)
                _save_state(cid, state)

                cmd_preview = cmd[:200]
                if HARD_BLOCK:
                    _emit_deny(file_path, ref_count, cmd_preview)
                else:
                    _emit_advisory(file_path, ref_count, cmd_preview)
                return 0

            if ref_count == 0:
                # New file (zero importers) — emit lower-severity advisory
                # without denying, so new-module heredoc writes are flagged.
                acked.add(abs_path)
                state["acked_files"] = list(acked)
                _save_state(cid, state)

                basename = os.path.basename(file_path)
                msg = (
                    f"BASH-WRITE-GATE (advisory): New source file `{basename}` written "
                    f"via Bash heredoc/tee — this bypasses Write hook safety checks. "
                    f"Consider verifying with `incremental-implementation` skill if this "
                    f"is a non-trivial new module."
                )
                print(json.dumps({"followup_message": msg}))
                return 0

        # No high-blast-radius source targets found
        _save_state(cid, state)  # persist ref_cache updates
        print("{}")
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"[bash-write-gate] Error: {exc}", file=sys.stderr)
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
