"""persist_common.py — per-session dedup ledger + CODEX append primitive.

The three Stop/post persistence writers this once served are down to one
(``codex-capture.py``; the memory writers were deleted 2026-09-27, D9). The
ledger stays so any future writer dedups the same way.

``already_persisted`` is a pure CHECK. Call ``mark_persisted`` only AFTER the
real write succeeded, so a failed write is retried on the next attempt (the old
check-and-record-in-one-call suppressed retries).

Ledger: ``state/persist-dedup/<session>.json``, content-hash keyed. Pure stdlib;
never raises.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001 - stdlib `platform` is NOT a substitute
    _plat = None  # type: ignore


def _state_dir() -> Path:
    if _plat is not None:
        return _plat.state_dir()
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    d = (Path(env).expanduser() if env else Path("~/.claude").expanduser()) / "state"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def _atomic_write(path: Path, data: str) -> bool:
    if _plat is not None:
        return _plat.atomic_write(path, data)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(data, encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _safe(s: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (s or "nosession"))[:80]


def _ledger_path(session_id: str) -> Path:
    d = _state_dir() / "persist-dedup"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d / f"{_safe(session_id)}.json"


def _digest(kind: str, content: str) -> str:
    return hashlib.sha1(f"{kind}\x00{content}".encode("utf-8", "replace")).hexdigest()


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"seen": {}, "ts": time.time()}
    except (OSError, ValueError):
        return {"seen": {}, "ts": time.time()}


def already_persisted(session_id: str, kind: str, content: str) -> bool:
    """True if (kind, content) was already marked persisted this session.
    Pure check — never records. Fail-open: any error -> False."""
    try:
        seen = _load(_ledger_path(session_id)).get("seen") or {}
        return _digest(kind, content) in seen
    except Exception:  # noqa: BLE001
        return False


def mark_persisted(session_id: str, kind: str, content: str) -> bool:
    """Record (kind, content) as persisted. Call AFTER the real write succeeded."""
    try:
        path = _ledger_path(session_id)
        led = _load(path)
        led.setdefault("seen", {})[_digest(kind, content)] = round(time.time(), 3)
        return _atomic_write(path, json.dumps(led, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        return False


def append_codex(codex_path: str | Path, section: str, text: str, session_id: str) -> bool:
    """Append ``- [date] text`` under an EXISTING ``## section`` heading in CODEX.md
    (a new heading is added at the end only when the section is missing). Deduped
    per session; marked persisted only after the write succeeds. Never raises."""
    try:
        kind = f"codex:{section}"
        if already_persisted(session_id, kind, text):
            return False
        p = Path(codex_path)
        prior = p.read_text(encoding="utf-8") if p.is_file() else "# CODEX.md\n"
        bullet = f"- [{time.strftime('%Y-%m-%d')}] {text.strip()}"
        heading = f"## {section}"
        lines = prior.splitlines()
        start = next((i for i, ln in enumerate(lines) if ln.strip() == heading), None)
        if start is None:
            new = prior.rstrip("\n") + f"\n\n{heading}\n{bullet}\n"
        else:
            end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
                       len(lines))
            while end > start + 1 and not lines[end - 1].strip():
                end -= 1  # insert before the section's trailing blank lines
            lines.insert(end, bullet)
            new = "\n".join(lines) + "\n"
        ok = _atomic_write(p, new)
        if ok:
            mark_persisted(session_id, kind, text)
        return ok
    except Exception:  # noqa: BLE001
        return False


__all__ = ["already_persisted", "mark_persisted", "append_codex"]
