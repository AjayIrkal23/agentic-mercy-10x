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


def test_turn_bash_results_pairs_evidence_with_its_tool_result(tmp_path):
    use = lambda tid, cmd: {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": cmd}}]}}
    res = lambda tid, err: {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "is_error": err, "content": "x"}]}}
    tr = _transcript(tmp_path, [
        _user(T0, "first"), use("a", "ls old"), res("a", True),
        _user(T1, "second"), use("b", "pytest -q"), res("b", True),
        use("c", "npm test"), res("c", False), use("d", "ruff check ."),
    ])
    assert turns.turn_bash_results(tr) == [("pytest -q", True), ("npm test", False), ("ruff check .", False)]
    assert turns.turn_bash_results(str(tmp_path / "missing.jsonl")) == []


def test_human_origin_is_a_turn(tmp_path):
    tr = _transcript(tmp_path, [_user(T0, "a"), _user(T1, "b", origin={"kind": "human"})])
    assert turns.last_user_turn(tr)[1] == "b"


def test_other_relayed_origins_still_count(tmp_path):
    """santa-diff P4: only task notifications are machine rows; a human message relayed
    by another channel keeps anchoring the turn."""
    tr = _transcript(tmp_path, [_user(T0, "a"), _user(T1, "b", origin={"kind": "channel"})])
    assert turns.last_user_turn(tr)[1] == "b"


def test_tail_entries_keeps_the_last_n_dict_rows(tmp_path):
    rows = [_user(T0, f"p{i}") for i in range(6)]
    p = tmp_path / "t.jsonl"
    lines = [json.dumps(r) for r in rows] + ["", "not json", "[1,2]"]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    got = turns.tail_entries(str(p), n=5)
    assert all(isinstance(e, dict) for e in got)
    # last 5 physical lines: rows 4, 5, blank, "not json", [1,2] -> two dicts, oldest first
    assert [e["message"]["content"] for e in got] == ["p4", "p5"]
    assert len(list(turns.iter_tail(str(p), 5))) == len(turns.tail_entries(str(p), 5))


def test_tail_entries_none_on_missing_and_empty_list_on_blank(tmp_path):
    assert turns.tail_entries(str(tmp_path / "missing.jsonl")) is None
    assert turns.tail_entries(None) is None
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert turns.tail_entries(str(empty)) == []
    assert list(turns.iter_tail(tmp_path / "none.jsonl")) == []


def test_scanners_share_one_reader(monkeypatch):
    import inspect
    assert inspect.getsource(turns).count("deque(") == 1
    monkeypatch.setattr(turns, "tail_entries", lambda *a, **k: [_user(T0, "x"), _write(T0, "/r/a.ts")])
    assert turns.turn_written_files("whatever") == ["/r/a.ts"]
    assert turns.last_user_turn("whatever")[1] == "x"


def test_turn_written_files_distinguishes_missing_from_empty(tmp_path):
    assert turns.turn_written_files(str(tmp_path / "missing.jsonl")) is None
    tr = _transcript(tmp_path, [_user(T0, "just a question")])
    assert turns.turn_written_files(tr) == []
