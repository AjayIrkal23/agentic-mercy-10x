#!/usr/bin/env python3
"""doctor.py — install-time health + trigger-surface verifier.

Rows (PASS / WARN / FAIL / SKIP; non-zero exit on any FAIL):

  link-doctor          every enabled dispatch link fires <10s, exit 0, parseable output
                       (run with CLAUDE_HOOK_DOCTOR=1 so mutating links no-op)
  interpreters         template fully tokenized; no /home/<user>/ or \\Users\\ literal
  render-equivalence   render(template ⊕ overlay) SEMANTICALLY == live settings.json
  hook-command         the rendered PreToolUse hook command runs through a shell: exit 0 + JSON
  statusline           the rendered statusLine.command runs through a shell: exit 0 + a non-empty line
  settings-safety     0 "lean-ctx" substrings in settings.json AND the template; deny == []
  lean-ctx-config      config.toml carries the manifest keys + the zero-injection floor
                       (doctor_host.ZERO_INJECTION) and lean-ctx >= min_version
  jcodemunch-config    ~/.code-index/config.jsonc carries the manifest keys
  plugins-contract     template enabledPlugins == manifest plugins.install
  plugins-installed    every manifest plugin installed + enabled (`claude plugin list`)
  generated-in-sync    generators --check: rc != 0 FAIL, `drift:` lines WARN
  palette-skills       SKILL.md / agent counts from disk; FAIL when either is 0
  aliases · R9/R10-validator · locked-source-links · ollama-embeddings (WARN) ·
  model-routing · workflow-args · hook-fixtures
  base-tools           claude, node + npm, git, uv resolve (FAIL; gh / ollama WARN; SKIP under
                       --ci or AGENTIC_MERCY_SKIP_BASE_TOOLS; doctor_basetools.py)
  mcp-roster           registrations vs manifest: missing, extras, npx pin drift,
                       deprecated packages, /mcp auth (WARN only; doctor_mcp.py)
  secret-perms         .env*, CLAUDE.machines.local.md, .credentials.json,
                       settings.user.json, ~/.claude.json not group/world readable
                       (WARN + chmod hint; Windows: SDDL from icacls, SIDs, WARN + icacls hint)
  mods / mods-runtime  doctor_mods.py: static contract + plugin validate + version
                       minimum; tsc + `claude plugin test`

``--ci``: machine-dependent rows (mcp-roster, lean-ctx, jcodemunch, ollama,
plugins-installed, mods-runtime) → SKIP; hook-command and statusline run under it when a rendered
settings.json exists. Pure stdlib; importable and CLI.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_HOOKS = _ROOT / "hooks"
for _p in (str(_ROOT / "installer"), str(_HOOKS), str(_HOOKS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402
import doctor_basetools  # noqa: E402
import doctor_checks  # noqa: E402
import doctor_hook  # noqa: E402
import doctor_host  # noqa: E402
import doctor_mcp  # noqa: E402
import doctor_mods  # noqa: E402

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"


def _row(rows, name, status, detail=""):
    rows.append((name, status, detail))


def _manifest() -> dict:
    return json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
def _check_link_doctor(rows):
    prev = os.environ.get("CLAUDE_HOOK_DOCTOR")
    os.environ["CLAUDE_HOOK_DOCTOR"] = "1"  # mutating links (selfheal, cleanup …) no-op
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
    finally:
        if prev is None:
            os.environ.pop("CLAUDE_HOOK_DOCTOR", None)
        else:
            os.environ["CLAUDE_HOOK_DOCTOR"] = prev


def _check_render_equivalence(rows):
    if not (_ROOT / "settings.json").exists():
        _row(rows, "render-equivalence", SKIP, "settings.json not rendered yet")
        return
    try:
        import render  # type: ignore
        ok, msg = render.check_equivalence()
        _row(rows, "render-equivalence", PASS if ok else FAIL, msg)
    except Exception as exc:  # noqa: BLE001
        _row(rows, "render-equivalence", FAIL, f"{type(exc).__name__}: {exc}")


def _check_lean_ctx(rows, ci: bool):
    if ci:
        _row(rows, "lean-ctx-config", SKIP, "--ci")
        return
    import deps  # type: ignore
    required = doctor_host.leanctx_required_with_floor(deps.leanctx_required())
    gaps = deps.leanctx_config_gaps(required)
    problems = [f"config keys off: {gaps[:6]}"] if gaps else []
    want = doctor_mods._vt(((deps._load_manifest().get("leanctx_config") or {}).get("min_version")) or "")
    if shutil.which("lean-ctx") and want:
        have = doctor_mods._vt(plat.run(["lean-ctx", "--version"], timeout=15).stdout or "")
        if have and have < want:
            problems.append(f"lean-ctx {'.'.join(map(str, have))} < {'.'.join(map(str, want))}")
    if problems:
        _row(rows, "lean-ctx-config", FAIL, "; ".join(problems))
    elif gaps is None:
        _row(rows, "lean-ctx-config", WARN, f"{deps.leanctx_config_path()} absent — the installer writes it")
    else:
        note = doctor_host.leanctx_unmanaged_note(deps.leanctx_config_path(), required)
        _row(rows, "lean-ctx-config", PASS, "zero injection (rules/shadow/read redirect+dedup/auto_inject off), "
             "no updates/telemetry" + (f" (info, unmanaged: {note})" if note else ""))


def _check_jcodemunch(rows, ci: bool):
    if ci:
        _row(rows, "jcodemunch-config", SKIP, "--ci")
        return
    import jcodemunch_config as jc  # type: ignore
    gaps = jc.gaps()
    if gaps is None:
        _row(rows, "jcodemunch-config", WARN, f"{jc.config_path()} absent — the installer writes it")
    elif gaps:
        _row(rows, "jcodemunch-config", FAIL, f"keys off: {gaps}")
    else:
        _row(rows, "jcodemunch-config", PASS, "tool_surface full, AI summaries on, home trusted "
             "(info: /tmp scratch clones are outside trusted_folders and never indexed)")


def _check_plugins_contract(rows):
    try:
        tmpl = json.loads((_ROOT / "settings.template.json").read_text(encoding="utf-8"))
        enabled = {k for k, v in (tmpl.get("enabledPlugins") or {}).items() if v}
        declared = {p["id"] for p in _manifest().get("plugins", {}).get("install", [])}
    except Exception as exc:  # noqa: BLE001
        _row(rows, "plugins-contract", FAIL, f"{type(exc).__name__}: {exc}")
        return
    diff = sorted(enabled ^ declared)
    _row(rows, "plugins-contract", FAIL if diff else PASS,
         f"template vs manifest differ: {diff}" if diff else f"{len(enabled)} plugins declared + enabled")


def _check_generated(rows):
    results = []
    for cmd in _manifest().get("doctor_probes", {}).get("generated_checks", []):
        argv = [plat.python_exe() if c == "{PYTHON}" else c.replace("{CLAUDE_DIR}", str(_ROOT)) for c in cmd]
        if Path(argv[1]).exists():
            results.append((Path(argv[1]).name, plat.run(argv, timeout=120)))
    _row(rows, "generated-in-sync", *doctor_checks.generated_status(results))


def _run_with_stdin(cmd, stdin_data: str):
    import subprocess
    try:
        return subprocess.run(cmd, input=stdin_data, capture_output=True, encoding="utf-8", errors="replace",
                              timeout=15, check=False)
    except Exception:  # noqa: BLE001
        return subprocess.CompletedProcess(cmd, 1, "", "")


def _claude_version() -> str:
    if not shutil.which("claude"):
        return ""
    return (plat.run(["claude", "--version"], timeout=30).stdout or "").strip().split(" ")[0]


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
        doctor_checks.check_locked_source_links(rows, links.find_symlinks(), _row, PASS, FAIL)
    except Exception as exc:  # noqa: BLE001
        _row(rows, "locked-source-links", WARN, f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
def run_doctor(*, ci: bool = False) -> list[tuple[str, str, str]]:
    import deps  # type: ignore
    rows: list[tuple[str, str, str]] = []
    m = _manifest()
    mods = m.get("mods") or {}
    _check_link_doctor(rows)
    _row(rows, "interpreters", *doctor_checks.interpreters_status(_ROOT))
    _check_render_equivalence(rows)
    _row(rows, "hook-command", *doctor_hook.check_hook_command(_ROOT, ci))
    _row(rows, "statusline", *doctor_hook.check_statusline(_ROOT, ci))
    _row(rows, "settings-safety", *doctor_checks.settings_safety_status(_ROOT))
    _check_lean_ctx(rows, ci)
    _check_jcodemunch(rows, ci)
    _check_plugins_contract(rows)
    _row(rows, "plugins-installed", *doctor_host.check_plugins_installed(m, ci))
    _check_generated(rows)
    doctor_checks.check_palette(rows, _ROOT, _row, PASS, FAIL)
    _row(rows, "aliases", *doctor_checks.aliases_status(_ROOT))
    _check_validator(rows)
    _check_zero_symlinks(rows)
    _row(rows, "base-tools", *doctor_basetools.check_base_tools(ci))
    _row(rows, "mcp-roster", *doctor_mcp.check_mcp_roster(
        ci, m, deps.user_config_file(), plat.claude_dir() / "mcp-needs-auth-cache.json"))
    _row(rows, "ollama-embeddings", *doctor_host.check_ollama(m, ci))
    doctor_checks.check_model_routing(rows, _ROOT, _HOOKS, _row, _run_with_stdin,
                                      plat.python_exe(), PASS, FAIL, WARN)
    doctor_checks.check_fixtures(rows, _ROOT, _row, PASS, FAIL, WARN)
    _row(rows, "secret-perms", *doctor_host.check_secret_perms(plat.claude_dir()))
    _row(rows, "mods", *doctor_mods.check_mods(_ROOT, mods, ci, _claude_version))
    enabled = [x for x in mods.get("enabled") or [] if isinstance(x, str)]
    _row(rows, "mods-runtime", *doctor_mods.check_mods_runtime(_ROOT, enabled, ci))
    return rows


def main(argv: list[str]) -> int:
    try:  # a piped cp1252 stdout cannot carry a non-ANSI profile path
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass
    ci = "--ci" in argv
    rows = run_doctor(ci=ci)
    print(f"=== doctor: {_ROOT} ===")
    for name, status, detail in rows:
        mark = {"PASS": "OK ", "WARN": "!! ", "SKIP": ".. ", "FAIL": "XX "}.get(status, "?? ")
        print(f"  {mark} {name:22s} {status:5s} {detail}")
    n_fail = sum(1 for _, s, _ in rows if s == FAIL)
    n_warn = sum(1 for _, s, _ in rows if s == WARN)
    n_skip = sum(1 for _, s, _ in rows if s == SKIP)
    print(f"=== {len(rows)-n_fail-n_warn-n_skip} PASS, {n_warn} WARN, {n_skip} SKIP, {n_fail} FAIL ===")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
