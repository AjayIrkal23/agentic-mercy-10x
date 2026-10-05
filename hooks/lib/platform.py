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
  run(cmd, ...)                 subprocess.run wrapper (never raises, no console window)
  shell_cmdline(cmd)            quoted cmd.exe command line for the .cmd shim fallback
  passes_cmd_exe(cmd)           False when a .cmd shim would have to carry an arg cmd.exe cannot
  spawn_worker(cmd, ...)        fire-and-forget background worker, no console window
  spawn_detached(cmd, ...)      spawn_worker with DEVNULL stdin (POSIX+Windows)
  popen_new_group(cmd, ...)     start child in own process group, return live Popen
  kill_tree(pid)                kill a process and its children, best-effort
  materialize(template, subs)   {PLACEHOLDER} substitution in a command list
  slugify_path(path)            filesystem-safe slug of an arbitrary path
  atomic_write(path, data)      write-to-temp + os.replace atomic file write
  replace_file(src, dst)        os.replace that retries a denied replace on Windows
  append_line(path, data)       concurrent-safe append of one record (bytes)
  locked_update(path, fn)       read-modify-write a JSON dict under a file lock
  locked_update_ok(path, fn)    same, returns (data, written)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Mapping, Sequence

IS_WINDOWS: bool = sys.platform.startswith("win")
if IS_WINDOWS:
    # A bare tool name (`git`, `whoami`, `npm`) is never resolved to a same-named file in the working
    # directory: a hostile checkout cannot shadow it (SEC1-04). An explicit value is kept.
    os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")

# Windows process creation flags. A background child gets CREATE_NO_WINDOW, never
# DETACHED_PROCESS: a detached child has no console, so every console program it
# starts (git, jcodemunch-mcp, npm, tasklist) allocates a visible one, and
# DETACHED_PROCESS also voids CREATE_NO_WINDOW when combined.
_NO_WINDOW = 0x08000000
_NEW_GROUP = 0x00000200


def no_window_kwargs() -> dict:
    """``creationflags`` that stop a console child from flashing a window (Windows only)."""
    return {"creationflags": _NO_WINDOW} if IS_WINDOWS else {}


def _utf8(text: bool) -> dict:
    """Text mode decodes as UTF-8 with replacement, never the ANSI code page: a fresh
    Windows box has no machine-wide PYTHONUTF8 and a 0x81 byte killed the reader thread (A6-03)."""
    return {"encoding": "utf-8", "errors": "replace"} if text else {}


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
    # CLAUDE_HOOK_STATE_DIR isolates test runs (tests/conftest.py)
    env = os.environ.get("CLAUDE_HOOK_STATE_DIR")
    d = Path(env).expanduser() if env else claude_dir() / "state"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def telemetry_dir() -> Path:
    # CLAUDE_HOOK_TELEMETRY_DIR isolates test and doctor runs (tests/conftest.py)
    env = os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR")
    d = Path(env).expanduser() if env else claude_dir() / "telemetry"
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

    Windows, anything that goes through cmd.exe (the `.cmd` shim fallback, or an explicit
    ``.cmd`` / ``.bat`` target, which CreateProcess runs under ``cmd /c``): see ``shell_cmdline``;
    an arg cmd.exe cannot deliver literally makes the call return 127 without running anything.
    """
    kw = dict(cwd=str(cwd) if cwd is not None else None, timeout=timeout,
              env=dict(env) if env is not None else None, capture_output=True, text=text, check=False,
              stdin=subprocess.DEVNULL if stdin_devnull else None, **_utf8(text), **no_window_kwargs())
    if IS_WINDOWS and cmd and str(cmd[0]).lower().endswith((".cmd", ".bat")):
        return _run_shell(cmd, kw) or subprocess.CompletedProcess(cmd, 127, "", "cannot start " + str(cmd[0]))
    try:
        return subprocess.run(list(cmd), **kw)  # noqa: S603 - trusted internal command lists
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", exc.stderr or "")
    except (OSError, ValueError) as exc:
        # Windows: a .cmd/.bat shim (the npm-installed `claude` CLI, `npx`, …) can't
        # be launched directly by CreateProcess — it raises OSError (WinError 193/2),
        # which is exactly the rc=127 seen for every `claude mcp add`/`claude plugin`.
        # Retry through the shell so cmd.exe resolves the shim. POSIX is untouched.
        return (_run_shell(cmd, kw) if IS_WINDOWS else None) or subprocess.CompletedProcess(cmd, 127, "", str(exc))


def _run_shell(cmd: Sequence[str], kw: dict) -> subprocess.CompletedProcess | None:
    """``cmd`` through cmd.exe as one quoted line: the result, a 124 on timeout, a 127 refusal, or
    None when it could not start (the caller reports that)."""
    try:
        line = shell_cmdline(cmd)
    except ValueError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", f"refused to run through cmd.exe: {exc}")
    try:
        return subprocess.run(line, shell=True, **kw)  # noqa: S602 - quoted, vetted line
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", exc.stderr or "")
    except (OSError, ValueError):
        return None


def _cmd_word(arg: str) -> str | None:
    """``arg`` as ONE cmd.exe word, or None when cmd.exe cannot deliver it literally. ``% ! CR LF`` never
    survive (variable expansion, delayed expansion, line truncation), and an odd number of `"` is refused
    (a truncated value or `k"&cmd&"`-style injection). Everything else is wrapped in double quotes with
    each `"` written as ``""`` (after doubling the backslashes in front of it): cmd.exe flips quote mode on
    every `"`, so the ``\\"`` form of the C runtime leaves the text between two escaped quotes OUTSIDE the
    quotes (`{"k":"v&w"}` ran `w"}`: proven on a real shim), while ``""`` keeps all of it inside. Measured
    on a real npm-style ``%*`` shim, Python and node receivers get the original arg back (18 of 18 vectors)."""
    if re.search(r"[%!\r\n]", arg) or arg.count('"') % 2:
        return None
    if arg and not re.search(r'[\s&|<>()^"]', arg):
        return arg
    out, slashes = ['"'], 0
    for ch in arg:
        if ch == "\\":
            slashes += 1
            continue
        out.append("\\" * (slashes * 2) + '""' if ch == '"' else "\\" * slashes + ch)
        slashes = 0
    return "".join(out) + "\\" * (slashes * 2) + '"'


def shell_cmdline(cmd: Sequence[str]) -> str:
    """A command line for ``shell=True`` (cmd.exe): every arg through ``_cmd_word``, so ``& | < > ( ) ^``
    stay literal in cmd's own parse AND in the second parse of an npm-style shim's ``%*`` (npm.cmd,
    npx.cmd, tsc.cmd); caret escaping survived only the first (SANTA1-06). Raises ValueError naming the
    arg that cmd.exe cannot carry (``run`` turns that into a 127 refusal, nothing is started)."""
    words = []
    for arg in cmd:
        word = _cmd_word(str(arg))
        if word is None:
            raise ValueError(f"arg {str(arg)!r} cannot be passed through cmd.exe literally "
                             "(it holds %, !, a line break or an odd number of double quotes)")
        words.append(word)
    return " ".join(words)


def passes_cmd_exe(cmd: Sequence[str]) -> bool:
    """False only when ``run(cmd)`` would have to go through cmd.exe and cannot carry an arg: Windows,
    ``cmd[0]`` has no ``.exe`` (CreateProcess starts that one directly) and resolves to a ``.cmd`` / ``.bat``
    shim, and ``shell_cmdline`` refuses an arg (``%``, ``!``, an odd number of ``"``). Ask BEFORE doing
    something that cannot be undone (SANTA1C-03: remove a server, then fail to add it back)."""
    if not IS_WINDOWS or not cmd:
        return True
    name = str(cmd[0])
    if shutil.which(name + ".exe") or not (shim := shutil.which(name)) or not shim.lower().endswith((".cmd", ".bat")):
        return True
    try:
        shell_cmdline(cmd)
    except ValueError:
        return False
    return True


def spawn_worker(
    cmd: Sequence[str],
    *,
    stdin_text: str | None = None,
    cwd: str | os.PathLike | None = None,
    env: Mapping[str, str] | None = None,
) -> int | None:
    """Fire-and-forget a background worker that outlives the caller. PID or None.

    POSIX: ``start_new_session=True``. Windows: ``CREATE_NO_WINDOW |
    CREATE_NEW_PROCESS_GROUP`` (never DETACHED_PROCESS, see ``_NO_WINDOW``). stdout and
    stderr are DEVNULL; ``stdin_text`` (if given) is the child's stdin, UTF-8, handed over as a
    delete-on-close temp file: a pipe holds 4 KB on Windows, so a bigger payload would block this
    caller until the child's interpreter started reading (A4v2-06). Temp file unavailable: the old
    pipe write. Never raises.
    """
    stdin_file = None
    if stdin_text is not None:
        try:
            import tempfile
            stdin_file = tempfile.TemporaryFile()
            stdin_file.write(stdin_text.encode("utf-8", "replace"))
            stdin_file.seek(0)
        except (OSError, ValueError):
            stdin_file = None
    kwargs: dict = {
        "cwd": str(cwd) if cwd is not None else None,
        "env": dict(env) if env is not None else None,
        "stdin": subprocess.DEVNULL if stdin_text is None else (stdin_file or subprocess.PIPE),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "text": True,
        **_utf8(True),  # UTF-8 whatever the locale: a cp1252 pipe raised on any other character
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = _NO_WINDOW | _NEW_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(list(cmd), **kwargs)  # noqa: S603
    except (OSError, ValueError):
        return None
    finally:
        if stdin_file is not None:
            stdin_file.close()  # the child holds its own handle; the file dies with the last one
    if stdin_text is not None and stdin_file is None:
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    return proc.pid


def spawn_detached(
    cmd: Sequence[str],
    *,
    cwd: str | os.PathLike | None = None,
    env: Mapping[str, str] | None = None,
) -> int | None:
    """Fire-and-forget a fully detached worker with no stdin. Returns the PID or None."""
    return spawn_worker(cmd, cwd=cwd, env=env)


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
        kwargs["creationflags"] = _NEW_GROUP
        if stdout is not None or stderr is not None:  # redirected: nothing to show a console for
            kwargs["creationflags"] |= _NO_WINDOW
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
                **no_window_kwargs(),
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
            return _pid_alive_windows(pid)
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, AttributeError):
        return False


def _pid_alive_windows(pid: int) -> bool:
    """OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) + exit code 259 (STILL_ACTIVE):
    ~0 ms and no window, where ``tasklist`` cost 115 ms and flashed a console (A4-15)."""
    import ctypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # own instance: no shared prototypes
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    k32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = k32.OpenProcess(0x1000, 0, pid)
    if not handle:
        return ctypes.get_last_error() == 5  # ACCESS_DENIED: it exists, we may not query it
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        k32.CloseHandle(handle)


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
            replace_file(tmp, target)
            return True
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    except OSError:
        return False


def replace_file(tmp: str | os.PathLike, target: str | os.PathLike) -> None:
    """``os.replace``; on Windows retry a denied replace (a reader holding the target open
    has no DELETE share) up to 20 times over ~0.6 s (A4-04). POSIX: one try."""
    for i in range(20):
        try:
            os.replace(tmp, target)
            return
        except PermissionError:
            if not IS_WINDOWS or i == 19:
                raise
            time.sleep(0.01 * (1 + i // 4))


_LOCK_WAIT_S = 10.0  # as long as LK_LOCK waited: ordinary contention must never drop an update


def _lock(fh, timeout: float | None = None) -> None:
    """Exclusive lock on ``fh``. Windows polls ``LK_NBLCK`` every 10 ms until ``timeout``
    (default ``_LOCK_WAIT_S``) then raises OSError, so only a genuinely stuck holder times
    out. POSIX blocks in flock."""
    if IS_WINDOWS:
        import msvcrt
        deadline = time.monotonic() + (_LOCK_WAIT_S if timeout is None else timeout)
        while True:
            fh.seek(0)
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
    else:
        import fcntl
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)


def append_line(path: str | os.PathLike, data: bytes) -> bool:
    """Append one record (bytes, already newline-terminated) without losing or
    interleaving it beside other writers. POSIX ``O_APPEND`` is atomic; on Windows it is
    seek-then-write, so the append runs under the ``<path>.lock`` lock, in binary mode
    (no CRLF). A stuck lock never drops the record (A4-05). True when written."""
    p = str(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)

    def _write() -> None:
        fd = os.open(p, flags, 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)

    try:
        if not IS_WINDOWS:
            _write()
            return True
        with open(p + ".lock", "a+") as lk:
            try:
                _lock(lk, timeout=1.0)  # a stuck holder costs 1 s, never the record
            except OSError:
                pass
            _write()
        return True
    except OSError:
        return False


def locked_update_ok(path: str | os.PathLike, fn, *, default=None) -> tuple:
    """:func:`locked_update` that also says whether ``fn``'s result reached the disk.

    Returns ``(data, written)``. Lock not obtained (holder stuck past ``_LOCK_WAIT_S``):
    ``(what is on disk now, False)``, ``fn`` is not applied, nothing is written, and a
    ``locked_update_timeout`` telemetry row says so. A file that exists but stays unreadable
    (``PermissionError`` after 3 tries 20 ms apart) is not "missing": same outcome, row
    ``locked_update_unreadable``, so a blank default never replaces real state. A failed
    ``atomic_write`` returns ``written=False`` and leaves a ``locked_update_write_failed`` row.
    """
    import json

    target = Path(path)
    data = dict(default or {})

    def _row(kind: str) -> None:
        try:
            from lib import hook_telemetry
            hook_telemetry.record("platform", kind, path=target.name)
        except Exception:  # noqa: BLE001
            pass

    def _read() -> tuple:
        """(dict, readable). Torn / corrupt JSON restarts from the default; a denied read is not corruption."""
        for attempt in range(3):
            try:
                loaded = json.loads(target.read_text(encoding="utf-8"))
                return (loaded if isinstance(loaded, dict) else data), True
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.02)
            except (OSError, ValueError):
                break
        else:
            return data, False
        return data, True

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target.with_name(target.name + ".lock"), "a+") as lock:
            try:
                _lock(lock)  # released when the handle closes
            except OSError:
                _row("locked_update_timeout")
                return _read()[0], False
            data, readable = _read()
            if not readable:
                _row("locked_update_unreadable")
                return data, False
            data = fn(data)
            written = atomic_write(target, json.dumps(data, indent=2))
            if not written:
                _row("locked_update_write_failed")
            return data, written
    except Exception:  # noqa: BLE001 - state is best-effort; callers stay fail-open
        return data, False


def locked_update(path: str | os.PathLike, fn, *, default=None) -> dict:
    """Read-modify-write a per-session JSON state file that several hooks share
    (audit J-01: plain read + write_text lost concurrent updates, and a torn read
    reset the evidence). Holds an exclusive lock on `<path>.lock`, applies
    `fn(data) -> data`, writes atomically. A missing or unreadable file starts from
    `default` (a fresh dict). Never raises; returns the dict it wrote (or tried to);
    when the lock could not be taken, the file's current content. See
    :func:`locked_update_ok` to learn whether the write happened.
    """
    return locked_update_ok(path, fn, default=default)[0]


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
    "no_window_kwargs",
    "shell_cmdline",
    "passes_cmd_exe",
    "spawn_worker",
    "spawn_detached",
    "popen_new_group",
    "kill_tree",
    "pid_alive",
    "materialize",
    "slugify_path",
    "atomic_write",
    "replace_file",
    "append_line",
    "locked_update",
    "locked_update_ok",
]
