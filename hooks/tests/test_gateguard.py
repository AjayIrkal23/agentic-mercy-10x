"""gateguard-write-gate: Python importers count toward the blast radius.

Builds a throwaway repo (a bare `.git` dir is enough for lib.repo_context.git_root)
around `shop/payments_core.py` and runs the hook's main() in-process. State,
report and bypass marker are redirected into tmp dirs so the run is hermetic.
(PKG gates: the package dir was `billing/`, which is now a sensitive target that asks on
its own; `shop/` keeps these importer-count tests about importers only.)
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
    "app/checkout.py": "import shop.payments_core\n",
    "app/invoice.py": "from shop.payments_core import charge\n",
    "shop/ledger.py": "from .payments_core import charge\n",
    "app/sub/refunds.py": "def f():\n    from ..shop.payments_core import refund\n",
    "app/report.py": "from shop import other, payments_core\n",
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
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)  # the impact report goes to the sandbox ~/.claude
    monkeypatch.delenv("CLAUDE_WORKBENCH_UNATTENDED", raising=False)
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
    target = root / "shop" / "payments_core.py"
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


# --- PKG gates: sensitive / secret targets ask; asks go through lib/gate_mode ----------------------
def _run_as(mod, target: Path, monkeypatch, sid: str, extra: dict | None = None, post: bool = False) -> dict:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(target)}, "session_id": sid, **(extra or {})}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "argv", ["gateguard-write-gate.py"] + (["post-tool-use"] if post else []))
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    return json.loads(buf.getvalue().strip() or "{}")


def test_sensitive_target_asks_without_importers(gate, repo, monkeypatch):
    root, _ = repo
    t = root / "src" / "auth" / "session.py"
    t.parent.mkdir(parents=True)
    t.write_text("x = 1\n", encoding="utf-8")
    out = _run(gate, t, monkeypatch)
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "ask" and "sensitive" in hso["permissionDecisionReason"]


def test_blast_bypass_marker_silences_sensitive_but_not_secret(gate, repo, monkeypatch):
    root, _ = repo
    gate._BYPASS_MARKER.write_text("", encoding="utf-8")          # the fixture points it at tmp
    wf = root / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("on: push\n", encoding="utf-8")
    assert _run(gate, wf, monkeypatch) == {}                       # Dockerfile / workflows / migrations: bypassed
    env = root / ".env"
    env.write_text("A=1\n", encoding="utf-8")
    hso = _run(gate, env, monkeypatch)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "ask" and "secret" in hso["permissionDecisionReason"]
    pem = root / "certs" / "k.pem"
    pem.parent.mkdir()
    pem.write_text("-----BEGIN X-----\n", encoding="utf-8")
    assert _run(gate, pem, monkeypatch)["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_second_write_to_the_same_file_does_not_ask_after_the_write_ran(gate, repo, monkeypatch):
    root, _ = repo
    t = root / "db" / "migrations" / "0003_add.sql"
    t.parent.mkdir(parents=True)
    t.write_text("-- x\n", encoding="utf-8")
    sid = f"gg-{uuid.uuid4().hex}"
    assert _run_as(gate, t, monkeypatch, sid)["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert _run_as(gate, t, monkeypatch, sid)["hookSpecificOutput"]["permissionDecision"] == "ask"  # declined
    _run_as(gate, t, monkeypatch, sid, post=True)                  # the approved write ran
    assert _run_as(gate, t, monkeypatch, sid) == {}


def test_subagent_payload_gets_an_advisory_not_a_prompt(gate, repo, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    root, _ = repo
    t = root / "Dockerfile"
    t.write_text("FROM x\n", encoding="utf-8")
    hso = _run_as(gate, t, monkeypatch, f"gg-{uuid.uuid4().hex}", extra={"agent_id": "a1"})["hookSpecificOutput"]
    assert "permissionDecision" not in hso and "ask downgraded: subagent" in hso["additionalContext"]
    rows = [json.loads(line) for p in (tmp_path / "tel").glob("*.jsonl")
            for line in p.read_text(encoding="utf-8").splitlines()]
    assert any(r.get("decision") == "ask_downgraded" and r["link_id"] == "gateguard-write-gate" for r in rows)


def test_skip_patterns_are_segment_anchored(gate, monkeypatch):
    monkeypatch.setattr(gate.os.path, "isfile", lambda p: True)
    assert not gate._should_skip("src/latest_orders.ts")       # `test_` is a basename prefix, not a substring
    assert not gate._should_skip("src/airplan-x.ts")           # `plan-` likewise
    assert not gate._should_skip("src/a.json.ts")              # extension is the LAST suffix
    assert not gate._should_skip("src/docs_helper.ts")         # `docs/` is a directory segment
    assert gate._should_skip("tests/test_x.py") and gate._should_skip("web\\docs\\x.py")
    assert gate._should_skip("a/package-lock.json")
