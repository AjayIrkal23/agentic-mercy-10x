"""WP-D (autonomy 2026-10-05): MCP pin reconcile, doctor routing, selfheal wiring, pins,
dispatch link. The claude CLI is a fake on PATH (see test_autonomy_wpd_fixtures)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from test_autonomy_wpd_fixtures import SECRET, box, manifest, npx  # noqa: F401

import deps  # noqa: E402
import doctor_mcp  # noqa: E402
import selfheal  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
ENV = {"TOKEN": SECRET, "KEEP": "1"}


@pytest.fixture(autouse=True)
def _pin_modules(monkeypatch):
    for mod in (deps, selfheal, doctor_mcp):  # other tests re-exec installer modules (I-17)
        monkeypatch.setitem(sys.modules, mod.__name__, mod)


def _use(monkeypatch, m: dict) -> None:
    monkeypatch.setattr(deps, "_load_manifest", lambda: m)


def _live(**entries) -> dict:
    return {k: {"type": "stdio", "command": "npx", "args": ["-y", v], "env": dict(ENV)} for k, v in entries.items()}


# --- deps.reconcile_mcp_pins ------------------------------------------------------ #
def test_pin_drift_is_re_registered_with_env_copied_verbatim(box, monkeypatch):
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@1.0.0"))
    out = deps.reconcile_mcp_pins()
    assert out == [("a", "PINNED @x/a@1.0.0 -> @x/a@2.0.0")]
    assert [c[:4] for c in box.calls()] == [["mcp", "remove", "--scope", "user"],
                                            ["mcp", "add-json", "--scope", "user"]]
    assert box.live()["a"] == {"type": "stdio", "command": "npx", "args": ["-y", "@x/a@2.0.0"], "env": ENV}


def test_floating_bare_package_gets_the_manifest_pin(box, monkeypatch):
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a"))
    assert deps.reconcile_mcp_pins() == [("a", "PINNED @x/a -> @x/a@2.0.0")]
    assert box.live()["a"]["args"] == ["-y", "@x/a@2.0.0"]


def test_no_drift_runs_no_command(box, monkeypatch):
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@2.0.0"))
    assert deps.reconcile_mcp_pins() == []
    assert box.calls() == []


def test_oauth_unpinned_unlisted_and_bare_binary_servers_are_skipped(box, monkeypatch):
    _use(monkeypatch, manifest(
        npx("web", "@x/web@2.0.0"), npx("loose", "@x/loose"), npx("bin", "@x/bin@2.0.0"),
        {"name": "oauth", "add": ["claude", "mcp", "add", "--transport", "http", "oauth", "https://h/mcp"]}))
    live = _live(loose="@x/loose@1.0.0", extra="@x/extra@1.0.0")
    live["web"] = {"type": "http", "url": "https://h/mcp"}
    live["oauth"] = {"type": "http", "url": "https://h/mcp"}
    live["bin"] = {"type": "stdio", "command": "bin-tool", "args": []}
    box.write_live(live)
    assert deps.reconcile_mcp_pins() == []
    assert box.calls() == []


def test_a_failed_add_restores_the_live_entry(box, monkeypatch):
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@1.0.0"))
    monkeypatch.setenv("FAKE_CLAUDE_FAIL_SPEC", "@x/a@2.0.0")
    out = deps.reconcile_mcp_pins()
    assert out == [("a", "WARN(rc=1, restored)")]
    assert box.live()["a"]["args"] == ["-y", "@x/a@1.0.0"] and box.live()["a"]["env"] == ENV


def test_a_failed_restore_is_reported_unregistered_not_restored(box, monkeypatch):
    """Santa: both add-json calls failing left the server out of ~/.claude.json while the
    status still said "restored"."""
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@1.0.0"))
    monkeypatch.setenv("FAKE_CLAUDE_FAIL_SPEC", "@x/a")  # the new spec AND the restore fail
    assert deps.reconcile_mcp_pins() == [("a", "FAIL(unregistered)")]
    assert "a" not in box.live()


def test_a_failed_restore_after_an_env_reconcile_is_reported_unregistered(box, monkeypatch):
    srv = npx("a", "@x/a@2.0.0")
    srv["add"] = srv["add"][:5] + ["-e", "FLAG=1"] + srv["add"][5:]
    _use(monkeypatch, manifest(srv))
    box.write_live(_live(a="@x/a@2.0.0"))
    monkeypatch.setenv("FAKE_CLAUDE_FAIL_SPEC", "@x/a")
    assert deps.reconcile_mcp_env() == [("a", "FAIL(unregistered)")]
    assert "a" not in box.live()


def test_a_successful_restore_keeps_the_restored_status(box, monkeypatch):
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@1.0.0"))
    monkeypatch.setenv("FAKE_CLAUDE_FAIL_SPEC", "@x/a@2.0.0")  # only the new spec fails
    assert deps.reconcile_mcp_pins() == [("a", "WARN(rc=1, restored)")]


def test_shell_wrapped_spec_is_swapped_inside_the_command_string(box, monkeypatch):
    _use(monkeypatch, manifest({"name": "gh", "add": ["claude", "mcp", "add", "gh", "--", "sh", "-c",
                                                      "T=$(gh auth token) exec npx -y @x/gh@2025.4.8"]}))
    box.write_live({"gh": {"type": "stdio", "command": "sh",
                           "args": ["-c", "T=$(gh auth token) exec npx -y @x/gh"]}})
    assert deps.reconcile_mcp_pins() == [("gh", "PINNED @x/gh -> @x/gh@2025.4.8")]
    assert box.live()["gh"]["args"] == ["-c", "T=$(gh auth token) exec npx -y @x/gh@2025.4.8"]


def test_uvx_specs_are_read_and_swapped(box, monkeypatch):
    assert doctor_mcp.npx_spec("uvx tool==1.2.3") == "tool==1.2.3"
    assert doctor_mcp.spec_version("tool==1.2.3") == "1.2.3"
    _use(monkeypatch, manifest({"name": "u", "add": ["claude", "mcp", "add", "u", "--", "uvx", "tool==2.0.0"]}))
    box.write_live({"u": {"type": "stdio", "command": "uvx", "args": ["tool==1.0.0"]}})
    assert deps.reconcile_mcp_pins() == [("u", "PINNED tool==1.0.0 -> tool==2.0.0")]
    assert box.live()["u"]["args"] == ["tool==2.0.0"]


def test_dry_run_plans_without_running_the_cli(box, monkeypatch):
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@1.0.0"))
    assert deps.reconcile_mcp_pins(dry_run=True) == [("a", "WOULD-PIN: @x/a@1.0.0 -> @x/a@2.0.0")]
    assert box.calls() == []


def test_no_env_value_reaches_any_status(box, monkeypatch):
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@1.0.0"))
    assert SECRET not in json.dumps(deps.reconcile_mcp_pins(dry_run=True))
    assert SECRET not in json.dumps(deps.reconcile_mcp_pins())


# --- doctor: drift is repairable --------------------------------------------------- #
def _drifted():
    return manifest(npx("a", "@x/a@2.0.0")), {"a": {"command": "npx", "args": ["-y", "@x/a@1.0.0"]}}


def test_roster_pin_drift_fails_only_when_a_reconcile_is_possible():
    m, live = _drifted()
    assert doctor_mcp.roster_status(m, live, set())[0] == "WARN"
    st, det = doctor_mcp.roster_status(m, live, set(), repairable=True)
    assert st == "FAIL" and "a @x/a@1.0.0 != @x/a@2.0.0" in det


def test_deprecated_note_alone_stays_a_warn_even_when_repairable():
    m = manifest(npx("a", "@x/a@2.0.0", deprecated="use the new one"))
    live = {"a": {"command": "npx", "args": ["-y", "@x/a@2.0.0"]}}
    st, det = doctor_mcp.roster_status(m, live, set(), repairable=True)
    assert st == "WARN" and "use the new one" in det


def test_unpinned_manifest_spec_is_not_pin_drift():
    m = manifest(npx("a", "@x/a"))
    live = {"a": {"command": "npx", "args": ["-y", "@x/a@1.0.0"]}}
    assert doctor_mcp.roster_status(m, live, set(), repairable=True)[0] == "PASS"


def test_repair_routes_a_roster_fail_to_the_pin_reconcile(box, monkeypatch):
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@1.0.0"))
    seen: list = []
    selfheal._repair(box.home, {"mcp-roster"}, None, lambda *a: seen.append(a))
    assert seen == [("repair", "a", "PINNED @x/a@1.0.0 -> @x/a@2.0.0")]


def test_install_pass_runs_the_pin_reconcile_after_the_env_reconcile(monkeypatch, tmp_path):
    order: list = []
    for fn in ("check_prereqs", "install_deps", "register_mcps", "reconcile_mcp_env",
               "reconcile_mcp_pins", "install_plugins", "run_post_steps"):
        monkeypatch.setattr(deps, fn, lambda *a, _n=fn, **k: order.append(_n) or [])
    monkeypatch.setattr(deps, "configure_lean_ctx", lambda **k: ("lean-ctx-config", "x"))
    monkeypatch.setattr(selfheal, "_ensure_settings", lambda *a, **k: None)
    monkeypatch.setattr(selfheal, "_validate_fix", lambda *a, **k: None)
    import jcodemunch_config as jc
    monkeypatch.setattr(jc, "configure", lambda **k: ("jcodemunch-config", "x"))
    selfheal._install_pass(tmp_path, object(), lambda *a: None, True)
    assert order.index("reconcile_mcp_pins") == order.index("reconcile_mcp_env") + 1


# --- manifest pins + dispatch link ------------------------------------------------- #
M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))


def test_every_package_launched_mcp_server_has_an_exact_pin():
    loose = []
    for s in M["mcp_servers"]:
        spec = doctor_mcp.npx_spec(" ".join(s["add"]))
        if spec and not (doctor_mcp.spec_version(spec) or "")[:1].isdigit():
            loose.append(f"{s['name']}:{spec}")
    assert not loose, loose


def test_lean_ctx_npm_install_is_pinned():
    dep = next(d for d in M["deps"] if d["id"] == "lean-ctx")
    assert any(a.startswith("lean-ctx-bin@") and a.split("@")[1][:1].isdigit() for a in dep["install"])


def test_dispatch_has_one_async_low_priority_selfheal_link():
    cfg = json.loads((_ROOT / "hooks" / "dispatch.config.json").read_text(encoding="utf-8"))
    links = [ln for ln in cfg["chains"]["session-start"] if "selfheal-daily" in " ".join(ln.get("cmd", []))]
    assert len(links) == 1
    ln = links[0]
    assert ln["type"] == "exec" and ln["async"] is True and ln["enabled"] is True
    assert ln["timeout_ms"] >= 5000 and (_ROOT / "hooks" / "tools" / "selfheal-daily.py").exists()
    ids = [x["id"] for x in cfg["chains"]["session-start"]]
    assert ids.index(ln["id"]) > ids.index("state-cleanup")
