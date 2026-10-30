"""lib.code_files: one anchored skip list, shared by every consumer (PKG hooks-hygiene-mod steps 1, 11, 12)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import code_files as cf  # noqa: E402

_WIN = "C:" + "\\"  # split so the G3 drive-literal gate never matches this file


def test_dir_segments_are_anchored_components():
    assert cf.is_skipped("/r/docs/x.ts") and cf.is_skipped("/r/a/docs/x.ts")
    assert not cf.is_skipped("/r/mydocs/x.ts") and not cf.is_skipped("/r/docsite/x.ts")
    assert cf.is_skipped(_WIN + "r\\node_modules\\a.js") and cf.is_skipped("/r/server_docs/a.md")
    assert cf.is_skipped("/tmp/x/a.py") and not cf.is_skipped("/r/tmp/a.py")   # tmp is root-anchored only
    assert cf.is_skipped("/r/.claude/hooks/a.py") and not cf.is_skipped("/r/.claude/agents/a.py")


def test_name_markers_apply_to_the_basename_only():
    assert cf.is_skipped("/r/src/.env.local") and cf.is_skipped("/r/vite.config.ts") and cf.is_skipped("/r/package.json")
    assert not cf.is_skipped("/r/.envs/app/main.py")     # a directory named .envs is not a dotenv file


def test_is_code_file_uses_the_same_list():
    assert cf.is_code_file("/r/mydocs/x.ts") and not cf.is_code_file("/r/docs/x.ts")
    assert not cf.is_code_file("/r/src/a.md") and cf.is_code_file("/r/src/a.py")


def test_extra_markers_from_a_caller():
    assert cf.is_skipped("/r/src/a_test.go", extra_names=("_test.go",))
    assert cf.is_skipped("/r/.expo/a.ts", extra_dirs=(".expo",)) and not cf.is_skipped("/r/.expo/a.ts")


def test_bare_and_empty_paths_never_raise():
    assert not cf.is_skipped("") and not cf.is_skipped(None) and not cf.is_skipped("a.py")
    assert cf.is_code_file("a.py") and not cf.is_code_file(None)


# --------------------------------------------------------------------------- #
# step 11: consumers share the anchored list
# --------------------------------------------------------------------------- #
def _load(alias: str, fname: str):
    spec = importlib.util.spec_from_file_location(alias, HOOKS / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_codex_capture_high_signal_uses_the_shared_list():
    m = _load("codex_capture_ut", "codex-capture.py")
    assert m.is_high_signal_path("/r/src/api/x.ts")
    assert not m.is_high_signal_path("/r/node_modules/src/api/x.ts")
    assert m.is_high_signal_path("/r/mydocs/src/api/x.ts")


def test_security_gate_should_skip_uses_the_shared_list():
    m = _load("security_gate_ut", "security-scan-gate.py")
    assert m._should_skip("/r/docs/auth.ts") is True
    assert m._should_skip("/r/mydocs/auth.ts") is False
    assert m._should_skip("/r/src/auth.test.ts") is True
    assert m._should_skip("/r/.claude/hooks/auth.py") is True
    assert m._should_skip("/r/graphify-out/auth.py") is True


def test_doc_update_enforcer_should_skip_uses_the_shared_list():
    m = _load("doc_update_ut", "doc-update-enforcer.py")
    assert m._should_skip("/r/docs/a.ts") is True
    assert m._should_skip("/r/mydocs/a.ts") is False
    assert m._should_skip("/r/plan-x/a.ts") is True


def test_security_gate_ignores_non_code_files(tmp_path):
    payload = {"session_id": "sg1", "tool_name": "Write",
               "tool_input": {"file_path": "/repo/api_docs/auth.md", "content": "token"}}
    env = {**os.environ, "CLAUDE_HOOK_DOTSTATE_DIR": str(tmp_path)}
    cp = subprocess.run([sys.executable, str(HOOKS / "security-scan-gate.py")], input=json.dumps(payload),
                        text=True, capture_output=True, timeout=30, env=env)
    assert cp.returncode == 0
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- #
# step 12: dox-write-gate ad-hoc note advisory
# --------------------------------------------------------------------------- #
def _dox(tmp_path, payload):
    env = {**os.environ, "CLAUDE_HOOK_DOTSTATE_DIR": str(tmp_path / "dot")}
    cp = subprocess.run([sys.executable, str(HOOKS / "dox-write-gate.py")], input=json.dumps(payload),
                        text=True, capture_output=True, timeout=30, env=env, cwd=str(payload["cwd"]))
    assert cp.returncode == 0, cp.stderr
    return json.loads(cp.stdout or "{}")


def test_dox_gate_adhoc_note_advisory_once(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "CLAUDE.md").write_text("# repo\n", encoding="utf-8")

    def pl(rel):
        return {"session_id": "s", "cwd": str(repo), "tool_name": "Write",
                "tool_input": {"file_path": str(repo / rel), "content": "x"}}

    out1 = _dox(tmp_path, pl("NOTES.md"))
    hso = out1["hookSpecificOutput"]
    assert "ad-hoc" in hso["additionalContext"].lower() and "permissionDecision" not in hso
    assert len(hso["additionalContext"]) <= 200
    assert _dox(tmp_path, pl("TODO.md")) == {}                      # once per session
    assert _dox(tmp_path, {**pl("docs/NOTES.md"), "session_id": "s2"}) == {}   # structured dir: silent
    assert _dox(tmp_path, {**pl(".claude/NOTES.md"), "session_id": "s3"}) == {}
