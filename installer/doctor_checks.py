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
    on drift it cannot fix itself)."""
    failed = [name for name, cp in results if cp.returncode != 0]
    if failed:
        return "FAIL", f"drift: {failed} (re-run the generator)"
    drift = [ln for _, cp in results for ln in (cp.stdout or "").splitlines() if ln.startswith("drift:")]
    if drift:
        return "WARN", f"{len(drift)} drift line(s), e.g. {drift[0][:120]}"
    return "PASS", "invoke skills + agent skill blocks in sync"


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
    """Validate the Sonnet 5.5 routing policy: Opus judges, Sonnet executes and
    escalates to Opus, Fable never pinned."""
    try:
        policy = json.loads((hooks / "model-policy.json").read_text(encoding="utf-8"))
        default = policy.get("default")
        pins = policy.get("agent_pins") or {}
        opus_pins = set(pins.get("opus") or [])
        judges = {"santa-reviewer", "frontend-uiux-designer", "planning-director",
                  "spec-architect", "debug-detective"}
        esc = policy.get("escalation") or {}
        executors = set(esc.get("agents") or [])
        ok = (
            default == "sonnet"
            and judges <= opus_pins
            and bool(executors) and not executors & opus_pins
            and esc.get("enabled") is True and esc.get("to") == "opus"
            and (policy.get("invoke_categories") or {}).get("IMPLEMENT") in (None, default)
            and not pins.get("fable")
        )
        row(rows, "model-routing", passed if ok else failed,
            f"default={default} judges-on-opus={judges <= opus_pins} "
            f"executors-pinned={sorted(executors & opus_pins)} escalation->{esc.get('to')}")
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
