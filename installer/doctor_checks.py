"""Source-derived checks shared by the installer doctor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

RowWriter = Callable[[list, str, str, str], None]


def check_palette(rows: list, root: Path, row: RowWriter, passed: str) -> None:
    """Report live palette counts (computed from disk; never a pinned snapshot)."""
    skill_count = len(list((root / "skills").glob("*/SKILL.md")))
    agent_count = len([p for p in (root / "agents").glob("*.md") if p.name not in ("CLAUDE.md", "AGENTS.md", "README.md")])
    row(rows, "palette-skills", passed, f"{skill_count} SKILL.md, {agent_count} agents (derived from disk)")


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
            keys = ("hook_event_name", "event", "tool_name", "prompt", "source")
            if not isinstance(data, dict) or not any(key in data for key in keys):
                bad.append(fixture.name)
        except ValueError:
            bad.append(fixture.name)
    detail = f"{len(fixtures)} fixtures" + (f"; malformed={bad}" if bad else "")
    row(rows, "hook-fixtures", passed if not bad else failed, detail)
