#!/usr/bin/env python3
"""index-lifecycle.py — active-repo, zero-daemon, 4-surface auto-index brain.

Owns the freshness lifecycle of all four code/doc index surfaces for the ONE
active repo the agent is working in:

    jcodemunch  (code symbol index, ~/.code-index/*-<name>*.db)
    jdocmunch   (doc section index, ~/.doc-index/local/<name>.json)
    graphify    (dependency graph, <root>/graphify-out/graph.json)
    dox         (per-dir CLAUDE.md tree, <root>/.claude/dox/data/.doxinit.json)

Modes (argv[1]):
    session-start   probe all 4 surfaces in parallel (<~1.5s), auto-spawn a
                    DETACHED single-shot builder for any MISSING/STALE surface,
                    drain any leftover write-journal, emit one status blob.
    post-write      journal a touched path IFF inside the active repo; flush at
                    N writes or T seconds (debounced, NO timer process).
    tick            lazy T-threshold re-check (piggybacks the next prompt).
    flush           drain the write-journal now (Stop-time).
    session-end     final journal drain + state write (replaces the old
                    systemd watch-daemon-session-end.py — no systemd anything).
    build           the DETACHED single-shot worker: --root/--key/--surfaces
                    [--incremental] [--journal FILE]. Refuses a mismatched key.

Design invariants (Spec B §3, Charter §7):
  * Active repo ONLY — the root is resolved exclusively by lib/repo_context.py.
    The config has NO path field, so there is nothing to iterate; a write
    outside the active repo is dropped (path-containment via rc.is_inside).
  * Zero daemons — builders are detached single-shot subprocesses
    (start_new_session POSIX / DETACHED_PROCESS Windows), time-boxed, that run
    one command and exit. No systemd, no persistent watchers, no timers.
  * Fail-open everywhere — any probe/build/lock error degrades to "assume
    fresh, continue"; a non-git cwd makes every surface a no-op at zero cost.
  * Windows + Ubuntu portable — all OS branching goes through lib/platform.py.

Foundation libs (lib/repo_context.py, lib/platform.py, lib/hook_telemetry.py)
are imported directly; if they are transiently unavailable the whole hook
fails open (prints "{}" / no-op), never breaking a session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

# --- foundation libs (P1-T1). Direct use; fail-open if transiently broken. ---
try:
    from lib import platform as plat
    from lib import repo_context as rc
    from lib import hook_telemetry as tel
    _LIBS_OK = True
except Exception:  # pragma: no cover - defensive; hook must never hard-crash
    _LIBS_OK = False


# --------------------------------------------------------------------------- #
# Paths & constants
# --------------------------------------------------------------------------- #
HOME = Path.home()
CODE_INDEX_DIR = HOME / ".code-index"
DOC_INDEX_DIR = HOME / ".doc-index" / "local"
STATE_DIR = HOOK_DIR / ".state" / "index"
CONFIG_FILE = HOOK_DIR / "index-lifecycle.config.json"

FRESH, STALE, MISSING, BUILDING, FAILED, UNAVAILABLE = (
    "FRESH", "STALE", "MISSING", "BUILDING", "FAILED", "UNAVAILABLE",
)
SURFACES = ("jcodemunch", "jdocmunch", "graphify", "dox")

DOC_GLOBS = ["*.md", "*.mdx", "*.markdown", "*.rst", "*.adoc", "*.txt",
             "*.yaml", "*.yml", "*.html", "*.ipynb"]

_DEFAULT_CONFIG = {
    "debounce": {"writes_threshold": 5, "seconds_threshold": 45},
    "probe_timeouts_ms": {"jcodemunch": 500, "jdocmunch": 800, "graphify": 3000, "dox": 300},
    "build_timeouts_s": {"jcodemunch": 300, "jdocmunch": 120, "graphify": 120, "dox": 60},
    "max_build_failures": 3,
    "lock_ttl_minutes": 30,
    "max_doc_stats": 5000,
    "incremental_file_cap": 20,
    "surfaces_enabled": {"jcodemunch": True, "jdocmunch": True, "graphify": True, "dox": True},
    "relax_read_gate_while_building": True,
}


# --------------------------------------------------------------------------- #
# Small fail-open wrappers around the foundation libs
# --------------------------------------------------------------------------- #
def _telem(kind: str, **fields) -> None:
    if not _LIBS_OK:
        return
    try:
        tel.record("index-lifecycle", kind, **fields)
    except Exception:
        pass


def _which(name: str) -> bool:
    import shutil
    return shutil.which(name) is not None


def _run(cmd, timeout):
    """Never-raising subprocess.run (delegates to lib.platform.run)."""
    if _LIBS_OK:
        return plat.run(cmd, timeout=timeout)
    import subprocess
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True,
                              timeout=timeout, check=False)
    except Exception as exc:  # noqa: BLE001
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def _pid_alive(pid: int) -> bool:
    if _LIBS_OK:
        try:
            return plat.pid_alive(pid)
        except Exception:
            return False
    try:
        if os.name == "nt":
            return True  # can't cheaply check; assume alive (conservative)
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def _atomic_write(path: Path, data: str) -> bool:
    if _LIBS_OK:
        try:
            return plat.atomic_write(path, data)
        except Exception:
            return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _spawn_detached(cmd, cwd=None):
    if _LIBS_OK:
        try:
            return plat.spawn_detached(cmd, cwd=cwd)
        except Exception:
            return None
    import subprocess
    try:
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                  "stderr": subprocess.DEVNULL, "close_fds": True,
                  "cwd": str(cwd) if cwd else None}
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        return subprocess.Popen(list(cmd), **kwargs).pid
    except Exception:  # noqa: BLE001
        return None


def _python_exe() -> str:
    if _LIBS_OK:
        try:
            return plat.python_exe()
        except Exception:
            pass
    return sys.executable or "python3"


def _repo_key(root: Path) -> str:
    """Mirror of lib.repo_context key formula: '<name>-<sha1(abspath)[:8]>'."""
    try:
        ap = str(root.resolve())
    except OSError:
        ap = str(root)
    digest = hashlib.sha1(ap.encode("utf-8", "replace")).hexdigest()[:8]
    return f"{root.name or 'root'}-{digest}"


# --------------------------------------------------------------------------- #
# Config / payload / state IO
# --------------------------------------------------------------------------- #
def _load_config() -> dict:
    cfg = json.loads(json.dumps(_DEFAULT_CONFIG))  # deep copy
    try:
        if CONFIG_FILE.is_file():
            user = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
    except Exception:
        pass
    return cfg


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    raw = raw.strip() if raw else ""
    if not raw:
        return {}
    try:
        p = json.loads(raw)
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}


def _active_ctx(payload):
    if not _LIBS_OK:
        return None
    try:
        return rc.active_repo(payload)
    except Exception:
        return None


def _state_path(key: str) -> Path:
    return STATE_DIR / f"{key}.json"


def _load_state(ctx) -> dict:
    p = _state_path(ctx.key)
    try:
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("surfaces", {})
                data.setdefault("journal", {"first_write_at": None, "entries": []})
                return data
    except Exception:
        pass
    return {
        "repo_root": ctx.root,
        "repo_key": ctx.key,
        "surfaces": {},
        "journal": {"first_write_at": None, "entries": []},
    }


def _save_state(ctx, state: dict) -> None:
    state["repo_root"] = ctx.root
    state["repo_key"] = ctx.key
    try:
        _atomic_write(_state_path(ctx.key), json.dumps(state, indent=2))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Build locks (PID-liveness + TTL, no daemons)
# --------------------------------------------------------------------------- #
def _lock_path(key: str, surface: str) -> Path:
    return STATE_DIR / f"{key}.{surface}.lock"


def _read_lock(p: Path):
    try:
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return d
    except Exception:
        pass
    return None


def _lock_is_live(key: str, surface: str, ttl_minutes: float) -> bool:
    """True if a build is genuinely in flight. Breaks a truly-stale lock.

    A lock is live if its pid is alive. If the pid is dead we keep it for a
    grace window (ttl) to cover the spawn→worker-writes-own-pid gap and to
    provide crash backoff; past the ttl we break it (telemetry lock_broken).
    """
    p = _lock_path(key, surface)
    d = _read_lock(p)
    if not d:
        return False
    pid = d.get("pid")
    started = float(d.get("started_at") or 0)
    try:
        if pid and _pid_alive(int(pid)):
            return True
    except Exception:
        pass
    age_min = (time.time() - started) / 60.0
    if age_min < ttl_minutes:
        return True  # startup grace / recent crash backoff
    try:
        p.unlink()
        _telem("lock_broken", surface=surface, key=key, age_min=round(age_min, 1))
    except OSError:
        pass
    return False


def _claim_lock(key: str, surface: str, cmd: str) -> bool:
    """Atomically create a lock. Returns True iff we created it (O_EXCL)."""
    p = _lock_path(key, surface)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "started_at": time.time(), "cmd": cmd}, f)
        return True
    except FileExistsError:
        return False
    except Exception:  # noqa: BLE001
        return False


def _rewrite_lock(key: str, surface: str, cmd: str) -> None:
    p = _lock_path(key, surface)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _atomic_write(p, json.dumps(
            {"pid": os.getpid(), "started_at": time.time(), "cmd": cmd}))
    except Exception:
        pass


def _release_lock(key: str, surface: str) -> None:
    try:
        _lock_path(key, surface).unlink()
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Probes — each returns (state, fingerprint: dict, detail: str)
# --------------------------------------------------------------------------- #
def _git(root: Path, args, timeout=5):
    return _run(["git", "-C", str(root)] + list(args), timeout=timeout)


def _dirty_sha(root: Path) -> str:
    cp = _git(root, ["status", "--porcelain", "-z"], timeout=5)
    body = (cp.stdout or "") if cp.returncode == 0 else ""
    return hashlib.sha1(body.encode("utf-8", "replace")).hexdigest()[:16]


def _probe_jcodemunch(root: Path, prior: dict) -> tuple:
    if not _which("jcodemunch-mcp"):
        return (UNAVAILABLE, {}, "jcodemunch-mcp not installed")
    dbs = sorted(CODE_INDEX_DIR.glob(f"*-{root.name}*.db")) or \
        sorted(CODE_INDEX_DIR.glob(f"*{root.name}*.db"))
    head_cp = _git(root, ["rev-parse", "HEAD"], timeout=5)
    head = head_cp.stdout.strip() if head_cp.returncode == 0 else None
    dirty = _dirty_sha(root)
    fp = {"git_head": head, "dirty_sha": dirty}
    if not dbs:
        return (MISSING, fp, "no index db")
    indexed_head = None
    try:
        conn = sqlite3.connect(str(dbs[0]))
        cur = conn.execute("SELECT value FROM meta WHERE key='git_head'")
        row = cur.fetchone()
        conn.close()
        indexed_head = row[0] if row else None
    except Exception:
        indexed_head = None
    if indexed_head and head and indexed_head != head:
        return (STALE, fp, "git HEAD moved since index")
    prior_dirty = (prior.get("fingerprint") or {}).get("dirty_sha")
    if prior_dirty is not None and prior_dirty != dirty:
        return (STALE, fp, "uncommitted edits since index")
    return (FRESH, fp, "")


def _probe_jdocmunch(root: Path, prior: dict, max_stats: int) -> tuple:
    name = root.name
    manifest = DOC_INDEX_DIR / f"{name}.json"
    if not manifest.is_file():
        return (MISSING, {}, "no doc manifest")
    cp = _git(root, ["ls-files", "-z", "--"] + DOC_GLOBS, timeout=5)
    newest = 0.0
    if cp.returncode == 0 and cp.stdout:
        rels = cp.stdout.split("\0")[:max_stats]
        for rel in rels:
            if not rel:
                continue
            try:
                mt = (root / rel).stat().st_mtime
                if mt > newest:
                    newest = mt
            except OSError:
                continue
    fp = {"manifest_mtime": manifest.stat().st_mtime, "newest_doc": newest}
    if newest and newest > manifest.stat().st_mtime + 2:
        return (STALE, fp, "tracked docs newer than index")
    return (FRESH, fp, "")


def _probe_graphify(root: Path, prior: dict, timeout_ms: int) -> tuple:
    graph = root / "graphify-out" / "graph.json"
    if not graph.is_file():
        return (MISSING, {}, "no graph.json")
    fp = {"graph_mtime": graph.stat().st_mtime}
    if _which("graphify"):
        cp = _run(["graphify", "check-update", str(root)], timeout=max(1.0, timeout_ms / 1000.0))
        if cp.returncode == 124:  # timeout — fail-open
            _telem("probe_timeout", surface="graphify", key=_repo_key(root))
            return (FRESH, fp, "probe timeout (assumed fresh)")
        if cp.returncode == 127:  # binary vanished mid-run → mtime fallback
            return _graphify_mtime_fallback(root, graph, fp)
        out = (cp.stdout or "").strip()
        if cp.returncode != 0:
            return (STALE, fp, out or "check-update non-zero")
        if out:
            return (STALE, fp, out)
        return (FRESH, fp, "")
    return _graphify_mtime_fallback(root, graph, fp)


def _graphify_mtime_fallback(root: Path, graph: Path, fp: dict) -> tuple:
    cp = _git(root, ["log", "-1", "--format=%ct", "HEAD"], timeout=5)
    if cp.returncode == 0 and cp.stdout.strip():
        try:
            commit_time = float(cp.stdout.strip())
            if commit_time > graph.stat().st_mtime:
                return (STALE, fp, "graph older than latest commit")
        except ValueError:
            pass
    return (FRESH, fp, "")


def _probe_dox(root: Path, prior: dict) -> tuple:
    sidecar = root / ".claude" / "dox" / "data" / ".doxinit.json"
    if not sidecar.is_file():
        return (MISSING, {}, "no dox sidecar")
    fp = {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        fp = {"fingerprint": data.get("fingerprint")}
    except Exception:
        pass
    # Cheap presence probe: drift within a documented tree is handled by the
    # idempotent sweep + the still-wired dox-child-scaffold PostToolUse hook.
    return (FRESH, fp, "")


_PROBE = {
    "jcodemunch": lambda root, prior, cfg: _probe_jcodemunch(root, prior),
    "jdocmunch": lambda root, prior, cfg: _probe_jdocmunch(root, prior, cfg["max_doc_stats"]),
    "graphify": lambda root, prior, cfg: _probe_graphify(root, prior, cfg["probe_timeouts_ms"]["graphify"]),
    "dox": lambda root, prior, cfg: _probe_dox(root, prior),
}


def _probe_all(ctx, state: dict, cfg: dict) -> dict:
    """Probe every enabled surface in parallel; fail-open to FRESH on timeout."""
    enabled = [s for s in SURFACES if cfg["surfaces_enabled"].get(s, True)]
    root = Path(ctx.root)
    results: dict = {}
    wall = max(cfg["probe_timeouts_ms"].values()) / 1000.0 + 1.0
    with ThreadPoolExecutor(max_workers=max(1, len(enabled))) as pool:
        futs = {
            pool.submit(_PROBE[s], root, state.get("surfaces", {}).get(s, {}), cfg): s
            for s in enabled
        }
        for fut, s in futs.items():
            try:
                results[s] = fut.result(timeout=wall)
            except (FutureTimeout, Exception):  # noqa: BLE001
                _telem("probe_timeout", surface=s, key=ctx.key)
                results[s] = (FRESH, {}, "probe timeout (assumed fresh)")
    return results


# --------------------------------------------------------------------------- #
# Builders (single-shot, time-boxed, run inside the detached worker)
# --------------------------------------------------------------------------- #
def _build_jcodemunch(root: Path, incremental: bool, paths, cfg: dict) -> bool:
    if not _which("jcodemunch-mcp"):
        return False
    to = cfg["build_timeouts_s"]["jcodemunch"]
    if incremental and paths and len(paths) <= cfg["incremental_file_cap"]:
        ok = True
        for pth in paths:
            cp = _run(["jcodemunch-mcp", "index-file", str(pth)], timeout=to)
            ok = ok and cp.returncode == 0
        return ok
    cp = _run(["jcodemunch-mcp", "index", str(root)], timeout=to)
    return cp.returncode == 0


def _build_jdocmunch(root: Path, incremental: bool, paths, cfg: dict) -> bool:
    if not _which("jdocmunch-mcp"):
        return False
    to = cfg["build_timeouts_s"]["jdocmunch"]
    name = root.name
    if incremental and paths:
        docs = [str(p) for p in paths
                if Path(p).suffix.lower() in
                {".md", ".mdx", ".markdown", ".rst", ".adoc", ".txt",
                 ".yaml", ".yml", ".html", ".ipynb"}]
        if not docs:
            return True  # nothing doc-shaped to reindex
        listing = STATE_DIR / f".jdoc-paths-{os.getpid()}-{int(time.time())}.txt"
        try:
            listing.write_text("\n".join(docs) + "\n", encoding="utf-8")
            cp = _run(["jdocmunch-mcp", "index-local", "--path", str(root),
                       "--name", name, "--paths-from", str(listing)], timeout=to)
            return cp.returncode == 0
        finally:
            try:
                listing.unlink()
            except OSError:
                pass
    cp = _run(["jdocmunch-mcp", "index-local", "--path", str(root),
               "--name", name], timeout=to)
    return cp.returncode == 0


def _build_graphify(root: Path, incremental: bool, paths, cfg: dict) -> bool:
    if not _which("graphify"):
        return False
    cp = _run(["graphify", "update", str(root)],
              timeout=cfg["build_timeouts_s"]["graphify"])
    return cp.returncode == 0


def _build_dox(root: Path, incremental: bool, paths, cfg: dict) -> bool:
    # Mid-session (incremental) dox freshness is owned by the still-wired
    # dox-child-scaffold.py PostToolUse hook, so incremental is a no-op here.
    if incremental:
        return True
    cp = _run([_python_exe(), str(HOOK_DIR / "dox_engine.py"), "sweep", str(root)],
              timeout=cfg["build_timeouts_s"]["dox"])
    return cp.returncode == 0


_BUILD = {
    "jcodemunch": _build_jcodemunch,
    "jdocmunch": _build_jdocmunch,
    "graphify": _build_graphify,
    "dox": _build_dox,
}


# --------------------------------------------------------------------------- #
# Journal flush (spawn ONE detached incremental worker)
# --------------------------------------------------------------------------- #
def _spawn_build(ctx, surfaces, incremental: bool, journal_file: Path | None) -> None:
    cmd = [_python_exe(), str(Path(__file__).resolve()), "build",
           "--root", ctx.root, "--key", ctx.key,
           "--surfaces", ",".join(surfaces)]
    if incremental:
        cmd.append("--incremental")
    if journal_file is not None:
        cmd += ["--journal", str(journal_file)]
    _spawn_detached(cmd, cwd=ctx.root)


def _flush(ctx, state: dict, cfg: dict) -> None:
    """Drain the write-journal: spawn one detached incremental worker, clear.

    Claims a per-surface lock before spawning so an incremental flush can never
    overlap another build of the SAME surface (no duplicate ``graphify update``,
    no concurrent index of the same DB). A surface already busy with a full
    build is skipped here — that full build already covers the journaled files.
    """
    journal = state.get("journal") or {}
    entries = journal.get("entries") or []
    if not entries:
        return
    paths = []
    seen = set()
    for e in entries:
        pth = e.get("path")
        if not pth or pth in seen:
            continue
        seen.add(pth)
        try:
            if Path(pth).exists():
                paths.append(pth)
        except OSError:
            continue
    if not paths:
        # Journaled files all vanished (deletes) — nothing to incrementally
        # index; a delete flips dirty_sha, so the next session-start probe marks
        # the surface STALE and fully rebuilds. Truncate and move on.
        state["journal"] = {"first_write_at": None, "entries": []}
        _save_state(ctx, state)
        return
    enabled = [s for s in SURFACES if cfg["surfaces_enabled"].get(s, True)]
    ttl = cfg["lock_ttl_minutes"]
    claimed = [s for s in enabled
               if not _lock_is_live(ctx.key, s, ttl)
               and _claim_lock(ctx.key, s, f"flush {s}")]
    if not claimed:
        # Every surface is mid-build — keep the journal and drain on the next
        # tick / Stop / session-start rather than overlapping a build.
        _telem("flush_deferred_all_locked", key=ctx.key, pending=len(paths))
        return
    listing = STATE_DIR / f"{ctx.key}.flush-{os.getpid()}-{int(time.time())}.txt"
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        listing.write_text("\n".join(paths) + "\n", encoding="utf-8")
    except OSError:
        listing = None
    _spawn_build(ctx, claimed, incremental=True, journal_file=listing)
    # Truncate the journal now (pragmatic: a failed build leaves the surface to
    # be caught STALE + fully rebuilt at the next session-start probe). The
    # detached worker releases each claimed surface lock when it finishes.
    state["journal"] = {"first_write_at": None, "entries": []}
    _save_state(ctx, state)


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
def mode_session_start(payload: dict, cfg: dict) -> int:
    ctx = _active_ctx(payload)
    if ctx is None:
        print("{}")
        return 0
    state = _load_state(ctx)

    # Drain a journal left behind by a killed session before probing.
    if (state.get("journal") or {}).get("entries"):
        _flush(ctx, state, cfg)
        state = _load_state(ctx)

    probes = _probe_all(ctx, state, cfg)
    ttl = cfg["lock_ttl_minutes"]
    maxf = cfg["max_build_failures"]
    lines: list[str] = []
    to_build: list[str] = []

    for surface in SURFACES:
        if surface not in probes:
            continue
        st, fp, detail = probes[surface]
        prior = state.get("surfaces", {}).get(surface, {})
        rec = {"state": st, "fingerprint": fp, "checked_at": int(time.time()),
               "built_at": prior.get("built_at"), "failures": prior.get("failures", 0)}

        if st == UNAVAILABLE:
            rec["state"] = UNAVAILABLE
            if prior.get("state") != UNAVAILABLE:  # note once
                lines.append(f"{surface}: UNAVAILABLE ({detail})")
        elif st == FRESH:
            rec["state"] = FRESH
            rec["failures"] = 0
            lines.append(f"{surface} index: FRESH — `{ctx.name}`")
        else:  # STALE or MISSING
            failures = prior.get("failures", 0)
            backed_off = (prior.get("state") == FAILED
                          and failures >= maxf
                          and prior.get("fingerprint") == fp)
            if backed_off:
                rec["state"] = FAILED
                lines.append(f"{surface} index: {st} but build FAILED "
                             f"{failures}x — backing off until it changes ({detail})")
            elif _lock_is_live(ctx.key, surface, ttl):
                rec["state"] = BUILDING
                lines.append(f"{surface} index: {st} — building in background…")
            elif _claim_lock(ctx.key, surface, f"session-start {surface}"):
                rec["state"] = BUILDING
                to_build.append(surface)
                lines.append(f"{surface} index: {st} for `{ctx.name}` — "
                             f"building in background (no action needed)")
            else:
                rec["state"] = BUILDING
                lines.append(f"{surface} index: {st} — building in background…")
        state.setdefault("surfaces", {})[surface] = rec

    _save_state(ctx, state)

    if to_build:
        _spawn_build(ctx, to_build, incremental=False, journal_file=None)

    if not lines:
        print("{}")
        return 0
    ctx_blob = ("Index lifecycle (auto, background — no agent action required):\n"
                + "\n".join(f"- {ln}" for ln in lines))
    print(json.dumps({"additionalContext": ctx_blob}))
    return 0


def _journal_touch(payload: dict, ctx, state: dict) -> bool:
    """Append the written path to the journal iff inside the active repo."""
    tool = payload.get("tool_name") or payload.get("tool") or ""
    tinput = payload.get("tool_input") or {}
    fpath = tinput.get("file_path") or tinput.get("path") or tinput.get("notebook_path")
    if not fpath:
        return False
    inside = rc.is_inside(ctx, fpath) if _LIBS_OK else False
    if not inside:
        _telem("out_of_repo_write", key=ctx.key, path=str(fpath)[:200])
        return False
    journal = state.setdefault("journal", {"first_write_at": None, "entries": []})
    if journal.get("first_write_at") is None:
        journal["first_write_at"] = time.time()
    journal.setdefault("entries", []).append(
        {"path": str(fpath), "tool": tool, "ts": time.time()})
    return True


def mode_post_write(payload: dict, cfg: dict) -> int:
    ctx = _active_ctx(payload)
    if ctx is None:
        print("{}")
        return 0
    state = _load_state(ctx)
    if not _journal_touch(payload, ctx, state):
        print("{}")
        return 0
    journal = state["journal"]
    entries = journal.get("entries", [])
    n = cfg["debounce"]["writes_threshold"]
    t = cfg["debounce"]["seconds_threshold"]
    first = journal.get("first_write_at") or time.time()
    if len(entries) >= n or (time.time() - first) >= t:
        _flush(ctx, state, cfg)  # flush saves state
    else:
        _save_state(ctx, state)
    print("{}")
    return 0


def mode_tick(payload: dict, cfg: dict) -> int:
    ctx = _active_ctx(payload)
    if ctx is None:
        print("{}")
        return 0
    state = _load_state(ctx)
    journal = state.get("journal") or {}
    entries = journal.get("entries") or []
    t = cfg["debounce"]["seconds_threshold"]
    first = journal.get("first_write_at")
    if entries and first is not None and (time.time() - first) >= t:
        _flush(ctx, state, cfg)
    print("{}")
    return 0


def mode_flush(payload: dict, cfg: dict) -> int:
    ctx = _active_ctx(payload)
    if ctx is None:
        print("{}")
        return 0
    state = _load_state(ctx)
    if (state.get("journal") or {}).get("entries"):
        _flush(ctx, state, cfg)
    print("{}")
    return 0


def mode_session_end(payload: dict, cfg: dict) -> int:
    return mode_flush(payload, cfg)


def mode_build(args, cfg: dict) -> int:
    """Detached single-shot worker. Refuses a mismatched repo key."""
    root = Path(args.root)
    if _repo_key(root) != args.key:
        _telem("build_refused_key_mismatch", key=args.key, root=str(root))
        return 0

    class _Ctx:
        pass
    ctx = _Ctx()
    ctx.root = str(root)
    ctx.key = args.key
    ctx.name = root.name

    surfaces = [s for s in (args.surfaces or "").split(",")
                if s and cfg["surfaces_enabled"].get(s, True)]
    if not surfaces:
        return 0
    paths = []
    if args.journal:
        try:
            paths = [ln.strip() for ln in
                     Path(args.journal).read_text(encoding="utf-8").splitlines()
                     if ln.strip()]
        except OSError:
            paths = []

    maxf = cfg["max_build_failures"]
    for surface in surfaces:
        _rewrite_lock(ctx.key, surface, f"build {surface}")
        ok = False
        try:
            ok = _BUILD[surface](root, args.incremental, paths, cfg)
        except Exception as exc:  # noqa: BLE001
            _telem("build_error", surface=surface, key=ctx.key, error=str(exc)[:200])
            ok = False
        finally:
            _release_lock(ctx.key, surface)

        # Reload → mutate only this surface → save (minimise cross-write window
        # with a concurrent post-write appending to the journal).
        state = _load_state(ctx)
        prior = state.get("surfaces", {}).get(surface, {})
        if ok:
            try:
                st, fp, _ = _PROBE[surface](root, prior, cfg)
            except Exception:  # noqa: BLE001
                st, fp = FRESH, prior.get("fingerprint", {})
            state.setdefault("surfaces", {})[surface] = {
                "state": FRESH, "fingerprint": fp,
                "checked_at": int(time.time()), "built_at": int(time.time()),
                "failures": 0}
            _telem("build_ok", surface=surface, key=ctx.key,
                   incremental=bool(args.incremental))
        else:
            failures = int(prior.get("failures", 0)) + 1
            state.setdefault("surfaces", {})[surface] = {
                "state": FAILED if failures >= maxf else STALE,
                "fingerprint": prior.get("fingerprint", {}),
                "checked_at": int(time.time()),
                "built_at": prior.get("built_at"), "failures": failures}
            _telem("build_fail", surface=surface, key=ctx.key, failures=failures)
        _save_state(ctx, state)

    if args.journal:
        try:
            Path(args.journal).unlink()
        except OSError:
            pass
    return 0


# --------------------------------------------------------------------------- #
# Public helper for jcodemunch-enforce.py (read-gate relaxation, Spec B §3.3)
# --------------------------------------------------------------------------- #
def is_building(payload: dict | None = None) -> bool:
    """True if any surface of the active repo is currently BUILDING.

    Consumed by jcodemunch-enforce.py to relax the blind-read gate so the agent
    is never bricked while an index self-heals in the background. Fail-open:
    returns False on any error (gate behaves normally).
    """
    try:
        cfg = _load_config()
        if not cfg.get("relax_read_gate_while_building", True):
            return False
        ctx = _active_ctx(payload or {})
        if ctx is None:
            return False
        for surface in SURFACES:
            if not cfg["surfaces_enabled"].get(surface, True):
                continue
            if _lock_is_live(ctx.key, surface, cfg["lock_ttl_minutes"]):
                return True
        # also honour a recently-written BUILDING state
        state = _load_state(ctx)
        for surface in SURFACES:
            if state.get("surfaces", {}).get(surface, {}).get("state") == BUILDING:
                if _lock_is_live(ctx.key, surface, cfg["lock_ttl_minutes"]):
                    return True
        return False
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv else "session-start"
    cfg = _load_config()

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    if mode == "build":
        parser = argparse.ArgumentParser(prog="index-lifecycle build")
        parser.add_argument("--root", required=True)
        parser.add_argument("--key", required=True)
        parser.add_argument("--surfaces", default="")
        parser.add_argument("--incremental", action="store_true")
        parser.add_argument("--journal", default="")
        try:
            args = parser.parse_args(argv[1:])
        except SystemExit:
            return 0
        return mode_build(args, cfg)

    payload = _read_payload()
    if mode == "session-start":
        return mode_session_start(payload, cfg)
    if mode == "post-write":
        return mode_post_write(payload, cfg)
    if mode == "tick":
        return mode_tick(payload, cfg)
    if mode == "flush":
        return mode_flush(payload, cfg)
    if mode == "session-end":
        return mode_session_end(payload, cfg)

    print("{}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - the hook must never crash a session
        try:
            print("{}")
        except Exception:
            pass
        sys.exit(0)
