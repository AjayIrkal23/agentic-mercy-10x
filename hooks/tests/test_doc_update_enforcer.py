"""doc-update-enforcer: a write under server_docs/ or frontend_docs/ is recorded as a surface
doc even though lib/code_files lists both folders as skip dirs. Before the fix the skip check
ran first, so in GO_UDP the commit gate (blocking-doc-enforcer) could never pass."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "doc-update-enforcer.py"
ROOT = "/work/GO_UDP/UDP_PLATFORM"


def _write(state_dir: Path, file_path: str) -> None:
    payload = {"session_id": "sid-1", "tool_name": "Edit", "tool_input": {"file_path": file_path}}
    subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
        env={"CLAUDE_HOOK_DOTSTATE_DIR": str(state_dir), "PATH": "/usr/bin:/bin"},
    )


def _state(state_dir: Path) -> dict:
    return json.loads(next(state_dir.glob("*doc-enforcer.json")).read_text(encoding="utf-8"))


def test_surface_doc_writes_are_recorded(tmp_path):
    _write(tmp_path, f"{ROOT}/server/internal/services/x/lookup.go")
    _write(tmp_path, f"{ROOT}/user-dashboard/src/components/shared/Bar.tsx")
    _write(tmp_path, f"{ROOT}/server/server_docs/06-operations/configuration-reference.md")
    _write(tmp_path, f"{ROOT}/user-dashboard/frontend_docs/01-overview/tech-stack.md")
    s = _state(tmp_path)
    assert s["be_touched"] and s["fe_touched"]
    assert s["be_docs_written"] and s["fe_docs_written"]


def test_skipped_non_doc_paths_stay_skipped(tmp_path):
    _write(tmp_path, f"{ROOT}/server/internal/services/x/lookup.go")
    _write(tmp_path, f"{ROOT}/user-dashboard/node_modules/pkg/docs/README.md")
    s = _state(tmp_path)
    assert not s["be_docs_written"] and not s["fe_docs_written"]
