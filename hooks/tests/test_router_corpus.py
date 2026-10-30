"""Router replay corpus: hard rows never misroute; soft rows stay under the budget.

Rows live in ``fixtures/router_corpus.jsonl`` (paraphrased; the repo is public: no IPs
beyond TEST-NET, no hostnames, no customer names). Each row runs through
``router.route_payload`` in-process against a synthetic repo in tmp, with the dev-server
listener probe patched (no ``ss``, no ``/proc``), so it runs the same on Linux and Windows.

Row keys: ``must`` / ``must_any`` / ``must_not`` are substrings of the injected context;
``must_not_rank1`` must not sit on the MUST-READ line; ``empty`` means no output at all
(machine prompts); ``intent_has`` / ``intent_lacks`` are classify-level asserts.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import uuid

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import classify as C  # noqa: E402
from prompt_router import router as R  # noqa: E402
from prompt_router.modules import mcp_routes as M  # noqa: E402

ROWS = [json.loads(line) for line in (_HOOKS / "tests" / "fixtures" / "router_corpus.jsonl")
        .read_text(encoding="utf-8").splitlines() if line.strip()]
# share of soft rows allowed to still miss (scripts/router_replay.py reads hooks/router-budget.json
# for the live corpus; this is the committed-fixture twin)
SOFT_BUDGET = 0.10


def _continue_prompt() -> str:
    path = _HOOKS.parent / "scripts" / "restore_sessions.py"
    spec = importlib.util.spec_from_file_location("_corpus_restore_sessions", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.CONTINUE_PROMPT


def _git_init(d: pathlib.Path) -> None:
    subprocess.run(["git", "init", "-q", str(d)], check=True)


def _repo(kind: str, tmp: pathlib.Path) -> pathlib.Path:
    """Synthetic repos only: no real project on disk (Windows/CI safe)."""
    if kind == "none":
        d = tmp / "plain"
        d.mkdir(exist_ok=True)
        return d
    d = tmp / kind
    if d.exists():
        return d
    d.mkdir()
    _git_init(d)
    if kind == "py":
        (d / "src").mkdir()
        (d / "src" / "__init__.py").write_text("", encoding="utf-8")
        (d / "main.py").write_text("", encoding="utf-8")
    elif kind == "fe3":
        (d / "package.json").write_text(json.dumps(
            {"dependencies": {"react": "18.3.1", "vite": "5.4.0", "three": "0.172.0"}}), encoding="utf-8")
    elif kind == "server":
        (d / "server").mkdir()
        (d / "server" / "package.json").write_text(json.dumps(
            {"dependencies": {"express": "4.21.0"}}), encoding="utf-8")
    elif kind == "supabase":
        (d / "supabase").mkdir()
        (d / "package.json").write_text(json.dumps(
            {"dependencies": {"@supabase/supabase-js": "2.45.0"}}), encoding="utf-8")
    return d


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    monkeypatch.setattr(M, "server_available", lambda names, _roots=None: (list(names) or [None])[0])
    return tmp_path


def _route(row: dict, tmp: pathlib.Path, monkeypatch) -> str:
    if row["repo"] == "judge":
        cfg = tmp / "cfg"
        (cfg / "double-shot-latte").mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
        root, cwd = None, cfg / "double-shot-latte"
    else:
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        root = _repo(row["repo"], tmp)
        cwd = root / "server" if row["repo"] == "server" else root
    lst = row.get("listener", "none")
    owner = {"own": str(root), "foreign": str(tmp / "elsewhere")}.get(lst)
    M.dev_server_port.cache_clear()
    M.reticle_instrumented.cache_clear()
    monkeypatch.setattr(M, "_listeners", lambda: [(5173, 4242)] if owner else [])
    monkeypatch.setattr(M, "_pid_cwd", lambda pid: owner)
    prompt = row["prompt"] if row["id"] != "M2" else _continue_prompt()
    return R.route_payload({"session_id": f"corpus-{row['id']}-{uuid.uuid4().hex[:6]}",
                            "cwd": str(cwd), "prompt": prompt})


def _misses(row: dict, text: str) -> list[str]:
    out = [f"missing {s}" for s in row.get("must", []) if s not in text]
    if row.get("must_any") and not any(s in text for s in row["must_any"]):
        out.append("none of must_any")
    out += [f"has {s}" for s in row.get("must_not", []) if s in text]
    first = next((ln for ln in text.splitlines() if "(MUST-READ)" in ln), "")
    out += [f"rank1 {s}" for s in row.get("must_not_rank1", []) if s in first]
    if row.get("empty") and text.strip():
        out.append("not empty")
    return out


@pytest.mark.parametrize("row", [r for r in ROWS if r["kind"] in ("hard", "pos")], ids=lambda r: r["id"])
def test_hard_and_positive_rows(row, env, monkeypatch):
    text = _route(row, env, monkeypatch)
    assert not _misses(row, text), (row["id"], _misses(row, text), text[:1500])


def test_soft_rows_within_budget(env, monkeypatch):
    soft = [r for r in ROWS if r["kind"] == "soft"]
    bad = {r["id"]: m for r in soft if (m := _misses(r, _route(r, env, monkeypatch)))}
    assert len(bad) / len(soft) <= SOFT_BUDGET, bad


@pytest.mark.parametrize("row", [r for r in ROWS if r.get("intent_has") or r.get("intent_lacks")],
                         ids=lambda r: r["id"])
def test_intents(row):
    p = C.classify({"prompt": row["prompt"], "cwd": "/nonexistent-dir"})
    assert set(row.get("intent_has", [])) <= set(p.intents), dict(p.intents)
    assert not set(row.get("intent_lacks", [])) & set(p.intents), dict(p.intents)


def test_continue_prompt_is_machine():
    assert C.is_trivial_ack(_continue_prompt())


def test_row_ids_unique():
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids))
