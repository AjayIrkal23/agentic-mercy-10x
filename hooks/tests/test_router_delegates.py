"""Delegate parity + safety tests (P1-T4).

Charter §3 verify: feeding the SAME fixture payload to the original hook via a
subprocess AND via the delegate's in-process import must yield the same emitted
trigger decision. We assert byte-parity for the two deterministic, state-free
delegates (sequential-thinking, ui-ux) and structural safety (no crash, gated
off by default, fail-open) for the framework as a whole.

Runnable: `pytest hooks/tests/test_router_delegates.py` or directly.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import modules  # noqa: E402
from prompt_router.modules import _base as B  # noqa: E402


def _subprocess_ac(hook_file: str, payload: dict, argv: list[str] | None = None) -> str | None:
    cmd = [sys.executable, str(_HOOKS / hook_file)] + (argv or [])
    try:
        cp = subprocess.run(cmd, input=json.dumps(payload), text=True,
                            capture_output=True, timeout=30, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return B.extract_additional_context(cp.stdout)


def test_seqthink_delegate_matches_subprocess():
    payload = {"prompt": "plan and design the architecture, then debug the root cause",
               "session_id": "delegate-parity-seq"}
    via_delegate = B.run_stdin_hook("sequential-thinking-mandate.py", "main", payload)
    via_subprocess = _subprocess_ac("sequential-thinking-mandate.py", payload)
    assert via_delegate == via_subprocess, (via_delegate, via_subprocess)


def test_uiux_delegate_matches_subprocess():
    # ui-ux is stateful (per-session dedup), so each call gets a FRESH session id
    # to compare a first-fire against a first-fire.
    prompt = "the dashboard navbar looks off, redesign the hero section"
    via_delegate = B.call_payload_fn(
        "ui-ux-stack-orchestrator.py", "handle_before_submit",
        {"prompt": prompt, "session_id": "delegate-parity-ui-A"}, cfg_loader="_load_config")
    via_subprocess = _subprocess_ac(
        "ui-ux-stack-orchestrator.py",
        {"prompt": prompt, "session_id": "delegate-parity-ui-B"}, argv=["before-submit"])
    # Both should agree on whether UI fired and, when fired, on the text.
    assert bool(via_delegate) == bool(via_subprocess), (via_delegate, via_subprocess)
    if via_delegate and via_subprocess:
        assert via_delegate == via_subprocess


def test_delegates_gated_off_by_default():
    assert modules.collect(None, {"config": {}, "mode": "live"}) == []
    assert modules.collect(None, {"config": {"delegates": {"enabled": True}}, "mode": "shadow"}) == []


def test_delegates_enabled_no_crash_returns_list():
    from prompt_router import classify as c
    payload = {"prompt": "debug the crash and review the code", "session_id": "delegate-nocrash"}
    profile = c.classify(payload)
    ctx = {"config": {"delegates": {"enabled": True, "enabled_in_shadow": True}},
           "mode": "shadow", "payload": payload}
    out = modules.collect(profile, ctx)
    assert isinstance(out, list)
    for it in out:
        assert "id" in it and "tier" in it and "text" in it


def test_broken_delegate_import_is_fail_open():
    # a missing hook file yields None, never an exception
    assert B.run_stdin_hook("does-not-exist-hook.py", "main", {"prompt": "x"}) is None
    assert B.load_hook("does-not-exist-hook.py") is None


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
    print(f"test_router_delegates: {passed} tests PASSED")


if __name__ == "__main__":
    _run_all()
