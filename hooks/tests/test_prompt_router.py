"""Router invariant test suite (P1-T11) — Charter §§1-2 made regression-proof.

Covers: priority-ordered budget (tier-0 never dropped, sum bounded, drops
logged); floor-coverage (build-trigger-floor.py --check as a test); manifest
dedup NEVER suppresses a first fire; trivial fast-exit ONLY on the exact ack
allowlist; substrate directives ALL emitted when applicable (no cap); router
fail-open on an internal error (still emits valid JSON); + a reusable
shadow-vs-live parity harness for P1-T8/P7.

Runnable: `pytest hooks/tests/test_prompt_router.py` or directly.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import budget as B          # noqa: E402
from prompt_router import classify as C        # noqa: E402
from prompt_router import manifest as M        # noqa: E402
from prompt_router import router as R          # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _run_router(payload: dict, argv=None) -> dict:
    cmd = [sys.executable, str(_HOOKS / "prompt_router" / "router.py")] + (argv or [])
    cp = subprocess.run(cmd, input=json.dumps(payload), text=True,
                        capture_output=True, timeout=30, check=False)
    # router prints exactly one JSON object
    out = cp.stdout.strip().splitlines()
    return json.loads(out[-1]) if out else {}


def _ac(payload: dict, argv=None) -> str:
    return _run_router(payload, argv).get("additionalContext", "")


def _uid(tag: str) -> str:
    import os
    import time
    return f"t11-{tag}-{os.getpid()}-{int(time.time()*1000)}"


# --------------------------------------------------------------------------- #
# budget
# --------------------------------------------------------------------------- #
def test_budget_tier0_never_dropped_even_over_budget():
    big = "x" * 4000  # ~1000 tokens
    items = [{"id": "g", "tier": 0, "text": big}]
    incl, dropped = B.apply(items, max_tokens=10)
    assert incl and not dropped
    assert incl[0]["id"] == "g"


def test_budget_drops_low_tier_over_budget_and_logs_reason():
    items = [
        {"id": "t0", "tier": 0, "text": "a" * 40},
        {"id": "t3a", "tier": 3, "text": "b" * 4000},
        {"id": "t3b", "tier": 3, "text": "c" * 4000},
    ]
    incl, dropped = B.apply(items, max_tokens=1100)  # ~1000 fits one t3 + t0
    ids_in = {i["id"] for i in incl}
    assert "t0" in ids_in                # tier-0 always
    assert dropped                       # at least one t3 dropped
    for d in dropped:
        assert "_drop_reason" in d       # every drop carries a logged reason


def test_budget_tier_order_is_ascending():
    items = [
        {"id": "adv", "tier": 3, "text": "z"},
        {"id": "gate", "tier": 0, "text": "z"},
        {"id": "sub", "tier": 1, "text": "z"},
    ]
    incl, _ = B.apply(items, max_tokens=10000)
    assert [i["id"] for i in incl] == ["gate", "sub", "adv"]


# --------------------------------------------------------------------------- #
# floor coverage
# --------------------------------------------------------------------------- #
def test_trigger_floor_check_passes():
    cp = subprocess.run([sys.executable, str(_HOOKS / "build-trigger-floor.py"), "--check", "--quiet"],
                        capture_output=True, text=True, check=False)
    assert cp.returncode == 0, cp.stderr


# --------------------------------------------------------------------------- #
# manifest dedup — never suppresses a first fire
# --------------------------------------------------------------------------- #
def test_manifest_dedup_never_suppresses_first_fire():
    emitted = {"skill:a", "substrate:jcodemunch"}
    items = [
        {"id": "skill:a", "text": "already seen"},      # suppressed
        {"id": "skill:NEW", "text": "brand new"},       # MUST fire
        {"id": None, "text": "no id"},                  # always kept
    ]
    kept, suppressed = M.dedup(items, emitted)
    kept_ids = {k.get("id") for k in kept}
    assert "skill:NEW" in kept_ids                      # first fire never lost
    assert None in kept_ids                             # id-less always kept
    assert {s["id"] for s in suppressed} == {"skill:a"}


def test_manifest_dedup_dupe_within_same_prompt():
    kept, suppressed = M.dedup(
        [{"id": "x", "text": "1"}, {"id": "x", "text": "2"}], set())
    assert len(kept) == 1 and len(suppressed) == 1


# --------------------------------------------------------------------------- #
# trivial fast-exit — exact allowlist ONLY
# --------------------------------------------------------------------------- #
def test_trivial_exit_only_on_exact_ack():
    assert C.is_trivial_ack("ok")
    assert C.is_trivial_ack("  Continue. ")
    # a short REAL prompt is NOT exited (the <12-char heuristic is dropped)
    assert not C.is_trivial_ack("fix bug")
    assert not C.is_trivial_ack("why?")
    assert not C.is_trivial_ack("the ui")


def test_trivial_ack_emits_nothing_e2e():
    assert _ac({"prompt": "ok", "session_id": "t11-ack"}) == ""


def test_short_real_prompt_still_triggers_e2e():
    # "fix the login bug" is short but real -> must NOT be trivially exited
    body = _ac({"prompt": "fix the login bug", "session_id": _uid("realshort")})
    assert body != ""


# --------------------------------------------------------------------------- #
# substrate: ALL applicable directives emitted (no cap-2)
# --------------------------------------------------------------------------- #
def test_all_substrate_directives_when_applicable():
    payload = {"prompt": "debug and refactor the architecture, update the README docs, "
                         "trace the dependency graph and blast radius",
               "session_id": _uid("substrate")}
    body = _ac(payload)
    # jcodemunch (code), jdocmunch (docs), sequential-thinking (reasoning), graphify (arch)
    assert "jcodemunch" in body
    assert "jdocmunch" in body
    assert "sequential-thinking" in body
    assert "graphify" in body


# --------------------------------------------------------------------------- #
# fail-open
# --------------------------------------------------------------------------- #
def test_router_fail_open_on_internal_error(monkeypatch=None):
    # force _gather_items to raise; router.main must still emit valid JSON
    orig = R._gather_items
    R._gather_items = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        import io
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(json.dumps({"prompt": "implement a feature", "session_id": "t11-failopen"}))
        cap = io.StringIO()
        sys.stdout = cap
        try:
            rc = R.main([])
        finally:
            sys.stdin, sys.stdout = old_in, old_out
        assert rc == 0
        json.loads(cap.getvalue().strip().splitlines()[-1])  # valid JSON, no crash
    finally:
        R._gather_items = orig


# --------------------------------------------------------------------------- #
# reusable shadow parity harness (P1-T8 / P7)
# --------------------------------------------------------------------------- #
def shadow_would_emit(prompt: str, sid: str) -> dict:
    """Run the router in --shadow and return the logged would-emit record.
    Reusable by the parity harness."""
    _run_router({"prompt": prompt, "session_id": sid}, argv=["--shadow"])
    from lib import platform as plat
    log = plat.telemetry_dir() / f"{sid}.router-shadow.jsonl"
    last = log.read_text(encoding="utf-8").strip().splitlines()[-1]
    return json.loads(last)


def test_shadow_harness_produces_record():
    rec = shadow_would_emit("debug the crash root cause in the service", _uid("shadow"))
    assert "would_emit" in rec and "emitted_ids" in rec


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_prompt_router: {len(fns)} tests PASSED")


if __name__ == "__main__":
    _run_all()
