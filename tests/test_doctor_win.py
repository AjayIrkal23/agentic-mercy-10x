"""W7 (Windows parity v4.1): doctor rows on Windows, tested on every OS.

secret-perms reads the DACL as SDDL (SIDs, no locale), junctions count as links, the rendered
hook command is run once, the doctor probes 127.0.0.1. (The mods-runtime and encoding half is
in test_doctor_win_mods.py.) icacls and the shell are injected, never the box's own."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import doctor_host  # noqa: E402
import doctor_hook  # noqa: E402
import links  # noqa: E402

ME = "S-1-5-21-1-2-3-1000"
OTHER = "S-1-5-21-9-9-9-1004"
FLAGGED = f".env\nD:AI(A;ID;0x1200a9;;;{OTHER})(A;ID;FA;;;{ME})(A;ID;FA;;;SY)(A;ID;FA;;;BA)"
CLEAN = f".claude.json\nD:(A;ID;FA;;;SY)(A;ID;FA;;;BA)(A;ID;FA;;;{ME})"


def _tree(tmp_path, names=(".env", "settings.user.json")):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text("{}", encoding="utf-8")
    root = tmp_path / "claude"
    root.mkdir()
    for n in names:
        (root / n).write_text("x", encoding="utf-8")
    return root, home


def _perms(root, home, sddl, **kw):
    seen: list = []

    def save(p):
        seen.append(Path(p).name)
        return sddl(Path(p).name) if callable(sddl) else sddl
    st, det = doctor_host.check_secret_perms(
        root, is_windows=True, icacls_save=save, user_sid=lambda: ME, home=home, **kw)
    return st, det, seen


# --- A6-01: secret-perms from SDDL ------------------------------------------------- #
def test_an_extra_sid_with_read_access_warns_and_names_the_sid_and_the_fix(tmp_path):
    root, home = _tree(tmp_path)
    st, det, _ = _perms(root, home, FLAGGED)
    assert st == "WARN" and OTHER in det
    for part in ("/inheritance:r", "/grant:r", "*S-1-5-18:F", "*S-1-5-32-544:F", f"*{ME}:F"):
        assert part in det


def test_owner_system_and_administrators_only_passes(tmp_path):
    root, home = _tree(tmp_path)
    st, det, seen = _perms(root, home, CLEAN)
    assert st == "PASS", det
    assert ".claude.json" in seen and ".env" in seen and "settings.user.json" in seen


@pytest.mark.parametrize("ace", [
    "(A;;FR;;;WD)", "(A;;0x1200a9;;;BU)", "(A;;GR;;;AU)", f"(A;;GA;;;{OTHER})",
    "(A;;0x1;;;S-1-5-32-545)", "(A;;FRFX;;;IU)",
])
def test_everyone_users_and_other_readers_are_flagged(tmp_path, ace):
    root, home = _tree(tmp_path, names=(".env",))
    st, det, _ = _perms(root, home, f"D:{ace}(A;;FA;;;{ME})")
    assert st == "WARN", det


@pytest.mark.parametrize("rights", ["CC", "CCSWLORC", "CCDCLCSWRPWPDTLOCRSDRCWDWO", "LOCC", "RCCC"])
def test_sddl_letter_pairs_that_grant_read_data_are_flagged(rights):
    """SANTA1C-04: Windows renders FILE_READ_DATA (0x1) as `CC`, 0x20089 as `CCSWLORC`, 0xF01FF as the long form."""
    assert doctor_host._readers(f"D:(A;;{rights};;;WD)", ME) == ["Everyone"]
    assert doctor_host._readers(f"D:(A;;{rights};;;BU)(A;;FA;;;{ME})", ME) == ["Users"]


@pytest.mark.parametrize("rights", ["SWLORC", "DCWPRP", "SDWDWO", "FW", "FX", ""])
def test_sddl_letter_pairs_without_read_data_stay_clean(rights):
    assert doctor_host._readers(f"D:(A;;{rights};;;WD)", ME) == []


def test_an_unknown_rights_token_counts_as_read_rather_than_pass():
    """`RX` is icacls display text, never an SDDL token: it is not in the table, so it is flagged like an
    unparseable hex mask instead of being trusted."""
    assert "RX" not in doctor_host._RIGHTS
    assert doctor_host._readers("D:(A;;RX;;;BU)", ME) == ["Users"]
    assert doctor_host._readers("D:(A;;FRX;;;BU)", ME) == ["Users"]  # odd length: the stray letter


def test_a_null_dacl_means_everyone_has_full_access():
    """P5: `D:NO_ACCESS_CONTROL` has no ACE at all, so the ACE scan alone said PASS."""
    assert doctor_host._readers("D:NO_ACCESS_CONTROL", ME) == ["Everyone"]


def test_the_builtin_administrator_alias_is_as_trusted_as_the_group():
    assert doctor_host._readers(f"D:(A;;FA;;;LA)(A;;FA;;;{ME})", ME) == []


@pytest.mark.parametrize("name", ["settings.json", "settings.json.pre-install", "settings.json.bak-20261006T010203Z",
                                  "settings.user.json"])
def test_settings_files_are_secret_adjacent_too(tmp_path, name):
    """SECURITY-1b: they can hold provider keys (env, apiKeyHelper), and `.pre-install` / `.bak-*` copy them."""
    root, home = _tree(tmp_path, names=(name,))
    st, det, seen = _perms(root, home, f"D:(A;;FR;;;WD)(A;;FA;;;{ME})")
    assert name in seen and st == "WARN" and name in det


@pytest.mark.parametrize("ace", ["(D;;FR;;;WD)", "(A;;0x100116;;;AU)", "(A;;FA;;;CO)", "(A;;FA;;;S-1-5-18)"])
def test_deny_only_write_only_and_system_aces_are_clean(tmp_path, ace):
    root, home = _tree(tmp_path, names=(".env",))
    st, det, _ = _perms(root, home, f"D:{ace}(A;;FA;;;{ME})")
    assert st == "PASS", det


def test_an_unreadable_acl_warns_and_never_passes(tmp_path):
    root, home = _tree(tmp_path, names=(".env",))
    st, det, _ = _perms(root, home, lambda name: None if name == ".env" else CLEAN)
    assert st == "WARN" and "could not read ACL" in det and ".env" in det


def test_an_unknown_current_user_warns_instead_of_flagging_every_file(tmp_path):
    root, home = _tree(tmp_path, names=(".env",))
    st, det = doctor_host.check_secret_perms(
        root, is_windows=True, icacls_save=lambda p: CLEAN, user_sid=lambda: "", home=home)
    assert st == "WARN" and "user SID" in det


def test_sddl_decodes_utf16le_with_and_without_a_bom():
    raw = CLEAN.encode("utf-16-le")
    assert doctor_host.decode_sddl(raw) == CLEAN
    assert doctor_host.decode_sddl(b"\xff\xfe" + raw) == CLEAN


def test_the_branch_follows_platform_is_windows(tmp_path, monkeypatch):
    root, home = _tree(tmp_path, names=(".env",))
    calls: list = []
    monkeypatch.setattr(doctor_host.plat, "IS_WINDOWS", True)
    doctor_host.check_secret_perms(root, icacls_save=lambda p: calls.append(p) or CLEAN,
                                   user_sid=lambda: ME, home=home)
    assert len(calls) == 2  # .env + ~/.claude.json
    calls.clear()
    monkeypatch.setattr(doctor_host.plat, "IS_WINDOWS", False)
    doctor_host.check_secret_perms(root, icacls_save=lambda p: calls.append(p) or CLEAN,
                                   user_sid=lambda: ME, home=home)
    assert calls == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes")
def test_dot_claude_json_is_checked_on_posix_too(tmp_path):
    root, home = _tree(tmp_path, names=())
    (home / ".claude.json").chmod(0o600)
    assert doctor_host.check_secret_perms(root, is_windows=False, home=home)[0] == "PASS"
    (home / ".claude.json").chmod(0o644)
    st, det = doctor_host.check_secret_perms(root, is_windows=False, home=home)
    assert st == "WARN" and ".claude.json" in det


# --- A6-10: junctions are links too ------------------------------------------------- #
def test_find_symlinks_lists_an_ntfs_junction(tmp_path, monkeypatch):
    (tmp_path / "plain").mkdir()
    (tmp_path / "junc").mkdir()
    monkeypatch.setattr(os.path, "isjunction", lambda p: Path(p).name == "junc", raising=False)
    assert links.find_symlinks(tmp_path) == [tmp_path / "junc"]


# --- A6-12: the rendered hook command runs --------------------------------------- #
def _settings(root, command="py -3 /x/hooks/dispatch.py pre-tool-use"):
    (root / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]}]}}), encoding="utf-8")
    return command


def test_hook_command_passes_on_json_and_fails_on_a_missing_interpreter(tmp_path):
    cmd = _settings(tmp_path)
    got: list = []

    def ok(command, payload, env):
        got.append((command, json.loads(payload), env))
        return 0, "{}"
    assert doctor_hook.check_hook_command(tmp_path, False, run=ok)[0] == "PASS"
    command, payload, env = got[0]
    assert command == cmd and payload["hook_event_name"] == "PreToolUse" and payload["tool_name"] == "Bash"
    assert env["CLAUDE_HOOK_DOCTOR"] == "1"
    for var in ("CLAUDE_HOOK_STATE_DIR", "CLAUDE_HOOK_TELEMETRY_DIR", "CLAUDE_HOOK_DOTSTATE_DIR"):
        assert env[var] and not Path(env[var]).is_relative_to(tmp_path), var
    assert doctor_hook.check_hook_command(tmp_path, False, run=lambda *a: (127, ""))[0] == "FAIL"
    assert doctor_hook.check_hook_command(tmp_path, False, run=lambda *a: (0, "not json"))[0] == "FAIL"
    assert doctor_hook.check_hook_command(tmp_path, False, run=lambda *a: (0, ""))[0] == "FAIL"


def test_hook_command_skips_without_settings_and_runs_under_ci_when_one_exists(tmp_path):
    """A6v2-04: the CI rehearsal renders a settings.json, so --ci still proves `py -3` under the hook shell."""
    never = lambda *a: pytest.fail("must not run")  # noqa: E731
    assert doctor_hook.check_hook_command(tmp_path, False, run=never)[0] == "SKIP"
    assert doctor_hook.check_hook_command(tmp_path, True, run=never)[0] == "SKIP"
    _settings(tmp_path)
    assert doctor_hook.check_hook_command(tmp_path, True, run=lambda *a: (0, "{}"))[0] == "PASS"
    assert doctor_hook.check_hook_command(tmp_path, True, run=lambda *a: (127, ""))[0] == "FAIL"


def test_hook_command_fails_when_settings_carry_no_pre_tool_use_command(tmp_path):
    (tmp_path / "settings.json").write_text("{}", encoding="utf-8")
    assert doctor_hook.check_hook_command(tmp_path, False, run=lambda *a: (0, "{}"))[0] == "FAIL"


def test_hook_command_default_runner_uses_a_shell_stdin_and_redirected_state(tmp_path):
    script = tmp_path / "hook.py"
    script.write_text("import json, os, sys\njson.load(sys.stdin)\n"
                      "print(json.dumps({'doctor': os.environ.get('CLAUDE_HOOK_DOCTOR')}))\n", encoding="utf-8")
    _settings(tmp_path, f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}"')
    st, det = doctor_hook.check_hook_command(tmp_path, False)
    assert st == "PASS", det


def _fake_git(tmp_path, with_bash=True):
    """`<root>/cmd/git.exe` beside `<root>/bin/bash.exe`: the Git for Windows layout."""
    (tmp_path / "git" / "cmd").mkdir(parents=True)
    (tmp_path / "git" / "cmd" / "git.exe").write_text("", encoding="utf-8")
    if with_bash:
        (tmp_path / "git" / "bin").mkdir()
        (tmp_path / "git" / "bin" / "bash.exe").write_text("", encoding="utf-8")
    return tmp_path / "git" / "cmd" / "git.exe", tmp_path / "git" / "bin" / "bash.exe"


def _spy_shell(monkeypatch, tmp_path, *, env_bash=None, git="none", windows=True):
    """Call `doctor_hook._shell` with subprocess.run recorded; the argv Claude Code's shell would get."""
    seen: list = []
    monkeypatch.setattr(doctor_hook.plat, "IS_WINDOWS", windows)
    monkeypatch.setattr(doctor_hook.subprocess, "run", lambda argv, **kw: seen.append((argv, kw)) or
                        subprocess.CompletedProcess(argv, 0, "{}", ""))
    monkeypatch.setattr(doctor_hook.shutil, "which", lambda n, *a, **k: git if n == "git" and git != "none" else None)
    if env_bash is None:
        monkeypatch.delenv("CLAUDE_CODE_GIT_BASH_PATH", raising=False)
    else:
        monkeypatch.setenv("CLAUDE_CODE_GIT_BASH_PATH", str(env_bash))
    doctor_hook._shell("py -3 x.py", "{}", {})
    return seen[0]


def test_hook_command_runs_under_git_bash_found_beside_git_when_the_variable_is_unset(monkeypatch, tmp_path):
    """P4: Claude Code runs hooks under Git Bash on Windows; a bash-only breakage (a backslash path in the
    command) must show in the row, so fall back to `<git>/../../bin/bash.exe` as doctor_basetools does."""
    git, bash = _fake_git(tmp_path)
    argv, kw = _spy_shell(monkeypatch, tmp_path, git=str(git))
    assert argv == [str(bash), "-c", "py -3 x.py"] and kw["shell"] is False


def test_hook_command_prefers_the_named_bash_over_the_git_one(monkeypatch, tmp_path):
    git, _bash = _fake_git(tmp_path)
    named = tmp_path / "other-bash.exe"
    named.write_text("", encoding="utf-8")
    assert _spy_shell(monkeypatch, tmp_path, env_bash=named, git=str(git))[0][0] == str(named)


def test_hook_command_falls_back_to_the_shell_without_any_bash(monkeypatch, tmp_path):
    git, _bash = _fake_git(tmp_path, with_bash=False)
    argv, kw = _spy_shell(monkeypatch, tmp_path, git=str(git))
    assert argv == "py -3 x.py" and kw["shell"] is True
    argv, kw = _spy_shell(monkeypatch, tmp_path, env_bash=tmp_path / "missing.exe")
    assert argv == "py -3 x.py" and kw["shell"] is True


def test_hook_command_uses_the_posix_shell_off_windows(monkeypatch, tmp_path):
    git, _bash = _fake_git(tmp_path)
    argv, kw = _spy_shell(monkeypatch, tmp_path, git=str(git), windows=False)
    assert argv == "py -3 x.py" and kw["shell"] is True  # `sh -c`, as Claude Code's hook runner


# --- SEC1-04: icacls / whoami come from %SystemRoot%\System32, never a PATH or cwd lookup ---- #
def _spy_run(monkeypatch, stdout=""):
    seen: list = []

    def run(argv, **kw):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 1, stdout, "")
    monkeypatch.setattr(doctor_host.subprocess, "run", run)
    return seen


def test_icacls_and_whoami_run_from_system32(monkeypatch, tmp_path):
    monkeypatch.setenv("SystemRoot", str(tmp_path / "win"))
    seen = _spy_run(monkeypatch, "x,S-1-5-21-1-2-3-1000\n")
    doctor_host._icacls_save(tmp_path / "f")
    doctor_host._user_sid()
    sys32 = tmp_path / "win" / "System32"
    assert [Path(a[0]) for a in seen] == [sys32 / "icacls.exe", sys32 / "whoami.exe"]


def test_icacls_and_whoami_fall_back_to_the_bare_name_without_systemroot(monkeypatch, tmp_path):
    monkeypatch.delenv("SystemRoot", raising=False)
    monkeypatch.delenv("SYSTEMROOT", raising=False)  # Windows env names are case-insensitive
    seen = _spy_run(monkeypatch)
    doctor_host._icacls_save(tmp_path / "f")
    doctor_host._user_sid()
    assert [a[0] for a in seen] == ["icacls", "whoami"]


# --- A6-08: the doctor probes 127.0.0.1 (IPv6 `localhost` costs 2 s on Windows) ---- #
def test_the_manifest_ollama_probe_uses_the_ipv4_literal():
    m = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    assert urlparse(m["doctor_probes"]["ollama"]["url"]).hostname == "127.0.0.1"
