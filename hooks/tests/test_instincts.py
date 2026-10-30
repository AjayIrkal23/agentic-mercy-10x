"""Tests for hooks/tools/instincts.py (package learning, docs/LEARNING.md).

Storage and identity, the ollama evolve step (skip, defer, write, re-affirm, decay/prune,
promote, compact, dry-run, budget, lock), session-start surfacing (direct and through
session_notices' exec path) and the status/export/import CLI with the import SSRF guard.
ollama is always faked; no test opens a socket.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import sys
import time
import urllib.error
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HOOKS))
from lib import model_mode, ollama, platform as plat, session_notices  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "learning"
NOW = 1_800_000_000.0
DAY = 86400.0


def _load():
    spec = importlib.util.spec_from_file_location("instincts_under_test", _HOOKS / "tools" / "instincts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inst = _load()


def _learning() -> Path:
    return plat.state_dir() / "learning"


def obs_path(key: str) -> Path:
    return _learning() / key / "observations.jsonl"


def inst_path(key: str) -> Path:
    return _learning() / "instincts" / f"{key}.jsonl"


@pytest.fixture
def box(tmp_path, monkeypatch):
    state = tmp_path / "state"
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(state))
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    monkeypatch.setattr(inst, "_now", lambda: NOW)
    monkeypatch.setattr(inst, "_CONFIG_PATH", tmp_path / "learning.config.json")
    key = inst.repo_key_of(str(repo))
    return {"state": state, "repo": repo, "key": key, "tmp": tmp_path, "obs": obs_path(key), "inst": inst_path(key),
            "glob": state / "learning" / "instincts" / "global.jsonl", "cursor": state / "learning" / key / "evolve.json"}


def new_repo(box, name):
    r = box["tmp"] / name
    (r / ".git").mkdir(parents=True)
    return r, inst.repo_key_of(str(r))


def seed_obs(key, n=30, start=NOW - 3600):
    sample = [json.loads(ln) for ln in (FIX / "observations-sample.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = []
    for i in range(n):
        r = dict(sample[i % len(sample)])
        r["ts"] = start + i * 60
        rows.append(r)
    p = obs_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return rows


def put_instincts(path: Path, fixture: str):
    text = (FIX / fixture).read_text(encoding="utf-8")
    text = (text.replace('"__TS__"', repr(NOW)).replace('"__OLDER__"', repr(NOW - 60 * DAY))
            .replace('"__OLD__"', repr(NOW - 15 * DAY)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def read_jsonl(path: Path):
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def write_rows(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def write_cfg(box, **cfg):
    (box["tmp"] / "learning.config.json").write_text(json.dumps(cfg), encoding="utf-8")


REPLY = json.loads((FIX / "ollama-reply.json").read_text(encoding="utf-8"))


def fake_ollama(monkeypatch, alive=True, reply=REPLY):
    calls = []
    monkeypatch.setattr(inst.ollama, "alive", lambda timeout_s=1.5: alive)

    def chat(model, messages, timeout_s=60, **kw):
        calls.append({"model": model, "messages": messages, "timeout_s": timeout_s})
        return reply
    monkeypatch.setattr(inst.ollama, "chat", chat)
    return calls


def cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = inst.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class _Ctx:
    def __init__(self, val):
        self.val = val

    def __enter__(self):
        return self.val

    def __exit__(self, *a):
        return False


def tel_rows(box):
    return [json.loads(ln) for f in (box["tmp"] / "tel").glob("hook-fires-*.jsonl")
            for ln in f.read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------- storage / identity
def test_repo_key_matches_model_mode(box):
    assert inst.repo_key_of(str(box["repo"])) == model_mode.repo_key(str(box["repo"]))
    plain = box["tmp"] / "plain"
    plain.mkdir()
    assert re.fullmatch(r"plain-[0-9a-f]{12}", inst.repo_key_of(str(plain)))
    assert inst.repo_key_of("") is None


def test_instinct_id_is_the_normalised_text_hash():
    assert inst.instinct_id("Run  npm test!") == inst.instinct_id("run npm test")
    assert re.fullmatch(r"[0-9a-f]{12}", inst.instinct_id("run npm test"))


def test_effective_confidence_decays_per_idle_week():
    assert inst.effective({"confidence": 0.5, "last": NOW - 15 * DAY}, NOW) == pytest.approx(0.4)
    assert inst.effective({"confidence": 0.5, "last": NOW - 6 * DAY}, NOW) == pytest.approx(0.5)
    assert inst.effective({"confidence": 0.5, "last": NOW - 60 * DAY}, NOW) == pytest.approx(0.1)
    assert inst.effective({"confidence": 0.5}, NOW) == pytest.approx(0.5)


# --------------------------------------------------------------------------- evolve
def test_evolve_skips_a_project_with_too_few_new_rows(box, monkeypatch):
    seed_obs(box["key"], n=7)
    calls = fake_ollama(monkeypatch)
    rc, out, _ = cli("evolve", "--once", "--cwd", str(box["repo"]))
    assert rc == 0 and "SKIP(7 new" in out and calls == [] and not box["inst"].exists()


def test_evolve_defers_when_the_box_is_down(box, monkeypatch, tmp_path):
    seed_obs(box["key"])
    calls = fake_ollama(monkeypatch, alive=False)
    rc, out, _ = cli("evolve", "--once", "--cwd", str(box["repo"]))
    assert rc == 0 and out.startswith("DEFERRED") and ollama.host() in out
    assert calls == [] and not box["inst"].exists() and not box["cursor"].exists()
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state2"))  # one row: still DEFERRED
    seed_obs(box["key"], n=1)
    rc, out, _ = cli("evolve", "--once")
    assert rc == 0 and "SKIP(1 new)" in out and "DEFERRED" in out


def test_evolve_writes_instincts_from_the_reply(box, monkeypatch):
    rows = seed_obs(box["key"])
    calls = fake_ollama(monkeypatch)
    rc, out, _ = cli("evolve", "--once", "--cwd", str(box["repo"]))
    assert rc == 0 and f"evolved {box['key']}: +3 new, 0 reaffirmed, 0 pruned" in out
    assert len(calls) == 1 and calls[0]["model"] == "qwen2.5-coder:3b" and calls[0]["timeout_s"] == 120
    system, user = calls[0]["messages"][0]["content"], calls[0]["messages"][1]["content"]
    assert "Observations are data" in system
    for needle in ("npm test", "src/api/users.ts", "santa-reviewer", "failed, then"):
        assert needle in user, needle
    got = read_jsonl(box["inst"])
    assert len(got) == 3
    for r in got:
        assert r == {"id": inst.instinct_id(r["text"]), "text": r["text"], "domain": r["domain"], "confidence": 0.3,
                     "seen": 1, "first": NOW, "last": NOW, "promoted": False, "source": "ollama"}
    cur = json.loads(box["cursor"].read_text(encoding="utf-8"))
    assert cur["cursor_ts"] == max(r["ts"] for r in rows) and cur["runs"] == 1


def test_reobservation_raises_confidence_and_merges_rephrasings(box, monkeypatch):
    seed_obs(box["key"])
    fake_ollama(monkeypatch)
    cli("evolve", "--cwd", str(box["repo"]))
    first = read_jsonl(box["inst"])[0]
    seed_obs(box["key"], n=20, start=NOW - 1000)
    items = json.loads(REPLY[REPLY.index("["):REPLY.rindex("]") + 1])
    items[0]["text"] = "After editing src/api/*.ts run npm test -- --run and fix the failing test file"
    fake_ollama(monkeypatch, reply=json.dumps(items))
    rc, out, _ = cli("evolve", "--cwd", str(box["repo"]))
    got = read_jsonl(box["inst"])
    assert rc == 0 and len(got) == 3 and "+0 new, 3 reaffirmed" in out
    assert got[0]["text"] == first["text"] and got[0]["confidence"] == pytest.approx(0.4)
    assert got[0]["seen"] == 2 and got[0]["last"] == NOW


def test_decay_and_prune(box, monkeypatch):
    put_instincts(box["inst"], "instincts-project-a.jsonl")
    seed_obs(box["key"])
    fake_ollama(monkeypatch, reply="[]")
    rc, out, _ = cli("evolve", "--cwd", str(box["repo"]))
    got = {r["id"]: r for r in read_jsonl(box["inst"])}
    assert rc == 0 and "prune-me" not in got and "1 pruned" in out
    assert got["decay-me"]["confidence"] == 0.5 and inst.effective(got["decay-me"], NOW) == pytest.approx(0.4)


def test_promotion_across_two_projects(box, monkeypatch):
    repo_b, key_b = new_repo(box, "repo-b")
    put_instincts(box["inst"], "instincts-project-a.jsonl")
    put_instincts(inst_path(key_b), "instincts-project-b.jsonl")
    seed_obs(box["key"])
    seed_obs(key_b)
    fake_ollama(monkeypatch, reply="[]")
    rc, out, _ = cli("evolve", "--all")
    glob = read_jsonl(box["glob"])
    assert rc == 0 and "1 promoted" in out and len(glob) == 1
    g = glob[0]
    assert g["id"] == "promote-me" and g["promoted"] is True and g["confidence"] == pytest.approx(0.85)
    assert g["projects"] == sorted([box["key"], key_b])
    for p in (box["inst"], inst_path(key_b)):
        assert next(r for r in read_jsonl(p) if r["id"] == "promote-me")["promoted"] is True
    seed_obs(box["key"], start=NOW - 100)
    seed_obs(key_b, start=NOW - 100)
    cli("evolve", "--all")
    assert len(read_jsonl(box["glob"])) == 1


def test_evolve_compacts_the_observation_log(box, monkeypatch):
    write_cfg(box, max_rows_per_project=25)
    rows = seed_obs(box["key"])
    fake_ollama(monkeypatch, reply="[]")
    cli("evolve", "--cwd", str(box["repo"]))
    kept = read_jsonl(box["obs"])
    assert [r["ts"] for r in kept] == [r["ts"] for r in rows[-25:]]


def test_dry_run_calls_alive_but_never_chat_and_writes_nothing(box, monkeypatch):
    seed_obs(box["key"])
    calls = fake_ollama(monkeypatch)
    rc, out, _ = cli("evolve", "--dry-run", "--cwd", str(box["repo"]))
    assert rc == 0 and f"would evolve {box['key']} (30 new)" in out and "ollama: up" in out
    assert calls == [] and not box["inst"].exists() and not box["cursor"].exists() and not box["glob"].exists()


def test_budget_stops_remaining_projects(box, monkeypatch):
    _, key_b = new_repo(box, "repo-b")
    seed_obs(box["key"])
    seed_obs(key_b)
    calls = fake_ollama(monkeypatch)
    rc, out, _ = cli("evolve", "--budget=-1")
    assert rc == 0 and out.count("time budget used") == 2 and calls == []
    assert not box["cursor"].exists()


def test_chat_none_is_a_per_project_defer(box, monkeypatch):
    seed_obs(box["key"])
    fake_ollama(monkeypatch, reply=None)
    rc, out, _ = cli("evolve", "--cwd", str(box["repo"]))
    assert rc == 0 and f"DEFERRED {box['key']}: no answer from qwen2.5-coder:3b" in out
    assert not box["cursor"].exists()


def test_lock_busy_exits_quietly(box, monkeypatch):
    seed_obs(box["key"])
    calls = fake_ollama(monkeypatch)
    monkeypatch.setattr(inst, "_try_lock", lambda p: _Ctx(False))
    assert cli("evolve") == (0, "busy\n", "") and calls == []


def test_unparseable_reply_is_a_defer_not_a_crash(box, monkeypatch):
    seed_obs(box["key"])
    fake_ollama(monkeypatch, reply="I cannot help with that")
    rc, out, _ = cli("evolve", "--cwd", str(box["repo"]))
    assert rc == 0 and f"DEFERRED {box['key']}: unparseable reply" in out
    assert any(r.get("kind") == "evolve_bad_reply" for r in tel_rows(box))
    assert not box["inst"].exists()


# --------------------------------------------------------------------------- surfacing
def _row(iid, conf, text):
    return {"id": iid, "text": text, "domain": "workflow", "confidence": conf, "seen": 2, "first": NOW, "last": NOW,
            "promoted": False, "source": "ollama"}


def seed_surface(box):
    write_rows(box["inst"], [_row("p95", 0.95, "Project habit ninety five"), _row("p75", 0.75, "Project habit seventy five"),
                             _row("p72", 0.72, "Project habit seventy two"), _row("p50", 0.5, "Project habit fifty")])
    write_rows(box["glob"], [dict(_row("g90", 0.9, "Global habit ninety"), promoted=True, projects=["a", "b"])])


def test_lines_rank_project_first_and_cap_three(box):
    seed_surface(box)
    got = inst.lines(str(box["repo"]), limit=3, min_confidence=0.7)
    # project rows get +0.25 for ranking: 0.95 -> 1.2, 0.75 -> 1.0, 0.72 -> 0.97, all above global 0.9
    assert got == ["instinct 95%: Project habit ninety five", "instinct 75%: Project habit seventy five",
                   "instinct 72%: Project habit seventy two"]
    more = inst.lines(str(box["repo"]), limit=5, min_confidence=0.7)
    assert more[3] == "instinct 90%: Global habit ninety" and len(more) == 4  # 0.5 never surfaces
    for ln in more:
        assert re.fullmatch(r"instinct \d{1,3}%: .{1,110}", ln)
    assert len(inst.lines(str(box["repo"]), limit=1)) == 1
    write_rows(box["inst"], [_row("long", 0.9, "x" * 300)])
    (ln,) = inst.lines(str(box["repo"]), limit=1)
    assert len(ln) == 110 and ln.endswith("…")


def test_lines_through_session_notices_exec_path(box, monkeypatch, tmp_path):
    seed_surface(box)
    monkeypatch.setattr(session_notices, "_HOOKS", _HOOKS)
    want = inst.lines(str(box["repo"]), limit=3, min_confidence=0.7)
    assert session_notices.instinct_lines(str(box["repo"])) == want
    with box["inst"].open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    assert session_notices.instinct_lines(str(box["repo"])) == want
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "empty"))
    assert session_notices.instinct_lines(str(box["repo"])) == []


def test_lines_are_read_only_and_fast(box):
    seed_surface(box)
    snap = {p: p.stat().st_mtime_ns for p in box["state"].rglob("*") if p.is_file()}
    t0 = time.monotonic()
    for _ in range(20):
        inst.lines(str(box["repo"]))
    assert time.monotonic() - t0 < 2.0
    assert {p: p.stat().st_mtime_ns for p in box["state"].rglob("*") if p.is_file()} == snap


# --------------------------------------------------------------------------- CLI
def test_status_without_network(box, monkeypatch):
    seed_obs(box["key"])
    put_instincts(box["inst"], "instincts-project-a.jsonl")
    fake_ollama(monkeypatch)
    monkeypatch.setattr(inst.ollama, "models", lambda timeout_s=3: ["qwen2.5-coder:3b"])
    rc, out, _ = cli("status", "--cwd", str(box["repo"]))
    assert rc == 0 and ollama.host() in out and "ollama: up" in out and "model qwen2.5-coder:3b: present" in out
    assert f"project {box['key']} (current): 30 observations (30 new), 3 instincts" in out
    assert " 85%  [workflow] Run the type checker" in out and "global: 0" in out
    rc, out, _ = cli("status", "--json", "--cwd", str(box["repo"]))
    data = json.loads(out)
    assert {"host", "alive", "model", "model_present", "projects", "global"} <= set(data)
    assert data["alive"] is True and data["model_present"] is True and data["projects"][0]["instincts"] == 3


def test_export_json_and_yaml(box, monkeypatch):
    put_instincts(box["inst"], "instincts-project-a.jsonl")
    rc, out, _ = cli("export", "--min", "0.7", "--cwd", str(box["repo"]))
    data = json.loads(out)
    assert rc == 0 and [r["id"] for r in data] == ["promote-me"] and data[0]["effective"] == pytest.approx(0.85)
    rc, out, _ = cli("export", "--yaml", "--cwd", str(box["repo"]))
    text = "Run the type checker before every commit in this repository"
    assert ("---\nid: promote-me\ntrigger: " + json.dumps(text) + "\nconfidence: 0.85\ndomain: workflow\n"
            "source: ollama\nscope: project\n---\n\n# " + text + "\n\n## Action\n" + text + "\n") in out
    target = box["tmp"] / "x.yaml"
    rc, out, _ = cli("export", "--yaml", "--output", str(target), "--cwd", str(box["repo"]))
    assert rc == 0 and out.startswith("exported 3 to") and "id: decay-me" in target.read_text(encoding="utf-8")


def test_import_file_merges_by_text_hash(box):
    put_instincts(box["inst"], "instincts-project-a.jsonl")
    rc, out, _ = cli("import", str(FIX / "import-ecc.yaml"), "--cwd", str(box["repo"]))
    assert rc == 0 and "added 1, merged 1" in out
    got = {r["text"]: r for r in read_jsonl(box["inst"])}
    vit = got["Run vitest with --run, never watch mode."]
    assert vit["source"] == "import:import-ecc.yaml" and vit["confidence"] == pytest.approx(0.7)
    merged = got["Run the type checker before every commit in this repository"]
    assert merged["confidence"] == pytest.approx(0.9) and merged["seen"] == 6 and merged["id"] == "promote-me"
    rc, out, _ = cli("import", str(FIX / "import.json"), "--cwd", str(box["repo"]))
    assert rc == 0 and "added 1, merged 1" in out
    got = {r["text"]: r for r in read_jsonl(box["inst"])}
    assert got["Run vitest with --run, never watch mode."]["confidence"] == pytest.approx(0.7)
    assert "Mock the network layer at the fetch boundary in unit tests" in got
    before = box["inst"].read_text(encoding="utf-8")
    rc, out, _ = cli("import", str(FIX / "import.json"), "--dry-run", "--global", "--cwd", str(box["repo"]))
    assert rc == 0 and not box["glob"].exists() and box["inst"].read_text(encoding="utf-8") == before
    rc, out, _ = cli("import", str(FIX / "import.json"), "--global")
    assert rc == 0 and len(read_jsonl(box["glob"])) == 2


class _HttpResp:
    def __init__(self, body: bytes, ctype: str):
        self._b, self.headers = body, {"Content-Type": ctype}

    def read(self, n=-1):
        return self._b if n < 0 else self._b[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_import_url_guard(box, monkeypatch):
    rc, _, err = cli("import", "http://example.com/x.yaml", "--cwd", str(box["repo"]))
    assert rc == 1 and "https only" in err
    opened = []
    monkeypatch.setattr(inst, "_open_https", lambda url, timeout: opened.append(url))
    for addr in (("127.0.0.1", 443), ("10.0.0.5", 443), ("169.254.1.1", 443), ("::1", 443, 0, 0), ("0.0.0.0", 443)):
        monkeypatch.setattr(inst.socket, "getaddrinfo", lambda *a, _s=addr, **k: [(2, 1, 6, "", _s)])
        rc, _, err = cli("import", "https://example.com/x.yaml", "--cwd", str(box["repo"]))
        assert rc == 1 and "non-public address" in err, addr
    assert opened == []  # the guard runs before any connection
    monkeypatch.setattr(inst.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    monkeypatch.setattr(inst, "_open_https", lambda url, timeout: _HttpResp(b"x" * (1048576 + 1), "text/yaml"))
    rc, _, err = cli("import", "https://example.com/x.yaml", "--cwd", str(box["repo"]))
    assert rc == 1 and "exceeds 1048576 bytes" in err

    def redirect(url, timeout):
        raise urllib.error.HTTPError(url, 302, "Found", {}, None)
    monkeypatch.setattr(inst, "_open_https", redirect)
    rc, _, err = cli("import", "https://example.com/x.yaml", "--cwd", str(box["repo"]))
    assert rc == 1 and "redirects are not followed" in err
    body = (FIX / "import-ecc.yaml").read_bytes()
    monkeypatch.setattr(inst, "_open_https", lambda url, timeout: _HttpResp(body, "application/zip"))
    rc, _, err = cli("import", "https://example.com/x.yaml", "--cwd", str(box["repo"]))
    assert rc == 1 and "unsupported content type" in err
    monkeypatch.setattr(inst, "_open_https", lambda url, timeout: _HttpResp(body, "text/yaml"))
    rc, out, _ = cli("import", "https://example.com/x.yaml", "--cwd", str(box["repo"]))
    assert rc == 0 and {r["source"] for r in read_jsonl(box["inst"])} == {"import:example.com"}
    seen = []
    monkeypatch.setattr(inst.socket, "getaddrinfo", lambda *a, **k: seen.append(a) or [(2, 1, 6, "", ("10.1.1.1", 443))])
    with pytest.raises(ValueError):
        inst._public_only("example.com")
    assert seen and seen[0][0] == "example.com"


def test_unknown_subcommand_and_help():
    rc, _, _ = cli("frobnicate")
    assert rc == 2
    rc, out, _ = cli("--help")
    assert rc == 0 and all(w in out for w in ("evolve", "status", "export", "import"))


def test_no_claude_quota_path():
    for rel in ("lib/ollama.py", "observe-log.py", "tools/instincts.py"):
        src = (_HOOKS / rel).read_text(encoding="utf-8")
        for bad in ("subprocess", "claude -p", "ANTHROPIC_API_KEY"):
            assert bad not in src, (rel, bad)
        assert "anthropic" not in src.lower(), rel
    src = (_HOOKS / "tools" / "instincts.py").read_text(encoding="utf-8")
    for bad in ("fcntl", "SIGALRM", "/proc", "systemctl"):
        assert bad not in src, bad


def test_digest_failure_pair_carries_the_error():
    rows = [{"ts": 1.0, "sid": "s", "tool": "Bash", "summary": "pytest -q", "ok": False, "files": [], "error": "Exit code 1"},
            {"ts": 2.0, "sid": "s", "tool": "Edit", "summary": "a.py (old 1, new 2)", "ok": True, "files": ["a.py"]},
            {"ts": 3.0, "sid": "s", "tool": "Bash", "summary": "pytest -q", "ok": True, "files": []},
            {"ts": 4.0, "sid": "s", "tool": "Bash", "summary": "make", "ok": False, "files": []},
            {"ts": 5.0, "sid": "s", "tool": "Bash", "summary": "make", "ok": True, "files": []}]
    text = inst.digest(rows, [], dict(inst.DEFAULTS), NOW)
    assert "Bash `pytest -q` failed (Exit code 1), then Edit a.py" in text
    assert "Bash `make` failed, then retry, then ok" in text


def test_windows_flag_changes_nothing(box, monkeypatch):
    monkeypatch.setattr(inst.plat, "IS_WINDOWS", True)
    seed_surface(box)
    fake_ollama(monkeypatch, alive=False)
    assert len(inst.lines(str(box["repo"]))) == 3
    rc, out, _ = cli("status", "--json", "--cwd", str(box["repo"]))
    assert rc == 0 and json.loads(out)["alive"] is False
