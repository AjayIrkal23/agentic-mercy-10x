"""Guard-rail tests for the WP-5 gate rework (2026-09-27).

  * HOME is never a repo: tdd launcher exits 0 silently for cwd `$HOME`;
    dox_engine refuses to plan/sweep `$HOME`; the shared classifier skips
    scratchpad / hooks / docs paths.
  * hard-completion-gate blocks at most ONCE per turn, honours stop_hook_active
    and an explicit user "stop".
  * invoke-suite-gate normalises naive timestamps to UTC.
  * security-scan-gate matches basename TOKENS, not substrings.
  * dangerous-bash-gate ignores quoted text and fingerprints the FULL command.
  * dox_cleanup only classifies the untouched template as a stub.

Pure stdlib + pytest. `python3 -m pytest hooks/tests/test_gates.py -q`.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_main(mod, payload: dict, monkeypatch) -> dict:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    out = buf.getvalue().strip()
    return json.loads(out) if out else {}


# --------------------------------------------------------------------------- #
# lib.code_files
# --------------------------------------------------------------------------- #
def test_code_files_classifier_and_home():
    from lib import code_files as cf
    assert cf.is_code_file("/work/u/CODE_FILES/app/src/a.ts")
    assert cf.is_code_file("/work/u/CODE_FILES/app/server/main.go")
    assert not cf.is_code_file("/tmp/claude-1000/x/scratchpad/probe.py")
    assert not cf.is_code_file("/work/u/.claude/hooks/gate.py")
    assert not cf.is_code_file("/work/u/CODE_FILES/app/docs/a.py")
    assert not cf.is_code_file("/work/u/CODE_FILES/app/README.md")
    assert not cf.is_code_file("")
    assert cf.is_home(str(Path.home()))
    assert not cf.is_home(str(Path.home() / ".claude"))
    # HOME is a ceiling: a file directly under ~ has no repo even if ~/.git exists.
    assert cf.git_root(str(Path.home() / "x.py")) is None


# --------------------------------------------------------------------------- #
# jcodemunch-enforce — exempt_paths must match native (Windows) separators
# --------------------------------------------------------------------------- #
def test_jcm_gate_exempts_claude_dir_with_native_separators():
    jcm = _load("jcodemunch_enforce", "jcodemunch-enforce.py")
    cfg = jcm._load_enforce_config()
    claude = Path.home() / ".claude"
    # str(Path) is backslashed on Windows, where "~" used to expand to a backslash
    # home glued onto "/.claude/", so the exemption never matched there.
    assert jcm._is_exempt(str(claude / "installer" / "doctor.py"), cfg)
    assert jcm._is_exempt((claude / "hooks" / "dispatch.py").as_posix(), cfg)
    assert not jcm._is_exempt("/work/repo/src/app.py", cfg)
    assert not jcm._is_exempt(r"D:\work\repo\src\app.py", cfg)


# --------------------------------------------------------------------------- #
# tdd launcher — HOME cwd is never a tdd project
# --------------------------------------------------------------------------- #
def test_tdd_launcher_home_cwd_exits_0_silent():
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    payload = json.dumps({"tool_name": "Edit",
                          "tool_input": {"file_path": str(Path.home() / "x.py")}})
    cp = subprocess.run([sys.executable, str(_HOOKS / "tdd_guard_launcher.py")],
                        input=payload, text=True, capture_output=True,
                        cwd=str(Path.home()), env=env, timeout=10)
    assert cp.returncode == 0
    assert cp.stdout.strip() == ""


def test_tdd_launcher_todowrite_is_noop(tmp_path):
    payload = json.dumps({"tool_name": "TodoWrite", "tool_input": {}})
    cp = subprocess.run([sys.executable, str(_HOOKS / "tdd_guard_launcher.py")],
                        input=payload, text=True, capture_output=True,
                        cwd=str(tmp_path), timeout=10)
    assert cp.returncode == 0 and cp.stdout.strip() == ""


# --------------------------------------------------------------------------- #
# dox_engine — refuses HOME / non-repos; sidecar written by sweep
# --------------------------------------------------------------------------- #
def test_dox_engine_refuses_home(capsys):
    dox = _load("dox_engine_ut", "dox_engine.py")
    assert dox._cli(["plan", str(Path.home())]) == 2
    assert "refusing" in capsys.readouterr().err


def test_dox_engine_refuses_non_repo(tmp_path):
    dox = _load("dox_engine_ut", "dox_engine.py")
    assert dox._cli(["plan", str(tmp_path)]) == 2


def test_dox_sweep_writes_sidecar_and_curates_index(tmp_path):
    dox = _load("dox_engine_ut", "dox_engine.py")
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / ".git").mkdir()
    for n in ("a", "b", "c"):
        (repo / "src" / f"{n}.py").write_text("x = 1\n")
    cfg = dox.load_cfg(None, root=repo)
    s = dox.sweep(repo, cfg, create=True)
    assert not s["refused"]
    assert (repo / dox.DATA_REL / dox.SIDECAR_NAME).is_file()
    assert (repo / "src" / "CLAUDE.md").is_file()
    # untouched template child is NOT indexed …
    root_doc = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert "src/CLAUDE.md" not in root_doc
    # … until someone fleshes it out.
    (repo / "src" / "CLAUDE.md").write_text("<!-- dox:child v1 -->\n# src\nReal docs.\n")
    dox.sweep(repo, cfg, create=True)
    assert "src/CLAUDE.md" in (repo / "CLAUDE.md").read_text(encoding="utf-8")


def test_dox_fallback_child_stub_is_not_indexed(tmp_path, monkeypatch):
    """No dox-doc-tree templates on disk (fresh checkout, bare HOME) -> the built-in
    fallback stub must still read as template-only, or sweep indexes empty stubs."""
    dox = _load("dox_engine_ut", "dox_engine.py")
    monkeypatch.setattr(dox, "REFS_DIR", tmp_path / "no-templates")
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / ".git").mkdir()
    for n in ("a", "b", "c"):
        (repo / "src" / f"{n}.py").write_text("x = 1\n")
    dox.sweep(repo, dox.load_cfg(None, root=repo), create=True)
    assert (repo / "src" / "CLAUDE.md").is_file()
    assert "src/CLAUDE.md" not in (repo / "CLAUDE.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# hard-completion-gate — once per turn, consent, stop_hook_active
# --------------------------------------------------------------------------- #
def _transcript(path: Path, prompts):
    lines = []
    for ts, text in prompts:
        lines.append(json.dumps({"type": "user", "timestamp": ts,
                                 "message": {"role": "user", "content": text}}))
        lines.append(json.dumps({"type": "assistant", "timestamp": ts,
                                 "message": {"role": "assistant", "content": "ok"}}))
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def gate(tmp_path, monkeypatch):
    hcg = _load("hcg_ut", "hard-completion-gate.py")
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(hcg, "STATE_DIR", state)
    monkeypatch.setattr(hcg, "TELEMETRY_DIR", tmp_path / "telemetry")
    cid = "sess-1"
    # 3 unique, non-infra code files → Gates 4 and 5 fail.
    (state / f"{cid}.desloppify.json").write_text(json.dumps({
        "code_writes": 3,
        "code_files": [f"/work/u/CODE_FILES/app/src/{n}.ts" for n in "abc"]}))
    transcript = tmp_path / "t.jsonl"
    _transcript(transcript, [("2026-09-27T10:00:00Z", "build the thing")])
    payload = {"session_id": cid, "transcript_path": str(transcript), "cwd": str(tmp_path)}
    return {"mod": hcg, "payload": payload, "transcript": transcript, "state": state}


def test_gate_blocks_once_then_allows_same_turn(gate, monkeypatch):
    first = _run_main(gate["mod"], gate["payload"], monkeypatch)
    assert first.get("decision") == "block"
    assert "Gate 4 (santa)" in first["reason"] and "Gate 5 (dead code)" in first["reason"]
    second = _run_main(gate["mod"], gate["payload"], monkeypatch)
    assert "decision" not in second
    assert second["systemMessage"].startswith("Completion gate override:")
    third = _run_main(gate["mod"], gate["payload"], monkeypatch)
    assert "decision" not in third  # still the same turn — never re-blocks


def test_gate_blocks_again_on_new_turn(gate, monkeypatch):
    _run_main(gate["mod"], gate["payload"], monkeypatch)
    _run_main(gate["mod"], gate["payload"], monkeypatch)
    _transcript(gate["transcript"], [("2026-09-27T10:00:00Z", "build the thing"),
                                     ("2026-09-27T10:30:00Z", "now add tests")])
    again = _run_main(gate["mod"], gate["payload"], monkeypatch)
    assert again.get("decision") == "block"


def test_gate_honours_stop_hook_active_and_consent(gate, monkeypatch):
    p = dict(gate["payload"], stop_hook_active=True)
    assert _run_main(gate["mod"], p, monkeypatch) == {}
    _transcript(gate["transcript"], [("2026-09-27T10:00:00Z", "build"),
                                     ("2026-09-27T10:05:00Z", "Stop. Don't do anything else")])
    assert _run_main(gate["mod"], gate["payload"], monkeypatch) == {}


def test_gate_thresholds_count_unique_files(gate, monkeypatch):
    # 2 unique files written 6 times → below the >=3 threshold → no block.
    (gate["state"] / "sess-1.desloppify.json").write_text(json.dumps({
        "code_writes": 6, "code_files": ["/work/u/CODE_FILES/app/src/a.ts",
                                          "/work/u/CODE_FILES/app/src/b.ts"]}))
    assert "decision" not in _run_main(gate["mod"], gate["payload"], monkeypatch)


def test_gate3_credits_security_sentinel_dispatch(gate, monkeypatch):
    hcg, cid = gate["mod"], "sess-1"
    (gate["state"] / f"{cid}.security-scan.json").write_text(json.dumps({
        "security_files": ["server/auth.go"], "reminded": True}))
    ok, _, _ = hcg.gate3_security(cid, [], None)
    assert not ok
    tel = hcg.TELEMETRY_DIR
    tel.mkdir(parents=True, exist_ok=True)
    (tel / f"{cid}.agent-dispatches.jsonl").write_text(
        json.dumps({"ts": "2026-09-27T10:01:00Z", "agent": "security-sentinel"}) + "\n")
    ok, _, _ = hcg.gate3_security(cid, [], None)
    assert ok


# --------------------------------------------------------------------------- #
# invoke-suite-gate — naive timestamps are UTC, never a TypeError
# --------------------------------------------------------------------------- #
def test_suite_gate_naive_timestamp_is_aware():
    isg = _load("isg_ut", "invoke-suite-gate.py")
    from datetime import timezone
    naive = isg._dt("2026-09-27T10:00:00")
    aware = isg._dt("2026-09-27T10:00:00Z")
    assert naive.tzinfo is not None and aware.tzinfo is not None
    assert naive == aware  # comparable, no TypeError
    assert naive.utcoffset() == timezone.utc.utcoffset(None)
    assert isg._dt("garbage") is None


def _suite_gate_run(tmp_path, cid: str, tool_uses: list, now: str = "") -> dict:
    """Push react-hooks-patterns for this turn, write a transcript whose current
    turn made ``tool_uses`` [(name, file_path)], run the gate, return its JSON."""
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc).isoformat()
    tel = _HOOKS / ".telemetry"
    tel.mkdir(parents=True, exist_ok=True)
    (tel / f"{cid}.pushed-skills.jsonl").write_text(json.dumps(
        {"ts": now, "skills": ["react-hooks-patterns"], "categories": [],
         "source": "router", "enforce": "hard"}) + "\n", encoding="utf-8")
    lines = [{"type": "user", "timestamp": now, "message": {"role": "user", "content": "do it"}}]
    for name, fp in tool_uses:
        lines.append({"type": "assistant", "timestamp": now, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": name, "input": {"file_path": fp, "command": "ls"}}]}})
    tr = tmp_path / "t.jsonl"
    tr.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    cp = subprocess.run([sys.executable, str(_HOOKS / "invoke-suite-gate.py")],
                        input=json.dumps({"session_id": cid, "transcript_path": str(tr)}),
                        text=True, capture_output=True, timeout=20, check=False)
    return json.loads(cp.stdout.strip().splitlines()[-1])


def _isg_cleanup(cid: str) -> None:
    for suffix in ("pushed-skills.jsonl", "suite-gate.json"):
        (_HOOKS / ".telemetry" / f"{cid}.{suffix}").unlink(missing_ok=True)


def test_suite_gate_passes_turn_without_code_writes(tmp_path):
    cid = f"isg-nocode-{os.getpid()}"
    assert _suite_gate_run(tmp_path, cid, [("Bash", ""), ("Read", "/app/src/x.tsx")]) == {}
    # infra/docs-only writes are not code for the suite gate either
    # (fixed ~/.claude path: `_HOOKS` is only under `.claude/hooks/` when checked out at ~/.claude)
    assert _suite_gate_run(tmp_path, cid, [("Edit", "home/.claude/hooks/x.py"),
                                           ("Write", "/app/docs/notes.md")]) == {}
    _isg_cleanup(cid)


def test_suite_gate_ignores_code_outside_skill_surface(tmp_path):
    cid = f"isg-be-{os.getpid()}"
    assert _suite_gate_run(tmp_path, cid, [("Edit", "/app/server/internal/handler.go")]) == {}
    _isg_cleanup(cid)


def test_suite_gate_nags_once_per_turn_on_matching_code_write(tmp_path):
    from datetime import datetime, timezone
    cid = f"isg-fe-{os.getpid()}"
    now = datetime.now(timezone.utc).isoformat()   # same turn for both Stop calls
    first = _suite_gate_run(tmp_path, cid, [("Edit", "/app/src/hooks/useThing.ts")], now)
    assert first.get("decision") == "block" and "react-hooks-patterns" in first["reason"]
    assert _suite_gate_run(tmp_path, cid, [("Edit", "/app/src/hooks/useThing.ts")], now) == {}
    _isg_cleanup(cid)


def test_suite_gate_implement_satisfied_by_any_implementor():
    isg = _load("isg_ut", "invoke-suite-gate.py")
    assert isg._category_satisfied("IMPLEMENT", "implementation-engineer",
                                   {"backend-implementor-specialist"}, [], "IMPL-REPORT.md", None)
    assert not isg._category_satisfied("IMPLEMENT", "implementation-engineer",
                                       {"santa-reviewer"}, [], "IMPL-REPORT.md", None)


# --------------------------------------------------------------------------- #
# security-scan-gate — tokens, not substrings
# --------------------------------------------------------------------------- #
def test_security_scan_gate_ignores_false_positive_basenames():
    ssg = _load("ssg_ut", "security-scan-gate.py")
    for fp in ("/app/src/components/Spinner.tsx", "/app/src/hooks/useQuery.ts",
               "/app/src/utils/mapping.ts", "/app/internal/validators.go",
               "/app/src/roles/RoleBadge.tsx"):
        assert not ssg._is_security_sensitive(fp), fp
    for fp in ("/app/server/auth_handler.go", "/app/src/refreshToken.ts",
               "/app/src/lib/jwt.ts", "/app/server/middleware/cors.go",
               "/app/src/RateLimit.ts"):
        assert ssg._is_security_sensitive(fp), fp


def test_security_scan_gate_matches_derived_forms_by_stem():
    """Santa A1: plurals / derived forms of security words must still count."""
    ssg = _load("ssg_ut", "security-scan-gate.py")
    for fp in ("/app/api/authentication.py", "/app/internal/user/authorization.go",
               "/app/src/sessions.ts", "/app/app/permissions.py", "/app/app/tokens.py",
               "/app/app/oauth2.go", "/app/app/credentials.py", "/app/app/passwords.py",
               "/app/src/loginForm.tsx", "/app/src/csrfGuard.ts", "/app/src/acl.go"):
        assert ssg._is_security_sensitive(fp), fp
    for fp in ("/app/src/components/Spinner.tsx", "/app/src/hooks/useQuery.ts",
               "/app/src/utils/pinned.ts", "/app/src/validate.ts"):
        assert not ssg._is_security_sensitive(fp), fp


# --------------------------------------------------------------------------- #
# hard-completion-gate CONSENT_RE — whole-message consent only (Santa P7)
# --------------------------------------------------------------------------- #
def test_consent_re_only_matches_standalone_stop_messages():
    hcg = _load("hcg_consent_ut", "hard-completion-gate.py")
    for msg in ("stop", "Stop.", "STOP!", "Stop. Don't do anything else", "that's all",
                "don't do anything", "leave it", "no more changes", "ok stop"):
        assert hcg.CONSENT_RE.search(msg), msg
    for msg in ("stop the server and fix the login bug", "Stop X from crashing",
                "stop using sed -i in the hooks", "leave it better than you found it: refactor"):
        assert not hcg.CONSENT_RE.search(msg), msg


# --------------------------------------------------------------------------- #
# teammate-idle-gate — bounded blocks per (run, teammate) (Santa A3)
# --------------------------------------------------------------------------- #
def test_teammate_idle_gate_gives_up_after_two_blocks(tmp_path, monkeypatch):
    tig = _load("tig_ut", "teammate-idle-gate.py")
    monkeypatch.setattr(tig, "STATE_FILE", tmp_path / "state" / "teammate-idle.json")
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    run = tmp_path / "work" / ".claude" / "runs" / "20260928-x"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps(
        {"expected_artifacts": {"impl-be": ".claude/runs/20260928-x/IMPL-REPORT-BE.md"}}))
    payload = {"teammate_name": "impl-be", "cwd": str(tmp_path / "work")}

    def fire() -> dict:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        buf = io.StringIO()
        with redirect_stdout(buf):
            tig.main()
        return json.loads(buf.getvalue().strip().splitlines()[-1])

    assert fire().get("decision") == "block"
    assert fire().get("decision") == "block"
    third = fire()
    assert "decision" not in third
    assert "IMPL-REPORT-BE.md" in third.get("systemMessage", "")
    # another teammate on the same run keeps its own budget
    payload["teammate_name"] = "impl-fe"
    (run / "run.json").write_text(json.dumps({"expected_artifacts": {
        "impl-be": ".claude/runs/20260928-x/IMPL-REPORT-BE.md",
        "impl-fe": ".claude/runs/20260928-x/IMPL-REPORT-FE.md"}}))
    assert fire().get("decision") == "block"


# --------------------------------------------------------------------------- #
# dangerous-bash-gate — quoted text ignored; full-command fingerprint
# --------------------------------------------------------------------------- #
def test_dangerous_bash_gate_strips_quotes_and_hashes_full_command():
    dbg = _load("dbg_ut", "dangerous-bash-gate.py")
    quoted = 'git commit -m "switch from rm -rf to trash"'
    assert not any(p.search(dbg._strip_quoted(quoted)) for p, _, _ in dbg.DANGEROUS_PATTERNS)
    heredoc = "cat <<'EOF'\nDROP TABLE users;\nEOF\n"
    assert not any(p.search(dbg._strip_quoted(heredoc)) for p, _, _ in dbg.DANGEROUS_PATTERNS)
    assert dbg._fingerprint("cd /very/long/path/here && rm -rf A", "rm") != \
        dbg._fingerprint("cd /very/long/path/here && rm -rf B", "rm")
    assert dbg._fingerprint("rm  -rf   A", "rm") == dbg._fingerprint("rm -rf A", "rm")


# --------------------------------------------------------------------------- #
# dox_cleanup — only the untouched template is a stub
# --------------------------------------------------------------------------- #
def test_dox_cleanup_stub_detection(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "dox_cleanup_ut", _HOOKS.parent / "scripts" / "dox_cleanup.py")
    dc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dc)
    stub = tmp_path / "a" / "CLAUDE.md"
    stub.parent.mkdir()
    stub.write_text("<!-- dox:child v1 -->\n# `a/`\n\n## What lives here\n\n<One or two lines: ...>\n")
    edited = tmp_path / "b" / "CLAUDE.md"
    edited.parent.mkdir()
    edited.write_text("<!-- dox:child v1 -->\n# `b/`\n\n## What lives here\n\nThe real thing.\n")
    assert dc.is_untouched_stub(stub)
    assert not dc.is_untouched_stub(edited)
    found = [d for d, _ in dc.find_candidates(tmp_path)]
    assert found == [stub]


def test_dox_cleanup_keeps_hand_edited_agents_md(tmp_path):
    """Santa P6: a stub CLAUDE.md's sibling AGENTS.md is deleted only if it is the
    untouched pointer template."""
    spec = importlib.util.spec_from_file_location(
        "dox_cleanup_ut2", _HOOKS.parent / "scripts" / "dox_cleanup.py")
    dc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dc)
    import dox_engine
    stub_text = "<!-- dox:child v1 -->\n# `x/`\n\n## What lives here\n\n<One or two lines: ...>\n"
    for name, ptr_text in (("plain", dox_engine.pointer_text({})),
                           ("legacy", dox_engine.pointer_text({}).replace(
                               dox_engine.POINTER_MARKER + "\n", "")),
                           ("edited", "# Codex rules\n\nReal hand-written instructions.\n")):
        d = tmp_path / name
        d.mkdir()
        (d / "CLAUDE.md").write_text(stub_text)
        (d / "AGENTS.md").write_text(ptr_text)
    pairs = {doc.parent.name: ptr for doc, ptr in dc.find_candidates(tmp_path)}
    assert set(pairs) == {"plain", "legacy", "edited"}
    assert pairs["plain"] is not None and pairs["legacy"] is not None
    assert pairs["edited"] is None


def test_tdd_guard_timeouts_nest_above_validator_latency():
    """tdd-guard (Sonnet via the Agent SDK) takes 4-7.3 s per call (2026-09-30). The old
    7 s cap dropped the slow tail silently, so a test-less edit got no advisory. Each
    outer layer must outlast the inner one, all inside the 30 s PreToolUse timeout."""
    gate = _load("tdd_gate_t", "tdd-guard-gate.py").TDD_TIMEOUT_S
    launcher = _load("tdd_launch_t", "tdd_guard_launcher.py")._GATE_TIMEOUT_S
    link = next(ln for ln in json.loads((_HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))
                ["chains"]["pre-tool-use"] if ln["id"] == "tdd-guard-launcher-pre")["timeout_ms"] / 1000
    assert 12 <= gate < launcher < link < 30
