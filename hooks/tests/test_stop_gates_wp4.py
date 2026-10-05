"""WP4 (audit 2026-10-05): Stop-gate scope fixes.

B2-04  the suite gate enforces only skills whose paths / one-sided surface match the
       turn's code writes; generic or soft pushes become a non-blocking systemMessage.
B2-05  completion-gate thresholds count project files only; ~/.claude infra
       (workflows, plans, agents, skills too) never counts (NEW-02).
P5     a turn key of "?" (no human prompt found) never persists nags and never
       grants the same-turn override, so neither leaks into the next turn.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tel() -> Path:
    p = Path(os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR") or _HOOKS / ".telemetry")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _isg(tmp_path, cid: str, push: dict, writes: list, human: bool = True, **extra) -> dict:
    """Run the suite gate with one push record and a turn that wrote ``writes``."""
    now = datetime.now(timezone.utc).isoformat()
    rec = {"ts": now, "categories": [], "source": "router", "enforce": "hard"}
    rec.update(push)
    rec = {k: v for k, v in rec.items() if v is not None}
    (_tel() / f"{cid}.pushed-skills.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    rows = [{"type": "user", "timestamp": now, "message": {"role": "user", "content": "go"}}] if human else []
    for fp in writes:
        rows.append({"type": "assistant", "timestamp": now, "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": fp}}]}})
    tr = tmp_path / f"{cid}.jsonl"
    tr.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    payload = dict({"session_id": cid, "transcript_path": str(tr)}, **extra)
    cp = subprocess.run([sys.executable, str(_HOOKS / "invoke-suite-gate.py")], input=json.dumps(payload),
                        text=True, capture_output=True, timeout=20, check=False)
    return json.loads(cp.stdout.strip().splitlines()[-1])


# --------------------------------------------------------------------------- B2-04
def test_skill_without_paths_or_one_sided_surface_never_matches():
    isg = _load("isg_wp4", "invoke-suite-gate.py")
    assert isg.skill_matches_writes({}, ["/app/server/src/x.ts"]) is False
    assert isg.skill_matches_writes({"paths": [], "surfaces": ["backend", "frontend"]},
                                    ["/app/src/components/A.tsx"]) is False
    # positive matches still enforce
    assert isg.skill_matches_writes({"surfaces": ["frontend"]}, ["/app/src/components/A.tsx"]) is True
    assert isg.skill_matches_writes({"surfaces": ["backend", "general"]}, ["/app/server/a.go"]) is True
    assert isg.skill_matches_writes({"paths": ["**/*.go"], "surfaces": ["backend", "frontend"]},
                                    ["/app/server/a.go"]) is True


def _queued(cid: str) -> list:
    """The advisory texts queued for the model's next prompt (CLAUDE.md §11: a note the user
    cannot act on never goes to the user's screen)."""
    return _load("sup_wp4", "dispatch_support.py").drain(cid)


def test_generic_rank1_push_on_code_turn_is_advisory_not_block(tmp_path):
    cid = f"wp4-generic-{os.getpid()}"
    out = _isg(tmp_path, cid, {"skills": ["tech-debt-audit"]}, ["/app/server/src/controller/x.ts"])
    assert "decision" not in out and "systemMessage" not in out
    assert any("tech-debt-audit" in t for t in _queued(cid))


def test_soft_push_is_advisory_even_when_surface_matches(tmp_path):
    cid = f"wp4-soft-{os.getpid()}"
    out = _isg(tmp_path, cid, {"skills": ["react-hooks-patterns"], "enforce": "soft"},
               ["/app/src/hooks/useThing.ts"])
    assert "decision" not in out and "systemMessage" not in out
    assert any("react-hooks-patterns" in t for t in _queued(cid))


def test_surface_matching_hard_push_still_blocks(tmp_path):
    cid = f"wp4-hard-{os.getpid()}"
    out = _isg(tmp_path, cid, {"skills": ["react-hooks-patterns"]}, ["/app/src/hooks/useThing.ts"])
    assert out.get("decision") == "block" and "react-hooks-patterns" in out["reason"]


# --------------------------------------------------------------------------- P5 (suite gate)
def test_unknown_turn_key_never_persists_nags(tmp_path):
    cid = f"wp4-qkey-{os.getpid()}"
    push = {"skills": ["react-hooks-patterns"], "ts": None}
    write = ["/app/src/hooks/useThing.ts"]
    first = _isg(tmp_path, cid, push, write, human=False)
    assert first.get("decision") == "block"
    assert not (_tel() / f"{cid}.suite-gate.json").exists()
    # the harness re-run after our block carries stop_hook_active → let it stop
    assert _isg(tmp_path, cid, push, write, human=False, stop_hook_active=True) == {}
    # a later turn that is also "?" is judged on its own, not on a leaked nag count
    assert _isg(tmp_path, cid, push, write, human=False).get("decision") == "block"


# --------------------------------------------------------------------------- hcg
@pytest.fixture
def hcg(tmp_path, monkeypatch):
    mod = _load("hcg_wp4", "hard-completion-gate.py")
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(mod, "STATE_DIR", state)
    monkeypatch.setattr(mod, "TELEMETRY_DIR", tmp_path / "tel")
    return mod, state


def _hcg_run(mod, payload, monkeypatch) -> dict:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    return json.loads(buf.getvalue().strip() or "{}")


def _files(state: Path, files: list) -> None:
    (state / "s.desloppify.json").write_text(json.dumps({"code_files": files}))


def test_infra_files_do_not_count_toward_gate_4_5_thresholds(hcg, tmp_path, monkeypatch):
    mod, state = hcg
    proj = [f"/w/CODE_FILES/app/src/{n}.ts" for n in "ab"]
    infra = ["/w/.claude/mods/m/a.ts", "/w/.claude/hooks/b.py", "/w/.claude/tests/c.py"]
    _files(state, proj + infra)
    out = _hcg_run(mod, {"session_id": "s", "cwd": str(tmp_path)}, monkeypatch)
    assert "decision" not in out


@pytest.mark.parametrize("path", ["/w/.claude/workflows/invoke-fullstack.js",
                                  "/w/.claude/plans/audit/router/drive.py",
                                  "/w/.claude/agents/x.md", "/w/.claude/skills/s/tool.py"])
def test_new_infra_markers(hcg, path):
    assert hcg[0]._is_infra_path(path)


def test_unknown_turn_key_gets_no_same_turn_override(hcg, tmp_path, monkeypatch):
    mod, state = hcg
    _files(state, [f"/w/CODE_FILES/app/src/{n}.ts" for n in "abc"])
    tr = tmp_path / "t.jsonl"   # no human prompt in the tail → turn key "?"
    tr.write_text(json.dumps({"type": "assistant", "message": {"content": "hi"}}) + "\n")
    payload = {"session_id": "s", "transcript_path": str(tr), "cwd": str(tmp_path)}
    assert _hcg_run(mod, payload, monkeypatch).get("decision") == "block"
    assert _hcg_run(mod, payload, monkeypatch).get("decision") == "block"
    assert _hcg_run(mod, dict(payload, stop_hook_active=True), monkeypatch) == {}
