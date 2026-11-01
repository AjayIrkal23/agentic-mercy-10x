"""scripts/router_replay.py on a synthetic transcript tree (never the real projects/):
JSON report shape, skip/dedupe rules, and the --check exit codes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "router_replay.py"


def _turn(text, cwd, **extra):
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {"type": "user", "timestamp": ts, "cwd": cwd, "message": {"role": "user", "content": text}, **extra}


def _tree(tmp: Path) -> Path:
    claude = tmp / "claude"
    proj = claude / "projects" / "-tmp-x"
    proj.mkdir(parents=True)
    cwd = str(tmp)
    rows = [
        _turn("fix the login bug in src/auth.py, it throws a TypeError", cwd),
        _turn("fix the login bug in src/auth.py, it throws a TypeError", cwd),        # duplicate
        _turn("ignored skill body", cwd, isMeta=True),                                  # meta
        {"type": "user", "timestamp": _turn("x", cwd)["timestamp"], "cwd": cwd,
         "message": {"content": [{"type": "tool_result", "content": "ok"}]}},         # tool result
        _turn("use opus for this project", cwd),                                        # mode phrase
        _turn("write a plan for the payment refactor", cwd),
    ]
    (proj / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return claude


def _run(tmp: Path, *args, budget: dict | None = None) -> subprocess.CompletedProcess:
    b = tmp / "budget.json"
    b.write_text(json.dumps(budget or {"window_days": 14, "max": {"union": 1.0}}), encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(tmp / "claude"), "--budget", str(b),
                           "--out-dir", str(tmp / "out"), *args],
                          capture_output=True, text=True, timeout=120, check=False)


def test_report_shape_and_skips(tmp_path):
    _tree(tmp_path)
    cp = _run(tmp_path, "--check")
    assert cp.returncode == 0, cp.stdout + cp.stderr
    rep = json.loads(next((tmp_path / "out").glob("*.json")).read_text(encoding="utf-8"))
    assert set(rep) >= {"date", "window_days", "counts", "rates", "max", "top_flagged"}
    c = rep["counts"]
    assert c["prompts"] == 3 and c["skipped_mode"] == 1          # dup, meta, tool_result dropped
    assert set(rep["rates"]) >= {"union", "threejs_no_3d", "debug_no_bug", "machine_routed", "egm_on_small",
                                 "zero_skill_dev", "audit_no_audit_skill", "stack_skill_missed",
                                 "infra_got_fe_skill", "zero_skill_prompts"}
    assert "fix the login bug" not in json.dumps(rep)               # counts only, no prompt text
    assert "router-replay --check: OK" in cp.stdout


def test_check_fails_when_a_rate_is_over_budget(tmp_path):
    _tree(tmp_path)
    # a negative max is exceeded by any rate, so the over-budget path runs deterministically
    cp = _run(tmp_path, "--check", budget={"window_days": 14, "max": {"union": -1}})
    assert cp.returncode == 1 and "OVER BUDGET: union" in cp.stdout


def test_no_transcripts_is_a_skip(tmp_path):
    (tmp_path / "claude" / "projects").mkdir(parents=True)
    cp = _run(tmp_path, "--check")
    assert cp.returncode == 0 and "SKIP(no transcripts)" in cp.stdout


def test_replay_leaves_no_temp_dirs(tmp_path):
    """FIX2 item 6: the per-prompt box was removed before flags_for() classified the prompt, and the
    surface cache (state/<repo>.stack.json) re-created it: one leaked router-replay-* dir per routed prompt."""
    _tree(tmp_path)
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "18"}}', encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=False, capture_output=True)
    box = tmp_path / "t"
    box.mkdir()
    b = tmp_path / "budget.json"
    b.write_text(json.dumps({"window_days": 14, "max": {"union": 1.0}}), encoding="utf-8")
    env = {**os.environ, "TMPDIR": str(box), "TEMP": str(box), "TMP": str(box)}
    cp = subprocess.run([sys.executable, str(SCRIPT), "--root", str(tmp_path / "claude"), "--budget", str(b),
                         "--out-dir", str(tmp_path / "out")], capture_output=True, text=True, timeout=120, env=env)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "routed 0/" not in cp.stdout, cp.stdout   # something routed, so the classify path ran
    assert sorted(p.name for p in box.iterdir()) == []
