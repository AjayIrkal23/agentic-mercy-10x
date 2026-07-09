#!/usr/bin/env python3
"""PostToolUse(Write|Edit|MultiEdit): auto-create per-folder dox docs.

The dox doctrine requires a `CLAUDE.md` + `AGENTS.md` in every directory, but the
ROOT was the only thing auto-stubbed — child docs depended on the agent voluntarily
running the dox-doc-tree skill, so they were rarely created.

This hook closes that gap ADDITIVELY: when ANY file (default: any directory; with
`documentAllDirs=false`, only code files in significant dirs) is written into a
dox-active repo (root `CLAUDE.md` present), it documents that file's directory via
`dox_engine.ensure_dir_documented` — creating a stub `CLAUDE.md` (`<!-- dox:child v1 -->`)
+ an `AGENTS.md` pointer and RE-SYNCING the root index — then nudges the agent to
flesh them out (Phase 7).

Delegates all filesystem logic to dox_engine (shared with the session sweep + CLI),
so "what counts as a documentable dir" and "how the root index is synced" stay in one
place. Idempotent (never overwrites an existing doc), throttled once per dir per
session, fails OPEN on any error.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR / ".state"
CONFIG = SCRIPT_DIR / "dox-tree-guard.config.json"

sys.path.insert(0, str(SCRIPT_DIR))
try:
    import dox_engine  # type: ignore
except Exception:  # pragma: no cover — engine missing -> fail open
    dox_engine = None  # type: ignore

SKIP_SEGMENTS = (
    "/.claude/", "/node_modules/", "/.git/", "/dist/", "/build/",
    "/__pycache__/", "/vendor/", "/.next/", "/target/", "/.venv/",
    "/graphify-out/", "/.code-index/", "/.planning/",
)


def _safe(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _load_state(cid: str) -> dict:
    p = STATE_DIR / f"{_safe(cid)}.dox-scaffold.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except Exception:
        return {}


def _save_state(cid: str, data: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / f"{_safe(cid)}.dox-scaffold.json").write_text(
            json.dumps(data), encoding="utf-8"
        )
    except Exception:
        pass


def _git_root(start: Path) -> "Path | None":
    cur = start if start.is_dir() else start.parent
    for _ in range(30):
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        print("{}")
        return 0

    if dox_engine is None:
        print("{}")
        return 0

    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        print("{}")
        return 0

    fp = (payload.get("tool_input") or {}).get("file_path") or ""
    if not fp:
        print("{}")
        return 0

    norm = fp.replace("\\", "/")
    if any(seg in norm for seg in SKIP_SEGMENTS):
        print("{}")
        return 0

    cfg = dox_engine.load_cfg(CONFIG)
    if cfg.get("enabled") is False:
        print("{}")
        return 0

    document_all = bool(cfg.get("documentAllDirs", True))
    exts = dox_engine._exts(cfg)
    # When NOT documenting all dirs, only react to code-file writes (legacy mode).
    if not document_all and os.path.splitext(norm)[1].lower() not in exts:
        print("{}")
        return 0

    file_path = Path(norm)
    d = file_path.parent
    root = _git_root(file_path)
    if root is None:
        print("{}")
        return 0

    # Only act in a dox-active repo (root CLAUDE.md present); else the root gate owns it.
    if not (root / "CLAUDE.md").is_file():
        print("{}")
        return 0

    # The repo root itself is covered by the root CLAUDE.md — no child needed there.
    try:
        if d.resolve() == root.resolve():
            print("{}")
            return 0
    except Exception:
        print("{}")
        return 0

    try:
        rel = str(d.resolve().relative_to(root.resolve()))
    except Exception:
        rel = d.name

    if (d / "CLAUDE.md").exists():
        # Already documented — nothing to create (root index already includes it).
        print("{}")
        return 0

    state = _load_state(cid)
    done = state.get("scaffolded", [])
    if rel in done:
        print("{}")
        return 0

    # Engine does the create (CLAUDE.md + AGENTS.md) + re-syncs the root index.
    try:
        made = dox_engine.ensure_dir_documented(root, d, cfg)
    except Exception:
        print("{}")
        return 0

    if not made:
        print("{}")
        return 0

    done.append(rel)
    state["scaffolded"] = done
    _save_state(cid, state)

    made_label = " + ".join(made)
    msg = (
        f"📄 dox: auto-created `{rel}/{made_label}` (stub) and re-synced the root "
        f"`CLAUDE.md` index — this directory had no local doc. Flesh out the stub "
        f"(what lives here, local conventions, key files) before completing — Phase 7. "
        f"The completion gate counts a CLAUDE.md update as the docs signal."
    )
    print(json.dumps({"additionalContext": msg}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
