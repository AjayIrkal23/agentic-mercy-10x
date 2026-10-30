"""Tests for scripts/restore_sessions.py (gated restore of killed sessions).

Fake `tmux` and `claude` binaries on PATH record every call; the ledger, the tier file,
the cursor and the locks live in a tmp state dir. Nothing real is launched.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ledger"
NOW = 1_800_000_000
ZERO_BOOT = "00000000-0000-0000-0000-000000000000"
posix_only = pytest.mark.skipif(os.name == "nt", reason="POSIX fake binaries; the Windows path is the flag test")


def _load():
    spec = importlib.util.spec_from_file_location("restore_sessions_under_test",
                                                  ROOT / "scripts" / "restore_sessions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rs = _load()
REAL_SID_OK = rs._SID_OK
U1 = "5f0c3a3e-1d2b-4c5d-9e8f-0a1b2c3d4e5f"

FAKE_TMUX = r"""#!/bin/sh
for a in "$@"; do printf '%s\037' "$a" >> "$FAKE_LOG"; done
printf '\n' >> "$FAKE_LOG"
env | sort > "$FAKE_LOG.env.$$"
if [ -n "$LOCK_FILE" ] && [ -f "$LOCK_FILE" ]; then cp "$LOCK_FILE" "$FAKE_LOG.lockseen"; fi
if [ "$1" = has-session ] && [ -n "$FAKE_NO_SESSION" ]; then exit 1; fi
if [ "$1" = new-window ] && [ -n "$FAKE_FAIL_WINDOW" ]; then exit 1; fi
if [ "$1" = new-window ] && [ -n "$MEM_FILE" ]; then
  printf '{"schema":1,"ts":%s,"level":"warn"}' "$NOW_TS" > "$MEM_FILE"
fi
exit 0
"""

FAKE_SYSTEMD_RUN = r"""#!/bin/sh
for a in "$@"; do printf '%s\037' "$a" >> "$FAKE_LOG.sdrun"; done
printf '\n' >> "$FAKE_LOG.sdrun"
while [ $# -gt 0 ] && [ "$1" != tmux ]; do shift; done
exec "$@"
"""


class World:
    def __init__(self, tmp_path, monkeypatch):
        self.tmp = tmp_path
        self.mp = monkeypatch
        self.state = tmp_path / "state"
        self.state.mkdir()
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self.log = tmp_path / "tmux.log"
        self.sleeps: list = []
        monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(self.state))
        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
        self.run_dir = tmp_path / "xdg"  # no `bus` file: no real systemd-run scope from a test
        self.run_dir.mkdir()
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(self.run_dir))
        for name, body in (("tmux", FAKE_TMUX), ("claude", "#!/bin/sh\nexit 0\n")):
            p = self.bin / name
            p.write_text(body, encoding="utf-8")
            p.chmod(0o755)
        monkeypatch.setenv("PATH", str(self.bin) + os.pathsep + os.environ.get("PATH", ""))
        monkeypatch.setenv("FAKE_LOG", str(self.log))
        monkeypatch.setattr(rs, "_sleep", lambda s: self.sleeps.append(s))
        monkeypatch.setattr(rs, "_now", lambda: NOW)
        monkeypatch.setattr(rs._sl, "_now", lambda: NOW)
        # shortcut: the gating/locking tests keep short readable sids ("a", "old"); the UUID-only gate itself
        # is covered by the *_real_sid_gate tests below, which put REAL_SID_OK back.
        monkeypatch.setattr(rs, "_SID_OK", re.compile(r"^[a-z][a-z0-9]{0,3}$|" + REAL_SID_OK.pattern[1:], re.I))

    def ledger(self, sid, **over):
        e = {"sid": sid, "pid": 4190000, "cwd": str(self.tmp), "transcript": None, "tmux": None,
             "scope": None, "started": NOW - 100, "seen": NOW - 100, "ended": None, "restored": False,
             "boot_id": ZERO_BOOT}
        e.update(over)
        d = self.state / "live-sessions"
        d.mkdir(exist_ok=True)
        (d / f"{sid}.json").write_text(json.dumps(e), encoding="utf-8")
        return e

    def entry(self, sid):
        return json.loads((self.state / "live-sessions" / f"{sid}.json").read_text(encoding="utf-8"))

    def tier(self, level, age=0):
        (self.state / "mem-pressure.json").write_text(
            json.dumps({"schema": 1, "ts": NOW - age, "level": level}), encoding="utf-8")

    def calls(self) -> list:
        if not self.log.exists():
            return []
        return [ln.split("\x1f")[:-1] for ln in self.log.read_text(encoding="utf-8").splitlines() if ln]

    def run(self, *argv, raw=False):
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = rs.main(["--state-dir", str(self.state), *argv])
        assert rc == 0
        text = buf.getvalue()
        return text if raw else json.loads(text)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


def _windows(calls):
    return [c for c in calls if c and c[0] in ("new-window", "new-session")]


@posix_only
def test_summary_shape_and_exit_zero(world):
    out = world.run()
    out.pop("tmux_session", None)
    assert out == {"launched": 0, "skipped": {"stale": 0, "ended": 0, "locked": 0, "flag_off": 0},
                   "stopped_reason": None, "dry_run": False, "plan": []}


@posix_only
def test_stale_entries_never_launch(world):
    world.ledger("old", started=NOW - 9000, seen=None)
    out = world.run()
    assert out["launched"] == 0 and out["skipped"]["stale"] == 1
    assert _windows(world.calls()) == []


def test_fixture_ledger_counts_one_stale(world):
    before = sorted(str(p.relative_to(FIXTURE)) for p in FIXTURE.rglob("*"))
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        assert rs.main(["--dry-run", "--state-dir", str(FIXTURE)]) == 0
    out = json.loads(buf.getvalue())
    if out["stopped_reason"] == "unsupported":
        pytest.skip("restore is POSIX only")
    assert out["skipped"]["stale"] >= 1 and out["skipped"]["ended"] >= 1
    assert sorted(str(p.relative_to(FIXTURE)) for p in FIXTURE.rglob("*")) == before


def test_flag_off_launches_nothing(world):
    world.ledger("a")
    text = world.run("--flag-file", str(ROOT / "tests" / "fixtures" / "oomguard.off.json"), raw=True)
    assert "flag_off" in text
    out = json.loads(text)
    assert out["launched"] == 0 and out["skipped"]["flag_off"] == 1 and out["stopped_reason"] == "flag_off"
    if os.name == "nt":  # expanduser reads USERPROFILE there, not the fake HOME
        return
    (world.home / ".claude").mkdir()
    (world.home / ".claude" / "oomguard.local.json").write_text('{"restore_enabled": false}', encoding="utf-8")
    out = world.run()
    assert out["launched"] == 0 and out["stopped_reason"] == "flag_off"
    assert world.calls() == []


@posix_only
def test_launches_in_start_order_and_marks_restored(world):
    world.ledger("b", started=NOW - 50, seen=NOW - 50)
    world.ledger("a", started=NOW - 90, seen=NOW - 90)
    out = world.run()
    assert out["launched"] == 2
    wins = _windows(world.calls())
    assert [w[w.index("-n") + 1] for w in wins] == ["a", "b"]
    assert world.entry("a")["restored"] is True and world.entry("b")["restored"] is True
    cursor = json.loads((world.state / "restore.cursor").read_text(encoding="utf-8"))
    assert len(cursor["launches"]) == 2
    for sid in ("a", "b"):
        lock = json.loads((world.state / "resume-lock" / sid).read_text(encoding="utf-8"))
        assert lock["owner"] == "python"


@posix_only
def test_tmux_command_shape(world, monkeypatch):
    world.ledger("a")
    world.run()
    calls = world.calls()
    assert calls[0] == ["has-session", "-t", "=claude"]
    nw = calls[1]
    assert nw[:7] == ["new-window", "-t", "=claude:", "-n", "a", "-c", str(world.tmp)]
    pane = nw[7]
    assert "env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT" in pane
    for name in rs.ENV_STRIP:
        assert f"-u {name}" in pane
    assert "--resume a" in pane
    assert rs.CONTINUE_PROMPT in pane or repr(rs.CONTINUE_PROMPT)[1:-1] in pane
    assert pane.endswith("; exec ${SHELL:-sh} -i")

    world.log.unlink()
    world.ledger("c")
    monkeypatch.setenv("FAKE_NO_SESSION", "1")
    world.run()
    calls = world.calls()
    assert calls[0] == ["has-session", "-t", "=claude"]
    assert calls[1][:9] == ["new-session", "-d", "-s", "claude", "-c", str(world.tmp), "-n", "c",
                            calls[1][8]]
    assert "--resume c" in calls[1][8]
    assert len(_windows(calls)) == 1


@posix_only
def test_claude_bin_prefers_the_wrapper(world, monkeypatch):
    world.ledger("a")
    world.run()
    assert " claude --resume a" in _windows(world.calls())[0][-1]
    cfg = world.tmp / "cfg"
    (cfg / "bin").mkdir(parents=True)
    wrapper = cfg / "bin" / "claude"
    wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    wrapper.chmod(0o755)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    world.log.unlink()
    world.ledger("b")
    world.run()
    assert f"{wrapper} --resume b" in _windows(world.calls())[0][-1]


@posix_only
def test_env_is_stripped_for_the_tmux_subprocess(world, monkeypatch):
    for k, v in (("CLAUDECODE", "1"), ("CLAUDE_CODE_SSE_PORT", "9"), ("LEAN_CTX_AGENT", "1"),
                 ("BASH_ENV", "/x"), ("MCP_TIMEOUT", "5")):
        monkeypatch.setenv(k, v)
    world.ledger("a")
    world.run()
    dumps = list(world.tmp.glob("tmux.log.env.*"))
    assert dumps
    for d in dumps:
        names = {ln.split("=", 1)[0] for ln in d.read_text(encoding="utf-8").splitlines() if "=" in ln}
        assert not names & {"CLAUDECODE", "CLAUDE_CODE_SSE_PORT", "LEAN_CTX_AGENT", "BASH_ENV", "MCP_TIMEOUT"}
        assert "PATH" in names and "HOME" in names


@posix_only
def test_per_window_and_stagger(world):
    for i in range(5):
        world.ledger(f"s{i}", started=NOW - 100 + i)
    out = world.run("--per-window", "2", "--stagger", "15")
    assert out["launched"] == 5
    assert world.sleeps == [15, 15]


@posix_only
def test_tier_flip_between_launches_stops_the_run(world, monkeypatch):
    world.ledger("a", started=NOW - 90)
    world.ledger("b", started=NOW - 50)
    world.tier("ok")
    monkeypatch.setenv("MEM_FILE", str(world.state / "mem-pressure.json"))
    monkeypatch.setenv("NOW_TS", str(NOW))
    out = world.run()
    assert out["launched"] == 1
    assert out["stopped_reason"] == "tier warn after 1"


@posix_only
@pytest.mark.parametrize("flags", [(), ("--only-if-ok",)])
def test_tier_warn_before_the_first_launch_launches_nothing(world, flags):
    world.ledger("a")
    world.tier("warn")
    out = world.run(*flags)
    assert out["launched"] == 0 and out["stopped_reason"] == "tier warn after 0"
    world.tier("crit")
    assert world.run(*flags)["stopped_reason"] == "tier crit after 0"
    world.tier("warn", age=120)
    out = world.run(*flags)
    assert out["launched"] == 1


@posix_only
def test_only_if_ok_flag_is_the_default_and_accepted(world):
    world.ledger("a")
    world.tier("warn")
    assert world.run("--only-if-ok")["stopped_reason"] == "tier warn after 0"
    world.tier("ok")
    assert world.run("--only-if-ok")["launched"] == 1


@posix_only
def test_hourly_cap(world):
    cursor = world.state / "restore.cursor"
    cursor.write_text(json.dumps({"launches": [NOW - 100] * 5}), encoding="utf-8")
    for sid in ("a", "b", "c"):
        world.ledger(sid)
    out = world.run()
    assert out["launched"] == 1 and out["stopped_reason"] == "hourly cap 6"

    world2_state = world.state
    for sid in ("a", "b", "c"):
        world.ledger(sid)
        (world2_state / "resume-lock" / sid).unlink(missing_ok=True)
    cursor.write_text(json.dumps({"launches": [NOW - 4000] * 6}), encoding="utf-8")
    out = world.run()
    assert out["launched"] == 3
    kept = json.loads(cursor.read_text(encoding="utf-8"))["launches"]
    assert all(t >= NOW - 3600 for t in kept) and len(kept) == 3


@posix_only
def test_resume_lock_held_skips_the_session(world):
    world.ledger("a")
    lock = world.state / "resume-lock" / "a"
    lock.parent.mkdir()
    fresh = json.dumps({"owner": "mod", "ts": NOW - 30})
    lock.write_text(fresh, encoding="utf-8")
    out = world.run()
    assert out["skipped"]["locked"] == 1 and out["launched"] == 0
    assert lock.read_text(encoding="utf-8") == fresh
    lock.write_text(json.dumps({"owner": "mod", "ts": NOW - 700}), encoding="utf-8")
    out = world.run()
    assert out["launched"] == 1
    assert json.loads(lock.read_text(encoding="utf-8"))["owner"] == "python"


@posix_only
def test_restore_lock_held_exits_locked(world, monkeypatch):
    world.ledger("a")
    lock = world.state / "restore.lock"
    lock.write_text(json.dumps({"pid": os.getpid(), "ts": NOW - 10}), encoding="utf-8")
    out = world.run()
    assert out["stopped_reason"] == "locked" and out["launched"] == 0
    lock.write_text(json.dumps({"pid": 4190000, "ts": NOW - 700}), encoding="utf-8")
    monkeypatch.setenv("LOCK_FILE", str(lock))
    out = world.run()
    assert out["launched"] == 1 and out["stopped_reason"] is None
    seen = json.loads((world.tmp / "tmux.log.lockseen").read_text(encoding="utf-8"))
    assert seen["pid"] == os.getpid()
    assert not lock.exists()


@posix_only
def test_dry_run_writes_nothing(world):
    world.ledger("a", started=NOW - 90)
    world.ledger("b", started=NOW - 50)
    world.ledger("old", started=NOW - 9000, seen=None)
    world.ledger("done", ended=NOW - 10)
    files = {p.name: p.read_bytes() for p in (world.state / "live-sessions").iterdir()}
    out = world.run("--dry-run")
    assert out["launched"] == 0 and out["dry_run"] is True
    plan = {p["sid"]: p for p in out["plan"]}
    assert plan["a"]["action"] == "launch" and plan["b"]["action"] == "launch"
    assert plan["old"]["reason"] == "stale" and plan["done"]["reason"] == "ended"
    for name in ("restore.lock", "restore.cursor", "resume-lock"):
        assert not (world.state / name).exists()
    assert {p.name: p.read_bytes() for p in (world.state / "live-sessions").iterdir()} == files
    assert world.calls() == []


@posix_only
def test_no_tmux_stops_with_reason(world, monkeypatch):
    (world.bin / "tmux").unlink()
    monkeypatch.setenv("PATH", str(world.bin))
    world.ledger("a")
    out = world.run()
    assert out["stopped_reason"] == "no tmux" and out["launched"] == 0


@posix_only
def test_max_caps_candidates(world):
    for i in range(4):
        world.ledger(f"s{i}", started=NOW - 100 + i)
    out = world.run("--max", "3")
    assert out["launched"] == 3 and out["stopped_reason"] == "max 3"


@posix_only
def test_resume_after_limit_respects_the_mod_flag(world):
    world.ledger("a", ended=NOW - 10)  # stopped on the limit and exited; a live pid is skipped (below)
    sf = world.state / "a.stop-failure.json"
    sf.write_text(json.dumps({"sid": "a", "ts": NOW - 10, "reason": "rate_limit"}), encoding="utf-8")
    mod = world.state / "mercy-mod.active.d" / "a.json"
    mod.parent.mkdir(exist_ok=True)
    mod.write_text(json.dumps({"sid": "a", "pid": 1, "ts": NOW - 5}), encoding="utf-8")
    out = world.run("--resume-after-limit")
    assert out["launched"] == 0 and out["skipped"]["locked"] == 1
    assert out["plan"][0]["reason"] == "mod owns resume"

    mod.write_text(json.dumps({"sid": "a", "pid": 1, "ts": NOW - 120}), encoding="utf-8")
    out = world.run("--resume-after-limit", "--dry-run")
    assert out["launched"] == 0 and out["plan"][0]["action"] == "launch"
    assert sf.exists()

    mod.unlink()
    out = world.run("--resume-after-limit")
    assert out["launched"] == 1
    pane = _windows(world.calls())[0][-1]
    assert "--resume a continue;" in pane
    assert not sf.exists()


@posix_only
def test_run_after_memwatch_debounce_file_launches(world):
    world.ledger("a")
    (world.state / "restore.spawned").write_text(json.dumps({"pid": os.getpid(), "ts": NOW}), encoding="utf-8")
    out = world.run("--only-if-ok", "--max-age", "7200")
    assert out["stopped_reason"] is None and out["launched"] >= 1  # the debounce file is not our lock


@posix_only
def test_new_session_gets_its_own_scope_when_the_user_bus_exists(world, monkeypatch):
    sd = world.bin / "systemd-run"
    sd.write_text(FAKE_SYSTEMD_RUN, encoding="utf-8")
    sd.chmod(0o755)
    (world.run_dir / "bus").write_text("", encoding="utf-8")
    monkeypatch.setenv("FAKE_NO_SESSION", "1")
    world.ledger("a")
    assert world.run()["launched"] == 1
    sdrun = [ln.split("\x1f")[:-1] for ln in Path(str(world.log) + ".sdrun").read_text(encoding="utf-8").splitlines()]
    assert len(sdrun) == 1  # only new-session; has-session talks to an existing server
    argv = sdrun[0]
    assert argv[:5] == ["--user", "--scope", "--quiet", "--collect", "--unit"]
    assert argv[5].startswith("claude-tmux-") and argv[6:8] == ["tmux", "new-session"]
    assert [c[0] for c in world.calls()] == ["has-session", "new-session"]


@posix_only
def test_no_scope_without_the_user_bus(world, monkeypatch):
    sd = world.bin / "systemd-run"
    sd.write_text(FAKE_SYSTEMD_RUN, encoding="utf-8")
    sd.chmod(0o755)
    monkeypatch.setenv("FAKE_NO_SESSION", "1")
    world.ledger("a")
    assert world.run()["launched"] == 1
    assert not Path(str(world.log) + ".sdrun").exists()
    assert rs._scope_prefix() == []
    monkeypatch.setattr(rs.plat, "IS_WINDOWS", True)
    (world.run_dir / "bus").write_text("", encoding="utf-8")
    assert rs._scope_prefix() == []


@posix_only
def test_service_run_also_resumes_after_limit_and_skips_live(world):
    world.ledger("d", ended=NOW - 10)
    world.ledger("l", pid=os.getpid(), boot_id=None)
    for sid in ("d", "l"):
        (world.state / f"{sid}.stop-failure.json").write_text(
            json.dumps({"sid": sid, "ts": NOW - 10, "reason": "rate_limit"}), encoding="utf-8")
    out = world.run("--only-if-ok", "--max-age", "7200", "--max", "6", "--per-window", "2")
    assert out["launched"] == 1
    plan = {p["sid"]: p for p in out["plan"]}  # the resume pass comes last, so its row wins
    assert plan["d"]["action"] == "launch" and plan["l"] == {"sid": "l", "action": "skip", "reason": "live"}
    panes = [w[-1] for w in _windows(world.calls())]
    assert len(panes) == 1 and "--resume d continue;" in panes[0]
    assert not (world.state / "d.stop-failure.json").exists()
    assert (world.state / "l.stop-failure.json").exists()


@posix_only
def test_restore_event_rows(world, monkeypatch):
    from lib import session_notices  # rs put hooks/ on sys.path

    events = world.state / "oomguard.events"
    world.ledger("a")
    world.run("--dry-run")
    assert not events.exists()
    assert world.run()["launched"] == 1
    rows = [json.loads(ln) for ln in events.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"kind": "restore", "sid": "a", "ok": True, "ts": NOW}]
    assert "1 session restored" in session_notices.memwatch_line()

    world.ledger("b")
    monkeypatch.setenv("FAKE_FAIL_WINDOW", "1")
    out = world.run()
    assert out["launched"] == 0
    rows = [json.loads(ln) for ln in events.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["sid"] == "b" and rows[-1]["ok"] is False


def test_windows_is_unsupported_and_exits_zero(world, monkeypatch):
    monkeypatch.setattr(rs.plat, "IS_WINDOWS", True)
    world.ledger("a")
    out = world.run()
    assert out["stopped_reason"] == "unsupported" and out["launched"] == 0
    assert world.calls() == []
    assert not (world.state / "restore.lock").exists() and not (world.state / "resume-lock").exists()


@posix_only
def test_cli_prints_json_even_on_internal_error(world, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(rs, "classify_ledger", boom)
    world.ledger("a")
    out = world.run()
    assert out["stopped_reason"].startswith("error:") and out["launched"] == 0
    assert not (world.state / "restore.lock").exists()


def test_help_lists_every_contract_flag():
    text = rs.build_parser().format_help()
    for flag in ("--dry-run", "--max", "--max-age", "--per-window", "--stagger", "--only-if-ok",
                 "--tmux-session", "--resume-after-limit", "--state-dir", "--flag-file", "--claude-bin"):
        assert flag in text


@posix_only
def test_fake_sids_are_skipped_by_the_real_sid_gate(world):
    world.mp.setattr(rs, "_SID_OK", REAL_SID_OK)
    for sid in ("verify-hookrt-r2-ss2", "doctor-fixture", "a"):
        world.ledger(sid)
    out = world.run("--dry-run")
    plan = {p["sid"]: p for p in out["plan"]}
    assert out["launched"] == 0
    for sid in ("verify-hookrt-r2-ss2", "doctor-fixture", "a"):
        assert plan[sid] == {"sid": sid, "action": "skip", "reason": "bad sid"}


@posix_only
def test_uuid_sid_passes_the_real_sid_gate(world):
    world.mp.setattr(rs, "_SID_OK", REAL_SID_OK)
    world.ledger(U1)
    world.ledger(U1.upper().replace("5F0C", "6A0C"))
    out = world.run("--dry-run")
    actions = sorted(p["action"] for p in out["plan"])
    assert actions == ["launch", "launch"] and out["launched"] == 0
