#!/usr/bin/env python3
"""jCodeMunch enforcement hook — progressive blocking edition.

Two roles, selected by argv[1]:

  prompt-submit   -> UserPromptSubmit. Injects a system-additionalContext reminder
                     that jcodemunch MCP tools must be used for code retrieval to
                     save tokens. Cheap (no MCP probing), runs every turn.

  pre-tool-use    -> PreToolUse. Inspects Read / Grep / Glob calls about to touch
                     a code file and applies progressive enforcement:

                     1. Non-code files (md, json, yaml, …)  → ALLOW silently.
                     2. jcodemunch index absent (strict_mode) → HARD BLOCK (existing).
                     3. Conversation blocks < initial_block_count → DENY (agent adapts).
                     4. Conversation blocks >= initial_block_count → ALLOW with 1-line advisory.

                     State is persisted per conversation in
                     ~/.claude/hooks/.state/{conversation_id}.mcp-enforce.json

Both modes fail OPEN: any unhandled error -> exit 0 with no output.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CODE_EXTS = {
    ".py", ".pyi",
    ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx",
    ".go", ".rs", ".java", ".kt", ".kts", ".scala",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cxx", ".hxx",
    ".rb", ".php", ".swift", ".m", ".mm",
    ".cs", ".fs", ".vb",
    ".lua", ".dart", ".ex", ".exs", ".erl", ".hs",
    ".sh", ".bash", ".zsh",
    ".vue", ".svelte",
}

INDEX_DIR = Path.home() / ".code-index"
ENFORCE_CONFIG_FILE = Path(__file__).parent / "jcodemunch-enforce.config.json"
STATE_DIR = Path(__file__).parent / ".state"

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _load_enforce_config() -> dict:
    """Load the new enforcement config; fall back to safe defaults."""
    defaults = {
        "initial_block_count": 5,
        "exempt_paths": ["~/.claude/", "/tmp/", ".env", "package.json", "go.mod", "go.sum"],
        "exempt_extensions": [
            ".md", ".json", ".yaml", ".yml", ".toml",
            ".env", ".txt", ".lock", ".sum", ".mod",
            ".sql", ".csv",
            ".bak", ".log", ".xml",
        ],
        "small_file_threshold_lines": 50,
        "strict_mode": True,
    }
    try:
        cfg = json.loads(ENFORCE_CONFIG_FILE.read_text(encoding="utf-8"))
        # Merge — explicit keys win, missing keys fall back to defaults.
        return {**defaults, **cfg}
    except Exception:
        return defaults


def _is_strict_mode(cfg: dict) -> bool:
    # The legacy jcodemunch-index-guard.config.json is retired (P3-T3); the
    # enforce config is the single source of the strict_mode toggle now.
    return bool(cfg.get("strict_mode", True))


def _index_building(payload: dict) -> bool:
    """True if index-lifecycle.py is building the active repo's index right now.

    While a MISSING/STALE index self-heals in the background, the read gate is
    relaxed so the agent is never bricked waiting on infrastructure (Spec B
    §3.3). Loaded lazily and only when a block is otherwise imminent, so the
    common (non-blocking) path pays nothing. Fail-open: any error → not building
    → the gate behaves normally.
    """
    try:
        import importlib.util

        p = Path(__file__).resolve().parent / "index-lifecycle.py"
        if not p.is_file():
            return False
        spec = importlib.util.spec_from_file_location("_index_lifecycle_probe", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return bool(mod.is_building(payload))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Index existence check (unchanged from original)
# ---------------------------------------------------------------------------


def _find_git_root(p: Path) -> Path | None:
    cur = p if p.is_dir() else p.parent
    for _ in range(30):
        if (cur / ".git").exists():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def _sanitize(name: str) -> str:
    """Mirror jcodemunch's db-name sanitization: non-alphanumerics → '-', collapsed.

    jcodemunch turns a repo name like "VAIBHAV KATWE" into "VAIBHAV-KATWE" when it
    builds the db filename. The old detector compared against the RAW folder name
    (with the space), so the glob never matched and an indexed repo was reported
    "missing". Sanitize the same way before matching.
    """
    out: list[str] = []
    prev_dash = False
    for ch in name:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")


def _git_remote_identity(root: Path) -> str | None:
    """Reconstruct jcodemunch's git-identity db stem '{owner}-{repo}' from .git/config.

    jcodemunch names a repo's index db after its git REMOTE (owner/repo), NOT the
    local folder — so a project whose folder differs from its remote, or whose
    folder contains characters jcodemunch sanitizes (e.g. a space), was otherwise
    reported as "index missing" even though it is fully indexed. Fail-soft: any
    problem → None.
    """
    try:
        gitdir = root / ".git"
        cfg: Path | None = None
        if gitdir.is_dir():
            cfg = gitdir / "config"
        elif gitdir.is_file():
            # worktree / submodule: '.git' is a pointer file to the real gitdir.
            for line in gitdir.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("gitdir:"):
                    real = Path(line.split(":", 1)[1].strip())
                    if not real.is_absolute():
                        real = (root / real).resolve()
                    cfg = real / "config"
                    break
        if not cfg or not cfg.is_file():
            return None
        url = None
        for line in cfg.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if s.startswith("url") and "=" in s:
                url = s.split("=", 1)[1].strip()
                break
        if not url:
            return None
        u = url[:-4] if url.endswith(".git") else url
        if "://" in u:                       # https://host/owner/repo
            u = u.split("://", 1)[1]
            u = u.split("/", 1)[1] if "/" in u else u
        elif ":" in u:                       # git@host:owner/repo (scp-like ssh)
            u = u.split(":", 1)[1]
        segs = [p for p in u.split("/") if p]
        if len(segs) < 2:
            return None
        owner, repo = segs[-2], segs[-1]
        return f"{_sanitize(owner)}-{_sanitize(repo)}"
    except Exception:
        return None


def _check_index_exists(target_path: str) -> bool:
    try:
        root = _find_git_root(Path(target_path))
        if root is None:
            return True
        # An index for this repo may be stored under EITHER identity mode:
        #   • git identity (jcodemunch's DEFAULT when a git remote exists):
        #       {owner}-{repo}.db  (e.g. AjayIrkal23-VAIBHAV-KATWE.db)
        #   • local identity (path-keyed):  local-{name}-{sha1(path)[:8]}.db
        #   • bare name fallback:            {repo}.db
        # Names are matched with jcodemunch's sanitization (space→'-', etc.) AND
        # the git-remote identity is reconstructed from .git/config — because the
        # db is named after the REMOTE, not the local folder. Without this, a repo
        # whose folder name has a space (or differs from its remote) was falsely
        # reported "index missing" and every source read was hard-blocked.
        h = hashlib.sha1(str(root).encode()).hexdigest()[:8]
        name = root.name
        sname = _sanitize(name)
        for cand in (
            f"local-{name}-{h}.db", f"local-{sname}-{h}.db",
            f"{name}.db", f"{sname}.db",
        ):
            if (INDEX_DIR / cand).is_file():
                return True
        # git-remote identity ({owner}-{repo}.db) — jcodemunch's DEFAULT naming.
        ident = _git_remote_identity(root)
        if ident and (INDEX_DIR / f"{ident}.db").is_file():
            return True
        # any-owner glob fallback ("*-{repo}.db"), sanitized then raw.
        for pat in (f"*-{sname}.db", f"*-{name}.db"):
            if any(INDEX_DIR.glob(pat)):
                return True
        return False
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Conversation state helpers
# ---------------------------------------------------------------------------


def _state_path(conversation_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in conversation_id)
    return STATE_DIR / f"{safe}.mcp-enforce.json"


def _load_state(conversation_id: str) -> dict:
    """Load per-conversation enforcement state; reset to defaults on corruption."""
    defaults: dict = {
        "jcodemunch_calls": 0,
        "read_blocked_count": 0,
        "read_allowed_count": 0,
    }
    if not conversation_id:
        return defaults
    try:
        path = _state_path(conversation_id)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            # Basic type-safety: all counts must be non-negative ints.
            for key in ("jcodemunch_calls", "read_blocked_count", "read_allowed_count"):
                if not isinstance(data.get(key), int) or data[key] < 0:
                    return defaults
            return data
    except Exception:
        pass
    return defaults


def _save_state(conversation_id: str, state: dict) -> None:
    if not conversation_id:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state_path(conversation_id).write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _fullstack_state_path(conversation_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in conversation_id)
    return Path(__file__).resolve().parent / ".state" / f"{safe}.fullstack.json"


def _coding_started(conversation_id: str) -> bool:
    """True once the agent has touched FE/BE paths (Agent coding phase)."""
    if not conversation_id:
        return False
    try:
        p = _fullstack_state_path(conversation_id)
        if not p.is_file():
            return False
        data = json.loads(p.read_text(encoding="utf-8"))
        return bool(
            data.get("frontend_touched")
            or data.get("backend_touched")
            or data.get("frontend_start_sent")
            or data.get("backend_start_sent")
            or data.get("fullstack_start_sent")
        )
    except Exception:
        return False


def _is_plan_or_ask(payload: dict) -> bool:
    mode = str(payload.get("session_type") or payload.get("mode") or "").lower()
    if mode in ("plan", "ask", "planning"):
        return True
    roots = payload.get("workspace_roots") or []
    if isinstance(roots, list) and roots:
        try:
            for marker in (Path(r) / ".claude" / "plan-mode-active" for r in roots if r):
                if marker.is_file():
                    return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Payload I/O helpers
# ---------------------------------------------------------------------------


def _read_payload() -> dict:
    raw = sys.stdin.read() or "{}"
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _emit_additional_context(event: str, text: str) -> None:
    out = {
        "additionalContext": text,
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()


def _emit_block(message: str) -> None:
    out = {
        "permissionDecision": "deny",
        "permissionDecisionReason": message,
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Prompt-submit role (unchanged semantics, tightened wording)
# ---------------------------------------------------------------------------

REMINDER = (
    "jCodeMunch MCP is INSTALLED and MANDATORY-FIRST for ALL code work — discovery "
    "AND reading code. Before any Read/Grep/Glob OR lean-ctx ctx_read/ctx_search on "
    "SOURCE files, use jcodemunch (~95% fewer tokens, no missed cross-module edges):\n"
    "  • Locate  → search_symbols / search_ast / search_text\n"
    "  • Read    → get_symbol_source / get_file_outline / assemble_task_context / get_context_bundle\n"
    "  • Impact  → find_references / find_importers / get_blast_radius / get_call_hierarchy\n"
    "  • Audit   → find_dead_code / get_coupling_metrics / get_hotspots / get_file_risk\n"
    "  • Plan    → plan_turn (plan the whole change before editing)\n"
    "jcodemunch reads its own finds too — don't re-read a source file through "
    "ctx_read once jcodemunch already returned it. lean-ctx is for NON-code "
    "(md/configs/env/lockfiles), shell, and dir trees only. State a reason if you "
    "must fall back."
)

# ---------------------------------------------------------------------------
# Prompt-submit state helpers (once-per-conversation guard)
# ---------------------------------------------------------------------------


def _prompt_state_path(conversation_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in conversation_id)
    return STATE_DIR / f"{safe}.jcodemunch-prompt-sent.json"


def _prompt_already_sent(conversation_id: str) -> bool:
    if not conversation_id:
        return False
    try:
        p = _prompt_state_path(conversation_id)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return bool(data.get("sent"))
    except Exception:
        pass
    return False


def _mark_prompt_sent(conversation_id: str) -> None:
    if not conversation_id:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _prompt_state_path(conversation_id).write_text(
            json.dumps({"sent": True}), encoding="utf-8"
        )
    except Exception:
        pass


def prompt_submit() -> int:
    payload = _read_payload()
    conversation_id = payload.get("conversation_id") or payload.get("session_id") or ""
    if _prompt_already_sent(conversation_id):
        return 0
    _emit_additional_context("UserPromptSubmit", REMINDER)
    _mark_prompt_sent(conversation_id)
    return 0


# ---------------------------------------------------------------------------
# Pre-tool-use role — progressive enforcement
# ---------------------------------------------------------------------------


def _is_exempt(target: str, cfg: dict) -> bool:
    """Return True if this target should be silently allowed (non-code)."""
    suffix = Path(target).suffix.lower() if target else ""

    # Exempt by extension.
    exempt_exts = {e.lower() for e in cfg.get("exempt_extensions", [])}
    if suffix in exempt_exts:
        return True

    # Exempt by path prefix / substring.
    home = str(Path.home())
    for raw_path in cfg.get("exempt_paths", []):
        resolved = raw_path.replace("~", home)
        if target.startswith(resolved) or resolved in target:
            return True

    # No code extension AND no known code path segment → treat as non-code.
    if suffix not in CODE_EXTS:
        code_segments = ("/src/", "/lib/", "/pkg/", "/internal/", "/app/", "/server/", "/client/", "/cmd/")
        if not any(seg in target for seg in code_segments):
            return True

    return False


def pre_tool_use() -> int:
    payload = _read_payload()
    tool = payload.get("tool_name") or payload.get("tool") or ""
    inp = payload.get("tool_input") or payload.get("input") or {}
    conversation_id = payload.get("conversation_id") or payload.get("session_id") or ""

    cfg = _load_enforce_config()
    gate_lean_ctx = bool(cfg.get("gate_lean_ctx", True))

    # Extract target path. Covers native Read/Grep/Glob AND lean-ctx ctx_* reads
    # so a blind source read can't silently route around jcodemunch.
    target = ""
    if tool == "Read":
        target = str(inp.get("file_path") or "")
    elif tool == "Grep":
        target = str(inp.get("path") or inp.get("glob") or "")
    elif tool == "Glob":
        target = str(inp.get("pattern") or "")
    elif tool in (
        "mcp__lean-ctx__ctx_read",
        "mcp__lean-ctx__ctx_search",
        "mcp__lean-ctx__ctx_multi_read",
    ):
        if not gate_lean_ctx:
            return 0
        if tool == "mcp__lean-ctx__ctx_multi_read":
            paths = inp.get("paths") or inp.get("files") or []
            target = str(paths[0]) if isinstance(paths, list) and paths else ""
        else:
            target = str(
                inp.get("path") or inp.get("file_path") or inp.get("pattern") or ""
            )
    else:
        return 0

    # --- Gate 1: Non-code / exempt → allow silently. ---
    if _is_exempt(target, cfg):
        return 0

    # --- Gate 2: Index absent in strict_mode → nudge, but NEVER brick. ---
    if not _check_index_exists(target) and _is_strict_mode(cfg):
        # …unless index-lifecycle is already building it in the background —
        # then allow the read (never brick the agent on self-healing infra).
        if _index_building(payload):
            return 0
        # Untrackable context (e.g. a subagent whose payload carries no session
        # id, and which may not even hold a jcodemunch tool to satisfy the block)
        # → fail OPEN immediately. A read must never be permanently deadlocked.
        if not conversation_id:
            return 0
        # Budgeted nudge: block a couple of times, then fail OPEN. This matches
        # the module contract ("you are never stuck"); previously Gate 2 had no
        # budget and could brick a subagent with no jcodemunch tool forever.
        st = _load_state(conversation_id)
        idx_budget = int(cfg.get("index_missing_block_budget", 2))
        idx_blocks = int(st.get("index_block_count", 0))
        if idx_blocks >= idx_budget:
            _emit_additional_context(
                "PreToolUse",
                "Advisory: jcodemunch index appears absent — index the repo for "
                "cheaper reads, but this read is allowed.",
            )
            return 0
        st["index_block_count"] = idx_blocks + 1
        _save_state(conversation_id, st)
        root = _find_git_root(Path(target))
        root_str = str(root) if root else "unknown"
        remaining = idx_budget - idx_blocks - 1
        tail = (
            f"({remaining} more block{'s' if remaining != 1 else ''}, then reads allowed)"
            if remaining > 0 else "(last block — subsequent reads allowed)"
        )
        block_msg = (
            f"BLOCKED: jcodemunch index missing for `{root_str}`. "
            f"Run mcp__jcodemunch__index_folder({{\"path\": \"{root_str}\"}}) first, "
            f"then retry {tool}. {tail}"
        )
        _emit_block(block_msg)
        return 0

    # --- Gate 3: Progressive count-based enforcement (coding phase only). ---
    state = _load_state(conversation_id)

    if state.get("jcodemunch_calls", 0) > 0:
        return 0

    if _is_plan_or_ask(payload):
        return 0

    enforce_after_write = bool(cfg.get("enforce_after_code_write", True))
    if enforce_after_write and not _coding_started(conversation_id):
        return 0

    initial_block_count = int(cfg.get("initial_block_count", 0))
    if initial_block_count <= 0 and enforce_after_write and _coding_started(conversation_id):
        initial_block_count = 2

    blocks_so_far = state.get("read_blocked_count", 0)

    if blocks_so_far < initial_block_count:
        # Relaxed while the index self-heals in the background (Spec B §3.3).
        if _index_building(payload):
            return 0
        # Still within the blocking budget — BLOCK this call.
        remaining_after = initial_block_count - blocks_so_far - 1
        state["read_blocked_count"] = blocks_so_far + 1
        _save_state(conversation_id, state)

        # Short, punchy block message.
        hint = Path(target).name if target else "this file"
        if remaining_after > 0:
            suffix_note = f"({remaining_after} more block{'s' if remaining_after != 1 else ''} remaining)"
        else:
            suffix_note = "(last block — subsequent Reads allowed with advisory)"
        block_msg = (
            f"BLOCKED: Use mcp__jcodemunch__search_symbols or get_symbol_source for '{hint}' first. "
            f"jcodemunch returns the same code with ~95% fewer tokens. "
            f"Call the MCP tool, then retry this Read only if jcodemunch returns nothing. "
            f"{suffix_note}"
        )
        _emit_block(block_msg)
        return 0

    # Budget exhausted — ALLOW with a single-line advisory.
    state["read_allowed_count"] = state.get("read_allowed_count", 0) + 1
    _save_state(conversation_id, state)

    _emit_additional_context(
        "PreToolUse",
        "Advisory: prefer jcodemunch for code retrieval (~95% fewer tokens).",
    )
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


_DEADCODE_TOOLS = (
    "find_dead_code", "get_dead_code_v2", "find_unused_paths",
    "get_blast_radius", "get_dependency_cycles",
)


def mcp_used() -> int:
    """afterMCPExecution: increment jcodemunch_calls; record dead-code audit signal."""
    payload = _read_payload()
    conversation_id = payload.get("conversation_id") or payload.get("session_id") or ""
    if not conversation_id:
        return 0
    state = _load_state(conversation_id)
    state["jcodemunch_calls"] = state.get("jcodemunch_calls", 0) + 1
    _save_state(conversation_id, state)

    # Satisfy the completion gate's dead-code check (Gate 5) when a dead-code /
    # blast-radius tool runs — the canonical "I audited my changes" signal.
    tool = str(payload.get("tool_name") or payload.get("tool") or "")
    if any(t in tool for t in _DEADCODE_TOOLS):
        try:
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in conversation_id)
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            (STATE_DIR / f"{safe}.deadcode.json").write_text(
                json.dumps({"fired": True}), encoding="utf-8"
            )
        except Exception:
            pass
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "prompt-submit"
    try:
        if mode == "prompt-submit":
            return prompt_submit()
        if mode == "pre-tool-use":
            return pre_tool_use()
        if mode == "mcp-used":
            return mcp_used()
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
