"""Router invariant suite (v3, 2026-09-27).

Covers: delivery shape (hookSpecificOutput + `<!-- prompt-router v3 -->` marker);
tier ordering (gates first — the budget machinery is gone, nothing is dropped);
floor coverage (build-trigger-floor.py --check as a test); manifest dedup never
suppresses a first fire; trivial fast-exit ONLY on the exact ack allowlist;
substrate directives (jcodemunch / jdocmunch / graphify — no sequential-thinking
nag, D17); router fail-open on an internal error (still emits valid JSON).

Runnable: `python3 -m pytest hooks/tests/test_prompt_router.py -q`.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import budget as B          # noqa: E402
from prompt_router import classify as C        # noqa: E402
from prompt_router import manifest as M        # noqa: E402
from prompt_router import router as R          # noqa: E402
from prompt_router.modules import mcp_routes as _mcp  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def fake_home(tmp_path_factory):
    """Hermetic HOME whose ~/.claude.json registers the MCP servers the router
    routes to — the router only emits lines for registered servers, so tests must
    not depend on this machine's real ~/.claude.json."""
    home = tmp_path_factory.mktemp("home")
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {
        n: {} for n in ("jcodemunch", "jdocmunch", "graphify", "sequential-thinking")}}),
        encoding="utf-8")
    return home


def _run_router(payload: dict, argv=None, home=None) -> dict:
    cmd = [sys.executable, str(_HOOKS / "prompt_router" / "router.py")] + (argv or [])
    env = None
    if home is not None:
        env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    cp = subprocess.run(cmd, input=json.dumps(payload), text=True, env=env,
                        capture_output=True, timeout=30, check=False)
    out = cp.stdout.strip().splitlines()
    return json.loads(out[-1]) if out else {}


def _ac(payload: dict, argv=None, home=None) -> str:
    return _run_router(payload, argv, home).get("hookSpecificOutput", {}).get("additionalContext", "")


def _uid(tag: str) -> str:
    import os
    import time
    return f"t11-{tag}-{os.getpid()}-{int(time.time()*1000)}"


# --------------------------------------------------------------------------- #
# delivery shape
# --------------------------------------------------------------------------- #
def test_emit_uses_hook_specific_output_with_marker():
    out = _run_router({"prompt": "implement the retry queue for failed webhook deliveries",
                       "session_id": _uid("shape")})
    hso = out.get("hookSpecificOutput")
    assert hso, f"top-level additionalContext is the pre-v3 (undelivered) shape: {out}"
    assert hso["hookEventName"] == "UserPromptSubmit"
    assert hso["additionalContext"].startswith(R.MARKER)


# --------------------------------------------------------------------------- #
# ordering (ex-budget): gates first, nothing dropped
# --------------------------------------------------------------------------- #
def test_apply_never_drops_and_keeps_tier0_first():
    items = [
        {"id": "adv", "tier": 3, "text": "z" * 4000},
        {"id": "gate", "tier": 0, "text": "z"},
        {"id": "sub", "tier": 1, "text": "z" * 4000},
    ]
    incl, dropped = B.apply(items, max_tokens=10)   # max_tokens is accepted and ignored
    assert not dropped
    assert [i["id"] for i in incl] == ["gate", "sub", "adv"]


def test_apply_is_stable_within_a_tier():
    items = [{"id": f"s{i}", "tier": 2, "text": "x"} for i in range(5)]
    incl, _ = B.apply(items)
    assert [i["id"] for i in incl] == [f"s{i}" for i in range(5)]


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
    assert "skill:NEW" in kept_ids
    assert None in kept_ids
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
    assert not C.is_trivial_ack("fix bug")
    assert not C.is_trivial_ack("why?")
    assert not C.is_trivial_ack("the ui")


def test_trivial_ack_emits_nothing_e2e():
    assert _ac({"prompt": "ok", "session_id": "t11-ack"}) == ""


def test_short_real_prompt_still_triggers_e2e():
    body = _ac({"prompt": "fix the login bug", "session_id": _uid("realshort")})
    assert body != ""


# --------------------------------------------------------------------------- #
# substrate directives — MCP-first "call X now" (D17 reversed 2026-09-28)
# --------------------------------------------------------------------------- #
def test_substrate_directives_when_applicable(fake_home):
    payload = {"prompt": "debug and refactor the architecture, update the README docs, "
                         "trace the dependency graph and blast radius",
               "session_id": _uid("substrate")}
    body = _ac(payload, home=fake_home)
    assert "jcodemunch" in body
    assert "jdocmunch" in body
    assert "graphify" in body
    assert "dox:" not in body   # static dox line dropped — CLAUDE.md carries it
    assert "mcp__sequential-thinking__sequentialthinking" in body   # registered in fake_home


def _mcp_items(prompt: str, servers: set[str], port=None, cwd="/nonexistent-dir") -> list[str]:
    """MCP route lines for a prompt with a faked server roster (no ~/.claude.json)."""
    _mcp.available_servers.cache_clear()
    _mcp.needs_auth.cache_clear()
    _mcp.dev_server_port.cache_clear()
    orig = (_mcp.available_servers, _mcp.needs_auth, _mcp.dev_server_port)
    _mcp.available_servers = lambda: set(servers)          # type: ignore[assignment]
    _mcp.needs_auth = lambda: set()                         # type: ignore[assignment]
    _mcp.dev_server_port = lambda: port                     # type: ignore[assignment]
    try:
        prof = C.classify({"prompt": prompt, "cwd": cwd})
        return [it["text"] for it in _mcp.items(prof, {"repo": None}, max_routes=4)]
    finally:
        _mcp.available_servers, _mcp.needs_auth, _mcp.dev_server_port = orig


_ALL = {"sequential-thinking", "semgrep", "context7", "memory", "reticle", "playwright",
        "higgsfield", "jcodemunch", "jdocmunch", "graphify"}


def test_mcp_route_seqthink_on_plan_and_decision():
    assert any("sequentialthinking" in t for t in _mcp_items("plan the migration to the new queue", _ALL))
    assert any("sequentialthinking" in t for t in _mcp_items("should we use redis or postgres here?", _ALL))


def test_mcp_route_availability_aware():
    assert not any("sequentialthinking" in t for t in _mcp_items("plan the migration", _ALL - {"sequential-thinking"}))


def test_mcp_route_context7_on_import():
    lines = _mcp_items("why does `import { useQuery } from '@tanstack/react-query'` refetch twice", _ALL)
    assert any("@tanstack/react-query" in t and "resolve-library-id" in t for t in lines), lines
    lines = _mcp_items("from pydantic import BaseModel fails validation", _ALL)
    assert any("pydantic" in t for t in lines), lines


def test_mcp_route_memory_and_semgrep():
    assert any("mcp__memory__search_nodes" in t for t in _mcp_items("remember that we use pnpm", _ALL))
    assert any("semgrep_scan" in t for t in _mcp_items("add jwt refresh to the login middleware", _ALL))


def test_mcp_route_browser_only_when_app_running():
    p = "verify the ui change works in the browser"
    assert not any("verify-ui-change" in t for t in _mcp_items(p, _ALL, port=None))
    assert any("verify-ui-change" in t and ":5173" in t for t in _mcp_items(p, _ALL, port=5173))


def test_verify_prompts_classify_as_verify():
    for p in ("verify the export works", "check it works after the refactor", "prove the fix"):
        assert "VERIFY" in C.classify({"prompt": p}).intents, p


def test_hooks_word_is_not_react_without_fe_context():
    from prompt_router.modules import surface as S
    for p in ("update my hooks so the MCPs fire automatically",
              "fix the hooks in dispatch config and the skills"):
        surf, _src, _weak = S.detect({"prompt": p, "cwd": "/nonexistent-dir"}, text=p.lower())
        assert "frontend" not in surf and "claude-infra" in surf, (p, surf)
    p = "add a useDebounce hook to the search component"
    surf, _src, _weak = S.detect({"prompt": p, "cwd": "/nonexistent-dir"}, text=p.lower())
    assert "frontend" in surf


def test_jcodemunch_directive_is_intent_specific(fake_home):
    body = _ac({"prompt": "debug why the export handler returns a 500", "session_id": _uid("jcmdebug")},
               home=fake_home)
    assert "get_call_hierarchy" in body


# --------------------------------------------------------------------------- #
# fail-open
# --------------------------------------------------------------------------- #
def test_router_fail_open_on_internal_error():
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
        json.loads(cap.getvalue().strip().splitlines()[-1])
    finally:
        R._gather_items = orig


# --------------------------------------------------------------------------- #
# path-scoped skills: no dead Skill() push
# --------------------------------------------------------------------------- #
def test_script_dir_never_shadows_stdlib():
    """Run as a script, router.py puts hooks/prompt_router/ first on sys.path, and its
    select.py then shadows stdlib `select` wherever that is not a builtin (CI's
    setup-python 3.12 ships it as a .so). `subprocess` imports `select`, so
    mcp_routes failed to import and every MCP route line vanished, silently."""
    pr = _HOOKS / "prompt_router"
    code = ("import runpy, sys, pathlib\n"
            f"d = pathlib.Path({str(pr)!r}).resolve()\n"
            "sys.path.insert(0, str(d))\n"
            "runpy.run_path(str(d / 'router.py'), run_name='router_probe')\n"
            "print(any(pathlib.Path(p or '.').resolve() == d for p in sys.path))\n")
    cp = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert cp.stdout.strip() == "False", cp.stdout + cp.stderr


def _pushed_actions(prompt: str, tag: str) -> list[tuple[str, str]]:
    import re
    out = _ac({"prompt": prompt, "session_id": _uid(tag), "cwd": "/nonexistent-dir"})
    return re.findall(r"^- \*\*([\w:.-]+)\*\* \((?:MUST|SHOULD)-READ\).*\n  (ACTION: .*)$",
                      out, re.M)


def test_path_scoped_skill_push_is_a_read_of_its_file():
    """Claude Code keeps a `paths:`-scoped skill out of the Skill tool's listing until a
    matching file is touched (`Unknown skill`), so its push is a Read of the SKILL.md."""
    meta = R._select.index_meta()
    pushed = _pushed_actions("add a paginated GET /products endpoint with input validation",
                             "pathscoped")
    scoped = [(n, a) for n, a in pushed if (meta.get(n) or {}).get("paths")]
    assert scoped, f"expected a paths:-scoped skill for a backend API prompt: {pushed}"
    for name, action in scoped:
        assert "Skill(" not in action and f"skills/{name}/SKILL.md" in action, (name, action)


def test_listed_skill_push_still_uses_the_skill_tool():
    pushed = dict(_pushed_actions("the checkout total is wrong intermittently, find the root cause",
                                  "listed"))
    assert 'Skill("debug-investigation")' in pushed.get("debug-investigation", ""), pushed
