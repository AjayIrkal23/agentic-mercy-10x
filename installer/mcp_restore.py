"""mcp_restore.py — swap one user-scope MCP registration without ever losing it silently.

``replace_entry`` removes ``name`` and adds ``new`` with ``claude mcp add-json``; when the
add fails it puts the ``old`` entry back and CHECKS that restore too (Santa autonomy review:
an unchecked restore left the server out of ~/.claude.json while the status said "restored").
Status strings are shared by ``deps.reconcile_mcp_env`` / ``reconcile_mcp_pins``. Pure stdlib.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402

UNREGISTERED = "FAIL(unregistered)"
CANNOT_PASS = "WARN(cannot pass cmd.exe; left as is)"


def _add_argv(name: str, entry: dict) -> list[str]:
    return ["claude", "mcp", "add-json", "--scope", "user", name, json.dumps(entry)]


def _add(name: str, entry: dict) -> int:
    return plat.run(_add_argv(name, entry), timeout=60).returncode


def replace_entry(name: str, new: dict, old: dict, ok_status: str) -> str:
    """``ok_status`` when the new entry registered; ``WARN(rc=N, restored)`` when it failed
    but the old one is back; ``FAIL(unregistered)`` when both adds failed (the next daily
    run re-adds a manifest server that is missing: ``deps.register_mcps``); ``CANNOT_PASS`` when
    ``claude`` is a Windows ``.cmd`` shim and cmd.exe cannot carry the JSON of either entry (a ``%``,
    ``!`` or escaped ``"``): decided BEFORE the remove, so the server is never taken out for nothing."""
    if not (plat.passes_cmd_exe(_add_argv(name, new)) and plat.passes_cmd_exe(_add_argv(name, old))):
        return CANNOT_PASS
    if plat.run(["claude", "mcp", "remove", "--scope", "user", name], timeout=60).returncode != 0:
        return "WARN(remove failed, unchanged)"
    rc = _add(name, new)
    if rc == 0:
        return ok_status
    return f"WARN(rc={rc}, restored)" if _add(name, old) == 0 else UNREGISTERED
