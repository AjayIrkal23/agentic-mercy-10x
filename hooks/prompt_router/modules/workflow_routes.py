"""workflow_routes.py — one ROUTING line pointing at a saved workflow (R3.2).

Reads ``<claude_dir>/workflows/index.json`` (written by scripts/build_workflows.py):
``[{"name", "file", "triggers", "acts", "min_size", "phases", "args_schema"}]``.
Missing -> the tracked ``workflows/src/index.src.json`` (the render is per machine, I10); invalid -> no line. Never generates scripts; never runs anything except an
optional ``git diff --name-only HEAD`` for REVIEW prompts (0.4 s cap). One line per
prompt, first rule wins:

  invoke   two or more acts at size M/L, two acts scoring >= auto_dispatch_threshold at any
           size, or size L with one act and no corpus trigger (below) -> the acts in canonical order
  review   REVIEW intent and >= 3 changed files (prompt paths or the git diff)
  other    a trigger hit + a named corpus (path, URL, "this repo") + size >= min_size; it beats a
           single-act size-L invoke, never a multi-act one

``tier_hint: "escalate"`` rides along when lib.model_mode.escalation_reason applies.
The line is a model instruction, never a command for the user. Fail-open to [].
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[2]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    _plat = None  # type: ignore

_SIZE_RANK = {"S": 1, "M": 2, "L": 3}
_CORPUS_RX = re.compile(r"\b(?:this|the|our|my) (?:repo(?:sitory)?|codebase|project|monorepo|service|harness)\b",
                        re.I)
_URL_RX = re.compile(r"https?://\S+", re.I)
_BUDGET_MS = 80
# FIX-r3 T7: the model already has the prompt; it fills this in instead of the router echoing up to 240 chars.
TASK_PLACEHOLDER = "<the prompt, verbatim>"


def _claude_dir() -> Path:
    if _plat is not None:
        return _plat.claude_dir()
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser()


def _source_index(wf: Path) -> list[dict]:
    """The tracked ``src/index.src.json`` ({name: {triggers, acts, min_size, args_schema}}) as index rows:
    the render is per machine and untracked (I10), so a fresh clone before its first render still routes."""
    data = json.loads((wf / "src" / "index.src.json").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return []
    return [{**v, "name": k, "file": f"{k}.js"} for k, v in sorted(data.items())
            if not k.startswith("_") and isinstance(v, dict)]


@lru_cache(maxsize=1)
def _index() -> list[dict]:
    wf = _claude_dir() / "workflows"
    try:
        data = json.loads((wf / "index.json").read_text(encoding="utf-8"))
        return [e for e in data if isinstance(e, dict) and e.get("name")] if isinstance(data, list) else []
    except FileNotFoundError:
        try:
            return _source_index(wf)
        except Exception:  # noqa: BLE001
            return []
    except Exception:  # noqa: BLE001
        return []


def _changed_files(root) -> int:
    """`git diff --name-only HEAD` count, 0.4 s cap; 0 on any error or under CLAUDE_HOOK_DOCTOR."""
    if not root or os.environ.get("CLAUDE_HOOK_DOCTOR"):
        return 0
    try:
        cp = subprocess.run(["git", "-C", str(root), "diff", "--name-only", "HEAD"],  # noqa: S603,S607
                            capture_output=True, text=True, timeout=0.4, check=False,
                            **(_plat.no_window_kwargs() if _plat else {}))
        return len([ln for ln in cp.stdout.splitlines() if ln.strip()]) if cp.returncode == 0 else 0
    except Exception:  # noqa: BLE001  FileNotFoundError (no git), timeout
        return 0


def _escalation(text: str, cwd: str) -> str | None:
    try:
        from lib import model_mode as _mm  # noqa: PLC0415
        policy = json.loads((_HOOKS / "model-policy.json").read_text(encoding="utf-8"))
        return _mm.escalation_reason(policy, "workflow", text, cwd or None)
    except Exception:  # noqa: BLE001
        return None


def _trigger_hits(entry: dict, text: str) -> int:
    from prompt_router.classify import KeywordMatcher  # noqa: PLC0415
    kws = [str(k) for k in entry.get("triggers") or []]
    return len(KeywordMatcher({"t": kws}).hits(text).get("t", [])) if kws else 0


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-") or "task"


def _run_dir(text: str, root=None, cwd: str = "") -> str:
    """<repo root>/.claude/runs/<UTC ts>-<slug>; the cwd when the prompt has no repo; relative only when neither is known."""
    rel = f".claude/runs/{datetime.now(timezone.utc):%Y%m%dT%H%M}-{_slug(text)}"
    base = root or cwd
    return str(Path(base) / rel) if base else rel


def _strong_acts(profile, threshold: int) -> list[str]:
    """Acts whose intent score meets the router's auto_dispatch_threshold, canonical order."""
    from prompt_router.classify import ACT_MAP, _ACT_PRIORITY  # noqa: PLC0415
    return [ACT_MAP[c] for c in _ACT_PRIORITY
            if c in ACT_MAP and int(profile.intents.get(c, 0) or 0) >= threshold]


def _pick(profile, raw: str, root, by: dict, idx: list[dict], threshold: int = 3, cwd: str = ""):
    """(entry, args) for the first rule that fires, else (None, None)."""
    acts = list(profile.acts or [])
    inv = by.get("invoke")
    # two score-1 intents on a small task ("fix the failing test") stay inline (REVIEW2 Fix 4)
    strong = _strong_acts(profile, threshold)
    multi = len(strong) >= 2 or (len(acts) >= 2 and profile.size != "S")
    url = _URL_RX.search(raw)
    corpus = bool(profile.paths) or bool(url) or bool(_CORPUS_RX.search(raw))
    size = _SIZE_RANK.get(profile.size, 2)

    def _trigger_entry():
        for e in idx:
            if e["name"] in ("invoke", "review"):
                continue
            need = _SIZE_RANK.get(str(e.get("min_size", "S")).upper(), 1)
            if size >= need and _trigger_hits(e, profile.text) >= 1:
                return e
        return None

    hit = _trigger_entry() if corpus else None
    # final-fix 5: a triggered workflow on a named corpus beats a single-act size-L invoke
    # ("research the changelog of <url>" used to become invoke {acts: [impl, docs]})
    if inv is not None and (multi or (profile.size == "L" and acts and hit is None)):
        allowed = inv.get("acts") or acts
        use = strong if len(strong) >= 2 else acts
        if profile.size == "L" and "impl" in acts and not ({"impl", "refactor"} & set(use)) \
                and {"test", "docs", "clean"} & set(use):
            # a size-L chain that writes (tests, docs) and whose profile named impl, but whose strong set
            # dropped it, gets impl back in canonical order. A chain that never asked for code
            # (docs-only, tests-only, audit / review / security) stays as is.
            use = use + ["impl"]
        # canonical order (the entry's `acts`), the order invoke.js runs them in anyway
        return inv, {"acts": [a for a in allowed if a in set(use)], "task": TASK_PLACEHOLDER,
                     "run": _run_dir(raw, root, cwd), "slug": _slug(raw)}
    rev = by.get("review")
    if rev is not None and "REVIEW" in profile.intents:
        if max(len(profile.paths), _changed_files(root)) >= 3:
            return rev, {"run": _run_dir(raw, root, cwd), "paths": list(profile.paths[:20])}
    if hit is not None:
        args = {"run": _run_dir(raw, root, cwd), "task": TASK_PLACEHOLDER}
        if profile.paths:
            args["corpus"] = list(profile.paths[:10])
        if url:
            args["url"] = url.group(0)
        return hit, args
    return None, None


def items(profile, ctx: dict) -> list[dict]:
    try:
        idx = _index()
        if not idx:
            return []
        t0 = time.perf_counter()
        by = {e["name"]: e for e in idx}
        payload = ctx.get("payload") or {}
        raw = str(payload.get("prompt") or profile.text or "")
        cwd = str(payload.get("cwd") or "")
        root = getattr(ctx.get("repo"), "root", None)
        try:
            threshold = int((ctx.get("config") or {}).get("auto_dispatch_threshold", 3))
        except (TypeError, ValueError):
            threshold = 3
        entry, args = _pick(profile, raw, root, by, idx, threshold, cwd)
        if entry is None:
            return []
        if _escalation(raw, cwd):
            args["tier_hint"] = "escalate"
        name = str(entry["name"])
        n_acts = len(args.get("acts") or entry.get("acts") or [])
        text = (f"WORKFLOW: run saved workflow {name} with args "
                f"{json.dumps(args, ensure_ascii=False, sort_keys=True)} "
                f"(size {profile.size}, {n_acts} act{'s' if n_acts != 1 else ''})")
        ms = (time.perf_counter() - t0) * 1000
        if ms > _BUDGET_MS:
            try:
                from lib import hook_telemetry as _tel  # noqa: PLC0415
                _tel.record("UserPromptSubmit", "prompt_router.workflow_slow", ms=round(ms, 2))
            except Exception:  # noqa: BLE001
                pass
        return [{"id": f"route:workflow:{name}:" + "+".join(sorted(args.get("acts") or [name])),
                 "tier": 2, "section": "ROUTING", "text": text}]
    except Exception:  # noqa: BLE001
        return []


__all__ = ["items"]
