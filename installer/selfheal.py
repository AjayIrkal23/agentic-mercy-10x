#!/usr/bin/env python3
"""selfheal.py — the fully-automatic install → repair → re-check loop.

The visual installer calls :func:`self_heal` on a target ``~/.claude``. It runs
the real install pass (deps / MCP / plugins / settings / post-steps) ONCE, then
repeatedly repairs and re-checks with the doctor until there are **zero FAILs**
(the "100%" state), a round budget is exhausted, or a round's repairs changed
nothing (same FAIL set twice: more rounds cannot help). No user interaction.

The dominant Windows failure mode it heals is R10 (the "47 HARD"): a Windows
``git clone`` that ignores ``.gitattributes -text`` rewrites LF->CRLF, and
``dir_content_hash`` reads raw BYTES, so every locked-skill hash drifts. The
committed baseline legitimately contains BOTH LF and CRLF files, so a blind
"normalize everything to LF" is wrong. Two repairs, primary + safe fallback,
live in ``r10_repair.py``:

  · PRIMARY  ``git -c core.autocrlf=false checkout -- <path>`` per CLEAN locked
             skill dir (refused on a dirty tree and on this repo itself).
  · FALLBACK per drifted locked dir: normalize CRLF->LF, keep it ONLY if the dir
             hash then matches its baseline; otherwise REVERT.

Order matters: the lean-ctx config (zero injection) is written BEFORE lean-ctx is
installed or registered (audit I-03), so its first start reads it.

MCP/plugin registration is attempted automatically; when the CLI is genuinely
absent it stays a non-blocking WARN — success is 0 doctor FAILs, never gated on
network-dependent registration. Pure stdlib.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402
from settings_stale import interpreter_gone  # noqa: E402
from r10_repair import (  # noqa: E402,F401 (git_restore_worktree / worktree_is_clean: bootstrap API)
    git_restore_worktree, heal_line_endings as _heal_line_endings, worktree_is_clean)


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


def _render_sources() -> list[Path]:
    """Files settings.json is rendered from (template, overlay, manifest → mods)."""
    import render  # type: ignore
    return [Path(render._TEMPLATE), Path(render._USER), _ROOT / "installer" / "manifest.json"]


def _stale(st: Path) -> bool:
    """settings.json is older than any file it is rendered from (audit I-16: an
    existing file used to be kept forever, so a pulled template never landed), or names an
    interpreter that no longer exists."""
    mtime = st.stat().st_mtime
    return any(p.is_file() and p.stat().st_mtime > mtime for p in _render_sources()) or interpreter_gone(st)


def _ensure_settings(target: Path, env, emit, *, force: bool = False, preserved: bool = False) -> None:
    import settings_install  # type: ignore
    settings_install.ensure(target, env, emit, force=force, stale=lambda st: _stale(st), preserved=preserved)


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
    if "base-tools" in names:  # claude / node / git / uv missing: the OS's no-admin installer again
        import basetools  # type: ignore
        import deps as _deps  # type: ignore
        if not basetools.skipped():
            for name, s in basetools.ensure_base_tools(env, _deps._load_manifest()):
                emit("repair", name, s)
    if "mcp-roster" in names:  # pin drift on a pinned server (doctor_mcp FAILs it when repairable)
        import deps as _deps  # type: ignore
        for name, s in _deps.reconcile_mcp_pins():
            emit("repair", name, s)
    if "validator" in names or "r9" in names or "r10" in names:
        _heal_line_endings(target, emit)
        _run_script(target, "hooks/build-skills-index.py", emit)
        _run_script(target, "hooks/build-trigger-floor.py", emit)
    # render drift, a bare interpreter, a dead rendered interpreter (`hook-command` / `statusline`: the
    # re-render re-detects it), or a mods FAIL (mods.enabled feeds env.CLAUDE_CODE_PLUGIN_DIRS):
    # re-render; _ensure_settings backs up first. The row NAME is compared whole: `mods-runtime`
    # (a load flake or a test failure) re-renders nothing.
    if ("render" in names or "interpreter" in names or "hook-command" in names or "statusline" in names
            or "mods" in {f.lower() for f in failed}):
        _ensure_settings(target, env, emit, force=True)


def _configure_lean_ctx(deps, ci: bool) -> tuple[str, str]:
    try:  # never abort the install on a config write error — the doctor row reports it
        return deps.configure_lean_ctx(dry_run=ci)
    except Exception as exc:  # noqa: BLE001
        return "lean-ctx-config", f"WARN({type(exc).__name__}: {exc})"


def _install_pass(target: Path, env, emit, ci: bool, todo: list | None = None) -> None:
    import basetools  # type: ignore
    import deps as _deps  # type: ignore
    import jcodemunch_config as _jc  # type: ignore
    import ostools  # type: ignore
    import settings_install  # type: ignore
    settings_install.preserve_existing(target, env, emit)  # the user's settings.json, before anything runs
    manifest = _deps._load_manifest()
    env, sudo_cmd = basetools.before_deps(env, manifest, ci, emit)  # apt tools, node, claude, uv, gh
    for name, s in _deps.check_prereqs(env):
        emit("prereq", name, s)
    emit("config", *_configure_lean_ctx(_deps, ci))  # BEFORE lean-ctx is installed (I-03)
    for name, s in _deps.install_deps(env, ci=ci, dry_run=ci):
        emit("dep", name, s)
    basetools.after_deps(manifest, ci, emit)  # ollama + all-minilm / qwen2.5-coder
    if todo is not None:
        todo.extend(ostools.checklist(manifest, sudo_cmd))
    for name, s in _deps.register_mcps(env, ci=ci, dry_run=ci):
        emit("mcp", name, s)
    for name, s in _deps.reconcile_mcp_env(dry_run=ci):
        emit("mcp-env", name, s)
    for name, s in _deps.reconcile_mcp_pins(dry_run=ci):
        emit("mcp-pin", name, s)
    for name, s in _deps.install_plugins(env, ci=ci, dry_run=ci):
        emit("plugin", name, s)
    emit("config", *_jc.configure(dry_run=ci))
    _ensure_settings(target, env, emit, preserved=True)
    for name, s in _deps.run_post_steps(env, ci=ci):
        emit("post", name, s)
    _validate_fix(target, emit)


# --------------------------------------------------------------------------- #
# the loop
# --------------------------------------------------------------------------- #
def self_heal(target, emit=None, *, max_rounds: int = 4, ci: bool = False) -> dict:
    """Install + repair until 0 doctor FAILs (or max_rounds, or no progress).
    Returns {success, rounds, fails, rows}. ``emit(kind, name, status)`` streams
    progress. ``ci=True``: nothing outside the checkout is written — deps / MCP /
    plugins / network post-steps / lean-ctx + jcodemunch config are only reported
    (WOULD-*); local repo steps (render settings.json, generators, validator,
    doctor --ci) really run. The pure read-only plan is ``python3 installer/deps.py``."""
    target = Path(target)
    if emit is None:
        def emit(kind, name, status):  # noqa: E731 - default console emitter
            print(f"  [{kind}] {name:28s} {status}")

    pin_config_dir(target)
    import detect as _detect   # type: ignore

    rows: list = []
    todo: list[str] = []  # the ONE batched end-of-run message (sudo line + human-only steps)
    fails: set = set()
    prev: set | None = None
    for rnd in range(1, max_rounds + 1):
        emit("round", f"round {rnd}/{max_rounds}", "START")
        # 0. heal line endings FIRST so the validator + R10 see the committed bytes
        _heal_line_endings(target, emit)
        env = _detect.detect()
        if rnd == 1:  # 1. heavy install pass — ONCE. Idempotent; later rounds skip it.
            _install_pass(target, env, emit, ci, todo)
            env = _detect.detect()  # base tools may have put claude / npm / uv on PATH

        # 2. health check — the authority on "done".
        rows = _doctor_rows(ci)
        fails = {r[0] for r in rows if r[1] == "FAIL"}
        for name, st, det in rows:
            emit("doctor", name, f"{st}: {det}")
        if not fails:
            emit("done", f"round {rnd}", "PASS — 0 FAIL")
            return {"success": True, "rounds": rnd, "fails": [], "rows": rows, "todo": todo}
        if fails == prev:
            emit("done", f"round {rnd}", f"STOP — repairs changed nothing: {sorted(fails)}")
            return {"success": False, "rounds": rnd, "fails": sorted(fails), "rows": rows, "todo": todo}
        prev = fails
        emit("repair", f"round {rnd}", f"{len(fails)} FAIL -> repairing: {sorted(fails)}")
        _repair(target, fails, env, emit)

    return {"success": False, "rounds": max_rounds, "fails": sorted(fails), "rows": rows, "todo": todo}


def main(argv=None) -> int:
    target = plat.claude_dir()
    res = self_heal(target, ci="--ci" in (argv or []))
    warns = [r for r in res["rows"] if r[1] == "WARN"]
    print(f"\nself-heal: {'SUCCESS' if res['success'] else 'INCOMPLETE'} "
          f"in {res['rounds']} round(s); {len(res['fails'])} FAIL, {len(warns)} WARN")
    return 0 if res["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
