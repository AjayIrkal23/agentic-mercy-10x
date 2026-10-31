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
  egm_on_small          the EGM design-doc line on a DEBUG or size-S prompt
  union                 any of the above

Recall signals (a skill the prompt should have got; rate = share of its own base, A-09):
  zero_skill_dev        base dev_prompts: IMPLEMENT/DEBUG/REFACTOR/TEST/REVIEW/AUDIT intent, no skill pushed
  audit_no_audit_skill  base audit_prompts: audit / tech debt / health check wording, no audit skill pushed
  stack_skill_missed    base stack_prompts: repo deps hold mongoose / fastify / vitest, a backend (or TEST)
                        prompt, mongoose-patterns / fastify-patterns / vitest-rtl not pushed
  infra_got_fe_skill    base infra_prompts: a claude-infra prompt that was handed a frontend-only skill
Judges read the prompt text and the repo's own package.json, never the router's UI verdict
(the 17:57 misroute came from a classifier false positive the judge shared).
`zero_skill_prompts` / `distinct_skills` are reported, not budgeted.

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
           "machine_routed", "backend_git_oneliner", "egm_on_small")
# recall signal -> the count that is its denominator
RECALL = {"zero_skill_dev": "dev_prompts", "audit_no_audit_skill": "audit_prompts",
          "stack_skill_missed": "stack_prompts", "infra_got_fe_skill": "infra_prompts"}
_SKIP_PREFIX = ("Caveat:", "[Request interrupted", "This session is being continued",
                "[Workflow harness", "Base directory for this skill", "<command-")
_MACHINE = ("<task-notification>", "<teammate-message", "<cross-session-message",
            "Another Claude session sent a message", "Session restored automatically after a crash",
            "[Subagent hand-back]", "<agent-message from=")
_DEV_INTENTS = {"IMPLEMENT", "DEBUG", "REFACTOR", "TEST", "REVIEW", "AUDIT"}
_AUDIT_RX = re.compile(r"\b(audit\w*|tech(?:nical)? debt|health[- ]?check|code health|bloat)\b", re.I)
_AUDIT_SKILLS = {"tech-debt-audit", "ponytail:ponytail-audit", "code-review-and-quality", "santa-review",
                 "ponytail:ponytail-review"}
_STACK_SKILL = (({"mongoose", "mongodb"}, "mongoose-patterns", "be"), ({"fastify"}, "fastify-patterns", "be"),
                ({"vitest"}, "vitest-rtl", "test"))
_SKILL_RE = re.compile(r"^- \*\*([^*]+)\*\* \((?:MUST-READ|SHOULD-READ)\)|\[inlined skill: ([^\]]+)\]", re.M)
_BUG_RX = re.compile(r"\b(bugs?|errors?|fail\w*|broken|crash\w*|fix\w*|issues?|not working|wrong|exception|"
                     r"traceback|doesn'?t|isn'?t|can'?t|cannot|why|stuck|hang\w*|slow|regress\w*|debug\w*|"
                     r"timed? ?out|not (?:show|load|open|work)\w*|missing)\b", re.I)
_UI_RX = re.compile(r"\b(ui|ux|pages?|screens?|buttons?|modals?|layouts?|css|styl\w+|design\w*|front[- ]?end|"
                    r"components?|dashboards?|forms?|tabs?|sidebars?|navbar|mobile|responsive|themes?|colou?rs?|"
                    r"fonts?|icons?|views?|browsers?|click\w*|display\w*|render\w*|visual\w*|animat\w+|scroll\w*|"
                    r"padding|margin|spacing|align\w*|width|height|green|blue|red|dark|light|map|chart|table|"
                    r"tooltip|screenshot|images?|logo|looks?|ugly|pretty|text|label|menu|toast|panel|card|"
                    r"android|iphone|ios|emulator|expo|react[- ]native|metro)\b|"
                    r"\[Image #|\.(?:png|jpe?g|svg|tsx|jsx|css)\b", re.I)
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


def _repo_deps(cwd: str) -> set[str]:
    """package.json dependency names of the git repo holding ``cwd`` (not ``$HOME``), read from the
    files themselves so the judge does not share the router's stack detection."""
    try:
        p = Path(cwd or "/nonexistent-dir").resolve()
        root = next((d for d in (p, *p.parents) if (d / ".git").exists()), None)
        if root is None or root == Path.home().resolve():
            return set()
        from prompt_router.modules import surface as _s  # noqa: PLC0415
        deps: set[str] = set()
        for m in _s._scan(root)[0]:
            if m.name == "package.json":
                deps |= _s._deps(m)
        return deps
    except Exception:  # noqa: BLE001 - a judge never stops the replay
        return set()


def judge(prompt: str, cwd: str, ctx: str, fe_only: set[str]) -> tuple[list[str], set[str]]:
    """(flags, bases): the signals this prompt trips and the recall denominators it belongs to."""
    from prompt_router import classify as _c  # noqa: PLC0415
    skills = [a or b for a, b in _SKILL_RE.findall(ctx)]
    prof = _c.classify({"prompt": prompt, "cwd": cwd or "/nonexistent-dir"})
    # the UI judge reads the words, not the router's verdict: a classifier false positive
    # (A-01: "tokens" made every prompt UI) must stay visible
    fe = bool(_UI_RX.search(prompt))
    out: list[str] = []
    bases: set[str] = set()
    machine = prompt.startswith(_MACHINE) or Path(cwd or "/").name == "double-shot-latte"
    if "threejs-r3f" in skills and not _3D_RX.search(prompt):
        out.append("threejs_no_3d")
    if "debug-investigation" in skills and not _BUG_RX.search(prompt):
        out.append("debug_no_bug")
    if not fe and any(s in fe_only for s in skills):
        out.append("fe_skill_no_ui")
    if "Your app is running" in ctx and not _in_git(cwd):
        out.append("app_line_no_repo")
    if machine and ctx:
        out.append("machine_routed")
    if "EGM artifact directory:" in ctx and ("DEBUG" in prof.intents or prof.size == "S"):
        out.append("egm_on_small")
    if ("backend-standards-always-follow" in skills and _GIT_RX.search(prompt)
            and len(prompt.split()) <= 20):
        out.append("backend_git_oneliner")
    if machine:
        return out, bases
    if _DEV_INTENTS & set(prof.intents):
        bases.add("dev_prompts")
        if not skills:
            out.append("zero_skill_dev")
    if _AUDIT_RX.search(prompt):
        bases.add("audit_prompts")
        if not _AUDIT_SKILLS & set(skills):
            out.append("audit_no_audit_skill")
    if "claude-infra" in prof.surfaces:
        bases.add("infra_prompts")
        if any(s in fe_only for s in skills):
            out.append("infra_got_fe_skill")
    deps = _repo_deps(cwd)
    strong = prof.surfaces - set(getattr(prof, "weak_surfaces", set()) or set())
    # a backend inferred from the repo stack alone (a pasted shell line, a docs request) is no backend task
    be = bool(strong & {"backend", "api"})
    test = "TEST" in prof.intents
    missed = False
    for names, skill, kind in _STACK_SKILL:
        if names & deps and (be if kind == "be" else test):
            bases.add("stack_prompts")
            missed = missed or skill not in skills
    if missed:
        out.append("stack_skill_missed")
    return out, bases


def flags_for(prompt: str, cwd: str, ctx: str, fe_only: set[str]) -> list[str]:
    return judge(prompt, cwd, ctx, fe_only)[0]


def replay(rows: list[dict]) -> tuple[dict, list[tuple[str, list[str]]]]:
    from prompt_router import router as _r  # noqa: PLC0415
    fe_only = _fe_only_skills()
    keys = ("CLAUDE_HOOK_STATE_DIR", "CLAUDE_HOOK_TELEMETRY_DIR", "CLAUDE_HOOK_DOTSTATE_DIR", "CLAUDE_HOOK_DOCTOR")
    saved = {k: os.environ.get(k) for k in keys}
    counts = {"prompts": len(rows), "skipped_mode": 0, "routed": 0, "union": 0, **{s: 0 for s in SIGNALS},
              "scored": 0, "zero_skill_prompts": 0, "distinct_skills": 0,
              **{b: 0 for b in RECALL.values()}, **{s: 0 for s in RECALL}}
    flagged: list[tuple[str, list[str]]] = []
    distinct: set[str] = set()
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
                f, bases = judge(row["prompt"], row["cwd"], ctx, fe_only)
            pushed = [a or b for a, b in _SKILL_RE.findall(ctx)]
            if not (row["prompt"].startswith(_MACHINE) or Path(row["cwd"] or "/").name == "double-shot-latte"):
                counts["scored"] += 1
                counts["zero_skill_prompts"] += 0 if pushed else 1
            distinct.update(pushed)
            for b in bases:
                counts[b] += 1
            for s in f:
                if s in RECALL:
                    counts[s] += 1
            precision = [s for s in f if s not in RECALL]
            if ctx:
                counts["routed"] += 1
                for s in precision:
                    counts[s] += 1
                if precision:
                    counts["union"] += 1
            if f:
                flagged.append((row["ref"], f))
        counts["distinct_skills"] = len(distinct)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return counts, flagged


def rates(counts: dict) -> dict:
    n = counts.get("routed") or 0
    out = {s: (round(counts[s] / n, 4) if n else 0.0) for s in ("union", *SIGNALS)}
    for s, base in RECALL.items():  # recall signals are shares of their own base
        out[s] = round(counts.get(s, 0) / counts[base], 4) if counts.get(base) else 0.0
    sc = counts.get("scored") or 0
    out["zero_skill_prompts"] = round(counts.get("zero_skill_prompts", 0) / sc, 4) if sc else 0.0
    return out


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
    for s, base in RECALL.items():
        print(f"  {s:22} {counts[s]:4}  {r[s]:.3f}  (of {counts[base]} {base})")
    print(f"  zero-skill prompts {counts['zero_skill_prompts']}/{counts['scored']} "
          f"({r['zero_skill_prompts']:.3f}), distinct skills pushed {counts['distinct_skills']}")
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
