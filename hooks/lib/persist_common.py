"""persist_common.py — one Memory/CODEX write primitive shared by the three
Stop/post persistence writers (P4-T6, audit C18).

Charter §3 keeps ``session-memory-writer.py``, ``session-learning-extractor.py``
and ``codex-capture.py`` as SEPARATE files/links (no fusion). This helper is the
single place that dedups their writes: each writer calls ``already_persisted``
before committing an observation/learning/decision, so the same content captured
by two overlapping writers is written ONCE, not twice — the double-write C18 fix
lives at the *write layer*, not by merging files.

Dedup is per-session (keyed by session id), content-hash based, stored under
``state/persist-dedup/<session>.json``. Pure stdlib; never raises.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    import platform as _plat  # type: ignore


def _safe(s: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (s or "nosession"))[:80]


def _ledger_path(session_id: str) -> Path:
    d = _plat.state_dir() / "persist-dedup"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d / f"{_safe(session_id)}.json"


def _digest(kind: str, content: str) -> str:
    return hashlib.sha1(f"{kind}\x00{content}".encode("utf-8", "replace")).hexdigest()


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"seen": {}, "ts": time.time()}


def already_persisted(session_id: str, kind: str, content: str, *, record: bool = True) -> bool:
    """Return True if (kind, content) was already persisted this session.

    ``kind`` groups the write surface ("memory", "codex-decision",
    "codex-learning"). When ``record`` is True and the content is new, it is
    marked so the next caller of the same content is deduped. Fail-open: on any
    error returns False (never suppresses a real write).
    """
    try:
        path = _ledger_path(session_id)
        led = _load(path)
        seen = led.setdefault("seen", {})
        h = _digest(kind, content)
        if h in seen:
            return True
        if record:
            seen[h] = round(time.time(), 3)
            _plat.atomic_write(path, json.dumps(led, ensure_ascii=False))
        return False
    except Exception:  # noqa: BLE001 - dedup must never break a persist
        return False


def append_codex(codex_path: str | Path, section: str, text: str, session_id: str) -> bool:
    """Append ``text`` under ``## section`` in CODEX.md, deduped per session.

    Returns True if written, False if skipped (duplicate) or on error.
    Never raises. Creates the file if missing.
    """
    try:
        if already_persisted(session_id, f"codex:{section}", text):
            return False
        p = Path(codex_path)
        prior = p.read_text(encoding="utf-8") if p.is_file() else "# CODEX.md\n"
        stamp = time.strftime("%Y-%m-%d")
        block = f"\n## {section}\n- [{stamp}] {text.strip()}\n"
        return _plat.atomic_write(p, prior + block)
    except Exception:  # noqa: BLE001
        return False


__all__ = ["already_persisted", "append_codex"]
