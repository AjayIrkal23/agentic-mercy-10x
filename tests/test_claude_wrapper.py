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
    size = json.loads(sfile.read_text(encoding="utf-8"))["workflowSizeGuideline"]
    assert size == _meminfo_size()
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


@pytest.mark.parametrize("shell,rc,which", [("zsh", ".zshrc", "whence -p claude"), ("bash", ".bashrc", "type -P claude")])
def test_shell_rc_resolves_the_launcher(box, shell, rc, which):
    tmp, env = box
    real_rc = Path.home() / rc
    if not shutil.which(shell) or not real_rc.is_file():
        pytest.skip(f"{shell} or ~/{rc} missing")
    shutil.copy(real_rc, tmp / rc)
    with open(tmp / rc, "a", encoding="utf-8") as fh:
        fh.write(f'\n# >>> claude-workbench >>>\nexport PATH="{ROOT / "bin"}:$PATH"\n# <<< claude-workbench <<<\n')
    fake = tmp / "fakebin" / "claude"
    p = subprocess.run([shell, "-ic", f"type claude; {which}; claude --version"], capture_output=True, text=True,
                       timeout=30, env={**env, "PATH": f"{tmp / 'fakebin'}:/usr/bin:/bin", "CLAUDE_REAL_BIN": str(fake)},
                       stdin=subprocess.DEVNULL)
    out = p.stdout
    real_line = next((x for x in out.splitlines() if x.startswith("REAL")), "")
    assert str(ROOT / "bin" / "claude") in out and real_line.endswith(" --version"), (out, p.stderr[-500:])
    if "alias claude" in real_rc.read_text(encoding="utf-8", errors="replace"):
        assert "claude is an alias" in out or "claude is aliased" in out


def test_lint():
    assert subprocess.run(["bash", "-n", str(WRAPPER), str(TMUXW)]).returncode == 0
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck absent")
    p = subprocess.run(["shellcheck", "-S", "warning", str(WRAPPER), str(TMUXW)], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout
