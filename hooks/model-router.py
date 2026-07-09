#!/usr/bin/env python3
"""
model-router.py — UserPromptSubmit hook.

Classifies prompt across 8 dimensions (0-100 total) and recommends
claude-opus-4-7 vs claude-sonnet-4-6 per prompt.

Protocol:
  stdin:  {"prompt": "...", "conversation_id": "...", "attachments": [...]}
  stdout: {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                   "additionalContext": "..."}}
  exit:   always 0 (fail-open)

State: ~/.claude/hooks/.state/{cid}.model-router.json
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "model-router.config.json"
STATE_DIR = SCRIPT_DIR / ".state"

OPUS_MODEL = "claude-opus-4-7"
SONNET_MODEL = "claude-sonnet-4-6"

_DEFAULT_CONFIG: dict[str, Any] = {
    "current_model": OPUS_MODEL,
    "thresholds": {"sonnet_max": 35, "sonnet_preferred_max": 55},
    "opus_hard_overrides": [],
    "sonnet_hard_overrides": [],
    "dimensions": {},
}


def _load_config() -> dict:
    if CONFIG_PATH.is_file():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return {**_DEFAULT_CONFIG, **raw}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULT_CONFIG)


def _flatten_prompt(payload: dict) -> str:
    parts: list[str] = []
    p = payload.get("prompt")
    if isinstance(p, str):
        parts.append(p)
    attachments = payload.get("attachments")
    if isinstance(attachments, list):
        for a in attachments:
            if isinstance(a, dict) and isinstance(a.get("file_path"), str):
                parts.append(a["file_path"])
    return "\n".join(parts).lower()


def _kw_match(text: str, keyword: str) -> bool:
    kw = keyword.strip().lower()
    if not kw:
        return False
    if len(kw) <= 4:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text))
    return kw in text


_CODE_EXT_PATTERN = re.compile(r"\b\w[\w\-/]*\.(?:go|tsx?|jsx?|py|sql|yaml|yml|rs|rb|java|kt|swift|c|cpp|h)\b")


def _count_code_file_refs(text: str) -> int:
    return len(set(_CODE_EXT_PATTERN.findall(text)))


def _check_hard_overrides(text: str, cfg: dict) -> str | None:
    for kw in cfg.get("sonnet_hard_overrides", []):
        if _kw_match(text, kw):
            return "sonnet_hard"
    for kw in cfg.get("opus_hard_overrides", []):
        if _kw_match(text, kw):
            return "opus_hard"
    return None


def _score_dimension(text: str, dim_cfg: dict, file_ref_count: int) -> int:
    max_score: int = dim_cfg.get("max_score", 10)
    keywords: list[dict] = dim_cfg.get("keywords", [])
    file_bonus_threshold: int = dim_cfg.get("file_bonus_threshold", 99)
    file_bonus: int = dim_cfg.get("file_bonus", 0)

    raw = 0
    for entry in keywords:
        kw = entry.get("kw", "")
        weight = entry.get("weight", 1)
        if _kw_match(text, kw):
            raw += weight

    if file_ref_count >= file_bonus_threshold:
        raw += file_bonus

    return min(raw, max_score)


def _score_all_dims(text: str, cfg: dict, file_ref_count: int) -> dict[str, int]:
    dims_cfg: dict = cfg.get("dimensions", {})
    result: dict[str, int] = {}
    for dim_name, dim_cfg in dims_cfg.items():
        result[dim_name] = _score_dimension(text, dim_cfg, file_ref_count)
    return result


def _tier(score: int, cfg: dict) -> tuple[str, str]:
    thresholds = cfg.get("thresholds", {})
    sonnet_max = thresholds.get("sonnet_max", 35)
    sonnet_preferred_max = thresholds.get("sonnet_preferred_max", 55)

    if score <= sonnet_max:
        return ("SONNET", SONNET_MODEL)
    elif score <= sonnet_preferred_max:
        return ("SONNET_PREFERRED", SONNET_MODEL)
    else:
        return ("OPUS", OPUS_MODEL)


def _state_path(cid: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", cid)[:64]
    return STATE_DIR / f"{safe}.model-router.json"


def _load_state(cid: str) -> dict:
    p = _state_path(cid)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "recommended_model": None,
        "score": 0,
        "tier": None,
        "dimensions": {},
        "override": None,
        "switch_count": 0,
        "classifications_count": 0,
        "timestamp": None,
    }


def _save_state(cid: str, state: dict) -> None:
    try:
        _state_path(cid).write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def _dims_str(dims: dict[str, int]) -> str:
    order = [
        "task_complexity", "scope", "risk_level", "creativity",
        "domain_depth", "reasoning_depth", "context_breadth", "output_stakes",
    ]
    short = {
        "task_complexity": "complexity",
        "scope": "scope",
        "risk_level": "risk",
        "creativity": "creativity",
        "domain_depth": "domain",
        "reasoning_depth": "reasoning",
        "context_breadth": "context",
        "output_stakes": "stakes",
    }
    parts = []
    for d in order:
        if d in dims:
            parts.append(f"{short.get(d, d)}={dims[d]}")
    return " ".join(parts)


def _build_context(
    tier: str,
    score: int,
    dims: dict[str, int],
    current_model: str,
    rec_model: str,
    override: str | None,
    switch_count: int,
) -> str:
    lines: list[str] = []

    if override == "sonnet_hard":
        lines.append(f"[MODEL ROUTER] HARD OVERRIDE -> SONNET (simple task keyword detected)")
    elif override == "opus_hard":
        lines.append(f"[MODEL ROUTER] HARD OVERRIDE -> OPUS (complex/critical task keyword detected)")
    else:
        lines.append(f"[MODEL ROUTER] Recommendation: {tier} (score: {score}/100)")
        if dims:
            lines.append(f"Dimensions: {_dims_str(dims)}")

    if rec_model == current_model:
        lines.append(f"Current model: {current_model} | MATCH — model is correct for this task.")
    else:
        lines.append(f"Current model: {current_model} | MISMATCH — suggest switching to {rec_model}")
        if rec_model == SONNET_MODEL:
            lines.append(f"Action: Tell the user to run `/model {SONNET_MODEL}` to save cost on this task.")
        else:
            lines.append(f"Action: Tell the user to run `/model {OPUS_MODEL}` — this task needs Opus capability.")

    if switch_count > 2:
        lines.append("Note: Multiple switches this session — suggestion is advisory only.")

    lines.append("Rule: See ~/.claude/rules/model-routing-rules.md for behavior spec.")
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        print("{}")
        return 0
    if not isinstance(payload, dict):
        print("{}")
        return 0

    cid: str = payload.get("conversation_id") or payload.get("session_id") or "unknown"
    cfg = _load_config()
    text = _flatten_prompt(payload)

    if not text.strip():
        print("{}")
        return 0

    file_ref_count = _count_code_file_refs(text)

    override = _check_hard_overrides(text, cfg)
    dims: dict[str, int] = {}

    if override == "sonnet_hard":
        score, tier_name, rec_model = 0, "SONNET_FORCE", SONNET_MODEL
    elif override == "opus_hard":
        score, tier_name, rec_model = 100, "OPUS_FORCE", OPUS_MODEL
    else:
        dims = _score_all_dims(text, cfg, file_ref_count)
        score = sum(dims.values())
        tier_name, rec_model = _tier(score, cfg)
        override = None

    state = _load_state(cid)
    prev_rec: str | None = state.get("recommended_model")
    count: int = state.get("classifications_count", 0)
    switch_count: int = state.get("switch_count", 0)

    is_first = count == 0
    is_mismatch = (rec_model != prev_rec) and not is_first

    if is_mismatch:
        switch_count += 1

    _save_state(cid, {
        "recommended_model": rec_model,
        "score": score,
        "tier": tier_name,
        "dimensions": dims,
        "override": override,
        "switch_count": switch_count,
        "classifications_count": count + 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    should_emit = is_first or is_mismatch

    if not should_emit:
        print("{}")
        return 0

    current_model = cfg.get("current_model", OPUS_MODEL)
    ctx = _build_context(
        tier_name, score, dims, current_model, rec_model, override, switch_count
    )

    print(json.dumps({
        "additionalContext": ctx,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
