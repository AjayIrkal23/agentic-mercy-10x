#!/usr/bin/env python3
"""
force-sonnet-subagent.py — DEPRECATED (2026-06-10), kept as a harmless no-op.

This hook used to HARD-PIN every subagent to Sonnet, strictly always. That blanket
override made Opus impossible to use for any subagent — including the UI/UX agent —
which contradicted the desired policy ("allow Sonnet and Opus both; Opus only for
heavy/complex or UI/UX tasks").

Routing now lives entirely in `opus-guard.py`, which:
  - pins `model:"sonnet"` by default (so nothing inherits the Opus parent),
  - pins `model:"opus"` only for the `[opus]` label or UI/UX agents,
  - honors the `~/.claude/state/sonnet-only-mode` kill-switch flag (all-sonnet) and
    the `~/.claude/state/opus-only-mode` flag (all-opus).

The "force all subagents to sonnet" behavior is therefore now a FLAG, not a hook:
    touch  ~/.claude/state/sonnet-only-mode    # force every subagent to Sonnet
    rm     ~/.claude/state/sonnet-only-mode     # back to smart routing

This file is unwired from settings.json. It remains only so any stray reference
fails open instead of erroring. It always allows the call unchanged.
"""
from __future__ import annotations

import sys


def main() -> int:
    # Drain stdin (hook contract) and allow unchanged. No-op by design.
    try:
        sys.stdin.read()
    except Exception:
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
