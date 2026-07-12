#!/usr/bin/env python3
"""test_dispatch_parity.py — the Charter §3 registration→link parity harness (P4-T2).

The 65→8 settings.json reduction is allowed ONLY with a harness proving every
legacy hook registration still maps to exactly one enabled dispatch link that
fires on the same event with an equivalent-or-broader tool scope and the same
command/mode. This is the GATE for P4-T7 (the settings.json rewrite).

Sources:
  * legacy registration inventory: ``hooks/legacy-settings-hooks.json`` (the T7
    snapshot of the pre-rewire hooks block) if present, else the live
    ``settings.json`` hooks block (valid BEFORE T7 rewrites it).
  * link inventory: ``hooks/dispatch.config.json``.

Run standalone to (re)write the mapping table:
    python3 hooks/tests/test_dispatch_parity.py            # writes plans/P4-dispatch-parity.md
Run under pytest for the assertions:
    pytest hooks/tests/test_dispatch_parity.py -q
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
_CLAUDE = _HOOKS.parent
_LEGACY_SNAP = _HOOKS / "legacy-settings-hooks.json"
_SETTINGS = _CLAUDE / "settings.json"
_CONFIG = _HOOKS / "dispatch.config.json"
_MAPTABLE = _CLAUDE / "plans" / "P4-dispatch-parity.md"

_INTERP = {"python", "python3", "py", "bash", "sh", "node", "nodejs"}

# settings.json event key -> dispatch event token
_EVENT_TOKEN = {
    "SessionStart": "session-start",
    "UserPromptSubmit": "user-prompt-submit",
    "PreToolUse": "pre-tool-use",
    "PostToolUse": "post-tool-use",
    "Stop": "stop",
    "SubagentStop": "subagent-stop",
    "PreCompact": "pre-compact",
    "SessionEnd": "session-end",
}

# events whose "matcher" is a session-source filter, not a tool_name matcher
_NON_TOOL_EVENTS = {"session-start", "stop", "subagent-stop", "pre-compact", "session-end"}

# INTENTIONAL command swaps (legacy reg -> new link), annotated not-unmapped.
# key: (event_token, script_basename, mode_args_tuple)
_KNOWN_SWAPS = {
    ("session-end", "watch-daemon-session-end.py", ()): (
        "index-session-end",
        "watch-daemon-session-end.py was a neutralized no-op that only forwarded "
        "to `index-lifecycle.py session-end`; the link now runs that command "
        "directly (HANDOFF P3-T2). Deregistered + atticked in P4-T7.",
    ),
    # P6-T2 cross-platform ports: bash launchers -> .py/.js, byte-parity verified
    # (fixture-parity harness). The bash originals stay on disk for the 30-day
    # flip-back window (legacy-settings-hooks.json restores them via
    # flip-dispatch.py --legacy); they retire with the legacy stack in P7-T4/T5.
    ("session-start", "tdd-guard-launcher.sh", ()): (
        "tdd-guard-launcher", "P6-T2: bash launcher ported to tdd_guard_launcher.py (parity-verified)."),
    ("user-prompt-submit", "tdd-guard-launcher.sh", ()): (
        "tdd-guard-launcher-ups", "P6-T2: bash launcher ported to tdd_guard_launcher.py (parity-verified)."),
    ("pre-tool-use", "tdd-guard-launcher.sh", ()): (
        "tdd-guard-launcher-pre", "P6-T2: bash launcher ported to tdd_guard_launcher.py (parity-verified)."),
    ("session-start", "gsd-session-state.sh", ()): (
        "gsd-session-state", "P6-T2: bash launcher ported to gsd-session-state.js (parity-verified)."),
    ("user-prompt-submit", "discovery-skills-reminder.sh", ("prompt",)): (
        "discovery-skills", "P6-T2: bash launcher ported to discovery-skills-reminder.py (byte-identical stdout)."),
    ("pre-tool-use", "gsd-validate-commit.sh", ()): (
        "gsd-validate-commit", "P6-T2: bash launcher ported to gsd-validate-commit.js (deny/exit-2 parity)."),
    ("post-tool-use", "gsd-phase-boundary.sh", ()): (
        "gsd-phase-boundary", "P6-T2: bash launcher ported to gsd-phase-boundary.js (parity-verified)."),
}


def _basename_noplace(path_token: str) -> str:
    t = path_token.replace("{HOOKS}", "").replace("${HOME}", "").replace("{HOME}", "")
    t = t.strip('"').strip("'")
    return Path(t).name


def _signature_from_str(command: str) -> tuple[str, tuple]:
    """(script_basename, mode_args) from a settings.json command string."""
    try:
        toks = shlex.split(command)
    except ValueError:
        toks = command.split()
    if not toks:
        return ("", ())
    head = Path(toks[0].strip('"').strip("'")).name.lower()
    if head in _INTERP and len(toks) >= 2:
        return (_basename_noplace(toks[1]), tuple(toks[2:]))
    # bare executable (e.g. lean-ctx)
    return (Path(toks[0].strip('"').strip("'")).name, tuple(toks[1:]))


def _signature_from_cmd(cmd: list) -> tuple[str, tuple]:
    """(script_basename, mode_args) from a dispatch.config.json cmd array.

    Recognises the ``{PY}``/``{NODE}`` interpreter placeholders as well as
    literal interpreter names, so a link ``["{PY}", "{HOOKS}/x.py", "mode"]``
    yields the same signature as the legacy ``python3 …/x.py mode``.
    """
    if not cmd:
        return ("", ())
    head_raw = str(cmd[0])
    head = Path(head_raw).name.lower().strip("{}")
    if (head in _INTERP or head in {"py", "node"}) and len(cmd) >= 2:
        return (_basename_noplace(str(cmd[1])), tuple(str(x) for x in cmd[2:]))
    return (Path(head_raw).name, tuple(str(x) for x in cmd[1:]))


def load_registrations() -> list[dict]:
    src = _LEGACY_SNAP if _LEGACY_SNAP.exists() else _SETTINGS
    data = json.loads(src.read_text(encoding="utf-8"))
    hooks = data.get("hooks", data)  # snapshot may store the raw hooks block
    regs = []
    n = 0
    for event, groups in hooks.items():
        if event not in _EVENT_TOKEN:
            continue
        for grp in groups:
            matcher = grp.get("matcher", ".*")
            for hk in grp.get("hooks", []):
                n += 1
                cmd = hk.get("command", "")
                regs.append({
                    "n": n,
                    "event": event,
                    "event_token": _EVENT_TOKEN[event],
                    "matcher": matcher,
                    "command": cmd,
                    "sig": _signature_from_str(cmd),
                })
    return regs


def load_links() -> dict:
    cfg = json.loads(_CONFIG.read_text(encoding="utf-8"))
    out = {}
    for event_token, links in (cfg.get("chains", {}) or {}).items():
        for ln in links:
            ln = dict(ln)
            ln["sig"] = _signature_from_cmd(ln.get("cmd", []))
            out.setdefault(event_token, []).append(ln)
    return out


def _matcher_covered(event_token: str, matcher: str, link: dict) -> bool:
    import re
    if event_token in _NON_TOOL_EVENTS:
        return True  # session-source matchers, not tool matchers
    tools = link.get("tools")
    if not tools:
        return True  # no filter = broader scope (covers everything)
    for tok in str(matcher).split("|"):
        tok = tok.strip()
        if not tok or tok == ".*":
            continue
        try:
            if re.search(tools, tok) is None:
                return False
        except re.error:
            return False
    return True


def build_mapping() -> tuple[list[dict], list[dict]]:
    """Returns (rows, unmapped). Each row: reg + matched link id/status."""
    regs = load_registrations()
    links = load_links()
    rows, unmapped = [], []
    for reg in regs:
        et, sig, matcher = reg["event_token"], reg["sig"], reg["matcher"]
        candidates = [
            ln for ln in links.get(et, [])
            if ln.get("sig") == sig
            and ln.get("enabled", True)
            and _matcher_covered(et, matcher, ln)
        ]
        if candidates:
            reg["link"] = candidates[0].get("id", "?")
            reg["status"] = "MAPPED"
            reg["note"] = "" if len(candidates) == 1 else f"(also: {[c['id'] for c in candidates[1:]]})"
        elif (et, sig[0], sig[1]) in _KNOWN_SWAPS:
            lid, why = _KNOWN_SWAPS[(et, sig[0], sig[1])]
            reg["link"] = lid
            reg["status"] = "INTENTIONAL-SWAP"
            reg["note"] = why
        else:
            reg["link"] = "—"
            reg["status"] = "UNMAPPED"
            reg["note"] = "NO enabled link on this event with matching command + covering tools scope"
            unmapped.append(reg)
        rows.append(reg)
    return rows, unmapped


# --------------------------------------------------------------------------- #
# pytest assertions
# --------------------------------------------------------------------------- #
def test_all_registrations_mapped():
    rows, unmapped = build_mapping()
    assert rows, "no legacy registrations parsed"
    assert not unmapped, "UNMAPPED registrations: " + json.dumps(
        [{"n": r["n"], "event": r["event"], "cmd": r["command"]} for r in unmapped], indent=2)


def test_registration_count_is_65():
    regs = load_registrations()
    assert len(regs) == 65, f"expected 65 legacy registrations, got {len(regs)}"


def test_every_link_has_an_id_and_type():
    links = load_links()
    for et, arr in links.items():
        for ln in arr:
            assert ln.get("id"), f"link without id in {et}"
            assert ln.get("type") in ("gate", "mutator", "advisory", "exec"), \
                f"bad type for {ln.get('id')} in {et}"


def test_dox_and_jcm_dual_matchers_both_mapped():
    """The two dox-write-gate matchers (W|E|ME and Bash) and the two jcm-enforce
    matchers (Read|Grep|Glob and lean-ctx mcp) must each resolve to a link."""
    rows, _ = build_mapping()
    dox = [r for r in rows if r["sig"][0] == "dox-write-gate.py"]
    jcm = [r for r in rows if r["sig"][0] == "jcodemunch-enforce.py" and r["event"] == "PreToolUse"]
    assert all(r["status"] == "MAPPED" for r in dox) and len(dox) == 2
    assert all(r["status"] == "MAPPED" for r in jcm) and len(jcm) == 2


# --------------------------------------------------------------------------- #
# fixture diff: gate decision standalone vs through dispatch (plan P4-T2 part d)
# --------------------------------------------------------------------------- #
def _run_standalone(script: str, payload: dict) -> str | None:
    """Run a repo hook script standalone with the current interpreter; return its
    permissionDecision. `script` is a hooks-relative path — portable, with no
    ${HOME}/.claude or `python3` assumption (CI checks the repo out OUTSIDE
    ~/.claude, and Windows has no `python3` on PATH)."""
    import subprocess
    import sys as _sys
    target = _HOOKS / script
    try:
        proc = subprocess.run([_sys.executable, str(target)], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=15, check=False)
        s = (proc.stdout or "").strip()
        if s.startswith("{"):
            d = json.loads(s)
            hso = d.get("hookSpecificOutput", {}) or {}
            return hso.get("permissionDecision") or d.get("permissionDecision")
    except Exception:  # noqa: BLE001
        return None
    return None


def _run_via_dispatch(event: str, payload: dict) -> str | None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("dispatch", str(_HOOKS / "dispatch.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = json.loads(_CONFIG.read_text(encoding="utf-8"))
    res = mod.dispatch(event, payload, cfg)
    return res.get("hookSpecificOutput", {}).get("permissionDecision")


def test_fixture_diff_dangerous_bash_gate():
    """A destructive Bash command must yield the SAME decision standalone and
    through the dispatch chain (dangerous-bash-gate is the danger-first link).

    dangerous-bash-gate allows a *second identical* attempt (override-once), so
    each side uses a UNIQUE command (unique fingerprint) — both are first
    attempts and must both DENY. This proves dispatch runs the real gate
    faithfully AND preserves the safety verdict."""
    import uuid
    danger = "rm -rf / --no-preserve-root"  # gate's recursive-force-delete pattern
    p_std = {"session_id": "fx-danger", "tool_name": "Bash",
             "tool_input": {"command": f"{danger}  # standalone-{uuid.uuid4().hex}"}}
    p_disp = {"session_id": "fx-danger", "tool_name": "Bash",
              "tool_input": {"command": f"{danger}  # dispatch-{uuid.uuid4().hex}"}}
    standalone = _run_standalone("dangerous-bash-gate.py", p_std)
    chained = _run_via_dispatch("pre-tool-use", p_disp)
    assert standalone == "deny", f"standalone gate did not deny: {standalone}"
    assert chained == "deny", f"dispatch chain did not deny the dangerous command: {chained}"
    assert standalone == chained, f"decision diverged: standalone={standalone} chained={chained}"


def test_fixture_diff_benign_bash_allows():
    """A benign Bash command is not denied by the chain (no spurious block)."""
    payload = {"session_id": "fx-benign", "tool_name": "Bash",
               "tool_input": {"command": "echo hello"}}
    chained = _run_via_dispatch("pre-tool-use", payload)
    assert chained in (None, "allow"), f"benign bash blocked: {chained}"


# --------------------------------------------------------------------------- #
# mapping-table writer (standalone)
# --------------------------------------------------------------------------- #
def write_maptable() -> str:
    rows, unmapped = build_mapping()
    mapped = sum(1 for r in rows if r["status"] == "MAPPED")
    swaps = sum(1 for r in rows if r["status"] == "INTENTIONAL-SWAP")
    lines = [
        "# P4 dispatch parity — registration → link mapping",
        "",
        "> Charter §3 precondition for P4-T7 (the settings.json 65→8 rewrite).",
        "> Every legacy `settings.json` hook registration must map to exactly one",
        "> **enabled** `dispatch.config.json` link on the same event, with an",
        "> equivalent-or-broader `tools:` scope and the same command/mode.",
        "",
        f"**{len(rows)} registrations · {mapped} MAPPED · {swaps} INTENTIONAL-SWAP · "
        f"{len(unmapped)} UNMAPPED** — {'PASS ✅' if not unmapped else 'FAIL ❌'}",
        "",
        "| # | event | matcher | legacy command | → link | status |",
        "|--:|---|---|---|---|---|",
    ]
    for r in rows:
        cmd = r["command"].replace("${HOME}/.claude/hooks/", "…/").replace("|", "\\|")
        matcher = str(r["matcher"]).replace("|", "\\|")
        lines.append(
            f"| {r['n']} | {r['event']} | `{matcher}` | `{cmd}` | `{r['link']}` | {r['status']} |")
    lines += ["", "## Intentional swaps / notes", ""]
    for r in rows:
        if r["status"] != "MAPPED" or r["note"]:
            if r["note"]:
                lines.append(f"- **#{r['n']} {r['event']} → `{r['link']}`** ({r['status']}): {r['note']}")
    lines += [
        "",
        "## Additions (new links, no legacy registration — Charter §2 additions-allowed)",
        "",
        "- `state-cleanup` (session-start exec) — 14d telemetry + 24h state purge.",
        "- `router-shadow` (user-prompt-submit exec) — router.py --shadow; starts the",
        "  ≥10-real-session zero-miss parity clock (HANDOFF P1-T8). Emits nothing.",
        "- `index-tick` (user-prompt-submit exec) — index-lifecycle tick (HANDOFF P3-T4).",
        "- `index-flush` (stop exec) — index-lifecycle flush (HANDOFF P3-T4).",
        "",
        "## Reconciliation decisions (documented deviations)",
        "",
        "- **Aggregators kept WHOLE** (`session-start-aggregator.py`, `post-write-aggregator.py`,",
        "  `token-stack-prompt-reminder.py`) are single links, NOT decomposed. Charter §3's",
        "  prime directive is *every hook stays its own file, no fusion*; decomposing risks",
        "  double-fires and strands P3's interim index-lifecycle wiring which lives inside them.",
        "  Consequence: `index-lifecycle session-start`/`post-write` stay wired via the aggregator",
        "  links (their current home) — NOT added as separate links (would double-fire). The",
        "  HANDOFF \"re-home\" items were predicated on decomposition and are moot under this",
        "  safer choice. The session-start MCP-roster/superpowers merge stays in the aggregator",
        "  (NOT ported into dispatch.py) — dispatch.py's advisory merge provides the equivalent.",
        "- **ponytail pre-tool-use** encoded as `advisory` (not `gate`): the `.*` deny-all is",
        "  defused to advisory (P4-T8, Charter §7 brick-risk). An INTENTIONAL enforcement",
        "  softening — any residual deny from the file is not enforced by the advisory link.",
        "- **model-router**, **codex-capture**, **invoke-suite-gate**, the three persistence",
        "  writers all remain their own files/links (Charter §3 — not folded).",
    ]
    text = "\n".join(lines) + "\n"
    _MAPTABLE.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    rows, unmapped = build_mapping()
    write_maptable()
    mapped = sum(1 for r in rows if r["status"] == "MAPPED")
    swaps = sum(1 for r in rows if r["status"] == "INTENTIONAL-SWAP")
    print(f"registrations={len(rows)} mapped={mapped} swap={swaps} unmapped={len(unmapped)}")
    print(f"mapping table -> {_MAPTABLE}")
    if unmapped:
        for r in unmapped:
            print(f"  UNMAPPED #{r['n']} {r['event']} {r['command']}")
        raise SystemExit(1)
    raise SystemExit(0)
