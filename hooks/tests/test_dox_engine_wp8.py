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


def test_new_child_doc_lists_its_code_files(tmp_path):
    root = _repo(tmp_path)
    cfg = dox.load_cfg(None, root=root)
    (root / "src" / "leaf" / "CLAUDE.md").unlink()
    dox.ensure_child(root, "src/leaf", cfg)
    body = (root / "src" / "leaf" / "CLAUDE.md").read_text(encoding="utf-8")
    assert all(f"`{n}`" in body for n in ("a.ts", "b.ts", "c.ts"))
    assert dox.unnamed_code_files(root, "src/leaf", cfg) == []
