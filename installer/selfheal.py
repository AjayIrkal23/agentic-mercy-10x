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

  · PRIMARY  ``git checkout -- .`` (autocrlf off) restores the EXACT committed
             bytes from the git object store — correct for mixed LF/CRLF dirs.
  · FALLBACK per drifted locked dir: normalize CRLF->LF, and keep the change ONLY
             if the dir hash then matches its baseline; otherwise REVERT. It can
             never make a dir worse; it fixes the common all-LF-baseline drift.

MCP/plugin registration is attempted automatically (the platform.run Windows shell
fallback makes the ``claude`` CLI runnable); when the CLI is genuinely absent it
stays a non-blocking WARN — success is 0 doctor FAILs, never gated on
network-dependent registration. Pure stdlib.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402


# --------------------------------------------------------------------------- #
# R10 line-ending repair (the "47 HARD" fix)
# --------------------------------------------------------------------------- #
def git_restore_worktree(root: Path) -> bool:
    """PRIMARY R10 fix: restore the working tree to its pristine committed bytes.

    Uses the git object store, so files land exactly as committed (correct for
    dirs that mix LF and CRLF). No-op (returns False) when the target is not a
    git checkout or git is unavailable."""
    root = Path(root)
    if not (root / ".git").exists() or not shutil.which("git"):
        return False
    plat.run(["git", "-C", str(root), "config", "core.autocrlf", "false"], timeout=30)
    plat.run(["git", "-C", str(root), "config", "core.eol", "lf"], timeout=30)
    cp = plat.run(["git", "-C", str(root), "checkout", "--", "."], timeout=180)
    return cp.returncode == 0


def _norm_bytes(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def repair_r10_drift(target: Path) -> int:
    """FALLBACK R10 fix (safe): for each locked content-hash skill dir whose hash
    currently mismatches its baseline, normalize CRLF->LF and KEEP it only if the
    dir then matches the baseline; otherwise revert. Never corrupts a dir. Returns
    the number of dirs healed."""
    try:
        import json
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


def _heal_line_endings(target: Path, emit) -> None:
    if git_restore_worktree(target):
        emit("repair", "git-restore", "OK (pristine committed bytes)")
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
        st.write_bytes(text.encode("utf-8"))  # LF bytes == the equivalence baseline
        emit("settings", "settings.json", "OK(rendered)")
    except Exception as exc:  # noqa: BLE001
        emit("settings", "settings.json", f"WARN({exc})")


def _doctor_rows():
    import importlib
    import doctor  # type: ignore
    importlib.reload(doctor)  # pick up freshly-written files each round
    return doctor.run_doctor()


def _repair(target: Path, failed: set, env, emit) -> None:
    names = " ".join(failed).lower()
    if "validator" in names or "r9" in names or "r10" in names:
        _heal_line_endings(target, emit)
        _run_script(target, "hooks/build-skills-index.py", emit)
        _run_script(target, "hooks/build-trigger-floor.py", emit)
    if "render" in names or "interpreter" in names:
        _ensure_settings(target, env, emit, force=True)


# --------------------------------------------------------------------------- #
# the loop
# --------------------------------------------------------------------------- #
def self_heal(target, emit=None, *, max_rounds: int = 4) -> dict:
    """Install + repair until 0 doctor FAILs (or max_rounds). Returns
    {success, rounds, fails, rows}. ``emit(kind, name, status)`` streams progress."""
    target = Path(target)
    if emit is None:
        def emit(kind, name, status):  # noqa: E731 - default console emitter
            print(f"  [{kind}] {name:28s} {status}")

    os.environ["CLAUDE_CONFIG_DIR"] = str(target)
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
            for name, s in _deps.install_deps(env):
                emit("dep", name, s)
            for name, s in _deps.register_mcps(env):
                emit("mcp", name, s)
            for name, s in _deps.install_plugins(env):
                emit("plugin", name, s)
            _ensure_settings(target, env, emit)
            for name, s in _deps.run_post_steps(env):
                emit("post", name, s)
            _validate_fix(target, emit)

        # 2. health check — the authority on "done".
        rows = _doctor_rows()
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
    res = self_heal(target)
    warns = [r for r in res["rows"] if r[1] == "WARN"]
    print(f"\nself-heal: {'SUCCESS' if res['success'] else 'INCOMPLETE'} "
          f"in {res['rounds']} round(s); {len(res['fails'])} FAIL, {len(warns)} WARN")
    return 0 if res["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
