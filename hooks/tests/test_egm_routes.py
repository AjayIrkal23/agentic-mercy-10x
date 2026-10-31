"""EGM (Elephant-Goldfish Model) router route: design-doc review, brainstorm, draft and drift report.

The plugin's skills are `disable-model-invocation`, so the Skill tool refuses them: the route tells the
model to Read the SKILL.md under the plugin root. Every test uses a FAKE plugin tree (monkeypatched
`egm_routes.plugin_root`), never the real plugin cache. Prompts are paraphrased.
"""
from __future__ import annotations

import json
import pathlib
import sys
import uuid

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import router as R  # noqa: E402
from prompt_router.modules import egm_routes as EG  # noqa: E402
from prompt_router.modules import mcp_routes as M  # noqa: E402

SKILLS = {"egm-review": "egm-review", "egm-brainstorm": "egm_brainstorm",   # underscore dir = old tag v0.1.0
          "egm-draft": "egm-draft", "egm-drift-report": "egm-drift-report"}


@pytest.fixture
def plugin(tmp_path, monkeypatch):
    root = tmp_path / "plugins" / "cache" / "egm" / "egm" / "0.1.0"
    for _name, d in SKILLS.items():
        (root / "skills" / d).mkdir(parents=True)
        (root / "skills" / d / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    monkeypatch.delenv("CLAUDE_WORKBENCH_UNATTENDED", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ATTENDED", raising=False)
    monkeypatch.setattr(M, "server_available", lambda names, _roots=None: (list(names) or [None])[0])
    monkeypatch.setattr(EG, "plugin_root", lambda pid: root.as_posix())
    work = tmp_path / "work"
    work.mkdir()
    return root, work


def test_no_line_from_the_home_dir(plugin, tmp_path, monkeypatch):
    """2026-10-31 live probe: from $HOME the line pointed EGM's artifacts at ~/.claude/egm."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    assert "/skills/egm" not in _route("how should we architect multi-tenant billing", home)


def _route(prompt: str, work: pathlib.Path) -> str:
    return R.route_payload({"session_id": f"egm-{uuid.uuid4().hex[:8]}", "cwd": str(work), "prompt": prompt})


def _egm_line(text: str) -> str:
    return next((ln for ln in text.splitlines() if "EGM" in ln), "")


@pytest.mark.parametrize("prompt,skill,dirname", [
    ("Review docs/designs/webhook-delivery.md with fresh eyes before we build it", "egm-review", "egm-review"),
    ("We need webhook delivery with retries and dedup across three services; brainstorm the design "
     "before any code", "egm-brainstorm", "egm_brainstorm"),
    ("check whether the design docs in docs/designs still match the code", "egm-drift-report", "egm-drift-report"),
    ("write the design doc from the concepts brief", "egm-draft", "egm-draft"),
    ("how should we architect multi-tenant billing", "egm-brainstorm", "egm_brainstorm"),
])
def test_route_fires_on_its_cue(plugin, prompt, skill, dirname):
    root, work = plugin
    text = _route(prompt, work)
    line = _egm_line(text)
    assert f"/skills/{dirname}/SKILL.md" in line, text
    assert "CLAUDE_PLUGIN_ROOT" in line and root.as_posix() in line, line
    assert "EGM artifact directory:" in line and (work / ".claude" / "egm").as_posix() in line, line
    assert "WORKFLOW:" not in text and "(MUST-READ)" not in text and "/egm:" not in text, text
    assert "santa-review" not in text and "santa-reviewer" not in text, text


@pytest.mark.parametrize("prompt", [
    "fix the typo in the login button label",
    "the checkout endpoint returns 500 after the last deploy, find the root cause",
    "review my changes before I merge",
    "review the landing page design, it looks off",
    "add a created_at field to the user model",
    "what is the elephant goldfish model?",
    "rename the webhook handler and bump the version",
])
def test_no_line_for_other_work(plugin, prompt):
    _root, work = plugin
    assert "/skills/egm" not in _route(prompt, work), prompt


def test_plugin_absent_or_disabled_adds_nothing(plugin, monkeypatch):
    _root, work = plugin
    monkeypatch.setattr(EG, "plugin_root", lambda pid: "")
    assert "/skills/egm" not in _route("Review docs/designs/webhook-delivery.md with fresh eyes", work)


def test_unattended_keeps_review_and_drops_interactive_routes(plugin, monkeypatch):
    _root, work = plugin
    monkeypatch.setenv("CLAUDE_WORKBENCH_UNATTENDED", "1")
    assert "/skills/egm-review/" in _route("Review docs/designs/webhook-delivery.md with fresh eyes", work)
    assert "Unattended:" in _egm_line(_route("Review docs/designs/webhook-delivery.md with fresh eyes", work))
    assert "/skills/egm" not in _route("how should we architect multi-tenant billing", work)
    assert "/skills/egm" not in _route("write the design doc from the concepts brief", work)


def test_attended_zero_alone_counts_as_attended(plugin, monkeypatch):
    """The owner's remote/app sessions run with ATTENDED=0 and entrypoint sdk-cli while present
    (live probe 2026-10-31): brainstorm must still fire there."""
    _root, work = plugin
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "0")
    for entry in ("remote", "sdk-cli"):
        monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", entry)
        assert "/skills/egm_brainstorm/" in _route("how should we architect multi-tenant billing", work)


def test_item_id_is_salted_per_review_target(plugin):
    from prompt_router.classify import classify
    _root, work = plugin
    ids = []
    for target in ("docs/designs/a.md", "docs/designs/b.md"):
        prompt = f"Review {target} with fresh eyes"
        prof = classify({"prompt": prompt, "cwd": str(work)})
        cfg = json.loads((_HOOKS / "prompt_router" / "router.config.json").read_text(encoding="utf-8"))
        items = EG.items(prof, {"config": cfg, "payload": {"prompt": prompt, "cwd": str(work)}, "repo": None})
        assert len(items) == 1
        ids.append(items[0]["id"])
    assert ids[0] != ids[1] and all(i.startswith("route:egm:egm-review:") for i in ids), ids


def test_skill_md_prefers_name_then_underscore(tmp_path):
    (tmp_path / "skills" / "egm_review").mkdir(parents=True)
    (tmp_path / "skills" / "egm_review" / "SKILL.md").write_text("x", encoding="utf-8")
    assert EG.skill_md(tmp_path.as_posix(), "egm-review").endswith("/skills/egm_review/SKILL.md")
    assert EG.skill_md(tmp_path.as_posix(), "egm-draft") is None


def test_plugin_root_normalises_windows_paths_and_needs_enabled(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    plug = tmp_path / "egm-root"
    (plug / "skills").mkdir(parents=True)
    (cfg / "plugins").mkdir(parents=True)
    (cfg / "settings.json").write_text(json.dumps({"enabledPlugins": {"egm@egm": True}}), encoding="utf-8")
    (cfg / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {"egm@egm": [
        {"scope": "project", "installPath": "D:\\x\\plugins\\cache\\egm\\egm\\0.0.1"},
        {"scope": "user", "installPath": plug.as_posix()}]}}),
        encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    EG.plugin_root.cache_clear()
    assert EG.plugin_root("egm@egm") == plug.as_posix()
    (cfg / "settings.json").write_text(json.dumps({"enabledPlugins": {"egm@egm": False}}), encoding="utf-8")
    EG.plugin_root.cache_clear()
    assert EG.plugin_root("egm@egm") == ""
    EG.plugin_root.cache_clear()


def test_windows_install_path_is_normalised():
    assert EG.norm_path("D:\\x\\plugins\\cache\\egm\\egm\\0.1.0") == "D:/x/plugins/cache/egm/egm/0.1.0"
