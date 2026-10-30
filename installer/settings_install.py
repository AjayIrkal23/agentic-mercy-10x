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
import platform as _platform
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
from lib import oomguard_config as ogc  # noqa: E402
from relocation import PRE_INSTALL as _SUFFIX  # noqa: E402  (the one `.pre-install` suffix)

PRE_INSTALL = "settings.json" + _SUFFIX


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


def _subs(env) -> dict | None:
    """The render tokens of this machine: `env.tokens` plus the status line's real interpreter
    (`render.machine_subs` adds the same; without it statusLine fell back to `python3`)."""
    tokens = getattr(env, "tokens", None)
    if tokens is None:
        return None
    return {**tokens, "PYTHON_EXE": getattr(env, "python_exe", None) or "python3"}


def preserve_existing(target, env, emit: Callable) -> None:
    """FIRST thing the install pass does: keep the user's own settings.json (copy + overlay seed)
    before any step can touch it (lean-ctx's postinstall injects into it during the deps step)."""
    st = Path(target) / "settings.json"
    users = _users_file(st)
    if users is None:
        return
    try:
        import render  # type: ignore
        _preserve(st, users, Path(target) / "settings.user.json", render, _subs(env), emit)
    except Exception as exc:  # noqa: BLE001
        emit("settings", PRE_INSTALL, f"WARN({exc})")


def _mem_total_mb() -> int:
    """MemTotal in MB from /proc/meminfo; 0 on failure (Windows, macOS, no /proc)."""
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


_PERMISSION_MODES = {"default", "acceptEdits", "plan", "bypassPermissions", "dontAsk"}


def machine_sizes(total_mb: int) -> dict[str, str]:
    """Per-machine env sized from MemTotal (MB); {} when unknown. The tool cap follows the one memory rule
    (ogc.memory_cap_mb, F7). The agent floors serve launches bin/claude does not size (-p, --bare, nested,
    no user bus); they scale with RAM (F6): 3 subagents / 2 workflow agents at 15-20 GB, 5 / 4 at 25-30 GB."""
    if total_mb <= 0:
        return {}
    sub = min(6, max(2, total_mb // 5120))
    return {"CLAUDE_CODE_TOOL_MEMORY_LIMIT": f"{ogc.memory_cap_mb(total_mb)}M",
            "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": str(sub),
            "CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS": str(max(1, sub - 1))}


def seed_machine_overlay(target, emit: Callable, *, environ=None, mem_total_mb=None, system=None,
                         fresh: bool = False) -> list[str]:
    """Per-machine keys a tracked template cannot know, written into settings.user.json (mode 600,
    atomic) only when absent, so render, hooks and runtime agree:
    - ``env.OLLAMA_HOST`` from the install-time environment (a remote ollama box, FI-1);
    - ``env.CLAUDE_CODE_TOOL_MEMORY_LIMIT`` = MemTotal minus 4 GiB, never below half (F7), and the two
      agent floors ``CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`` / ``CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS``
      (F6), on Linux, from ``machine_sizes()``. The tool cap caps ONE cgroup (``app.slice/claude-code-bash``)
      that every session's tool commands share, so it is machine-wide (FI-3, REVERIFY R5); the template's
      6G / 5 / 4 stay the floor where nothing sizes them;
    - on a ``fresh`` install (no settings.json before): ``permissions.defaultMode`` =
      ``$AGENTIC_MERCY_PERMISSION_MODE`` or ``acceptEdits``, and remote control only with bypass (SP-1).
    Returns the seeded key names."""
    environ = os.environ if environ is None else environ
    p = Path(target) / "settings.user.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (OSError, ValueError):
        emit("settings", "settings.user.json", "WARN(unreadable; not seeded)")
        return []
    env = data.get("env") if isinstance(data.get("env"), dict) else {}
    seeded: list[str] = []
    host = str(environ.get("OLLAMA_HOST") or "").strip()
    if host and not env.get("OLLAMA_HOST"):
        env["OLLAMA_HOST"] = host
        seeded.append("OLLAMA_HOST")
    if (system or _platform.system()) == "Linux":
        total = mem_total_mb if mem_total_mb is not None else _mem_total_mb()
        for key, value in machine_sizes(total).items():
            if key not in env:  # a value already there is the user's: kept
                env[key] = value
                seeded.append(key)
    if env:
        data["env"] = env
    if fresh and "permissions" not in data:
        mode = str(environ.get("AGENTIC_MERCY_PERMISSION_MODE") or "").strip()
        mode = mode if mode in _PERMISSION_MODES else "acceptEdits"
        data["permissions"] = {"defaultMode": mode}
        data.setdefault("remoteControlAtStartup", mode == "bypassPermissions")
        seeded.append("permissions.defaultMode")
    if seeded:
        if plat.atomic_write(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n"):  # mkstemp: 0600
            try:
                p.chmod(0o600)
            except OSError:
                pass
            emit("settings", "settings.user.json", "OK(seeded " + ", ".join(seeded) + ")")
        else:
            emit("settings", "settings.user.json", "WARN(write failed; not seeded)")
            return []
    return seeded


def seed_askpass(target, emit: Callable) -> bool:
    """POSIX: the tracked ``scripts/sudo-askpass.example.sh`` becomes the gitignored
    ``scripts/sudo-askpass.sh`` (mode 700) once the owner opts in with a non-empty ``LOCAL_SUDO_PASS`` in
    ``<target>/.env``. The helper reads that file when sudo calls it; no password is copied anywhere. An
    existing helper is the owner's and is never replaced (F8)."""
    if os.name != "posix":
        return False
    t = Path(target)
    src, dst = t / "scripts" / "sudo-askpass.example.sh", t / "scripts" / "sudo-askpass.sh"
    try:
        lines = (t / ".env").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    opted_in = any(ln.strip().removeprefix("export ").strip().partition("=")[0] == "LOCAL_SUDO_PASS"
                   and ln.partition("=")[2].strip().strip("'\"") for ln in lines)
    if not opted_in or dst.exists() or dst.is_symlink() or not src.is_file():
        return False
    try:
        shutil.copyfile(src, dst)
        dst.chmod(0o700)
    except OSError as exc:
        emit("settings", dst.name, f"WARN({type(exc).__name__})")
        return False
    emit("settings", dst.name, "OK(from sudo-askpass.example.sh, mode 700)")
    return True


def permission_line(target) -> str | None:
    """The checklist line naming the permission mode a fresh install seeded, else None."""
    try:
        data = json.loads((Path(target) / "settings.user.json").read_text(encoding="utf-8"))
        mode = data["permissions"]["defaultMode"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return (f"Permission mode on this machine: {mode} (set permissions.defaultMode in "
            "~/.claude/settings.user.json to change it).")


def _tier_first(target, render) -> None:
    """No state/plan-tier.json yet (fresh install): detect the tier before the first render, so the
    tier keys are right in round 1 instead of after the `plan-tier` post step and a second round."""
    try:
        from lib import plan_tier  # noqa: PLC0415
        if not plan_tier.state_path().is_file():
            render._detect_tier_first(Path(target))
    except Exception:  # noqa: BLE001 - the post step still detects it
        pass


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
        subs, overlay = _subs(env), Path(target) / "settings.user.json"
        if users is not None:
            _preserve(st, users, overlay, render, subs, emit)
        _tier_first(target, render)  # a fresh HOME renders tier-correct in round 1 (FIX-r2 I7)
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
