"""Neutralized daemon-refcount shim (P3-T2).

The refcounting this module used to perform (start/stop of per-project watch
services) was removed as part of the 2026-07-09 / 2026-07-11 daemon excision.
Index freshness is now handled event-driven by ``index-lifecycle.py`` (Spec B)
with detached single-shot builders and journal flushes — no persistent services.

These functions remain only as inert no-op stubs so any lingering importer keeps
working. The file is queued for attic (and deregistration of its last registered
importer, ``watch-daemon-session-end.py``) in HANDOFF-P4-registrations.md.
"""
from __future__ import annotations


def service_name(prefix, source_root):  # pragma: no cover - inert stub
    return ""


def acquire(prefix, source_root, session_id=""):  # pragma: no cover - inert stub
    """No-op. Formerly registered a session ref and started a watch service."""
    return ""


def release(prefix, source_root, session_id=""):  # pragma: no cover - inert stub
    """No-op. Formerly dropped a session ref and stopped an idle watch service."""
    return None
