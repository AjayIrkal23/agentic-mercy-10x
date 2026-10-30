#!/usr/bin/env python3
"""router_replay.py: replay this machine's recent prompts through the prompt router and
measure misroutes against ``hooks/router-budget.json`` (audit2 A12).

Read-only over ``<claude_dir>/projects/*/*.jsonl``. Each top-level user turn of the last
``window_days`` (not ``isMeta`` / ``isSidechain``, no ``tool_result``, deduped) runs
in-process through ``prompt_router.router.route_payload`` with a fresh temporary
``CLAUDE_HOOK_STATE_DIR`` / ``CLAUDE_HOOK_TELEMETRY_DIR`` / ``CLAUDE_HOOK_DOTSTATE_DIR`` and
``CLAUDE_HOOK_DOCTOR=1``, so nothing reaches the live state. A per-project model-mode
directive ("use opus for this project") is skipped: it would set a pin.

Signals per routed prompt (a prompt the router injected anything for):
  threejs_no_3d         threejs-r3f pushed, no 3D word in the prompt
  debug_no_bug          debug-investigation pushed, no bug word in the prompt
  fe_skill_no_ui        a frontend-only skill pushed on a prompt with no UI signal
  app_line_no_repo      "Your app is running" on a cwd outside any git repo
  machine_routed        a harness prompt (teammate relay, restore, judge) got routed
  backend_git_oneliner  backend-standards pushed on a short commit/push/deploy line
  union                 any of the above

Output: counts and rates only, to ``<state_dir>/router-replay/<date>.json``. Prompt text
never leaves the process; the top flagged prompts print as ``<transcript>:<line>``.

Usage:
  python3 scripts/router_replay.py                 # report
  python3 scripts/router_replay.py --check         # exit 1 when a rate exceeds its max
  options: --root <claude_dir> --budget <json> --out-dir <dir> --days N
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_HOOKS = _ROOT / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

SIGNALS = ("threejs_no_3d", "debug_no_bug", "fe_skill_no_ui", "app_line_no_repo",
           "machine_routed", "backend_git_oneliner")
_SKIP_PREFIX = ("Caveat:", "[Request interrupted", "This session is being continued",
                "[Workflow harness", "Base directory for this skill", "<command-")
_MACHINE = ("<task-notification>", "<teammate-message", "<cross-session-message",
            "Another Claude session sent a message:", "Session restored automatically after a crash")
_SKILL_RE = re.compile(r"^- \*\*([^*]+)\*\* \((?:MUST-READ|SHOULD-READ)\)|\[inlined skill: ([^\]]+)\]", re.M)
_BUG_RX = re.compile(r"\b(bugs?|errors?|fail\w*|broken|crash\w*|fix\w*|issues?|not working|wrong|exception|"
                     r"traceback|doesn'?t|isn'?t|can'?t|cannot|why|stuck|hang\w*|slow|regress\w*|debug\w*|"
                     r"timed? ?out|not (?:show|load|open|work)\w*|missing)\b", re.I)
_UI_RX = re.compile(r"\b(ui|ux|page|screen|button|modal|layout|css|style|design|frontend|component|"
                    r"dashboard|form|tab|sidebar|navbar|mobile|responsive|theme|color|font|icon|view|"
                    r"browser|click|display|render\w*|visual\w*|animation|scroll)\b", re.I)
_3D_RX = re.compile(r"\b(3d|three(?:\.?js)?|r3f|webgl|glb|gltf|shaders?|globe|scene|canvas|fiber|drei|mesh)\b", re.I)
_GIT_RX = re.compile(r"\b(commit|comit|push|deploy|merge|pull request|pr)\b", re.I)
_FE_EXTRA = {"debug-broken-ui", "improve-ui", "fixing-accessibility", "fixing-metadata",
             "fixing-motion-performance", "design-system-compliance", "test-error-states",
             "verify-ui-change", "design-taste-frontend", "frontend-standards-always-follow",
             "react-hooks-patterns"}


def _load_json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _prompt_of(e: dict) -> str | None:
    if e.get("type") != "user" or e.get("isMeta") or e.get("isSidechain") or e.get("isCompactSummary"):
        return None
    if e.get("toolUseResult") is not None:
        return None
    c = (e.get("message") or {}).get("content")
    if isinstance(c, list):
        if any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
            return None
        c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text")
    if not isinstance(c, str):
        return None
    t = c.strip()
    if len(t) < 3 or t.startswith(_SKIP_PREFIX):
        return None
    return t


def collect(root: Path, days: int, now: float | None = None) -> list[dict]:
    """[{prompt, cwd, ref}] from the transcripts; ``ref`` = ``<project>/<file>:<line>``."""
    cut = (now or time.time()) - days * 86400
    rows, seen = [], set()
    for f in sorted((root / "projects").glob("*/*.jsonl")):
        try:
            if f.stat().st_mtime < cut:
                continue
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for n, ln in enumerate(lines, 1):
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if not isinstance(e, dict):
                continue
            t = _prompt_of(e)
            if t is None:
                continue
            try:
                when = datetime.fromisoformat(str(e.get("timestamp") or "").replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
            key = t[:400]
            if when < cut or key in seen:
                continue
            seen.add(key)
            rows.append({"prompt": t, "cwd": str(e.get("cwd") or ""),
                         "ref": f"{f.parent.name}/{f.name}:{n}"})
    return rows


def _in_git(cwd: str) -> bool:
    try:
        p = Path(cwd).resolve()
    except (OSError, RuntimeError):
        return False
    return any((d / ".git").exists() for d in (p, *p.parents))


def _fe_only_skills() -> set[str]:
    from lib import skills_index as _si  # noqa: PLC0415
    idx = _si.skills(_HOOKS)
    out = {n for n, m in idx.items() if isinstance(m, dict) and m.get("surfaces")
           and set(m["surfaces"]) <= {"frontend", "ui"}}
    return out | _FE_EXTRA


def flags_for(prompt: str, cwd: str, ctx: str, fe_only: set[str]) -> list[str]:
    from prompt_router import classify as _c  # noqa: PLC0415
    skills = [a or b for a, b in _SKILL_RE.findall(ctx)]
    prof = _c.classify({"prompt": prompt, "cwd": cwd or "/nonexistent-dir"})
    fe = "frontend" in prof.surfaces or prof.is_ui or bool(_UI_RX.search(prompt))
    out = []
    if "threejs-r3f" in skills and not _3D_RX.search(prompt):
        out.append("threejs_no_3d")
    if "debug-investigation" in skills and not _BUG_RX.search(prompt):
        out.append("debug_no_bug")
    if not fe and any(s in fe_only for s in skills):
        out.append("fe_skill_no_ui")
    if "Your app is running" in ctx and not _in_git(cwd):
        out.append("app_line_no_repo")
    if prompt.startswith(_MACHINE) or Path(cwd or "/").name == "double-shot-latte":
        out.append("machine_routed")
    if ("backend-standards-always-follow" in skills and _GIT_RX.search(prompt)
            and len(prompt.split()) <= 20):
        out.append("backend_git_oneliner")
    return out


def replay(rows: list[dict]) -> tuple[dict, list[tuple[str, list[str]]]]:
    from prompt_router import router as _r  # noqa: PLC0415
    fe_only = _fe_only_skills()
    keys = ("CLAUDE_HOOK_STATE_DIR", "CLAUDE_HOOK_TELEMETRY_DIR", "CLAUDE_HOOK_DOTSTATE_DIR", "CLAUDE_HOOK_DOCTOR")
    saved = {k: os.environ.get(k) for k in keys}
    counts = {"prompts": len(rows), "skipped_mode": 0, "routed": 0, "union": 0, **{s: 0 for s in SIGNALS}}
    flagged: list[tuple[str, list[str]]] = []
    try:
        for i, row in enumerate(rows):
            if _r.parse_mode_phrase(row["prompt"]):
                counts["skipped_mode"] += 1
                continue
            with tempfile.TemporaryDirectory(prefix="router-replay-") as box:
                for k, sub in zip(keys[:3], ("state", "telemetry", "dotstate")):
                    os.environ[k] = str(Path(box) / sub)
                os.environ["CLAUDE_HOOK_DOCTOR"] = "1"
                try:
                    ctx = _r.route_payload({"session_id": f"replay-{i}", "cwd": row["cwd"], "prompt": row["prompt"]})
                except Exception:  # noqa: BLE001 - one bad prompt never stops the replay
                    ctx = ""
                # inside the box: classify() caches state/<repo>.stack.json, which re-created a removed box
                f = flags_for(row["prompt"], row["cwd"], ctx, fe_only) if ctx else []
            if not ctx:
                continue
            counts["routed"] += 1
            for s in f:
                counts[s] += 1
            if f:
                counts["union"] += 1
                flagged.append((row["ref"], f))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return counts, flagged


def rates(counts: dict) -> dict:
    n = counts.get("routed") or 0
    return {s: (round(counts[s] / n, 4) if n else 0.0) for s in ("union", *SIGNALS)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when a rate exceeds its budget")
    ap.add_argument("--root", default=None, help="claude dir holding projects/ (default: this checkout)")
    ap.add_argument("--budget", default=str(_HOOKS / "router-budget.json"))
    ap.add_argument("--out-dir", default=None, help="report dir (default <state_dir>/router-replay)")
    ap.add_argument("--days", type=int, default=None)
    a = ap.parse_args(argv)
    budget = _load_json(Path(a.budget))
    days = a.days or int(budget.get("window_days") or 14)
    root = Path(a.root) if a.root else _ROOT
    out_dir = Path(a.out_dir) if a.out_dir else None
    if out_dir is None:
        from lib import platform as _plat  # noqa: PLC0415
        out_dir = _plat.state_dir() / "router-replay"
    rows = collect(root, days)
    if not rows:
        print("router-replay: SKIP(no transcripts)")
        return 0
    counts, flagged = replay(rows)
    r = rates(counts)
    report = {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "window_days": days,
              "counts": counts, "rates": r, "max": budget.get("max") or {},
              "top_flagged": [{"ref": ref, "flags": f} for ref, f in flagged[:10]]}
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{report['date']}.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    except OSError:
        pass
    print(f"router-replay: routed {counts['routed']}/{counts['prompts']} "
          f"union {r['union']:.3f} ({counts['union']}/{counts['routed']})")
    for s in SIGNALS:
        print(f"  {s:22} {counts[s]:4}  {r[s]:.3f}")
    for ref, f in flagged[:10]:
        print(f"  flagged {ref}  {','.join(f)}")
    if not a.check:
        return 0
    over = [f"{k} {r.get(k, 0.0):.3f} > {float(v):.3f}" for k, v in (budget.get("max") or {}).items()
            if r.get(k, 0.0) > float(v)]
    for line in over:
        print(f"OVER BUDGET: {line}")
    print("router-replay --check: " + ("FAIL" if over else "OK"))
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
