"""_base.py — shared machinery for S3 delegates (P1-T4).

Charter §3: each delegate IMPORTS the original injector hook and only ADAPTS
its I/O to the router's item schema — the original file stays the single home
of its logic (no copies, no keyword pruning). Because the legacy hooks are
stdin/stdout scripts (guarded by ``if __name__ == '__main__'``), we import the
module (side-effect-free) and call its prompt-mode function with stdin/stdout
temporarily redirected — a genuine in-process call, not a subprocess, whose
output is byte-identical to running the hook standalone (the P1-T4 parity test).

Hook files use dashes in their names, so they are loaded via importlib from an
explicit path under a synthetic module name (cached).

SAFETY: delegates are gated by router.config ``delegates.enabled`` (default
false) and never run in shadow mode unless ``enabled_in_shadow`` is set — a
stateful legacy hook must not double-fire beside the still-installed legacy
injector during the shadow window (Charter §2). They reuse exact legacy logic
and activate at/after cutover when the legacy stack is flipped off.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[2]  # .../hooks
_MOD_CACHE: dict[str, object] = {}


def load_hook(filename: str):
    """Import a hook module by filename (dashes ok), side-effect-free. Cached."""
    if filename in _MOD_CACHE:
        return _MOD_CACHE[filename]
    path = _HOOKS / filename
    if not path.is_file():
        _MOD_CACHE[filename] = None
        return None
    modname = "hook_" + filename.replace("-", "_").replace(".py", "")
    try:
        spec = importlib.util.spec_from_file_location(modname, str(path))
        if spec is None or spec.loader is None:
            _MOD_CACHE[filename] = None
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # __main__ guard prevents CLI side effects
        _MOD_CACHE[filename] = mod
        return mod
    except Exception:  # noqa: BLE001 - a broken hook must not break the router
        _MOD_CACHE[filename] = None
        return None


def extract_additional_context(text: str) -> str | None:
    """Pull the additionalContext string out of a hook's stdout (which may be
    one or more JSON objects). Returns None when the hook emitted nothing."""
    if not text:
        return None
    found: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ac = _deep_ac(obj)
        if ac:
            found.append(ac)
    return "\n".join(found) if found else None


def _deep_ac(obj) -> str | None:
    if isinstance(obj, dict):
        if isinstance(obj.get("additionalContext"), str) and obj["additionalContext"].strip():
            return obj["additionalContext"]
        for v in obj.values():
            r = _deep_ac(v)
            if r:
                return r
    return None


def run_stdin_hook(filename: str, func_name: str, payload: dict,
                   *, argv: list[str] | None = None) -> str | None:
    """Call a stdin/stdout hook function in-process with I/O redirected.

    Returns the extracted additionalContext, or None. Never raises.
    """
    mod = load_hook(filename)
    if mod is None:
        return None
    fn = getattr(mod, func_name, None)
    if not callable(fn):
        return None
    old_stdin, old_stdout, old_argv = sys.stdin, sys.stdout, sys.argv
    buf = io.StringIO()
    try:
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.stdout = buf
        sys.argv = [filename] + (argv or [])
        try:
            fn()
        except SystemExit:
            pass
        except Exception:  # noqa: BLE001 - fail-open per delegate
            return None
    finally:
        sys.stdin, sys.stdout, sys.argv = old_stdin, old_stdout, old_argv
    return extract_additional_context(buf.getvalue())


def call_payload_fn(filename: str, func_name: str, payload: dict, cfg_loader: str | None = None) -> str | None:
    """Call a hook function that already takes a payload (e.g. ui-ux
    ``handle_before_submit(payload, cfg)``). Extracts additionalContext from the
    returned dict. Never raises."""
    mod = load_hook(filename)
    if mod is None:
        return None
    fn = getattr(mod, func_name, None)
    if not callable(fn):
        return None
    try:
        cfg = {}
        if cfg_loader:
            loader = getattr(mod, cfg_loader, None)
            if callable(loader):
                cfg = loader() or {}
        out = fn(payload, cfg)
        if isinstance(out, dict):
            return _deep_ac(out)
        if isinstance(out, str):
            return out or None
    except Exception:  # noqa: BLE001
        return None
    return None


def item(iid: str, tier: int, section: str, text: str) -> dict:
    return {"id": iid, "tier": tier, "section": section, "text": text}


__all__ = ["load_hook", "run_stdin_hook", "call_payload_fn",
           "extract_additional_context", "item"]
