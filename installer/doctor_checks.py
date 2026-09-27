"""Source-derived checks shared by the installer doctor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

RowWriter = Callable[[list, str, str, str], None]


def check_palette(rows: list, root: Path, row: RowWriter, passed: str) -> None:
    """Report live palette counts without treating manifest snapshots as policy."""
    skill_count = len(list((root / "skills").glob("*/SKILL.md")))
    command_count = len(list((root / "commands").glob("*.md")))
    row(rows, "palette-skills", passed, f"{skill_count} SKILL.md (derived from source)")
    row(rows, "palette-commands", passed, f"{command_count} command files (derived from source)")


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
    """Validate the Sonnet-default, Opus-implementation routing policy."""
    try:
        policy = json.loads((hooks / "model-policy.json").read_text(encoding="utf-8"))
        impl = (policy.get("invoke_categories") or {}).get("IMPLEMENT")
        default = policy.get("default")
        opus_pins = set((policy.get("agent_pins") or {}).get("opus") or [])
        required = {
            "implementation-engineer",
            "backend-implementor-specialist",
            "frontend-implementor-specialist",
            "integrator-specialist",
        }
        fable_pins = set((policy.get("agent_pins") or {}).get("fable") or [])
        ok = (
            impl == "opus"
            and default == "sonnet"
            and required <= opus_pins
            and not fable_pins
        )
        row(rows, "model-routing", passed if ok else failed,
            f"IMPLEMENT={impl} default={default}")
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
