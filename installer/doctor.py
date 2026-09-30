#!/usr/bin/env python3
"""doctor.py — install-time health + trigger-surface verifier.

Rows (PASS / WARN / FAIL / SKIP; non-zero exit on any FAIL):

  link-doctor          every enabled dispatch link fires <10s, parseable output
                       (run with CLAUDE_HOOK_DOCTOR=1 so mutating links no-op)
  interpreters         template fully tokenized; no /home/<user>/ or \\Users\\ literal
                       in settings.template.json / installer/manifest.json
  render-equivalence   render(template ⊕ overlay) SEMANTICALLY == live settings.json
                       (Claude-managed keys ignored; SKIP when settings.json is absent)
  settings-safety      0 "lean-ctx" substrings in settings.json AND the template;
                       permissions.deny == []
  lean-ctx-config      ~/.config/lean-ctx/config.toml carries the manifest keys and
                       lean-ctx >= min_version (WARN when not configured yet)
  jcodemunch-config    ~/.code-index/config.jsonc carries the manifest keys
                       (tool_surface full, AI summaries, home trusted; WARN when absent)
  plugins-contract     template enabledPlugins == manifest plugins.install
  generated-in-sync    gen-invoke-skills / gen-agent-skill-blocks --check
  palette-skills       SKILL.md / agent counts, derived from disk (never pinned)
  aliases · R9/R10-validator · locked-source-links · mcp-roster (WARN: missing /
  needs /mcp auth) · ollama-embeddings (WARN) · model-routing · workflow-args ·
  hook-fixtures

``--ci``: machine-dependent rows (mcp-roster, lean-ctx-config, ollama) → SKIP.
Pure stdlib; importable (``run_doctor(ci=...)``) and CLI.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_HOOKS = _ROOT / "hooks"
for _p in (str(_ROOT / "installer"), str(_HOOKS), str(_HOOKS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402
import doctor_checks  # noqa: E402

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
_HOME_LITERAL = re.compile(r"/home/(?!\.\.\.)[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/|\\\\Users\\\\")


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


def _check_interpreters(rows):
    tmpl = _ROOT / "settings.template.json"
    if not tmpl.exists():
        _row(rows, "interpreters", FAIL, "settings.template.json missing")
        return
    text = tmpl.read_text(encoding="utf-8")
    bad = [lit for lit in ("python3 ${HOME}", "/usr/bin/node", "/usr/bin/python", "bash ", ".sh") if lit in text]
    for f in (tmpl, _ROOT / "installer" / "manifest.json"):
        if _HOME_LITERAL.search(f.read_text(encoding="utf-8")):
            bad.append(f"home-literal in {f.name}")
    have_tokens = all(t in text for t in ("{{PYTHON}}", "{{CLAUDE_DIR}}"))
    if bad or not have_tokens:
        _row(rows, "interpreters", FAIL, f"bare literals={bad} tokens={'ok' if have_tokens else 'MISSING'}")
    else:
        _row(rows, "interpreters", PASS, "template fully tokenized; no home literals")


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


def _check_settings_safety(rows):
    bad = []
    for name in ("settings.template.json", "settings.json"):
        p = _ROOT / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        if "lean-ctx" in text:
            bad.append(f'{name} contains "lean-ctx" ({text.count("lean-ctx")}x)')
        try:
            deny = (json.loads(text).get("permissions") or {}).get("deny", [])
        except ValueError:
            deny = ["<unparseable>"]
        if deny:
            bad.append(f"{name} permissions.deny={deny}")
    _row(rows, "settings-safety", FAIL if bad else PASS,
         "; ".join(bad) if bad else '0 "lean-ctx" substrings; permissions.deny []')


def _version_tuple(s: str) -> tuple:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", s or "")
    return tuple(int(x) for x in m.groups()) if m else ()


def _check_lean_ctx(rows, ci: bool):
    if ci:
        _row(rows, "lean-ctx-config", SKIP, "--ci")
        return
    import deps  # type: ignore
    req = deps.leanctx_required()
    gaps = deps.leanctx_config_gaps(req)
    problems = []
    if gaps:
        problems.append(f"config keys off: {gaps[:6]}")
    want = _version_tuple(((deps._load_manifest().get("leanctx_config") or {}).get("min_version")) or "")
    if shutil.which("lean-ctx") and want:
        cp = plat.run(["lean-ctx", "--version"], timeout=15)
        have = _version_tuple(cp.stdout or "")
        if have and have < want:
            problems.append(f"lean-ctx {'.'.join(map(str, have))} < {'.'.join(map(str, want))}")
    if problems:
        _row(rows, "lean-ctx-config", FAIL, "; ".join(problems))
    elif gaps is None:
        _row(rows, "lean-ctx-config", WARN, f"{deps.leanctx_config_path()} absent — the installer writes it")
    else:
        _row(rows, "lean-ctx-config", PASS, "no hooks/rules/skill injection, no updates/telemetry, shadow off")


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
        _row(rows, "jcodemunch-config", PASS, "tool_surface full, AI summaries on, home trusted")


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
    bad = []
    for cmd in _manifest().get("doctor_probes", {}).get("generated_checks", []):
        argv = [plat.python_exe() if c == "{PYTHON}" else c.replace("{CLAUDE_DIR}", str(_ROOT)) for c in cmd]
        if not Path(argv[1]).exists():
            continue
        if plat.run(argv, timeout=120).returncode != 0:
            bad.append(Path(argv[1]).name)
    _row(rows, "generated-in-sync", FAIL if bad else PASS,
         f"drift: {bad} (re-run the generator)" if bad else "invoke skills + agent skill blocks in sync")


def _check_palette(rows):
    doctor_checks.check_palette(rows, _ROOT, _row, PASS)


def _check_model_routing(rows):
    doctor_checks.check_model_routing(
        rows, _ROOT, _HOOKS, _row, _run_with_stdin, plat.python_exe(), PASS, FAIL, WARN)


def _run_with_stdin(cmd, stdin_data: str):
    import subprocess
    try:
        return subprocess.run(cmd, input=stdin_data, capture_output=True, text=True, timeout=15, check=False)
    except Exception:  # noqa: BLE001
        return subprocess.CompletedProcess(cmd, 1, "", "")


def _check_fixtures(rows):
    doctor_checks.check_fixtures(rows, _ROOT, _row, PASS, FAIL, WARN)


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
        if canon and ":" not in canon and not (_ROOT / "skills" / canon / "SKILL.md").exists():
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
        doctor_checks.check_locked_source_links(rows, links.find_symlinks(), _row, PASS, FAIL)
    except Exception as exc:  # noqa: BLE001
        _row(rows, "locked-source-links", WARN, f"{type(exc).__name__}: {exc}")


def _check_mcp_roster(rows, ci: bool):
    if ci:
        _row(rows, "mcp-roster", SKIP, "--ci (no ~/.claude.json in CI)")
        return
    import deps  # type: ignore
    expected = _manifest().get("doctor_probes", {}).get("mcp_roster", [])
    have = deps.registered_user_mcps()
    missing = [m for m in expected if m not in have]
    try:
        auth = json.loads((plat.claude_dir() / "mcp-needs-auth-cache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        auth = {}
    needs = sorted(m for m in expected if m in auth)
    detail = "all registered" if not missing else f"missing: {missing}"
    if needs:
        detail += f"; needs /mcp auth: {needs}"
    _row(rows, "mcp-roster", WARN if (missing or needs) else PASS, f"{detail} ({deps.user_config_file().name})")


def _check_ollama(rows, ci: bool):
    """Semantic search needs a local ollama + the embedding model — WARN only."""
    probe = _manifest().get("doctor_probes", {}).get("ollama") or {}
    if ci or not probe:
        _row(rows, "ollama-embeddings", SKIP, "--ci" if ci else "no probe declared")
        return
    import urllib.request
    try:
        with urllib.request.urlopen(probe["url"], timeout=3) as resp:  # noqa: S310 (localhost)
            full = {m.get("name", "") for m in json.load(resp).get("models", [])}
    except Exception as exc:  # noqa: BLE001
        _row(rows, "ollama-embeddings", WARN, f"ollama unreachable ({type(exc).__name__}) — {probe.get('note', '')}")
        return
    base = {n.split(":")[0] for n in full}
    # a tagged probe entry (qwen2.5-coder:3b) needs that exact tag; an untagged one any tag
    missing = [m for m in probe.get("models", []) if (m not in full if ":" in m else m not in base)]
    _row(rows, "ollama-embeddings", WARN if missing else PASS,
         f"missing models {missing}: ollama pull {' '.join(missing)}" if missing else f"models ok: {probe['models']}")


# --------------------------------------------------------------------------- #
def run_doctor(*, ci: bool = False) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    _check_link_doctor(rows)
    _check_interpreters(rows)
    _check_render_equivalence(rows)
    _check_settings_safety(rows)
    _check_lean_ctx(rows, ci)
    _check_jcodemunch(rows, ci)
    _check_plugins_contract(rows)
    _check_generated(rows)
    _check_palette(rows)
    _check_aliases(rows)
    _check_validator(rows)
    _check_zero_symlinks(rows)
    _check_mcp_roster(rows, ci)
    _check_ollama(rows, ci)
    _check_model_routing(rows)
    _check_fixtures(rows)
    return rows


def main(argv: list[str]) -> int:
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
