"""Lead items of the 2026-10-05 audit fix pass (WP8): small cross-package fixes.

Runnable: `python3 -m pytest hooks/tests/test_lead_wp8.py -q`.
"""
from __future__ import annotations

import io
import json
import pathlib
import sys

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from prompt_router import router as R   # noqa: E402


class _Rec:
    def __init__(self):
        self.rows = []

    def record(self, event, kind, **kw):
        self.rows.append((event, kind, kw))


def test_router_live_row_carries_ms(monkeypatch, capsys):
    """A-10: every dispatch row carries `ms`; the router's own row must too."""
    rec = _Rec()
    monkeypatch.setattr(R, "_tel", rec)
    payload = {"session_id": "t-wp8-ms", "prompt": "fix the failing vitest test in src/api/config.ts",
               "cwd": str(HOOKS)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    R.run([])
    capsys.readouterr()
    live = [kw for ev, kind, kw in rec.rows if kind == "prompt_router.live"]
    assert live, rec.rows
    assert isinstance(live[0].get("ms"), (int, float)) and live[0]["ms"] >= 0


# --------------------------------------------------------------------------- J-01
_WORKER = """
import sys
sys.path.insert(0, {hooks!r})
from lib import platform as P
def add(d):
    d.setdefault("paths", []).append(sys.argv[1])
    return d
for i in range(25):
    P.locked_update({path!r}, lambda d: add(d) or d)
"""


def test_locked_update_loses_no_concurrent_writes(tmp_path):
    """J-01: N processes read-modify-writing one state file must all survive."""
    import subprocess
    target = tmp_path / "s.desloppify.json"
    script = tmp_path / "w.py"
    script.write_text(_WORKER.format(hooks=str(HOOKS), path=str(target)), encoding="utf-8")
    procs = [subprocess.Popen([sys.executable, str(script), f"w{n}"]) for n in range(6)]
    assert all(p.wait(timeout=60) == 0 for p in procs)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert len(data["paths"]) == 6 * 25


def test_locked_update_starts_fresh_on_a_corrupt_file_and_leaves_no_temp(tmp_path):
    from lib import platform as P
    target = tmp_path / "s.security-scan.json"
    target.write_text("{torn", encoding="utf-8")
    out = P.locked_update(target, lambda d: {**d, "x": 1})
    assert out == {"x": 1} and json.loads(target.read_text(encoding="utf-8")) == {"x": 1}
    assert not list(tmp_path.glob(".tmp-*.swap"))


# --------------------------------------------------------------------------- WP6 handoff
@pytest.mark.parametrize("prompt,consent", [
    ("just stop", True), ("Skip verification.", True), ("skip the verify", True),
    ("don’t do anything else", True), ("that’s all", True), ("ok, stop now", True),
    ("stop the server and fix the login bug", False), ("skip the tests and ship", False),
])
def test_hcg_consent_matches_the_mod(prompt, consent):
    """mods/mercy/hooks/lib/consent.ts and hard-completion-gate CONSENT_RE agree."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("hcg_wp8", HOOKS / "hard-completion-gate.py")
    hcg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hcg)
    assert bool(hcg.CONSENT_RE.match(prompt)) is consent


def test_subagent_mode_line_says_omit_model(monkeypatch):
    """WP5 lead line: opus-guard applies a pinned per-project mode; subagents omit model."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("subctx_wp8", HOOKS / "subagent-context.py")
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    from lib import model_mode
    monkeypatch.setattr(model_mode, "forced_mode", lambda cwd: "opus")
    text = sc.build({"cwd": "/repo/app"})
    assert "pinned to opus" in text and "omit model" in text
    assert 'pass model:"opus"' not in text


def test_cross_session_message_is_not_a_user_prompt():
    """NEW-10: a peer session's message arrives as a prompt; the router pushed UI
    skills onto it and the Stop gates would anchor a 'human' turn on it."""
    from prompt_router import classify as C
    from lib import turns
    msg = '<cross-session-message from="uds:/x.sock" from-name="peer">Agreed: c3 owns Phase 5</cross-session-message>'
    assert C.is_trivial_ack(msg)
    assert turns._prompt_text({"type": "user", "message": {"role": "user", "content": msg}}) is None


def test_adapted_multi_path_deny_keeps_the_other_paths_context(monkeypatch):
    """Santa H2: a ctx_patch on two files, path 2 denied: path 1's (drained) advisory was dropped."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("dispatch_wp8", HOOKS / "dispatch.py")
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)

    class Sup:
        @staticmethod
        def adapt(payload):
            return [{"n": 1}, {"n": 2}]
    monkeypatch.setattr(d, "_sup", Sup)
    canned = {1: {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                         "additionalContext": "tdd-guard: write the test first"}},
              2: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                         "permissionDecisionReason": "dox: add a CLAUDE.md"}}}
    monkeypatch.setattr(d, "_dispatch_one", lambda ev, p, cfg, only, drain=False, adapted=False: canned[p["n"]])
    out = d.dispatch("pre-tool-use", {"tool_name": "mcp__lean-ctx__ctx_patch"}, {})["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "dox: add a CLAUDE.md" in out["permissionDecisionReason"]
    assert "tdd-guard: write the test first" in out["permissionDecisionReason"]


def test_substrate_lines_respect_project_disabled_servers(monkeypatch):
    """Santa A2: _mcp_ok had no root, so disabledMcpServers never hid the jcodemunch line."""
    from types import SimpleNamespace
    from prompt_router import classify as C
    from prompt_router.modules import mcp_routes as M
    monkeypatch.setattr(M, "available_servers", lambda: {"jcodemunch", "jdocmunch"})
    monkeypatch.setattr(M, "needs_auth", lambda: set())
    monkeypatch.setattr(M, "project_servers", lambda root: set())
    monkeypatch.setattr(M, "_user_cfg", lambda: {"projects": {"/r": {"disabledMcpServers": ["jcodemunch"]}}})
    prof = C.classify({"prompt": "fix the bug in the payment handler controller, it crashes", "cwd": "/tmp"})
    on = [i["id"] for i in R._substrate_items(prof, {"repo": SimpleNamespace(root="/r")})]
    off = [i["id"] for i in R._substrate_items(prof, {"repo": SimpleNamespace(root="/other")})]
    assert not any(i.startswith("substrate:jcodemunch") for i in on), on
    assert any(i.startswith("substrate:jcodemunch") for i in off), off


def test_long_punctuation_prompt_classifies_fast_and_keeps_its_words():
    """Santa A3: prompt_paths was quadratic on '.'/'-' runs (40k chars: 23 s > the 15 s hook timeout)."""
    import time
    from prompt_router import classify as C

    def run(n):
        t0 = time.perf_counter()
        prof = C.classify({"prompt": "fix the failing test in server/src/a.ts " + "." * n + " then update the docs",
                           "cwd": "/tmp"})
        return time.perf_counter() - t0, prof

    # Scaling, not a wall-clock budget (A7-07): 4x the input must cost about 4x (linear), never 16x
    # (quadratic: 40k chars took 23 s). Both sizes run on the same box in the same moment, so a
    # loaded runner slows both; the slack absorbs scheduler noise on the tiny linear timings.
    run(2000)  # warm-up: first-call imports must not land in the small timing
    small, _ = run(10000)
    big, prof = run(40000)
    assert big < 8 * small + 0.5, f"classify scales badly: 10k={small:.3f}s 40k={big:.3f}s"
    assert "TEST" in prof.intents or "DEBUG" in prof.intents, prof.intents
    assert "DOCS" in prof.intents, prof.intents


def test_disabled_servers_keyed_by_launch_folder_count_too(monkeypatch):
    """Santa-2 A1: ~/.claude.json projects are keyed by the launch cwd, not the git root."""
    from prompt_router.modules import mcp_routes as M
    monkeypatch.setattr(M, "available_servers", lambda: {"jcodemunch"})
    monkeypatch.setattr(M, "needs_auth", lambda: set())
    monkeypatch.setattr(M, "project_servers", lambda root: set())
    monkeypatch.setattr(M, "_user_cfg", lambda: {"projects": {"/r/sub": {"disabledMcpServers": ["jcodemunch"]}}})
    assert M.server_available(["jcodemunch"], ["/r", "/r/sub"]) is None
    assert M.server_available(["jcodemunch"], "/r") == "jcodemunch"


def test_go_phrase_needs_a_noun_phrase_not_a_verb():
    """Santa-2 A2: 'let's go program it' made golang-patterns rank 1 in a non-Go repo."""
    from prompt_router.modules import surface as SF
    assert "go" not in SF.detect({"prompt": "let's go program it", "cwd": "/tmp"})[0]
    assert "go" in SF.detect({"prompt": "write a small go cli that reads a csv", "cwd": "/tmp"})[0]


# --------------------------------------------------------------------------- J-02
_DOTSTATE_MODULES = [
    "bash-write-gate.py", "blocking-doc-enforcer.py", "codex-capture.py", "dangerous-bash-gate.py",
    "doc-update-enforcer.py", "dox-child-scaffold.py", "dox-write-gate.py", "gateguard-write-gate.py",
    "graphify-enforce.py", "graphify_launcher.py", "hard-completion-gate.py", "index-lifecycle.py",
    "jcodemunch-enforce.py", "jdocmunch-enforce.py", "mcp-post-hints.py", "santa-method-writer.py",
    "session-lifecycle.py", "session-start-aggregator.py", "skill-invocation-tracker.py",
    "teammate-idle-gate.py", "desloppify-cleanup.py", "first-write-skill-gate.py",
    "fullstack-skills-reminder.py", "security-scan-gate.py", "security-semgrep-tracker.py",
    "tools/state-cleanup.py",
]


@pytest.mark.parametrize("module", _DOTSTATE_MODULES)
def test_every_dotstate_writer_honours_the_override(module):
    """J-02: hooks/.state is derived from the script path, so a sandbox HOME never
    isolated it; every module that builds it must honour CLAUDE_HOOK_DOTSTATE_DIR."""
    src = (HOOKS / module).read_text(encoding="utf-8")
    assert "CLAUDE_HOOK_DOTSTATE_DIR" in src, module


def test_dotstate_override_reaches_a_spawned_hook(tmp_path):
    import os
    import subprocess
    sid = f"t-wp8-dotstate-{os.getpid()}"
    env = {**os.environ, "CLAUDE_HOOK_DOTSTATE_DIR": str(tmp_path)}
    payload = {"session_id": sid, "tool_name": "Write",
               "tool_input": {"file_path": "/repo/app/server/src/auth/login.ts"}}
    subprocess.run([sys.executable, str(HOOKS / "security-scan-gate.py")], input=json.dumps(payload),
                   text=True, env=env, capture_output=True, timeout=30, check=True)
    assert (tmp_path / f"{sid}.security-scan.json").is_file()
    assert not (HOOKS / ".state" / f"{sid}.security-scan.json").exists()


def test_link_doctor_children_never_write_live_state():
    src = (HOOKS / "tools" / "link-doctor.py").read_text(encoding="utf-8")
    for var in ("CLAUDE_HOOK_DOTSTATE_DIR", "CLAUDE_HOOK_STATE_DIR", "CLAUDE_HOOK_TELEMETRY_DIR"):
        assert var in src, var


@pytest.mark.parametrize("script", ["security-scan-gate.py", "security-semgrep-tracker.py",
                                    "first-write-skill-gate.py", "fullstack-skills-reminder.py",
                                    "desloppify-cleanup.py"])
def test_state_writers_go_through_locked_update(script):
    """J-01: no shared per-session state file is written with a bare write_text RMW."""
    src = (HOOKS / script).read_text(encoding="utf-8")
    assert "locked_update" in src
    for line in src.splitlines():
        assert not ("write_text(json.dumps" in line and "state" in line.lower()), line
