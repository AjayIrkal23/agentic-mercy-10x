"""model_mode.py — per-project subagent model mode (D4).

State file: ``<claude_dir>/state/model-modes/<repo_key>`` containing
``sonnet`` | ``opus`` | ``fable``. Consumers: opus-guard (Agent tool),
workflow-model-guard (Workflow tool), the prompt router (sets the mode from
explicit override phrases via ``set_mode``) and
``scripts/model-mode.py`` (CLI). The GLOBAL ``state/<mode>-only-mode`` flags stay
the kill-switch and are checked by the guards themselves, before this module.

repo_key = ``<basename>-<sha1(realpath(git root or cwd))[:12]>`` — the git root
(via lib.repo_context.git_root, which never treats $HOME as a repo) so every
subdir of a repo shares one mode. Everything fails soft: any error -> None /
False, never raises.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

try:
    from lib import platform as _plat
    from lib import repo_context as _rc
except Exception:  # noqa: BLE001 - never let an import failure brick a hook
    _plat = None  # type: ignore
    _rc = None  # type: ignore

MODES = ("sonnet", "opus", "fable")


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


def forced_mode(cwd: str | os.PathLike | None) -> str | None:
    """This repo's pinned model, or None (smart routing)."""
    key = repo_key(cwd)
    if not key:
        return None
    try:
        mode = (modes_dir() / key).read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return mode if mode in MODES else None


def set_mode(cwd: str | os.PathLike | None, model: str | None) -> bool:
    """Pin ``model`` for this repo, or clear the pin when ``model`` is None."""
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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(model + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


_DEFAULT_FLAGS = {"sonnet": "sonnet-only-mode", "opus": "opus-only-mode", "fable": "fable-only-mode"}


def global_flags(policy: dict | None = None) -> list[str]:
    """Active global kill-switch flags, in precedence order. Same files the guards read:
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


def escalation_reason(policy: dict, subagent_type: str, text: str, cwd: str | None) -> str | None:
    """Why an execution agent is lifted to ``escalation.to``, or None. Fail-open:
    a retry marker, else (no plan marker) prompt_router.classify size/risk >= heavy_qualifiers."""
    esc = policy.get("escalation")
    if not isinstance(esc, dict) or not esc.get("enabled"):
        return None
    if subagent_type not in {str(a).lower() for a in esc.get("agents") or []}:
        return None
    try:
        import re  # noqa: PLC0415
        if any(re.search(p, text, re.IGNORECASE) for p in esc.get("retry_markers") or []):
            return "previous attempt failed"
        if any(re.search(p, text, re.IGNORECASE) for p in esc.get("plan_markers") or []):
            return None  # a plan/spec/contract drives the work: Sonnet executes it
        from prompt_router.classify import classify  # noqa: PLC0415 - only on this path

        prof = classify({"prompt": text, "cwd": cwd or ""})
        hq = policy.get("heavy_qualifiers") or {}
        rank = {"S": 1, "M": 2, "L": 3}
        if (rank.get(prof.size, 0) >= rank.get(hq.get("min_size", "L"), 3)
                and prof.risk >= int(hq.get("min_risk", 2))):
            return f"large task with no plan (size {prof.size}, risk {prof.risk})"
    except Exception:  # noqa: BLE001 - escalation must never break routing
        return None
    return None


__all__ = ["MODES", "modes_dir", "repo_key", "forced_mode", "set_mode", "global_flags",
           "user_phrase", "escalation_reason"]
