"""G6: no machine home literals in tracked Markdown (audit 2026-10-05 J-05, WP7)."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _gate():
    spec = importlib.util.spec_from_file_location("grep_gates_wp7", _ROOT / "scripts" / "grep_gates.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_tracked_markdown_home_literals_are_reported(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    docs = tmp_path / "docs" / "archive"
    docs.mkdir(parents=True)
    home = "/" + "home/someone/"  # split so this file never trips the gate itself
    (docs / "a.md").write_text(f"run `{home}.local/bin/x`\nredacted /home/.../ ok\n~/.claude ok\n", encoding="utf-8")
    (tmp_path / "untracked.md").write_text(f"{home}x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "docs/archive/a.md"], check=True)
    hits = _gate().doc_home_literals(tmp_path)
    assert hits == ["docs/archive/a.md:1"]


def test_live_tracked_markdown_is_clean():
    assert _gate().doc_home_literals(_ROOT) == []
