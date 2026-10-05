"""mcp-post-hints.py — PostToolUse "call this MCP now" hints (2026-09-28)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

_spec = importlib.util.spec_from_file_location("mcp_post_hints", _HOOKS / "mcp-post-hints.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)  # type: ignore[union-attr]


def _repo(tmp_path: Path) -> Path:
    r = tmp_path / "app"
    (r / "src" / "auth").mkdir(parents=True)
    (r / "src" / "components").mkdir(parents=True)
    (r / "db" / "migrations").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    return r


def _run(monkeypatch, payload: dict, state: dict, servers=("semgrep", "context7", "reticle", "jcodemunch"),
         port=None) -> list[str]:
    from lib import code_files
    # lib.code_files skips "/tmp/" paths (scratch) — tmp_path lives there, so judge by extension.
    monkeypatch.setattr(code_files, "is_code_file",
                        lambda p: Path(str(p)).suffix in code_files.CODE_EXTENSIONS)
    monkeypatch.setattr(H, "_server", lambda name: name in servers)
    monkeypatch.setattr(H, "_dev_port", lambda: port)
    return H.hints(payload, state)


def _edit(fp: Path, new: str, old: str = "") -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": str(fp), "old_string": old, "new_string": new}}


def test_security_file_triggers_semgrep_once(tmp_path, monkeypatch):
    fp = _repo(tmp_path) / "src" / "auth" / "session.ts"
    st: dict = {}
    first = _run(monkeypatch, _edit(fp, "export const x = 1"), st)
    assert any("semgrep_scan" in h and str(fp) in h for h in first)
    assert not any("semgrep_scan" in h for h in _run(monkeypatch, _edit(fp, "export const y = 2"), st))


def test_semgrep_hint_skipped_when_server_missing(tmp_path, monkeypatch):
    fp = _repo(tmp_path) / "src" / "auth" / "session.ts"
    assert not any("semgrep" in h for h in _run(monkeypatch, _edit(fp, "x"), {}, servers=()))


def test_new_third_party_import_triggers_context7(tmp_path, monkeypatch):
    fp = _repo(tmp_path) / "src" / "api.ts"
    new = "import { z } from 'zod'\nimport x from './local'\nimport fs from 'node:fs'\nimport { useQuery } from '@tanstack/react-query/build'"
    hs = _run(monkeypatch, _edit(fp, new, old="import { z } from 'zod'"), {})
    c7 = [h for h in hs if "context7" in h]
    assert c7 and "@tanstack/react-query" in c7[0] and "zod" not in c7[0] and "local" not in c7[0]


def test_python_stdlib_and_local_imports_ignored(tmp_path, monkeypatch):
    r = _repo(tmp_path)
    (r / "mypkg").mkdir()
    fp = r / "svc.py"
    hs = _run(monkeypatch, {"tool_name": "Write", "tool_input": {
        "file_path": str(fp), "content": "import os\nfrom mypkg import a\nfrom pydantic import BaseModel\n"}}, {})
    c7 = [h for h in hs if "context7" in h]
    assert c7 and "pydantic" in c7[0] and "mypkg" not in c7[0] and "os" not in c7[0].split("(")[1]


def test_fe_component_hint_only_when_app_running(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    # reticle is named only where the repo carries its plugin (audit G-14; WP1 test_router_wp1_mcp.py)
    (repo / "package.json").write_text('{"devDependencies": {"@reticlehq/vite": "^1"}}')
    fp = repo / "src" / "components" / "Badge.tsx"
    assert not any("reticle" in h for h in _run(monkeypatch, _edit(fp, "x"), {}, port=None))
    assert any("reticle" in h and ":5173" in h for h in _run(monkeypatch, _edit(fp, "x"), {}, port=5173))


def test_migration_triggers_postgres_checklist(tmp_path, monkeypatch):
    fp = _repo(tmp_path) / "db" / "migrations" / "0007_add_index.sql"
    assert any("postgres-patterns" in h for h in _run(monkeypatch, _edit(fp, "CREATE INDEX"), {}))


def test_blast_radius_after_more_than_three_files(tmp_path, monkeypatch):
    r = _repo(tmp_path)
    st: dict = {}
    outs = [_run(monkeypatch, _edit(r / "src" / f"m{i}.ts", "x"), st) for i in range(5)]
    blast = [i for i, hs in enumerate(outs) if any("get_blast_radius" in h for h in hs)]
    assert blast == [3]


def test_session_start_memory_directive(monkeypatch):
    spec = importlib.util.spec_from_file_location("mem_load", _HOOKS / "memory-load-on-start.py")
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)  # type: ignore[union-attr]
    monkeypatch.setattr(M, "memory_server_configured", lambda: True)
    assert 'search_nodes("GO_UDP")' in M.search_directive("GO_UDP", "startup")
    assert M.search_directive("GO_UDP", "compact") == ""
    assert M.search_directive("", "startup") == ""          # $HOME / no repo: no project work
    monkeypatch.setattr(M, "memory_server_configured", lambda: False)
    assert M.search_directive("GO_UDP", "startup") == ""


def test_non_write_tool_and_bad_payload_fail_open(monkeypatch):
    assert _run(monkeypatch, {"tool_name": "Read", "tool_input": {"file_path": "/x/auth.ts"}}, {}) == []
    cp = subprocess.run([sys.executable, str(_HOOKS / "mcp-post-hints.py")], input="not json",
                        text=True, capture_output=True, timeout=10, check=False)
    assert cp.stdout.strip() == "{}"
