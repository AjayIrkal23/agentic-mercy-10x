#!/usr/bin/env python3
"""flip-router.py — one-command cutover / revert for the prompt router (P1-T9).

Holds BOTH UserPromptSubmit stacks and atomically swaps the ``UserPromptSubmit``
section of ``settings.json`` between them, one command, no other edits
(Charter §2 — 30-day one-flip revert):

  --router     install the router UserPromptSubmit stack
               (prompt_router/router.py + lean-ctx hook observe).
  --status     print which stack is currently installed.

  RETIRED 2026-07-14: --snapshot / --legacy (UPS flip-back) are gone — the legacy
  injector stack was deleted. Full recovery is via git (pre-100x / pre-legacy-retirement).

Safety:
  * ``--settings <path>`` targets an alternate file (used by tests + dry runs);
    default is ~/.claude/settings.json.
  * ``--dry-run`` prints the would-be settings.json without writing.
  * Every write is atomic (temp + os.replace) and the result is re-parsed to
    prove it is valid JSON before the swap is considered done.
  * Legacy injector FILES are never touched — they stay on disk, runnable, for
    the full 30-day window; only the settings.json registration flips.

Pure Python 3 stdlib. Windows+POSIX portable (paths via ${HOME}; interpreter
resolution is P6's job — the command templates use python3/bash as the live
settings.json already does).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
_LEGACY_SNAPSHOT = _HOOKS / "legacy-prompt-stack.json"


def _default_settings() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(env).expanduser() if env else Path("~/.claude").expanduser()
    return base / "settings.json"


# The router stack: ONE process replaces the 15-injector chain (its work is done
# in-process by prompt_router). lean-ctx observe is preserved (bash-output hook).
def _router_block() -> list:
    return [
        {
            "matcher": ".*",
            "hooks": [
                {"command": "python3 ${HOME}/.claude/hooks/prompt_router/router.py",
                 "timeout": 20, "type": "command"},
                {"command": "lean-ctx hook observe", "timeout": 5, "type": "command"},
            ],
        }
    ]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, data: dict) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)  # prove validity before touching the target
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".settings-", suffix=".swap")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def snapshot(settings: Path) -> int:
    print("RETIRED 2026-07-14: the legacy UserPromptSubmit stack was deleted; there "
          "is nothing to snapshot. Recovery is via git: `git checkout pre-100x` or "
          "`git checkout pre-legacy-retirement`.", file=sys.stderr)
    return 1


def _current_mode(settings: Path) -> str:
    try:
        ups = _load_json(settings).get("hooks", {}).get("UserPromptSubmit", [])
    except (OSError, json.JSONDecodeError):
        return "unknown"
    cmds = [h.get("command", "") for b in ups for h in b.get("hooks", [])]
    if any("prompt_router/router.py" in c for c in cmds):
        return "router"
    return "legacy"


def to_router(settings: Path, dry_run: bool) -> int:
    data = _load_json(settings)
    data.setdefault("hooks", {})["UserPromptSubmit"] = _router_block()
    if dry_run:
        print(json.dumps(data["hooks"]["UserPromptSubmit"], indent=2))
        return 0
    _atomic_write_json(settings, data)
    print("flipped -> ROUTER stack (1 process). Revert via git: pre-legacy-retirement / pre-100x.")
    return 0


def to_legacy(settings: Path, dry_run: bool) -> int:
    print("RETIRED 2026-07-14: the legacy UserPromptSubmit stack has been deleted; "
          "flip-back is gone. Full recovery is via git: `git checkout pre-100x` "
          "(whole overhaul) or `pre-legacy-retirement` (this cleanup).", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    settings = _default_settings()
    dry = "--dry-run" in argv
    if "--settings" in argv:
        i = argv.index("--settings")
        if i + 1 < len(argv):
            settings = Path(argv[i + 1]).expanduser()
    if "--snapshot" in argv:
        return snapshot(settings)
    if "--router" in argv:
        return to_router(settings, dry)
    if "--legacy" in argv:
        return to_legacy(settings, dry)
    if "--status" in argv:
        print(f"UserPromptSubmit stack: {_current_mode(settings)}  ({settings})")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
