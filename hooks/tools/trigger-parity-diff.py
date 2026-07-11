#!/usr/bin/env python3
"""trigger-parity-diff.py — shadow-mode ZERO-MISS parity harness (P1-T8, P1-T10).

Charter §2: the router's trigger surface must be a provable SUPERSET of the
legacy stack. For every prompt this harness computes:
  * legacy signals — the skills/substrate directives the LEGACY UserPromptSubmit
    injectors emit (each hook in hooks/legacy-prompt-stack.json run as a
    subprocess on the same payload, combined additionalContext parsed), and
  * router signals — what the router would emit (router.py --shadow).
A MISS is any signal the legacy stack fired that the router did NOT. The bar is
ZERO misses; router-only additions are fine (and expected).

Outputs:
  (a) machine diff  ~/.claude/telemetry/trigger-parity/<sid>.jsonl
  (b) human report  ~/.claude/plans/P1-shadow-parity.md   (per-trigger table)

Modes:
  --fixtures            run the built-in representative fixture set (bootstrap /
                        demo; the ≥10 REAL sessions are appended over time).
  --session <sid>       diff one real shadow session (reads its router-shadow.jsonl
                        for prompts) against the legacy stack replayed offline.
  --watchdog            P1-T10: replay recent real sessions offline weekly; append
                        any suspected miss to telemetry/trigger-miss-watch.jsonl.

Pure Python 3 stdlib. Windows+POSIX portable. The legacy injectors are run
read-only (their own state writes are their business; we only read stdout).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
_CLAUDE = _HOOKS.parent
_LEGACY_SNAPSHOT = _HOOKS / "legacy-prompt-stack.json"
_ROUTER = _HOOKS / "prompt_router" / "router.py"
_SKILLS_INDEX = _HOOKS / "skills-index.json"
_PARITY_DIR = _CLAUDE / "telemetry" / "trigger-parity"
_REPORT = _CLAUDE / "plans" / "P1-shadow-parity.md"
_MISS_WATCH = _CLAUDE / "telemetry" / "trigger-miss-watch.jsonl"

# Representative fixtures across the mixed task types the ≥10 real sessions must
# also cover (FE, BE/Go, debug, UI, docs, /invoke, arch, trivial).
_FIXTURES = [
    ("fe-api", "add a fetch call to the frontend api client for the orders list"),
    ("be-go", "implement a Go controller and service for orders with table-driven tests"),
    ("debug", "root cause the null pointer crash in the auth service stack trace"),
    ("ui", "the dashboard navbar looks off, redesign the hero section and card layout"),
    ("docs", "update the README and server_docs for the new endpoint"),
    ("arch", "map the dependency graph and blast radius before I refactor the module"),
    ("security", "audit the login flow for owasp vulnerabilities"),
    ("invoke", "/invoke audit impl for the payments domain"),
    ("plan", "plan and spec the multi-service event pipeline across FE+BE+infra"),
    ("cleanup", "find and remove dead code and unused imports in the client"),
    ("review", "review this pull request for correctness and quality"),
    ("trivial-ack", "ok"),
]

# Canonical substrate signals every parity comparison tracks.
_SUBSTRATE = {
    "jcodemunch": ("jcodemunch",),
    "graphify": ("graphify",),
    "jdocmunch": ("jdocmunch",),
    "sequential-thinking": ("sequential-thinking", "sequential thinking"),
    "dox": ("dox",),
    "tdd": ("tdd", "failing test first"),
    "lean-ctx": ("lean-ctx",),
    "ui-ux-stack": ("ui/ux", "impeccable", "taste-skill", "craft stack"),
    "higgsfield": ("higgsfield",),
}


def _skill_names() -> set[str]:
    try:
        idx = json.loads(_SKILLS_INDEX.read_text(encoding="utf-8"))
        return set(idx.get("skills", {}).keys())
    except (OSError, json.JSONDecodeError):
        return set()


_SKILLS = _skill_names()


def _signals(text: str) -> set[str]:
    """Extract the comparable signal set from an additionalContext blob."""
    t = (text or "").lower()
    sig: set[str] = set()
    for name, needles in _SUBSTRATE.items():
        if any(n in t for n in needles):
            sig.add(f"substrate:{name}")
    for sk in _SKILLS:
        # word-ish boundary to avoid substring false positives on short names
        if re.search(r"(?<![a-z0-9])" + re.escape(sk.lower()) + r"(?![a-z0-9])", t):
            sig.add(f"skill:{sk}")
    return sig


# --------------------------------------------------------------------------- #
# legacy stack replay
# --------------------------------------------------------------------------- #
def _legacy_commands() -> list[str]:
    try:
        snap = json.loads(_LEGACY_SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    cmds = []
    for blk in snap.get("user_prompt_submit", []):
        for h in blk.get("hooks", []):
            c = h.get("command")
            if c:
                cmds.append(c)
    return cmds


def _expand(cmd: str) -> list[str]:
    home = os.path.expanduser("~")
    cmd = cmd.replace("${HOME}", home).replace("$HOME", home)
    return cmd.split()


def _extract_ac(stdout: str) -> str:
    parts = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ac = _deep_ac(obj)
        if ac:
            parts.append(ac)
    return "\n".join(parts)


def _deep_ac(obj):
    if isinstance(obj, dict):
        v = obj.get("additionalContext")
        if isinstance(v, str) and v.strip():
            return v
        for x in obj.values():
            r = _deep_ac(x)
            if r:
                return r
    return None


def legacy_emit(payload: dict) -> str:
    """Combined additionalContext from replaying every legacy UPS injector."""
    combined = []
    for cmd in _legacy_commands():
        argv = _expand(cmd)
        if not argv:
            continue
        try:
            cp = subprocess.run(argv, input=json.dumps(payload), text=True,
                                capture_output=True, timeout=40, check=False)
        except (subprocess.TimeoutExpired, OSError):
            continue
        ac = _extract_ac(cp.stdout)
        if ac:
            combined.append(ac)
    return "\n".join(combined)


def router_emit(payload: dict) -> tuple[str, list[str]]:
    """Router would-emit text + emitted ids (via --shadow log)."""
    sid = payload.get("session_id", "parity-probe")
    try:
        subprocess.run([sys.executable, str(_ROUTER), "--shadow"],
                       input=json.dumps(payload), text=True,
                       capture_output=True, timeout=30, check=False)
    except (subprocess.TimeoutExpired, OSError):
        return "", []
    from lib import platform as plat  # local import; lib is on path via _HOOKS
    log = plat.telemetry_dir() / f"{sid}.router-shadow.jsonl"
    try:
        last = log.read_text(encoding="utf-8").strip().splitlines()[-1]
        rec = json.loads(last)
        return rec.get("would_emit", ""), rec.get("emitted_ids", [])
    except (OSError, json.JSONDecodeError, IndexError):
        return "", []


# --------------------------------------------------------------------------- #
# diff one prompt
# --------------------------------------------------------------------------- #
def diff_prompt(label: str, prompt: str, sid: str) -> dict:
    _HOOKS_STR = str(_HOOKS)
    if _HOOKS_STR not in sys.path:
        sys.path.insert(0, _HOOKS_STR)
    payload = {"prompt": prompt, "session_id": sid, "cwd": str(_CLAUDE)}
    # A charter-sanctioned exact-ack suppression (Charter §1) is NOT a miss —
    # the router intentionally emits nothing on 'yes'/'ok'/'continue'.
    from prompt_router import classify as _c
    intentional_ack = _c.is_trivial_ack(prompt)

    legacy_text = legacy_emit(payload)
    router_text, router_ids = router_emit(payload)
    legacy_sig = _signals(legacy_text)
    router_sig = _signals(router_text) | set(router_ids)
    raw_misses = sorted(legacy_sig - router_sig)
    misses = [] if intentional_ack else raw_misses
    verdict = "OK-ACK" if intentional_ack else ("OK" if not misses else "MISS")
    return {
        "label": label,
        "prompt": prompt[:160],
        "legacy_signals": sorted(legacy_sig),
        "router_signals": sorted(router_sig),
        "misses": misses,
        "intentional_suppressions": raw_misses if intentional_ack else [],
        "router_only": sorted(router_sig - legacy_sig),
        "verdict": verdict,
    }


# --------------------------------------------------------------------------- #
# report writers
# --------------------------------------------------------------------------- #
def _write_machine(sid: str, rows: list[dict]) -> Path:
    _PARITY_DIR.mkdir(parents=True, exist_ok=True)
    path = _PARITY_DIR / f"{sid}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def _write_report(rows: list[dict], *, session_label: str) -> None:
    total_miss = sum(len(r["misses"]) for r in rows)
    lines = []
    if not _REPORT.exists():
        lines += [
            "# P1 Shadow Parity — zero-miss trigger report",
            "",
            "> Charter v3 §2. The router's trigger surface must be a SUPERSET of the legacy",
            "> stack. **Bar: ZERO rows where legacy fired and the router did not**, across",
            "> **>=10 real sessions** of mixed task types. Router-only additions are fine.",
            "",
            "> STATUS: **PENDING-TIME** — the >=10-real-session zero-miss run accrues as the",
            "> router shadow-runs beside the legacy stack (registered by P4 per HANDOFF).",
            "> The section below is the harness bootstrap (fixtures + any recorded sessions).",
            "> Cutover (`flip-router.py --router`) is blocked until 10 real sessions show 0 misses.",
            "",
            "| session | prompts | misses | verdict |",
            "|---|---:|---:|---|",
            "<!-- parity:summary:start -->",
            "<!-- parity:summary:end -->",
            "",
        ]
    verdict = "PASS (0 miss)" if total_miss == 0 else f"FAIL ({total_miss} miss)"
    block = [
        f"## Session `{session_label}` — {time.strftime('%Y-%m-%d %H:%M')} — {verdict}",
        "",
        "| trigger label | legacy fired | router fired | miss | verdict |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lf = ", ".join(r["legacy_signals"]) or "-"
        rf = ", ".join(r["router_signals"]) or "-"
        miss = ", ".join(r["misses"]) or "none"
        block.append(f"| {r['label']}: {r['prompt'][:48]} | {lf[:60]} | {rf[:60]} | {miss} | {r['verdict']} |")
    block.append("")
    with _REPORT.open("a", encoding="utf-8") as fh:
        if lines:
            fh.write("\n".join(lines) + "\n")
        fh.write("\n".join(block) + "\n")


# --------------------------------------------------------------------------- #
# modes
# --------------------------------------------------------------------------- #
def run_fixtures() -> int:
    sid_base = "parity-fixtures"
    rows = []
    for i, (label, prompt) in enumerate(_FIXTURES):
        rows.append(diff_prompt(label, prompt, f"{sid_base}-{i}"))
    _write_machine(sid_base, rows)
    _write_report(rows, session_label=sid_base)
    total_miss = sum(len(r["misses"]) for r in rows)
    print(f"fixtures: {len(rows)} prompts, {total_miss} miss(es). "
          f"report -> {_REPORT}  machine -> {_PARITY_DIR / (sid_base + '.jsonl')}")
    return 0 if total_miss == 0 else 1


def run_session(sid: str) -> int:
    from lib import platform as plat
    log = plat.telemetry_dir() / f"{sid}.router-shadow.jsonl"
    prompts = []
    try:
        for line in log.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("prompt"):
                prompts.append(rec["prompt"])
    except (OSError, json.JSONDecodeError):
        print(f"no shadow log for session {sid}", file=sys.stderr)
        return 1
    rows = [diff_prompt(f"p{i}", p, f"{sid}-replay-{i}") for i, p in enumerate(prompts)]
    _write_machine(sid, rows)
    _write_report(rows, session_label=sid)
    total_miss = sum(len(r["misses"]) for r in rows)
    print(f"session {sid}: {len(rows)} prompts, {total_miss} miss(es).")
    return 0 if total_miss == 0 else 1


def run_watchdog() -> int:
    """P1-T10: offline replay of recent shadow sessions; append misses to the watch log."""
    from lib import platform as plat
    tdir = plat.telemetry_dir()
    misses_found = 0
    for log in sorted(tdir.glob("*.router-shadow.jsonl")):
        sid = log.name.replace(".router-shadow.jsonl", "")
        prompts = []
        try:
            for line in log.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if rec.get("prompt"):
                    prompts.append(rec["prompt"])
        except (OSError, json.JSONDecodeError):
            continue
        for i, p in enumerate(prompts):
            r = diff_prompt(f"wd{i}", p, f"{sid}-wd-{i}")
            if r["misses"]:
                misses_found += len(r["misses"])
                with _MISS_WATCH.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"ts": round(time.time(), 3), "session": sid,
                                         "prompt": p[:160], "misses": r["misses"]},
                                        ensure_ascii=False) + "\n")
    print(f"watchdog: {misses_found} suspected miss(es) "
          f"{'-> ' + str(_MISS_WATCH) if misses_found else '(clean)'}")
    return 0 if misses_found == 0 else 1


def main(argv: list[str]) -> int:
    if "--fixtures" in argv:
        return run_fixtures()
    if "--session" in argv:
        i = argv.index("--session")
        return run_session(argv[i + 1]) if i + 1 < len(argv) else 1
    if "--watchdog" in argv:
        return run_watchdog()
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
