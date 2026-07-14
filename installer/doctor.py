#!/usr/bin/env python3
"""doctor.py — install-time health + trigger-surface verifier (P6-T5 core / P6-T6 full).

Absorbs ``hooks/tools/link-doctor.py`` (synthetic-event fire through every dispatch
link, Charter §3) and adds the trigger-surface + portability invariants so any
regression is caught at install/update time, not mid-session:

  link-doctor          every enabled dispatch link fires <10s, parseable output
  interpreters         the settings TEMPLATE is fully tokenized (no bare
                       python3/usr-bin-node/bash/.sh) — the Windows-runnable bar
  render-equivalence   render(template) == live settings.json (byte-identical)
  palette-skills       219 SKILL.md under skills/ (195 bodies + 24 aliases)
  palette-commands     21 command files in commands/
  command-resolution   all 139 historic /invoke names resolve (file or invoke_compat)
  aliases              24 alias skills, each resolving to an existing canonical
  R9/R10               validate_skills.py green (floor guard + upstream-intactness)
  zero-symlinks        no symlink survives on the installed skill surface
  mcp-roster           every expected MCP registered (settings.json / ~/.claude.json)

PASS/WARN/FAIL table; non-zero exit on any FAIL. Pure stdlib; importable
(``run_doctor()``) and CLI. P6-T6 extends it with tests/fixtures/hook-events and
model-routing fixtures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_HOOKS = _ROOT / "hooks"
for _p in (str(_ROOT / "installer"), str(_HOOKS), str(_HOOKS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


def _row(rows, name, status, detail=""):
    rows.append((name, status, detail))


# --------------------------------------------------------------------------- #
def _check_link_doctor(rows):
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("link_doctor", _HOOKS / "tools" / "link-doctor.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        passed, failed, detail_rows = mod.run_doctor()
        bad = [r for r in detail_rows if not (r[2] == "PASS" or r[2].startswith(("SKIP", "WARN")))]
        _row(rows, "link-doctor", PASS if failed == 0 else FAIL, f"{passed}/{passed+failed} links ok" + (f"; bad={[b[1] for b in bad]}" if bad else ""))
    except Exception as exc:  # noqa: BLE001
        _row(rows, "link-doctor", FAIL, f"{type(exc).__name__}: {exc}")


def _check_interpreters(rows):
    tmpl = _ROOT / "settings.template.json"
    if not tmpl.exists():
        _row(rows, "interpreters", FAIL, "settings.template.json missing")
        return
    text = tmpl.read_text(encoding="utf-8")
    bad = []
    for lit in ("python3 ${HOME}", "/usr/bin/node", "/usr/bin/python", "bash ", ".sh"):
        if lit in text:
            bad.append(lit)
    have_tokens = all(t in text for t in ("{{PYTHON}}", "{{NODE}}", "{{CLAUDE_DIR}}"))
    if bad or not have_tokens:
        _row(rows, "interpreters", FAIL, f"bare literals={bad} tokens={'ok' if have_tokens else 'MISSING'}")
    else:
        _row(rows, "interpreters", PASS, "template fully tokenized")


def _check_render_equivalence(rows):
    try:
        import render  # type: ignore
        ok, msg = render.check_equivalence()
        _row(rows, "render-equivalence", PASS if ok else FAIL, msg)
    except Exception as exc:  # noqa: BLE001
        _row(rows, "render-equivalence", WARN, f"{type(exc).__name__}: {exc}")


def _count_skill_mds() -> int:
    n = 0
    skills = _ROOT / "skills"
    for p in skills.glob("*/SKILL.md"):
        n += 1
    return n


def _check_palette(rows):
    manifest = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    want = manifest.get("palette", {})
    want_sk = want.get("skill_names", 219)
    n_sk = _count_skill_mds()
    # The gstack clone (skills/gstack/, gitignored, upstream) contributes exactly
    # one depth-2 SKILL.md — the router. Before `gstack-upgrade`/the installer
    # clones it (fresh checkout, CI pre-clone), the count is want-1; that is still
    # a healthy workbench, so treat it as PASS with a note rather than a FAIL.
    gstack_present = (_ROOT / "skills" / "gstack" / "SKILL.md").exists()
    if n_sk == want_sk and gstack_present:
        _row(rows, "palette-skills", PASS, f"{n_sk} SKILL.md (want {want_sk})")
    elif n_sk == want_sk - 1 and not gstack_present:
        _row(rows, "palette-skills", PASS, f"{n_sk} SKILL.md (gstack clone not installed; full={want_sk})")
    else:
        _row(rows, "palette-skills", FAIL, f"{n_sk} SKILL.md (want {want_sk}, gstack={'yes' if gstack_present else 'no'})")
    cmds = list((_ROOT / "commands").glob("*.md"))
    _row(rows, "palette-commands", PASS if len(cmds) == want.get("command_files", 21) else FAIL, f"{len(cmds)} command files (want {want.get('command_files')})")


def resolve_historic_commands(names, cmd_dir: Path, cmap: dict) -> list[str]:
    """Pure resolver (testable): a historic /invoke name resolves iff it has a
    command FILE or an invoke_compat translator entry. Returns the unresolved."""
    return [n for n in names if not (cmd_dir / f"{n}.md").exists() and n not in cmap]


def _check_command_resolution(rows):
    hist = _HOOKS / "historic-invoke-commands.json"
    compat = _HOOKS / "commands-compat.json"
    if not hist.exists():
        _row(rows, "command-resolution", WARN, "historic-invoke-commands.json absent")
        return
    names = json.loads(hist.read_text(encoding="utf-8")).get("names", [])
    cmap = {}
    if compat.exists():
        cmap = json.loads(compat.read_text(encoding="utf-8")).get("map", {})
    unresolved = resolve_historic_commands(names, _ROOT / "commands", cmap)
    if unresolved:
        _row(rows, "command-resolution", FAIL, f"{len(unresolved)}/{len(names)} unresolved e.g. {unresolved[:5]}")
    else:
        _row(rows, "command-resolution", PASS, f"all {len(names)} historic names resolve (file or translator)")


def _check_model_routing(rows):
    # 1. IMPLEMENT suite pins Opus (the /invoke-impl carve-out; single source of truth).
    try:
        policy = json.loads((_HOOKS / "model-policy.json").read_text(encoding="utf-8"))
        impl = (policy.get("invoke_categories") or {}).get("IMPLEMENT")
        default = policy.get("default")
        ok = impl == "opus" and default == "sonnet"
        _row(rows, "model-routing", PASS if ok else FAIL, f"IMPLEMENT={impl} default={default}")
    except Exception as exc:  # noqa: BLE001
        _row(rows, "model-routing", FAIL, f"model-policy.json: {type(exc).__name__}: {exc}")
        return
    # 2. workflow-model-guard preserves tool_input.args byte-for-byte (P2 regression).
    fx = _ROOT / "tests" / "fixtures" / "hook-events" / "workflow-model-guard.json"
    guard = _HOOKS / "workflow-model-guard.py"
    if not fx.exists() or not guard.exists():
        _row(rows, "workflow-args", WARN, "fixture or guard missing")
        return
    try:
        payload = json.loads(fx.read_text(encoding="utf-8"))
        want_args = payload["tool_input"]["args"]
        cp = _run_with_stdin([plat.python_exe(), str(guard)], json.dumps(payload))
        out = json.loads(cp.stdout) if cp.stdout.strip() else {}
        updated = (out.get("hookSpecificOutput") or {}).get("updatedInput") or {}
        got_args = updated.get("args")
        _row(rows, "workflow-args", PASS if got_args == want_args else FAIL,
             "args preserved byte-for-byte" if got_args == want_args else f"args changed: {got_args}")
    except Exception as exc:  # noqa: BLE001
        _row(rows, "workflow-args", FAIL, f"{type(exc).__name__}: {exc}")


def _run_with_stdin(cmd, stdin_data: str):
    import subprocess
    try:
        return subprocess.run(cmd, input=stdin_data, capture_output=True, text=True, timeout=15, check=False)
    except Exception:  # noqa: BLE001
        return subprocess.CompletedProcess(cmd, 1, "", "")


def _check_fixtures(rows):
    fx_dir = _ROOT / "tests" / "fixtures" / "hook-events"
    if not fx_dir.exists():
        _row(rows, "hook-fixtures", WARN, "tests/fixtures/hook-events absent")
        return
    bad = []
    for f in fx_dir.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            # a valid hook payload names its event or tool in one of these ways
            if not isinstance(d, dict) or not any(k in d for k in ("hook_event_name", "event", "tool_name", "prompt", "source")):
                bad.append(f.name)
        except ValueError:
            bad.append(f.name)
    n = len(list(fx_dir.glob("*.json")))
    _row(rows, "hook-fixtures", PASS if not bad else FAIL, f"{n} fixtures" + (f"; malformed={bad}" if bad else ""))


def _check_aliases(rows):
    ap = _HOOKS / "skill-aliases.json"
    if not ap.exists():
        _row(rows, "aliases", WARN, "skill-aliases.json absent")
        return
    data = json.loads(ap.read_text(encoding="utf-8"))
    entries = {k: v for k, v in data.items() if not k.startswith("_")}
    missing_canon = []
    for alias, target in entries.items():
        canon = target if isinstance(target, str) else (target.get("canonical") if isinstance(target, dict) else None)
        if canon and not (_ROOT / "skills" / canon / "SKILL.md").exists():
            missing_canon.append(f"{alias}->{canon}")
    if missing_canon:
        _row(rows, "aliases", FAIL, f"{len(missing_canon)} aliases point at a missing canonical: {missing_canon[:5]}")
    else:
        _row(rows, "aliases", PASS, f"{len(entries)} aliases resolve")


def _check_validator(rows):
    script = _ROOT / "scripts" / "validate_skills.py"
    if not script.exists():
        _row(rows, "R9/R10-validator", WARN, "validate_skills.py absent")
        return
    cp = plat.run([plat.python_exe(), str(script)], timeout=120)
    tail = (cp.stdout or "").strip().splitlines()[-1:] or [""]
    _row(rows, "R9/R10-validator", PASS if cp.returncode == 0 else FAIL, tail[0][:80])


def _check_zero_symlinks(rows):
    try:
        import links  # type: ignore
        syms = links.find_symlinks()
        _row(rows, "zero-symlinks", PASS if not syms else FAIL, f"{len(syms)} symlink(s)" + (f" e.g. {syms[0]}" if syms else ""))
    except Exception as exc:  # noqa: BLE001
        _row(rows, "zero-symlinks", WARN, f"{type(exc).__name__}: {exc}")


def _registered_mcp_names() -> set[str]:
    names: set[str] = set()
    for cfg in (_ROOT / "settings.json", Path.home() / ".claude.json"):
        try:
            d = json.loads(cfg.read_text(encoding="utf-8"))
            names |= set((d.get("mcpServers") or {}).keys())
        except Exception:  # noqa: BLE001
            pass
    return names


def _check_mcp_roster(rows):
    manifest = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest.get("doctor_probes", {}).get("mcp_roster", [])
    have = _registered_mcp_names()
    missing = [m for m in expected if m not in have]
    # missing MCPs are a WARN (registration site varies: settings.json vs ~/.claude.json
    # vs a CI runner with neither) — not an install-blocking FAIL.
    _row(rows, "mcp-roster", PASS if not missing else WARN, "all registered" if not missing else f"missing: {missing}")


# --------------------------------------------------------------------------- #
def run_doctor(*, ci: bool = False) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    _check_link_doctor(rows)
    _check_interpreters(rows)
    _check_render_equivalence(rows)
    _check_palette(rows)
    _check_command_resolution(rows)
    _check_aliases(rows)
    _check_validator(rows)
    _check_zero_symlinks(rows)
    _check_mcp_roster(rows)
    _check_model_routing(rows)
    _check_fixtures(rows)
    return rows


def main(argv: list[str]) -> int:
    ci = "--ci" in argv
    rows = run_doctor(ci=ci)
    print("=== ~/.claude doctor ===")
    worst_fail = False
    for name, status, detail in rows:
        mark = {"PASS": "OK ", "WARN": "!! ", "SKIP": ".. ", "FAIL": "XX "}.get(status, "?? ")
        print(f"  {mark} {name:22s} {status:5s} {detail}")
        if status == FAIL:
            worst_fail = True
    n_fail = sum(1 for _, s, _ in rows if s == FAIL)
    n_warn = sum(1 for _, s, _ in rows if s == WARN)
    print(f"=== {len(rows)-n_fail-n_warn} PASS, {n_warn} WARN, {n_fail} FAIL ===")
    return 1 if worst_fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
