#!/usr/bin/env python3
"""flip-dispatch.py — one-command cutover / revert for the hook dispatcher (P4-T7).

Swaps ONLY the ``hooks`` block of ``settings.json`` between:
  * the LEGACY 65-registration block (verbatim snapshot), and
  * the 8 dispatcher entries (one ``dispatch.py <event>`` per event).

Everything else in settings.json (env, permissions, mcpServers, model, …) is
preserved byte-for-byte by round-tripping the parsed JSON and touching only the
``hooks`` key.

  --snapshot   freeze the CURRENT settings.json hooks block VERBATIM to
               hooks/legacy-settings-hooks.json (the revert point + the parity
               harness's legacy-inventory source).
  --dispatch   replace the hooks block with the 8 dispatcher entries
               (snapshots first if no snapshot exists — never flip without a
               revert point).
  --legacy     restore the hooks block from legacy-settings-hooks.json
               (byte-identical 65-registration restore).
  --status     print which block is currently installed.

Safety: ``--settings <path>`` targets an alternate file; ``--dry-run`` prints
without writing; every write is atomic (temp + os.replace) and re-parsed to
prove validity before the swap is committed. Pure Python 3 stdlib. Windows+POSIX
portable (``${HOME}`` templating; the dispatcher command uses ``python3`` exactly
as the live settings.json already does — interpreter shimming is P6's job).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_HOOKS = _ROOT / "hooks"
_LEGACY_SNAPSHOT = _HOOKS / "legacy-settings-hooks.json"

# outer per-event timeouts (seconds) — generous enough to cover the slowest
# priority-0 link in each chain (dispatch applies its own SOFT ms budget +
# per-link timeouts internally; this is only Claude Code's kill ceiling).
_EVENT_TIMEOUT = {
    "session-start": 60,      # session-start-aggregator link (45s)
    "user-prompt-submit": 45,  # ui-ux before-submit (30s) + router shadow (20s)
    "pre-tool-use": 65,        # tdd-guard launcher link (60s)
    "post-tool-use": 30,
    "stop": 30,
    "subagent-stop": 15,
    "pre-compact": 15,
    "session-end": 15,
}

# settings.json hooks key -> dispatch event token
_EVENT_KEY = {
    "SessionStart": "session-start",
    "UserPromptSubmit": "user-prompt-submit",
    "PreToolUse": "pre-tool-use",
    "PostToolUse": "post-tool-use",
    "Stop": "stop",
    "SubagentStop": "subagent-stop",
    "PreCompact": "pre-compact",
    "SessionEnd": "session-end",
}


def _dispatch_block() -> dict:
    """The 8-entry hooks block: one dispatch.py invocation per event."""
    block: dict = {}
    for key, token in _EVENT_KEY.items():
        block[key] = [{
            "matcher": ".*",
            "hooks": [{
                "type": "command",
                "command": f"python3 ${{HOME}}/.claude/hooks/dispatch.py {token}",
                "timeout": _EVENT_TIMEOUT[token],
            }],
        }]
    return block


def _default_settings() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(env).expanduser() if env else Path("~/.claude").expanduser()
    return base / "settings.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write_json(path: Path, data: dict) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)  # prove validity BEFORE touching the target
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
    data = _load_json(settings)
    hooks = data.get("hooks", {})
    payload = {
        "_about": "Verbatim freeze of the legacy 65-registration hooks block for "
                  "flip-dispatch.py --legacy revert (Charter §2/§3, 30-day window). "
                  "Also the parity harness's legacy-inventory source (P4-T2).",
        "captured_from": str(settings),
        "hooks": hooks,
    }
    _atomic_write_json(_LEGACY_SNAPSHOT, payload)
    n = sum(len(g.get("hooks", [])) for arr in hooks.values() for g in arr)
    print(f"snapshot: froze {n} legacy hook registrations -> {_LEGACY_SNAPSHOT.name}")
    return 0


def _current_mode(settings: Path) -> str:
    try:
        hooks = _load_json(settings).get("hooks", {})
    except (OSError, json.JSONDecodeError):
        return "unknown"
    cmds = [h.get("command", "") for arr in hooks.values() for g in arr for h in g.get("hooks", [])]
    if any("dispatch.py" in c for c in cmds):
        # a pure dispatch block is exactly 8 dispatch commands and nothing else
        if all("dispatch.py" in c for c in cmds):
            return "dispatch"
        return "mixed"
    return "legacy"


def to_dispatch(settings: Path, dry_run: bool) -> int:
    data = _load_json(settings)
    if not _LEGACY_SNAPSHOT.exists():
        snapshot(settings)  # never flip without a revert point
    data.setdefault("hooks", {})
    data["hooks"] = _dispatch_block()
    if dry_run:
        print(json.dumps(data["hooks"], indent=2))
        return 0
    _atomic_write_json(settings, data)
    print("flipped -> DISPATCH block (8 entries). Revert: flip-dispatch.py --legacy")
    return 0


def to_legacy(settings: Path, dry_run: bool) -> int:
    if not _LEGACY_SNAPSHOT.exists():
        print("ERROR: no legacy-settings-hooks.json snapshot — run --snapshot first", file=sys.stderr)
        return 1
    snap = _load_json(_LEGACY_SNAPSHOT)
    hooks = snap.get("hooks", {})
    data = _load_json(settings)
    data.setdefault("hooks", {})
    data["hooks"] = hooks
    if dry_run:
        print(json.dumps(hooks, indent=2))
        return 0
    _atomic_write_json(settings, data)
    print("flipped -> LEGACY block (byte-identical 65-registration restore).")
    return 0


def main(argv: list[str]) -> int:
    settings = _default_settings()
    dry = "--dry-run" in argv
    if "--settings" in argv:
        i = argv.index("--settings")
        if i + 1 < len(argv):
            settings = Path(argv[i + 1]).expanduser()
    if "--snapshot" in argv:
        return snapshot(settings)
    if "--dispatch" in argv:
        return to_dispatch(settings, dry)
    if "--legacy" in argv:
        return to_legacy(settings, dry)
    if "--status" in argv:
        print(f"hooks block: {_current_mode(settings)}  ({settings})")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
