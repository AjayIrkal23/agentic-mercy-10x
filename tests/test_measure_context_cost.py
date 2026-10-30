"""scripts/measure_context_cost.py: the measured always-on context cost (docs/TOKEN-BUDGET.md)."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = _ROOT / "scripts" / "measure_context_cost.py"
ROWS = ["CLAUDE.md", "CLAUDE.machines.local.md (imported part)", "rules/0*.md (no paths: frontmatter)", "MEMORY.md",
        "skill listing (local + plugins)", "agent descriptions", "session-start aggregator sample",
        "subagent-context sample", "plan-tier notice line", "instinct lines"]
HEADINGS = ["## Fixed per session", "## Per event", "## Observed", "## Eager MCP schemas", "## How to re-measure",
            "## Weekly manual inputs", "## Token advice carried over from ECC"]


def _mod():
    spec = importlib.util.spec_from_file_location("measure_context_cost", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


mc = _mod()


def _run(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(_ROOT), *args], capture_output=True,
                          encoding="utf-8", timeout=120, env={**os.environ, **(env or {})})


def test_first_line_is_doctrine_total():
    r = _run("--drafts", "docs/merge")
    assert r.returncode == 0, r.stderr
    assert re.match(r"^doctrine total: [\d,]+ chars", r.stdout.splitlines()[0])
    m = re.search(r"doctrine\D*(\d[\d,]*)", r.stdout)
    assert m and int(m.group(1).replace(",", "")) <= 20000, r.stdout


def test_rows_present():
    out = _run("--drafts", "docs/merge").stdout
    for name in ROWS:
        assert f"| {name} |" in out, name
    assert "| eager MCP schemas |" not in out
    assert "| eager MCP schemas |" in _run("--drafts", "docs/merge", "--mcp-eager").stdout


def _il(sid: str, chars: int, source: str) -> str:
    return json.dumps({"ts": "x", "sid": sid, "path": "~/x.md", "chars": chars, "source": source,
                       "load_reason": "session_start"})


def test_observed_fixture(tmp_path):
    (tmp_path / "2026-10-29.instructions-loaded.jsonl").write_text(
        "\n".join([_il("a", 1000, "user"), _il("a", 2000, "rules"), _il("b", 4000, "user"),
                   _il("doctor-x", 99999, "user")]) + "\n", encoding="utf-8")
    text = mc.observed_text(tmp_path)
    assert "median 3,500 chars over 2 sessions" in text
    empty = tmp_path / "empty"
    empty.mkdir()
    assert "no telemetry yet" in mc.observed_text(empty)
    r = _run("--observed", env={"CLAUDE_HOOK_TELEMETRY_DIR": str(tmp_path)})
    assert "median 3,500" in r.stdout


def test_counts_table():
    out = _run("--counts").stdout
    rows = [ln for ln in out.splitlines() if ln.startswith("| ") and not ln.startswith("| Thing")
            and not ln.startswith("| Row") and not ln.startswith("|---")]
    counts = {ln.split("|")[1].strip(): ln.split("|")[2].strip() for ln in rows}
    things = ["Local skills", "Plugin skills", "Agents", "Hook events wired", "Dispatch links enabled",
              "MCP servers", "Plugins", "Vendored skill sources", "Test files"]
    for t in things:
        assert counts.get(t, "").isdigit(), (t, counts.get(t))
    assert int(counts["Local skills"]) == len(list((_ROOT / "skills").glob("*/SKILL.md")))


def test_overrides_change_listing(tmp_path):
    for name in ("a", "b"):
        d = tmp_path / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: skill {name} description\n---\nbody\n",
                                    encoding="utf-8")
    ov = tmp_path / "ov.json"
    ov.write_text(json.dumps({"skillOverrides": {"a": "name-only", "b": "user-invocable-only"}}), encoding="utf-8")
    assert mc.listing_chars(tmp_path, mc.load_overrides(tmp_path, str(ov)))[0] == len("a") + 4
    assert mc.listing_chars(tmp_path, {})[0] == sum(len(n) + len(f"skill {n} description") + 4 for n in "ab")


def test_write_document(tmp_path):
    tb = tmp_path / "TB.md"
    r = _run("--write", str(tb))
    assert r.returncode == 0, r.stderr
    text = tb.read_text(encoding="utf-8")
    for h in HEADINGS:
        assert text.count(h + "\n") == 1, h
    _run("--write", str(tb), "--record", "1234")
    text = tb.read_text(encoding="utf-8")
    assert text.count("<!-- mcp-eager-observed: 1234 -->") == 1
    _run("--write", str(tb), "--record", "1234")
    again = tb.read_text(encoding="utf-8")
    assert again.count("<!-- mcp-eager-observed:") == 1 and all(again.count(h + "\n") == 1 for h in HEADINGS)
    # a later --write without --record keeps the recorded figure
    _run("--write", str(tb))
    assert "<!-- mcp-eager-observed: 1234 -->" in tb.read_text(encoding="utf-8")


def test_json():
    r = _run("--drafts", "docs/merge", "--json")
    data = json.loads(r.stdout)
    first = _run("--drafts", "docs/merge").stdout.splitlines()[0]
    assert data["doctrine_total"] == int(re.search(r"([\d,]+) chars", first).group(1).replace(",", ""))


def test_no_network_no_writes():
    owned = [_ROOT / "docs" / "TOKEN-BUDGET.md", *sorted((_ROOT / "docs" / "merge").rglob("*"))]

    def snap():
        return {str(p): p.stat().st_mtime_ns for p in owned if p.exists()}

    before = snap()
    _run("--drafts", "docs/merge", "--counts", "--observed", "--mcp-eager")
    assert snap() == before
