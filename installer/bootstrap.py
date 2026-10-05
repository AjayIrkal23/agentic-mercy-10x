#!/usr/bin/env python3
"""bootstrap.py — auto-detect ~/.claude, auto-relocate into it, launch the UI.

The workbench only works when it lives at ``~/.claude`` (that is the only path
Claude Code reads). Users clone it *anywhere* (e.g. ``~/agentic-mercy-10x``), so
the single entry point does everything with **zero** user action:

  1. detect the canonical target (``$CLAUDE_CONFIG_DIR`` or ``~/.claude``);
  2. if we are running from anywhere else, MERGE-COPY the whole bundle into the
     target (overwriting bundle files, never deleting the user's runtime data —
     projects/, todos/, memory/, state/, settings.user.json), then RE-LAUNCH from
     the target so every engine root resolves to ``~/.claude``;
  3. launch the visual installer, which auto-runs the self-heal loop to 100%.

No CLI verbs, no prompts, no folder picker — fully automatic. The only flag is
``--ci``: the same flow headless in the console. Network steps and everything outside
the checkout (deps, MCP, plugins, lean-ctx / jcodemunch config) are planned (WOULD-*);
local repo steps really run (render settings.json, generators, skill validator). It is
NOT read-only: the read-only plan is ``python3 installer/deps.py``. Pure stdlib;
Windows + POSIX.
"""
from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_SRC_ROOT / "installer"), str(_SRC_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402

_GUARD = "AGENTIC_MERCY_RELOCATED"          # re-exec guard — never relocate twice
_SKIP_COPY_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}
# sentinel bundle items that prove a complete install is present at the target.
_BUNDLE_ITEMS = ("skills", "hooks", "agents", "rules", "scripts", "installer",
                 "settings.template.json", "install-ui.py")
# console only, never the web UI. --ci plans every network step (WOULD-*); --headless is the
# real install without the browser (fresh servers / containers / ssh).
_HEADLESS_FLAGS = {"--ci", "--headless"}


def canonical_target() -> Path:
    """The one true ~/.claude — honours CLAUDE_CONFIG_DIR when set."""
    return plat.claude_dir()


def missing_items(target: Path) -> list[str]:
    """Bundle sentinels absent at the target (empty list == looks installed)."""
    target = Path(target)
    return [n for n in _BUNDLE_ITEMS if not (target / n).exists()]


def _needs_relocate(src: Path, target: Path) -> bool:
    try:
        src, target = src.resolve(), target.resolve()
    except OSError:
        return True
    if src == target:
        return False                        # already AT ~/.claude (dev machine)
    if target in src.parents:
        return False                        # clone lives INSIDE ~/.claude — run in place
    return True


PRE_INSTALL = ".pre-install"


def _put(src: Path, dst: Path, kept: list | None) -> None:
    """Copy src over dst. With ``kept`` (a list: the FIRST install), a dst that already exists with
    DIFFERENT bytes (the user's own CLAUDE.md, a same-named skill or agent) is first kept once as
    ``<name>.pre-install``; an existing kept copy is never overwritten. ``kept=None`` (a re-run on
    a complete install) overwrites plainly: the differences are files the installer regenerated."""
    if kept is not None and dst.is_file() and not dst.is_symlink():
        keep = dst.with_name(dst.name + PRE_INSTALL)
        if not keep.exists() and not filecmp.cmp(src, dst, shallow=False):
            shutil.copy2(dst, keep)
            kept.append(dst.name)
    shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path, kept: list | None = None) -> int:
    """Merge-copy src -> dst, overwriting collisions (on the first install the user's differing
    files are kept as ``*.pre-install`` first), keeping dst extras."""
    n = 0
    for dp, dns, fns in os.walk(src):
        dns[:] = [d for d in dns if d not in _SKIP_COPY_DIRS]
        rel = Path(dp).relative_to(src)
        out = dst / rel
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        for fn in fns:
            try:
                _put(Path(dp) / fn, out / fn, kept)
                n += 1
            except OSError:
                pass
    return n


def relocate(src: Path, target: Path, emit=None) -> int:
    """Move the bundle's content into ~/.claude, replacing bundle files in place.

    User runtime dirs already at the target are preserved (merge, never wipe).
    On the FIRST install (bundle items missing at the target) a differing file of the user's own
    is kept once as ``<name>.pre-install`` (one summary line is printed). Returns the number of
    files copied."""
    src, target = Path(src), Path(target)
    kept: list[str] | None = [] if missing_items(target) else None
    if emit is None:
        def emit(kind, name, status):  # noqa: E731
            print(f"  [{kind}] {name}: {status}")
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    total = 0
    for item in sorted(src.iterdir()):
        if item.name in _SKIP_COPY_DIRS:
            continue
        try:
            if item.resolve() == target.resolve():   # overlap guard
                continue
        except OSError:
            pass
        dest = target / item.name
        if item.is_dir():
            total += _copy_tree(item, dest, kept)
        else:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                _put(item, dest, kept)
                total += 1
            except OSError:
                pass
    emit("relocate", str(target), f"OK — {total} files replaced into ~/.claude")
    if kept:
        print(f"  Kept {len(kept)} of your files as *{PRE_INSTALL} next to the originals "
              f"(e.g. {', '.join(sorted(set(kept))[:3])}).")
    return total


def _launch_ui() -> int:
    """Import and run the visual installer from wherever we currently are."""
    for _p in (str(Path(__file__).resolve().parents[1] / "installer"),
               str(Path(__file__).resolve().parents[1] / "hooks")):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    import ui  # type: ignore
    return ui.main([])


def _run_headless(ci: bool) -> int:
    """Console self-heal (no web server). ``--ci`` = plan every network step."""
    for _p in (str(Path(__file__).resolve().parents[1] / "installer"),
               str(Path(__file__).resolve().parents[1] / "hooks")):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    import selfheal  # type: ignore
    res = selfheal.self_heal(canonical_target(), ci=ci)
    warns = [r for r in res["rows"] if r[1] == "WARN"]
    print(f"\ninstall: {'SUCCESS' if res['success'] else 'INCOMPLETE'} in {res['rounds']} round(s); "
          f"{len(res['fails'])} FAIL {sorted(res['fails'])}, {len(warns)} WARN")
    if res.get("todo"):
        print("\n" + "\n".join(res["todo"]))
        if not ci:
            print("  Open a new terminal (or `export PATH=\"$HOME/.local/bin:$PATH\"`) so `claude` is on PATH.")
    return 0 if res["success"] else 1


def main(argv=None) -> int:
    argv = [] if argv is None else list(argv)
    if any(a not in _HEADLESS_FLAGS for a in argv):
        print(
            "install.py takes no verbs; run it without arguments (visual installer), with "
            "--headless (real install in the console) or --ci (network steps planned, local "
            "repo steps run). Read-only plan: "
            "python3 installer/deps.py; health check: python3 installer/doctor.py; "
            "status: python3 check.py.",
            file=sys.stderr,
        )
        return 2
    headless = bool(argv)

    target = canonical_target()

    # Step 1 (user's flow): check whether all bundle items already exist at ~/.claude.
    missing = missing_items(target)

    if _needs_relocate(_SRC_ROOT, target) and os.environ.get(_GUARD) != "1":
        print(f"\n  Detected clone at {_SRC_ROOT}")
        if missing:
            print(f"  {len(missing)} bundle item(s) missing at {target}: {', '.join(missing[:6])}")
        print(f"  Auto-installing into {target} …")
        # Restore the clone's worktree to pristine committed bytes FIRST, so a
        # Windows autocrlf-mangled checkout is fixed before we copy — the copied
        # bundle then lands byte-correct and R10 passes with no guessing.
        # Guard: NEVER on a dirty clone (`checkout -- .` would discard edits);
        # git_restore_worktree also refuses its own repo, so this may be a no-op.
        try:
            import selfheal  # type: ignore
            if not (_SRC_ROOT / ".git").exists():
                pass  # not a git checkout (tarball / copy) — nothing to restore
            elif not selfheal.worktree_is_clean(_SRC_ROOT):
                print("  Clone has uncommitted changes — skipping git restore.")
            elif selfheal.git_restore_worktree(_SRC_ROOT):
                print("  Restored pristine line endings in the clone (git).")
        except Exception:  # noqa: BLE001
            pass
        relocate(_SRC_ROOT, target)
        # re-launch FROM the target so deps/doctor/render/selfheal all resolve
        # their _ROOT to ~/.claude and operate on the real install, not the clone.
        os.environ[_GUARD] = "1"
        if target.resolve() != (Path.home() / ".claude").resolve():
            os.environ["CLAUDE_CONFIG_DIR"] = str(target)  # default target: leave unset
        entry = target / "install-ui.py"
        if entry.exists():
            proc = subprocess.Popen([sys.executable, str(entry), *argv], env=os.environ)
            proc.wait()
            return proc.returncode
        # extreme fallback: entry didn't copy — run in place.

    return _run_headless(ci="--ci" in argv) if headless else _launch_ui()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
