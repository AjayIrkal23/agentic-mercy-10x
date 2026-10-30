#!/usr/bin/env python3
"""plan-tier-detect.py — SessionStart exec link (crit_exempt) and installer post_step `plan-tier`.

Detects the Claude plan tier (lib/plan_tier.detect: the only credentials reader in the workbench),
writes state/plan-tier.json, sets a one-line notice when the tier changed (session_notices renders it),
logs {tier, source, changed} to hook telemetry (never a token), and on a tier change re-renders settings
through installer/render.py (detached; falls back to scripts/build_workflows.py when render.py is absent),
so model / fallbackModel / CLAUDE_CODE_SUBAGENT_MODEL follow the tier. stdin is never read (the dispatcher's
payload carries nothing it needs). stdout: one JSON summary unless --quiet. Exit 0 always.

CLI: --home DIR (fake home: tests) --state FILE (state path override) --root DIR (claude dir override
for the render / builder lookup) --quiet.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

try:
    from lib import platform as plat
except Exception:  # noqa: BLE001
    plat = None  # type: ignore


def _spawn(cmd: list) -> None:
    """Fire-and-forget (module-level so tests can record it)."""
    if plat is not None:
        plat.spawn_detached(cmd)


def main(argv: list | None = None) -> int:
    try:
        ap = argparse.ArgumentParser(add_help=False)
        ap.add_argument("--home")
        ap.add_argument("--state")
        ap.add_argument("--root")
        ap.add_argument("--quiet", action="store_true")
        args, _ = ap.parse_known_args(argv)
        # stdin (the SessionStart payload) is never read: an open, never-closed pipe would block a hand
        # run, and dispatch's subprocess.run(input=...) / spawn_worker already tolerate an unread stdin.
        from lib import plan_tier

        d = plan_tier.detect(Path(args.home) if args.home else None)
        r = plan_tier.update_state(d, Path(args.state) if args.state else None)
        try:
            from lib import hook_telemetry

            hook_telemetry.record("session-start", "plan-tier-detect", tier=d["tier"], source=d["source"],
                                  changed=r["changed"], ok=r["ok"])
        except Exception:  # noqa: BLE001 - telemetry is best-effort
            pass
        # an isolated test state (CLAUDE_HOOK_STATE_DIR) must never drive the live builder; --root opts in
        if r["changed"] and plat is not None and (args.root or not os.environ.get("CLAUDE_HOOK_STATE_DIR")):
            try:
                root = Path(args.root) if args.root else plat.claude_dir()
                render = root / "installer" / "render.py"
                builder = root / "scripts" / "build_workflows.py"
                if render.is_file():
                    _spawn([plat.python_exe(), str(render)])   # settings + every post-step (build-workflows among them)
                elif builder.is_file():
                    _spawn([plat.python_exe(), str(builder)])
            except Exception:  # noqa: BLE001
                pass
        if not args.quiet:
            print(json.dumps({"tier": d["tier"], "source": d["source"], "changed": r["changed"]}))
        return 0
    except Exception:  # noqa: BLE001 - never fail a session start
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
