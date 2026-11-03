"""Source-derived checks shared by the installer doctor."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Iterable

RowWriter = Callable[[list, str, str, str], None]
_HOME_LITERAL = re.compile(r"/home/(?!\.\.\.)[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/|\\\\Users\\\\")


def interpreters_status(root: Path) -> tuple[str, str]:
    tmpl = root / "settings.template.json"
    if not tmpl.exists():
        return "FAIL", "settings.template.json missing"
    text = tmpl.read_text(encoding="utf-8")
    bad = [lit for lit in ("python3 ${HOME}", "/usr/bin/node", "/usr/bin/python", "bash ", ".sh") if lit in text]
    for f in (tmpl, root / "installer" / "manifest.json"):
        if _HOME_LITERAL.search(f.read_text(encoding="utf-8")):
            bad.append(f"home-literal in {f.name}")
    have_tokens = all(t in text for t in ("{{PYTHON}}", "{{CLAUDE_DIR}}"))
    # audit I-11: a tokenized template could still point at a renamed/deleted script
    for rel in sorted(set(re.findall(r"\{\{CLAUDE_DIR\}\}/([\w./-]+\.py)", text))):
        if not (root / rel).is_file():
            bad.append(f"missing script {rel}")
    if bad or not have_tokens:
        return "FAIL", f"bare literals={bad} tokens={'ok' if have_tokens else 'MISSING'}"
    return "PASS", "template fully tokenized; no home literals"


def settings_safety_status(root: Path) -> tuple[str, str]:
    bad = []
    for name in ("settings.template.json", "settings.json"):
        p = root / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        if "lean-ctx" in text:
            bad.append(f'{name} contains "lean-ctx" ({text.count("lean-ctx")}x)')
        try:
            deny = (json.loads(text).get("permissions") or {}).get("deny", [])
        except ValueError:
            deny = ["<unparseable>"]
        # the template owns an empty deny list; live deny rules are the user's own (carried
        # by the re-render), lean-ctx's injected ones are caught by the substring check above
        if deny and (name == "settings.template.json" or deny == ["<unparseable>"]):
            bad.append(f"{name} permissions.deny={deny}")
    return ("FAIL", "; ".join(bad)) if bad else ("PASS", '0 "lean-ctx" substrings; permissions.deny []')


def aliases_status(root: Path) -> tuple[str, str]:
    ap = root / "hooks" / "skill-aliases.json"
    if not ap.exists():
        return "WARN", "skill-aliases.json absent"
    data = json.loads(ap.read_text(encoding="utf-8"))
    entries = {k: v for k, v in data.items() if not k.startswith("_")}
    missing = []
    for alias, target in entries.items():
        canon = target if isinstance(target, str) else (target.get("canonical") if isinstance(target, dict) else None)
        if canon and ":" not in canon and not (root / "skills" / canon / "SKILL.md").exists():
            missing.append(f"{alias}->{canon}")
    if missing:
        return "FAIL", f"{len(missing)} aliases point at a missing canonical: {missing[:5]}"
    return "PASS", f"{len(entries)} aliases resolve"


def check_palette(rows: list, root: Path, row: RowWriter, passed: str, failed: str) -> None:
    """Report live palette counts (computed from disk; never a pinned snapshot).
    FAIL on an empty catalog (audit I-11: the row could not fail before)."""
    skill_count = len(list((root / "skills").glob("*/SKILL.md")))
    agent_count = len([p for p in (root / "agents").glob("*.md") if p.name not in ("CLAUDE.md", "AGENTS.md", "README.md")])
    status = passed if skill_count and agent_count else failed
    row(rows, "palette-skills", status, f"{skill_count} SKILL.md, {agent_count} agents (derived from disk)")


def generated_status(results: list) -> tuple[str, str]:
    """[(script name, CompletedProcess)] of the generators' --check runs. Non-zero ->
    FAIL; exit 0 but `drift:` lines on stdout -> WARN (gen-agent-skill-blocks exits 0
    on drift it cannot fix itself). Exit 2 with `PyYAML missing` is not drift: SKIP naming the
    cause, the R9/R10-validator row carries the one FAIL (REVERIFY R2)."""
    nomod = [name for name, cp in results if cp.returncode == 2 and "PyYAML missing" in (cp.stderr or "")]
    failed = [name for name, cp in results if cp.returncode != 0 and name not in nomod]
    if failed:
        return "FAIL", f"drift: {failed} (re-run the generator)"
    if nomod:
        return "SKIP", f"PyYAML missing (pip install pyyaml==6.0.3): {nomod} not checked"
    drift = [ln for _, cp in results for ln in (cp.stdout or "").splitlines() if ln.startswith("drift:")]
    if drift:
        return "WARN", f"{len(drift)} drift line(s), e.g. {drift[0][:120]}"
    return "PASS", "invoke skills + agent skill blocks in sync"


_WF_BAD = ("DRIFT", "MISSING", "EXTRA", "NOT-RENDERED")


DESIGN_TRIO = ("impeccable", "ui-ux-pro-max", "hallmark")


def design_trio_status(root: Path, ci: bool = False) -> tuple[str, str]:
    """v5.2.0 design trio: the three vendored skills (FAIL when one is missing: the vendor-skills post step
    restores it), node for Hallmark's scripts (WARN), the Impeccable engine cached and verified (WARN: the
    impeccable-engine post step and the daily self-heal fetch it). --ci checks the skills only."""
    root = Path(root)
    missing = [s for s in DESIGN_TRIO if not (root / "skills" / s / "SKILL.md").is_file()]
    if missing:
        return "FAIL", f"vendored skills missing: {', '.join(missing)} (scripts/vendor_skill.py --all)"
    if ci:
        return "PASS", "skills vendored (node and the engine are not checked under --ci)"
    try:
        from lib import impeccable_engine  # noqa: PLC0415  (doctor.py puts hooks/ on sys.path)
        from lib import platform as plat  # noqa: PLC0415
        engine = impeccable_engine.cached_binary(root / "skills" / "impeccable")
        version = impeccable_engine.version(root / "skills" / "impeccable")
        node = plat.node_exe()
    except Exception as exc:  # noqa: BLE001
        return "WARN", f"cannot probe: {exc}"
    warns = []
    if not node:
        warns.append("no node: Hallmark theme deal and sloplint steps skip")
    if engine is None:
        warns.append(f"Impeccable engine {version} not cached (scripts/impeccable_engine.py; "
                     "the daily self-heal fetches it)")
    return ("WARN", "; ".join(warns)) if warns else ("PASS", f"skills vendored, node, Impeccable engine {version} cached")


def workflows_rendered_status(root: Path, ci: bool = False) -> tuple[str, str]:
    """I10: workflows/*.js + index.json are a per-machine render (untracked). Missing or drifted -> FAIL,
    which self-heal repairs with `scripts/build_workflows.py --quiet`. --ci: SKIP (CI renders and checks)."""
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415
    root = Path(root)
    script = root / "scripts" / "build_workflows.py"
    if ci:
        return "SKIP", "ci: the CI job renders and checks the workflows itself"
    if not script.is_file() or not (root / "workflows" / "src").is_dir():
        return "SKIP", "no workflow sources"
    if not (root / "workflows" / "index.json").is_file():
        return "FAIL", "workflows not rendered (self-heal runs scripts/build_workflows.py)"
    try:
        cp = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return "WARN", f"build_workflows.py --check: {type(exc).__name__}"
    lines = (cp.stdout or "").strip().splitlines()
    if cp.returncode != 0:
        bad = [ln for ln in lines if ln.startswith(_WF_BAD)]
        return "FAIL", ("; ".join(bad[:3]) or f"--check rc={cp.returncode}") + " (self-heal re-renders)"
    return "PASS", lines[-1][:100] if lines else "rendered"


def _approved_locked_source(link: Path) -> bool:
    """Accept only links that resolve to a recognizable skill source surface."""
    try:
        target = link.resolve(strict=True)
    except OSError:
        return False
    if target.is_file():
        return link.name == "SKILL.md"
    if not target.is_dir():
        return False
    if (target / "SKILL.md").is_file():
        return True
    return link.name == "sections" and (target.parent / "SKILL.md").is_file()


def check_locked_source_links(
    rows: list,
    symlinks: Iterable[Path],
    row: RowWriter,
    passed: str,
    failed: str,
) -> None:
    links = list(symlinks)
    unapproved = [link for link in links if not _approved_locked_source(link)]
    if unapproved:
        row(rows, "locked-source-links", failed,
            f"{len(unapproved)} unapproved symlink(s) e.g. {unapproved[0]}")
        return
    row(rows, "locked-source-links", passed,
        f"{len(links)} approved locked-source symlink(s)")


# Fallback for a policy without `roles`: the judges pinned before roles existed.
_LEGACY_JUDGES = frozenset({"santa-reviewer", "frontend-uiux-designer", "planning-director",
                            "spec-architect", "debug-detective"})


def check_model_routing(
    rows: list,
    root: Path,
    hooks: Path,
    row: RowWriter,
    run_with_stdin: Callable,
    python_exe: str,
    passed: str,
    failed: str,
    warned: str,
) -> None:
    """Validate the routing policy: Opus judges, executors escalate to Opus (on max20 they run
    Opus outright since 2026-10-31, owner: quality over token cost), Fable never pinned."""
    try:
        policy = json.loads((hooks / "model-policy.json").read_text(encoding="utf-8"))
        default = policy.get("default")
        pins = policy.get("agent_pins") or {}
        opus_pins = set(pins.get("opus") or [])
        role_map = (policy.get("roles") or {}).get("agents") or {}
        judges = {a for a, r in role_map.items() if r == "judge"} or set(_LEGACY_JUDGES)
        esc = policy.get("escalation") or {}
        executors = set(esc.get("agents") or [])
        ok = (
            default == "sonnet"
            and judges <= opus_pins
            and bool(executors)
            and esc.get("enabled") is True and esc.get("to") == "opus"
            and (policy.get("invoke_categories") or {}).get("IMPLEMENT") in (None, default)
            and not pins.get("fable")
        )
        detail = (f"default={default} judges-on-opus={judges <= opus_pins} "
                  f"executors-pinned={sorted(executors & opus_pins)} escalation->{esc.get('to')}")
        if not judges <= opus_pins:
            detail += f" judges-not-pinned={sorted(judges - opus_pins)}"
        if not policy.get("tiers"):
            detail += " (no tiers block)"
        row(rows, "model-routing", passed if ok else failed, detail)
    except Exception as exc:  # noqa: BLE001
        row(rows, "model-routing", failed,
            f"model-policy.json: {type(exc).__name__}: {exc}")
        return

    fixture = root / "tests" / "fixtures" / "hook-events" / "workflow-model-guard.json"
    guard = hooks / "workflow-model-guard.py"
    if not fixture.exists() or not guard.exists():
        row(rows, "workflow-args", warned, "fixture or guard missing")
        return
    try:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        want_args = payload["tool_input"]["args"]
        completed = run_with_stdin([python_exe, str(guard)], json.dumps(payload))
        output = json.loads(completed.stdout) if completed.stdout.strip() else {}
        updated = (output.get("hookSpecificOutput") or {}).get("updatedInput") or {}
        got_args = updated.get("args")
        detail = "args preserved byte-for-byte" if got_args == want_args else f"args changed: {got_args}"
        row(rows, "workflow-args", passed if got_args == want_args else failed, detail)
    except Exception as exc:  # noqa: BLE001
        row(rows, "workflow-args", failed, f"{type(exc).__name__}: {exc}")


def _fixture_ok(data) -> bool:
    """A hook-event fixture names its event and session; a tool event also carries
    tool_name + a tool_input object (audit I-11: any dict with one key used to pass)."""
    if not isinstance(data, dict) or not data.get("session_id"):
        return False
    event = data.get("hook_event_name") or data.get("event") or ""
    if not event:
        return False
    if "ToolUse" in str(event) or event in ("pre-tool-use", "post-tool-use"):
        return bool(data.get("tool_name")) and isinstance(data.get("tool_input"), dict)
    return True


def check_fixtures(rows: list, root: Path, row: RowWriter,
                   passed: str, failed: str, warned: str) -> None:
    fixture_dir = root / "tests" / "fixtures" / "hook-events"
    if not fixture_dir.exists():
        row(rows, "hook-fixtures", warned, "tests/fixtures/hook-events absent")
        return
    bad = []
    fixtures = list(fixture_dir.glob("*.json"))
    for fixture in fixtures:
        try:
            data = json.loads(fixture.read_text(encoding="utf-8"))
            if not _fixture_ok(data):
                bad.append(fixture.name)
        except ValueError:
            bad.append(fixture.name)
    detail = f"{len(fixtures)} fixtures" + (f"; malformed={bad}" if bad else "")
    row(rows, "hook-fixtures", passed if not bad else failed, detail)
