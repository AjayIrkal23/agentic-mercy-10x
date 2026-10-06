"""gateguard-write-gate audit fixes (2026-10-05 B1-08): TS/JS importers need a quoted,
boundary-anchored specifier (comments and sibling prefixes do not count); an ask is
acknowledged only after the write ran (PostToolUse), not before the user answers; the
reason no longer claims a stderr report."""
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

_REAL = {
    "src/a.ts": "import { W } from './components/Widget'\n",
    "src/b.tsx": "import W from \"../components/Widget\";\n",
    "src/c.js": "const W = require('./components/Widget.js')\n",
    "src/d.ts": "export { W } from './components/Widget'\n",
}


@pytest.fixture
def gate(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("gg_wp3", _HOOKS / "gateguard-write-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    # `~` is read from HOME on POSIX and USERPROFILE on Windows: the gate writes
    # ~/.claude/.gateguard-last-impact.md, so the sandbox must hold on both (A7-06)
    assert Path.home() == home, "sandbox home does not hold: the gate would write the live ~/.claude"
    for var in mod._BYPASS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mod, "_BYPASS_MARKER", tmp_path / "no-bypass")
    return mod


@pytest.fixture
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("ggwp3")
    (root / ".git").mkdir()
    target = root / "src" / "components" / "Widget.tsx"
    target.parent.mkdir(parents=True)
    target.write_text("export const W = 1\n", encoding="utf-8")
    return root, target


def _write(root: Path, files: dict) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")


def _run(mod, target: Path, monkeypatch, sid: str, event: str = "pre") -> dict:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(target)}, "session_id": sid}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "argv", ["gateguard-write-gate.py"] + (["post-tool-use"] if event == "post" else []))
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    return json.loads(buf.getvalue().strip() or "{}")


def _ask(out: dict) -> bool:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision") == "ask"


def test_comment_and_sibling_prefix_do_not_count(gate, repo, monkeypatch):
    root, target = repo
    _write(root, {**_REAL,
                  "src/e.ts": "// moved from ./components/Widget\n",
                  "src/f.ts": "import G from './components/WidgetGroup'\n"})
    found = {Path(e["path"]).name for e in gate._gather_importers(str(target), str(root))}
    assert found == {"a.ts", "b.tsx", "c.js", "d.ts"}
    assert _run(gate, target, monkeypatch, f"gg-{uuid.uuid4().hex}") == {}


def test_ask_repeats_until_the_write_ran(gate, repo, monkeypatch):
    root, target = repo
    _write(root, {**_REAL, "src/g.ts": "import { W } from '@/components/Widget'\n"})
    sid = f"gg-{uuid.uuid4().hex}"
    first = _run(gate, target, monkeypatch, sid)
    assert _ask(first)
    assert "stderr" not in first["hookSpecificOutput"]["permissionDecisionReason"]
    assert _ask(_run(gate, target, monkeypatch, sid))  # user declined: no PostToolUse, still asks
    _run(gate, target, monkeypatch, sid, event="post")  # the approved write ran
    assert _run(gate, target, monkeypatch, sid) == {}


def test_post_ack_is_wired_in_the_live_config():
    cfg = json.loads((_HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))
    link = next(ln for ln in cfg["chains"]["post-tool-use"] if ln["id"] == "gateguard-ack")
    assert link["type"] == "exec" and "post-tool-use" in link["cmd"]
