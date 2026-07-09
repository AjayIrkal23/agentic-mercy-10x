#!/usr/bin/env python3
"""dox-write-gate.py — PreToolUse hook on Write|Edit|MultiEdit|Bash.

Enforces the dox CLAUDE.md documentation tree at write time (companion to the
auto-init dox-tree-guard.py). Two tiers:

  Tier 1 (HARD deny): a CODE file is about to be written in a git repo that has NO
          root CLAUDE.md. Blocks until the root is scaffolded. Override: re-issue the
          exact same edit once (records a fingerprint, second attempt passes) — same
          pattern as dangerous-bash-gate.py.
  Tier 2 (soft ASK): root exists, but the target file's directory is "significant"
          (>= threshold code files) and has no local CLAUDE.md. Prompts once per dir
          per session to create one. Never a hard block. Toggle: config.softAskLocalDoc.

ALWAYS ALLOWED (never gated): writes to docs/scaffold — *.md, CLAUDE.md, AGENTS.md,
CODEX.md, and anything under a .claude/ directory. This keeps scaffolding (and the
override itself) always possible, and keeps hooks/skills/rules editable.

Fails OPEN. Exit 0 always. Python 3.8+ stdlib only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR / ".state"
CONFIG_PATH = SCRIPT_DIR / "dox-write-gate.config.json"
ROOT_DOC = "CLAUDE.md"

DEFAULTS = {
    "enabled": True,
    "exemptRepos": [],
    "documentAllDirs": True,
    "autoCreateChildren": True,
    "significantDirThreshold": 3,
    "softAskLocalDoc": True,
    "docFilenames": ["CLAUDE.md", "AGENTS.md", "CODEX.md"],
    "codeExtensions": [
        ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
        ".py", ".go", ".rs", ".java", ".kt",
        ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".swift", ".scala",
    ],
}

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", ".next", "out",
    "coverage", "testdata", ".venv", "venv", "__pycache__", ".claude",
    "target", "bin", "obj", ".turbo", ".cache", "graphify-out", ".planning",
}


# --------------------------------------------------------------------------- #
# Config / state
# --------------------------------------------------------------------------- #
def _config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        if CONFIG_PATH.is_file():
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                cfg.update(user)
    except Exception:
        pass
    return cfg


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _state_path(cid: str) -> Path:
    return STATE_DIR / f"{_safe_cid(cid)}.dox-gate.json"


def _load_state(cid: str) -> dict:
    if not cid:
        return {"overridden": [], "asked_dirs": []}
    p = _state_path(cid)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"overridden": [], "asked_dirs": []}


def _save_state(cid: str, state: dict) -> None:
    if not cid:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state_path(cid).write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Path helpers
# --------------------------------------------------------------------------- #
def _allow() -> int:
    print("{}")
    return 0


def _deny(reason: str) -> int:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


def _ask(reason: str) -> int:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


def _git_root(start: Path) -> "Path | None":
    cur = start if start.is_dir() else start.parent
    for _ in range(30):
        if (cur / ".git").exists():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def _abspath(file_path: str) -> Path:
    p = Path(file_path)
    if p.is_absolute():
        return p
    base = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return (Path(base) / p).resolve()


def _is_doc_or_scaffold(file_path: str, cfg: dict) -> bool:
    fp = file_path.replace("\\", "/")
    if ".claude" in fp.split("/"):          # anything under a .claude/ dir
        return True
    base = os.path.basename(fp)
    if base in set(cfg.get("docFilenames") or DEFAULTS["docFilenames"]):
        return True
    return os.path.splitext(fp)[1].lower() == ".md"


def _is_code_file(file_path: str, cfg: dict) -> bool:
    exts = set(cfg.get("codeExtensions") or DEFAULTS["codeExtensions"])
    return os.path.splitext(file_path)[1].lower() in exts


def _is_exempt(root: Path, cfg: dict) -> bool:
    try:
        rp = root.resolve()
        for ex in cfg.get("exemptRepos") or []:
            try:
                if rp == Path(str(ex)).expanduser().resolve():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _dir_is_significant(d: Path, cfg: dict) -> bool:
    # documentAllDirs -> every directory deserves a local doc (end-to-end coverage).
    if cfg.get("documentAllDirs", True):
        return True
    exts = set(cfg.get("codeExtensions") or DEFAULTS["codeExtensions"])
    threshold = int(cfg.get("significantDirThreshold") or 3)
    try:
        n = sum(
            1 for f in d.iterdir()
            if f.is_file() and f.suffix.lower() in exts
        )
        return n >= threshold
    except OSError:
        return False


def _bash_target(cmd: str, cfg: dict) -> str:
    """Best-effort: detect a code file a shell command writes to (>, >>, tee).

    Conservative — returns "" unless a code-extension path is clearly the write target.
    """
    exts = tuple(cfg.get("codeExtensions") or DEFAULTS["codeExtensions"])
    import re
    # redirections:  > path   >> path   | tee path
    for m in re.finditer(r"(?:>>?|(?:\|\s*tee(?:\s+-a)?))\s+([^\s;&|]+)", cmd):
        cand = m.group(1).strip().strip('"').strip("'")
        if cand.lower().endswith(exts):
            return cand
    return ""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return _allow()

    try:
        cfg = _config()
        if not cfg.get("enabled", True):
            return _allow()

        tool = str(payload.get("tool_name") or payload.get("tool") or "")
        ti = payload.get("tool_input") or {}

        # Resolve the write target.
        if tool in ("Write", "Edit", "MultiEdit", "StrReplace"):
            file_path = (
                ti.get("file_path") or ti.get("path") or ti.get("target_file") or ""
            )
            if isinstance(file_path, list):
                file_path = str(file_path[0]) if file_path else ""
            file_path = str(file_path)
        elif tool in ("Bash", "Shell"):
            file_path = _bash_target(str(ti.get("command") or ""), cfg)
        else:
            return _allow()

        if not file_path:
            return _allow()

        # Doc/scaffold writes are ALWAYS allowed (escape valve).
        if _is_doc_or_scaffold(file_path, cfg):
            return _allow()
        # Only gate real code files.
        if not _is_code_file(file_path, cfg):
            return _allow()

        abs_path = _abspath(file_path)
        root = _git_root(abs_path)
        if root is None or _is_exempt(root, cfg):
            return _allow()  # not a git repo (or exempt) — out of scope

        cid = str(payload.get("conversation_id") or payload.get("session_id") or "")
        state = _load_state(cid)
        root_doc = root / ROOT_DOC

        # ---- Tier 1: hard deny when no root CLAUDE.md exists ----
        if not root_doc.exists():
            fp = f"missing-root::{abs_path}"
            if fp in set(state.get("overridden") or []):
                return _allow()  # override accepted (2nd identical attempt)
            ov = list(state.get("overridden") or [])
            ov.append(fp)
            state["overridden"] = ov
            _save_state(cid, state)
            return _deny(
                f"DOX GATE: no root `CLAUDE.md` in `{root.name}` "
                f"({root}). Code work is blocked until the dox tree's root exists.\n\n"
                "Fix (preferred): invoke the `dox-doc-tree` skill and scaffold the root "
                "(+ the area you're touching). Writing `CLAUDE.md`/`*.md` is always allowed.\n"
                "Override: re-issue this exact edit once to proceed anyway (logged)."
            )

        # ---- Tier 2: soft ask for a missing LOCAL CLAUDE.md ----
        # When children are auto-created (PostToolUse dox-child-scaffold/engine), the
        # local doc appears right after this write — no need to interrupt with an ask.
        if cfg.get("autoCreateChildren", True):
            return _allow()
        if not cfg.get("softAskLocalDoc", True):
            return _allow()
        target_dir = abs_path.parent
        try:
            if target_dir.resolve() == root.resolve():
                return _allow()  # root doc covers the repo root
        except Exception:
            return _allow()

        local_doc = target_dir / ROOT_DOC
        if local_doc.exists():
            return _allow()

        try:
            rel_dir = target_dir.resolve().relative_to(root.resolve()).as_posix()
        except Exception:
            return _allow()

        asked = set(state.get("asked_dirs") or [])
        if rel_dir in asked or not _dir_is_significant(target_dir, cfg):
            return _allow()
        asked.add(rel_dir)
        state["asked_dirs"] = sorted(asked)
        _save_state(cid, state)
        return _ask(
            f"DOX: `{rel_dir}/` has no local `CLAUDE.md` (dox tree). Create/extend one "
            "via the `dox-doc-tree` skill so local rules travel with the code — or approve "
            "to proceed. (Asked once per directory.)"
        )

    except Exception as exc:  # noqa: BLE001
        print(f"[dox-write-gate] Error: {exc}", file=sys.stderr)
        return _allow()


if __name__ == "__main__":
    raise SystemExit(main())
