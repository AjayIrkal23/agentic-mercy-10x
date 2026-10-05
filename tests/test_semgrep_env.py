"""semgrep needs EIO_BACKEND=posix on this workbench (audit 2026-10-05 J-14).

semgrep-core's OCaml eio runtime opens one io_uring per worker; with the default 8 MB
RLIMIT_MEMLOCK a multi-file scan dies with "io_uring_queue_init: Cannot allocate
memory" and reports 0 files scanned (Gate 3 could never see a real scan). The posix
backend avoids io_uring; the MCP server and hook-spawned scans inherit settings env.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_template_env_sets_posix_eio_backend():
    env = json.loads((ROOT / "settings.template.json").read_text(encoding="utf-8"))["env"]
    assert env.get("EIO_BACKEND") == "posix"
