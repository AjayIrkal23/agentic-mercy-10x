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

Pass order (B1-17): (1) gates and mutators, sequential and interleaved in declared
order (a mutator feeds the gates after it, not before); (2) execs; (3) advisories in
parallel. A ``"defer": true`` advisory (tdd-guard) is spawned detached instead and its
text is delivered by the next PreToolUse/PostToolUse dispatch of that session; ``--only``
runs it synchronously (the mod's async lane needs the answer).

Link types (declared per link):
  gate      sequential; may emit ``permissionDecision: deny|ask``. A deny ends the
            chain at once; its reason carries earlier gate notes and any held ask.
            An ask is held while later gates run (a later deny wins), then pauses
            the call. Gate notes sort before advisories under the char cap, which
            cuts on a line boundary. NEVER budget-dropped.
  mutator   sequential; may emit ``updatedInput`` (opus-guard, workflow-model-guard);
            threaded forward into later links. Only a Bash ``command`` with control
            characters is dropped (the harness rejects it); Agent/Workflow prompts
            legitimately contain newlines and always pass through.
  advisory  run in a ThreadPool in parallel; ``additionalContext`` merged in
            priority order; skipped once the ms budget is blown.
  exec      side effect (journals, trackers); output ignored (still telemetered).
            Waited on (bounded by ``timeout_ms``) unless the link sets
            ``"async": true`` — then it is spawned detached and never waited on.

Top-level ``{"decision":"block"}`` from a gate short-circuits Stop, ConfigChange and
TeammateIdle (TeammateIdle exits 2 with the reason on stderr to keep the teammate
working). A Stop gate's ``systemMessage`` is passed through when nothing blocks.

Mod bridge (``mods/mercy``): when the mod owns links for this session it sets
``MERCY_MOD_OWNED`` (comma-separated link ids) and ``MERCY_MOD_SESSION`` (the owning
session id) in the Claude Code process env, which every hook inherits. Links in that
set are skipped here, but only for that session's payloads, so a nested ``claude``
without the mod still runs everything. ``dispatch.py <event> --only id1,id2`` runs just
those links (ownership ignored): that is how the mod runs an owned link when it can
fire, synchronously or in the background. No env set → behaviour is unchanged.
Rows of ``--only`` runs carry ``via: "mod"``; ``MERCY_MOD_FAILED`` hands one call's links
back (see ``_mod_owned``).

lean-ctx ``ctx_shell`` / ``shell`` / ``ctx_patch`` (and ``ctx_call`` wrapping them) are
reshaped into Bash / Edit / Write payloads by ``dispatch_support.adapt`` so every gate
and post-write link sees them (B1-04); rows carry ``adapted_from``.

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
try:
    import dispatch_support as _sup
except Exception:  # noqa: BLE001
    _sup = None  # type: ignore

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
    "subagent-start": "SubagentStart",
    "post-compact": "PostCompact",
    "config-change": "ConfigChange",
    "teammate-idle": "TeammateIdle",
    "post-tool-use-failure": "PostToolUseFailure",
}

# events whose gates answer with a top-level {"decision":"block","reason":...}
_TOP_LEVEL_BLOCK_EVENTS = ("stop", "config-change", "teammate-idle")
# events whose harness schema rejects hookSpecificOutput. PostCompact stdout only
# reaches the user as a display message — post-compaction state is re-injected
# from SessionStart(source=="compact") instead (session-lifecycle.py).
_NO_HSO_EVENTS = ("SessionEnd", "PreCompact", "PostCompact", "Stop", "SubagentStop",
                  "ConfigChange", "TeammateIdle")

# Defaults if the config omits a budget for an event (SOFT — advisory-only).
_DEFAULT_BUDGET = {"ms": 2500, "chars": 4000}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
_CUR_TOOL = ""  # set per dispatch(); stamped on every telemetry row
_ROW_EXTRA: dict = {}  # per dispatch(): via="mod" for --only runs, adapted_from=<lean-ctx tool>


def _telemeter(event: str, link_id: str, **fields) -> None:
    if _tel is None:
        return
    fields.setdefault("tool", _CUR_TOOL)
    for k, v in _ROW_EXTRA.items():
        fields.setdefault(k, v)
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
        return re.fullmatch(f"(?:{pat})", tool) is not None
    except re.error:
        return True  # a bad regex must not silently drop a trigger


def _spawn_async(link: dict, event: str, payload_text: str, sid: str) -> None:
    """Fire-and-forget: detached child, payload on stdin, never waited on."""
    lid = link.get("id", "?")
    try:
        proc = subprocess.Popen(  # noqa: S603 - trusted internal command lists
            _resolve_cmd(link.get("cmd", [])), stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True, text=True,
        )
        try:
            proc.stdin.write(payload_text)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        _telemeter(event, lid, decision="spawned", session=sid, type="exec")
    except Exception as exc:  # noqa: BLE001
        _telemeter(event, lid, decision="error", session=sid, type="exec",
                   error=f"{type(exc).__name__}: {exc}"[:300])


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
        # raw text of a crashed link (a traceback) never reaches the model (B1-15)
        return parsed, (out if proc.returncode == 0 else "")
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


_MOD_BEAT_MAX_AGE_S = 120  # the mod refreshes MERCY_MOD_BEAT on every tool event


def _mod_owned(payload: dict) -> frozenset:
    """Link ids the mercy mod runs itself for this payload's session (empty otherwise).

    Ownership needs a fresh heartbeat: if the mod is unloaded mid-session (a remote
    rollout switch, a crash), its env vars linger but the beat ages, and every link
    runs here again within two minutes.

    Hand-back (B1-06): ``MERCY_MOD_FAILED=<tool_use_id>:id,id`` means the mod's run of
    those ids failed for that call (set before handing the call on, so Python runs them
    now). A full release clears ``MERCY_MOD_OWNED`` itself."""
    owner = os.environ.get("MERCY_MOD_SESSION", "")
    sid = str(payload.get("session_id") or "")
    if not owner or owner != sid:
        return frozenset()
    try:
        age_s = time.time() - float(os.environ.get("MERCY_MOD_BEAT", "0")) / 1000.0
    except ValueError:
        return frozenset()
    if not 0 <= age_s <= _MOD_BEAT_MAX_AGE_S:
        return frozenset()
    owned = _ids(os.environ.get("MERCY_MOD_OWNED", ""))
    tu, _, failed = os.environ.get("MERCY_MOD_FAILED", "").partition(":")
    if tu and tu == str(payload.get("tool_use_id") or ""):
        owned -= _ids(failed)
    return owned


def _ids(text: str) -> frozenset:
    return frozenset(x.strip() for x in (text or "").split(",") if x.strip())


def _cap(text: str, limit: int) -> str:
    """Line-boundary cut with a ``[truncated]`` marker (B1-16)."""
    if _sup is not None:
        return _sup.cap(text, limit)
    return text[:limit] if limit else text


def _has_hidden_control_chars(obj) -> bool:
    """True if any string in a (possibly nested) tool_input contains a C0 control
    character (newline/carriage-return/etc., excluding tab) that the harness
    rejects in an updatedInput as "control characters hidden in the approval
    dialog". Used to drop a mutator's rewrite that would fail validation — the
    ORIGINAL command (already accepted by the harness) then runs unmodified.
    """
    if isinstance(obj, str):
        return any((ord(c) < 0x20 and c != "\t") or ord(c) == 0x7F for c in obj)
    if isinstance(obj, dict):
        return any(_has_hidden_control_chars(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_has_hidden_control_chars(v) for v in obj)
    return False


# --------------------------------------------------------------------------- #
# main dispatch
# --------------------------------------------------------------------------- #
_TOOL_EVENTS = ("pre-tool-use", "post-tool-use", "post-tool-use-failure")


def dispatch(event: str, payload: dict, cfg: dict, only: frozenset | None = None) -> dict:
    """Run ``event``'s chain. A lean-ctx write/shell call is first reshaped into the
    Bash / Edit / Write payloads the gates read (B1-04), one run per touched path."""
    global _ROW_EXTRA
    _ROW_EXTRA = {"via": "mod"} if only is not None else {}
    adapted = _sup.adapt(payload) if (_sup and event in _TOOL_EVENTS) else None
    if not adapted:
        return _dispatch_one(event, payload, cfg, only, drain=True)
    _ROW_EXTRA["adapted_from"] = _tool_name(payload)
    results = [_dispatch_one(event, p, cfg, only, drain=(i == 0), adapted=True)
               for i, p in enumerate(adapted)]
    for dec in ("deny", "ask"):
        for r in results:
            hso = r.get("hookSpecificOutput") or {}
            if hso.get("permissionDecision") == dec:
                # the other paths' context (incl. advisories drained on path 1) rides along,
                # else it is lost: the queue file is already gone (Santa H2)
                rest = [(x.get("hookSpecificOutput") or {}).get("additionalContext", "")
                        for x in results if x is not r]
                key = "permissionDecisionReason" if dec == "deny" else "additionalContext"
                hso[key] = "\n\n".join(c for c in [hso.get(key, "")] + rest if c)
                return r
    merged = "\n\n".join(c for c in ((r.get("hookSpecificOutput") or {}).get("additionalContext", "")
                                     for r in results) if c)
    if not merged:
        return {}
    return {"hookSpecificOutput": {"hookEventName": _EVENT_NAME.get(event, event),
                                   "additionalContext": merged}}


def _dispatch_one(event: str, payload: dict, cfg: dict, only: frozenset | None = None,
                  drain: bool = False, adapted: bool = False) -> dict:
    global _CUR_TOOL
    event_name = _EVENT_NAME.get(event, event)
    sid = str(payload.get("session_id") or payload.get("session") or "")
    tool = _tool_name(payload)
    _CUR_TOOL = tool

    chain = (cfg.get("chains", {}) or {}).get(event, []) or []
    budget = (cfg.get("budgets", {}) or {}).get(event, _DEFAULT_BUDGET)
    ms_budget = float(budget.get("ms", _DEFAULT_BUDGET["ms"]))
    char_cap = int(budget.get("chars", _DEFAULT_BUDGET["chars"]))

    # split links by type, preserving declared order, applying enable + tool filter;
    # `only` (the mod's --only run) selects links; otherwise mod-owned links are skipped.
    # An adapted lean-ctx call is never owned: the mod plans by the real tool name.
    owned = frozenset() if (only is not None or adapted) else _mod_owned(payload)
    active = [ln for ln in chain
              if ln.get("enabled", True) and _link_matches(ln, tool)
              and (only is None or ln.get("id") in only)
              and ln.get("id") not in owned]

    contexts: list[tuple[int, str]] = []
    if drain and only is None and _sup and event in ("user-prompt-submit", "pre-tool-use", "post-tool-use"):
        # advisories of deferred links (tdd-guard) from earlier calls (B1-02), and Stop-gate
        # notes for the model (CLAUDE.md §11) — the prompt delivers them before any tool runs
        contexts += [(1, "[Deferred advisory from an earlier write]\n" + c) for c in _sup.drain(sid)]
    updated_input = None
    system_message = ""     # Stop gates may emit a non-blocking systemMessage
    held_ask = None         # (reason, link id): later gates still run, a later deny wins (B1-07)
    # ASCII-escaped JSON: link stdin (and our stdout) encode with the console codepage
    # when PYTHONUTF8 is unset, and cp1252 cannot encode "→" — every link errored.
    payload_text = json.dumps(payload)
    t_start = time.perf_counter()

    def _ms() -> float:
        return round((time.perf_counter() - t_start) * 1000, 2)

    # ---- pass 1: sequential gates + mutators (in declared order) ---------- #
    advisory_links = []
    exec_links = []
    for ln in active:
        typ = ln.get("type", "advisory")
        if typ == "gate":
            parsed, _ = _run_link(ln, event, payload_text, sid)
            if event in _TOP_LEVEL_BLOCK_EVENTS and isinstance(parsed, dict):
                if parsed.get("decision") == "block":
                    _telemeter(event, "_dispatch", decision="block", session=sid, ms=_ms(),
                               note=f"short-circuit@{ln.get('id')}")
                    return {
                        "decision": "block",
                        "reason": str(parsed.get("reason") or ""),
                    }
                if parsed.get("systemMessage") and not system_message:
                    system_message = str(parsed["systemMessage"])
            dec, reason = ((None, None) if event in _TOP_LEVEL_BLOCK_EVENTS
                           else _extract_decision(parsed))
            if dec == "deny":
                # a deny ends the chain; earlier gate notes and a held ask ride along
                _telemeter(event, "_dispatch", decision=dec, session=sid, ms=_ms(),
                           note=f"short-circuit@{ln.get('id')}")
                notes = [c for _, c in sorted(contexts, key=lambda p: p[0])]
                if held_ask:
                    notes.append(f"(an earlier gate, {held_ask[1]}, also asked: {held_ask[0]})")
                if notes:
                    reason = f"{reason}\n\nEarlier gate notes:\n" + "\n\n".join(notes)
                return {"hookSpecificOutput": {
                    "hookEventName": event_name,
                    "permissionDecision": dec,
                    "permissionDecisionReason": _cap(reason, char_cap),
                }}
            if dec == "ask" and held_ask is None:
                held_ask = (reason, ln.get("id", "?"))
            ctx = _extract_context(parsed)
            if ctx:  # gate notes outrank advisories under the char cap (B1-16)
                contexts.append((int(ln.get("priority", -1)), ctx))
        elif typ == "mutator":
            parsed, _ = _run_link(ln, event, payload_text, sid)
            ui = _extract_updated_input(parsed)
            if ui is not None:
                if tool == "Bash" and _has_hidden_control_chars(
                        ui.get("command") if isinstance(ui, dict) else ui):
                    # A Bash `command` rewrite with control chars fails the harness
                    # approval check — DROP it; the original command runs unmodified.
                    # Only Bash: Agent/Workflow prompts legitimately carry newlines
                    # (dropping those made opus-guard inert, A01-B1).
                    _telemeter(event, ln.get("id", "?"), decision="mutation-dropped",
                               session=sid, note="control-chars-in-bash-command")
                else:
                    # A mutator's own permissionDecision:"allow" is NOT forwarded:
                    # the harness applies a bare updatedInput (hookUpdatedInput) and
                    # the normal permission flow still runs (Santa P2).
                    updated_input = ui
                    # thread the mutation forward
                    newp = dict(payload)
                    newp["tool_input"] = ui
                    payload_text = json.dumps(newp)
            ctx = _extract_context(parsed)
            if ctx:
                contexts.append((int(ln.get("priority", 5)), ctx))
        elif typ == "exec":
            exec_links.append(ln)
        else:  # advisory
            advisory_links.append(ln)

    if held_ask is not None:
        # an ask still pauses the call: execs and advisories wait for the answer, as before
        _telemeter(event, "_dispatch", decision="ask", session=sid, ms=_ms(),
                   note=f"short-circuit@{held_ask[1]}")
        hso = {"hookEventName": event_name, "permissionDecision": "ask",
               "permissionDecisionReason": held_ask[0]}
        notes = "\n\n".join(c for _, c in sorted(contexts, key=lambda p: p[0]))
        if notes:
            hso["additionalContext"] = _cap(notes, char_cap)
        if updated_input is not None:
            hso["updatedInput"] = updated_input
        return {"hookSpecificOutput": hso}

    # ---- deferred advisories: detached, delivered on a later call (B1-02) - #
    if only is None and sid and _sup:
        keep = []
        for ln in advisory_links:
            if ln.get("defer") and _sup.spawn_deferred(
                    _resolve_cmd(ln.get("cmd", [])), float(ln.get("timeout_ms", 5000)) / 1000.0,
                    payload_text, sid, event, ln.get("id", "?")):
                _telemeter(event, ln.get("id", "?"), decision="deferred", session=sid,
                           type="advisory", ms=0)
            else:
                keep.append(ln)
        advisory_links = keep

    # ---- pass 2: execs (async ones detached; the rest bounded by timeout) -- #
    for ln in exec_links:
        if ln.get("async"):
            _spawn_async(ln, event, payload_text, sid)
        else:
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
                               budget_hit=True, session=sid, ms=0)
            run_now = [ln for ln in advisory_links if int(ln.get("priority", 5)) == 0]
        if run_now:
            try:
                # imported here: concurrent.futures costs ~10 ms of the 35 ms dispatcher
                # start, and most dispatches have no advisory left to run
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=min(8, len(run_now))) as pool:
                    futs = {pool.submit(_run_link, ln, event, payload_text, sid): ln
                            for ln in run_now}
                    for fut, ln in list(futs.items()):
                        try:
                            parsed, raw = fut.result(timeout=float(ln.get("timeout_ms", 5000)) / 1000.0 + 1)
                        except Exception:  # noqa: BLE001
                            parsed, raw = None, ""
                        ctx = _extract_context(parsed)
                        if not ctx and parsed is None and raw and raw.strip():
                            # advisory links may emit RAW TEXT (not JSON) meant to
                            # be injected — legacy Claude Code injects UserPromptSubmit
                            # stdout verbatim (e.g. discovery-skills-reminder.sh).
                            # Preserve it so no advisory is lost through dispatch.
                            ctx = raw.strip()[:8000]
                        if ctx:
                            contexts.append((int(ln.get("priority", 5)), ctx))
            except Exception:  # noqa: BLE001
                pass

    # ---- assemble the single merged response ------------------------------ #
    contexts.sort(key=lambda p: p[0])  # gate notes (-1), then priority 0 first
    merged = _cap("\n\n".join(c for _, c in contexts if c).strip(), char_cap)
    total_ms = round((time.perf_counter() - t_start) * 1000, 2)
    if total_ms > ms_budget:
        _telemeter(event, "_dispatch", decision="budget-overrun",
                   ms=total_ms, budget_hit=True, session=sid)

    # Stop accepts only a top-level block or a systemMessage. Advisory text and
    # the permissionDecision schema belong to other hook events.
    if event in ("stop", "teammate-idle"):
        return {"systemMessage": system_message} if system_message else {}

    # Harness schema: hookSpecificOutput is invalid for several events, and an
    # empty one (no additionalContext/updatedInput) fails validation elsewhere —
    # emit it only when there is real content for an event that accepts it.
    if event_name in _NO_HSO_EVENTS or (not merged and updated_input is None):
        return {}
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
        try:  # Claude Code writes UTF-8; the console codepage (cp1252) would garble it
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # a StringIO stdin in tests
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
        only = None
        if len(argv) >= 2 and argv[1] == "--only":
            only = _ids(argv[2] if len(argv) >= 3 else "")
            if not only:  # a bare --only selects nothing; it must never run the whole chain
                print("{}")
                return 0
        result = dispatch(event, payload, cfg, only)
        if event == "teammate-idle" and result.get("decision") == "block":
            # exit 2 + stderr = keep the teammate working (TeammateIdle contract)
            print(result.get("reason") or "expected artifact missing", file=sys.stderr)
            return 2
        print(json.dumps(result))  # ASCII-escaped: a cp1252 stdout cannot print "→"
        return 0
    except Exception:  # noqa: BLE001 - the dispatcher must never brick a session
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
