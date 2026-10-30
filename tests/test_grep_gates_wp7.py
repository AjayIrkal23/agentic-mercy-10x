"""G6: no machine home literals in tracked Markdown (audit 2026-10-05 J-05, WP7)."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _gate():
    spec = importlib.util.spec_from_file_location("grep_gates_wp7", _ROOT / "scripts" / "grep_gates.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_tracked_markdown_home_literals_are_reported(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    docs = tmp_path / "docs" / "archive"
    docs.mkdir(parents=True)
    home = "/" + "home/someone/"  # split so this file never trips the gate itself
    (docs / "a.md").write_text(f"run `{home}.local/bin/x`\nredacted /home/.../ ok\n~/.claude ok\n", encoding="utf-8")
    (tmp_path / "untracked.md").write_text(f"{home}x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "docs/archive/a.md"], check=True)
    hits = _gate().doc_home_literals(tmp_path)
    assert hits == ["docs/archive/a.md:1"]


def test_live_tracked_markdown_is_clean():
    assert _gate().doc_home_literals(_ROOT) == []


def test_g7_runs_clean_on_live_tree():
    failures, passes = _gate().run_gates()
    assert any(p.startswith("G7") for p in passes), (failures, passes)


# --- scripts/check_ownership.py (integrate, plan 6.10.1) ------------------------------------
import json, os, sys  # noqa: E401,E402


def _own(tmp_path, packages: dict, changed: list[str]):
    pk = tmp_path / "PACKAGES.json"
    pk.write_text(json.dumps(packages), encoding="utf-8")
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "-C", str(wt), "init", "-q"], check=True)
    for rel in changed:
        p = wt / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    return subprocess.run([sys.executable, str(_ROOT / "scripts" / "check_ownership.py"),
                           "--packages", str(pk), "--worktree", str(wt), "--json"],
                          capture_output=True, text=True)


PK = {"packages": [{"id": "a", "owned_paths": ["hooks/x.py", "docs"]}, {"id": "b", "owned_paths": ["scripts"]}]}


def test_ownership_ok_when_every_change_is_owned(tmp_path):
    cp = _own(tmp_path, PK, ["hooks/x.py", "docs/a/b.md", "scripts/s.py"])
    out = json.loads(cp.stdout)
    assert cp.returncode == 0 and out["unowned"] == [] and out["multi"] == [] and out["changed"] == 3
    assert out["by_package"] == {"a": 2, "b": 1}


def test_ownership_breach_names_the_path_and_exits_1(tmp_path):
    cp = _own(tmp_path, PK, ["hooks/x.py", "rogue/new.py"])
    assert cp.returncode == 1 and json.loads(cp.stdout)["unowned"] == ["rogue/new.py"]


def test_ownership_multi_owner_is_a_breach(tmp_path):
    pk = {"packages": [{"id": "a", "owned_paths": ["docs"]}, {"id": "b", "owned_paths": ["docs/x.md"]}]}
    cp = _own(tmp_path, pk, ["docs/x.md"])
    assert cp.returncode == 1 and json.loads(cp.stdout)["multi"] == [["docs/x.md", ["a", "b"]]]


def test_ownership_reads_packages_from_the_env_when_no_flag(tmp_path):
    pk = tmp_path / "PACKAGES.json"
    pk.write_text(json.dumps(PK), encoding="utf-8")
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "-C", str(wt), "init", "-q"], check=True)
    cp = subprocess.run([sys.executable, str(_ROOT / "scripts" / "check_ownership.py"), "--worktree", str(wt)],
                        capture_output=True, text=True, env={**os.environ, "CLAUDE_ECC_PACKAGES": str(pk)})
    assert cp.returncode == 0 and cp.stdout.startswith("OK 0 changed")


def test_ownership_fails_loud_without_a_packages_file(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ECC_PACKAGES"}
    cp = subprocess.run([sys.executable, str(_ROOT / "scripts" / "check_ownership.py"), "--worktree", str(tmp_path)],
                        capture_output=True, text=True, env=env)
    assert cp.returncode == 2 and "PACKAGES" in cp.stderr
