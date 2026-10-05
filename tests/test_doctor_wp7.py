"""Doctor rows added or hardened by WP7 (audit 2026-10-05): mods version policy and
runtime (A-06/I-07, I-04), MCP roster extras/pins/deprecation (I-09, G-04, I-12, G-01),
installed plugins (I-10), secret-file modes (J-06), lean-ctx zero-injection (G-13) and
the rows that could not fail (I-11). Every branch runs on injected inputs: no claude
CLI, no network, no live ~/.claude.json."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import doctor_checks  # noqa: E402
import doctor_host  # noqa: E402
import doctor_mcp  # noqa: E402
import doctor_mods  # noqa: E402


# --- A-06 / I-07: the pin is a minimum within the verified minor ------------------- #
@pytest.mark.parametrize("have,want,status", [
    ("2.1.288", "2.1.288", "PASS"), ("2.1.289", "2.1.288", "PASS"),
    ("2.1.287", "2.1.288", "WARN"), ("2.2.0", "2.1.288", "WARN"), ("", "2.1.288", "PASS"),
])
def test_mods_version_policy(have, want, status):
    assert doctor_mods.version_status(have, want)[0] == status


# --- I-04: tsc + claude plugin test --------------------------------------------- #
def _mod_root(tmp_path, types=True):
    mod = tmp_path / "mods" / "m"
    (mod / ".claude-plugin" / ("types" if types else "x")).mkdir(parents=True)
    (mod / "tsconfig.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _runner(results: dict):
    calls = []

    def run(argv):
        calls.append(argv)
        key = "tsc" if "tsc" in Path(argv[0]).name else "test"
        return results[key]
    run.calls = calls
    return run


def _which(*present):
    return lambda name: f"/bin/{name}" if name in present else None


def test_mods_runtime_passes_when_tsc_and_tests_pass(tmp_path):
    run = _runner({"tsc": (0, ""), "test": (0, "68 pass")})
    st, det = doctor_mods.check_mods_runtime(_mod_root(tmp_path), ["m"], False, _which("tsc", "claude"), run)
    assert st == "PASS" and len(run.calls) == 2, det


def test_mods_runtime_fails_on_a_type_error(tmp_path):
    run = _runner({"tsc": (2, "x.ts(1,1): error TS2322"), "test": (0, "")})
    assert doctor_mods.check_mods_runtime(_mod_root(tmp_path), ["m"], False, _which("tsc", "claude"), run)[0] == "FAIL"


def test_mods_runtime_fails_on_a_failing_test(tmp_path):
    run = _runner({"tsc": (0, ""), "test": (1, "1 fail")})
    assert doctor_mods.check_mods_runtime(_mod_root(tmp_path), ["m"], False, _which("tsc", "claude"), run)[0] == "FAIL"


def test_mods_runtime_warns_when_the_rollout_switch_is_off(tmp_path):
    run = _runner({"tsc": (2, "error TS"), "test": (1, "hooks modules are turned off")})
    assert doctor_mods.check_mods_runtime(_mod_root(tmp_path), ["m"], False, _which("tsc", "claude"), run)[0] == "WARN"


def test_mods_runtime_warns_without_tools_and_skips_in_ci(tmp_path):
    root = _mod_root(tmp_path, types=False)
    assert doctor_mods.check_mods_runtime(root, ["m"], False, _which(), _runner({}))[0] == "WARN"
    assert doctor_mods.check_mods_runtime(root, ["m"], True, _which("tsc", "claude"), _runner({}))[0] == "SKIP"


# --- I-09 / G-04 / I-12 / G-01: roster extras, pin drift, deprecation ------------ #
def _manifest(*servers):
    return {"mcp_servers": list(servers), "doctor_probes": {"mcp_roster": [s["name"] for s in servers]}}


def _srv(name, pkg, **kw):
    return {"name": name, "add": ["claude", "mcp", "add", name, "--", "npx", "-y", pkg], **kw}


def test_npx_spec_reads_plain_scoped_and_shell_forms():
    assert doctor_mcp.npx_spec("npx -y @a/b@1.2.3 mcp") == "@a/b@1.2.3"
    assert doctor_mcp.npx_spec("npx -y plain") == "plain"
    assert doctor_mcp.npx_spec("sh -c T=$(gh auth token) exec npx -y @x/y@2025.4.8") == "@x/y@2025.4.8"
    assert doctor_mcp.npx_spec("/usr/bin/semgrep mcp") is None


def test_roster_passes_when_live_matches_manifest():
    m = _manifest(_srv("a", "@a/a@1.0.0"))
    live = {"a": {"command": "npx", "args": ["-y", "@a/a@1.0.0"]}}
    assert doctor_mcp.roster_status(m, live, set())[0] == "PASS"


def test_roster_warns_on_an_extra_live_server():
    m = _manifest(_srv("a", "@a/a@1.0.0"))
    live = {"a": {"command": "npx", "args": ["-y", "@a/a@1.0.0"]}, "drawio": {"command": "npx", "args": ["-y", "@drawio/mcp"]}}
    st, det = doctor_mcp.roster_status(m, live, set())
    assert st == "WARN" and "drawio" in det


def test_roster_warns_on_pin_drift_and_never_prints_env():
    m = _manifest(_srv("a", "@a/a@1.0.1"))
    live = {"a": {"command": "npx", "args": ["-y", "@a/a@1.0.0"], "env": {"TOKEN": "s3cr3t"}}}
    st, det = doctor_mcp.roster_status(m, live, set())
    assert st == "WARN" and "1.0.0" in det and "1.0.1" in det and "s3cr3t" not in det


def test_roster_warns_on_a_deprecated_package():
    m = _manifest(_srv("gh", "@x/gh@1.0.0", deprecated="migrate to github/github-mcp-server"))
    live = {"gh": {"command": "npx", "args": ["-y", "@x/gh@1.0.0"]}}
    st, det = doctor_mcp.roster_status(m, live, set())
    assert st == "WARN" and "github-mcp-server" in det


def test_live_manifest_pins_every_npx_server():
    m = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    unpinned = []
    for s in m["mcp_servers"]:
        spec = doctor_mcp.npx_spec(" ".join(s["add"]))
        if spec and not doctor_mcp.spec_version(spec):
            unpinned.append(s["name"])
    assert not unpinned
    names = [s["name"] for s in m["mcp_servers"]]
    assert "drawio" in names and names == m["doctor_probes"]["mcp_roster"]
    assert next(s for s in m["mcp_servers"] if s["name"] == "github").get("deprecated")


# --- I-10: plugins installed + enabled ------------------------------------------ #
_DECL = [{"id": "a@m"}, {"id": "ponytail@ponytail", "mandatory": True}]


def test_plugins_installed_pass_warn_fail():
    ok = [{"id": "a@m", "enabled": True}, {"id": "ponytail@ponytail", "enabled": True}]
    assert doctor_host.plugins_status(_DECL, ok)[0] == "PASS"
    assert doctor_host.plugins_status(_DECL, [ok[1]])[0] == "WARN"
    assert doctor_host.plugins_status(_DECL, [ok[0]])[0] == "FAIL"
    assert doctor_host.plugins_status(_DECL, [ok[0], {"id": "ponytail@ponytail", "enabled": False}])[0] == "FAIL"
    assert doctor_host.plugins_status(_DECL, None)[0] == "SKIP"


# --- J-06: secret-adjacent files must not be group/world readable ---------------- #
@pytest.mark.skipif(os.name == "nt", reason="POSIX modes")
def test_secret_perms_warns_with_the_fix_command(tmp_path):
    for name in (".env", ".env.devpc", "CLAUDE.machines.local.md", "settings.user.json", "notes.md"):
        (tmp_path / name).write_text("x", encoding="utf-8")
        (tmp_path / name).chmod(0o600)
    assert doctor_host.check_secret_perms(tmp_path)[0] == "PASS"
    (tmp_path / "CLAUDE.machines.local.md").chmod(0o664)
    (tmp_path / "notes.md").chmod(0o664)
    st, det = doctor_host.check_secret_perms(tmp_path)
    assert st == "WARN" and "chmod 600" in det and "CLAUDE.machines.local.md" in det and "notes.md" not in det


# --- G-13: the zero-injection keys are asserted even if the manifest drops one --- #
def test_leanctx_floor_adds_dropped_zero_injection_keys():
    req = doctor_host.leanctx_required_with_floor({"top": {"shadow_mode": False}})
    assert req["top"]["rules_injection"] == "off" and req["setup"]["auto_inject_rules"] is False
    m = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))["leanctx_config"]
    for table, keys in doctor_host.ZERO_INJECTION.items():
        for k, v in keys.items():
            assert m[table][k] == v, (table, k)


# --- I-11: rows that could not fail ---------------------------------------------- #
def _rows():
    rows: list = []
    return rows, (lambda r, n, s, d: r.append((n, s, d)))


def test_palette_fails_on_an_empty_catalog(tmp_path):
    rows, row = _rows()
    doctor_checks.check_palette(rows, tmp_path, row, "PASS", "FAIL")
    assert rows[0][1] == "FAIL"


def test_fixtures_reject_a_tool_event_without_tool_input(tmp_path):
    d = tmp_path / "tests" / "fixtures" / "hook-events"
    d.mkdir(parents=True)
    (d / "a.json").write_text(json.dumps({"hook_event_name": "PreToolUse", "session_id": "s", "tool_name": "Bash"}))
    rows, row = _rows()
    doctor_checks.check_fixtures(rows, tmp_path, row, "PASS", "FAIL", "WARN")
    assert rows[0][1] == "FAIL"


def test_generated_drift_lines_become_a_warn():
    cp = subprocess.CompletedProcess([], 0, "drift: a: b (not in routing sources)\nok\n", "")
    assert doctor_checks.generated_status([("gen.py", cp)])[0] == "WARN"
    clean = subprocess.CompletedProcess([], 0, "ok\n", "")
    assert doctor_checks.generated_status([("gen.py", clean)])[0] == "PASS"
    bad = subprocess.CompletedProcess([], 1, "", "")
    assert doctor_checks.generated_status([("gen.py", bad)])[0] == "FAIL"


def _tokenized_root(tmp_path, script="hooks/dispatch.py"):
    (tmp_path / "installer").mkdir()
    (tmp_path / "installer" / "manifest.json").write_text("{}", encoding="utf-8")
    cmd = f"{{{{PYTHON}}}} {{{{CLAUDE_DIR}}}}/{script} pre-tool-use"
    (tmp_path / "settings.template.json").write_text(json.dumps({"hooks": {"x": cmd}}), encoding="utf-8")
    return tmp_path


def test_interpreters_fails_when_a_template_script_is_missing(tmp_path):
    root = _tokenized_root(tmp_path)
    st, det = doctor_checks.interpreters_status(root)
    assert st == "FAIL" and "hooks/dispatch.py" in det
    (root / "hooks").mkdir()
    (root / "hooks" / "dispatch.py").write_text("", encoding="utf-8")
    assert doctor_checks.interpreters_status(root)[0] == "PASS"


# --- G-13: unmanaged lean-ctx keys are surfaced (info, never a status change) ----- #
@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib (the note is empty on 3.10)")
def test_leanctx_note_names_unmanaged_shell_keys(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('shell_security = "off"\nshell_allowlist_extra = ["a", "b"]\nshadow_mode = false\n',
                   encoding="utf-8")
    note = doctor_host.leanctx_unmanaged_note(cfg, {"top": {"shadow_mode": False}})
    assert "shell_security=off" in note and "shell_allowlist_extra(2)" in note and "shadow_mode" not in note
    assert doctor_host.leanctx_unmanaged_note(tmp_path / "absent.toml", {}) == ""
