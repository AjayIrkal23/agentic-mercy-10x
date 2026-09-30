"""blocking-doc-enforcer: `git commit` in a doc-layout repo (GO_UDP / UDP_PLATFORM) is
denied until the touched surface's docs AND PROJECT_LINKAGES.md are written this
session; every other repo, amends, and sessions without code writes pass."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS))


def _gate(tmp_path, monkeypatch, command: str, cwd: str, state: dict | None) -> dict:
    spec = importlib.util.spec_from_file_location("bde_t", HOOKS / "blocking-doc-enforcer.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)
    if state is not None:
        (tmp_path / "sid-1.doc-enforcer.json").write_text(json.dumps(state), encoding="utf-8")
    payload = {"session_id": "sid-1", "tool_name": "Bash", "cwd": cwd,
               "tool_input": {"command": command}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    return json.loads(buf.getvalue() or "{}")


BE = {"be_touched": True, "fe_touched": False, "code_files": ["/work/GO_UDP/server/a.go"]}


def _denied(out: dict) -> bool:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"


def test_blocks_backend_commit_without_docs(tmp_path, monkeypatch):
    out = _gate(tmp_path, monkeypatch, "git commit -m x", "/work/GO_UDP",
                {**BE, "be_docs_written": False, "linkages_written": False})
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert _denied(out) and "server_docs/" in reason and "PROJECT_LINKAGES.md" in reason


def test_passes_once_docs_and_linkages_are_written(tmp_path, monkeypatch):
    out = _gate(tmp_path, monkeypatch, "git commit -m x", "/work/GO_UDP",
                {**BE, "be_docs_written": True, "linkages_written": True})
    assert not _denied(out)


def test_linkages_alone_still_missing_docs_blocks(tmp_path, monkeypatch):
    out = _gate(tmp_path, monkeypatch, "git commit -m x", "/work/GO_UDP",
                {**BE, "be_docs_written": False, "linkages_written": True})
    assert _denied(out)


def test_other_repos_amends_and_no_state_pass(tmp_path, monkeypatch):
    bad = {**BE, "be_docs_written": False, "linkages_written": False}
    assert not _denied(_gate(tmp_path, monkeypatch, "git commit -m x", "/work/shop", bad))
    assert not _denied(_gate(tmp_path, monkeypatch, "git commit --amend", "/work/GO_UDP", bad))
    assert not _denied(_gate(tmp_path / "none", monkeypatch, "git commit -m x", "/work/GO_UDP", None))
