#!/usr/bin/env python3
"""dox-tree-guard.py — auto-initialize & maintain the dox CLAUDE.md tree per repo.

Mirrors tdd-guard-init-guard.py / the jcodemunch+graphify index guards: the user
never hand-creates the dox scaffold. Detects whether a repo has a dox documentation
tree, and on SessionStart runs a full END-TO-END SWEEP via `dox_engine` — creating a
`CLAUDE.md` + `AGENTS.md` in EVERY directory (not just "significant" ones) and syncing
the root `CLAUDE.md` index block to match the tree on disk.

Bootstrap policy: "auto-create everything + agent fills the prose". The guard writes
the root stub AND every child stub (marked `<!-- dox:root v1 -->` / `<!-- dox:child v1 -->`);
the agent fleshes out the local rules. Coverage is automatic; quality is the agent's job.

Modes (argv[1]):
  session  Full sweep (SessionStart, via session-start-aggregator). When the structure
           FINGERPRINT changed, or any directory is missing its docs, sweeps the whole
           tree and reports what was created. Otherwise silent.
  prompt   Cheap pass (UserPromptSubmit, via token-stack-prompt-reminder). Stubs a
           missing root + reminds; once a root exists, steers "read dox first".

Ownership (so hand-written roots are never clobbered):
  A root is AUTO-MANAGED iff it carries the dox marker (we wrote it) OR the sidecar
  records autoManaged=true. A hand-written root with no marker is left untouched for its
  prose — but its auto-managed `<!-- dox:index -->` block IS still synced (append-once
  if absent), because keeping the index current is the whole point.

NOT a PreToolUse gate — fails OPEN, never blocks. Emits {"additionalContext": ...}.
Python 3.8+ stdlib only. Exit 0 always.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR / ".state"
CONFIG_PATH = SCRIPT_DIR / "dox-tree-guard.config.json"

sys.path.insert(0, str(SCRIPT_DIR))
try:
    import dox_engine  # type: ignore
except Exception:  # pragma: no cover — engine missing -> fail open
    dox_engine = None  # type: ignore

DATA_REL = Path(".claude") / "dox" / "data"
SIDECAR_NAME = ".doxinit.json"
ROOT_DOC = "CLAUDE.md"
SCHEMA_VERSION = 2
MAX_REPORTED = 12


# --------------------------------------------------------------------------- #
# IO helpers
# --------------------------------------------------------------------------- #
def _read_payload() -> dict:
    try:
        raw = sys.stdin.read() or "{}"
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def _emit(text: str) -> int:
    print(json.dumps({"additionalContext": text}) if text else "{}")
    return 0


def _cfg() -> dict:
    if dox_engine is None:
        return {"enabled": True}
    return dox_engine.load_cfg(CONFIG_PATH)


def _git_root(start: Path) -> "Path | None":
    cur = start if start.is_dir() else start.parent
    for _ in range(25):
        if (cur / ".git").exists():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def _find_root(payload: dict) -> "Path | None":
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots:
        p = Path(str(roots[0]))
        if p.is_dir():
            return _git_root(p) or p
    for key in ("cwd", "project_dir"):
        v = payload.get(key)
        if v and Path(str(v)).is_dir():
            return _git_root(Path(str(v)))
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return _git_root(Path(env))
    return _git_root(Path(os.getcwd()))


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


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _prompt_state_path(cid: str) -> Path:
    return STATE_DIR / f"{_safe_cid(cid)}.dox-prompt.json"


def _load_prompt_state(cid: str) -> dict:
    if not cid:
        return {}
    p = _prompt_state_path(cid)
    try:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_prompt_state(cid: str, state: dict) -> None:
    if not cid:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _prompt_state_path(cid).write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Sidecar persistence
# --------------------------------------------------------------------------- #
def _paths(root: Path) -> "tuple[Path, Path, Path]":
    data = root / DATA_REL
    return data, root / ROOT_DOC, data / SIDECAR_NAME


def _load_sidecar(sidecar: Path) -> "dict | None":
    try:
        if sidecar.is_file():
            return json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _write_sidecar(data: Path, sidecar: Path, fp: str, collected: dict,
                   auto_managed: bool) -> None:
    try:
        data.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps({
            "autoManaged": auto_managed,
            "version": SCHEMA_VERSION,
            "fingerprint": fp,
            "documentedDirs": collected.get("dirs", []),
            "missingChildren": collected.get("missing", []),
        }, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _root_is_dox(root_doc: Path, cfg: dict) -> bool:
    marker = cfg.get("rootDoxMarker") or dox_engine.ROOT_MARKER
    try:
        return marker in root_doc.read_text(encoding="utf-8")[:400]
    except Exception:
        return False


def _missing_line(collected: dict) -> str:
    miss = collected.get("missing", [])
    if not miss:
        return ""
    shown = miss[:MAX_REPORTED]
    extra = len(miss) - len(shown)
    tail = f" (+{extra} more)" if extra > 0 else ""
    return "Directories still missing a local CLAUDE.md: " + \
        ", ".join(f"`{d}`" for d in shown) + tail


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
def run_session() -> int:
    if dox_engine is None:
        return _emit("")
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return _emit("")
    payload = _read_payload()
    root = _find_root(payload)
    if root is None or not (root / ".git").exists() or _is_exempt(root, cfg):
        return _emit("")

    data, root_doc, sidecar_path = _paths(root)
    collected = dox_engine.collect(root, cfg)
    if not collected["has_code"]:
        return _emit("")  # not a code project — don't pollute
    fp = dox_engine.fingerprint(collected)
    sidecar = _load_sidecar(sidecar_path)
    root_missing = not root_doc.exists()

    # Skip work only when everything is already in place AND unchanged.
    unchanged = (
        not root_missing
        and not collected["missing"]
        and sidecar is not None
        and sidecar.get("fingerprint") == fp
    )
    if unchanged:
        return _emit("")

    # Full end-to-end sweep: root + every dir gets docs, root index synced.
    summary = dox_engine.sweep(root, cfg, create=True)
    collected = summary.get("collected", collected)
    fp = summary.get("fingerprint", fp)

    dox_managed = _root_is_dox(root_doc, cfg)
    auto = dox_managed or bool(sidecar and sidecar.get("autoManaged")) or root_missing
    _write_sidecar(data, sidecar_path, fp, collected, auto_managed=auto)

    n_new = len(summary["documented_dirs"])
    total = summary["total_dirs"]
    bits = []
    if summary["root_created"]:
        bits.append("root `CLAUDE.md` stubbed")
    if n_new:
        bits.append(f"created `CLAUDE.md` + `AGENTS.md` in {n_new} new dir(s)")
    if summary["index_synced"]:
        bits.append(f"root index synced ({total} dirs)")
    if summary.get("truncated"):
        bits.append(f"⚠ truncated at maxSweepDirs={cfg.get('maxSweepDirs')}")
    if not bits:
        # Nothing created and index already current — but fingerprint moved.
        miss = _missing_line(collected)
        if not miss:
            return _emit("")
        return _emit(f"dox: `{root.name}` — {miss}.")

    head = f"dox: swept `{root.name}` — " + "; ".join(bits) + "."
    tail = (
        " These are STUBS — flesh out each local `CLAUDE.md` (what lives here, "
        "conventions, key files) as you touch the area (Phase 7). Read the root "
        "`CLAUDE.md` → the local one before editing code in any directory."
    )
    return _emit(head + tail)


def run_prompt() -> int:
    if dox_engine is None:
        return _emit("")
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return _emit("")
    payload = _read_payload()
    root = _find_root(payload)
    if root is None or not (root / ".git").exists() or _is_exempt(root, cfg):
        return _emit("")

    data, root_doc, sidecar_path = _paths(root)

    # ---- Root MISSING: stub it (+ a quick sweep) and mandate scaffolding. ----
    if not root_doc.exists():
        collected = dox_engine.collect(root, cfg)
        if not collected["has_code"]:
            return _emit("")
        summary = dox_engine.sweep(root, cfg, create=True)
        collected = summary.get("collected", collected)
        _write_sidecar(data, sidecar_path, summary.get("fingerprint", ""),
                       collected, auto_managed=True)
        n_new = len(summary["documented_dirs"])
        return _emit(
            f"DOX FIRST — dox tree bootstrapped for `{root.name}` (root + "
            f"{n_new} dir(s) now have `CLAUDE.md`/`AGENTS.md` stubs). STEP 1 of this "
            "task: flesh out the root + the area you're touching via the `dox-doc-tree` "
            "skill (code writes are gated until the root exists). STEP LAST (Phase 7): "
            "update the touched dirs' `CLAUDE.md` + repo docs."
        )

    # ---- Root EXISTS: steer "read dox first", every task. ----
    cid = str(payload.get("session_id") or payload.get("conversation_id") or "")
    state = _load_prompt_state(cid)
    repo_key = str(root.resolve())
    seen = state.get("read_first_repos") or []

    if repo_key not in seen:
        seen.append(repo_key)
        state["read_first_repos"] = seen
        _save_prompt_state(cid, state)

        collected = dox_engine.collect(root, cfg)
        documented = [d for d in collected["dirs"] if d not in set(collected["missing"])]
        child_hint = ""
        if documented:
            shown = documented[:8]
            extra = len(documented) - len(shown)
            tail = f" (+{extra} more)" if extra > 0 else ""
            child_hint = (
                " Local docs exist in: "
                + ", ".join(f"`{d}/CLAUDE.md`" for d in shown) + tail + "."
            )
        return _emit(
            f"DOX FIRST — `{root.name}` has a documentation tree. STEP 1 of this task, "
            "before reading code or editing anything: read `CLAUDE.md` (repo root) for "
            "project-wide rules, then the local `CLAUDE.md` for the directory you'll touch "
            f"(root → target) so you start with full context.{child_hint} STEP LAST "
            "(Phase 7): update the local `CLAUDE.md` for every directory you changed, plus "
            "repo docs — the Stop gate enforces this."
        )

    return _emit(
        f"DOX FIRST: read `{root.name}`'s `CLAUDE.md` (root → target dir) before working; "
        "update the touched dirs' `CLAUDE.md` + repo docs at the end."
    )


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "session"
    try:
        return run_prompt() if mode == "prompt" else run_session()
    except Exception:
        return _emit("")


if __name__ == "__main__":
    raise SystemExit(main())
