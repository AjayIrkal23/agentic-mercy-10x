"""hookify (ECC hookify runtime, Python port): repo-local `.claude/hookify.<name>.local.md` rules are
UNTRUSTED input (a cloned repo can carry them), so every limit is hard: symlinks, >64 KB files and
git-tracked files are refused, 100 rules, 400-char patterns with a ReDoS screen, 64 KB fields, a 1 s
deadline, 2,000-char messages, 5 shown. `block` denies Bash/Write calls; prompt/stop are advisory."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import hookify_rules as hr  # noqa: E402
from lib import platform as plat  # noqa: E402

if shutil.which("git") is None:
    pytest.skip("git is not on PATH", allow_module_level=True)


@pytest.fixture()
def repo(tmp_path_factory):
    r = tmp_path_factory.mktemp("hkrepo")
    subprocess.run(["git", "init", "-q", str(r)], check=True, capture_output=True)
    (r / ".claude").mkdir()
    return r


def _rule(repo: Path, name: str, fm: str, body: str = "Do not do that.") -> Path:
    p = repo / ".claude" / f"hookify.{name}.local.md"
    p.write_text(f"---\n{fm.strip()}\n---\n{body}\n", encoding="utf-8")
    return p


@pytest.fixture()
def gate():
    spec = importlib.util.spec_from_file_location(f"hk_{uuid.uuid4().hex}", HOOKS / "hookify-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(gate, monkeypatch, repo, event: str, **extra) -> dict:
    payload = {"session_id": "h1", "hook_event_name": event, "cwd": str(repo), **extra}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    gate.main()
    return json.loads(out.getvalue() or "{}")


def _bash(cmd: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


# --- parsing / trust ---------------------------------------------------------------------------------
def test_parse_basic_and_advanced_forms():
    r = hr.parse_rule("---\nname: block-rm\nenabled: true\nevent: bash\naction: block\npattern: rm\\s+-rf\n---\n"
                      "No rm -rf here.\n")
    assert (r["name"], r["event"], r["action"], r["conditions"], r["message"]) == (
        "block-rm", "bash", "block", [], "No rm -rf here.")
    r = hr.parse_rule("---\nname: warn-env\nevent: file\ntool_matcher: Edit|Write\nconditions:\n"
                      "  - field: file_path\n    operator: regex_match\n    pattern: \\.env$\n"
                      "  - field: new_text\n    operator: contains\n    pattern: API_KEY\n---\nbody\n")
    assert len(r["conditions"]) == 2 and r["tool_matcher"] == "Edit|Write" and r["action"] == "warn"
    assert r["conditions"][1] == {"field": "new_text", "operator": "contains", "pattern": "API_KEY"}


@pytest.mark.parametrize("fm", [
    "event: bash\npattern: x",                                  # no name
    "name: a\nevent: nope\npattern: x",                         # bad event
    "name: a\naction: kill\npattern: x",                        # bad action
    "name: a\npattern: x\nconditions:\n  - field: command\n    operator: contains\n    pattern: y",  # both
    "name: a\nevent: bash",                                     # neither
    "name: a\npattern: " + "x" * 401,                           # too long
    "name: a\nconditions:\n  - field: command\n    operator: matches\n    pattern: y",            # operator
    "name: a\npattern: [a, b]",                                 # flow collection
    "name: a\npattern: |\n  multi",                             # block scalar
])
def test_parse_rejects(fm):
    with pytest.raises(ValueError) as e:
        hr.parse_rule(f"---\n{fm}\n---\nbody\n")
    assert "x" * 50 not in str(e.value)  # never echoes the pattern


def test_regex_safety_screen():
    for p in ("(a+)+", "(a|b)*c", r"\1", "(?<=x)", ".*foo.*", r"(\w+\s?)+$"):
        assert not hr.is_safe_regex(p), p
    for p in (r"rm\s+-rf", r"console\.log\(", r"\.env$", r"^git\s+push"):
        assert hr.is_safe_regex(p), p


@pytest.mark.skipif(plat.IS_WINDOWS, reason="symlinks need privileges on Windows")
def test_symlinked_rule_is_refused(repo, tmp_path):
    real = tmp_path / "real.md"
    real.write_text("---\nname: a\npattern: x\n---\nb\n", encoding="utf-8")
    os.symlink(str(real), str(repo / ".claude" / "hookify.link.local.md"))
    rules, diags = hr.load_rules(str(repo))
    assert rules == [] and any("symlink" in d for d in diags)


def test_load_limits_tracked_oversize_count_and_malformed(repo):
    _rule(repo, "tracked", "name: tracked\npattern: x")
    subprocess.run(["git", "-C", str(repo), "add", "-f", ".claude"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
                   check=True, capture_output=True)
    _rule(repo, "big", "name: big\npattern: x", "y" * (65 * 1024))
    _rule(repo, "broken", "name: Bad Name!\npattern: x")
    _rule(repo, "ok", "name: ok\npattern: x")
    rules, diags = hr.load_rules(str(repo))
    assert [r["name"] for r in rules] == ["ok"]
    assert any("tracked" in d for d in diags) and any("oversize" in d for d in diags)
    assert any("broken" in d for d in diags)


def test_at_most_100_rules(repo):
    for i in range(101):
        _rule(repo, f"r{i:03d}", f"name: r{i:03d}\npattern: x{i}")
    rules, _ = hr.load_rules(str(repo))
    assert len(rules) == 100


def test_cache_skips_reparse_until_the_file_changes(repo, monkeypatch):
    p = _rule(repo, "c", "name: c\npattern: x")
    assert len(hr.load_rules(str(repo))[0]) == 1

    def boom(_text):
        raise ValueError("parse called")
    monkeypatch.setattr(hr, "parse_rule", boom)
    assert [r["name"] for r in hr.load_rules(str(repo))[0]] == ["c"]
    p.write_text("---\nname: c\npattern: xyz\n---\nchanged body\n", encoding="utf-8")
    rules, diags = hr.load_rules(str(repo))
    assert rules == [] and any("parse called" in d for d in diags)
    assert list((plat.state_dir() / "hookify-cache").glob("*.json"))


def test_unknown_tracking_disables_rules(repo, monkeypatch):
    _rule(repo, "a", "name: a\npattern: x")
    monkeypatch.setattr(hr, "_tracked_paths", lambda root: None)
    assert hr.load_rules(str(repo)) == ([], ["tracking unknown: rules disabled"])


# --- evaluation / output ------------------------------------------------------------------------------
def test_bash_block_denies_with_the_untrusted_prefix(gate, repo, monkeypatch):
    _rule(repo, "block-rm-home", "name: block-rm-home\nevent: bash\naction: block\npattern: rm\\s+-rf\\s+~",
          "Never delete the home dir.")
    hso = _run(gate, monkeypatch, repo, "PreToolUse", **_bash("rm -rf ~/x"))["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert hso["permissionDecisionReason"].startswith("[untrusted local rule block-rm-home]")
    assert "Never delete the home dir." in hso["permissionDecisionReason"]
    assert _run(gate, monkeypatch, repo, "PreToolUse", **_bash("ls")) == {}
    assert _run(gate, monkeypatch, repo, "PreToolUse", tool_name="Write",
                tool_input={"file_path": str(repo / "rm -rf ~"), "content": "rm -rf ~"}) == {}


def test_bash_warn_is_context_only(gate, repo, monkeypatch):
    _rule(repo, "warn-push", "name: warn-push\nevent: bash\npattern: ^git\\s+push")
    hso = _run(gate, monkeypatch, repo, "PreToolUse", **_bash("git push origin x"))["hookSpecificOutput"]
    assert "permissionDecision" not in hso and "[untrusted local rule warn-push]" in hso["additionalContext"]


def test_file_conditions_all_must_hold(gate, repo, monkeypatch):
    _rule(repo, "warn-env-key", "name: warn-env-key\nevent: file\nconditions:\n"
          "  - field: file_path\n    operator: regex_match\n    pattern: \\.env$\n"
          "  - field: new_text\n    operator: contains\n    pattern: API_KEY")
    hit = _run(gate, monkeypatch, repo, "PreToolUse", tool_name="Edit",
               tool_input={"file_path": str(repo / ".env"), "old_string": "", "new_string": "API_KEY=1"})
    assert "warn-env-key" in hit["hookSpecificOutput"]["additionalContext"]
    assert _run(gate, monkeypatch, repo, "PreToolUse", tool_name="Edit",
                tool_input={"file_path": str(repo / ".env"), "old_string": "", "new_string": "X=1"}) == {}
    win = _run(gate, monkeypatch, repo, "PreToolUse", tool_name="Edit",
               tool_input={"file_path": "C" + ":\\proj\\.env", "old_string": "", "new_string": "API_KEY=2"})
    assert "warn-env-key" in win["hookSpecificOutput"]["additionalContext"]


def test_tool_matcher_scopes_an_all_rule(gate, repo, monkeypatch):
    _rule(repo, "warn-any", "name: warn-any\nevent: all\ntool_matcher: Bash\npattern: secretword")
    assert _run(gate, monkeypatch, repo, "PreToolUse", **_bash("echo secretword"))
    assert _run(gate, monkeypatch, repo, "PreToolUse", tool_name="Edit",
                tool_input={"file_path": str(repo / "a.txt"), "new_string": "secretword"}) == {}


def test_prompt_rules_are_advisory_even_when_block(gate, repo, monkeypatch):
    _rule(repo, "no-prod", "name: no-prod\nevent: prompt\naction: block\npattern: deploy.*prod", "Ask first.")
    out = _run(gate, monkeypatch, repo, "UserPromptSubmit", prompt="deploy to prod now")
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit" and "permissionDecision" not in hso
    assert hso["additionalContext"].startswith("[untrusted local rule no-prod]")
    assert "(block requested; advisory on this event)" in hso["additionalContext"]


def test_stop_rules_honour_stop_hook_active(gate, repo, monkeypatch):
    _rule(repo, "e2e", "name: e2e\nevent: stop\npattern: .*", "Run the e2e suite before saying done.")
    out = _run(gate, monkeypatch, repo, "Stop", stop_hook_active=False, last_assistant_message="done")
    assert "e2e suite" in out["systemMessage"]
    assert _run(gate, monkeypatch, repo, "Stop", stop_hook_active=True, last_assistant_message="done") == {}


def test_stop_rules_print_a_top_level_system_message(gate, repo, monkeypatch):
    """REVIEW2 Fix 4: Stop accepts only a top-level block or systemMessage; hookSpecificOutput never arrives."""
    _rule(repo, "stop-check", "name: stop-check\nevent: stop\npattern: all done", "Run the smoke test first.")
    out = _run(gate, monkeypatch, repo, "Stop", last_assistant_message="All done, shipped.")
    assert set(out) == {"systemMessage"}
    assert out["systemMessage"].startswith("[untrusted local rule stop-check]")
    assert "smoke test" in out["systemMessage"]


def test_dispatch_forwards_the_stop_rule_once_the_link_is_a_gate(repo, monkeypatch, tmp_path):
    """The dispatch end of Fix 4: a Stop gate's systemMessage is passed through. The `hookify-stop` link's
    type in dispatch.config.json is integrate-owned (REVIEW2-FIX-integrate cross-package item); this
    pins the contract with the type forced to `gate`."""
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    for var in ("MERCY_MOD_SESSION", "MERCY_MOD_OWNED", "MERCY_MOD_FAILED"):
        monkeypatch.delenv(var, raising=False)
    spec = importlib.util.spec_from_file_location(f"dp_{uuid.uuid4().hex}", HOOKS / "dispatch.py")
    dp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dp)
    cfg = json.loads((HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))
    link = next(ln for ln in cfg["chains"]["stop"] if ln["id"] == "hookify-stop")
    link["type"] = "gate"
    _rule(repo, "stop-check", "name: stop-check\nevent: stop\npattern: all done", "Run the smoke test first.")
    payload = {"session_id": f"hk-{uuid.uuid4().hex}", "hook_event_name": "Stop", "cwd": str(repo),
               "stop_hook_active": False, "last_assistant_message": "All done, shipped."}
    out = dp.dispatch("stop", payload, cfg, {"hookify-stop"})
    assert set(out) == {"systemMessage"} and "smoke test" in out["systemMessage"]


def test_fields_are_judged_on_their_first_64kb(gate, repo, monkeypatch):
    _rule(repo, "marker", "name: marker\nevent: bash\npattern: zzmarker")
    far = "a" * 100_000 + " zzmarker " + "a" * 100_000
    assert _run(gate, monkeypatch, repo, "PreToolUse", **_bash(far)) == {}
    near = "a" * 1_000 + " zzmarker " + "a" * 199_000
    assert _run(gate, monkeypatch, repo, "PreToolUse", **_bash(near))


def test_deadline_fails_open_and_logs(gate, repo, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    _rule(repo, "d", "name: d\nevent: bash\naction: block\npattern: rm")
    monkeypatch.setattr(hr, "MAX_EVAL_S", 0.0)
    assert _run(gate, monkeypatch, repo, "PreToolUse", **_bash("rm x")) == {}
    rows = [json.loads(line) for p in (tmp_path / "tel").glob("*.jsonl")
            for line in p.read_text(encoding="utf-8").splitlines()]
    assert any(r.get("decision") == "deadline" for r in rows)


def test_100_rules_on_64kb_finish_under_a_second(gate, repo, monkeypatch):
    for i in range(100):
        _rule(repo, f"t{i:03d}", f"name: t{i:03d}\nevent: bash\npattern: never{i}here")
    t0 = time.perf_counter()
    assert _run(gate, monkeypatch, repo, "PreToolUse", **_bash("x " * 32_000)) == {}
    assert time.perf_counter() - t0 < 1.0


def test_message_caps(gate, repo, monkeypatch):
    _rule(repo, "long", "name: long\nevent: bash\npattern: hello", "m" * 10_000)
    ctx = _run(gate, monkeypatch, repo, "PreToolUse", **_bash("hello"))["hookSpecificOutput"]["additionalContext"]
    assert "m" * 2000 + " …" in ctx and "m" * 2001 not in ctx
    for i in range(6):
        _rule(repo, f"w{i}", f"name: w{i}\nevent: bash\npattern: hello", f"msg {i}")
    ctx = _run(gate, monkeypatch, repo, "PreToolUse", **_bash("hello"))["hookSpecificOutput"]["additionalContext"]
    assert ctx.count("[untrusted local rule") == 5 and "(+2 more)" in ctx


def test_no_rules_dir_or_no_repo_is_fast(gate, monkeypatch, tmp_path_factory):
    bare = tmp_path_factory.mktemp("hknorepo")
    gitonly = tmp_path_factory.mktemp("hkgit")
    (gitonly / ".git").mkdir()
    for cwd in (bare, gitonly):
        t0 = time.perf_counter()
        assert _run(gate, monkeypatch, cwd, "PreToolUse", **_bash("rm -rf x")) == {}
        assert time.perf_counter() - t0 < 0.05
    monkeypatch.setenv("HOME", str(gitonly))
    monkeypatch.setenv("USERPROFILE", str(gitonly))
    assert _run(gate, monkeypatch, gitonly, "PreToolUse", **_bash("rm -rf x")) == {}


def test_malformed_stdin(gate, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    gate.main()
    assert out.getvalue().strip() == "{}"
