"""model_mode.py — per-project subagent model mode (D4) and the shared model resolver (R3.3).

State file: ``<claude_dir>/state/model-modes/<repo_key>`` containing ``haiku`` | ``sonnet`` |
``opus`` | ``fable``. A pin above the plan tier's ceiling is capped on write (``set_mode``) and on
read (``forced_mode``); the file itself is never rewritten on read. Consumers: opus-guard (Agent),
workflow-model-guard (Workflow), the prompt router (``set_mode`` from override phrases) and
``scripts/model-mode.py`` (CLI).

``resolve()`` is the single routing implementation both guards call:
session flag > per-project pin > explicit model/[label] (guarded roles and fable need the user's
phrase) > role x tier > escalation > usage step-down > tier ceiling.

repo_key = ``<basename>-<sha1(realpath(git root or cwd))[:12]>``. Everything fails soft: any error
-> None / False / a literal fallback, never raises.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

try:
    from lib import platform as _plat
    from lib import repo_context as _rc
except Exception:  # noqa: BLE001 - never let an import failure brick a hook
    _plat = None  # type: ignore
    _rc = None  # type: ignore

MODES = ("haiku", "sonnet", "opus", "fable")
_ORDER = ["haiku", "sonnet", "opus", "fable"]
# fail-open literals (policy missing/corrupt): judges keep their max20 seat, everyone else `default`
_LIT_ROLES = {a: "judge" for a in ("santa-reviewer", "frontend-uiux-designer", "planning-director",
                                   "spec-architect", "debug-detective", "audit-specialist")}
_LIT_TIERS = {"pro": {"roles": {"judge": "sonnet", "default": "haiku"}, "escalate": {}},
              "max5": {"roles": {"judge": "sonnet", "default": "sonnet"}, "escalate": {}},
              "max20": {"roles": {"judge": "opus", "default": "sonnet"}, "escalate": {}}}
_LIT_TIERS["api"] = _LIT_TIERS["max5"]
_LIT_GUARDED = {"judge", "impl", "integrate", "security", "test"}


def _claude_dir() -> Path:
    if _plat is not None:
        return _plat.claude_dir()
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path("~/.claude").expanduser()


def modes_dir() -> Path:
    return _claude_dir() / "state" / "model-modes"


def repo_key(cwd: str | os.PathLike | None) -> str | None:
    """Stable per-repo key, or None when ``cwd`` is missing/unusable."""
    if not cwd:
        return None
    root: Path | None = None
    if _rc is not None:
        try:
            root = _rc.git_root(cwd)
        except Exception:  # noqa: BLE001
            root = None
    if root is None:
        try:
            root = Path(cwd).expanduser().resolve()
        except (OSError, RuntimeError):
            return None
    digest = hashlib.sha1(str(root).encode("utf-8", "replace")).hexdigest()[:12]
    return f"{root.name or 'root'}-{digest}"


def _tier_now() -> str | None:
    try:
        from lib import plan_tier  # noqa: PLC0415

        return plan_tier.read()["tier"]
    except Exception:  # noqa: BLE001
        return None


def _cap(model: str) -> str:
    """``model`` clamped to the current tier's ceiling; unchanged when the tier lib is unavailable."""
    tier = _tier_now()
    if not tier:
        return model
    try:
        from lib import plan_tier  # noqa: PLC0415

        return plan_tier.cap(model, tier)
    except Exception:  # noqa: BLE001
        return model


def cap_reason(model: str) -> str | None:
    """One line when the current tier's ceiling changes ``model``, else None."""
    model = (model or "").lower()
    capped = _cap(model)
    if capped == model:
        return None
    tier = _tier_now()
    return f"{model} exceeds the {tier} ceiling ({capped}); stored {capped}"


def forced_mode(cwd: str | os.PathLike | None, *, cap: bool = True) -> str | None:
    """This repo's pinned model (capped to the tier ceiling unless ``cap=False``), or None."""
    key = repo_key(cwd)
    if not key:
        return None
    try:
        mode = (modes_dir() / key).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    if mode not in MODES:
        return None
    return _cap(mode) if cap else mode


def set_mode(cwd: str | os.PathLike | None, model: str | None) -> bool:
    """Pin ``model`` (capped to the tier ceiling) for this repo, or clear the pin when None."""
    key = repo_key(cwd)
    if not key:
        return False
    path = modes_dir() / key
    try:
        if model is None:
            path.unlink(missing_ok=True)
            return True
        model = model.lower()
        if model not in MODES:
            return False
        model = _cap(model)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(model + "\n")
        return True
    except OSError:
        return False


_DEFAULT_FLAGS = {"haiku": "haiku-only-mode", "sonnet": "sonnet-only-mode", "opus": "opus-only-mode",
                  "fable": "fable-only-mode"}


def global_flags(policy: dict | None = None) -> list[str]:
    """Active global kill-switch flags, in precedence order (haiku first). Same files the guards read:
    ``<claude_dir>/<session_flags.dir>/<session_flags.<model>>`` (fail-open to literals)."""
    sf = (policy or {}).get("session_flags")
    sf = sf if isinstance(sf, dict) else {}
    base = _claude_dir() / (sf.get("dir") if isinstance(sf.get("dir"), str) and sf.get("dir") else "state")
    prec = sf.get("precedence")
    prec = prec if isinstance(prec, list) and prec and all(p in _DEFAULT_FLAGS for p in prec) else list(MODES)
    out = []
    for m in prec:
        name = sf.get(m) if isinstance(sf.get(m), str) and sf.get(m) else _DEFAULT_FLAGS[m]
        if (base / name).is_file():
            out.append(m)
    return out


def user_phrase(model: str, transcript_path, phrases: dict | None) -> str | None:
    """The override phrase for ``model`` (policy ``override_phrases``) found in the user's
    last real prompt of the transcript, or None. Meta rows, tool results and task
    notifications are not the user's words (lib.turns). Any error -> None."""
    if not transcript_path or not isinstance(phrases, dict):
        return None
    try:
        from lib import turns  # noqa: PLC0415 - only on the explicit-model path
        _, text = turns.last_user_turn(transcript_path)
    except Exception:  # noqa: BLE001
        return None
    low = (text or "").lower()
    for p in phrases.get(model) or []:
        if isinstance(p, str) and p and p.lower() in low:
            return p
    return None


def _classify(text: str, cwd: str | None):
    try:
        from prompt_router.classify import classify  # noqa: PLC0415 - only on the paths that need it

        return classify({"prompt": text, "cwd": cwd or ""})
    except Exception:  # noqa: BLE001
        return None


def _plan_marker(policy: dict, text: str) -> bool:
    try:
        esc = policy.get("escalation") or {}
        return any(re.search(p, text, re.IGNORECASE) for p in esc.get("plan_markers") or [])
    except Exception:  # noqa: BLE001
        return False


def escalation_signal(policy: dict, text: str, cwd: str | None) -> str | None:
    """Why executor work should go one model up, or None. A retry marker, else (no plan marker)
    prompt_router.classify size/risk >= heavy_qualifiers. Fail-open: any error -> None."""
    esc = policy.get("escalation")
    if not isinstance(esc, dict) or not esc.get("enabled"):
        return None
    try:
        if any(re.search(p, text, re.IGNORECASE) for p in esc.get("retry_markers") or []):
            return "previous attempt failed"
        if any(re.search(p, text, re.IGNORECASE) for p in esc.get("plan_markers") or []):
            return None  # a plan/spec/contract drives the work: the cheaper model executes it
        prof = _classify(text, cwd)
        if prof is None:
            return None
        hq = policy.get("heavy_qualifiers") or {}
        rank = {"S": 1, "M": 2, "L": 3}
        if (rank.get(prof.size, 0) >= rank.get(hq.get("min_size", "L"), 3)
                and prof.risk >= int(hq.get("min_risk", 2))):
            return f"large task with no plan (size {prof.size}, risk {prof.risk})"
    except Exception:  # noqa: BLE001 - escalation must never break routing
        return None
    return None


def role_of(policy: dict, subagent_type: str, label: str | None = None) -> str:
    roles = policy.get("roles") if isinstance(policy.get("roles"), dict) else {}
    agents = roles.get("agents") if isinstance(roles.get("agents"), dict) else _LIT_ROLES
    r = agents.get((subagent_type or "").lower())
    if r:
        return r
    if label:
        low = label.lower()
        for sub, rr in (roles.get("labels") or {}).items():
            if sub in low:
                return rr
    return roles.get("default") or "default"


def tier_block(policy: dict, tier: str) -> dict:
    """tiers[tier], else the api block, else the literal table."""
    tiers = policy.get("tiers") if isinstance(policy.get("tiers"), dict) else {}
    for t in (tier, "api"):
        blk = tiers.get(t)
        if isinstance(blk, dict) and isinstance(blk.get("roles"), dict):
            return blk
    return _LIT_TIERS.get(tier, _LIT_TIERS["api"])


def is_guarded(policy: dict, subagent_type: str, label: str | None = None) -> bool:
    roles = policy.get("roles") if isinstance(policy.get("roles"), dict) else {}
    guarded = roles.get("guarded") if isinstance(roles.get("guarded"), list) else _LIT_GUARDED
    return role_of(policy, subagent_type, label) in set(guarded)


def escalation_reason(policy: dict, subagent_type: str, text: str, cwd: str | None) -> str | None:
    """escalation_signal() for an executor: its role has an escalate target in some tier (legacy
    fallback: ``escalation.agents`` when the policy has no ``tiers``). Signature unchanged."""
    tiers = policy.get("tiers") if isinstance(policy.get("tiers"), dict) else {}
    if tiers:
        role = role_of(policy, subagent_type)
        member = any(role in (blk.get("escalate") or {}) for blk in tiers.values() if isinstance(blk, dict))
    else:
        esc = policy.get("escalation") if isinstance(policy.get("escalation"), dict) else {}
        member = (subagent_type or "").lower() in {str(a).lower() for a in esc.get("agents") or []}
    return escalation_signal(policy, text, cwd) if member else None


def resolve(policy: dict, subagent_type: str, *, asked: str | None, phrase_for, text: str, cwd: str | None,
            tier: str, usage_active: bool, flags: list, pin: str | None, label: str | None = None,
            asked_src: str = "param") -> tuple[str, str]:
    """-> (model, reason). ``asked`` = explicit model param or [label] (lowercase) or None;
    ``phrase_for(model)`` -> the user's override phrase for that model this turn, or None;
    ``flags`` = active global flags in precedence order; ``pin`` = per-project mode.
    Order: flags > pin > explicit (+phrase for guarded roles / fable) > role route (escalation,
    planned-small, size bump, judge phrase lift) > usage step-down > tier cap."""
    try:
        from lib import plan_tier, usage_guard  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        plan_tier = usage_guard = None  # type: ignore
    try:
        blk = tier_block(policy, tier)
        role = role_of(policy, subagent_type, label)
        order = policy.get("model_order") if isinstance(policy.get("model_order"), list) else _ORDER

        def finish(model: str, reason: str, *, user_said: bool = False) -> tuple[str, str]:
            if usage_active:
                if model == "fable":
                    model, reason = "sonnet", reason + "; usage-guard: fable paused -> sonnet"
                elif not user_said and usage_guard is not None:
                    d = usage_guard.step_down(model, role, tier, policy)
                    if d != model:
                        reason += f"; usage-guard: {model} -> {d}"
                        model = d
            c = plan_tier.cap(model, tier) if plan_tier is not None else model
            if c != model:
                reason += f"; tier-cap: {model} -> {c} ({tier})"
                model = c
            return model, reason

        if flags:
            return finish(flags[0], f"{flags[0]}-only-mode active", user_said=True)
        if pin:
            return finish(pin, "per-project model mode")
        if asked and asked in order:
            if asked != "fable" and not is_guarded(policy, subagent_type, label):
                return finish(asked, "explicit model param" if asked_src == "param" else "description label",
                              user_said=True)
            p = phrase_for(asked)
            if p:
                return finish(asked, f"explicit {asked} (user said '{p}')", user_said=True)
        roles = blk.get("roles") or {}
        model = roles.get(role) or roles.get("default") or "sonnet"
        reason = f"role {role} -> {model} (tier {tier})"
        esc = blk.get("escalate") or {}
        sig = escalation_signal(policy, text, cwd) if role in esc else None
        prof = None
        if sig:
            model = esc[role]
            reason += f"; escalated: {sig} -> {model}"
        elif role == "impl" and blk.get("impl_planned_small") and _plan_marker(policy, text):
            prof = _classify(text, cwd)
            if prof is not None and prof.size in ("S", "M"):
                model = blk["impl_planned_small"]
                reason += f"; planned small task (size {prof.size}) -> {model}"
        bumps = (blk.get("size_bumps") or {}).get(role)
        if bumps:
            prof = prof or _classify(text, cwd)
            if prof is not None and prof.size in bumps:
                model = bumps[prof.size]
                reason += f"; size bump {prof.size} -> {model}"
        said = False  # the user's own phrase this turn: the usage guard does not step it down
        lift = blk.get("judge_phrase_lift")
        if role == "judge" and lift and not asked:
            p = phrase_for(lift)
            if p:
                model, said = lift, True
                reason += f"; phrase lift (user said '{p}')"
        if asked == "fable" and order.index(model) < order.index("sonnet"):
            model = "sonnet"  # an unauthorised fable request still lands on sonnet, never below
        if asked and asked != model:
            reason += f"; explicit '{asked}' ignored (no '{asked}' override phrase in the user's turn)"
        return finish(model, reason, user_said=said)
    except Exception as exc:  # noqa: BLE001 - routing must never raise
        m = plan_tier.cap("sonnet", tier) if plan_tier is not None else "sonnet"
        return m, f"resolver error: {type(exc).__name__}"


__all__ = ["MODES", "modes_dir", "repo_key", "forced_mode", "set_mode", "cap_reason", "global_flags",
           "user_phrase", "escalation_signal", "escalation_reason", "role_of", "tier_block", "is_guarded",
           "resolve"]
