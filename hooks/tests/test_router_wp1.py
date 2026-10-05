"""WP1 router fixes from the 2026-10-05 audit (C-04, C-07, C-12 classify side).

C-04  negation window ("no need for", "don't", "do not", "without" within 3 words)
      drops the negated keyword; light plural stemming ("bugs", "crashes", "errors");
      "write <x> tests" -> TEST; "crashed", "didn't work" -> DEBUG.
C-12  LARGE size comes from phrases, never from one noun ("websocket", "streaming").
C-07  Expo / React Native repos get a `mobile` surface; the bare word "mobile" is no
      longer a web-UI keyword.
Runnable: `python3 -m pytest hooks/tests/test_router_wp1.py -q`.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from prompt_router import classify as C           # noqa: E402
from prompt_router.modules import surface as SF   # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_stack_cache(tmp_path, monkeypatch):
    cache = tmp_path / "state"
    cache.mkdir()
    monkeypatch.setattr(SF, "_cache_dir", lambda: cache)


def _prof(prompt: str, cwd: pathlib.Path):
    return C.classify({"prompt": prompt, "cwd": str(cwd), "session_id": "t-wp1"})


# --------------------------------------------------------------------------- C-04
@pytest.mark.parametrize("prompt,absent", [
    ("no need for a security review, only rename the variable", {"SECURITY", "REVIEW"}),
    ("do not add tests, just fix the typo in README", {"TEST"}),
    ("don't write tests for this one, just bump the version", {"TEST"}),
    ("rename the helper without breaking the tests", set()),
])
def test_negated_keywords_do_not_count(prompt, absent, tmp_path):
    assert not absent & set(_prof(prompt, tmp_path).intents)


def test_negation_only_covers_three_words(tmp_path):
    p = _prof("do not touch the readme, but debug the crash in the login flow", tmp_path)
    assert "DEBUG" in p.intents


@pytest.mark.parametrize("prompt,intent", [
    ("fix the bugs in the admin panel", "DEBUG"),
    ("the Expo app crashes on Android 14 when opening the camera", "DEBUG"),
    ("the export crashed after the last deploy", "DEBUG"),
    ("hmm that didn't work", "DEBUG"),
    ("CI shows no-explicit-any errors in the expenses api", "DEBUG"),
    ("write vitest tests for the useProjectFilters hook in src/hooks", "TEST"),
    ("write some unit tests for the parser", "TEST"),
])
def test_plurals_and_phrases_reach_their_intent(prompt, intent, tmp_path):
    assert intent in _prof(prompt, tmp_path).intents


def test_plural_stemming_is_for_intents_only():
    """`components` in a path must not become a UI hit (UI lists carry their own plurals)."""
    m = C.KeywordMatcher({"act:DEBUG": ["bug"], "ui": ["component"]})
    assert m.hits("fix the bugs in src/components/x.tsx") == {"act:DEBUG": ["bug"]}


# --------------------------------------------------------------------------- C-12
@pytest.mark.parametrize("prompt", [
    "fix the websocket reconnect bug in the telegram sender",
    "fix the streaming bug where the chart is empty on the dashboard",
])
def test_single_nouns_do_not_make_a_task_large(prompt, tmp_path):
    assert _prof(prompt, tmp_path).size != "L"


def test_scale_phrases_still_make_a_task_large(tmp_path):
    assert _prof("refactor across the codebase and rewrite the auth module from scratch",
                 tmp_path).size == "L"


# --------------------------------------------------------------------------- C-16
def test_both_routers_load_weights_identically(tmp_path, monkeypatch):
    """One loader: clamp to [0.1, 1.0] (demote only) and drop keys that name no skill."""
    import importlib
    from prompt_router import select as S
    f = tmp_path / "w.json"
    f.write_text(json.dumps({"weights": {"debug-investigation": 1.5, "tdd": 0.01,
                                         "forensic-hotspot-finder": 0.5, "x": "bad"}}))
    known = {"debug-investigation", "tdd"}
    monkeypatch.setattr(S, "_WEIGHTS", f)
    monkeypatch.setattr(S, "index_meta", lambda: {k: {} for k in known})
    sr = importlib.import_module("skill_router")
    monkeypatch.setattr(sr, "WEIGHTS_FILE", f)
    want = {"debug-investigation": 1.0, "tdd": 0.1}
    assert S._weights() == want
    assert sr._load_weights(known) == want


# --------------------------------------------------------------------------- C-07
def _mobile_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "mono"
    (root / ".git").mkdir(parents=True)
    (root / "package.json").write_text(json.dumps({"dependencies": {"react": "^18", "vite": "^7"}}),
                                       encoding="utf-8")
    app = root / "mobile-app"
    app.mkdir()
    (app / "package.json").write_text(json.dumps({"dependencies": {
        "expo": "^53", "expo-router": "^5", "react-native": "0.79", "react": "^19"}}), encoding="utf-8")
    return root


def test_expo_dependencies_add_a_mobile_stack_tag(tmp_path):
    root = _mobile_repo(tmp_path)
    repo = type("R", (), {"root": str(root), "key": "mono-t"})()
    assert "mobile" in SF.stack_fingerprint(repo)["tags"]


def test_mobile_prompt_gets_mobile_surface_not_web(tmp_path):
    root = _mobile_repo(tmp_path)
    p = _prof("the Expo app crashes on Android 14 when opening the camera", root)
    assert "mobile" in p.surfaces
    assert not {"frontend", "backend"} & (p.surfaces - p.weak_surfaces)


def test_mobile_surface_maps_to_the_expo_skill():
    from types import SimpleNamespace
    from prompt_router import select as S
    p = SimpleNamespace(surfaces={"mobile"}, weak_surfaces=set())
    assert S._surface_skills(p).get("expo-react-native", 0) >= 3.0


def test_bare_mobile_word_is_not_a_ui_signal(tmp_path):
    p = _prof("plan how to add offline mode to the mobile app", tmp_path)
    assert "mobile" not in p.ui_hit
    assert not p.is_ui
