"""dox_engine leaf-doc coverage (audit 2026-10-05 F-12): a leaf dir's CLAUDE.md should
name its code files; layer roots (> LEAF_MAX_FILES code files) stay folded by design.
Runnable: `python3 -m pytest hooks/tests/test_dox_engine_wp8.py -q`.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "dox_engine_wp8", Path(__file__).resolve().parents[1] / "dox_engine.py")
dox = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dox)


def _repo(tmp: Path) -> Path:
    root = tmp / "repo"
    leaf = root / "src" / "leaf"
    leaf.mkdir(parents=True)
    for n in ("a.ts", "b.ts", "c.ts"):
        (leaf / n).write_text("export {}\n", encoding="utf-8")
    (leaf / "CLAUDE.md").write_text("# leaf\n\n| `a.ts` | thing |\n", encoding="utf-8")
    big = root / "src" / "ui"
    big.mkdir()
    for i in range(dox.LEAF_MAX_FILES + 1):
        (big / f"c{i}.tsx").write_text("export {}\n", encoding="utf-8")
    (big / "CLAUDE.md").write_text("# ui (folded)\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def test_leaf_doc_reports_unnamed_code_files_and_layer_roots_stay_folded(tmp_path):
    root = _repo(tmp_path)
    cfg = dox.load_cfg(None, root=root)
    assert dox.unnamed_code_files(root, "src/leaf", cfg) == ["b.ts", "c.ts"]
    assert dox.unnamed_code_files(root, "src/ui", cfg) == []


def _scaffold(root: Path, tmp: Path, name: str, sid: str = "dox-s1") -> str:
    import json
    import os
    import sys
    payload = {"session_id": sid, "tool_name": "Write",
               "tool_input": {"file_path": str(root / "src" / "leaf" / name)}}
    env = {**os.environ, "CLAUDE_HOOK_DOTSTATE_DIR": str(tmp / "dot")}
    cp = subprocess.run([sys.executable, str(Path(dox.__file__).parent / "dox-child-scaffold.py")],
                        input=json.dumps(payload), capture_output=True, text=True, env=env)
    return json.loads(cp.stdout or "{}").get("additionalContext", "")


def test_code_file_missing_from_its_documented_dir_gets_one_nudge(tmp_path):
    root = _repo(tmp_path)
    (root / "CLAUDE.md").write_text("# repo\n", encoding="utf-8")  # dox-active
    (root / "src" / "leaf" / "b.test.ts").write_text("export {}\n", encoding="utf-8")
    assert _scaffold(root, tmp_path, "a.ts") == ""            # named in the doc
    assert _scaffold(root, tmp_path, "b.test.ts") == ""       # tests are not Key files
    txt = _scaffold(root, tmp_path, "b.ts")
    assert "src/leaf/CLAUDE.md" in txt and "`b.ts`" in txt
    assert _scaffold(root, tmp_path, "c.ts") == ""            # once per dir per session


def test_new_child_doc_lists_its_code_files(tmp_path):
    root = _repo(tmp_path)
    cfg = dox.load_cfg(None, root=root)
    (root / "src" / "leaf" / "CLAUDE.md").unlink()
    dox.ensure_child(root, "src/leaf", cfg)
    body = (root / "src" / "leaf" / "CLAUDE.md").read_text(encoding="utf-8")
    assert all(f"`{n}`" in body for n in ("a.ts", "b.ts", "c.ts"))
    assert dox.unnamed_code_files(root, "src/leaf", cfg) == []
