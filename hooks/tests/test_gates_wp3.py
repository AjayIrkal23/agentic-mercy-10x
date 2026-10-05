"""Audit 2026-10-05 WP3: first-write-skill-gate stops wasting a turn, tdd-guard skips
non-code edits with neutral wording (B1-20), the destructive-connector ask gate (G-02),
and the tdd-guard link is deferred off the critical path (B1-02)."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _main(mod, payload: dict, monkeypatch) -> dict:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    mod.main()
    out = buf.getvalue().strip()
    return json.loads(out) if out else {}


# ---- first-write-skill-gate ------------------------------------------------ #
def _fw(tmp_path, monkeypatch):
    mod = _load("fw_gate", "first-write-skill-gate.py")
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mod, "TELEMETRY_DIR", tmp_path / "tel")
    return mod


def _write(path: str, sid: str = "fw-s1") -> dict:
    return {"session_id": sid, "tool_name": "Write", "tool_input": {"file_path": path, "content": "x"}}


def test_first_code_write_is_allowed_with_the_skill_paths(tmp_path, monkeypatch):
    mod = _fw(tmp_path, monkeypatch)
    out = _main(mod, _write("/repo/server/src/a.ts"), monkeypatch)
    hso = out["hookSpecificOutput"]
    assert hso.get("permissionDecision") in (None, "allow")
    ctx = hso["additionalContext"]
    assert "backend-standards-always-follow/SKILL.md" in ctx
    assert os.path.isabs(ctx.split("Read ", 1)[1].split()[0])


def test_hint_once_per_session_per_surface(tmp_path, monkeypatch):
    mod = _fw(tmp_path, monkeypatch)
    assert _main(mod, _write("/repo/server/src/a.ts"), monkeypatch)
    assert _main(mod, _write("/repo/server/src/b.ts"), monkeypatch) == {}
    fe = _main(mod, _write("/repo/src/components/X.tsx"), monkeypatch)
    assert "frontend-standards-always-follow" in fe["hookSpecificOutput"]["additionalContext"]
    assert _main(mod, _write("/repo/src/components/Y.tsx"), monkeypatch) == {}
    assert _main(mod, _write("/repo/server/src/c.ts", sid="fw-s2"), monkeypatch)


def test_no_hint_when_a_baseline_skill_was_loaded(tmp_path, monkeypatch):
    mod = _fw(tmp_path, monkeypatch)
    (tmp_path / "tel").mkdir()
    (tmp_path / "tel" / "fw-s1.skill-invocations.jsonl").write_text(
        json.dumps({"skill": "backend-standards-always-follow"}) + "\n", encoding="utf-8")
    assert _main(mod, _write("/repo/server/src/a.ts"), monkeypatch) == {}


def test_non_code_write_is_silent(tmp_path, monkeypatch):
    mod = _fw(tmp_path, monkeypatch)
    assert _main(mod, _write("/repo/README.md"), monkeypatch) == {}


# ---- tdd-guard (B1-20) ---------------------------------------------------- #
def _active_repo(tmp_path) -> Path:
    repo = tmp_path / "proj"
    (repo / ".claude" / "tdd-guard" / "data").mkdir(parents=True)
    (repo / ".claude" / "tdd-guard" / "data" / "config.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _fake_tdd_guard(tmp_path) -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "tdd-guard"
    marker = tmp_path / "called"
    fake.write_text(f"#!/bin/sh\ncat >/dev/null\ntouch {marker}\n"
                    "echo '{\"decision\":\"block\",\"reason\":\"write a test\"}'\n", encoding="utf-8")
    fake.chmod(0o755)
    return bindir


def _launch(tmp_path, repo: Path, file_path: str) -> str:
    bindir = tmp_path / "bin" if (tmp_path / "bin").exists() else _fake_tdd_guard(tmp_path)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo), "PATH": f"{bindir}:{os.environ['PATH']}"}
    payload = {"session_id": "t", "tool_name": "Edit",
               "tool_input": {"file_path": file_path, "old_string": "a", "new_string": "b"}}
    proc = subprocess.run([sys.executable, str(HOOKS / "tdd_guard_launcher.py")], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=30, env=env)
    return proc.stdout


def test_launcher_skips_non_code_edits(tmp_path):
    repo = _active_repo(tmp_path)
    assert _launch(tmp_path, repo, str(repo / "README.md")).strip() == ""
    assert not (tmp_path / "called").exists()
    assert "write a test" in _launch(tmp_path, repo, str(repo / "src" / "a.ts"))
    assert (tmp_path / "called").exists()


def test_tdd_advisory_is_stack_neutral():
    gate = _load("tdd_gate", "tdd-guard-gate.py")
    msg = json.loads(gate._advisory("no test"))["hookSpecificOutput"]["additionalContext"]
    assert "golang" not in msg and "make tdd" not in msg
    assert "test-driven-development" in msg


def test_tdd_link_is_deferred_in_the_live_config():
    cfg = json.loads((HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))
    link = next(ln for ln in cfg["chains"]["pre-tool-use"] if ln["id"] == "tdd-guard-launcher-pre")
    assert link.get("defer") is True


# ---- connector-ask-gate (G-02) -------------------------------------------- #
def _conn(tool: str, monkeypatch) -> dict:
    mod = _load("conn_gate", "connector-ask-gate.py")
    return _main(mod, {"session_id": "c", "tool_name": tool, "tool_input": {}}, monkeypatch)


def test_destructive_connector_tools_ask(monkeypatch):
    for tool in ("mcp__claude_ai_Zoho_Books__delete_invoice", "mcp__claude_ai_Google_Drive__trash_file",
                 "mcp__claude_ai_Google_Drive__share_file", "mcp__claude_ai_Apollo_io__apollo_emailer_messages_send_now",
                 "mcp__plugin_small-business_shopify__bulk-update-product-status",
                 "mcp__claude_ai_Claude_Docs__delete", "mcp__plugin_small-business_shopify__graphql_mutation"):
        hso = _conn(tool, monkeypatch).get("hookSpecificOutput") or {}
        assert hso.get("permissionDecision") == "ask", tool
        assert tool.split("__")[-1] in hso["permissionDecisionReason"]


def test_read_only_connector_tools_pass(monkeypatch):
    for tool in ("mcp__claude_ai_Zoho_Books__list_invoices", "mcp__claude_ai_Google_Drive__search_files",
                 "mcp__claude_ai_Apollo_io__apollo_contacts_search", "mcp__plugin_pdf-viewer_pdf__display_pdf",
                 "mcp__claude_ai_Google_Drive__read_file_content", "mcp__memory__delete_entities"):
        assert _conn(tool, monkeypatch) == {}, tool


def test_connector_gate_is_wired():
    cfg = json.loads((HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))
    link = next(ln for ln in cfg["chains"]["pre-tool-use"] if ln["id"] == "connector-ask-gate")
    assert link["type"] == "gate"
    assert re.fullmatch(link["tools"], "mcp__claude_ai_Zoho_Books__delete_invoice")
    assert re.fullmatch(link["tools"], "mcp__plugin_small-business_shopify__create-product")
    assert not re.fullmatch(link["tools"], "mcp__jcodemunch__search_symbols")
