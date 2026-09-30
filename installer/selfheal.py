#!/usr/bin/env python3
"""selfheal.py — the fully-automatic install → repair → re-check loop.

The visual installer calls :func:`self_heal` on a target ``~/.claude``. It runs
the real install pass (deps / MCP / plugins / settings / post-steps) ONCE, then
repeatedly repairs and re-checks with the doctor until there are **zero FAILs**
(the "100%" state) or a round budget is exhausted. No user interaction anywhere.

The dominant Windows failure mode it heals is R10 (the "47 HARD"): a Windows
``git clone`` that ignores ``.gitattributes -text`` rewrites LF->CRLF, and
``dir_content_hash`` reads raw BYTES, so every locked-skill hash drifts. The
committed baseline legitimately contains BOTH LF and CRLF files, so a blind
"normalize everything to LF" is wrong — it would corrupt the baseline-CRLF files.
Two repairs, primary + safe fallback:

  · PRIMARY  ``git -c core.autocrlf=false checkout -- <path>`` restores the EXACT
             committed bytes from the git object store — correct for mixed
             LF/CRLF dirs. REFUSED on a dirty tree and on this repo itself
             (``_ROOT``); the heal loop applies it only per CLEAN locked skill dir.
  · FALLBACK per drifted locked dir: normalize CRLF->LF, and keep the change ONLY
             if the dir hash then matches its baseline; otherwise REVERT. It can
             never make a dir worse; it fixes the common all-LF-baseline drift.

MCP/plugin registration is attempted automatically (the platform.run Windows shell
fallback makes the ``claude`` CLI runnable); when the CLI is genuinely absent it
stays a non-blocking WARN — success is 0 doctor FAILs, never gated on
network-dependent registration. Pure stdlib.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402


# --------------------------------------------------------------------------- #
# R10 line-ending repair (the "47 HARD" fix)
# --------------------------------------------------------------------------- #
def _git_clean(root: Path, pathspec: str) -> bool:
    """True iff ``git status --porcelain -- <pathspec>`` ran and printed nothing."""
    st = plat.run(["git", "-C", str(root), "status", "--porcelain", "--", pathspec], timeout=60)
    return st.returncode == 0 and not (st.stdout or "").strip()


def _git_restore_clean(root: Path, pathspec: str) -> bool:
    """``checkout -- <pathspec>`` with the exact committed bytes, ONLY when that
    pathspec is clean — a checkout over local edits would discard them."""
    if not _git_clean(root, pathspec):
        return False
    cp = plat.run(["git", "-C", str(root), "-c", "core.autocrlf=false",
                   "checkout", "--", pathspec], timeout=180)
    return cp.returncode == 0


def worktree_is_clean(root: Path) -> bool:
    """True iff ``root`` is a git checkout with no uncommitted change at all."""
    root = Path(root)
    return (root / ".git").exists() and bool(shutil.which("git")) and _git_clean(root, ".")


def git_restore_worktree(root: Path) -> bool:
    """PRIMARY R10 fix: restore a CLEAN clone to its pristine committed bytes.

    Uses the git object store, so files land exactly as committed (correct for
    dirs that mix LF and CRLF). Returns False (no-op) when the target is not a
    git checkout, git is unavailable, the tree has ANY uncommitted change (a
    ``checkout -- .`` would discard it), or ``root`` is this very repo
    (``_ROOT``, src == target) — the live workbench is never reset."""
    root = Path(root)
    if not (root / ".git").exists() or not shutil.which("git"):
        return False
    if root.resolve() == _ROOT:
        return False
    return _git_restore_clean(root, ".")


def _norm_bytes(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def repair_r10_drift(target: Path) -> int:
    """FALLBACK R10 fix (safe): for each locked content-hash skill dir whose hash
    currently mismatches its baseline, normalize CRLF->LF and KEEP it only if the
    dir then matches the baseline; otherwise revert. Never corrupts a dir. Returns
    the number of dirs healed."""
    try:
        import skills_lib as sl  # type: ignore
    except Exception:  # noqa: BLE001
        return 0
    prov_path = Path(target) / "hooks" / "skills-provenance.json"
    try:
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return 0
    healed = 0
    for name, meta in prov.items():
        if name.startswith("_") or not isinstance(meta, dict):
            continue
        if meta.get("hashBasis") != "content-hash":
            continue
        d = sl.SKILLS_DIR / name
        baseline = meta.get("baselineHash")
        if not d.is_dir() or not baseline:
            continue
        if sl.dir_content_hash(d) == baseline:
            continue  # already correct
        snap: dict[Path, bytes] = {}
        for fp in d.rglob("*"):
            if not fp.is_file():
                continue
            try:
                b = fp.read_bytes()
            except OSError:
                continue
            if b"\x00" in b or b"\r" not in b:
                continue
            snap[fp] = b
            try:
                fp.write_bytes(_norm_bytes(b))
            except OSError:
                pass
        if sl.dir_content_hash(d) == baseline:
            healed += 1
        else:
            for fp, b in snap.items():  # normalize didn't match baseline — revert
                try:
                    fp.write_bytes(b)
                except OSError:
                    pass
    return healed


def _locked_skill_names(target: Path) -> list[str]:
    """Names of the locked (vendored) skills: ``hooks/skills-sources.json`` when
    present (WP-9), else the legacy ``hooks/skills-provenance.json`` keys."""
    for rel in ("hooks/skills-sources.json", "hooks/skills-provenance.json"):
        try:
            data = json.loads((Path(target) / rel).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(data, dict):
            return [n for n, m in data.items() if not n.startswith("_") and isinstance(m, dict)]
    return []


def _heal_line_endings(target: Path, emit) -> None:
    # Never `checkout -- .` here: restore ONLY locked skill dirs that are clean,
    # one pathspec at a time, so no local edit anywhere can be discarded.
    target = Path(target)
    if (target / ".git").exists() and shutil.which("git"):
        healed = [n for n in _locked_skill_names(target)
                  if (target / "skills" / n).is_dir() and _git_restore_clean(target, f"skills/{n}")]
        if healed:
            emit("repair", "git-restore", f"OK ({len(healed)} clean locked skill dirs)")
    n = repair_r10_drift(target)
    if n:
        emit("repair", "line-endings", f"OK ({n} skill dirs healed)")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _run_script(target: Path, rel: str, emit, *args: str) -> None:
    script = Path(target) / rel
    if not script.exists():
        emit("repair", rel, "SKIP(absent)")
        return
    cp = plat.run([plat.python_exe(), str(script), *args], timeout=300)
    emit("repair", Path(rel).name, "OK" if cp.returncode == 0 else f"WARN(rc={cp.returncode})")


def _validate_fix(target: Path, emit) -> None:
    # --fix only rewrites USER skills (R1/R4/R8); locked skills are never touched,
    # so it cannot drift an R10 baseline.
    _run_script(target, "scripts/validate_skills.py", emit, "--fix")


def _ensure_settings(target: Path, env, emit, *, force: bool = False) -> None:
    st = Path(target) / "settings.json"
    if st.exists() and not force:
        emit("settings", "settings.json", "PRESENT (kept)")
        return
    try:
        import render  # type: ignore
        text = render.render(subs=getattr(env, "tokens", None))
        if st.exists():  # keep the user's Claude-managed keys (theme, tui, voice …)
            text = render.carry_managed(text, st)
        st.write_bytes(text.encode("utf-8"))  # LF bytes == the equivalence baseline
        emit("settings", "settings.json", "OK(rendered)")
    except Exception as exc:  # noqa: BLE001
        emit("settings", "settings.json", f"WARN({exc})")


def _doctor_rows(ci: bool = False):
    import importlib
    import doctor  # type: ignore
    importlib.reload(doctor)  # pick up freshly-written files each round
    return doctor.run_doctor(ci=ci)


def pin_config_dir(target) -> None:
    """Export CLAUDE_CONFIG_DIR only for a NON-default target. Setting it to the
    default ~/.claude would make the claude CLI use ~/.claude/.claude.json instead
    of ~/.claude.json and register every MCP into the wrong file."""
    if Path(target).resolve() != (Path.home() / ".claude").resolve():
        os.environ["CLAUDE_CONFIG_DIR"] = str(target)
    else:
        os.environ.pop("CLAUDE_CONFIG_DIR", None)


def _repair(target: Path, failed: set, env, emit) -> None:
    names = " ".join(failed).lower()
    if "generated" in names:
        _run_script(target, "hooks/gen-invoke-skills.py", emit)
        _run_script(target, "hooks/gen-agent-skill-blocks.py", emit)
    if "lean-ctx" in names:
        import deps as _deps  # type: ignore
        emit("repair", *_deps.configure_lean_ctx())
    if "jcodemunch" in names:
        import jcodemunch_config as _jc  # type: ignore
        emit("repair", *_jc.configure())
    if "validator" in names or "r9" in names or "r10" in names:
        _heal_line_endings(target, emit)
        _run_script(target, "hooks/build-skills-index.py", emit)
        _run_script(target, "hooks/build-trigger-floor.py", emit)
    if "render" in names or "interpreter" in names:
        st = Path(target) / "settings.json"
        if st.exists():  # never force-rerender without a recoverable copy (*.bak* is gitignored)
            bak = st.with_name(f"settings.json.bak-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}")
            shutil.copy2(st, bak)
            emit("settings", bak.name, "OK(backup)")
        _ensure_settings(target, env, emit, force=True)


# --------------------------------------------------------------------------- #
# the loop
# --------------------------------------------------------------------------- #
def self_heal(target, emit=None, *, max_rounds: int = 4, ci: bool = False) -> dict:
    """Install + repair until 0 doctor FAILs (or max_rounds). Returns
    {success, rounds, fails, rows}. ``emit(kind, name, status)`` streams progress.
    ``ci=True`` = network-free plan: deps / MCP / plugin / network post-steps are
    only reported (WOULD-*); local steps (render, lean-ctx config, generators,
    validator, doctor --ci) really run."""
    target = Path(target)
    if emit is None:
        def emit(kind, name, status):  # noqa: E731 - default console emitter
            print(f"  [{kind}] {name:28s} {status}")

    pin_config_dir(target)
    import detect as _detect   # type: ignore
    import deps as _deps       # type: ignore

    rows: list = []
    fails: set = set()
    for rnd in range(1, max_rounds + 1):
        emit("round", f"round {rnd}/{max_rounds}", "START")

        # 0. heal line endings FIRST so the post-step validator + R10 see the
        #    exact committed bytes (git restore, then the safe per-dir fallback).
        _heal_line_endings(target, emit)

        env = _detect.detect()

        # 1. heavy install pass — ONCE (round 1). Idempotent; later rounds skip it.
        if rnd == 1:
            for name, s in _deps.check_prereqs(env):
                emit("prereq", name, s)
            for name, s in _deps.install_deps(env, ci=ci, dry_run=ci):
                emit("dep", name, s)
            for name, s in _deps.register_mcps(env, ci=ci, dry_run=ci):
                emit("mcp", name, s)
            for name, s in _deps.reconcile_mcp_env(dry_run=ci):
                emit("mcp-env", name, s)
            for name, s in _deps.install_plugins(env, ci=ci, dry_run=ci):
                emit("plugin", name, s)
            emit("config", *_deps.configure_lean_ctx())
            import jcodemunch_config as _jc  # type: ignore
            emit("config", *_jc.configure(dry_run=ci))
            _ensure_settings(target, env, emit)
            for name, s in _deps.run_post_steps(env, ci=ci):
                emit("post", name, s)
            _validate_fix(target, emit)

        # 2. health check — the authority on "done".
        rows = _doctor_rows(ci)
        fails = {r[0] for r in rows if r[1] == "FAIL"}
        for name, st, det in rows:
            emit("doctor", name, f"{st}: {det}")

        if not fails:
            emit("done", f"round {rnd}", "PASS — 0 FAIL")
            return {"success": True, "rounds": rnd, "fails": [], "rows": rows}

        emit("repair", f"round {rnd}", f"{len(fails)} FAIL -> repairing: {sorted(fails)}")
        _repair(target, fails, env, emit)

    return {"success": False, "rounds": max_rounds, "fails": sorted(fails), "rows": rows}


def main(argv=None) -> int:
    target = plat.claude_dir()
    res = self_heal(target, ci="--ci" in (argv or []))
    warns = [r for r in res["rows"] if r[1] == "WARN"]
    print(f"\nself-heal: {'SUCCESS' if res['success'] else 'INCOMPLETE'} "
          f"in {res['rounds']} round(s); {len(res['fails'])} FAIL, {len(warns)} WARN")
    return 0 if res["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
