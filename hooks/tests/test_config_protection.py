"""config-protection-gate.py (ECC config-protection, ported as an ask): an EXISTING linter/formatter config
asks before a Write/Edit/MultiEdit/NotebookEdit unless the turn's human prompt asked for it; new configs,
build configs (vite/jest/tsconfig/pyproject/package.json) and ~/.claude are free; an interactive ask
repeats until approved; a subagent / unattended run gets a logged advisory (once per file per session)
instead of a prompt nobody can answer."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import platform as plat  # noqa: E402


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("CLAUDE_WORKBENCH_UNATTENDED", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


@pytest.fixture()
def cp():
    spec = importlib.util.spec_from_file_location(f"cp_{uuid.uuid4().hex}", HOOKS / "config-protection-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    return r


def _run(mod, monkeypatch, payload) -> dict:
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload if isinstance(payload, str) else json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    mod.main()
    return json.loads(out.getvalue() or "{}")


def _edit(path, sid=None, tool="Edit", transcript=None, **extra) -> dict:
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    p = {"tool_name": tool, "tool_input": {key: str(path), "old_string": "a", "new_string": "b"},
         "session_id": sid or f"cp-{uuid.uuid4().hex}", **extra}
    if transcript:
        p["transcript_path"] = str(transcript)
    return p


def _transcript(tmp_path: Path, prompt_text: str, tail: list | None = None) -> Path:
    t = tmp_path / f"t-{uuid.uuid4().hex}.jsonl"
    rows = [{"type": "user", "message": {"role": "user", "content": prompt_text}, "timestamp": "2026-10-29T10:00:00Z"}]
    rows += tail or []
    t.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return t


def _decision(out: dict) -> str | None:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision")


def test_every_protected_basename_asks_when_it_exists(cp, repo, monkeypatch):
    for base in sorted(cp.PROTECTED):
        f = repo / base
        f.write_text("{}\n", encoding="utf-8")
        hso = _run(cp, monkeypatch, _edit(f))["hookSpecificOutput"]
        assert hso["permissionDecision"] == "ask", base
        assert base in hso["permissionDecisionReason"] and "fix the source" in hso["permissionDecisionReason"].lower()


def test_a_new_config_does_not_ask(cp, repo, monkeypatch):
    assert _run(cp, monkeypatch, _edit(repo / ".eslintrc.json", tool="Write")) == {}


@pytest.mark.parametrize("base,want", [
    ("eslint.config.base.mjs", "ask"), (".prettierrc.shared.yml", "ask"), (".eslintrc.ci.json", "ask"),
    ("vite.config.ts", None), ("vitest.config.ts", None), ("jest.config.js", None), ("tsconfig.json", None),
    ("pyproject.toml", None), ("package.json", None),
])
def test_split_configs_and_unprotected_build_configs(cp, repo, monkeypatch, base, want):
    f = repo / base
    f.write_text("x\n", encoding="utf-8")
    assert _decision(_run(cp, monkeypatch, _edit(f))) == want


def test_basename_match_is_case_insensitive(cp, repo, monkeypatch):
    f = repo / "ESLINT.CONFIG.JS"
    f.write_text("x\n", encoding="utf-8")
    assert _decision(_run(cp, monkeypatch, _edit(f))) == "ask"


@pytest.mark.skipif(plat.IS_WINDOWS, reason="symlinks need privileges on Windows")
def test_dangling_symlink_counts_as_existing(cp, repo, monkeypatch, tmp_path):
    link = repo / ".eslintrc.json"
    os.symlink(str(tmp_path / "nowhere"), str(link))
    assert _decision(_run(cp, monkeypatch, _edit(link))) == "ask"


@pytest.mark.parametrize("prompt,base,want", [
    ("tune the eslint rules for hooks", "eslint.config.mjs", None),
    ("fix the lint config", ".prettierrc", None),
    ("update .markdownlint.json", ".markdownlint.json", None),
    ("fix the failing tests", ".prettierrc", "ask"),
])
def test_prompt_escape(cp, repo, monkeypatch, tmp_path, prompt, base, want):
    f = repo / base
    f.write_text("x\n", encoding="utf-8")
    t = _transcript(tmp_path, prompt)
    assert _decision(_run(cp, monkeypatch, _edit(f, transcript=t))) == want


def test_a_tool_result_mentioning_the_tool_is_no_escape(cp, repo, monkeypatch, tmp_path):
    f = repo / ".eslintrc.json"
    f.write_text("x\n", encoding="utf-8")
    tool_row = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "x", "content": "eslint failed: fix the lint config"}]}}
    t = _transcript(tmp_path, "fix the failing tests", tail=[tool_row])
    assert _decision(_run(cp, monkeypatch, _edit(f, transcript=t))) == "ask"


def test_claude_dir_is_exempt(cp, monkeypatch, tmp_path):
    cc = tmp_path / "cc"
    cc.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cc))
    f = cc / "biome.json"
    f.write_text("{}\n", encoding="utf-8")
    assert _run(cp, monkeypatch, _edit(f)) == {}


def test_an_interactive_ask_repeats_until_approved(cp, repo, monkeypatch):
    """REVIEW2 Fix 3: a declined ask must not turn into an allow on the retry."""
    f = repo / ".eslintrc.json"
    f.write_text("{}\n", encoding="utf-8")
    sid = f"c1-{uuid.uuid4().hex}"
    assert _decision(_run(cp, monkeypatch, _edit(f, sid=sid))) == "ask"
    assert _decision(_run(cp, monkeypatch, _edit(f, sid=sid))) == "ask"


def test_the_advisory_is_once_per_file_per_session(cp, repo, monkeypatch):
    f = repo / ".eslintrc.json"
    f.write_text("{}\n", encoding="utf-8")
    sid = f"c2-{uuid.uuid4().hex}"
    hso = _run(cp, monkeypatch, _edit(f, sid=sid, agent_id="a1"))["hookSpecificOutput"]
    assert "ask downgraded: subagent" in hso["additionalContext"]
    assert _run(cp, monkeypatch, _edit(f, sid=sid, agent_id="a1")) == {}
    hso = _run(cp, monkeypatch, _edit(f, agent_id="a1"))["hookSpecificOutput"]   # another session advises again
    assert "ask downgraded: subagent" in hso["additionalContext"]


def test_subagent_and_unattended_runs_get_an_advisory(cp, repo, monkeypatch):
    f = repo / ".eslintrc.json"
    f.write_text("{}\n", encoding="utf-8")
    hso = _run(cp, monkeypatch, _edit(f, agent_id="a1"))["hookSpecificOutput"]
    assert "permissionDecision" not in hso and "ask downgraded: subagent" in hso["additionalContext"]
    monkeypatch.setenv("CLAUDE_WORKBENCH_UNATTENDED", "1")
    hso = _run(cp, monkeypatch, _edit(f))["hookSpecificOutput"]
    assert "permissionDecision" not in hso and "ask downgraded: unattended" in hso["additionalContext"]


def test_notebook_read_and_malformed_payloads(cp, repo, monkeypatch):
    f = repo / ".prettierrc.json"
    f.write_text("{}\n", encoding="utf-8")
    assert _decision(_run(cp, monkeypatch, _edit(f, tool="NotebookEdit"))) == "ask"
    assert _run(cp, monkeypatch, {"tool_name": "Read", "tool_input": {"file_path": str(f)}, "session_id": "r"}) == {}
    assert _run(cp, monkeypatch, "not json") == {}


def test_multiedit_shape_with_edits_list(cp, repo, monkeypatch):
    f = repo / "biome.json"
    f.write_text("{}\n", encoding="utf-8")
    payload = {"tool_name": "MultiEdit", "tool_input": {"edits": [{"file_path": str(f), "old_string": "a"}]},
               "session_id": f"cp-{uuid.uuid4().hex}"}
    assert _decision(_run(cp, monkeypatch, payload)) == "ask"


def test_windows_path_spelling(cp, repo, monkeypatch):
    p = str(repo) + "\\.eslintrc.json"   # a real path on Windows; a backslash-named file on POSIX
    Path(p).write_text("{}\n", encoding="utf-8")
    assert _decision(_run(cp, monkeypatch, _edit(p))) == "ask"


def test_relative_path_resolves_against_cwd(cp, repo, monkeypatch):
    (repo / ".stylelintrc.json").write_text("{}\n", encoding="utf-8")
    assert _decision(_run(cp, monkeypatch, _edit(".stylelintrc.json", cwd=str(repo)))) == "ask"
