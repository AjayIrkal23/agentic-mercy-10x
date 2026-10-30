"""test_claude_wrapper.py — bin/claude (scope + launch caps) and bin/claude-tmux, with fake binaries."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "bin" / "claude"
TMUXW = ROOT / "bin" / "claude-tmux"
sys.path.insert(0, str(ROOT / "hooks"))
from lib import platform as plat  # noqa: E402

pytestmark = pytest.mark.skipif(plat.IS_WINDOWS or not shutil.which("bash"), reason="bash launcher, Linux only")

FAKE_CLAUDE = ("#!/usr/bin/env bash\nprintf '%s\\n' \"REAL $*\"\n"
               "env | grep -E '^(CLAUDE_WORKBENCH|CLAUDE_CODE_WORKFLOW_MAX|CLAUDE_CODE_MAX_CONCURRENT)' | sort\n")
FAKE_RUN = ("#!/usr/bin/env bash\nprintf 'SYSTEMD-RUN %s\\n' \"$*\"\n"
            "while [ $# -gt 0 ] && [ \"$1\" != -- ]; do shift; done\nshift\nexec \"$@\"\n")
FAKE_TMUX = "#!/usr/bin/env bash\nprintf 'TMUX %s\\n' \"$*\"\n"


def _exe(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def box(tmp_path):
    fb = tmp_path / "fakebin"
    _exe(fb / "claude", FAKE_CLAUDE)
    _exe(fb / "systemd-run", FAKE_RUN)
    _exe(fb / "tmux", FAKE_TMUX)
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "bus").write_text("", encoding="utf-8")
    env = {"PATH": f"{ROOT / 'bin'}:{fb}:/usr/bin:/bin", "HOME": str(tmp_path), "XDG_RUNTIME_DIR": str(tmp_path / "run")}
    return tmp_path, env


def _run(env, *argv, exe=WRAPPER, **extra):
    e = {k: v for k, v in {**env, **extra}.items() if v is not None}
    return subprocess.run([str(exe), *argv], capture_output=True, text=True, env=e, timeout=20)


def _meminfo_size() -> str:
    kb = next(int(line.split()[1]) for line in open("/proc/meminfo", encoding="ascii") if line.startswith("MemAvailable"))
    gib = kb // 1048576
    return "small" if gib < 8 else "medium" if gib < 16 else "large"


def test_interactive_runs_in_a_scope_with_caps(box):
    tmp, env = box
    out = _run(env, "--resume", "abc").stdout
    m = re.search(r"SYSTEMD-RUN --user --scope --quiet --collect --unit claude-(\d+) -p OOMPolicy=continue "
                  r"-p ManagedOOMPreference=avoid -p MemoryHigh=12G -- ", out)
    assert m, out
    pid = m[1]
    sfile = tmp / ".claude" / "state" / f"launch-settings-{pid}.json"
    assert f"REAL --settings {sfile} --resume abc" in out and "CLAUDE_WORKBENCH_SCOPE=1" in out
    wf = int(re.search(r"CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS=(\d+)", out)[1])
    sub = int(re.search(r"CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=(\d+)", out)[1])
    assert 1 <= wf <= 8 and 2 <= sub <= 6
    launch = json.loads(sfile.read_text(encoding="utf-8"))
    size = launch["workflowSizeGuideline"]
    assert size == _meminfo_size()
    # the launch-settings env block carries both caps (it beats the user settings file's env)
    assert launch["env"] == {"CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS": str(wf),
                             "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": str(sub)}
    caps = json.loads((tmp / ".claude" / "state" / "launch-caps" / f"{pid}.json").read_text(encoding="utf-8"))
    assert set(caps) == {"mem_available_mb", "workflow_agents", "subagents", "size_guideline", "ts"}
    gib = caps["mem_available_mb"] // 1024  # the wrapper's own reading: the formula, race-free
    assert (caps["workflow_agents"], caps["subagents"], caps["size_guideline"]) == \
        (wf, sub, size) == (min(8, max(1, gib // 3)), min(6, max(2, gib // 2)), size)


def test_memory_high_override_and_existing_settings_and_caps(box):
    tmp, env = box
    assert "MemoryHigh=8G" in _run(env, CLAUDE_SCOPE_MEMORY_HIGH="8G").stdout
    before = len(list((tmp / ".claude" / "state").glob("launch-settings-*")))
    out = _run(env, "--settings", "x.json", CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS="3").stdout
    real_line = next(x for x in out.splitlines() if x.startswith("REAL"))
    assert real_line == "REAL --settings x.json"
    assert len(list((tmp / ".claude" / "state").glob("launch-settings-*"))) == before
    assert "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS=3" in out


@pytest.mark.parametrize("argv,unattended", [(["-p", "hi"], True), (["--print", "hi"], True), (["--bare"], False)])
def test_print_and_bare_pass_through(box, argv, unattended):
    tmp, env = box
    out = _run(env, *argv).stdout
    assert "SYSTEMD-RUN" not in out and out.startswith("REAL " + " ".join(argv))
    assert ("CLAUDE_WORKBENCH_UNATTENDED=1" in out) is unattended
    assert "CLAUDE_WORKBENCH_SCOPE" not in out and "MAX_CONCURRENT" not in out
    assert not (tmp / ".claude" / "state" / "launch-caps").exists()


# --- final-fix 4: the tier's main model rides on --model when nothing else chose one ---------------
def _tier(tmp, main="opus", settings="{}"):
    (tmp / ".claude" / "state").mkdir(parents=True, exist_ok=True)
    (tmp / ".claude" / "state" / "plan-tier.json").write_text(
        json.dumps({"schema": 1, "tier": "max20", "main": main, "source": "credentials", "detected_at": 1}),
        encoding="utf-8")
    if settings is not None:
        (tmp / ".claude" / "settings.json").write_text(settings, encoding="utf-8")


def _real(out: str) -> str:
    return next((x for x in out.splitlines() if x.startswith("REAL")), "")


def test_tier_main_model_is_passed_when_nothing_else_sets_it(box):
    tmp, env = box
    _tier(tmp)
    assert "--model opus --resume abc" in _real(_run(env, "--resume", "abc").stdout)
    # the no-bus passthrough is interactive too
    assert _real(_run(env, XDG_RUNTIME_DIR=str(tmp / "nobus")).stdout) == "REAL --model opus"


def test_user_model_flag_wins(box):
    tmp, env = box
    _tier(tmp)
    for argv in (["--model", "sonnet"], ["--model=sonnet"]):
        line = _real(_run(env, *argv).stdout)
        assert line.endswith(" ".join(argv)) and "opus" not in line, line


def test_anthropic_model_env_wins(box):
    tmp, env = box
    _tier(tmp)
    assert "--model" not in _real(_run(env, ANTHROPIC_MODEL="claude-x").stdout)


@pytest.mark.parametrize("name", ["settings.json", "settings.local.json"])
def test_project_settings_model_wins(box, name):
    """SANTA-GATE 4: --model outranks every settings file, so a project's own model pick must stop the injection."""
    tmp, env = box
    _tier(tmp)
    proj = tmp / "proj" / "sub"
    (tmp / "proj" / ".claude").mkdir(parents=True)
    proj.mkdir()
    subprocess.run(["git", "init", "-q", str(tmp / "proj")], check=True, capture_output=True, timeout=20)
    (tmp / "proj" / ".claude" / name).write_text('{\n  "model": "sonnet"\n}\n', encoding="utf-8")
    out = subprocess.run([str(WRAPPER)], capture_output=True, text=True, env=env, cwd=proj, timeout=20)
    assert "--model" not in _real(out.stdout), out.stdout
    (tmp / "proj" / ".claude" / name).write_text('{\n  "theme": "dark"\n}\n', encoding="utf-8")
    out = subprocess.run([str(WRAPPER)], capture_output=True, text=True, env=env, cwd=proj, timeout=20)
    assert "--model opus" in _real(out.stdout), out.stdout


def test_saved_slash_model_choice_wins(box):
    tmp, env = box
    _tier(tmp, settings='{\n  "fallbackModel": ["sonnet"],\n  "model": "sonnet"\n}\n')
    assert "--model" not in _real(_run(env).stdout)
    _tier(tmp, settings='{\n  "fallbackModel": ["sonnet", "haiku"]\n}\n')  # fallbackModel is not a model pick
    assert "--model opus" in _real(_run(env).stdout)


def test_print_bare_nested_and_subcommands_get_no_model(box):
    tmp, env = box
    _tier(tmp)
    assert _real(_run(env, "-p", "x").stdout) == "REAL -p x"
    assert _real(_run(env, "--bare").stdout) == "REAL --bare"
    assert "--model" not in _real(_run(env, CLAUDECODE="1").stdout)
    assert "--model" not in _real(_run(env, "mcp", "list").stdout)  # subcommands take no session model
    for argv in (["logs", "abc"], ["stop", "x"], ["rm", "x"], ["attach", "x"], ["respawn", "x"],
                 ["purge", "."], ["agents"], ["kill", "x"]):
        assert "--model" not in _real(_run(env, *argv).stdout), argv


def _real_claude() -> str | None:
    """The real CLI on PATH, never this launcher (the fixture and ~/.claude/bin put bin/ first)."""
    import os  # noqa: PLC0415
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = shutil.which("claude", path=d) if d else None
        if not cand:
            continue
        with open(os.path.realpath(cand), "rb") as fh:
            if b"agentic-mercy oomguard launcher" not in fh.read(512):
                return cand
    return None


@pytest.mark.skipif(_real_claude() is None, reason="no real claude binary on PATH")
def test_subcommand_list_matches_the_real_cli():
    """Rot guard: every `claude --help` subcommand is in the launcher's no-model case branch."""
    out = subprocess.run([_real_claude(), "--help"], capture_output=True, text=True, timeout=60).stdout
    cmds = out.split("Commands:", 1)[1] if "Commands:" in out else ""
    words = {w for line in cmds.splitlines() if re.match(r"^  [a-z]", line)
             for w in line.split()[0].split("|")} - {"help"}
    assert words, out[-500:]
    branch = re.search(r'case "\$\{1:-\}" in[^\n]*\n\s*([^)]+)\)', WRAPPER.read_text(encoding="utf-8"))
    listed = set(branch[1].split("|")) if branch else set()
    assert words <= listed, sorted(words - listed)


def test_stale_plan_tier_is_redetected_from_newer_credentials(box):
    tmp, env = box
    _tier(tmp)  # max20 / opus, detected long ago
    (tmp / ".claude" / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"subscriptionType": "pro", "rateLimitTier": "default_claude_pro"}}),
        encoding="utf-8")
    state = tmp / ".claude" / "state"
    # the state-dir env keeps the detector from spawning a render
    out = _real(_run(env, CLAUDE_HOOK_STATE_DIR=str(state)).stdout)
    assert "--model sonnet" in out and "opus" not in out, out
    assert json.loads((state / "plan-tier.json").read_text(encoding="utf-8"))["tier"] == "pro"


def test_missing_plan_tier_or_main_adds_nothing(box):
    tmp, env = box
    assert "--model" not in _real(_run(env).stdout)
    (tmp / ".claude" / "state").mkdir(parents=True, exist_ok=True)
    (tmp / ".claude" / "state" / "plan-tier.json").write_text('{"schema": 1, "tier": "max20"}', encoding="utf-8")
    assert "--model" not in _real(_run(env).stdout)


def test_print_argv_shows_the_decision_without_side_effects(box):
    tmp, env = box
    _tier(tmp)
    out = _run(env, "--version", CLAUDE_LAUNCHER_PRINT_ARGV="1").stdout.splitlines()
    assert out[1:] == ["--model", "opus", "--version"] and out[0].endswith("/fakebin/claude"), out
    assert not (tmp / ".claude" / "state" / "launch-caps").exists()
    assert "SYSTEMD-RUN" not in "\n".join(out)


def test_nested_no_bus_no_systemd_run_pass_through(box):
    tmp, env = box
    assert "SYSTEMD-RUN" not in _run(env, CLAUDECODE="1").stdout
    assert "SYSTEMD-RUN" not in _run(env, CLAUDE_WORKBENCH_SCOPE="1").stdout
    assert "SYSTEMD-RUN" not in _run(env, XDG_RUNTIME_DIR=str(tmp / "nobus")).stdout
    (tmp / "fakebin" / "systemd-run").unlink()
    shbin = tmp / "shbin"  # bash and the few tools the wrapper reads with, but no systemd-run
    shbin.mkdir()
    for tool in ("bash", "readlink", "head", "grep"):
        if shutil.which(tool):
            (shbin / tool).symlink_to(shutil.which(tool))
    p = _run(env, PATH=f"{ROOT / 'bin'}:{tmp / 'fakebin'}:{shbin}")
    assert "SYSTEMD-RUN" not in p.stdout and p.stdout.startswith("REAL")


def test_real_bin_env_and_missing_real(box):
    tmp, env = box
    alt = _exe(tmp / "alt" / "other", "#!/usr/bin/env bash\necho ALT \"$@\"\n")
    assert _run(env, "-p", "x", PATH=f"{ROOT / 'bin'}:/usr/bin:/bin", CLAUDE_REAL_BIN=str(alt)).stdout.startswith("ALT -p x")
    p = _run(env, PATH=f"{ROOT / 'bin'}:/usr/bin:/bin")
    if shutil.which("claude", path="/usr/bin:/bin"):
        pytest.skip("a system claude exists in /usr/bin")
    assert p.returncode == 127 and "claude: real binary not found" in p.stderr


def test_never_execs_a_copy_of_itself(box):
    tmp, env = box
    copy = tmp / "copybin" / "claude"
    copy.parent.mkdir()
    shutil.copy(WRAPPER, copy)
    copy.chmod(0o755)
    p = _run(env, "-p", "x", PATH=f"{copy.parent}:{ROOT / 'bin'}:{tmp / 'fakebin'}:/usr/bin:/bin")
    assert p.returncode == 0 and "REAL -p x" in p.stdout


def test_claude_tmux(box):
    tmp, env = box
    out = _run(env, "new", "-s", "w", exe=TMUXW).stdout
    assert re.search(r"SYSTEMD-RUN --user --scope --quiet --collect --unit tmux-claude-\d+ -p OOMPolicy=continue "
                     r"-p ManagedOOMPreference=omit -- tmux new -s w", out) and "TMUX new -s w" in out
    for extra in ({"CLAUDE_WORKBENCH_SCOPE": "1"}, {"XDG_RUNTIME_DIR": str(tmp / "nobus")}):
        out = _run(env, "ls", exe=TMUXW, **extra).stdout
        assert out == "TMUX ls\n"


@pytest.mark.parametrize("shell,rc,which,flag", [("zsh", ".zshrc", "whence -p claude", "-ic"),
                                                  ("bash", ".bashrc", "type -P claude", "-ic"),
                                                  ("bash", ".profile", "type -P claude", "-lc")])
def test_shell_rc_resolves_the_launcher(box, shell, rc, which, flag):
    tmp, env = box
    real_rc = Path.home() / rc
    if not shutil.which(shell) or not real_rc.is_file():
        pytest.skip(f"{shell} or ~/{rc} missing")
    if rc == ".profile" and (Path.home() / ".bashrc").is_file():
        shutil.copy(Path.home() / ".bashrc", tmp / ".bashrc")  # ~/.profile sources it, then prepends ~/.local/bin
    shutil.copy(real_rc, tmp / rc)
    with open(tmp / rc, "a", encoding="utf-8") as fh:
        fh.write(f'\n# >>> claude-workbench >>>\nexport PATH="{ROOT / "bin"}:$PATH"\n# <<< claude-workbench <<<\n')
    fake = tmp / "fakebin" / "claude"
    p = subprocess.run([shell, flag, f"type claude; {which}; claude --version"], capture_output=True, text=True,
                       timeout=30, env={**env, "PATH": f"{tmp / 'fakebin'}:/usr/bin:/bin", "CLAUDE_REAL_BIN": str(fake)},
                       stdin=subprocess.DEVNULL)
    out = p.stdout
    real_line = next((x for x in out.splitlines() if x.startswith("REAL")), "")
    assert str(ROOT / "bin" / "claude") in out and real_line.endswith(" --version"), (out, p.stderr[-500:])
    if flag == "-ic" and "alias claude" in real_rc.read_text(encoding="utf-8", errors="replace"):
        assert "claude is an alias" in out or "claude is aliased" in out


def test_lint():
    assert subprocess.run(["bash", "-n", str(WRAPPER), str(TMUXW)]).returncode == 0
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck absent")
    p = subprocess.run(["shellcheck", "-S", "warning", str(WRAPPER), str(TMUXW)], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout
