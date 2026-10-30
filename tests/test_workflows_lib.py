"""Generated saved-workflow library (MERGE-PLAN R3.2): templates -> scripts, tier literals, stub runs."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC, FIX = ROOT / "workflows" / "src", ROOT / "tests" / "fixtures" / "workflows"


def _wf_dir() -> Path:
    """The machine's render (workflows/*.js is per machine and untracked, I10); a fresh clone that has not
    rendered yet gets a max20 render in a temp dir for the static and stub tests."""
    live = ROOT / "workflows"
    if (live / "index.json").is_file() and (live / ".rendered.json").is_file():
        return live
    import atexit
    import shutil
    import tempfile
    out = Path(tempfile.mkdtemp(prefix="wf-render-")) / "workflows"
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_workflows.py"), "--tier", "max20", "--usage", "off",
                    "--out", str(out), "--quiet"], check=True, capture_output=True, text=True, timeout=120)
    atexit.register(shutil.rmtree, out.parent, True)
    return out


WF = _wf_dir()
sys.path.insert(0, str(ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "plan-tier"))
from lib import model_mode as mm  # noqa: E402
from lib import platform as plat  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load("build_workflows", ROOT / "scripts" / "build_workflows.py")
POLICY = json.loads((ROOT / "hooks" / "model-policy.json").read_text(encoding="utf-8"))
NAMES = {"invoke", "invoke-fullstack", "review", "audit", "research", "migrate", "build"}
FORBIDDEN = re.compile(r"Date\.now|Math\.random|new Date\(\s*\)|\bimport\(")
OPTS = re.compile(r"\{[^{}]*agentType:\s*'([\w-]+)',\s*model:\s*'(\w+)'[^{}]*\}")
LABEL = re.compile(r"label:\s*'([^']*)'")
UP = re.compile(r"up\(\{[^}]*agentType:\s*'([\w-]+)',\s*model:\s*'(\w+)'[^}]*\},\s*'(\w+)'\)")
META_PHASE = re.compile(r"\{\s*title:\s*'([^']+)'(?:\s*,\s*model:\s*'(\w+)')?\s*\}")
NODE = plat.node_exe()
needs_node = pytest.mark.skipif(NODE is None, reason="node not on PATH")
CANON = ["audit", "spec", "plan", "debug", "test", "impl", "refactor", "design", "clean",
         "security", "review", "docs", "verify"]


def scripts() -> list[Path]:
    return sorted(WF.glob("*.js"))


def rendered() -> dict:
    return json.loads((WF / ".rendered.json").read_text(encoding="utf-8"))


def scenario(name: str) -> dict:
    return json.loads((FIX / "scenarios" / f"{name}.json").read_text(encoding="utf-8"))


def run_stub(script: Path, sc: dict, tmp_path: Path) -> dict:
    f = tmp_path / "scenario.json"
    f.write_text(json.dumps(sc), encoding="utf-8")
    cp = subprocess.run([NODE, str(FIX / "stub.mjs"), str(script), str(f)], capture_output=True, text=True,
                        encoding="utf-8", timeout=60, **plat.no_window_kwargs())
    assert cp.returncode == 0, cp.stderr
    out = json.loads(cp.stdout.strip().splitlines()[-1])
    assert out["error"] is None, out["error"]
    return out


def build(tmp_path: Path, tier: str, usage: bool = False, *extra: str) -> Path:
    out = tmp_path / f"wf-{tier}{'-ug' if usage else ''}"
    cp = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_workflows.py"), "--tier", tier,
                         "--usage", "on" if usage else "off", "--out", str(out), *extra],
                        capture_output=True, text=True, encoding="utf-8")
    assert cp.returncode == 0, cp.stdout + cp.stderr
    return out


def builder(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "build_workflows.py"), *argv],
                          capture_output=True, text=True, encoding="utf-8")


def meta_block(text: str) -> str:
    start = text.index("export const meta = {")
    end = B.meta_end(text)
    return text[start:end]


def labels(out: dict) -> list:
    return [c["label"] for c in out["calls"]]


def tier_now() -> tuple[str, bool]:
    rec = rendered()
    return rec["tier"], bool(rec["usage_guard"])


# ---------- static: every rendered script ----------

@needs_node
def test_every_script_parses():
    assert {f.stem for f in scripts()} >= NAMES
    for f in scripts():
        cp = subprocess.run([NODE, "--check", str(f)], capture_output=True, text=True, **plat.no_window_kwargs())
        assert cp.returncode == 0, f"{f.name}: {cp.stderr}"


def test_no_clock_random_or_import():
    for f in scripts():
        assert not FORBIDDEN.search(f.read_text(encoding="utf-8")), f.name


def test_meta_literal_and_phases():
    for f in scripts():
        text = f.read_text(encoding="utf-8")
        first = next(ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("//"))
        assert re.match(r"^export const meta = \{", first), f.name
        mb = meta_block(text)
        assert f"name: '{f.stem}'" in mb, f.name
        assert "description:" in mb and "whenToUse:" in mb, f.name
        phases = META_PHASE.findall(mb)
        assert phases, f.name
        for title, model in phases:
            assert model in POLICY["model_order"], f"{f.name}: phase {title} has model {model!r}"


def test_index_json_shape():
    idx = json.loads((WF / "index.json").read_text(encoding="utf-8"))
    by = {e["name"]: e for e in idx}
    assert set(by) >= NAMES
    for name, e in by.items():
        for k in ("name", "file", "triggers", "acts", "min_size", "phases", "args_schema"):
            assert k in e, f"{name} lacks {k}"
        assert e["file"] == f"{name}.js" and (WF / e["file"]).is_file()
        assert e["min_size"] in {"S", "M", "L"}
        text = (WF / e["file"]).read_text(encoding="utf-8")
        want = [{"title": t, **({"model": m} if m else {})} for t, m in META_PHASE.findall(meta_block(text))]
        assert e["phases"] == want, name
        assert isinstance(e["args_schema"], dict) and e["args_schema"]["type"] == "object"
    assert by["invoke"]["acts"] == CANON
    assert by["invoke-fullstack"]["triggers"] == []
    assert by["migrate"]["min_size"] == "L"


# ---------- tier literals ----------

def test_call_sites_match_tier():
    tier, usage = tier_now()
    seen = 0
    for f in scripts():
        text = f.read_text(encoding="utf-8")
        for mo in OPTS.finditer(text):
            seen += 1
            agent, model = mo.group(1), mo.group(2)
            assert "${" not in mo.group(0), f"{f.name}: template literal inside opts: {mo.group(0)[:80]}"
            lab = LABEL.search(mo.group(0))
            label = lab.group(1) if lab else None
            role = mm.role_of(POLICY, agent, label)
            if agent == "general-purpose":
                assert label and label.startswith("explore:"), f"{f.name}: general-purpose label {label!r}"
                assert role == "explore", f"{f.name}: {label} -> {role}"
            assert model == B.resolve(POLICY, tier, usage, role), f"{f.name}: {agent} ({role}) on {model}"
        for agent, _base, upm in UP.findall(text):
            role = mm.role_of(POLICY, agent)
            assert role in {"impl", "integrate", "security", "test"}, f"{f.name}: up() on {agent} ({role})"
            assert upm == B.resolve(POLICY, tier, usage, role, up=True), f"{f.name}: up({agent}) -> {upm}"
        # every agentType literal sits in an opts object the regexes can read (no nested braces)
        assert len(OPTS.findall(text)) == text.count("agentType:"), f.name
    assert seen >= 40


def test_check_is_noop_on_fresh_build_and_detects_edit(tmp_path):
    out = build(tmp_path, "max20")
    assert builder("--check", "--out", str(out)).returncode == 0
    rec1 = (out / ".rendered.json").read_bytes()
    build(tmp_path, "max20")
    assert (out / ".rendered.json").read_bytes() == rec1
    with open(out / "review.js", "a", encoding="utf-8", newline="\n") as fh:
        fh.write("//x\n")
    cp = builder("--check", "--out", str(out))
    assert cp.returncode == 1 and "DRIFT review.js" in cp.stdout


def test_check_reports_missing_and_extra(tmp_path):
    out = build(tmp_path, "max5")
    (out / "audit.js").unlink()
    (out / "stray.js").write_text("//\n", encoding="utf-8")
    cp = builder("--check", "--out", str(out))
    assert cp.returncode == 1 and "MISSING audit.js" in cp.stdout and "EXTRA stray.js" in cp.stdout
    cp = builder("--check", "--out", str(tmp_path / "nowhere"))
    assert cp.returncode == 1 and "NOT-RENDERED" in cp.stdout


def test_pro_render_has_no_opus_or_fable(tmp_path):
    out = build(tmp_path, "pro")
    for f in out.glob("*.js"):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"model: '(opus|fable)'", text), f.name
        assert not any(m in ("opus", "fable") for _a, _b, m in UP.findall(text)), f.name
    out = build(tmp_path, "pro", True)
    for f in out.glob("*.js"):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"'(sonnet|opus|fable)'", text), f.name


def test_rendered_record_is_deterministic(tmp_path):
    out = build(tmp_path, "max5")
    a = (out / ".rendered.json").read_bytes()
    build(tmp_path, "max5")
    assert (out / ".rendered.json").read_bytes() == a
    rec = json.loads(a)
    assert rec["tier"] == "max5" and rec["usage_guard"] is False and rec["policy_sha"] == B.policy_sha(
        (ROOT / "hooks" / "model-policy.json").read_bytes())
    assert "ts" not in rec and re.fullmatch(r"[0-9a-f]{64}", rec["content_sha"])
    # usage on changes bytes and the record; usage off again reproduces the FIRST record byte for byte (no churn)
    cp = builder("--tier", "max5", "--usage", "on", "--out", str(out))
    assert cp.returncode == 0
    rec2 = json.loads((out / ".rendered.json").read_text(encoding="utf-8"))
    assert rec2["usage_guard"] is True and rec2["content_sha"] != rec["content_sha"]
    cp = builder("--tier", "max5", "--usage", "off", "--out", str(out))
    assert cp.returncode == 0
    assert (out / ".rendered.json").read_bytes() == a


def test_check_catches_hand_edited_record(tmp_path):
    out = build(tmp_path, "max20")
    rec = json.loads((out / ".rendered.json").read_text(encoding="utf-8"))
    rec["content_sha"] = "0" * 64
    (out / ".rendered.json").write_text(json.dumps(rec, sort_keys=True) + "\n", encoding="utf-8")
    cp = builder("--check", "--out", str(out))
    assert cp.returncode == 1 and "DRIFT .rendered.json (content_sha)" in cp.stdout


def test_machine_render_reproduces_byte_identical_outputs(tmp_path):
    """A re-render of the recorded tier/usage leaves every output untouched (no churn on self-heal)."""
    rec = rendered()
    cp = builder("--tier", rec["tier"], "--usage", "on" if rec["usage_guard"] else "off", "--out", str(tmp_path / "w"))
    assert cp.returncode == 0, cp.stdout + cp.stderr
    for p in sorted((tmp_path / "w").iterdir()):
        assert p.read_bytes() == (WF / p.name).read_bytes(), p.name


def test_api_and_max20_renders_both_check_ok(tmp_path):
    """I10: the render is per machine; every tier renders cleanly and proves itself with --check."""
    for tier in ("api", "max20"):
        out = build(tmp_path, tier)
        cp = builder("--check", "--out", str(out))
        assert cp.returncode == 0 and f"tier {tier}" in cp.stdout, cp.stdout


def test_render_outputs_are_gitignored_and_sources_are_not():
    """I10: workflows/*.js, index.json and .rendered.json are per-machine artifacts (like settings.json), so a
    tier render never dirties tracked files; the templates and docs stay tracked."""
    ignored = ["workflows/review.js", "workflows/index.json", "workflows/.rendered.json"]
    kept = ["workflows/src/review.js.tpl", "workflows/src/index.src.json", "workflows/CLAUDE.md", "workflows/README.md"]
    cp = subprocess.run(["git", "-C", str(ROOT), "check-ignore", *ignored, *kept],
                        capture_output=True, text=True, timeout=30)
    assert sorted(cp.stdout.split()) == sorted(ignored), cp.stdout + cp.stderr
    # a tracked file is never ignored: the render outputs must be out of the index too
    ls = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--", "workflows/*.js", "workflows/index.json",
                         "workflows/.rendered.json"], capture_output=True, text=True, timeout=30)
    assert ls.stdout.strip() == "", ls.stdout


def test_unknown_role_token_is_refused(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.src.json").write_text(json.dumps({"x": {"triggers": [], "acts": [], "min_size": "S",
                                                          "args_schema": {"type": "object"}}}), encoding="utf-8")
    (src / "x.js.tpl").write_text("export const meta = {\n  name: 'x',\n  description: 'd',\n  whenToUse: 'w',\n"
                                  "  phases: [{ title: 'A', model: '{{model:nope}}' }],\n}\n", encoding="utf-8")
    cp = builder("--tier", "max20", "--usage", "off", "--src", str(src), "--out", str(tmp_path / "o"))
    assert cp.returncode == 2 and "unknown role token" in cp.stderr
    assert not (tmp_path / "o").exists()


# ---------- invoke.js mirrors the router's acts table ----------

def test_invoke_acts_table_matches_router_config():
    gen = _load("gen_invoke_skills", ROOT / "hooks" / "gen-invoke-skills.py")
    cfg = json.loads((ROOT / "hooks" / "autonomous-skill-router.config.json").read_text(encoding="utf-8"))
    acts = gen.load_acts(cfg)
    row = re.compile(r"\{ act: '(\w+)', agent: '([\w-]+)', artifact: ([`'][^`']*[`']), mutates: (true|false), "
                     r"checkpoint: (true|false) \}")
    rows = row.findall((WF / "invoke.js").read_text(encoding="utf-8"))
    assert [(r[0], r[1], r[3] == "true", r[4] == "true") for r in rows] == \
        [(a["act"], a["agent"], a["mutates"], a["checkpoint"]) for a in acts]
    for r, a in zip(rows, acts):
        assert r[2][1:-1] == a["artifact"].replace("{date}", "${date}").replace("{slug}", "${slug}"), a["act"]


# ---------- stub runs (fake runtime under node vm) ----------

@needs_node
def test_stub_invoke_fullstack(tmp_path):
    tier, usage = tier_now()
    sc = scenario("invoke-fullstack")
    out = run_stub(WF / "invoke-fullstack.js", sc, tmp_path)
    assert labels(out) == ["spec", "plan", "backend", "frontend", "integrate", "santa", "security", "docs", "qa"]
    assert [c["phase"] for c in out["calls"]] == ["Spec", "Plan", "Backend", "Frontend", "Integrate",
                                                  "Close", "Close", "Close", "Verify"]
    assert all(c["model"] and c["agentType"] for c in out["calls"])
    assert out["result"]["dead"] == ["security"] and out["result"]["incomplete"] is True
    sc["args"]["tier_hint"] = "escalate"
    out = run_stub(WF / "invoke-fullstack.js", sc, tmp_path)
    by = {c["label"]: c for c in out["calls"]}
    assert by["backend"]["model"] == B.resolve(POLICY, tier, usage, "impl", up=True)
    assert by["spec"]["model"] == B.resolve(POLICY, tier, usage, "judge")


@needs_node
def test_stub_invoke_fullstack_stops_on_dead_spec_and_plan(tmp_path):
    sc = scenario("invoke-fullstack")
    out = run_stub(WF / "invoke-fullstack.js", {**sc, "replies": [{"label": "^spec$", "value": None}]}, tmp_path)
    assert labels(out) == ["spec"]
    assert out["result"]["dead"] == ["spec"] and out["result"]["incomplete"] is True
    assert any("stopping" in ln for ln in out["logs"])
    out = run_stub(WF / "invoke-fullstack.js", {**sc, "replies": [{"label": "^plan$", "value": None}]}, tmp_path)
    assert labels(out) == ["spec", "plan"] and out["result"]["dead"] == ["plan"] and out["result"]["incomplete"] is True


@needs_node
def test_stub_invoke_fullstack_dead_counts_every_phase(tmp_path):
    sc = scenario("invoke-fullstack")
    out = run_stub(WF / "invoke-fullstack.js", {**sc, "replies": [{"label": "^backend$", "value": None},
                                                                  {"label": "^security$", "value": None}]}, tmp_path)
    assert labels(out) == ["spec", "plan", "backend", "frontend", "integrate", "santa", "security", "docs", "qa"]
    assert out["result"]["dead"] == ["backend", "security"] and out["result"]["incomplete"] is True
    fe = next(c for c in out["calls"] if c["label"] == "frontend")
    assert "IMPL-REPORT-BE.md" not in fe["prompt"] and "SPEC-x.md" in fe["prompt"]
    assert any("frontend builds from the spec" in ln for ln in out["logs"])


@needs_node
def test_stub_invoke(tmp_path):
    sc = scenario("invoke")
    out = run_stub(WF / "invoke.js", sc, tmp_path)
    ls, r = labels(out), out["result"]
    assert ls[:4] == ["explore:brief", "plan", "impl", "clean"] and ls[-1] == "qa"
    assert set(ls[4:-1]) == {"workflow:review", "docs"}
    assert r["done"] == ["plan", "impl"] and "docs" in r["failed"] and r["incomplete"] is True
    assert "bogus" in " ".join(out["logs"])
    assert r["verdicts"]["review"] == "APPROVE" and r["checkpoints"][0]["act"] == "plan"
    assert r["artifacts"]["plan"].endswith("plan-2026-10-29-x.md")
    # nested workflow() unavailable -> inline santa fallback
    out = run_stub(WF / "invoke.js", {**sc, "workflow_unavailable": True}, tmp_path)
    fb = [c for c in out["calls"] if c["label"] == "review"]
    assert len(fb) == 1 and fb[0]["agentType"] == "santa-reviewer"
    # a non-mutating chain: no closers, no verify
    out = run_stub(WF / "invoke.js", {**sc, "args": {**sc["args"], "acts": ["spec"]}}, tmp_path)
    assert out["result"]["incomplete"] is False and out["result"]["closers"] == []
    assert list(dict.fromkeys(c["phase"] for c in out["calls"])) == ["Brief", "Acts"]
    # touched_security adds the security closer; mixed surface runs backend -> frontend -> integrate
    sc2 = {**sc, "default": {**sc["default"], "touched_security": True}, "replies": [],
           "args": {**sc["args"], "acts": ["plan", "impl"], "surface": "mixed"}}
    out = run_stub(WF / "invoke.js", sc2, tmp_path)
    ls = labels(out)
    assert ls[2:5] == ["backend", "frontend", "integrate"] and "security" in ls
    assert out["result"]["incomplete"] is False
    # no valid acts
    out = run_stub(WF / "invoke.js", {**sc, "args": {**sc["args"], "acts": ["nope"]}}, tmp_path)
    assert out["result"]["error"] == "no valid acts" and out["calls"] == []


@needs_node
def test_invoke_retries_a_dead_act_once(tmp_path):
    sc = scenario("invoke")
    sc = {**sc, "args": {**sc["args"], "acts": ["audit"]}, "replies": [{"label": "^audit$", "value": None}]}
    out = run_stub(WF / "invoke.js", sc, tmp_path)
    audits = [c for c in out["calls"] if c["label"] == "audit"]
    assert labels(out).count("audit") == 2 and out["result"]["failed"] == ["audit"]
    assert not audits[0]["prompt"].startswith("RETRY:") and audits[1]["prompt"].startswith("RETRY:")
    assert any("audit returned nothing" in ln and "retrying once" in ln for ln in out["logs"])
    # a live first run is never retried
    out = run_stub(WF / "invoke.js", {**sc, "replies": []}, tmp_path)
    assert labels(out).count("audit") == 1 and out["result"]["failed"] == []


@needs_node
def test_invoke_keeps_an_incomplete_review_incomplete(tmp_path):
    sc = scenario("invoke")
    sc = {**sc, "replies": [{"label": "^review:2$", "value": {"path": "p", "summary": "s", "verdict": "APPROVE"}}],
          "workflow": {"review": {"verdict": "CHANGES_REQUESTED", "incomplete": True, "blocking": [], "advisory": [], "stats": {}}}}
    out = run_stub(WF / "invoke.js", {**sc, "args": {**sc["args"], "size": "XL"}}, tmp_path)
    r = out["result"]
    assert "review:2" in labels(out)                       # the second pass still re-checks the findings
    assert r["verdicts"]["review"] == "CHANGES_REQUESTED"  # but never lifts an incomplete review's verdict
    assert r["incomplete"] is True and r["failed"] == []   # incomplete comes from the review flag alone
    assert any("review incomplete" in ln for ln in out["logs"])
    out = run_stub(WF / "invoke.js", {**sc, "args": {**sc["args"], "size": "M"}}, tmp_path)
    assert "review:2" not in labels(out)
    assert out["result"]["verdicts"]["review"] == "CHANGES_REQUESTED" and out["result"]["incomplete"] is True


@needs_node
def test_mixed_surface_retries_per_step_not_the_whole_act(tmp_path):
    sc = scenario("invoke")
    sc = {**sc, "args": {**sc["args"], "acts": ["impl"], "surface": "mixed"},
          "replies": [{"label": "^frontend$", "value": None}]}
    out = run_stub(WF / "invoke.js", sc, tmp_path)
    ls = labels(out)
    assert ls.count("backend") == 1 and ls.count("frontend") == 2 and ls.count("integrate") == 0
    fe = [c for c in out["calls"] if c["label"] == "frontend"]
    assert not fe[0]["prompt"].startswith("RETRY:") and fe[1]["prompt"].startswith("RETRY:")
    assert out["result"]["failed"] == ["impl"] and out["result"]["incomplete"] is True
    assert any("frontend returned nothing" in ln and "retrying once" in ln for ln in out["logs"])
    # the single-agent surfaces keep their one retry
    out = run_stub(WF / "invoke.js", {**sc, "args": {**sc["args"], "surface": "backend"},
                                      "replies": [{"label": "^impl$", "value": None}]}, tmp_path)
    assert labels(out).count("impl") == 2


@needs_node
def test_stub_review_refute_by_default(tmp_path):
    sc = scenario("review")
    out = run_stub(WF / "review.js", sc, tmp_path)
    r = out["result"]
    assert r["incomplete"] is True and r["verdict"] == "CHANGES_REQUESTED"
    assert len(r["blocking"]) == 1 and "could not confidently refute" in r["blocking"][0]["note"]
    assert r["stats"]["raw"] == 3 and r["stats"]["unique"] == 2
    assert any(f["severity"] == "MEDIUM" for f in r["advisory"])
    dims = [c["label"] for c in out["calls"] if c["label"].startswith("review:")]
    assert dims == ["review:breaker:1", "review:simplifier:1", "review:lang:typescript:1", "review:security:1",
                    "review:security:1a", "review:security:1b"]  # 3 paths = one chunk; the dead security job halves once
    sec = next(f for f in r["failedDimensions"] if f["dimension"] == "security:1")
    assert sec["paths"] == ["src/auth/login.ts", "src/a.ts", "src/b.ts"]
    ver = [c for c in out["calls"] if c["label"].startswith("verify:")]
    assert len(ver) == 1 and ver[0]["agentType"] == "santa-reviewer"
    assert r["report"]["json_path"].endswith("SANTA-REVIEW.json") and r["report_written"] is True
    # confident refutation + healthy security dimension -> APPROVE
    replies = [x for x in sc["replies"] if x["label"] not in ("^review:security:1", "^verify:src/a.ts")]
    replies.append({"label": "^verify:src/a.ts", "value": {"isReal": False, "confidence": 0.9, "evidence": "guarded"}})
    out = run_stub(WF / "review.js", {**sc, "replies": replies}, tmp_path)
    r = out["result"]
    assert r["verdict"] == "APPROVE" and r["blocking"] == []
    assert any(f.get("note") and "refuted" in f["note"] for f in r["advisory"])
    # nothing named: breaker + simplifier over this session's diff, no report without run
    out = run_stub(WF / "review.js", {"args": {}, "default": {"verdict": "APPROVE", "findings": []}}, tmp_path)
    dims = [c["label"] for c in out["calls"]]
    assert dims == ["review:breaker:1", "review:simplifier:1"]
    assert "this session's diff" in out["calls"][0]["promptHead"]
    assert out["result"]["verdict"] == "APPROVE" and out["result"]["report"] is None


@needs_node
def test_stub_review_same_dimension_neighbours_are_not_merged(tmp_path):
    """Two HIGHs from one dimension at lines 10 and 12: refuting the first must not clear the second."""
    sc = scenario("review")
    replies = [x for x in sc["replies"] if x["label"] not in ("^review:breaker:1$", "^review:lang:typescript:1$",
                                                              "^verify:src/a.ts")]
    replies += [
        {"label": "^review:breaker:1$", "value": {"verdict": "CHANGES_REQUESTED", "findings": [
            {"title": "off by one", "severity": "HIGH", "file": "src/a.ts", "line": 10, "evidence": "i <= n",
             "proof": "reads past the end"},
            {"title": "null deref of user.id", "severity": "HIGH", "file": "src/a.ts", "line": 12,
             "evidence": "user.id without a guard", "proof": "user is null on the anonymous path"}]}},
        {"label": "^verify:src/a.ts:10$", "value": {"isReal": False, "confidence": 0.9, "evidence": "n is exclusive here"}},
        {"label": "^verify:src/a.ts:12$", "value": {"isReal": True, "confidence": 0.9, "evidence": "confirmed"}},
    ]
    out = run_stub(WF / "review.js", {**sc, "replies": replies}, tmp_path)
    r = out["result"]
    assert r["stats"]["raw"] == 2 and r["stats"]["unique"] == 2            # not merged
    assert sorted(c["label"] for c in out["calls"] if c["label"].startswith("verify:")) == \
        ["verify:src/a.ts:10", "verify:src/a.ts:12"]
    assert r["verdict"] == "CHANGES_REQUESTED" and [b["line"] for b in r["blocking"]] == [12]
    assert any("off by one" in (f.get("title") or "") for f in r["advisory"])   # the refuted one moved to advisory


@needs_node
def test_stub_review_cross_dimension_neighbours_still_merge_and_keep_members(tmp_path):
    sc = scenario("review")           # breaker a.ts:10 (HIGH) + lang a.ts:11 (HIGH)
    out = run_stub(WF / "review.js", sc, tmp_path)
    r = out["result"]
    assert r["stats"]["raw"] == 3 and r["stats"]["unique"] == 2
    merged = next(b for b in r["blocking"] if b["file"] == "src/a.ts")
    assert sorted(merged["dimensions"]) == ["breaker", "lang:typescript"]
    assert [m["line"] for m in merged["members"]] == [10, 11]
    assert {m["title"] for m in merged["members"]} == {"off by one", "index overflow"}
    ver = next(c for c in out["calls"] if c["label"].startswith("verify:"))
    assert "EVERY claim" in ver["prompt"] and "index overflow" in ver["prompt"] and "arr[n] is undefined" in ver["prompt"]


@needs_node
def test_review_chunks_paths_and_fails_closed_on_uncovered(tmp_path):
    sc = scenario("review")  # nine paths -> 2 chunks of <= 6 per dimension (no security trigger in p*.py)
    sc["args"] = {**sc["args"], "paths": [f"p{i}.py" for i in range(1, 10)]}
    sc["replies"] = [
        {"label": "^review:breaker:2$", "value": None},
        {"label": "^review:breaker:2a$", "value": None},
        {"label": "^review:breaker:2b$", "value": {"verdict": "APPROVE", "findings": []}},
        {"label": "^review:simplifier:1$", "value": {"verdict": "APPROVE", "findings": [], "incomplete": True,
                                                    "uncovered": ["p3.py"]}},
    ] + sc["replies"]
    out = run_stub(WF / "review.js", sc, tmp_path)
    labs = labels(out)
    assert {"review:breaker:1", "review:breaker:2", "review:breaker:2a", "review:breaker:2b",
            "review:simplifier:1", "review:simplifier:2"} <= set(labs)
    assert "review:simplifier:1a" not in labs  # an incomplete (non-null) reviewer is not retried
    failed = {f["dimension"]: f for f in out["result"]["failedDimensions"]}
    assert failed["breaker:2"]["paths"] == ["p7.py", "p8.py"] and "retry" in failed["breaker:2"]["error"]
    assert failed["simplifier:1"]["paths"] == ["p3.py"] and failed["simplifier:1"]["error"] == "reviewer reported incomplete"
    assert out["result"]["incomplete"] is True and out["result"]["verdict"] == "CHANGES_REQUESTED"
    assert out["result"]["stats"]["jobs"] == 2 * len({lb.split(":")[1] for lb in labs if lb.startswith("review:")})
    retry = next(c for c in out["calls"] if c["label"] == "review:breaker:2a")
    assert retry["prompt"].startswith("RETRY:") and "p7.py, p8.py" in retry["prompt"] and "p9.py" not in retry["prompt"]
    assert any("2 chunk(s)" in ln for ln in out["logs"])


@needs_node
def test_stub_audit(tmp_path):
    out = run_stub(WF / "audit.js", scenario("audit"), tmp_path)
    r = out["result"]
    assert labels(out) == ["explore:slice:hooks", "explore:slice:scripts", "explore:slice:installer-ui", "map"]
    assert [c["phase"] for c in out["calls"]] == ["Slices", "Slices", "Slices", "Map"]
    assert r["dead"] == ["scripts"] and r["incomplete"] is True and r["map"] == "p"
    assert [s["surface"] for s in r["slices"]] == ["hooks", "Installer UI"]
    out = run_stub(WF / "audit.js", {"args": {"run": "/tmp/r/x", "corpus": ["a/", "b/"]}}, tmp_path)
    assert labels(out) == ["explore:slice:a", "explore:slice:b", "map"]


@needs_node
def test_stub_research(tmp_path):
    out = run_stub(WF / "research.js", scenario("research"), tmp_path)
    r = out["result"]
    assert labels(out) == ["explore:source:1", "explore:source:2", "synthesis"]
    assert r["dead"] == [] and r["incomplete"] is False and len(r["slices"]) == 2
    out = run_stub(WF / "research.js", {"args": {"run": "/tmp/r/x"}}, tmp_path)
    assert out["result"]["error"] == "no sources" and out["calls"] == []
    out = run_stub(WF / "research.js", {"args": {"run": "/tmp/r/x", "task": "q", "corpus": ["a.md"]}}, tmp_path)
    assert labels(out) == ["explore:source:1", "synthesis"]


@needs_node
def test_stub_migrate(tmp_path):
    sc = scenario("migrate")
    out = run_stub(WF / "migrate.js", sc, tmp_path)
    r = out["result"]
    assert list(dict.fromkeys(c["phase"] for c in out["calls"])) == ["Inventory", "Dispositions", "Packages", "Critic", "Revision"]
    assert r["revised"] is True and r["critic"] == 1 and r["incomplete"] is False
    rev = [c for c in out["calls"] if c["label"] == "revision"]
    assert len(rev) == 1 and rev[0]["agentType"] == "planning-director"
    low = {**sc, "replies": [{"label": "^critic$", "value": {"issues": [{"id": "c1", "severity": "low", "text": "nit"}]}}]}
    out = run_stub(WF / "migrate.js", low, tmp_path)
    assert out["result"]["revised"] is False and "revision" not in labels(out)
    dead = {**sc, "replies": [{"label": "^packages$", "value": None}]}
    out = run_stub(WF / "migrate.js", dead, tmp_path)
    assert out["result"]["incomplete"] is True and "critic" not in labels(out)


@needs_node
def test_stub_build(tmp_path):
    sc = scenario("build")  # happy path: drop the dead-reviewer replies (test_build_reviews_per_chunk_and_retries_once)
    sc["replies"] = [x for x in sc["replies"] if not x["label"].startswith(("^santa:pkg-a", "^santa:pkg-c"))]
    out = run_stub(WF / "build.js", sc, tmp_path)
    ls, r = labels(out), out["result"]
    assert ls[0] == "explore:packages"
    assert any(ln == "packages listed: pkg-a:1 pkg-b:2 pkg-c:8" for ln in out["logs"])
    assert ls.index("spec:pkg-b") < ls.index("spec:pkg-a") and ls.index("spec:pkg-c") < ls.index("spec:pkg-a")
    assert ls.count("diagnose:pkg-a:1") == 1 and ls.count("fix:pkg-a:1") == 1 and "diagnose:pkg-a:2" not in ls
    assert "triage" in ls and "review-fix:pkg-b" in ls and "final-verify" in ls
    assert len(r["packages"]) == 3 and all(p["status"] == "pass" for p in r["packages"])
    assert r["review_findings"] == 1 and r["incomplete"] is False
    # max_parallel 1 -> one package per wave; listing failure ends the run
    sc = scenario("build")
    sc["args"]["max_parallel"] = 1
    out = run_stub(WF / "build.js", sc, tmp_path)
    assert sum(1 for x in out["logs"] if x.startswith("wave ")) == 3
    sc["replies"] = [{"label": "^explore:packages$", "value": None}]
    out = run_stub(WF / "build.js", sc, tmp_path)
    assert out["result"]["incomplete"] is True and labels(out) == ["explore:packages"]


@needs_node
def test_build_reviews_per_chunk_and_retries_once(tmp_path):
    out = run_stub(WF / "build.js", scenario("build"), tmp_path)
    labs = labels(out)
    assert labs.count("santa:pkg-c:1") == 1 and labs.count("santa:pkg-c:2") == 1          # 8 paths -> 2 chunks
    assert "santa:pkg-c:1a" in labs and "santa:pkg-c:1b" in labs                          # one halving retry
    assert "santa:pkg-a:1:retry" in labs and "santa:pkg-a:1:retry:retry" not in labs       # single path: same scope, once
    assert "verify:pkg-b:retry" in labs
    assert next(p for p in out["result"]["packages"] if p["id"] == "pkg-b")["status"] == "pass"
    unc = {u["pkg"]: u["paths"] for u in out["result"]["review_uncovered"]}
    assert unc == {"pkg-c": ["c1.py", "c2.py", "c3.py", "c6.py"]}                          # half a (null) + self-reported c6
    assert "review:pkg-c" in out["result"]["dead"] and out["result"]["incomplete"] is True
    assert any("retrying once as two halves" in ln for ln in out["logs"])
    assert any("left uncovered" in ln for ln in out["logs"])
    santa = [c for c in out["calls"] if c["agentType"] == "santa-reviewer"]
    assert all(c["schema"] for c in santa) and all("ONLY these owned paths" in c["prompt"] for c in santa)
    assert next(c for c in santa if c["label"] == "santa:pkg-c:1a")["prompt"].startswith("RETRY:")


@needs_node
def test_parallel_reviewers_get_unique_notes_files(tmp_path):
    out = run_stub(WF / "build.js", scenario("build"), tmp_path)
    santa = [c for c in out["calls"] if c["agentType"] == "santa-reviewer"]
    notes = [re.search(r"notes/santa-[A-Za-z0-9._-]+\.md", c["prompt"]).group(0) for c in santa]
    assert len(set(notes)) == len(notes) and all(":" not in n for n in notes)
    assert all("never write SANTA-REVIEW.md" in c["prompt"] for c in santa)
    retry = next(c for c in santa if c["label"] == "santa:pkg-c:1a")
    assert retry["prompt"].startswith("RETRY:") and "notes/santa-pkg-c-1a.md" in retry["prompt"]
    # final-verify runs alone and names its own FINAL-VERIFY.md: only the per-package verifiers get notes files
    ver = [c for c in out["calls"] if c["agentType"] == "qa-verifier" and not c["label"].startswith("final-verify")]
    assert all("Do not edit any file under the worktree" in c["prompt"] and "notes/verify-" in c["prompt"] for c in ver)
    assert "notes/verify-pkg-a.md" in next(c for c in ver if c["label"] == "verify:pkg-a")["prompt"]
    # review.js: one notes file per dimension x chunk, and per adversarial verifier
    sc = scenario("review")
    sc["args"] = {**sc["args"], "paths": [f"p{i}.py" for i in range(1, 10)]}
    out = run_stub(WF / "review.js", sc, tmp_path)
    rev = [c for c in out["calls"] if c["label"].startswith("review:")]
    notes = [re.search(r"notes/review-[A-Za-z0-9._-]+\.md", c["prompt"]).group(0) for c in rev]
    assert len(set(notes)) == len(notes) and "notes/review-breaker-1.md" in notes
    vers = [c for c in out["calls"] if c["label"].startswith("verify:")]
    assert vers and all("notes/verify-" in c["prompt"] for c in vers)
    # no run folder -> notes stay in the reply
    out = run_stub(WF / "review.js", {**sc, "args": {k: v for k, v in sc["args"].items() if k != "run"}}, tmp_path)
    assert all("Keep notes in your reply, not in a file." in c["prompt"]
               for c in out["calls"] if c["label"].startswith("review:"))


@needs_node
def test_build_bounds_the_review_fan_out_per_package(tmp_path):
    sc = scenario("build")
    sc["replies"] = [{"label": "^explore:packages$", "value": {"packages": [
        {"id": "big", "title": "B", "risk": "low", "depends_on": [], "owned_paths": [f"f{i}.py" for i in range(150)]},
        {"id": "small", "title": "S", "risk": "low", "depends_on": [], "owned_paths": ["a.py", "b.py"]}]}}]
    out = run_stub(WF / "build.js", sc, tmp_path)
    labs = labels(out)
    assert labs.count("santa:big:8") == 1 and "santa:big:9" not in labs          # 150 paths -> 8 chunks of <= 19, not 25 of 6
    assert labs.count("santa:small:1") == 1 and "santa:small:2" not in labs
    big = next(c for c in out["calls"] if c["label"] == "santa:big:1")
    assert big["prompt"].count(".py") == 19
    assert any(ln == "packages listed: big:150 small:2" for ln in out["logs"])
    assert any(ln == "review fan-out: 9 santa reviewers across 2 packages (max 8 per package)" for ln in out["logs"])
    assert out["result"]["review_uncovered"] == [] and out["result"]["incomplete"] is False
