"""The install must never silently destroy what a user already has (Santa installer review):
relocating the clone keeps differing user files once as `<name>.pre-install`, and the first
settings.json render keeps the user's env / apiKeyHelper / model / own hooks / defaultMode."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bootstrap  # noqa: E402
import settings_seed  # noqa: E402


# --- 1. relocation keeps the user's own files ------------------------------------------ #
def _tree(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


def test_relocate_keeps_a_differing_user_file_once_as_pre_install(tmp_path, capsys):
    src = _tree(tmp_path / "clone", {"CLAUDE.md": "author", "skills/caveman/SKILL.md": "author skill",
                                     "agents/team-lead.md": "author agent", "rules/00.md": "same"})
    target = _tree(tmp_path / "home" / ".claude", {
        "CLAUDE.md": "MINE", "skills/caveman/SKILL.md": "my skill", "agents/team-lead.md": "my agent",
        "rules/00.md": "same", "projects/p/x.jsonl": "history"})
    seen: list = []
    bootstrap.relocate(src, target, emit=lambda *a: seen.append(a))
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "author"
    assert (target / "CLAUDE.md.pre-install").read_text(encoding="utf-8") == "MINE"
    assert (target / "skills/caveman/SKILL.md.pre-install").read_text(encoding="utf-8") == "my skill"
    assert (target / "agents/team-lead.md.pre-install").read_text(encoding="utf-8") == "my agent"
    assert not (target / "rules/00.md.pre-install").exists()  # identical: nothing to keep
    assert (target / "projects/p/x.jsonl").read_text(encoding="utf-8") == "history"
    out = capsys.readouterr().out
    assert "3 of your files" in out and "pre-install" in out and out.strip().count("\n") == 0


def test_a_later_run_never_overwrites_the_kept_copy(tmp_path):
    src = _tree(tmp_path / "clone", {"CLAUDE.md": "author"})
    target = _tree(tmp_path / "t", {"CLAUDE.md": "MINE"})
    bootstrap.relocate(src, target, emit=lambda *a: None)
    (target / "CLAUDE.md").write_text("edited later", encoding="utf-8")
    bootstrap.relocate(src, target, emit=lambda *a: None)
    assert (target / "CLAUDE.md.pre-install").read_text(encoding="utf-8") == "MINE"
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "author"


def test_a_complete_install_is_not_scanned_again(tmp_path, capsys):
    """Re-running from the clone rewrites files the installer itself regenerated (skills index,
    token-cost front matter): 22 bogus `.pre-install` copies appeared in the container. Only the
    FIRST install (bundle items missing at the target) keeps the user's differing files."""
    src = _tree(tmp_path / "clone", {"CLAUDE.md": "author"})
    target = _tree(tmp_path / "t", {"CLAUDE.md": "installed then edited"})
    for name in bootstrap._BUNDLE_ITEMS:
        p = target / name
        p.mkdir(exist_ok=True) if "." not in name else p.write_text("x", encoding="utf-8")
    assert not bootstrap.missing_items(target)
    bootstrap.relocate(src, target, emit=lambda *a: None)
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "author"
    assert not (target / "CLAUDE.md.pre-install").exists()
    assert "pre-install" not in capsys.readouterr().out


def test_a_fresh_target_prints_nothing_about_preserved_files(tmp_path, capsys):
    src = _tree(tmp_path / "clone", {"CLAUDE.md": "author"})
    bootstrap.relocate(src, tmp_path / "fresh", emit=lambda *a: None)
    assert "pre-install" not in capsys.readouterr().out
    assert not list((tmp_path / "fresh").glob("*.pre-install"))


# --- 2. the first settings render merges instead of replacing -------------------------- #
@pytest.fixture
def r():
    spec = importlib.util.spec_from_file_location("render", _ROOT / "installer" / "render.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["render"] = mod
    spec.loader.exec_module(mod)
    return mod


USER = {
    "env": {"CLAUDE_CODE_USE_BEDROCK": "1", "HTTPS_PROXY": "http://proxy:3128", "MY_FLAG": "x",
            "ANTHROPIC_BASE_URL": "https://gw.example/v1"},
    "apiKeyHelper": "/opt/bin/get-key",
    "model": "opus",
    "permissions": {"defaultMode": "acceptEdits", "allow": ["Bash(ls:*)"]},
    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "/usr/local/bin/notify-done"}]}]},
}


def test_seed_keeps_provider_keys_helper_model_mode_and_own_hooks(r):
    rendered = json.loads(r.render(user_path=None))
    seed = settings_seed.seed_overlay(USER, rendered)
    assert seed["env"] == USER["env"]  # none of these are template keys
    assert seed["apiKeyHelper"] == "/opt/bin/get-key" and seed["model"] == "opus"
    assert seed["permissions"] == {"defaultMode": "acceptEdits"}  # allow rules ride the carry
    assert seed["hooks"]["Stop"] == USER["hooks"]["Stop"]


def test_seed_env_clash_user_wins_for_provider_keys_template_wins_otherwise(r):
    rendered = json.loads(r.render(user_path=None))
    plain = next(k for k, v in rendered["env"].items() if isinstance(v, str) and "PROXY" not in k
                 and not k.startswith(("ANTHROPIC", "AWS", "CLAUDE_CODE_USE")))
    user = {"env": {plain: "user-value", "ANTHROPIC_BASE_URL": "https://gw/", "HTTP_PROXY": "p"}}
    rendered["env"]["ANTHROPIC_BASE_URL"] = "https://template/"
    seed = settings_seed.seed_overlay(user, rendered)
    assert plain not in seed["env"]  # template wins an ordinary clash
    assert seed["env"]["ANTHROPIC_BASE_URL"] == "https://gw/" and seed["env"]["HTTP_PROXY"] == "p"


def test_seed_skips_hooks_the_template_already_has_and_lean_ctx_injections(r):
    rendered = json.loads(r.render(user_path=None))
    event, groups = next(iter(rendered["hooks"].items()))
    own = {"hooks": {event: [*groups, {"hooks": [{"type": "command", "command": "lean-ctx hook observe"}]}],
                     "Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}
    seed = settings_seed.seed_overlay(own, rendered)
    assert event not in seed.get("hooks", {})
    assert seed["hooks"]["Stop"] == [{"hooks": [{"type": "command", "command": "mine"}]}]


def test_render_appends_overlay_hooks_after_the_workbench_hooks_without_duplicates(r, tmp_path):
    overlay = tmp_path / "user.json"
    mine = {"hooks": [{"type": "command", "command": "/usr/local/bin/notify-done"}]}
    overlay.write_text(json.dumps({"hooks": {"Stop": [mine]}, "model": "opus",
                                   "permissions": {"defaultMode": "acceptEdits"}}), encoding="utf-8")
    base = json.loads(r.render(user_path=None))
    out = json.loads(r.render(user_path=overlay))
    assert out["hooks"]["Stop"][:len(base["hooks"]["Stop"])] == base["hooks"]["Stop"]
    assert out["hooks"]["Stop"][-1] == mine and out["hooks"]["Stop"].count(mine) == 1
    assert out["model"] == "opus" and out["permissions"]["defaultMode"] == "acceptEdits"
    assert out["permissions"]["deny"] == base["permissions"]["deny"]
    overlay.write_text(json.dumps({"hooks": {"Stop": base["hooks"]["Stop"]}}), encoding="utf-8")
    assert json.loads(r.render(user_path=overlay))["hooks"]["Stop"] == base["hooks"]["Stop"]


def test_install_render_runs_the_status_line_with_the_detected_interpreter(r, tmp_path, monkeypatch):
    """`render.py` adds PYTHON_EXE to the machine tokens; the install pass rendered from
    `env.tokens` alone, so statusLine fell back to `python3` and render-equivalence FAILed
    on every fresh Windows install (W8 sandbox run)."""
    import types
    import settings_install
    target = tmp_path / "t"
    target.mkdir()
    monkeypatch.setattr(r, "_USER", target / "settings.user.json")
    env = types.SimpleNamespace(tokens={"PYTHON": "py -3", "CLAUDE_DIR": "E:/u/.claude", "NODE": "node"},
                                python_exe="E:/Py/python.exe")
    settings_install.ensure(target, env, lambda *a: None, force=True, stale=lambda st: False)
    live = json.loads((target / "settings.json").read_text(encoding="utf-8"))
    assert live["statusLine"]["command"].startswith("E:/Py/python.exe ")


def _selfheal():
    spec = importlib.util.spec_from_file_location("selfheal", _ROOT / "installer" / "selfheal.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["selfheal"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_first_install_keeps_a_permanent_copy_and_seeds_the_overlay(r, tmp_path, monkeypatch):
    selfheal = _selfheal()
    target = tmp_path / "t"
    target.mkdir()
    (target / "settings.json").write_text(json.dumps(USER), encoding="utf-8")
    monkeypatch.setattr(r, "_USER", target / "settings.user.json")
    emitted: list = []
    selfheal._ensure_settings(target, None, lambda *a: emitted.append(a))
    assert json.loads((target / "settings.json.pre-install").read_text(encoding="utf-8")) == USER
    live = json.loads((target / "settings.json").read_text(encoding="utf-8"))
    assert live["env"]["CLAUDE_CODE_USE_BEDROCK"] == "1" and live["apiKeyHelper"] == "/opt/bin/get-key"
    assert live["model"] == "opus" and live["permissions"]["defaultMode"] == "acceptEdits"
    assert live["hooks"]["Stop"][-1] == USER["hooks"]["Stop"][0]
    assert (target / "settings.user.json").is_file()
    assert any("pre-install" in n for _, n, _ in emitted)
    selfheal._ensure_settings(target, None, lambda *a: None, force=True)  # a re-run changes nothing
    assert json.loads((target / "settings.json.pre-install").read_text(encoding="utf-8")) == USER
    assert json.loads((target / "settings.json").read_text(encoding="utf-8")) == live


def test_the_permanent_copy_survives_rotation_of_the_dated_backups(r, tmp_path, monkeypatch):
    selfheal = _selfheal()
    target = tmp_path / "t"
    target.mkdir()
    (target / "settings.json").write_text(json.dumps(USER), encoding="utf-8")
    monkeypatch.setattr(r, "_USER", target / "settings.user.json")
    selfheal._ensure_settings(target, None, lambda *a: None)
    for i in range(6):  # more renders than backups.KEEP
        data = json.loads((target / "settings.json").read_text(encoding="utf-8"))
        data["theme"] = f"t{i}"
        (target / "settings.json").write_text(json.dumps(data), encoding="utf-8")
        selfheal._ensure_settings(target, None, lambda *a: None, force=True)
    assert json.loads((target / "settings.json.pre-install").read_text(encoding="utf-8")) == USER


def test_the_users_file_is_kept_before_lean_ctx_can_touch_it(r, tmp_path):
    """lean-ctx's postinstall injects into settings.json during the deps step, BEFORE the render:
    the kept copy and the seed must come from the user's original, taken first thing."""
    selfheal = _selfheal()
    import settings_install
    target = tmp_path / "t"
    target.mkdir()
    (target / "settings.json").write_text(json.dumps(USER), encoding="utf-8")
    settings_install.preserve_existing(target, None, lambda *a: None)
    injected = {**USER, "hooks": {**USER["hooks"], "PostToolUse": [
        {"hooks": [{"type": "command", "command": "lean-ctx hook observe"}]}]}}
    (target / "settings.json").write_text(json.dumps(injected), encoding="utf-8")
    selfheal._ensure_settings(target, None, lambda *a: None, preserved=True)
    assert json.loads((target / "settings.json.pre-install").read_text(encoding="utf-8")) == USER
    live = json.loads((target / "settings.json").read_text(encoding="utf-8"))
    assert "lean-ctx" not in json.dumps(live) and live["env"]["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert "lean-ctx" not in (target / "settings.user.json").read_text(encoding="utf-8")


def test_a_file_only_lean_ctx_wrote_on_a_fresh_machine_is_not_the_users(r, tmp_path):
    selfheal = _selfheal()
    import settings_install
    target = tmp_path / "t"
    target.mkdir()
    settings_install.preserve_existing(target, None, lambda *a: None)  # nothing there yet
    (target / "settings.json").write_text(
        json.dumps({"hooks": {"PostToolUse": [{"hooks": [{"command": "lean-ctx hook observe"}]}]}}), encoding="utf-8")
    selfheal._ensure_settings(target, None, lambda *a: None, preserved=True)
    assert not (target / "settings.json.pre-install").exists() and not (target / "settings.user.json").exists()
    assert "lean-ctx" not in (target / "settings.json").read_text(encoding="utf-8")


def test_a_settings_json_we_rendered_is_not_treated_as_the_users(r, tmp_path, monkeypatch):
    selfheal = _selfheal()
    target = tmp_path / "t"
    target.mkdir()
    monkeypatch.setattr(r, "_USER", target / "settings.user.json")
    selfheal._ensure_settings(target, None, lambda *a: None)  # fresh machine: renders ours
    selfheal._ensure_settings(target, None, lambda *a: None, force=True)
    assert not (target / "settings.json.pre-install").exists()
    assert not (target / "settings.user.json").exists()


def test_an_existing_user_overlay_is_never_overwritten(r, tmp_path, monkeypatch):
    selfheal = _selfheal()
    target = tmp_path / "t"
    target.mkdir()
    (target / "settings.json").write_text(json.dumps(USER), encoding="utf-8")
    (target / "settings.user.json").write_text('{"theme": "mine"}', encoding="utf-8")
    monkeypatch.setattr(r, "_USER", target / "settings.user.json")
    selfheal._ensure_settings(target, None, lambda *a: None)
    assert (target / "settings.user.json").read_text(encoding="utf-8") == '{"theme": "mine"}'
    assert (target / "settings.json.pre-install").is_file()


def test_the_settings_copy_name_is_built_from_the_one_pre_install_suffix():
    """REAP-1 A6: `settings.json.pre-install` is `settings.json` + relocation's `.pre-install`, not a second constant."""
    import relocation
    import settings_install
    assert settings_install.PRE_INSTALL == "settings.json" + relocation.PRE_INSTALL == "settings.json.pre-install"
