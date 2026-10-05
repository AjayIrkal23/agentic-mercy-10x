"""lib/turns: only a human prompt starts a turn (audit 2026-10-05 B2-01).

Stop-hook feedback and skill-body loads (isMeta), <task-notification> rows
(origin.kind task-notification) and the "[Request interrupted by user]" marker are
user-typed rows in the transcript but not human turns; counting them re-armed the
once-per-turn Stop gates and emptied the "files written this turn" list.
A slash command's non-meta `<command-name>` row IS a human turn.
"""
from __future__ import annotations

import json
import pathlib
import sys

HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import turns  # noqa: E402

T0, T1, T2, T3, T4 = (f"2026-10-05T10:0{i}:00+00:00" for i in range(5))


def _user(ts, content, **extra):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": content}, **extra}


def _write(ts, path):
    return {"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": path}}]}}


def _transcript(tmp_path, rows) -> str:
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return str(p)


def test_meta_and_system_rows_do_not_start_a_turn(tmp_path):
    tr = _transcript(tmp_path, [
        _user(T0, "add the helper and a test"),
        _write(T0, "/repo/src/a.ts"),
        _user(T1, "Stop hook feedback: SUITE GATE (1/1) ...", isMeta=True),
        _user(T2, [{"type": "text", "text": "Base directory for this skill: /x"}], isMeta=True),
        _user(T3, "<task-notification>\n<task-id>abc</task-id>", origin={"kind": "task-notification"}),
        _user(T4, "[Request interrupted by user]"),
    ])
    assert turns.last_user_turn(tr) == (turns.to_aware(T0), "add the helper and a test")
    assert turns.turn_written_files(tr) == ["/repo/src/a.ts"]


def test_slash_command_row_is_a_human_turn(tmp_path):
    tr = _transcript(tmp_path, [
        _user(T0, "first"),
        _user(T1, "<command-name>/invoke</command-name>\n<command-args>impl</command-args>"),
        _user(T2, [{"type": "text", "text": "skill body"}], isMeta=True),
    ])
    ts, text = turns.last_user_turn(tr)
    assert ts == turns.to_aware(T1) and text.startswith("<command-name>")


def test_turn_bash_commands_since_the_human_prompt(tmp_path):
    bash = lambda ts, cmd: {"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}}
    tr = _transcript(tmp_path, [
        _user(T0, "first"), bash(T0, "ls old"),
        _user(T1, "second"), bash(T2, "sed -n 1,80p ~/.claude/skills/x/SKILL.md"),
        _user(T3, "Stop hook feedback: ...", isMeta=True), bash(T4, "npm test"),
    ])
    assert turns.turn_bash_commands(tr) == ["sed -n 1,80p ~/.claude/skills/x/SKILL.md", "npm test"]


def test_human_origin_is_a_turn(tmp_path):
    tr = _transcript(tmp_path, [_user(T0, "a"), _user(T1, "b", origin={"kind": "human"})])
    assert turns.last_user_turn(tr)[1] == "b"


def test_other_relayed_origins_still_count(tmp_path):
    """santa-diff P4: only task notifications are machine rows; a human message relayed
    by another channel keeps anchoring the turn."""
    tr = _transcript(tmp_path, [_user(T0, "a"), _user(T1, "b", origin={"kind": "channel"})])
    assert turns.last_user_turn(tr)[1] == "b"
