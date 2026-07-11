#!/usr/bin/env python3
"""PostToolUse sub-script: delegate to `jdocmunch-mcp hook-posttooluse`.

Thin wrapper so the jdocmunch auto-reindex (after Edit/Write on doc files)
fits the post-write-aggregator.py chain convention (python3 script, JSON on
stdin/stdout).  The upstream hook filters doc extensions itself and spawns a
throttled background reindex worker.  Fails open on any error.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

BINARY = shutil.which("jdocmunch-mcp") or str(
    Path.home() / ".local" / "bin" / "jdocmunch-mcp"
)


def main() -> int:
    payload_txt = sys.stdin.read() or "{}"
    try:
        proc = subprocess.run(
            [BINARY, "hook-posttooluse"],
            input=payload_txt,
            capture_output=True,
            text=True,
            timeout=5,
        )
        out = proc.stdout.strip()
        if proc.returncode == 0 and out:
            blob = json.loads(out)
            if isinstance(blob, dict):
                print(json.dumps(blob))
                return 0
    except Exception:
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
