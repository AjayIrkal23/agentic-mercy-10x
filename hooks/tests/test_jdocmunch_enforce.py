"""jdocmunch-enforce (jdoc-doc-steer) — audit 2026-10-05 B1-12.

The steer must only nudge whole reads of LARGE indexed docs; small files, sliced
reads and the mandated orientation docs are read directly, and a no-op prints `{}`
so the dispatcher's output-rate metric means something.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location("jde", HOOKS / "jdocmunch-enforce.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def env(tmp_path, monkeypatch):
    m = _mod()
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    idx = tmp_path / "doc-index"
    idx.mkdir()
    (idx / "repo.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(m, "INDEX_DIR", idx)
    monkeypatch.setattr(m, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(m, "_repo_root", lambda: repo)
    return m, repo


def run(m, monkeypatch, tool_input: dict) -> dict:
    payload = {"session_id": "t-jde", "tool_name": "Read", "tool_input": tool_input}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    m.handle_pre_tool_use()
    return json.loads(out.getvalue())


def test_large_doc_whole_read_is_steered(env, monkeypatch):
    m, repo = env
    big = repo / "docs" / "guide.md"
    big.write_text("# h\n" + "x" * 20000, encoding="utf-8")
    assert "jDocMunch" in run(m, monkeypatch, {"file_path": str(big)}).get("additionalContext", "")


def test_small_doc_is_not_steered(env, monkeypatch):
    m, repo = env
    small = repo / "docs" / "short.md"
    small.write_text("# short\nline\n", encoding="utf-8")
    assert run(m, monkeypatch, {"file_path": str(small)}) == {}


def test_sliced_read_is_not_steered(env, monkeypatch):
    m, repo = env
    big = repo / "docs" / "guide.md"
    big.write_text("x" * 20000, encoding="utf-8")
    assert run(m, monkeypatch, {"file_path": str(big), "offset": 10, "limit": 40}) == {}


def test_codex_md_is_read_directly(env, monkeypatch):
    m, repo = env
    codex = repo / "CODEX.md"
    codex.write_text("x" * 20000, encoding="utf-8")
    assert run(m, monkeypatch, {"file_path": str(codex)}) == {}


def test_non_doc_noop_prints_empty_object(env, monkeypatch):
    m, repo = env
    assert run(m, monkeypatch, {"file_path": str(repo / "app.py")}) == {}
