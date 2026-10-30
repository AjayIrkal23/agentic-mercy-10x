"""lib/plan_tier.py + hooks/plan-tier-detect.py: plan-tier detection from fixture credentials (never
the machine's), the state file, the notice line, render overrides, ceilings, and the guarantee that no
token fragment reaches the state file, stdout, stderr or telemetry (MERGE-PLAN R3.3)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "plan-tier"
HOOK = str(ROOT / "hooks" / "plan-tier-detect.py")
sys.path.insert(0, str(ROOT / "hooks"))
from lib import plan_tier as PT  # noqa: E402

FRAGMENTS = ("FAKE-ACCESS", "FAKE-REFRESH", "NOT-A-TOKEN", "accessToken", "refreshToken", "oken")


@pytest.mark.parametrize("case,tier,source", [
    ("pro", "pro", "credentials"), ("max5", "max5", "credentials"), ("max20", "max20", "credentials"),
    ("max-unknown", "max5", "credentials"), ("team", "api", "credentials"),
    ("fallback", "max5", "claude.json"), ("missing", "api", "none"), ("malformed", "api", "none")])
def test_detect_maps_fixtures(case, tier, source):
    d = PT.detect(FIX / case)
    assert (d["tier"], d["source"], d["schema"]) == (tier, source, 1) and d["detected_at"] > 0


def test_detect_prefers_credentials_over_claude_json():
    assert PT.detect(FIX / "max20")["source"] == "credentials"


def test_no_fixture_token_fragment_anywhere(tmp_path):
    d = PT.detect(FIX / "max20")
    PT.write_state(d, tmp_path / "s.json")
    blob = (tmp_path / "s.json").read_text(encoding="utf-8") + json.dumps(d) + repr(d)
    for frag in FRAGMENTS:
        assert frag not in blob
    env = {**os.environ, "CLAUDE_HOOK_TELEMETRY_DIR": str(tmp_path / "tele")}
    cp = subprocess.run([sys.executable, HOOK, "--home", str(FIX / "max20"), "--state", str(tmp_path / "s2.json")],
                        input="{}", capture_output=True, text=True, env=env)
    assert cp.returncode == 0
    everything = cp.stdout + cp.stderr + "".join(
        p.read_text(encoding="utf-8") for p in (tmp_path / "tele").rglob("*") if p.is_file())
    assert "NOT-A-TOKEN" not in everything and "oken" not in everything


def test_detect_never_walks_other_keys(monkeypatch):
    seen = []

    class Spy(dict):
        def items(self):
            seen.append("items")
            return super().items()

        def keys(self):
            seen.append("keys")
            return super().keys()

        def __iter__(self):
            seen.append("iter")
            return super().__iter__()

    monkeypatch.setattr(PT, "_load_json",
                        lambda p: Spy({"claudeAiOauth": Spy({"subscriptionType": "pro", "accessToken": "X"})}))
    assert PT.detect(Path("/nonexistent"))["tier"] == "pro" and seen == []


def test_read_trusts_state_regardless_of_age(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path))
    (tmp_path / "plan-tier.json").write_text(
        json.dumps({"schema": 1, "tier": "pro", "source": "credentials", "detected_at": 0}), encoding="utf-8")
    d = PT.read()
    assert d["tier"] == "pro" and d["stale"] is True and "missing" not in d


def test_read_missing_or_invalid_falls_back_to_max20(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path))
    assert PT.read() == {"schema": 1, "tier": "max20", "source": "none", "detected_at": 0,
                         "missing": True, "stale": False}
    (tmp_path / "plan-tier.json").write_text("{ nope", encoding="utf-8")
    assert PT.read()["tier"] == "max20"
    (tmp_path / "plan-tier.json").write_text(json.dumps({"schema": 1, "tier": "platinum"}), encoding="utf-8")
    assert PT.read()["tier"] == "max20"


def test_render_overrides_per_tier():
    assert PT.render_overrides("pro") == {"model": "sonnet", "env": {"CLAUDE_CODE_SUBAGENT_MODEL": "haiku"},
                                          "fallbackModel": ["haiku"]}
    assert PT.render_overrides("max5")["model"] == "sonnet" and PT.render_overrides("api") == PT.render_overrides("max5")
    assert PT.render_overrides("max20") == {"model": "opus", "env": {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"},
                                            "fallbackModel": ["sonnet", "haiku"]}
    assert PT.render_overrides("nonsense") == PT.render_overrides("api")


def test_user_model_wins_over_render_override():  # the merge order integrate uses: template + overrides + user
    sys.path.insert(0, str(ROOT / "installer"))
    from settings_diff import deep_merge
    merged = deep_merge(deep_merge({"env": {"X": "1"}}, PT.render_overrides("pro")), {"model": "opus"})
    assert merged["model"] == "opus" and merged["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "haiku"
    assert merged["env"]["X"] == "1"


def test_ceiling_and_cap():
    assert PT.ceiling("pro") == "sonnet" and PT.cap("opus", "pro") == "sonnet" and PT.cap("fable", "max5") == "opus"
    assert PT.cap("haiku", "max20") == "haiku" and PT.cap("fable", "max20") == "fable" and PT.cap("gpt", "pro") == "gpt"


@pytest.mark.parametrize("case,main", [("pro", "sonnet"), ("max5", "sonnet"), ("max20", "opus"),
                                       ("team", "sonnet"), ("missing", "sonnet")])
def test_detect_and_state_carry_the_tier_main_model(tmp_path, monkeypatch, case, main):
    """Final-fix 4: bin/claude reads `main` from plan-tier.json and passes --model when nothing else chose one."""
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path))
    d = PT.detect(FIX / case)
    assert d["main"] == main
    PT.update_state(d)
    assert json.loads((tmp_path / "plan-tier.json").read_text(encoding="utf-8"))["main"] == main
    assert PT.read()["main"] == main


def test_read_of_a_state_file_without_main_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path))
    (tmp_path / "plan-tier.json").write_text(
        json.dumps({"schema": 1, "tier": "max20", "source": "credentials", "detected_at": 0}), encoding="utf-8")
    d = PT.read()
    assert d["tier"] == "max20" and "main" not in d


def test_write_state_and_notice(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path))
    assert PT.update_state(PT.detect(FIX / "max20"))["changed"] is False  # first ever write: no notice
    assert PT.notice_line() == ""
    r = PT.update_state(PT.detect(FIX / "pro"))
    assert r["changed"] is True and "max20 -> pro" in PT.notice_line() and "credentials" in PT.notice_line()
    assert PT.update_state(PT.detect(FIX / "pro"))["changed"] is False and PT.notice_line() == ""


def test_fail_open_on_policy_missing(monkeypatch):
    monkeypatch.setattr(PT, "_policy", lambda: {})
    assert PT.render_overrides("pro")["model"] == "sonnet" and PT.cap("opus", "pro") == "sonnet"
    assert PT.render_overrides("max20")["fallbackModel"] == ["sonnet", "haiku"]


def test_windows_stub_is_harmless(monkeypatch):
    from lib import platform as plat
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    assert PT.detect(FIX / "missing")["tier"] == "api"


# --- hooks/plan-tier-detect.py ------------------------------------------------------------

def test_acceptance_smoke_under_a_fake_home(tmp_path):
    st = tmp_path / "pt2.json"
    cp = subprocess.run([sys.executable, HOOK, "--home", str(FIX / "max20"), "--state", str(st)],
                        input="", capture_output=True, text=True,
                        env={**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)})
    assert cp.returncode == 0
    d = json.loads(st.read_text(encoding="utf-8"))
    assert d["tier"] == "max20" and "oken" not in json.dumps(d)


def test_cli_writes_state_and_prints_summary(tmp_path):
    st = tmp_path / "pt.json"
    cp = subprocess.run([sys.executable, HOOK, "--home", str(FIX / "pro"), "--state", str(st)], input="{}",
                        capture_output=True, text=True,
                        env={**os.environ, "HOME": str(tmp_path), "CLAUDE_HOOK_TELEMETRY_DIR": str(tmp_path / "t")})
    assert cp.returncode == 0 and json.loads(st.read_text(encoding="utf-8"))["tier"] == "pro"
    assert json.loads(cp.stdout.strip()) == {"tier": "pro", "source": "credentials", "changed": False}


def test_cli_tolerates_empty_stdin_and_garbage(tmp_path):
    for stdin in ("", "not json", json.dumps({"hook_event_name": "SessionStart", "source": "startup"})):
        cp = subprocess.run([sys.executable, HOOK, "--home", str(FIX / "missing"), "--state", str(tmp_path / "x.json")],
                            input=stdin, capture_output=True, text=True)
        assert cp.returncode == 0
        assert json.loads((tmp_path / "x.json").read_text(encoding="utf-8"))["tier"] == "api"


def test_cli_change_sets_notice_and_telemetry(tmp_path):
    st, tele = tmp_path / "pt.json", tmp_path / "tele"
    env = {**os.environ, "CLAUDE_HOOK_TELEMETRY_DIR": str(tele)}
    subprocess.run([sys.executable, HOOK, "--home", str(FIX / "max20"), "--state", str(st)], input="{}",
                   env=env, check=True, capture_output=True, text=True)
    cp = subprocess.run([sys.executable, HOOK, "--home", str(FIX / "pro"), "--state", str(st)], input="{}",
                        env=env, capture_output=True, text=True)
    d = json.loads(st.read_text(encoding="utf-8"))
    assert d["tier"] == "pro" and "max20 -> pro" in d["notice"] and json.loads(cp.stdout)["changed"] is True
    rows = "".join(p.read_text(encoding="utf-8") for p in tele.rglob("*.jsonl"))
    assert '"plan-tier-detect"' in rows and "pro" in rows and "NOT-A-TOKEN" not in rows and "oken" not in rows


def _hook_module():
    spec = importlib.util.spec_from_file_location("plan_tier_detect_under_test", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_rerenders_on_a_tier_change_render_first_builder_fallback(tmp_path, monkeypatch, capsys):
    mod = _hook_module()
    calls = []
    monkeypatch.setattr(mod, "_spawn", lambda cmd: calls.append(cmd))
    root, st = tmp_path / "root", tmp_path / "pt.json"
    (root / "scripts").mkdir(parents=True)
    argv = ["--root", str(root), "--state", str(st), "--quiet"]
    assert mod.main(argv + ["--home", str(FIX / "max20")]) == 0
    assert mod.main(argv + ["--home", str(FIX / "pro")]) == 0  # changed, but no builder yet
    assert calls == []
    builder = root / "scripts" / "build_workflows.py"
    builder.write_text("# fake\n", encoding="utf-8")
    assert mod.main(argv + ["--home", str(FIX / "max5")]) == 0  # changed + builder -> one detached call
    assert len(calls) == 1 and calls[0][-1] == str(builder)
    assert mod.main(argv + ["--home", str(FIX / "max5")]) == 0  # unchanged -> no call
    assert len(calls) == 1
    (root / "installer").mkdir()
    (root / "installer" / "render.py").write_text("# fake\n", encoding="utf-8")
    assert mod.main(argv + ["--home", str(FIX / "pro")]) == 0      # changed + render.py -> render, not the builder
    assert len(calls) == 2 and calls[1][-1] == str(root / "installer" / "render.py")
    assert capsys.readouterr().out == ""  # --quiet


def test_cli_windows_stub_exits_zero(monkeypatch, tmp_path, capsys):
    mod = _hook_module()
    from lib import platform as plat
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    assert mod.main(["--home", str(FIX / "missing"), "--state", str(tmp_path / "w.json")]) == 0
    assert json.loads(capsys.readouterr().out)["tier"] == "api"
