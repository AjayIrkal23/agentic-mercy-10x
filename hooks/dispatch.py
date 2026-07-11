#!/usr/bin/env python3
"""dispatch.py — the universal event chain-runner (P4-T1, Charter §3).

ONE process per hook event. Registered once per event in ``settings.json``:

    python3 ~/.claude/hooks/dispatch.py <event>

Every legacy hook becomes a *link* in an ordered, config-driven chain declared
in ``hooks/dispatch.config.json``. dispatch.py is a faithful **multiplexer**: it
runs each link exactly as ``settings.json`` ran it before (each link is still its
own ``.py``/``.js``/binary, invoked as a subprocess — Charter §3 "orchestration,
NOT fusion; every hook stays its own file"), and merges the results into the one
response the harness expects for that event.

What the orchestration layer adds on top of the old N-registrations-per-event:
  * per-link ``try/except`` isolation — one link's crash logs to telemetry and
    the chain continues (never takes down its siblings);
  * per-link ``enabled: true|false`` flag in the config;
  * per-link ``tools:`` regex (replaces the 19 separate PreToolUse matchers);
  * every link fire telemetry-logged from day 1 via ``lib/hook_telemetry.py``;
  * SOFT per-event ms budgets — overruns are logged; **gates, mutators and execs
    are NEVER budget-dropped**, only the lowest-priority *advisory* links are
    skipped once the wall budget is blown (and the skip is telemetered);
  * ``{PY}`` / ``{NODE}`` / ``{HOOKS}`` / ``{HOME}`` resolution via ``lib/platform.py``.

Link types (declared per link):
  gate      sequential; may emit ``permissionDecision: deny|ask``; first deny/ask
            short-circuits the chain; NEVER budget-dropped.
  mutator   sequential; may emit ``updatedInput`` (opus-guard, workflow-model-guard,
            lean-ctx rewrite/redirect); threaded forward into later links.
  advisory  run in a ThreadPool in parallel; ``additionalContext`` merged in
            priority order; skipped once the ms budget is blown.
  exec      fire-and-forget side effect (journals, trackers, lean-ctx observe);
            output ignored (still telemetered).

Fail-open at every level: any internal error prints ``{}`` (allow) so a broken
dispatcher can never brick a session.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

try:  # shared foundation; never let an import failure brick the hook
    from lib import platform as _plat
    from lib import hook_telemetry as _tel
except Exception:  # noqa: BLE001
    _plat = None  # type: ignore
    _tel = None  # type: ignore

CONFIG = _HOOKS / "dispatch.config.json"

# event token (argv) -> hookEventName (harness schema)
_EVENT_NAME = {
    "session-start": "SessionStart",
    "user-prompt-submit": "UserPromptSubmit",
    "pre-tool-use": "PreToolUse",
    "post-tool-use": "PostToolUse",
    "stop": "Stop",
    "subagent-stop": "SubagentStop",
    "pre-compact": "PreCompact",
    "session-end": "SessionEnd",
}

# Defaults if the config omits a budget for an event (SOFT — advisory-only).
_DEFAULT_BUDGET = {"ms": 2500, "chars": 4000}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _telemeter(event: str, link_id: str, **fields) -> None:
    if _tel is None:
        return
    try:
        _tel.record(event, link_id, **fields)
    except Exception:  # noqa: BLE001
        pass


def _resolve_cmd(cmd) -> list:
    """Materialize ``{PY}``/``{NODE}``/``{HOOKS}``/``{HOME}`` placeholders."""
    py = _plat.python_exe() if _plat else (sys.executable or "python3")
    node = (_plat.node_exe() if _plat else None) or "node"
    hooks = str(_HOOKS)
    home = os.path.expanduser("~")
    subs = {"PY": py, "NODE": node, "HOOKS": hooks, "HOME": home}
    out = []
    for part in cmd:
        s = str(part)
        for k, v in subs.items():
            s = s.replace("{" + k + "}", v)
        out.append(s)
    return out


def _tool_name(payload: dict) -> str:
    return str(payload.get("tool_name") or payload.get("tool") or "")


def _link_matches(link: dict, tool: str) -> bool:
    pat = link.get("tools")
    if not pat:
        return True  # no tool filter -> always applies (session/stop/etc.)
    try:
        return re.search(pat, tool) is not None
    except re.error:
        return True  # a bad regex must not silently drop a trigger


def _run_link(link: dict, event: str, payload_text: str, sid: str):
    """Run one link as a subprocess. Returns (parsed_json_or_None, chars_out).

    Never raises — a crash is caught, telemetered, and reported as error.
    """
    lid = link.get("id", "?")
    cmd = _resolve_cmd(link.get("cmd", []))
    timeout = float(link.get("timeout_ms", 5000)) / 1000.0
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(  # noqa: S603 - trusted internal command lists
            cmd, input=payload_text, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
        out = proc.stdout or ""
        ms = round((time.perf_counter() - t0) * 1000, 2)
        parsed = None
        s = out.strip()
        if s.startswith("{"):
            try:
                parsed = json.loads(s)
            except (ValueError, TypeError):
                parsed = None
        decision = "run"
        if isinstance(parsed, dict):
            hso = parsed.get("hookSpecificOutput", {}) or {}
            decision = hso.get("permissionDecision") or parsed.get("permissionDecision") or "run"
        _telemeter(event, lid, ms=ms, exit=proc.returncode,
                   chars_out=len(out), decision=decision, session=sid,
                   type=link.get("type"))
        return parsed, out
    except subprocess.TimeoutExpired:
        ms = round((time.perf_counter() - t0) * 1000, 2)
        _telemeter(event, lid, ms=ms, exit=124, chars_out=0,
                   decision="timeout", session=sid, type=link.get("type"),
                   error="timeout")
        return None, ""
    except Exception as exc:  # noqa: BLE001 - one link never stops the chain
        ms = round((time.perf_counter() - t0) * 1000, 2)
        _telemeter(event, lid, ms=ms, exit=1, chars_out=0, decision="error",
                   session=sid, type=link.get("type"), error=f"{type(exc).__name__}: {exc}"[:300])
        return None, ""


def _extract_context(parsed) -> str:
    if not isinstance(parsed, dict):
        return ""
    hso = parsed.get("hookSpecificOutput")
    if isinstance(hso, dict) and hso.get("additionalContext"):
        return str(hso["additionalContext"])
    if parsed.get("additionalContext"):
        return str(parsed["additionalContext"])
    # safety net: some legacy hooks still emit the non-standard followup_message
    # key (bash-write-gate was fixed in P4-T3; this catches any stragglers so a
    # trigger is never silently dropped through the dispatcher).
    if parsed.get("followup_message"):
        return str(parsed["followup_message"])
    return ""


def _extract_decision(parsed):
    """Return (decision, reason) if this link denies/asks, else (None, None)."""
    if not isinstance(parsed, dict):
        return None, None
    hso = parsed.get("hookSpecificOutput", {}) or {}
    dec = hso.get("permissionDecision") or parsed.get("permissionDecision")
    if dec in ("deny", "ask"):
        reason = (hso.get("permissionDecisionReason")
                  or parsed.get("permissionDecisionReason") or "")
        return dec, reason
    return None, None


def _extract_updated_input(parsed):
    if not isinstance(parsed, dict):
        return None
    hso = parsed.get("hookSpecificOutput", {}) or {}
    return hso.get("updatedInput") or parsed.get("updatedInput")


# --------------------------------------------------------------------------- #
# main dispatch
# --------------------------------------------------------------------------- #
def dispatch(event: str, payload: dict, cfg: dict) -> dict:
    event_name = _EVENT_NAME.get(event, event)
    sid = str(payload.get("session_id") or payload.get("session") or "")
    tool = _tool_name(payload)

    chain = (cfg.get("chains", {}) or {}).get(event, []) or []
    budget = (cfg.get("budgets", {}) or {}).get(event, _DEFAULT_BUDGET)
    ms_budget = float(budget.get("ms", _DEFAULT_BUDGET["ms"]))
    char_cap = int(budget.get("chars", _DEFAULT_BUDGET["chars"]))

    # split links by type, preserving declared order, applying enable + tool filter
    active = [ln for ln in chain
              if ln.get("enabled", True) and _link_matches(ln, tool)]
    for ln in chain:
        if not ln.get("enabled", True):
            _telemeter(event, ln.get("id", "?"), decision="disabled", session=sid)

    contexts: list[tuple[int, str]] = []
    updated_input = None
    payload_text = json.dumps(payload, ensure_ascii=False)
    t_start = time.perf_counter()

    # ---- pass 1: sequential gates + mutators (in declared order) ---------- #
    advisory_links = []
    exec_links = []
    for ln in active:
        typ = ln.get("type", "advisory")
        if typ == "gate":
            parsed, _ = _run_link(ln, event, payload_text, sid)
            dec, reason = _extract_decision(parsed)
            if dec is not None:
                # short-circuit: emit the deny/ask decision now
                _telemeter(event, "_dispatch", decision=dec, session=sid,
                           note=f"short-circuit@{ln.get('id')}")
                return {"hookSpecificOutput": {
                    "hookEventName": event_name,
                    "permissionDecision": dec,
                    "permissionDecisionReason": reason,
                }}
            ctx = _extract_context(parsed)
            if ctx:
                contexts.append((int(ln.get("priority", 5)), ctx))
        elif typ == "mutator":
            parsed, _ = _run_link(ln, event, payload_text, sid)
            ui = _extract_updated_input(parsed)
            if ui is not None:
                updated_input = ui
                # thread the mutation forward
                newp = dict(payload)
                newp["tool_input"] = ui
                payload_text = json.dumps(newp, ensure_ascii=False)
            ctx = _extract_context(parsed)
            if ctx:
                contexts.append((int(ln.get("priority", 5)), ctx))
        elif typ == "exec":
            exec_links.append(ln)
        else:  # advisory
            advisory_links.append(ln)

    # ---- pass 2: execs (fire-and-forget, but telemetered) ----------------- #
    for ln in exec_links:
        _run_link(ln, event, payload_text, sid)

    # ---- pass 3: advisory links in a ThreadPool, budget-aware ------------- #
    over_budget = (time.perf_counter() - t_start) * 1000.0 > ms_budget
    if advisory_links:
        run_now = advisory_links
        if over_budget:
            # gates/mutators already blew the wall budget: only run the
            # highest-priority advisory (mandatory-trigger) links, drop the rest.
            for ln in advisory_links:
                if int(ln.get("priority", 5)) > 0:
                    _telemeter(event, ln.get("id", "?"), decision="skip-budget",
                               budget_hit=True, session=sid)
            run_now = [ln for ln in advisory_links if int(ln.get("priority", 5)) == 0]
        if run_now:
            try:
                with ThreadPoolExecutor(max_workers=min(8, len(run_now))) as pool:
                    futs = {pool.submit(_run_link, ln, event, payload_text, sid): ln
                            for ln in run_now}
                    for fut, ln in list(futs.items()):
                        try:
                            parsed, _ = fut.result(timeout=float(ln.get("timeout_ms", 5000)) / 1000.0 + 1)
                        except Exception:  # noqa: BLE001
                            parsed = None
                        ctx = _extract_context(parsed)
                        if ctx:
                            contexts.append((int(ln.get("priority", 5)), ctx))
            except Exception:  # noqa: BLE001
                pass

    # ---- assemble the single merged response ------------------------------ #
    contexts.sort(key=lambda p: p[0])  # priority 0 first
    merged = "\n\n".join(c for _, c in contexts if c).strip()
    if char_cap and len(merged) > char_cap:
        merged = merged[:char_cap]
    total_ms = round((time.perf_counter() - t_start) * 1000, 2)
    if total_ms > ms_budget:
        _telemeter(event, "_dispatch", decision="budget-overrun",
                   ms=total_ms, budget_hit=True, session=sid)

    out: dict = {"hookSpecificOutput": {"hookEventName": event_name}}
    if merged:
        out["hookSpecificOutput"]["additionalContext"] = merged
    if updated_input is not None:
        out["hookSpecificOutput"]["updatedInput"] = updated_input
    return out


def main(argv: list[str]) -> int:
    try:
        event = argv[0] if argv else ""
        if event not in _EVENT_NAME:
            print("{}")
            return 0
        try:
            raw = sys.stdin.read() or "{}"
        except Exception:  # noqa: BLE001
            raw = "{}"
        try:
            payload = json.loads(raw) if raw.strip().startswith("{") else {}
        except (ValueError, TypeError):
            payload = {}
        try:
            cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            print("{}")
            return 0
        result = dispatch(event, payload, cfg)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception:  # noqa: BLE001 - the dispatcher must never brick a session
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
