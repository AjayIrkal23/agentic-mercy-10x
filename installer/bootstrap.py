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

No CLI verbs, no prompts, no folder picker — UI only, fully automatic. Pure
stdlib; Windows + POSIX.
"""
from __future__ import annotations

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
_BUNDLE_ITEMS = ("skills", "hooks", "commands", "rules", "scripts", "installer",
                 "settings.template.json", "install-ui.py")


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


def _copy_tree(src: Path, dst: Path) -> int:
    """Merge-copy src -> dst, overwriting collisions, keeping dst extras."""
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
                shutil.copy2(Path(dp) / fn, out / fn)
                n += 1
            except OSError:
                pass
    return n


def relocate(src: Path, target: Path, emit=None) -> int:
    """Move the bundle's content into ~/.claude, replacing bundle files in place.

    User runtime dirs already at the target are preserved (merge, never wipe).
    Returns the number of files copied."""
    src, target = Path(src), Path(target)
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
            total += _copy_tree(item, dest)
        else:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
                total += 1
            except OSError:
                pass
    emit("relocate", str(target), f"OK — {total} files replaced into ~/.claude")
    return total


def _launch_ui() -> int:
    """Import and run the visual installer from wherever we currently are."""
    for _p in (str(Path(__file__).resolve().parents[1] / "installer"),
               str(Path(__file__).resolve().parents[1] / "hooks")):
        if _p not in sys.path:
            sys.path.insert(0, _p)
    import ui  # type: ignore
    return ui.main([])


def main(argv=None) -> int:
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
        try:
            import selfheal  # type: ignore
            if selfheal.git_restore_worktree(_SRC_ROOT):
                print("  Restored pristine line endings in the clone (git).")
        except Exception:  # noqa: BLE001
            pass
        relocate(_SRC_ROOT, target)
        # re-launch FROM the target so deps/doctor/render/selfheal all resolve
        # their _ROOT to ~/.claude and operate on the real install, not the clone.
        os.environ[_GUARD] = "1"
        os.environ["CLAUDE_CONFIG_DIR"] = str(target)
        entry = target / "install-ui.py"
        if entry.exists():
            proc = subprocess.Popen([sys.executable, str(entry)], env=os.environ)
            proc.wait()
            return proc.returncode
        # extreme fallback: entry didn't copy — run the UI in place.

    return _launch_ui()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
