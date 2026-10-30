"""FIX-r3 T7: per-prompt router injection budget. No skill body is inlined by default (the MUST-READ pointer
names the skill and its Read path; `deep_inject_chars` opts back in), and the WORKFLOW line never echoes
the prompt into `args.task` (the model already has the prompt)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HOOKS))

from prompt_router import router as R  # noqa: E402

SECURITY = "refactor the auth middleware to add rate limiting and run a security review"
MIGRATE = ("Migrate the whole backend from Express to Fastify across all 40 route files, add tests for every route, "
           "update the docs, then run a full security review and a Santa review of the result")
PLACEHOLDER = "<the prompt, verbatim>"


def _route(prompt: str, cfg_dir: Path, cwd: str = "/nonexistent-dir") -> str:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_HOOK_STATE_DIR"}
    env.update({"CLAUDE_HOOK_DOCTOR": "1", "CLAUDE_CONFIG_DIR": str(cfg_dir)})
    cp = subprocess.run([sys.executable, str(_HOOKS / "prompt_router" / "router.py")],
                        input=json.dumps({"session_id": "t-budget", "cwd": cwd, "prompt": prompt}),
                        capture_output=True, text=True, env=env, timeout=30, check=False)
    out = json.loads(cp.stdout.strip().splitlines()[-1])
    return (out.get("hookSpecificOutput") or {}).get("additionalContext", "")


def _cfg_with_workflows(tmp_path: Path) -> Path:
    cfg = tmp_path / "cfg"
    (cfg / "workflows" / "src").mkdir(parents=True)
    shutil.copy2(_HOOKS.parent / "workflows" / "src" / "index.src.json", cfg / "workflows" / "src" / "index.src.json")
    return cfg


def test_shipped_config_inlines_no_skill_body():
    cfg = json.loads((_HOOKS / "prompt_router" / "router.config.json").read_text(encoding="utf-8"))
    assert int(cfg.get("deep_inject_chars", 0)) == 0
    assert R._skill_excerpt("owasp-security", 0) == ""


def test_security_prompt_names_the_skill_without_its_body(tmp_path):
    text = _route(SECURITY, tmp_path)
    # 4,714 ch with the 3,379-ch body before T7; final-fix 2 (one-line skills, 3 pushes, shorter
    # substrate / MCP / dispatch lines) measured 1,207 here (no workflow index: dispatch lines instead)
    assert "[inlined skill:" not in text and len(text) <= 1250, len(text)
    must = [ln for ln in text.splitlines() if "MUST-READ" in ln]
    assert len(must) == 1 and "owasp-security" in must[0], must


def test_workflow_line_carries_no_prompt_echo(tmp_path):
    text = _route(MIGRATE, _cfg_with_workflows(tmp_path))
    line = next(ln for ln in text.splitlines() if ln.lstrip("- ").startswith("WORKFLOW:"))
    args = json.loads(line.split("with args ", 1)[1].rsplit(" (", 1)[0])
    assert args["task"] == PLACEHOLDER and "Fastify" not in line and len(line) < 320, line


def test_skill_push_is_one_line_each_and_at_most_three(monkeypatch):
    from prompt_router import select as S
    from prompt_router.classify import TaskProfile
    names = ("owasp-security", "code-simplification", "backend-standards-always-follow", "update-docs", "santa-review")
    monkeypatch.setattr(S, "rank_skills", lambda p, top_n=4, **k: [(n, 9.0 - i) for i, n in enumerate(names)][:top_n])
    prof = TaskProfile(text="review the auth security", intents={"SECURITY": 4}, surfaces=set())
    cfg = json.loads((_HOOKS / "prompt_router" / "router.config.json").read_text(encoding="utf-8"))
    items = [it for it in R._skill_items(prof, {"config": cfg}) if it["id"].startswith("skill:")]
    assert items and len(items) <= 3, items
    assert all("\n" not in it["text"] and "ACTION: " in it["text"] for it in items), items


def test_action_token_survives_one_line_format():
    from prompt_router import policy as P
    assert P.skill_line("owasp-security", "MUST-READ", "/x/SKILL.md") == \
        "- **owasp-security** (MUST-READ) ACTION: Read /x/SKILL.md"
    assert P.skill_line("code-simplification", "SHOULD-READ", None) == \
        '- **code-simplification** (SHOULD-READ) ACTION: Skill("code-simplification")'


def test_both_first_write_gates_merge_into_one_line():
    from types import SimpleNamespace
    from prompt_router.classify import TaskProfile
    prof = TaskProfile(text="add a POST /orders endpoint with validation and tests", intents={"IMPLEMENT": 3, "TEST": 3},
                       surfaces={"backend"})
    prof.first_write_candidate = True
    items = R._gate_items(prof, {"repo": SimpleNamespace(root="/r")})
    assert [it["id"] for it in items] == ["gate:firstwrite+tdd"], items
    # the mercy governor drops it after the first write by this phrase
    assert "First substantive change this session" in items[0]["text"] and "TDD" in items[0]["text"]


def test_opt_in_deep_inject_is_capped(monkeypatch):
    from prompt_router import select as S
    from prompt_router.classify import TaskProfile
    monkeypatch.setattr(S, "rank_skills", lambda *a, **k: [("owasp-security", 9.0), ("x", 1.0)])
    prof = TaskProfile(text="review the auth security", intents={"SECURITY": 4}, surfaces=set())
    items = R._skill_items(prof, {"config": {"auto_dispatch_threshold": 3, "deep_inject_chars": 600}})
    deep = [it for it in items if it["text"].startswith("[inlined skill:")]
    assert len(deep) == 1 and len(deep[0]["text"]) <= 700
    items = R._skill_items(prof, {"config": {"auto_dispatch_threshold": 3}})
    assert not [it for it in items if it["text"].startswith("[inlined skill:")]
