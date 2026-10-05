"""Router scoring fixes from the 2026-10-05 audit (C-01, C-02, C-09).

C-02  description-derived keywords (index `source: description`) count half and cap at
      2.0; select.py only checked `floor-fallback`, a value the builder never writes.
C-09  hidden / user-only skills (`disable-model-invocation`) are never pushed.
C-01  learned weights may demote but never boost: the weights loop is fed by test
      sessions and its input froze on 2026-09-27.
"""
from __future__ import annotations

import pathlib
import sys
from types import SimpleNamespace

HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from prompt_router import classify as C  # noqa: E402
from prompt_router import select as S    # noqa: E402

KWS = ["alpha beta", "gamma", "delta", "epsilon", "zeta", "theta"]


def _profile(text: str):
    return SimpleNamespace(text=text, intents=(), surfaces=(), paths=())


def _score(source: str) -> float:
    index = {"skills": {"x": {"source": source, "keywords": KWS}}}
    p = _profile(" ".join(KWS))
    return S._index_skills(p, index, C.ngrams(p.text)).get("x", 0.0)


def test_description_keywords_count_half_and_cap_at_two():
    assert _score("description") == 2.0
    assert _score("floor-fallback") == 2.0
    assert _score("metadata") == 4.0


def test_stack_only_surface_earns_half_surface_credit():
    """C-03: a surface known only from the repo stack (not the prompt) is weak."""
    index = {"skills": {"x": {"source": "metadata", "keywords": [], "surfaces": ["backend"]}}}
    strong = SimpleNamespace(text="", intents=(), surfaces=("backend",), paths=(), weak_surfaces=set())
    weak = SimpleNamespace(text="", intents=(), surfaces=("backend",), paths=(), weak_surfaces={"backend"})
    assert S._index_skills(strong, index, set())["x"] == 1.0
    assert S._index_skills(weak, index, set())["x"] == 0.5


def test_hidden_skills_are_never_ranked(tmp_path):
    prof = C.classify({"prompt": "use context7 mcp to fetch the docs for the react library",
                       "cwd": str(tmp_path), "session_id": "t-c09"})
    hidden = {n for n, m in (S._load_json(S._SKILLS_INDEX).get("skills") or {}).items()
              if isinstance(m, dict) and m.get("hidden")}
    assert hidden, "index should flag user-only skills"
    assert not hidden & {n for n, _ in S.rank_all(prof)}


def _intents(prompt: str, tmp_path) -> set:
    return set(C.classify({"prompt": prompt, "cwd": str(tmp_path), "session_id": "t-c04"}).intents)


def test_urls_and_guard_names_are_not_security(tmp_path):
    """C-04: `https` in a URL and tool names like tdd-guard were SECURITY triggers."""
    assert "SECURITY" not in _intents("follow https://example.com/docs/guide to upgrade vite", tmp_path)
    assert "SECURITY" not in _intents("fix the tdd-guard advisory wording", tmp_path)
    assert "SECURITY" in _intents("harden the login endpoint against brute force", tmp_path)


def test_weights_demote_but_never_boost(tmp_path, monkeypatch):
    prof = C.classify({"prompt": "add a REST endpoint with pagination and a vitest test",
                       "cwd": str(tmp_path), "session_id": "t-c01"})
    base = dict(S.rank_all(prof))
    name = next(iter(base))
    monkeypatch.setattr(S, "_weights", lambda: {name: 1.5})
    assert dict(S.rank_all(prof))[name] == base[name]
    monkeypatch.setattr(S, "_weights", lambda: {name: 0.5})
    assert dict(S.rank_all(prof))[name] == base[name] * 0.5
