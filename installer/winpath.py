"""winpath.py — the Windows tools dir and the per-user environment (PATH, env vars, Run key).

``wintools`` / ``winollama`` install into one user-owned tools dir and need it on PATH for the
NEXT terminal (registry) and for THIS process and its children (``os.environ``). Everything that
touches ``HKCU`` goes through a ``registry`` object (``get`` / ``set`` / ``broadcast``) so the
tests inject a fake; ``WinRegistry`` is the real one and imports ``winreg`` / ``ctypes.windll``
only when used. Never ``setx`` (it downgrades REG_EXPAND_SZ to REG_SZ and cuts at 1024 chars).
``AGENTIC_MERCY_SANDBOX=1`` (the sandbox rehearsal) skips every registry write; the in-process
environment still updates. Pure stdlib.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

TOOLS_ENV = "AGENTIC_MERCY_TOOLS_DIR"
SANDBOX_ENV = "AGENTIC_MERCY_SANDBOX"
ENV_KEY = "Environment"
MACHINE_ENV_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def tools_dir(environ=None) -> Path:
    """``$AGENTIC_MERCY_TOOLS_DIR`` else ``%LOCALAPPDATA%\\Programs\\agentic-mercy`` (no admin). Under
    ``AGENTIC_MERCY_SANDBOX=1`` the default is derived from USERPROFILE instead: a rehearsal redirects
    the profile but inherits the real LOCALAPPDATA, which would put gigabytes in the real profile."""
    environ = os.environ if environ is None else environ
    if environ.get(TOOLS_ENV):
        return Path(environ[TOOLS_ENV])
    home = environ.get("USERPROFILE") or str(Path.home())
    base = (str(Path(home) / "AppData" / "Local") if sandboxed(environ)
            else environ.get("LOCALAPPDATA") or str(Path(home) / "AppData" / "Local"))
    return Path(base) / "Programs" / "agentic-mercy"


def outside_profile(path, environ=None) -> bool:
    """True when ``path`` is under neither USERPROFILE nor LOCALAPPDATA (SEC1B-02: a shared folder such
    as ``D:\\Dev`` may be writable by other local users, and its tools go first on the user PATH)."""
    environ = os.environ if environ is None else environ

    def flat(p) -> str:
        return str(p).lower().replace("\\", "/").rstrip("/") + "/"
    roots = [environ.get("USERPROFILE") or str(Path.home()), environ.get("LOCALAPPDATA") or ""]
    return not any(r and flat(path).startswith(flat(r)) for r in roots)


def sandboxed(environ=None) -> bool:
    return (os.environ if environ is None else environ).get(SANDBOX_ENV) == "1"


# where uv / npm / pipx put installed tools; a rehearsal that inherits them installs into the real dirs
_TOOL_LOCATION_VARS = ("UV_TOOL_DIR", "UV_TOOL_BIN_DIR", "UV_PYTHON_INSTALL_DIR", "NPM_CONFIG_PREFIX",
                       "PIPX_HOME", "PIPX_BIN_DIR")


def scrub_sandbox_env(environ=None) -> list[str]:
    """Under ``AGENTIC_MERCY_SANDBOX=1`` drop the inherited tool-location variables (any case), so every
    install lands in the throwaway profile; caches (``UV_CACHE_DIR`` ...) stay shared. Returns the names."""
    environ = os.environ if environ is None else environ
    if not sandboxed(environ):
        return []
    gone = [k for k in list(environ) if k.upper() in _TOOL_LOCATION_VARS]
    for k in gone:
        del environ[k]
    return gone


class WinRegistry:
    """The real ``HKCU`` access behind the seam. Values are ``(str, "REG_SZ"|"REG_EXPAND_SZ")``."""

    def get(self, name: str, key: str = ENV_KEY):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ) as k:
                value, kind = winreg.QueryValueEx(k, name)
        except FileNotFoundError:
            return None
        return str(value), ("REG_EXPAND_SZ" if kind == winreg.REG_EXPAND_SZ else "REG_SZ")

    def get_machine(self, name: str):
        """Read-only: the same value in ``HKLM`` (system environment)."""
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, MACHINE_ENV_KEY, 0, winreg.KEY_READ) as k:
                value, kind = winreg.QueryValueEx(k, name)
        except FileNotFoundError:
            return None
        return str(value), ("REG_EXPAND_SZ" if kind == winreg.REG_EXPAND_SZ else "REG_SZ")

    def set(self, name: str, value: str, kind: str = "REG_SZ", key: str = ENV_KEY) -> None:
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, getattr(winreg, kind), value)

    def broadcast(self) -> None:
        """WM_SETTINGCHANGE("Environment") so Explorer and new terminals re-read the environment."""
        import ctypes
        fn = ctypes.windll.user32.SendMessageTimeoutW
        fn.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_wchar_p,
                       ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_size_t)]
        # HWND_BROADCAST, WM_SETTINGCHANGE, SMTO_ABORTIFHUNG, 5 s per window
        fn(0xFFFF, 0x001A, 0, "Environment", 0x2, 5000, ctypes.byref(ctypes.c_size_t()))


def _norm(entry: str, environ=None) -> str:
    """A PATH entry as compared for duplicates: %VAR% expanded, case and trailing separator ignored."""
    env = {k.upper(): v for k, v in (os.environ if environ is None else environ).items()}
    out = re.sub(r"%([^%]+)%", lambda m: env.get(m.group(1).upper(), m.group(0)), entry.strip())
    return out.lower().rstrip("\\/")


def add_user_path(dirs, registry, environ=None) -> list[str]:
    """Put the ``dirs`` the user PATH lacks first (one already there keeps the user's order, SANTA2B-01;
    this process's PATH still gets all of them first): the registry value keeps its kind (REG_EXPAND_SZ when
    absent), duplicates (case-insensitive, %VAR% expanded) are dropped, nothing is truncated, the
    broadcast follows the write, and this process's PATH gets the same dirs. A PATH that already
    reads right is not rewritten. Returns the dirs. (ponytail: a literal ``%`` in a dir name would
    be expanded by Windows; tools dirs never contain one.)"""
    environ = os.environ if environ is None else environ
    new: list[str] = []
    for d in map(str, dirs):
        if _norm(d, environ) not in {_norm(x, environ) for x in new}:
            new.append(d)
    drop = {_norm(d, environ) for d in new}
    if not sandboxed(environ):
        raw, kind = registry.get("Path") or ("", "REG_EXPAND_SZ")
        have = {_norm(e, environ) for e in raw.split(";") if e.strip()}
        missing = [d for d in new if _norm(d, environ) not in have]  # present ones keep the user's order
        if missing:
            registry.set("Path", ";".join(missing + [e for e in raw.split(";") if e.strip()]), kind)
            registry.broadcast()
    rest = [e for e in environ.get("PATH", "").split(os.pathsep) if e and _norm(e, environ) not in drop]
    environ["PATH"] = os.pathsep.join(new + rest)
    return new


def set_user_env(name: str, value: str, registry, environ=None) -> None:
    """A per-user REG_SZ variable (new terminals) plus this process; unchanged values are not rewritten."""
    environ = os.environ if environ is None else environ
    if not sandboxed(environ):
        have = registry.get(name)
        if not have or have[0] != value:
            registry.set(name, value, "REG_SZ")
            registry.broadcast()
    environ[name] = value


def set_run_value(name: str, command: str, registry, environ=None) -> bool:
    """One ``HKCU\\...\\Run`` autostart value (no admin, no broadcast). False in the sandbox."""
    if sandboxed(environ):
        return False
    have = registry.get(name, RUN_KEY)
    if not have or have[0] != command:
        registry.set(name, command, "REG_SZ", RUN_KEY)
    return True
