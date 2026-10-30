"""R3.6: a model-routing prompt must not be routed as frontend work."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from prompt_router import classify as C   # noqa: E402

PROMPT = ("Also i even want another feature: if the plan is plus 20$ plan it wont let user use opus "
          "and fable ... redesign the model selector as well for tasks")
FE_SKILLS = ("frontend-standards-always-follow", "design-taste-frontend", "react-hooks-patterns",
             "modern-web-guidance")


def _route(prompt: str, cfg_dir, cwd: str = "/nonexistent-dir") -> str:
    """A doctor dry-fire (no CLAUDE_HOOK_STATE_DIR) like acceptance command 3; any state
    write lands under ``cfg_dir`` through CLAUDE_CONFIG_DIR."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_HOOK_STATE_DIR"}
    env.update({"CLAUDE_HOOK_DOCTOR": "1", "CLAUDE_CONFIG_DIR": str(cfg_dir)})
    cp = subprocess.run([sys.executable, str(_HOOKS / "prompt_router" / "router.py")],
                        input=json.dumps({"session_id": "t-mr", "cwd": cwd, "prompt": prompt}),
                        capture_output=True, text=True, env=env, timeout=30, check=False)
    out = json.loads(cp.stdout.strip().splitlines()[-1])
    return (out.get("hookSpecificOutput") or {}).get("additionalContext", "")


def test_regression_prompt_is_model_routing_not_frontend(tmp_path):
    p = C.classify({"prompt": PROMPT, "cwd": "/nonexistent-dir"})
    assert "MODEL_ROUTING" in p.intents and "claude-infra" in p.surfaces
    assert not p.is_ui and "frontend" not in p.surfaces and "DESIGN" not in p.intents
    text = _route(PROMPT, tmp_path)
    assert "model-policy.json" in text
    for s in FE_SKILLS:
        assert s not in text, s
    assert "frontend-uiux-designer" not in text and "act design" not in text


def test_redesign_of_a_page_is_still_ui():
    p = C.classify({"prompt": "redesign the login page", "cwd": "/nonexistent-dir"})
    assert p.is_ui and "frontend" in p.surfaces and "MODEL_ROUTING" not in p.intents


def test_haiku_for_docs_agents_is_model_routing():
    p = C.classify({"prompt": "give docs agents the haiku model", "cwd": "/nonexistent-dir"})
    assert "MODEL_ROUTING" in p.intents and "claude-infra" in p.surfaces and not p.is_ui


def test_model_picker_component_on_a_page_stays_ui():
    p = C.classify({"prompt": "add a model picker component to the settings page", "cwd": "/nonexistent-dir"})
    assert p.is_ui and "frontend" in p.surfaces      # UI nouns present: the veto does not apply


def test_model_routing_has_no_act_and_no_skill_push():
    assert "MODEL_ROUTING" not in C.ACT_MAP
    cats = json.loads((_HOOKS / "autonomous-skill-router.config.json").read_text(encoding="utf-8"))["categories"]
    mr = cats["MODEL_ROUTING"]
    assert mr["keywords"] == [] and mr["local_skills"] == [] and "act" not in mr and mr["surface"] == "claude-infra"


def test_doctor_runs_are_repeatable(tmp_path):
    """A doctor dry-fire never reads or writes the manifest: the same prompt twice gives the same text."""
    first = _route(PROMPT, tmp_path)
    assert first and first == _route(PROMPT, tmp_path)
    assert not list((tmp_path / "state").glob("*.router-manifest.json"))


def test_named_frontend_stack_survives_a_model_word():
    """Deviation guard: "use opus to ... in react" keeps the frontend surface the prompt names.
    REVIEW2 Fix 1: a lone model name is the override phrase, not model-routing talk."""
    p = C.classify({"prompt": "use opus to implement the checkout flow in react", "cwd": "/nonexistent-dir"})
    assert "MODEL_ROUTING" not in p.intents and "frontend" in p.surfaces


def _react_repo(tmp_path):
    repo = tmp_path / "fe"
    (repo / ".git").mkdir(parents=True)
    (repo / "package.json").write_text('{"dependencies": {"react": "18.3.1", "react-dom": "18.3.1"}}',
                                       encoding="utf-8")
    return repo


def test_override_phrase_keeps_frontend_routing(tmp_path):
    """REVIEW2 Fix 1: "use opus for this: ..." (CLAUDE.md section 2) must not wipe UI routing."""
    repo = _react_repo(tmp_path)
    prompt = "use opus for this: add infinite scroll to the photo gallery"
    p = C.classify({"prompt": prompt, "cwd": str(repo)})
    assert "MODEL_ROUTING" not in p.intents
    assert p.is_ui and "frontend" in p.surfaces and "claude-infra" not in p.surfaces
    text = _route(prompt, tmp_path / "cfg", cwd=str(repo))
    assert "model-policy.json" not in text


def test_with_sonnet_build_table_stays_ui(tmp_path):
    p = C.classify({"prompt": "with sonnet, build a sortable data table with sticky headers",
                    "cwd": str(_react_repo(tmp_path))})
    assert p.is_ui and "frontend" in p.surfaces and "MODEL_ROUTING" not in p.intents


def test_5x_faster_is_not_model_routing(tmp_path):
    p = C.classify({"prompt": "make the image gallery load 5x faster", "cwd": str(_react_repo(tmp_path))})
    assert "MODEL_ROUTING" not in p.intents and "frontend" in p.surfaces


def test_routing_noun_with_model_name_is_still_model_routing(tmp_path):
    p = C.classify({"prompt": "switch the subagent model routing to haiku", "cwd": str(_react_repo(tmp_path))})
    assert "MODEL_ROUTING" in p.intents and "claude-infra" in p.surfaces
    assert "frontend" not in p.surfaces and not p.is_ui


def test_two_model_names_alone_are_model_routing():
    p = C.classify({"prompt": "should the reviewers run on opus or sonnet", "cwd": "/nonexistent-dir"})
    assert p.intents.get("MODEL_ROUTING") == 2 and "claude-infra" in p.surfaces


def test_two_model_names_on_a_ui_task_keep_frontend(tmp_path):
    p = C.classify({"prompt": "use opus or sonnet to build a sortable data table with sticky headers",
                    "cwd": str(_react_repo(tmp_path))})
    assert "MODEL_ROUTING" in p.intents and p.is_ui and "frontend" in p.surfaces
