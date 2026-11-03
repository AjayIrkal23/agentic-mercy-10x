"""ui-quality-autorun (PostToolUse, 2026-11-03): the UI linters run by themselves after a UI file edit."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ui_quality_autorun_u", HOOKS / "ui-quality-autorun.py")
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)  # type: ignore[union-attr]

FAKE_DETECT = """import json, sys
print(json.dumps([{"antipattern": "overused-font", "name": "Overused font", "severity": "warning",
                   "line": 3, "snippet": "Primary font: inter", "file": sys.argv[-1]}]))
"""
FAKE_SLOPLINT = """import sys
print(sys.argv[-1])
print("  FAIL 7a :1 pure #000: color: #000 (body) | fix: tint it")
print("  REFLEX 26b :1 no :active styling anywhere")
print("sloplint: 1 FAIL, 1 REFLEX across 1 file(s).")
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "app"
    (root / ".git").mkdir(parents=True)
    (root / "src").mkdir()
    det = tmp_path / "fake_detect.py"
    det.write_text(FAKE_DETECT, encoding="utf-8")
    slop = tmp_path / "fake_sloplint.py"
    slop.write_text(FAKE_SLOPLINT, encoding="utf-8")
    monkeypatch.setattr(ui, "_impeccable_cmd", lambda: [sys.executable, str(det)])
    monkeypatch.setattr(ui, "_sloplint_cmd", lambda: [sys.executable, str(slop)])
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    return root


def _payload(fp: Path, sid: str = "s1") -> dict:
    return {"session_id": sid, "tool_name": "Edit", "tool_input": {"file_path": str(fp)}, "cwd": str(fp.parent)}


def test_detect_runs_on_a_ui_file(repo):
    fp = repo / "src" / "Hero.tsx"
    fp.write_text("export const Hero = () => <h1>Hi</h1>\n", encoding="utf-8")
    text = ui.advise(_payload(fp))
    assert "UI auto-check ran on src/Hero.tsx" in text and "overused-font:3" in text
    assert "hallmark" not in text                         # no stamp -> no sloplint


def test_sloplint_runs_only_on_a_hallmark_page(repo):
    fp = repo / "src" / "page.css"
    fp.write_text("/* Hallmark · v2.0.0 · theme: coral */\nbody { color: #000 }\n", encoding="utf-8")
    text = ui.advise(_payload(fp))
    assert "hallmark FAIL 7a:1" in text and "hallmark REFLEX 26b:1" in text


def test_same_findings_reported_once_per_session(repo):
    fp = repo / "src" / "Hero.tsx"
    fp.write_text("x\n", encoding="utf-8")
    assert ui.advise(_payload(fp))
    assert ui.advise(_payload(fp)) == ""
    assert ui.advise(_payload(fp, sid="s2"))                # a new session reports again


@pytest.mark.parametrize("name", ["api.py", "README.md", "node_modules/pkg/a.tsx", "dist/app.css"])
def test_non_ui_and_vendor_files_are_skipped(repo, name):
    fp = repo / name
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("x\n", encoding="utf-8")
    assert ui.advise(_payload(fp)) == ""


def test_outside_a_repo_and_missing_engine_are_silent(repo, tmp_path, monkeypatch):
    loose = tmp_path / "loose.tsx"
    loose.write_text("x\n", encoding="utf-8")
    assert ui.advise(_payload(loose)) == ""
    monkeypatch.setattr(ui, "_impeccable_cmd", lambda: None)
    fp = repo / "src" / "Hero.tsx"
    fp.write_text("x\n", encoding="utf-8")
    assert ui.advise(_payload(fp)) == ""


def test_engine_lookup_needs_the_verified_stamp(tmp_path, monkeypatch):
    monkeypatch.delenv("IMPECCABLE_BIN", raising=False)
    monkeypatch.setenv("IMPECCABLE_HOME", str(tmp_path))
    version = (HOOKS.parent / "skills" / "impeccable" / "scripts" / "VERSION").read_text(encoding="utf-8").strip()
    binary = tmp_path / "bin" / version / ("impeccable.exe" if os.name == "nt" else "impeccable")
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    assert ui._impeccable_cmd() is None                    # never an unverified binary
    Path(f"{binary}.verified").write_text("abc 0\n", encoding="utf-8")
    assert ui._impeccable_cmd() == [str(binary)]


def test_main_prints_valid_json(repo, monkeypatch, capsys):
    fp = repo / "src" / "Hero.tsx"
    fp.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": staticmethod(lambda: json.dumps(_payload(fp)))})())
    ui.main()
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
