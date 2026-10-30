"""Pin the plan tier / usage guard for one test. Writes into CLAUDE_HOOK_STATE_DIR (set by conftest).

Shared by hooks/tests/* and tests/* (sys.path.insert this directory, then `import tier_fixture as TF`).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def state_dir() -> Path:
    d = Path(os.environ["CLAUDE_HOOK_STATE_DIR"])
    d.mkdir(parents=True, exist_ok=True)
    return d


def set_tier(tier: str, detected_at: float | None = None) -> Path:
    p = state_dir() / "plan-tier.json"
    p.write_text(json.dumps({"schema": 1, "tier": tier, "source": "credentials",
                             "detected_at": time.time() if detected_at is None else detected_at}),
                 encoding="utf-8")
    return p


def set_usage(pct: float | None, resets_at=None, sid: str = "t1", age_s: float = 0.0) -> Path:
    """One bridge file; pct None removes every bridge file and the usage-guard state."""
    b = state_dir() / "session-bridge"
    b.mkdir(exist_ok=True)
    if pct is None:
        for f in b.glob("*.json"):
            f.unlink()
        (state_dir() / "usage-guard.json").unlink(missing_ok=True)
        return b
    p = b / f"{sid}.json"
    p.write_text(json.dumps({"sid": sid, "five_hour_pct": pct, "five_hour_resets_at": resets_at}),
                 encoding="utf-8")
    t = time.time() - age_s
    os.utime(p, (t, t))
    return p


def clear() -> None:
    for name in ("plan-tier.json", "usage-guard.json"):
        (state_dir() / name).unlink(missing_ok=True)
    set_usage(None)
