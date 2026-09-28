#!/usr/bin/env python3
"""PostToolUse aggregator: one dispatch link for the post-write side effects.

Runs the sub-chain IN PARALLEL (ThreadPoolExecutor) and merges the children's
`additionalContext` in declaration order. Sequential execution summed the
children's timeouts (30 s) past the 12 s link timeout, so one slow child killed
every advisory (A03-B20). Doc-index refresh is owned by index-lifecycle
(jdocmunch surface); the duplicate jdocmunch-reindex-hook was retired 2026-09-27.
"""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
# (script, timeout[, args]). index-lifecycle journals the touched path (active
# repo only) and spawns ONE detached incremental indexer at N=5 writes / T=45s;
# it emits no additionalContext.
CHAIN: list[tuple] = [
    ("index-lifecycle.py", 8, ["post-write"]),
    ("dox-child-scaffold.py", 6),
    ("doc-update-enforcer.py", 5),
    ("security-scan-gate.py", 5),
]


def _merge(existing: str, add: str) -> str:
    add_st = add.strip()
    if not add_st:
        return existing
    if not existing.strip():
        return add_st
    return f"{existing.rstrip()}\n\n{add_st}"


def _run(script: str, payload_txt: str, timeout: int, args=None) -> str:
    cmd = [sys.executable or "python3", str(HOOK_DIR / script)] + list(args or [])
    try:
        proc = subprocess.run(
            cmd,
            input=payload_txt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return ""
        blob = json.loads(proc.stdout)
        if not isinstance(blob, dict):
            return ""
        chunk = blob.get("additionalContext") or blob.get("additional_context")
        if not isinstance(chunk, str):
            hso = blob.get("hookSpecificOutput")
            chunk = hso.get("additionalContext") if isinstance(hso, dict) else None
        if isinstance(chunk, str):
            return chunk
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    except Exception:  # noqa: BLE001 — a child must never take the chain down
        pass
    return ""


def main() -> int:
    raw = sys.stdin.read()
    payload_txt = raw if raw.strip() else "{}"

    with ThreadPoolExecutor(max_workers=len(CHAIN)) as pool:
        futures = [
            pool.submit(_run, entry[0], payload_txt, entry[1], entry[2] if len(entry) > 2 else None)
            for entry in CHAIN
        ]
        aggregated = ""
        for fut in futures:  # declaration order, not completion order
            try:
                chunk = fut.result()
            except Exception:  # noqa: BLE001
                chunk = ""
            if chunk:
                aggregated = _merge(aggregated, chunk)

    if not aggregated.strip():
        print("{}")
        return 0
    print(json.dumps({"additionalContext": aggregated}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
