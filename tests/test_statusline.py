"""test_statusline.py — scripts/statusline.py renders one status line from the statusLine JSON.

Every test runs the script as a subprocess (the way Claude Code does) with the git cache
redirected into tmp_path through CLAUDE_STATUSLINE_CACHE_DIR.
"""

from __future__ import annotations

import calendar
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "statusline.py"
ESC = "\x1b"
EPOCH = 1_700_000_000  # 2023-11-14T22:13:20Z
ISO = "2023-11-14T22:13:20Z"


def _hhmm(epoch: int) -> str:
    return time.strftime("%H:%M", time.localtime(epoch))


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "cache"


@pytest.fixture
def run(cache, tmp_path):
    def _run(payload=None, *, raw=None, env=None, cwd=None):
        base = {k: v for k, v in os.environ.items()
                if not k.startswith("GIT_") and k not in ("NO_COLOR", "COLUMNS")}
        base["CLAUDE_STATUSLINE_CACHE_DIR"] = str(cache)
        base["NO_COLOR"] = "1"
        base.update(env or {})
        base = {k: v for k, v in base.items() if v is not None}
        data = raw if raw is not None else json.dumps(payload).encode()
        return subprocess.run([sys.executable, str(SCRIPT)], input=data, capture_output=True,
                              env=base, cwd=str(cwd or tmp_path), timeout=10)
    return _run


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false",
                    *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-b", "main")
    (r / "a.txt").write_text("one\n")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-m", "init")
    (r / "a.txt").write_text("two\n")          # ~1 modified
    (r / "c.txt").write_text("staged\n")
    _git(r, "add", "c.txt")                    # +1 staged
    (r / "b.txt").write_text("loose\n")        # ?1 untracked
    return r


def full_payload(repo: Path) -> dict:
    return {
        "model": {"display_name": "Opus 4.7"},
        "effort": {"level": "xhigh"},
        "context_window": {"used_percentage": 42, "context_window_size": 1000000},
        "cost": {"total_cost_usd": 1.3649, "total_duration_ms": 12 * 60_000 + 5,
                 "total_lines_added": 120, "total_lines_removed": 34},
        "rate_limits": {"five_hour": {"used_percentage": 31, "resets_at": EPOCH},
                        "seven_day": {"used_percentage": 64, "resets_at": EPOCH + 86400}},
        "workspace": {"current_dir": str(repo)},
        "vim": {"mode": "NORMAL"},
        "agent": {"name": "reviewer"},
    }


def test_full_payload_renders_every_segment(run, repo):
    p = run(full_payload(repo))
    out = p.stdout.decode()
    assert p.returncode == 0 and out.count("\n") == 1
    for want in ("◆ Opus 4.7 (xhigh)", "▰▰▰▰▱▱▱▱▱▱ 42%", "$1.36", f"5h 31% ↻{_hhmm(EPOCH)}",
                 "7d 64%", "⎇ main +1 ~1 ?1", "⏱ 12m", "+120 −34", "vim N", "@reviewer"):
        assert want in out, want
    assert out.count(" │ ") >= 6


def test_empty_payload_prints_something(run):
    p = run({})
    assert p.returncode == 0 and p.stdout.decode().strip() == "◆ Claude"


@pytest.mark.parametrize("raw", [b"not json", b"", b"\xff\xfe\x00garbage", b"[1,2]", b"null", b'"x"'])
def test_garbage_stdin_exits_zero(run, raw):
    p = run(raw=raw)
    assert p.returncode == 0 and p.stdout.decode().strip().startswith("◆ Claude")


def test_null_and_wrong_typed_fields_never_raise(run):
    p = run({"model": None, "context_window": {"used_percentage": "abc"}, "cost": [],
             "rate_limits": {"five_hour": {"used_percentage": None, "resets_at": "soon"}}})
    assert p.returncode == 0 and p.stdout.decode().strip() == "◆ Claude"


def test_no_color_strips_escapes_and_color_adds_them(run, repo):
    assert ESC not in run(full_payload(repo)).stdout.decode()
    colored = run(full_payload(repo), env={"NO_COLOR": None}).stdout.decode()
    assert ESC + "[" in colored


@pytest.mark.parametrize("pct,code", [(10, 78), (49, 78), (50, 220), (79, 220), (80, 203), (100, 203)])
def test_context_colour_thresholds(run, pct, code):
    out = run({"context_window": {"used_percentage": pct}}, env={"NO_COLOR": None}).stdout.decode()
    assert f"{ESC}[38;5;{code}m" in out


def test_seven_day_only_at_fifty_and_zero_cost_hidden(run):
    low = run({"cost": {"total_cost_usd": 0},
               "rate_limits": {"seven_day": {"used_percentage": 49}}}).stdout.decode()
    assert "7d" not in low and "$" not in low
    high = run({"rate_limits": {"seven_day": {"used_percentage": 50}}}).stdout.decode()
    assert "7d 50%" in high


def test_resets_at_epoch_and_iso_both_format(run):
    for stamp in (EPOCH, ISO, str(EPOCH), "2023-11-14T22:13:20+00:00"):
        out = run({"rate_limits": {"five_hour": {"used_percentage": 5, "resets_at": stamp}}}).stdout.decode()
        assert f"5h 5% ↻{_hhmm(calendar.timegm((2023, 11, 14, 22, 13, 20)))}" in out, stamp


@pytest.mark.parametrize("ms,txt", [(45_000, "⏱ 45s"), (12 * 60_000, "⏱ 12m"), (65 * 60_000, "⏱ 1h05m")])
def test_duration_format(run, ms, txt):
    assert txt in run({"cost": {"total_duration_ms": ms}}).stdout.decode()


def test_lines_hidden_when_both_zero(run):
    out = run({"cost": {"total_lines_added": 0, "total_lines_removed": 0}}).stdout.decode()
    assert "+0" not in out and "−" not in out


def test_columns_truncation_keeps_priority_segments(run, repo):
    out = run(full_payload(repo), env={"COLUMNS": "70"}).stdout.decode().strip()
    assert len(out) <= 70
    for keep in ("◆ Opus 4.7", "42%", "$1.36", "⎇ main"):
        assert keep in out
    for dropped in ("⏱", "+120", "@reviewer"):
        assert dropped not in out
    tiny = run(full_payload(repo), env={"COLUMNS": "10"}).stdout.decode()
    assert "◆ Opus 4.7" in tiny and "⎇ main" in tiny
    wide = run(full_payload(repo), env={"COLUMNS": "abc"}).stdout.decode()
    assert "⏱" in wide


def test_git_counts_branch_and_detached_head(run, repo):
    out = run({"workspace": {"current_dir": str(repo)}}).stdout.decode()
    assert "⎇ main +1 ~1 ?1" in out
    sha = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=repo, capture_output=True,
                         text=True, check=True).stdout.strip()
    _git(repo, "checkout", "--detach")
    out = run({"workspace": {"current_dir": str(repo)}}, env={"CLAUDE_STATUSLINE_CACHE_DIR": str(repo.parent / "c2")})
    assert f"⎇ {sha}" in out.stdout.decode()


def test_git_hidden_outside_a_repo(run, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    out = run({"workspace": {"current_dir": str(plain)}},
              env={"GIT_CEILING_DIRECTORIES": str(tmp_path)}).stdout.decode()
    assert "⎇" not in out


def test_git_ahead_behind_from_upstream(run, repo, tmp_path):
    _git(repo, "stash", "-u")
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "main")
    (repo / "n.txt").write_text("n\n")
    _git(repo, "add", "n.txt")
    _git(repo, "commit", "-m", "ahead")
    out = run({"workspace": {"current_dir": str(repo)}}).stdout.decode()
    assert "⎇ main ↑1" in out and "↓" not in out


def test_git_result_is_cached_per_repo(run, repo, cache):
    pl = {"workspace": {"current_dir": str(repo)}}
    first = run(pl).stdout.decode()
    (repo / "extra.txt").write_text("x\n")
    assert run(pl).stdout.decode() == first          # within 5 s: served from the cache
    assert any(cache.iterdir())
    fresh = run(pl, env={"CLAUDE_STATUSLINE_CACHE_DIR": str(cache) + "-new"}).stdout.decode()
    assert "?2" in fresh and fresh != first


# The warm-path wall-clock test is gone (A3v2-06, A7v2-05: it failed 8 of 12 runs on a loaded box). What it
# guarded is structural and pinned in test_statusline_win.py: `test_warm_path_skips_openssl` (the
# import-time list has no hashlib / tempfile / subprocess, so no git process) and
# `test_a_fresh_cache_entry_means_no_git_call` (call count).

