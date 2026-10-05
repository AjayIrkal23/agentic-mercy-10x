#!/usr/bin/env python3
"""bootstrap.py — auto-detect ~/.claude, auto-relocate into it, launch the UI.

The workbench only works when it lives at ``~/.claude`` (that is the only path
Claude Code reads). Users clone it *anywhere* (e.g. ``~/agentic-mercy-10x``), so
the single entry point does everything with **zero** user action:

  1. detect the canonical target (``$CLAUDE_CONFIG_DIR`` or ``~/.claude``);
  2. if we are running from anywhere else, MERGE-COPY the whole bundle into the
     target (overwriting bundle files, never deleting the user's runtime data —
     projects/, todos/, memory/, state/, settings.user.json), then RE-LAUNCH from
     the target so every engine root resolves to ``~/.claude`` (the copy itself
     lives in ``relocation.py``: files it could not copy are listed, and a failure
     under a bundle item stops the install);
  3. launch the visual installer, which auto-runs the self-heal loop to 100%.

No CLI verbs, no prompts, no folder picker — fully automatic. The only flags are
``--headless`` (the real install in the console) and ``--ci``: the same flow headless
in the console. Network steps and everything outside
the checkout (deps, MCP, plugins, lean-ctx / jcodemunch config) are planned (WOULD-*);
local repo steps really run (render settings.json, generators, skill validator). It is
NOT read-only: the read-only plan is ``python3 installer/deps.py``. Pure stdlib;
Windows + POSIX.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_SRC_ROOT / "installer"), str(_SRC_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402
from relocation import _BUNDLE_ITEMS, fatal_failures, missing_items, relocate  # noqa: E402,F401  (_BUNDLE_ITEMS: tests)
from winutil import which  # noqa: E402  (never a binary from the working directory)

_GUARD = "AGENTIC_MERCY_RELOCATED"          # re-exec guard — never relocate twice
# console only, never the web UI. --ci plans every network step (WOULD-*); --headless is the
# real install without the browser (fresh servers / containers / ssh).
_HEADLESS_FLAGS = {"--ci", "--headless"}


def canonical_target() -> Path:
    """The one true ~/.claude — honours CLAUDE_CONFIG_DIR when set."""
    return plat.claude_dir()


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
    # --ci SKIPs the machine rows and plans every network step: "SUCCESS" there read like a real install (A6v2-03)
    head = ("install (plan only): " + ("OK" if res["success"] else "INCOMPLETE")) if ci else (
        "install: " + ("SUCCESS" if res["success"] else "INCOMPLETE"))
    print(f"\n{head} in {res['rounds']} round(s); {len(res['fails'])} FAIL {sorted(res['fails'])}, "
          f"{len(warns)} WARN" + ("; nothing was installed" if ci else ""))
    if res.get("todo"):
        text = "\n".join(res["todo"])
        print("\n" + text)
        if not ci and _path_hint() not in text:  # the Windows checklist already carries its line
            print("  " + _path_hint())
    return 0 if res["success"] else 1


def _path_hint() -> str:
    """How to get the freshly installed tools on PATH: a new terminal on Windows, the export on POSIX."""
    import ostools  # type: ignore
    return ostools.path_hint()


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
            elif not which("git"):
                print("  git not found — skipping git restore (nothing to repair: .gitattributes keeps LF).")
            elif not selfheal.worktree_is_clean(_SRC_ROOT):
                print("  Clone has uncommitted changes — skipping git restore.")
            elif selfheal.git_restore_worktree(_SRC_ROOT):
                print("  Restored pristine line endings in the clone (git).")
        except Exception:  # noqa: BLE001
            pass
        failed: list = []
        relocate(_SRC_ROOT, target, failed=failed)
        fatal = fatal_failures(failed)
        if fatal:  # a locked or unwritable bundle file: running on would install a mixed old/new bundle
            print(f"\n  Could not copy {len(fatal)} bundle file(s), e.g. {fatal[0][0]}. Close Claude Code and any "
                  f"program using {target}, then run the installer again.")
            return 1
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
