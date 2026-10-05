"""winutil.py — small shared helpers of the Windows base-tool installers (wintools, winollama).

Path judgements that work on any OS (the Windows branches are tested on Ubuntu), the Python
probe behind ``pick_python`` (A5-01/A5-11: a Microsoft Store ``WindowsApps`` stub is not a Python),
``which`` (never a binary from the working directory), ``git_bash`` (the one rule for "this git
has a bash"), the Authenticode check of what we execute, and ``guard``, which turns a failed
install step into a status string. Pure stdlib.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
for _p in (str(_HERE), str(_HERE.parent / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from lib import platform as plat  # noqa: E402

COMPLETE = ".agentic-mercy-complete"  # written after a verified install, like ollama_setup.COMPLETE
GIT_BASH_VAR = "CLAUDE_CODE_GIT_BASH_PATH"
_PROBE = "import sys;print('%d.%d' % sys.version_info[:2])"


def _norm(p) -> str:
    return str(p).lower().replace("/", "\\").rstrip("\\")


def same_path(a, b) -> bool:
    """Two Windows paths as the same place: case, separators and a trailing separator ignored."""
    return _norm(a) == _norm(b)


def sha256_ok(path, want: str) -> bool:
    """True when ``path`` is a file whose SHA-256 equals ``want`` (a verified archive a failed run kept)."""
    p = Path(path)
    if not p.is_file():
        return False
    h = hashlib.sha256()
    try:
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return False
    return h.hexdigest() == (want or "").lower()


def drop(path) -> None:
    """Delete a file we are done with. A scanner or the indexer holding it open is not a failure: the
    install already worked (A5v2-03: the PermissionError used to turn INSTALLED into WARN)."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def store_stub(path) -> bool:
    """A Microsoft Store App Execution Alias (``...\\WindowsApps\\python3.exe``): not a real tool."""
    return "\\windowsapps\\" in _norm(path) + "\\"


def within(path, root) -> bool:
    return _norm(path).startswith(_norm(root) + "\\")


def ver(text) -> tuple[int, ...] | None:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return tuple(int(g) for g in m.groups() if g is not None) if m else None


def _here(p) -> str:
    return os.path.normcase(os.path.abspath(str(p)))


def which(name: str) -> str | None:
    """``shutil.which`` that never returns a binary from the current directory. Python 3.10/3.11 search
    the cwd FIRST on Windows (3.12 honours NoDefaultCurrentDirectoryInExePath), so a repo holding a
    ``claude.exe`` or ``py.exe`` would run at session start (SEC1B-01). The cwd counts only when it is
    really on PATH (not as ``.`` or an empty entry)."""
    hit = shutil.which(name)
    if hit and _here(os.path.dirname(hit)) == _here(os.getcwd()):
        real = {_here(e) for e in os.environ.get("PATH", "").split(os.pathsep) if e.strip() not in ("", ".")}
        return hit if _here(os.getcwd()) in real else None
    return hit


def git_bash(git, env_values) -> Path | None:
    """The ``bash.exe`` of a complete Git for Windows, or None. An env value (``CLAUDE_CODE_GIT_BASH_PATH``,
    process / user / machine scope) naming an existing ``bash.exe`` counts when a git is on PATH (``git``)
    or its root has a ``git.exe``; else walk up from ``git`` (at most 3 levels: ``cmd\\``, ``bin\\``,
    ``mingw64\\bin\\``, ``ucrt64\\bin\\``) for ``<root>\\bin\\bash.exe`` (SANTA1B-01)."""
    for v in env_values:
        b = Path(v) if v else None
        if b and b.name.lower() == "bash.exe" and b.is_file():
            root = b.parent.parent
            if git or (root / "cmd" / "git.exe").is_file() or (root / "bin" / "git.exe").is_file():
                return b
    for p in list(Path(git).parents)[:3] if git else []:
        if (p / "bin" / "bash.exe").is_file():
            return p / "bin" / "bash.exe"
    return None


def bash_values(environ, registry=None) -> list[str]:
    """``CLAUDE_CODE_GIT_BASH_PATH`` as the process, the user (HKCU) and the machine (HKLM) have it, in
    that order, for ``git_bash``: the ONE reader behind the installer's git-reuse rule and the doctor
    row (A5v2-10: the doctor read the process only and WARNed on a value only the registry held).
    ``registry`` is the ``winpath`` seam (``get`` / ``get_machine``); None or a locked hive = not set."""
    out = [environ.get(GIT_BASH_VAR, "")]
    for read in ("get", "get_machine"):
        try:
            out.append((getattr(registry, read)(GIT_BASH_VAR) or ("",))[0])
        except Exception:  # noqa: BLE001  (no winreg off Windows, a locked hive: just not set)
            pass
    return out


_SIG_PS = ("$s=Get-AuthenticodeSignature -LiteralPath $env:AM_FILE;$s.Status;"
           "if($s.SignerCertificate){$s.SignerCertificate.GetNameInfo('SimpleName',$false)}")


def signature_problem(path, run: Callable, environ, signers=None) -> str | None:
    """None when ``path`` may run, else a WARN row. ``signers`` (exact certificate names) demands a Valid
    Authenticode signature by one of them; None (the PortableGit SFX, whose signer is not documented
    here) accepts Valid by anyone or no signature at all (the pinned SHA-256 is the control) and
    refuses a signature that is present but bad. PowerShell is called by its System32 path."""
    root = (environ.get("SystemRoot") or environ.get("windir")
            or os.path.join(environ.get("SystemDrive", "C:") + os.sep, "Windows"))
    ps = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    cp = run([str(ps), "-NoProfile", "-NonInteractive", "-Command", _SIG_PS], timeout=120, stdin_devnull=True,
             env={**os.environ, "AM_FILE": str(path)})
    lines = (cp.stdout or "").strip().splitlines() if cp.returncode == 0 else []
    status, who = (lines[0].strip() if lines else ""), (lines[1].strip() if len(lines) > 1 else "")
    ok = (status == "Valid" and (signers is None or who in signers)) or (signers is None and status == "NotSigned")
    return None if ok else f"WARN({Path(path).name} signature {status or 'unreadable'}{': ' + who if who else ''} - refused)"


def pick_python(which: Callable = which, run: Callable = plat.run, tools=None, current=None) -> list[str] | None:
    """The first working Python >= 3.10 as an argv prefix: ``py -3``, a PATH python, the tools-dir one,
    then ``current`` (the interpreter running the caller: install.ps1's Python is on the registry PATH,
    not on this process's yet); Store stubs are never run. None when there is none."""
    cands: list[list[str]] = []
    if (p := which("py")) and not store_stub(p):
        cands.append([p, "-3"])
    cands += [[p] for p in (which("python"), which("python3")) if p and not store_stub(p)]
    if tools and (Path(tools) / "python" / "python.exe").is_file():
        cands.append([str(Path(tools) / "python" / "python.exe")])
    if current and not store_stub(current):
        cands.append([str(current)])
    for c in cands:
        cp = run([*c, "-c", _PROBE], timeout=30, stdin_devnull=True)
        v = ver(cp.stdout) if cp.returncode == 0 else None
        if v and v >= (3, 10):
            return c
    return None


def win_arch(environ) -> str:
    a = (environ.get("PROCESSOR_ARCHITEW6432") or environ.get("PROCESSOR_ARCHITECTURE") or "AMD64").upper()
    return "arm64" if a == "ARM64" else "x64"


def free_bytes(path) -> int:
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def guard(fn: Callable) -> str:
    """Run an install step; a blocked network or a bad zip is a WARN row, never a crash."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        return "WARN(checksum mismatch — refused)" if "checksum" in msg else f"WARN({type(exc).__name__}: {msg[:90]})"
