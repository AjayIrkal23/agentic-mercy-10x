"""platform.py — the ONE cross-platform branching point.

Pure Python 3 stdlib. No hardcoded absolute paths (everything via
``pathlib`` + ``os.path.expanduser``). Windows and POSIX both supported; the
single ``sys.platform`` test lives here so no other module in the system needs
to branch on the OS.

Exports:
  IS_WINDOWS                    bool
  claude_dir()                  Path to ~/.claude
  state_dir()                   Path to ~/.claude/state (created)
  telemetry_dir()               Path to ~/.claude/telemetry (created)
  attic_dir()                   Path to ~/.claude/attic/<date> (not auto-created)
  hooks_dir()                   Path to ~/.claude/hooks
  python_exe()                  best-effort python interpreter path (str)
  node_exe()                    best-effort node interpreter path (str) or None
  run(cmd, ...)                 subprocess.run wrapper (never raises)
  spawn_detached(cmd, ...)      fire-and-forget detached worker (POSIX+Windows)
  popen_new_group(cmd, ...)     start child in own process group, return live Popen
  kill_tree(pid)                kill a process and its children, best-effort
  materialize(template, subs)   {PLACEHOLDER} substitution in a command list
  slugify_path(path)            filesystem-safe slug of an arbitrary path
  atomic_write(path, data)      write-to-temp + os.replace atomic file write
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Mapping, Sequence

IS_WINDOWS: bool = sys.platform.startswith("win")


# --------------------------------------------------------------------------- #
# Canonical directories (all derived from ~ — never a literal /home/... path)
# --------------------------------------------------------------------------- #
def claude_dir() -> Path:
    """Return ~/.claude. Honours CLAUDE_CONFIG_DIR when the harness sets it."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path("~/.claude").expanduser()


def hooks_dir() -> Path:
    return claude_dir() / "hooks"


def state_dir() -> Path:
    d = claude_dir() / "state"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def telemetry_dir() -> Path:
    d = claude_dir() / "telemetry"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def attic_dir(date: str = "2026-07-11") -> Path:
    """Return ~/.claude/attic/<date>. Not auto-created (attic moves are explicit)."""
    return claude_dir() / "attic" / date


# --------------------------------------------------------------------------- #
# Interpreter discovery
# --------------------------------------------------------------------------- #
def python_exe() -> str:
    """Best-effort path to a Python 3 interpreter.

    Prefer the running interpreter (``sys.executable``); fall back to PATH.
    """
    if sys.executable:
        return sys.executable
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return found
    return "python3"


def node_exe() -> str | None:
    """Best-effort path to a Node interpreter, or None when absent."""
    for name in ("node", "nodejs"):
        found = shutil.which(name)
        if found:
            return found
    return None


# --------------------------------------------------------------------------- #
# Process control
# --------------------------------------------------------------------------- #
def run(
    cmd: Sequence[str],
    *,
    cwd: str | os.PathLike | None = None,
    timeout: float | None = None,
    env: Mapping[str, str] | None = None,
    text: bool = True,
    stdin_devnull: bool = False,
) -> subprocess.CompletedProcess:
    """subprocess.run that never raises — returns a CompletedProcess.

    On timeout/OSError a synthetic CompletedProcess with returncode 124/127 is
    returned so callers can stay fail-open. Pass ``stdin_devnull=True`` for a
    possibly-interactive child (e.g. an ``npx`` installer) so it gets EOF instead
    of blocking on a prompt — the timeout then bounds any residual wait.
    """
    try:
        return subprocess.run(  # noqa: S603 - trusted internal command lists
            list(cmd),
            cwd=str(cwd) if cwd is not None else None,
            timeout=timeout,
            env=dict(env) if env is not None else None,
            capture_output=True,
            text=text,
            check=False,
            stdin=subprocess.DEVNULL if stdin_devnull else None,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", exc.stderr or "")
    except (OSError, ValueError) as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def spawn_detached(
    cmd: Sequence[str],
    *,
    cwd: str | os.PathLike | None = None,
    env: Mapping[str, str] | None = None,
) -> int | None:
    """Fire-and-forget a fully detached worker. Returns the PID or None.

    POSIX: ``start_new_session=True`` (new session, survives parent exit).
    Windows: ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP``.
    Never raises.
    """
    kwargs: dict = {
        "cwd": str(cwd) if cwd is not None else None,
        "env": dict(env) if env is not None else None,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    try:
        if IS_WINDOWS:
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            kwargs["creationflags"] = flags
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(list(cmd), **kwargs)  # noqa: S603
        return proc.pid
    except (OSError, ValueError):
        return None


def popen_new_group(
    cmd: Sequence[str] | str,
    *,
    shell: bool = False,
    cwd: str | os.PathLike | None = None,
    env: Mapping[str, str] | None = None,
    stdout=None,
    stderr=None,
):
    """Start a child in its OWN process group and return the live Popen handle.

    Unlike :func:`spawn_detached` (fire-and-forget, DEVNULL, returns only a PID),
    this returns the ``subprocess.Popen`` so the caller can ``poll()``/``wait()``
    for readiness and later ``kill_tree(proc.pid)`` the whole group.

    POSIX: ``start_new_session=True`` (new session ⇒ new process group ⇒ the whole
    tree is reachable via ``killpg``).
    Windows: ``CREATE_NEW_PROCESS_GROUP`` (so ``taskkill /T`` reaches the tree).
    Raises the underlying OSError (callers that must stay fail-open should guard).
    """
    kwargs: dict = {
        "cwd": str(cwd) if cwd is not None else None,
        "env": dict(env) if env is not None else None,
        "stdout": stdout,
        "stderr": stderr,
        "shell": shell,
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x00000200  # CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(list(cmd) if not shell else cmd, **kwargs)  # noqa: S603


def kill_tree(pid: int) -> None:
    """Best-effort kill of a process (and its group/children). Never raises."""
    try:
        if IS_WINDOWS:
            subprocess.run(  # noqa: S603,S607
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                check=False,
            )
        else:
            import signal

            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    os.kill(pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
    except Exception:  # noqa: BLE001 - kill must never raise
        pass


def pid_alive(pid: int) -> bool:
    """True if a PID is currently live. Best-effort, cross-platform."""
    if pid <= 0:
        return False
    try:
        if IS_WINDOWS:
            out = subprocess.run(  # noqa: S603,S607
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in (out.stdout or "")
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


# --------------------------------------------------------------------------- #
# Command templating
# --------------------------------------------------------------------------- #
def materialize(template: Iterable[str], subs: Mapping[str, str]) -> list[str]:
    """Substitute ``{KEY}`` placeholders in a command template list.

    Placeholders use braces, e.g. ``["{PY}", "{HOOKS}/x.py"]`` with
    ``subs={"PY": python_exe(), "HOOKS": str(hooks_dir())}``. Unknown
    placeholders are left verbatim (no KeyError).
    """
    out: list[str] = []
    for part in template:
        s = str(part)
        for key, val in subs.items():
            s = s.replace("{" + key + "}", str(val))
        out.append(s)
    return out


# --------------------------------------------------------------------------- #
# Filesystem helpers
# --------------------------------------------------------------------------- #
def slugify_path(path: str | os.PathLike) -> str:
    """A filesystem-safe, collision-resistant slug of an arbitrary path.

    Used for per-repo state filenames. Deterministic and portable.
    """
    import hashlib

    norm = str(path).replace("\\", "/").rstrip("/")
    name = Path(norm).name or "root"
    digest = hashlib.sha1(norm.encode("utf-8", "replace")).hexdigest()[:8]
    safe = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in name)
    return f"{safe}-{digest}"


def atomic_write(path: str | os.PathLike, data: str, *, encoding: str = "utf-8") -> bool:
    """Atomic file write: temp file in the same dir + os.replace. Never raises.

    Returns True on success, False on failure (caller stays fail-open).
    """
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp-", suffix=".swap")
        try:
            with os.fdopen(fd, "w", encoding=encoding) as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)
            return True
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    except OSError:
        return False


__all__ = [
    "IS_WINDOWS",
    "claude_dir",
    "hooks_dir",
    "state_dir",
    "telemetry_dir",
    "attic_dir",
    "python_exe",
    "node_exe",
    "run",
    "spawn_detached",
    "popen_new_group",
    "kill_tree",
    "pid_alive",
    "materialize",
    "slugify_path",
    "atomic_write",
]
