"""hooks/tools/selfheal-daily.py (WP-D): rate limit, lock, independent steps, summary
contract for the aggregator, log hygiene, --dry-run. Fake claude on PATH, tmp state dir."""
from __future__ import annotations

import datetime as dt
import importlib.util
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from test_autonomy_wpd_fixtures import SECRET, box, manifest, npx  # noqa: F401

import deps  # noqa: E402
import selfheal  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
ENV = {"TOKEN": SECRET}
_NODE = shutil.which("node")


@pytest.fixture
def sd(box, monkeypatch):
    for mod in (deps, selfheal):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "x")  # selfheal.pin_config_dir edits os.environ:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")       # let monkeypatch restore it afterwards
    spec = importlib.util.spec_from_file_location("selfheal_daily", _ROOT / "hooks" / "tools" / "selfheal-daily.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    monkeypatch.setattr(deps, "_load_manifest", lambda: manifest(npx("a", "@x/a@2.0.0")))
    box.write_live({"a": {"type": "stdio", "command": "npx", "args": ["-y", "@x/a@1.0.0"], "env": dict(ENV)}})
    monkeypatch.setenv("SELFHEAL_DAILY_ALLOW_TEST", "1")  # these tests run the real main() on purpose
    return mod


def test_main_is_a_no_op_under_pytest_without_the_opt_in(sd, box, monkeypatch, capsys):
    """A test that fires the real session-start chain must never self-heal the LIVE install."""
    calls = _counting(sd, monkeypatch)
    monkeypatch.delenv("SELFHEAL_DAILY_ALLOW_TEST")
    assert "PYTEST_CURRENT_TEST" in __import__("os").environ
    assert sd.main([]) == 0
    assert calls == [] and capsys.readouterr().out.strip() == "{}"
    assert list(box.state.iterdir()) == []


def test_mcp_step_re_registers_a_manifest_server_missing_from_the_config(sd, box, monkeypatch):
    """A restore that failed leaves the server unregistered; the next daily run adds it back."""
    monkeypatch.setattr(deps, "_load_manifest",
                        lambda: manifest(npx("a", "@x/a@2.0.0"), npx("gone", "@x/gone@1.0.0")))
    box.write_live({"a": {"type": "stdio", "command": "npx", "args": ["-y", "@x/a@2.0.0"], "env": dict(ENV)}})
    _only(sd, monkeypatch, "mcp")
    sd.main([])
    assert any(c[:2] == ["mcp", "add"] and "gone" in c for c in box.calls())
    assert any("gone" in c and "ADDED" in c for c in _summary(box)["changed"])


def test_a_server_that_could_not_be_restored_is_an_error_in_the_summary(sd, box, monkeypatch):
    _only(sd, monkeypatch, "mcp")
    monkeypatch.setenv("FAKE_CLAUDE_FAIL_SPEC", "@x/a")
    sd.main([])
    assert any("FAIL(unregistered)" in e for e in _summary(box)["errors"])


def _only(sd, monkeypatch, *names):
    monkeypatch.setattr(sd, "STEPS", [s for s in sd.STEPS if s[0] in names])


def _summary(box) -> dict:
    return json.loads((box.state / "selfheal-daily.json").read_text(encoding="utf-8"))


def _stamp(box, hours_ago: float, **extra) -> None:
    at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)
    (box.state / "selfheal-daily.json").write_text(
        json.dumps({"at": at.isoformat(), "changed": [], "errors": [], "reported": True, **extra}), encoding="utf-8")


def _counting(sd, monkeypatch, result=None):
    calls: list = []
    monkeypatch.setattr(sd, "STEPS", [("one", lambda ctx: calls.append(1) or (result or []))])
    return calls


def test_pin_drift_is_reconciled_and_summarised_for_the_aggregator(sd, box, monkeypatch, capsys):
    _only(sd, monkeypatch, "mcp")
    assert sd.main([]) == 0
    assert capsys.readouterr().out.strip() == "{}"
    s = _summary(box)
    assert set(s) == {"at", "changed", "errors", "reported"}
    assert s["reported"] is False and s["errors"] == []
    assert any("a" in c and "@x/a@1.0.0 -> @x/a@2.0.0" in c for c in s["changed"])
    assert box.live()["a"]["args"] == ["-y", "@x/a@2.0.0"]
    log = (box.state / "selfheal-daily.log").read_text(encoding="utf-8")
    assert "@x/a@1.0.0 -> @x/a@2.0.0" in log


def test_no_secret_reaches_the_log_summary_or_stdout(sd, box, monkeypatch, capsys):
    _only(sd, monkeypatch, "mcp")
    sd.main([])
    blob = capsys.readouterr().out + (box.state / "selfheal-daily.log").read_text(encoding="utf-8")
    blob += (box.state / "selfheal-daily.json").read_text(encoding="utf-8")
    assert SECRET not in blob


def test_nothing_to_do_is_stamped_and_already_reported(sd, box, monkeypatch):
    _only(sd, monkeypatch, "mcp")
    box.write_live({"a": {"type": "stdio", "command": "npx", "args": ["-y", "@x/a@2.0.0"]}})
    sd.main([])
    s = _summary(box)
    assert s["changed"] == [] and s["errors"] == [] and s["reported"] is True and s["at"]
    assert box.calls() == []


def test_runs_at_most_once_a_day(sd, box, monkeypatch):
    calls = _counting(sd, monkeypatch)
    sd.main([])
    sd.main([])
    assert len(calls) == 1
    _stamp(box, 25)
    sd.main([])
    assert len(calls) == 2


def test_a_held_lock_skips_the_run(sd, box, monkeypatch):
    calls = _counting(sd, monkeypatch)
    # held through the module's own lock (fcntl on POSIX, msvcrt on Windows): a
    # module-level `import fcntl` stopped the whole suite from collecting on Windows
    with sd._try_lock(box.state / "selfheal-daily.lock") as held:
        assert held
        assert sd.main([]) == 0
    assert calls == [] and not (box.state / "selfheal-daily.json").exists()


def test_one_failing_step_never_stops_the_others(sd, box, monkeypatch):
    def boom(ctx):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(sd, "STEPS", [("bad", boom), ("good", lambda ctx: [("dep", "x", "INSTALLED")])])
    assert sd.main([]) == 0
    s = _summary(box)
    assert s["changed"] == ["dep x: INSTALLED"]
    assert len(s["errors"]) == 1 and "bad" in s["errors"][0] and "kaboom" in s["errors"][0]


def test_unreported_changes_from_the_last_run_are_carried_forward(sd, box, monkeypatch):
    _stamp(box, 30, changed=["dep old: INSTALLED"], reported=False)
    monkeypatch.setattr(sd, "STEPS", [("good", lambda ctx: [("dep", "new", "INSTALLED")])])
    sd.main([])
    s = _summary(box)
    assert s["changed"] == ["dep old: INSTALLED", "dep new: INSTALLED"] and s["reported"] is False


def test_dry_run_prints_the_plan_and_writes_nothing(sd, box, monkeypatch, capsys):
    _only(sd, monkeypatch, "mcp")
    _stamp(box, 1)  # a fresh stamp does not stop a dry run
    before = (box.state / "selfheal-daily.json").read_text(encoding="utf-8")
    assert sd.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "WOULD-PIN: @x/a@1.0.0 -> @x/a@2.0.0" in out and SECRET not in out
    assert box.calls() == []
    assert sorted(p.name for p in box.state.iterdir()) == ["selfheal-daily.json"]
    assert (box.state / "selfheal-daily.json").read_text(encoding="utf-8") == before


def test_doctor_mode_is_a_no_op(sd, box, monkeypatch, capsys):
    calls = _counting(sd, monkeypatch)
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    assert sd.main([]) == 0
    assert calls == [] and capsys.readouterr().out.strip() == "{}"
    assert list(box.state.iterdir()) == []


def test_link_doctor_probe_payload_is_a_no_op(sd, box, monkeypatch, capsys):
    """hooks/tools/link-doctor.py fires every link with session_id 'link-doctor' and does
    not always set CLAUDE_HOOK_DOCTOR: a probe must never touch the live registrations."""
    calls = _counting(sd, monkeypatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"session_id": "link-doctor", "source": "startup"})))
    assert sd.main([]) == 0
    assert calls == [] and capsys.readouterr().out.strip() == "{}"
    assert box.calls() == [] and not (box.state / "selfheal-daily.json").exists()


def test_a_real_session_payload_still_runs(sd, box, monkeypatch):
    calls = _counting(sd, monkeypatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"session_id": "abc", "source": "startup"})))
    sd.main([])
    assert len(calls) == 1


def test_deps_step_installs_missing_tools_and_reports_failures(sd, box, monkeypatch):
    seen: dict = {}

    def fake(env, *, ci=False, dry_run=False, skip_optional=False):
        seen.update(ci=ci, dry_run=dry_run)
        return [("x", "INSTALLED"), ("y", "PRESENT"), ("z", "WARN(rc=1)")]
    monkeypatch.setattr(deps, "install_deps", fake)
    _only(sd, monkeypatch, "deps")
    sd.main([])
    s = _summary(box)
    assert seen == {"ci": False, "dry_run": False}
    assert s["changed"] == ["dep x: INSTALLED"] and s["errors"] == ["dep z: WARN(rc=1)"]


def test_deps_step_heals_base_tools_through_the_os_dispatcher(sd, box, monkeypatch):
    """`userspace.ensure_userspace` returns [] off POSIX, so the daily run never repaired
    Windows base tools; `basetools.ensure_base_tools` picks wintools there."""
    import basetools  # type: ignore
    monkeypatch.delenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", raising=False)
    seen: list = []
    monkeypatch.setattr(basetools, "ensure_base_tools",
                        lambda env, manifest, *, ci=False, dry_run=False: seen.append((ci, dry_run)) or [("git", "INSTALLED x")])
    monkeypatch.setattr(deps, "install_deps", lambda env, **k: [])
    _only(sd, monkeypatch, "deps")
    sd.main([])
    assert seen == [(False, False)]
    assert _summary(box)["changed"] == ["dep git: INSTALLED x"]


def _settings(sd, box, monkeypatch, *, exists: bool, stale: bool):
    target = box.home / "claude-dir"
    target.mkdir()
    if exists:
        (target / "settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sd.plat, "claude_dir", lambda: target)
    rendered: list = []
    monkeypatch.setattr(selfheal, "_stale", lambda st: stale)
    monkeypatch.setattr(selfheal, "_ensure_settings",
                        lambda t, env, emit, **k: rendered.append(1) or emit("settings", "settings.json", "OK(rendered, was stale)"))
    _only(sd, monkeypatch, "settings")
    return rendered


def test_settings_are_re_rendered_only_when_missing_or_stale(sd, box, monkeypatch):
    rendered = _settings(sd, box, monkeypatch, exists=True, stale=False)
    sd.main([])
    assert rendered == []
    _stamp(box, 30)
    monkeypatch.setattr(selfheal, "_stale", lambda st: True)
    sd.main([])
    assert rendered == [1] and _summary(box)["changed"] == ["settings settings.json: OK(rendered, was stale)"]


def test_settings_dry_run_plans_without_rendering(sd, box, monkeypatch, capsys):
    rendered = _settings(sd, box, monkeypatch, exists=True, stale=True)
    sd.main(["--dry-run"])
    assert rendered == [] and "WOULD-RENDER" in capsys.readouterr().out


def _fake_vendor(tmp: Path, monkeypatch, sd, check_rc: int) -> Path:
    log = tmp / "vendor.log"
    script = tmp / "vendor_skill.py"
    script.write_text("import sys\nopen(%r, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                      "sys.exit(%d if '--check' in sys.argv else 0)\n" % (str(log), check_rc), encoding="utf-8")
    monkeypatch.setattr(sd, "VENDOR", script)
    return log


def test_vendored_skills_are_re_vendored_only_on_drift(sd, box, monkeypatch, tmp_path):
    _only(sd, monkeypatch, "vendor")
    log = _fake_vendor(tmp_path, monkeypatch, sd, check_rc=0)  # OK / BEHIND exit 0
    sd.main([])
    assert log.read_text(encoding="utf-8").split("\n")[:-1] == ["--all --check"]
    assert _summary(box)["changed"] == []
    _stamp(box, 30)
    log = _fake_vendor(tmp_path, monkeypatch, sd, check_rc=1)  # DRIFT
    log.unlink()
    sd.main([])
    assert log.read_text(encoding="utf-8").split("\n")[:-1] == ["--all --check", "--all"]
    assert any(c.startswith("vendor") for c in _summary(box)["changed"])


def test_ponytail_board_import_runs_from_the_installed_plugin(sd, box, monkeypatch):
    if not _NODE:
        pytest.skip("no node on PATH")
    monkeypatch.setattr(sd.plat, "node_exe", lambda: _NODE)  # box trims PATH to the fake claude
    target = box.home / "claude-dir"
    hooks = target / "plugins" / "cache" / "ponytail" / "5.3.2" / "hooks"
    hooks.mkdir(parents=True)
    projects, ran = box.home / "projects", box.home / "ran.txt"
    projects.mkdir()
    for name in ("old.jsonl", "live.jsonl", "notes.txt"):
        (projects / name).write_text("{}", encoding="utf-8")
    two_days_ago = time.time() - 2 * 86400
    os.utime(projects / "old.jsonl", (two_days_ago, two_days_ago))
    # what the real import sees in a projects dir: a live transcript must stay hidden
    (hooks / "ponytail-band-import.js").write_text(
        "const fs = require('fs');\nmodule.exports = { run() { fs.writeFileSync("
        f"{json.dumps(str(ran))}, fs.readdirSync({json.dumps(str(projects))}).sort().join(',')); return {{}} }} }};\n",
        encoding="utf-8")
    monkeypatch.setattr(sd.plat, "claude_dir", lambda: target)
    _only(sd, monkeypatch, "ponytail-board")
    sd.main([])  # no installed_plugins.json: nothing to run, not an error
    assert not ran.exists() and _summary(box)["errors"] == []
    (target / "plugins" / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {"ponytail@ponytail": [{"installPath": str(hooks.parent)}]}}), encoding="utf-8")
    _stamp(box, 30)
    sd.main([])
    assert ran.read_text(encoding="utf-8") == "notes.txt,old.jsonl" and _summary(box)["errors"] == []


# --- integrate: the seven merge steps (plan 6.10, R3.7) ------------------------------------
def _cp(rc=0, out="", err=""):
    import types
    return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


def test_step_ids_and_order(sd):
    ids = [n for n, _ in sd.STEPS]
    assert ids == ["mcp", "deps", "plan-tier", "settings", "oomguard", "machines-split", "vendor", "workflows",
                   "library", "mcp-inventory", "ponytail-board", "learning-evolve"]
    assert ids.index("plan-tier") < ids.index("settings")  # a new tier lands in the same run's render


def test_learning_evolve_rows(sd, monkeypatch, tmp_path):
    ctx = sd.Ctx(False, tmp_path, 60)
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(0, "evolved k-1: +1 new, 0 reaffirmed, 0 pruned\n"
                                                               "DEFERRED k-2: no answer\n2 promoted\n"))
    assert sd._learning_evolve(ctx) == [("learning", "k-1", "EVOLVED +1 new, 0 reaffirmed, 0 pruned"),
                                        ("learning", "global", "EVOLVED 2 promoted")]
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(1))
    assert sd._learning_evolve(ctx) == [("learning", "evolve", "WARN(rc=1)")]
    monkeypatch.setattr(sd, "INSTINCTS", tmp_path / "missing.py")
    assert sd._learning_evolve(ctx) == []


def test_workflows_step_renders_only_on_drift(sd, monkeypatch, tmp_path):
    def run(argv, timeout=None, **k):
        return _cp(1 if "--check" in argv else 0)
    monkeypatch.setattr(sd.plat, "run", run)
    assert sd._workflows(sd.Ctx(True, tmp_path, 60)) == [("workflows", "render", "WOULD-RENDER (drift or not rendered)")]
    assert sd._workflows(sd.Ctx(False, tmp_path, 60)) == [("workflows", "render", "OK(rendered)")]
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(0))
    assert sd._workflows(sd.Ctx(False, tmp_path, 60)) == []


def test_library_step_skips_without_the_vault(sd, monkeypatch, tmp_path):
    monkeypatch.setattr(sd, "LIB_INDEX", tmp_path / "nope.py")
    assert sd._library(sd.Ctx(False, tmp_path, 60)) == [("library", "index", "SKIP(absent)")]


def test_machines_split_rows(sd, monkeypatch, tmp_path):
    ctx = sd.Ctx(False, tmp_path, 60)
    monkeypatch.setattr(sd, "SPLIT", tmp_path / "split.py")
    (tmp_path / "split.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(0, "machines-split: moved 3 tails; journal x.md; terms 12"))
    assert sd._machines_split(ctx) == [("machines-split", "apply", "MOVED(machines-split: moved 3 tails; journal x.md; terms 12)")]
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(0, "unchanged"))
    assert sd._machines_split(ctx) == []
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(2, "machines-split: REFUSED — journal not gitignored"))
    assert sd._machines_split(ctx)[0][2].startswith("WARN(rc=2")


def test_oomguard_step_splits_rows(sd, monkeypatch, tmp_path):
    import types
    monkeypatch.setitem(sys.modules, "oomguard_setup", types.SimpleNamespace(
        ensure=lambda dry=False: ["unit claude-memwatch.service: CREATED", "SKIP: no systemd user manager"]))
    assert sd._oomguard(sd.Ctx(False, tmp_path, 60)) == [("oomguard", "unit claude-memwatch.service", "CREATED"),
                                                         ("oomguard", "SKIP", "no systemd user manager")]


def test_plan_tier_step_reports_only_a_change(sd, monkeypatch, tmp_path):
    ctx = sd.Ctx(False, tmp_path, 60)
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(0, '{"tier": "pro", "changed": true}'))
    assert sd._plan_tier(ctx) == [("plan-tier", "detect", "UPDATED tier=pro")]
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(0, '{"tier": "pro", "changed": false}'))
    assert sd._plan_tier(ctx) == []
    assert sd._plan_tier(sd.Ctx(True, tmp_path, 60)) == [("plan-tier", "detect", "WOULD-DETECT")]


def test_mcp_inventory_skips_without_the_writer_flag(sd, monkeypatch, tmp_path):
    """Rohit's PC, round 2 (I-2): the daily self-heal rewrote the tracked mcp-inventory.md on a second machine,
    which dirties its checkout and blocks the next `git pull --ff-only`. Only the committing machine opts in."""
    target = tmp_path / "inv.md"
    target.write_bytes(b"keep\n")
    monkeypatch.setattr(sd, "INVENTORY_MD", target)
    monkeypatch.setattr(sd, "INVENTORY", tmp_path / "inv.py")
    (tmp_path / "inv.py").write_text("", encoding="utf-8")
    monkeypatch.delenv("AGENTIC_MERCY_INVENTORY_WRITER", raising=False)
    monkeypatch.setattr(sd.plat, "claude_dir", lambda: tmp_path)
    monkeypatch.setattr(sd.plat, "IS_WINDOWS", False)
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(0, "| Server |\n| new |\n"))
    assert sd._mcp_inventory(sd.Ctx(False, tmp_path, 60)) == []
    assert target.read_bytes() == b"keep\n"
    (tmp_path / "settings.user.json").write_text('{"env": {"AGENTIC_MERCY_INVENTORY_WRITER": "1"}}', encoding="utf-8")
    assert sd._mcp_inventory(sd.Ctx(False, tmp_path, 60)) == [("mcp-inventory", "mcp-inventory.md", "UPDATED")]


def test_mcp_inventory_rewrites_only_on_change(sd, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_MERCY_INVENTORY_WRITER", "1")
    target = tmp_path / "skills" / "mcp-usage-standards" / "references" / "mcp-inventory.md"
    target.parent.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    monkeypatch.setattr(sd, "INVENTORY_MD", target)
    monkeypatch.setattr(sd, "INVENTORY", tmp_path / "inv.py")
    (tmp_path / "inv.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(0, "new\n"))
    assert sd._mcp_inventory(sd.Ctx(False, tmp_path, 60)) == [("mcp-inventory", "mcp-inventory.md", "UPDATED")]
    assert target.read_text(encoding="utf-8") == "new\n"
    assert sd._mcp_inventory(sd.Ctx(False, tmp_path, 60)) == []
    assert sd._mcp_inventory(sd.Ctx(True, tmp_path, 60)) == []        # dry: never writes


def test_mcp_inventory_keeps_the_preamble(sd, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENTIC_MERCY_INVENTORY_WRITER", "1")
    target = tmp_path / "inv.md"
    target.write_text("# Inventory\nhand text\n\n| Server | x |\n|---|---|\n| a | 1 |\n", encoding="utf-8")
    monkeypatch.setattr(sd, "INVENTORY_MD", target)
    monkeypatch.setattr(sd, "INVENTORY", tmp_path / "inv.py")
    (tmp_path / "inv.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(0, "generated header\n| Server | x |\n|---|---|\n| b | 2 |\n"))
    assert sd._mcp_inventory(sd.Ctx(False, tmp_path, 60)) == [("mcp-inventory", "mcp-inventory.md", "UPDATED")]
    assert target.read_text(encoding="utf-8") == "# Inventory\nhand text\n\n| Server | x |\n|---|---|\n| b | 2 |\n"


def test_mcp_inventory_output_is_public(sd):
    home = str(Path.home())
    md = (f"| Server | Scope |\n|---|---|\n| `a` | user | `{home}/.local/bin/a` |\n"
          f"| `s` | project:{home}/r | http |\n2 servers\n")
    out = sd._public(md)
    assert home not in out and "project:" not in out and "`~/.local/bin/a`" in out and out.endswith("2 servers\n")


def test_mcp_inventory_scrubs_every_spelling_of_a_windows_home(sd, monkeypatch):
    from pathlib import PureWindowsPath
    home = PureWindowsPath("C:" + "\\", "Users", "someone")  # built, not a literal (portability gate G2/G3)
    fwd, back = home.as_posix(), str(home)
    monkeypatch.setattr(sd.Path, "home", classmethod(lambda cls: home))
    md = ("| Server | Scope | Transport | Target | Reach |\n|---|---|---|---|---|\n"
          f"| `g` | user | stdio | `{fwd}/AppData/py/python.exe {fwd}/.claude/hooks/x.py` | — |\n"
          f"| `j` | user | stdio | `{back}\\.local\\bin\\j.exe` | — |\n"
          f"| `s` | project:{fwd}/r | http | `https://x` | — |\n"
          "| `f` | plugin:f@m | http | `https://f` | — |\n"
          "\n2 user-scope, 2 project/plugin-scope servers.\n")
    out = sd._public(md)
    assert "someone" not in out and "project:" not in out
    assert "`~/AppData/py/python.exe ~/.claude/hooks/x.py`" in out
    assert out.endswith("2 user-scope, 1 project/plugin-scope servers.\n")  # recounted after the drop


def test_mcp_inventory_skips_on_the_windows_replica(sd, monkeypatch, tmp_path):
    target = tmp_path / "inv.md"
    target.write_text("keep\n", encoding="utf-8")
    monkeypatch.setattr(sd, "INVENTORY_MD", target)
    monkeypatch.setattr(sd, "INVENTORY", tmp_path / "inv.py")
    (tmp_path / "inv.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(sd.plat, "IS_WINDOWS", True)
    monkeypatch.setattr(sd.plat, "run", lambda *a, **k: _cp(0, "| Server |\n| new |\n"))
    assert sd._mcp_inventory(sd.Ctx(False, tmp_path, 60)) == [("mcp-inventory", "mcp-inventory.md", "SKIP(replica)")]
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_changed_markers_cover_the_new_statuses(sd):
    for s in ("CREATED x", "UPDATED", "APPENDED", "ENABLED", "MOVED(x)", "REBUILT", "EVOLVED +1", "ALWAYS-LOAD true",
              "OK(rendered)"):
        assert sd._classify(s) == "changed", s
    assert sd._classify("SKIP(absent)") is None and sd._classify("WARN(rc=1)") == "error"
