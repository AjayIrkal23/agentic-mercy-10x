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


__all__ = ["MODES", "modes_dir", "repo_key", "forced_mode", "set_mode"]
