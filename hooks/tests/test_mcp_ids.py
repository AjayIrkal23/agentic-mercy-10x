"""lib/mcp_ids: the exact repo arguments every MCP nudge names (B-06, B-07)."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import mcp_ids  # noqa: E402


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    code, docs = tmp_path / "code-index", tmp_path / "doc-index"
    code.mkdir()
    docs.mkdir()
    life = mcp_ids._lifecycle()
    monkeypatch.setattr(life, "CODE_INDEX_DIR", code)
    monkeypatch.setattr(life, "DOC_INDEX_DIR", docs)
    mcp_ids.ids.cache_clear()
    return root, code, docs


def _db(path: Path, repo_id: str, source_root: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE meta (key TEXT, value TEXT)")
    conn.executemany("INSERT INTO meta VALUES (?, ?)", [("repo", repo_id), ("source_root", str(source_root))])
    conn.commit()
    conn.close()


def test_no_indexes_gives_empty_ids(repo):
    root, _, _ = repo
    assert mcp_ids.ids(str(root)) == {"jcodemunch": "", "graphify": "", "jdocmunch": ""}
    assert mcp_ids.call_lines(root) == []


def test_ids_come_from_the_indexes(repo):
    root, code, docs = repo
    _db(code / "Owner-remote-name.db", "Owner/remote-name", root)  # named after the remote, not the folder
    (root / "graphify-out").mkdir()
    (root / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    (docs / "proj.json").write_text('{"repo":"local/proj","source_root":"%s"}' % root, encoding="utf-8")
    got = mcp_ids.ids(str(root))
    assert got == {"jcodemunch": "Owner/remote-name", "graphify": str(root), "jdocmunch": "local/proj"}
    text = "\n".join(mcp_ids.call_lines(root))
    assert 'repo="Owner/remote-name"' in text and f'project_path="{root}"' in text and 'repo="local/proj"' in text


def test_project_root_refuses_home_and_non_repos(tmp_path):
    assert mcp_ids.project_root(tmp_path) is None
    assert mcp_ids.project_root(Path.home()) is None
    assert mcp_ids.project_root("") is None
