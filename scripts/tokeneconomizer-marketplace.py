#!/usr/bin/env python3
"""tokeneconomizer-marketplace.py — the TokenEconomizer marketplace step of the installer.

TokenEconomizer runs in place from a local clone (its documented Claude Code install: the plugin's
`lib/` links the package), so a machine without `~/CODE_FILES/TokenEconomizer` first clones the
user's fork at the branch that carries the session-history backfill, then registers the clone as a
marketplace. An existing clone is used as it is (never pulled or reset). Exit code = the failing
step's, so the installer reports WARN(rc=N).

Before that it pins `toolprune: off` in `~/.tokeneconomizer/config.json` (other keys kept):
TokenEconomizer's own default is `auto`, which writes `permissions.deny` rules into every repo's
`.claude/settings.local.json` and hides tools (2026-10-31: the owner wants every tool available).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from lib import platform as plat  # noqa: E402

FORK = "https://github.com/AjayIrkal23/TokenEconomizer.git"
BRANCH = "history-backfill"


def clone_dir() -> Path:
    return Path.home() / "CODE_FILES" / "TokenEconomizer"


def _run(argv: list[str]) -> int:
    """`plat.run`: on Windows a `claude` that is a `.cmd` shim goes through cmd.exe; never raises."""
    cp = plat.run(argv, timeout=600, stdin_devnull=True)
    if cp.returncode:
        print((cp.stderr or cp.stdout or "")[-400:], file=sys.stderr)
    return cp.returncode


def te_config() -> Path:
    return Path.home() / ".tokeneconomizer" / "config.json"


def ensure_toolprune_off() -> str:
    """Pin `toolprune: off`, keep every other key; an unreadable file is left alone (never clobbered)."""
    path = te_config()
    try:
        cfg = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        return "SKIP(unreadable config left as is)"
    if not isinstance(cfg, dict):
        return "SKIP(unexpected config shape left as is)"
    if cfg.get("toolprune") == "off":
        return "PRESENT"
    cfg["toolprune"] = "off"
    path.parent.mkdir(parents=True, exist_ok=True)
    return "SET" if plat.atomic_write(path, json.dumps(cfg, indent=2) + "\n") else "FAIL(write)"


def main(run=_run) -> int:
    print(f"tokeneconomizer toolprune off: {ensure_toolprune_off()}")
    dest = clone_dir()
    if not (dest / ".claude-plugin" / "marketplace.json").is_file():
        if dest.exists():
            print(f"{dest} exists but is not a TokenEconomizer checkout; left alone", file=sys.stderr)
            return 1
        rc = run(["git", "clone", "--branch", BRANCH, FORK, str(dest)])
        if rc:
            return rc
    return run(["claude", "plugin", "marketplace", "add", str(dest)])


if __name__ == "__main__":
    sys.exit(main())
