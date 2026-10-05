"""settings_install.py — render ``settings.json`` for the self-heal loop without losing the user's.

``ensure`` is what ``selfheal._ensure_settings`` runs. On the FIRST install over a settings.json
the workbench did not render, it keeps a permanent ``settings.json.pre-install`` (the dated
``.bak-*`` copies rotate) and seeds ``settings.user.json`` from the user's env / apiKeyHelper /
model / defaultMode / own hooks (``settings_seed``) before rendering, so Bedrock, proxy and
apiKeyHelper setups keep authenticating. Writes are atomic. Pure stdlib.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from tempfile import mkstemp
from typing import Callable

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import backups  # noqa: E402
import settings_seed  # noqa: E402
from lib import platform as plat  # noqa: E402

PRE_INSTALL = "settings.json.pre-install"


def _users_file(st: Path) -> dict | None:
    """The user's own settings.json (parsed), or None when there is nothing of theirs to keep."""
    keep = st.with_name(PRE_INSTALL)
    if not st.is_file() or keep.exists():
        return None
    try:
        data = json.loads(st.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}  # unreadable: still keep the copy, seed nothing
    return None if settings_seed.is_workbench_file(data) else (data if isinstance(data, dict) else {})


def _preserve(st: Path, user: dict, overlay: Path, render, subs, emit: Callable) -> None:
    keep = st.with_name(PRE_INSTALL)
    shutil.copy2(st, keep)
    keep.chmod(0o600)
    emit("settings", keep.name, "OK(permanent copy of your settings.json)")
    if overlay.exists() or not user:
        return
    seed = settings_seed.seed_overlay(user, json.loads(render.render(user_path=None, subs=subs)),
                                      render.CLAUDE_MANAGED_KEYS)
    if seed and plat.atomic_write(overlay, json.dumps(seed, indent=2, ensure_ascii=False) + "\n"):
        emit("settings", overlay.name, f"OK(seeded: {', '.join(sorted(seed))})")


def preserve_existing(target, env, emit: Callable) -> None:
    """FIRST thing the install pass does: keep the user's own settings.json (copy + overlay seed)
    before any step can touch it (lean-ctx's postinstall injects into it during the deps step)."""
    st = Path(target) / "settings.json"
    users = _users_file(st)
    if users is None:
        return
    try:
        import render  # type: ignore
        _preserve(st, users, Path(target) / "settings.user.json", render, getattr(env, "tokens", None), emit)
    except Exception as exc:  # noqa: BLE001
        emit("settings", PRE_INSTALL, f"WARN({exc})")


def ensure(target, env, emit: Callable, *, force: bool, stale: Callable[[Path], bool],
           preserved: bool = False) -> None:
    """``preserved``: ``preserve_existing`` already ran in this install pass, so a settings.json
    present now was written by a step of ours (lean-ctx) and is not the user's."""
    st = Path(target) / "settings.json"
    users = None if preserved else _users_file(st)
    # lean-ctx's first run (npm postinstall) injects hooks + allow rules: always re-render over
    # that; a settings.json that is not ours is rendered over too (after being kept)
    force = force or users is not None or (
        st.exists() and "lean-ctx" in st.read_text(encoding="utf-8", errors="replace"))
    is_stale = st.exists() and not force and stale(st)
    if st.exists() and not force and not is_stale:
        emit("settings", "settings.json", "PRESENT (kept)")
        return
    try:
        import render  # type: ignore
        subs, overlay = getattr(env, "tokens", None), Path(target) / "settings.user.json"
        if users is not None:
            _preserve(st, users, overlay, render, subs, emit)
        text = render.render(user_path=overlay, subs=subs)
        if st.exists():  # keep the user's Claude-managed keys (theme, tui, voice …) and additions
            text = render.carry_managed(text, st)
            if st.read_text(encoding="utf-8") != text:  # recoverable, bounded (A-09)
                emit("settings", backups.backup(st).name, "OK(backup)")
        fd, tmp = mkstemp(dir=str(st.parent), prefix=".settings-", suffix=".swap")  # atomic
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(text.encode("utf-8"))  # LF bytes == the equivalence baseline
            os.replace(tmp, st)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        emit("settings", "settings.json", "OK(rendered, was stale)" if is_stale else "OK(rendered)")
    except Exception as exc:  # noqa: BLE001
        emit("settings", "settings.json", f"WARN({exc})")
