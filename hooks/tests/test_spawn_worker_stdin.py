"""A4v2-06: `spawn_worker(stdin_text=...)` never blocks its caller on the child.

The payload used to be written into a `subprocess.PIPE`: Windows pipes hold 4 KB, so anything bigger (every
Write/Edit JSON of a few KB, through `dispatch_support.spawn_deferred`) stalled the PreToolUse path until the
child's interpreter started reading. The payload now goes through a delete-on-close temp file the child
reads as its stdin.

The child waits for a `go` file the test controls, so "the caller returned before the child read anything"
is structural (no clock): a blocking implementation never returns until `go` exists, and the test fails.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS))
from lib import platform as plat  # noqa: E402

PAYLOAD = ("0123456789abcdef" * 4096 + "é中\U0001F600")  # 64 KB + non-ASCII


def _child(go: Path, out: Path) -> list:
    code = ("import os,sys,time\n"
            f"go,out={str(go)!r},{str(out)!r}\n"
            "t=time.time()\n"
            "while not os.path.exists(go) and time.time()-t<60: time.sleep(0.05)\n"
            "open(out,'wb').write(sys.stdin.buffer.read())\n")
    return [sys.executable, "-c", code]


def _spawn_in_thread(cmd, text, **kw):
    box: dict = {}
    th = threading.Thread(target=lambda: box.update(pid=plat.spawn_worker(cmd, stdin_text=text, **kw)), daemon=True)
    th.start()
    th.join(15)  # a blocking spawn_worker is still stuck on the pipe here
    return th, box


def _wait_for(path: Path, size: int = 1, timeout: float = 30.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if path.exists() and path.stat().st_size >= size:
            return True
        time.sleep(0.05)
    return False


def test_a_64kb_payload_does_not_block_the_caller_on_a_child_that_has_not_read(tmp_path):
    go, out = tmp_path / "go", tmp_path / "got.bin"
    th, box = _spawn_in_thread(_child(go, out), PAYLOAD)
    try:
        assert not th.is_alive(), "spawn_worker is blocked writing the payload into a pipe"
        assert box["pid"]
        assert not out.exists()  # the child has read nothing yet: the caller really returned early
    finally:
        go.write_text("go", encoding="utf-8")
    assert _wait_for(out, len(PAYLOAD.encode("utf-8")))
    assert out.read_bytes().decode("utf-8") == PAYLOAD


def test_the_payload_file_is_gone_once_both_sides_closed_it(tmp_path, monkeypatch):
    import tempfile
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))
    go, out = tmp_path / "go", tmp_path / "got.bin"
    th, box = _spawn_in_thread(_child(go, out), PAYLOAD)
    go.write_text("go", encoding="utf-8")
    assert not th.is_alive() and _wait_for(out, len(PAYLOAD.encode("utf-8")))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and any(tmpdir.iterdir()):
        time.sleep(0.1)  # the child exits right after writing; Windows frees the file on its last handle
    assert list(tmpdir.iterdir()) == []


def test_a_temp_file_failure_falls_back_to_the_pipe(tmp_path, monkeypatch):
    import tempfile

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(tempfile, "TemporaryFile", boom)
    out = tmp_path / "got.bin"
    code = f"import sys;open({str(out)!r},'wb').write(sys.stdin.buffer.read())"
    assert plat.spawn_worker([sys.executable, "-c", code], stdin_text="small é") is not None
    assert _wait_for(out, 1) and out.read_bytes().decode("utf-8") == "small é"


def test_no_stdin_text_still_means_devnull(monkeypatch):
    seen: list = []

    class _P:
        pid = 1

        def __init__(self, cmd, **kw):
            seen.append(kw["stdin"])
    monkeypatch.setattr(subprocess, "Popen", _P)
    assert plat.spawn_worker(["x"]) == 1
    assert seen == [subprocess.DEVNULL]


@pytest.mark.parametrize("text", ["", "x"])
def test_the_child_gets_exactly_the_text_even_when_it_is_empty(tmp_path, text):
    out = tmp_path / "got.bin"
    code = f"import sys;open({str(out)!r},'wb').write(sys.stdin.buffer.read())"
    assert plat.spawn_worker([sys.executable, "-c", code], stdin_text=text) is not None
    assert _wait_for(out, 0) and _wait_for_exit(out, len(text))


def _wait_for_exit(out: Path, size: int) -> bool:
    end = time.monotonic() + 30
    while time.monotonic() < end:
        if out.exists() and out.stat().st_size == size:
            return True
        time.sleep(0.05)
    return False
