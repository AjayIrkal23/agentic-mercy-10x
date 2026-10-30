#!/usr/bin/env python3
"""golive.py — the go-live runner (MERGE-PLAN R3.5). Every step exits; no servers; a failing step stops the run;
nothing is retried destructively; the first git write comes AFTER both secrets layers pass.
  golive.py --plan                       print the ordered steps, run nothing (any OS)
  golive.py --gitleaks-config            print the gitleaks TOML of the secrets step (GITLEAKS_CONFIG_TOML)
  golive.py --yes-automatic [--from ID] [--skip ID ...] [--worktree P] [--live P] [--branch ecc-merge] [--tag v4.3.0]
            [--packages P] [--remote-ssh URL] [--trailer LINE ...]
Refuses to run without --yes-automatic, on Windows, or when --skip names a secrets step.
State: state/golive/<ts>.jsonl (one row per step) and state/golive/<ts>-<id>.log (output tails).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "hooks"), str(ROOT / "installer")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from lib import platform as plat  # noqa: E402

_NO_SKIP = {"secrets-gitleaks", "secrets-known-values", "ownership", "pytest"}
_ZRAM_CONF = "[zram0]\nzram-size = ram / 2\ncompression-algorithm = zstd\n"
_SWAPOFF_MIN_MB = 14 * 1024
_COMMIT_MSG = "feat: ECC merge, OOM guard, plan-tier routing, workflows, {T}"
# gitleaks config, passed as GITLEAKS_CONFIG_TOML. `gitleaks dir` ignores .gitignore, so the gitignored caches
# and sidecars are excluded here; the rule allowlists match documentation placeholders and scrubber test inputs
# (verified 2026-10-30), by line so the stdin (diff) leg honours them too. Print it: golive.py --gitleaks-config.
GITLEAKS_TOML = """title = "dotclaude go-live"

[extend]
useDefault = true

[allowlist]
description = "gitignored caches, byte-code, sidecars"
paths = [
  '''(^|/)\\.cache/''',
  '''(^|/)__pycache__/''',
  '''\\.pyc$''',
  '''(^|/)node_modules/''',
  '''(^|/)\\.pytest_cache/''',
  '''(^|/)graphify-out/''',
  '''(^|/)\\.claude/''',
  '''(^|/)\\.git/''',
]

[[rules]]
id = "generic-api-key"
[[rules.allowlists]]
description = "placeholders: scrubber test input, a security guide's bad example, star-history embed tokens"
regexTarget = "line"
regexes = ['''abcdef123456789''', '''sk-proj-abc123\\.\\.\\.''', '''api\\.star-history\\.com/(chart|svg)\\?.*sealed_token=''']

[[rules]]
id = "curl-auth-header"
[[rules.allowlists]]
regexTarget = "line"
regexes = ['''Bearer abcdefghijklmnop''']
"""


@dataclass
class Step:
    id: str
    desc: str
    argv: list[list[str]] = field(default_factory=list)  # templates: {PY} {W} {L} {B} {T}
    timeout: int = 120
    cwd: str = "{W}"


STEPS: list[Step] = [
    Step("ownership", "every changed path belongs to its package (CLAUDE_ECC_PACKAGES)",
         [["{PY}", "{W}/scripts/check_ownership.py"]], 120),
    Step("pytest", "full suite in the worktree", [["{PY}", "-m", "pytest", "hooks/tests", "tests", "-q",
                                                   "-p", "no:cacheprovider"]], 1800),
    Step("validators", "link-doctor, skills, grep gates, import hygiene, mods, workflows, library index", [
        ["{PY}", "{W}/hooks/tools/link-doctor.py"],
        ["{PY}", "{W}/scripts/validate_skills.py"],
        ["{PY}", "{W}/scripts/grep_gates.py"],
        ["{PY}", "{W}/scripts/validate_imports.py", "library", "skills", "agents", "hooks", "docs", "--root", "{W}"],
        ["{PY}", "{W}/scripts/validate_mods.py", "--static", "--no-tests"],
        ["{PY}", "{W}/scripts/build_workflows.py", "--check"],
        ["{PY}", "{W}/scripts/build_library_index.py", "--check"]], 300),
    Step("render-check", "settings render dry-run + doctor --ci", [
        ["{PY}", "{W}/installer/render.py", "--dry-run"], ["{PY}", "{W}/installer/doctor.py", "--ci"]], 300),
    # the one generator allowed to dirty the tree at release: the shipped TOKEN-BUDGET.md is never stale
    # (before the secrets scans, so the regenerated doc is scanned too)
    Step("tokens", "regenerate docs/TOKEN-BUDGET.md from the release tree", [
        ["{PY}", "{W}/scripts/measure_context_cost.py", "--root", "{W}", "--write", "{W}/docs/TOKEN-BUDGET.md",
         "--counts", "--observed", "--mcp-eager"]], 120),
    Step("secrets-gitleaks", "secrets layer 1: gitleaks (GITLEAKS_TOML) over the tree and the branch diff (redacted)", [
        ["gitleaks", "dir", "{W}", "--redact", "--exit-code", "1", "--no-banner"],
        ["git", "-C", "{W}", "diff", "main...{B}"],
        ["gitleaks", "stdin", "--redact", "--exit-code", "1", "--no-banner"]], 600),
    Step("secrets-known-values", "secrets layer 2: known live values (key names only)", [
        ["{PY}", "{W}/scripts/secrets_scan.py", "--known-values", "--live", "--tree", "{W}", "--diff",
         "main...{B}"]], 300),
    Step("git-commit", "git add -A, then git commit with the release message (+ --trailer lines)", [
        ["git", "-C", "{W}", "add", "-A"],
        ["git", "-C", "{W}", "commit", "-q", "-m", "{MSG}"]], 120),
    Step("merge", "merge the branch into the live tree", [["git", "-C", "{L}", "merge", "--no-ff", "--no-edit",
                                                           "{B}"]], 120, "{L}"),
    Step("render-live", "render + doctor on the live tree", [
        ["{PY}", "{L}/installer/render.py"], ["{PY}", "{L}/installer/doctor.py"]], 900, "{L}"),
    # no live OOM kill here: the scope probe only proves the user manager accepts the policy (plan R3.4)
    Step("guard-checks", "OOM guard: DefaultOOMPolicy, memwatch runs the live tree, restore unit, scope probe, "
         "mem-pressure", [
        ["systemctl", "--user", "show", "-p", "DefaultOOMPolicy"],
        ["systemctl", "--user", "is-active", "claude-memwatch"],
        ["systemctl", "--user", "is-enabled", "claude-restore"],
        ["systemctl", "--user", "show", "claude-memwatch", "-p", "ExecStart"],
        ["systemd-run", "--user", "--scope", "--quiet", "--unit", "claude-test-scope-golive", "-p", "MemoryMax=300M",
         "-p", "OOMPolicy=continue", "{PY}", "-c", "pass"]], 120, "{L}"),
    Step("zram", "A5: zram swap via sudo askpass (skips without askpass or apt)", [
        ["sudo", "-A", "apt-get", "install", "-y", "systemd-zram-generator"]], 600, "{L}"),
    Step("mcp-remove", "A6: remove the higgsfield user MCP, openart must stay", [
        ["claude", "mcp", "remove", "higgsfield", "-s", "user"], ["claude", "mcp", "list"]], 120, "{L}"),
    Step("push", "tag + push (ssh remote when .github/workflows changed)", [
        ["git", "-C", "{L}", "tag", "-a", "{T}", "-m", "{T}"], ["git", "push", "origin", "main", "{T}"]], 300, "{L}"),
    Step("replica", "Windows replica sync (PASS/WARN/SKIP, never FAIL)", [["{PY}", "{L}/scripts/replica_sync.py"]],
         1200, "{L}"),
    Step("memory", "write the memory lines to state/golive (applied by the main session)", [], 0, "{L}"),
]


# ---------------------------------------------------------------- seams (monkeypatched by tests)

def _run(argv, *, cwd=None, timeout=None, env=None, input=None) -> subprocess.CompletedProcess:
    if input is None:
        return plat.run(argv, cwd=cwd, timeout=timeout, env=env)
    try:
        return subprocess.run(list(argv), cwd=cwd, timeout=timeout, env=env, input=input, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", check=False)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(argv, 124, exc.stdout or "", exc.stderr or "")
    except OSError as exc:
        return subprocess.CompletedProcess(argv, 127, "", str(exc))


def _script_exists(path: str) -> bool:
    return Path(path).is_file()


# ---------------------------------------------------------------- helpers

def _subs(a) -> dict[str, str]:
    return {"{PY}": plat.python_exe(), "{W}": str(a.worktree), "{L}": str(a.live), "{B}": a.branch,
            "{T}": a.tag, "{MSG}": (getattr(a, "message", None) or _COMMIT_MSG).replace("{T}", a.tag)}


def _resolve(tmpl: list[str], subs: dict[str, str]) -> list[str]:
    out = []
    for arg in tmpl:
        for k, v in subs.items():
            arg = arg.replace(k, v)
        out.append(arg)
    return out


def _push_argv(remote_https: str, workflows_changed: bool, tag: str = "v4.3.0", branch: str = "main",
               remote_ssh: str | None = None) -> list[str]:
    """Pushes that touch .github/workflows need the SSH remote (the HTTPS token lacks `workflow` scope)."""
    if not workflows_changed:
        return ["git", "push", "origin", branch, tag]
    if remote_ssh:
        return ["git", "push", remote_ssh, branch, tag]
    m = re.match(r"https://github\.com/([^/]+)/(.+?)(?:\.git)?/?$", remote_https.strip())
    url = f"git@github.com:{m.group(1)}/{m.group(2)}.git" if m else remote_https.strip()
    return ["git", "push", url, branch, tag]


_ZRAM_RESTART_HEADROOM_MB = 2048


def _crit_mb() -> int:
    """memwatch's crit line (hooks/memwatch.config.json tiers.crit.mem_available_mb); 3072 when unreadable."""
    try:
        cfg = json.loads((ROOT / "hooks" / "memwatch.config.json").read_text(encoding="utf-8"))
        return int(cfg["tiers"]["crit"]["mem_available_mb"])
    except (OSError, ValueError, KeyError, TypeError):
        return 3072


def _zram_used_mb(path: str = "/sys/block/zram0/mm_stat") -> int:
    """MB of data in zram0 (mm_stat orig_data_size): what a restart (swapoff first) must fit in RAM."""
    try:
        with open(path, encoding="ascii") as fh:
            return int(fh.read().split()[0]) // (1024 * 1024)
    except (OSError, ValueError, IndexError):
        return 0


def _zram_applied(zramctl_out: str) -> bool:
    """zramctl `NAME ALGORITHM DISKSIZE` shows the generator's algorithm (zstd), not the package default."""
    for line in zramctl_out.splitlines():
        f = line.split()
        if f and f[0].endswith("zram0"):
            return len(f) > 1 and f[1].strip("[]") == "zstd"
    return False


def _zram_deferred(used_mb: int, avail_mb: int) -> str:
    return (f"WARN(zram: config installed, restart deferred: {used_mb} MB in zram, {avail_mb} MB available; "
            f"needs > {used_mb + _crit_mb() + _ZRAM_RESTART_HEADROOM_MB} MB available to restart live, "
            "else it applies on the next reboot)")


def _zram_plan(askpass_exists: bool, apt: bool | None = None, mem_available_mb: int | None = None,
               conf_path: str = "{ZRAM_CONF}", zram_used_mb: int | None = None):
    """A skip tuple, or the sudo argv list. The unit is RESTARTED (`restart` starts an inactive unit; apt's
    postinst only daemon-reloads): always when zram0 holds no data, else only when its data fits in RAM and
    what is left stays 2 GB above memwatch's crit line (O8: else the sentinel kills during the apply; the
    conf applies on the next reboot); swapoff of /swap.img only when RAM headroom is large enough."""
    if not askpass_exists:
        return ("zram", "SKIP(no sudo askpass)")
    if apt is None:
        import ostools
        apt = ostools.apt_available()
    if not apt:
        return ("zram", "SKIP(no apt)")
    if mem_available_mb is None:
        probe = plat.mem_probe() or {}
        mem_available_mb = int(probe.get("mem_available_mb") or 0)  # plat.mem_probe() keys are MB
    if zram_used_mb is None:
        zram_used_mb = _zram_used_mb()
    steps = [["sudo", "-A", "apt-get", "install", "-y", "systemd-zram-generator"],
             ["sudo", "-A", "install", "-m644", conf_path, "/etc/systemd/zram-generator.conf"],
             ["sudo", "-A", "systemctl", "daemon-reload"]]
    # no data in zram0 (fresh host: the unit is not up yet, apt's postinst only daemon-reloads; or an empty
    # device): (re)starting costs no RAM, so always do it. A device with data restarts only when the data
    # fits back in RAM 2 GB above memwatch's crit line (O8); else the conf applies on the next reboot.
    if zram_used_mb == 0 or mem_available_mb > zram_used_mb + _crit_mb() + _ZRAM_RESTART_HEADROOM_MB:
        steps.append(["sudo", "-A", "systemctl", "restart", "systemd-zram-setup@zram0"])
    if mem_available_mb > _SWAPOFF_MIN_MB:
        steps.append(["sudo", "-A", "swapoff", "/swap.img"])
    return steps


def _memory_note(ts: str, date: str) -> Path:
    d = plat.state_dir() / "golive"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{ts}-memory.md"
    text = (f"decision:: [{date}] ECC merge v4.3.0 went live: library/ zero-cost vault, OOM guard tiers, "
            "plan-tier routing, workflows. why: one merged release, gated by the full suite and the "
            "two-layer secrets scan.\n"
            f"decision:: [{date}] go-live is automatic after the two-layer secrets scan (gitleaks + known "
            "values); ask-or-advise rule: only human-only steps are asked, once and batched.\n"
            "- [OOM guard](docs/OOM-GUARD.md) -> docs/OOM-GUARD.md\n")
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


class _Fail(Exception):
    def __init__(self, status: str, rc: int = 1, out: str = ""):
        super().__init__(status)
        self.status, self.rc, self.out = status, rc, out


def _call(argv, step: Step, subs, *, env=None, input=None) -> subprocess.CompletedProcess:
    for arg in argv[1:3]:
        if arg.endswith(".py") and os.path.isabs(arg) and not _script_exists(arg):
            raise _Fail(f"FAIL(missing {Path(arg).name})", 127)
    cp = _run(argv, cwd=_resolve([step.cwd], subs)[0], timeout=step.timeout or None, env=env, input=input)
    if cp.returncode == 124:
        raise _Fail("FAIL(timeout)", 124, (cp.stdout or "") + (cp.stderr or ""))
    return cp


def _out(cp) -> str:
    return (cp.stdout or "") + (cp.stderr or "")


def _check(cp, what: str = "") -> str:
    if cp.returncode != 0:
        raise _Fail(f"FAIL({what + ' ' if what else ''}rc={cp.returncode})", cp.returncode, _out(cp))
    return _out(cp)


# ---------------------------------------------------------------- step executors: (status, rc, output)

def _x_generic(step, subs, a):
    env = None
    if step.id == "ownership":
        env = {**os.environ, "CLAUDE_ECC_PACKAGES": str(a.packages)}
    elif step.id == "pytest":
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}  # no .pyc for gitleaks dir to trip on
        env.pop("CLAUDE_TEST_LIVE_OOM", None)  # the real OOM kill test stays opt-in by hand, never in go-live
    out = []
    for tmpl in step.argv:
        argv = _resolve(tmpl, subs)
        label = next((Path(x).name for x in argv[1:] if x.endswith(".py")), step.id)
        out.append(_check(_call(argv, step, subs, env=env), label))
    return "OK", 0, "\n".join(out)


def _gitleaks_bin(a) -> str | None:
    found = shutil.which("gitleaks")
    if found:
        return found
    try:
        import basetools
        manifest = json.loads((Path(a.worktree) / "installer" / "manifest.json").read_text(encoding="utf-8"))
        basetools.ensure_gitleaks(manifest, ci=False, dry_run=False)
    except Exception:  # noqa: BLE001  re-checked below; missing -> FAIL
        pass
    local = Path.home() / ".local" / "bin" / "gitleaks"
    return shutil.which("gitleaks") or (str(local) if local.is_file() else None)


def _x_gitleaks(step, subs, a):
    gl = _gitleaks_bin(a)
    if not gl:
        raise _Fail("FAIL(gitleaks missing: add user_space.gitleaks to installer/manifest.json)", 127)
    tree, diff, pipe = (_resolve(t, subs) for t in step.argv)
    env = {k: v for k, v in os.environ.items() if k != "GITLEAKS_CONFIG"}  # it would outrank the TOML below
    env["GITLEAKS_CONFIG_TOML"] = GITLEAKS_TOML
    out = _check(_call([gl, *tree[1:]], step, subs, env=env), "gitleaks dir")
    diff_text = _check(_call(diff, step, subs), "git diff")
    out += _check(_call([gl, *pipe[1:]], step, subs, env=env, input=diff_text), "gitleaks stdin")
    return "OK", 0, out


def _x_commit(step, subs, a):
    add, commit = (_resolve(t, subs) for t in step.argv)
    _check(_call(add, step, subs), "add")
    for t in a.trailer:
        commit += ["--trailer", t]
    cp = _call(commit, step, subs)
    if cp.returncode == 1 and "nothing to commit" in _out(cp):
        return "OK(nothing to commit)", 0, _out(cp)
    return "OK", 0, _check(cp, "commit")


def _x_guard(step, subs, a):
    show, active, enabled, execstart, scope = (_resolve(t, subs) for t in step.argv)
    out = _check(_call(show, step, subs), "show")
    if "continue" not in out:
        raise _Fail("FAIL(DefaultOOMPolicy is not continue)", 1, out)
    _check(_call(active, step, subs), "memwatch inactive")
    _check(_call(enabled, step, subs), "restore not enabled")
    unit = _check(_call(execstart, step, subs), "memwatch ExecStart")
    if str(a.live) not in unit:
        raise _Fail("FAIL(memwatch does not run the live tree)", 1, unit)
    _check(_call(scope, step, subs), "scope probe")
    try:
        json.loads((Path(a.live) / "state" / "mem-pressure.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _Fail(f"FAIL(mem-pressure.json: {type(exc).__name__})", 1) from exc
    return "OK", 0, out


def _x_zram(step, subs, a):
    askpass = Path(a.live) / "scripts" / "sudo-askpass.sh"
    plan = _zram_plan(askpass.is_file())
    if isinstance(plan, tuple):
        return plan[1], 0, ""
    env = {**os.environ, "SUDO_ASKPASS": str(askpass)}
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        conf = Path(tmp) / "zram-generator.conf"
        conf.write_text(_ZRAM_CONF, encoding="utf-8", newline="\n")
        for argv in plan:
            argv = [str(conf) if x == "{ZRAM_CONF}" else x for x in argv]
            if "swapoff" in argv and "zram0" not in _out(_call(["swapon", "--show"], step, subs)):
                out.append("swapoff skipped: zram0 not active")
                continue
            out.append(_check(_call(argv, step, subs, env=env), argv[2]))
    shown = _out(_call(["swapon", "--show"], step, subs))
    if "zram0" not in shown:
        raise _Fail("FAIL(zram0 not in swapon --show)", 1, shown)
    zc = _out(_call(["zramctl", "--noheadings", "--output", "NAME,ALGORITHM,DISKSIZE"], step, subs))
    if not _zram_applied(zc):
        probe = plat.mem_probe() or {}
        return _zram_deferred(_zram_used_mb(), int(probe.get("mem_available_mb") or 0)), 0, \
            "\n".join(out + [zc])
    return "OK", 0, "\n".join(out)


def _x_mcp(step, subs, a):
    remove, listing = (_resolve(t, subs) for t in step.argv)
    cp = _call(remove, step, subs)
    if cp.returncode != 0 and "not found" not in _out(cp).lower():
        raise _Fail(f"FAIL(mcp remove rc={cp.returncode})", cp.returncode, _out(cp))
    out = _check(_call(listing, step, subs), "mcp list")
    if "openart" not in out:
        raise _Fail("FAIL(openart missing after the removal)", 1, out)
    return "OK", 0, out


def _x_push(step, subs, a):
    tag_argv = _resolve(step.argv[0], subs)
    live = ["git", "-C", str(a.live)]
    have = _call(live + ["rev-parse", "-q", "--verify", f"refs/tags/{a.tag}^{{commit}}"], step, subs)
    if have.returncode == 0:
        main_sha = _call(live + ["rev-parse", "main"], step, subs).stdout.strip()
        if have.stdout.strip() != main_sha:
            raise _Fail(f"FAIL(tag {a.tag} exists on another commit)", 1)
    else:
        _check(_call(tag_argv, step, subs), "tag")
    changed = _call(live + ["diff", "--name-only", "main@{1}..main", "--", ".github/workflows"], step, subs)
    if changed.returncode != 0:
        changed = _call(live + ["log", "-1", "-m", "--name-only", "--format=", "main", "--", ".github/workflows"],
                        step, subs)
    remote = _call(live + ["remote", "get-url", "origin"], step, subs).stdout.strip()
    argv = _push_argv(remote, bool(changed.stdout.strip()), a.tag, "main", a.remote_ssh)
    return "OK", 0, _check(_call(argv, step, subs), "push")


def _x_replica(step, subs, a):
    argv = _resolve(step.argv[0], subs)
    if not _script_exists(argv[1]):
        return "WARN(replica_sync.py missing)", 0, ""
    cp = _call(argv, step, subs)
    last = (_out(cp).strip().splitlines() or [""])[-1]
    return (last if cp.returncode == 0 and last else f"WARN(rc={cp.returncode})"), 0, _out(cp)


_EXEC = {"secrets-gitleaks": _x_gitleaks, "git-commit": _x_commit, "guard-checks": _x_guard, "zram": _x_zram,
         "mcp-remove": _x_mcp, "push": _x_push, "replica": _x_replica}


# ---------------------------------------------------------------- plan + main

def _print_plan(a, subs, start: int, skip: set[str]) -> None:
    print(f"golive plan: branch {a.branch} -> live tree, tag {a.tag}")
    for i, st in enumerate(STEPS, 1):
        mark = "  SKIPPED(--from)" if i - 1 < start else ("  SKIPPED(--skip)" if st.id in skip else "")
        print(f"{i:02d} {st.id:<21} {st.desc}{mark}")
        for tmpl in st.argv:
            print("     $ " + " ".join(_resolve(tmpl, subs)))


def _record(log: Path, ts: str, step: Step, subs, rc: int, status: str, secs: float, out: str) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": ts, "id": step.id, "argv": [_resolve(t, subs) for t in step.argv], "rc": rc,
           "status": "FAIL" if status.startswith("FAIL") else status, "detail": status, "seconds": round(secs, 2)}
    with log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    tail = "\n".join((out or "").splitlines()[-40:])
    (log.parent / f"{ts}-{step.id}.log").write_text(tail + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    home = Path.home()
    ap = argparse.ArgumentParser(prog="golive.py", description=__doc__.split("\n")[0])
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--yes-automatic", action="store_true")
    ap.add_argument("--from", dest="start", default=None)
    ap.add_argument("--skip", action="append", default=[])
    ap.add_argument("--worktree", default=os.environ.get("GOLIVE_WORKTREE") or str(home / "CODE_FILES" / "dotclaude-merge"))
    ap.add_argument("--live", default=str(plat.claude_dir()))
    ap.add_argument("--branch", default="ecc-merge")
    ap.add_argument("--tag", default="v4.3.0")
    ap.add_argument("--packages", default=os.environ.get("CLAUDE_ECC_PACKAGES")
                    or str(home / "CODE_FILES" / "claude-ecc-merge" / "plan" / "PACKAGES.json"))
    ap.add_argument("--remote-ssh", default=None)
    ap.add_argument("--trailer", action="append", default=[])
    ap.add_argument("--message", default=None, help="release commit subject; {T} becomes the tag")
    ap.add_argument("--gitleaks-config", action="store_true", help="print the gitleaks TOML the secrets step uses")
    a = ap.parse_args(argv)
    if a.gitleaks_config:
        sys.stdout.write(GITLEAKS_TOML)
        return 0
    ids = [s.id for s in STEPS]
    bad = [s for s in a.skip if s in _NO_SKIP or s not in ids]
    if bad or (a.start and a.start not in ids):
        print(f"golive: refused: cannot skip {bad} (secrets, ownership and pytest always run)" if bad
              else f"golive: unknown --from id {a.start!r}")
        return 2
    start = ids.index(a.start) if a.start else 0
    subs = _subs(a)
    _print_plan(a, subs, start, set(a.skip))
    if a.plan:
        return 0
    if plat.IS_WINDOWS:
        print("golive: refused: run go-live from the Linux workstation (--plan works anywhere)")
        return 2
    if not a.yes_automatic:
        print("refusing to run: pass --yes-automatic")
        return 2
    ts = time.strftime("%Y%m%dT%H%M%S") + f"{int(time.time() * 1e6) % 1_000_000:06d}"
    log = plat.state_dir() / "golive" / f"{ts}.jsonl"
    for st in STEPS[start:]:
        if st.id in a.skip:
            print(f"{st.id} SKIPPED(--skip)")
            continue
        t0 = time.monotonic()
        try:
            if st.id == "memory":
                p = _memory_note(ts, time.strftime("%Y-%m-%d"))
                status, rc, out = "OK", 0, str(p)
                print(f"MEMORY: apply with mcp__memory__add_observations + the MEMORY.md index edit ({p})")
            else:
                status, rc, out = _EXEC.get(st.id, _x_generic)(st, subs, a)
        except _Fail as f:
            status, rc, out = f.status, f.rc, f.out
        _record(log, ts, st, subs, rc, status, time.monotonic() - t0, out)
        print(f"{st.id} {status}")
        if status.startswith("FAIL"):
            print(f"golive: FAIL at {st.id} (see {log.parent / (ts + '-' + st.id + '.log')})")
            return 1
    print("golive: DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
