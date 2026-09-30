"""gateguard-write-gate: Python importers count toward the blast radius.

Builds a throwaway repo (a bare `.git` dir is enough for lib.repo_context.git_root)
around `billing/payments_core.py` and runs the hook's main() in-process. State,
report and bypass marker are redirected into tmp dirs so the run is hermetic.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import uuid
from contextlib import redirect_stdout
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

# One file per import form the gate must recognise.
_IMPORTERS = {
    "app/checkout.py": "import billing.payments_core\n",
    "app/invoice.py": "from billing.payments_core import charge\n",
    "billing/ledger.py": "from .payments_core import charge\n",
    "app/sub/refunds.py": "def f():\n    from ..billing.payments_core import refund\n",
    "app/report.py": "from billing import other, payments_core\n",
}


@pytest.fixture
def gate(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("gateguard_write_gate", _HOOKS / "gateguard-write-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for var in mod._BYPASS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mod, "_BYPASS_MARKER", tmp_path / "no-bypass")
    return mod


@pytest.fixture
def repo(tmp_path_factory):
    # tmp_path_factory, not tmp_path: tmp_path embeds the test name ("test_…"),
    # which the gate's SKIP_PATTERNS would treat as a test file.
    root = tmp_path_factory.mktemp("ggrepo")
    (root / ".git").mkdir()
    target = root / "billing" / "payments_core.py"
    target.parent.mkdir()
    target.write_text("def charge():\n    pass\n", encoding="utf-8")
    return root, target


def _write(root: Path, files: dict) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def _run(mod, target: Path, monkeypatch) -> dict:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(target)},
               "session_id": f"gg-{uuid.uuid4().hex}"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    return json.loads(buf.getvalue().strip() or "{}")


def test_python_module_with_five_importers_asks(gate, repo, monkeypatch):
    root, target = repo
    _write(root, _IMPORTERS)
    out = _run(gate, target, monkeypatch)
    hso = out.get("hookSpecificOutput", {})
    assert hso.get("permissionDecision") == "ask"
    assert "imported by 5 other file(s)" in hso["permissionDecisionReason"]


def test_python_module_with_four_importers_allows(gate, repo, monkeypatch):
    root, target = repo
    _write(root, dict(list(_IMPORTERS.items())[:4]))
    assert _run(gate, target, monkeypatch) == {}


def test_python_stem_in_comment_or_string_not_counted(gate, repo, monkeypatch):
    root, target = repo
    files = dict(list(_IMPORTERS.items())[:4])
    files["app/notes.py"] = (
        "# payments_core handles charges\n"
        'NAME = "payments_core"\n'
        "from payments_core_extra import thing\n"
    )
    _write(root, files)
    found = {Path(e["path"]).name for e in gate._gather_importers(str(target), str(root))}
    assert found == {"checkout.py", "invoice.py", "ledger.py", "refunds.py"}
    assert _run(gate, target, monkeypatch) == {}


def test_skip_patterns_match_windows_separators(gate, monkeypatch):
    """Claude Code on Windows sends `a\\b` paths; the `node_modules/`, `docs/` style skips
    never matched them (e2e run 2)."""
    monkeypatch.setattr(gate.os.path, "isfile", lambda p: True)
    assert gate._should_skip("web\\node_modules\\pkg\\index_core.js")
    assert gate._should_skip("web\\docs\\examples\\sample_core.py")
    assert not gate._should_skip("web\\src\\billing\\payments_core.py")


def test_importers_found_without_a_grep_binary(gate, repo, monkeypatch):
    """Windows has no grep on PATH (CI's windows-latest), and grep's `path:line:text`
    output split on ':' breaks on drive-letter paths. The search must be pure Python."""
    root, target = repo
    _write(root, _IMPORTERS)
    monkeypatch.setenv("PATH", "")
    found = gate._gather_importers(str(target), str(root))
    assert len(found) == 5
    assert all(e["lines"] and e["lines"][0]["lineno"] >= 1 for e in found)
