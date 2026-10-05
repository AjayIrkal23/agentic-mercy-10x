#!/usr/bin/env python3
"""statusline.py — Claude Code status line: one line from the statusLine JSON on stdin.

    ◆ Opus 4.7 (xhigh) │ ▰▰▰▰▱▱▱▱▱▱ 42% │ $1.36 │ 5h 31% ↻18:40 │ ⎇ main +1 ~1 ?1 ↑1 │ ⏱ 12m │ +120 −34

Stdlib only, Python >= 3.10, any OS. Segments hide when their data is missing; bad input
prints ``◆ Claude`` and exits 0. Env: NO_COLOR, COLUMNS (drops segments right-to-left),
CLAUDE_STATUSLINE_CACHE_DIR (git cache, 5 s per directory; default $XDG_RUNTIME_DIR / temp).
"""

from __future__ import annotations

import json
import os
import sys
import time
import zlib

SEP = " │ "
GIT_TTL = 5.0
GIT_STALE = 60.0  # a timed-out git may fall back on the last good summary for this long, no longer
GIT_TIMEOUT = 1.5 if os.name == "nt" else 0.5  # Windows git on NTFS is 3-5x slower
GIT_ARGV = ["git", "--no-optional-locks", "status", "--porcelain=v2", "--branch"]  # a module constant: a test seam
GREEN, YELLOW, RED, CYAN, PURPLE, DIM = 78, 220, 203, 117, 141, 245


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def _get(d, *path):
    for k in path:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def _text(x, limit=24):
    return x.strip()[:limit] if isinstance(x, str) and x.strip() else None


def _painter(on: bool):
    return (lambda code, s: f"\x1b[38;5;{code}m{s}\x1b[0m") if on else (lambda code, s: s)


def _level(pct: float) -> int:
    return GREEN if pct < 50 else YELLOW if pct < 80 else RED


def seg_model(d, c):
    name = _text(_get(d, "model", "display_name"), 40) or "Claude"
    eff = _text(_get(d, "effort", "level"), 12)
    return c(CYAN, f"◆ {name}" + (f" ({eff})" if eff else "")), True


def seg_context(d, c):
    pct = _num(_get(d, "context_window", "used_percentage"))
    if pct is None:
        return None
    cells = max(0, min(10, int(pct // 10)))
    return c(_level(pct), "▰" * cells + "▱" * (10 - cells) + f" {pct:.0f}%"), True


def seg_cost(d, c):
    usd = _num(_get(d, "cost", "total_cost_usd"))
    return (c(DIM, f"${usd:.2f}"), True) if usd and usd >= 0.005 else None


def _hhmm(stamp):
    """resets_at as local HH:MM; accepts epoch seconds (or ms) and ISO-8601 strings."""
    try:
        v = _num(stamp)
        if v is None and isinstance(stamp, str):
            from datetime import datetime
            v = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00")).timestamp()
        return None if v is None else time.strftime("%H:%M", time.localtime(v / 1000 if v > 1e11 else v))
    except (ValueError, OverflowError, OSError):
        return None


def seg_limits(d, c):
    parts = []
    five = _num(_get(d, "rate_limits", "five_hour", "used_percentage"))
    if five is not None:
        when = _hhmm(_get(d, "rate_limits", "five_hour", "resets_at"))
        parts.append(c(_level(five), f"5h {five:.0f}%" + (f" ↻{when}" if when else "")))
    week = _num(_get(d, "rate_limits", "seven_day", "used_percentage"))
    if week is not None and week >= 50:
        parts.append(c(_level(week), f"7d {week:.0f}%"))
    return (" ".join(parts), False) if parts else None


def _cache_dir() -> str:
    base = os.environ.get("CLAUDE_STATUSLINE_CACHE_DIR")
    if base:
        return base
    run = os.environ.get("XDG_RUNTIME_DIR")
    if run:
        return os.path.join(run, "claude-statusline")
    who = os.getuid() if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
    tmp = os.environ.get("TMPDIR") or os.environ.get("TEMP") or os.environ.get("TMP")
    if not (tmp and os.path.isdir(tmp)):  # unset, or a dead drive: tempfile's writable fallback, imported only here
        import tempfile
        tmp = tempfile.gettempdir()
    return os.path.join(tmp, f"claude-statusline-{who}")


def _cache_path(cwd: str) -> str:
    k = cwd.encode("utf-8", "replace")  # crc32+adler32: no hashlib (its OpenSSL DLL costs ~10 ms on Windows)
    return os.path.join(_cache_dir(), f"{zlib.crc32(k):08x}{zlib.adler32(k):08x}.json")


def _parse_git(out: str):
    g = {"b": None, "ahead": 0, "behind": 0, "staged": 0, "mod": 0, "new": 0}
    oid = ""
    for line in out.splitlines():
        if line.startswith("# branch.oid "):
            oid = line[13:]
        elif line.startswith("# branch.head "):
            g["b"] = line[14:]
        elif line.startswith("# branch.ab "):
            a, b = line[12:].split()
            g["ahead"], g["behind"] = int(a[1:]), int(b[1:])
        elif line[:2] in ("1 ", "2 "):
            x, y = line[2], line[3]
            g["staged"] += x != "."
            g["mod"] += y != "."
        elif line.startswith("u "):
            g["mod"] += 1
        elif line.startswith("? "):
            g["new"] += 1
    if g["b"] == "(detached)":
        g["b"] = oid[:7]
    return g if g["b"] else None


def _kill_tree(p) -> None:
    """End git AND whatever it spawned (a fsmonitor hook, the `cmd\\git.exe` launcher's real git): a
    survivor holding the stdout pipe would make the next read wait for it (A3v2-01)."""
    import subprocess
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, timeout=5,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW
        else:
            import signal
            os.killpg(p.pid, signal.SIGKILL)  # git runs in its own session
    except Exception:  # noqa: BLE001 - already gone, no taskkill: p.kill() below still ends git itself
        pass
    try:
        p.kill()
    except OSError:
        pass


def _git_status(cwd: str):
    """git's porcelain summary, or None; raises TimeoutExpired after GIT_TIMEOUT with the whole tree
    killed. Not `subprocess.run(timeout=)`: on a timeout it kills only git, then waits for the pipe."""
    import subprocess
    try:
        p = subprocess.Popen(GIT_ARGV, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                             env={**os.environ, "LC_ALL": "C"},
                             **({} if os.name == "nt" else {"start_new_session": True}))
    except Exception:  # noqa: BLE001 - no git, bad dir: the segment just hides
        return None
    try:
        out, _ = p.communicate(timeout=GIT_TIMEOUT)
        return _parse_git(out) if p.returncode == 0 else None
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        try:
            p.communicate(timeout=1)  # the tree is dead, so the pipe is closed; never wait on a survivor
        except Exception:  # noqa: BLE001
            pass
        raise
    except Exception:  # noqa: BLE001 - unparsable output
        return None


def _store(path: str, entry: dict) -> None:
    tmp = f"{path}.{os.getpid()}"
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(entry, f)
        os.replace(tmp, path)  # Windows: PermissionError while another process reads the file
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def git_info(cwd: str):
    """Cached (5 s, per directory) git summary dict, or None when not a repo. A git timeout keeps the
    last good summary instead of caching a miss, but only for GIT_STALE seconds (past that a frozen
    branch / dirty count would mislead), and re-stamps the entry so the 5 s TTL applies and the next
    refreshes do not each wait out GIT_TIMEOUT. `ok` = when the summary was last really obtained."""
    path, last, ok, now = _cache_path(cwd), None, 0.0, time.time()
    try:
        with open(path, encoding="utf-8") as f:
            hit = json.load(f)
        last, ok = hit["g"], float(hit.get("ok", hit["t"]))
        if 0 <= now - hit["t"] < GIT_TTL:
            return last if now - ok < GIT_STALE else None
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        g = _git_status(cwd)
    except Exception:  # noqa: BLE001 - subprocess.TimeoutExpired
        _store(path, {"t": time.time(), "ok": ok, "g": last})
        return last if now - ok < GIT_STALE else None
    _store(path, {"t": time.time(), "g": g})
    return g


def seg_git(d, c):
    cwd = (_text(_get(d, "workspace", "current_dir"), 4096) or _text(d.get("cwd"), 4096)
           or _text(_get(d, "workspace", "project_dir"), 4096) or os.getcwd())
    g = git_info(cwd)
    if not g:
        return None
    bits = [f"⎇ {g['b']}"]
    for key, mark in (("staged", "+"), ("mod", "~"), ("new", "?"), ("ahead", "↑"), ("behind", "↓")):
        if g[key]:
            bits.append(f"{mark}{g[key]}")
    return c(PURPLE, " ".join(bits)), True


def seg_duration(d, c):
    ms = _num(_get(d, "cost", "total_duration_ms"))
    if not ms or ms < 1000:
        return None
    s = int(ms // 1000)
    txt = f"{s}s" if s < 60 else f"{s // 60}m" if s < 3600 else f"{s // 3600}h{s % 3600 // 60:02d}m"
    return c(DIM, f"⏱ {txt}"), False


def seg_lines(d, c):
    add = int(_num(_get(d, "cost", "total_lines_added")) or 0)
    rem = int(_num(_get(d, "cost", "total_lines_removed")) or 0)
    if not add and not rem:
        return None
    return f"{c(GREEN, f'+{add}')} {c(RED, f'−{rem}')}", False


def seg_mode(d, c):
    mode, name = _text(_get(d, "vim", "mode"), 12), _text(_get(d, "agent", "name"), 20)
    bits = ([f"vim {mode[0].upper()}"] if mode else []) + ([f"@{name}"] if name else [])
    return (c(DIM, " ".join(bits)), False) if bits else None


SEGMENTS = (seg_model, seg_context, seg_cost, seg_limits, seg_git, seg_duration, seg_lines, seg_mode)


def _width(s: str) -> int:
    out, skip = 0, False
    for ch in s:
        if ch == "\x1b":
            skip = True
        elif skip:
            skip = ch != "m"
        else:
            out += 1
    return out


def render(d: dict, color: bool, columns: int | None) -> str:
    c = _painter(color)
    segs = []
    for fn in SEGMENTS:
        try:
            r = fn(d, c)
        except Exception:  # noqa: BLE001 - one bad field must not blank the line
            r = None
        if r:
            segs.append(list(r))
    while columns and sum(_width(t) for t, _ in segs) + len(SEP) * (len(segs) - 1) > columns:
        drop = next((i for i in range(len(segs) - 1, -1, -1) if not segs[i][1]), None)
        if drop is None:
            break
        del segs[drop]
    return c(DIM, SEP).join(t for t, _ in segs)


def main() -> int:
    try:
        getattr(sys.stdout, "reconfigure", lambda **_: None)(  # Windows: cp1252 chokes on ▰, text mode writes \r\n
            encoding="utf-8", errors="replace", newline="\n")  # a lone surrogate prints `?`, never a traceback
        try:
            d = json.loads(sys.stdin.buffer.read().decode("utf-8-sig", "replace"))  # PowerShell pipes add a BOM
        except ValueError:
            d = {}
        cols = os.environ.get("COLUMNS", "")
        line = render(d if isinstance(d, dict) else {}, not os.environ.get("NO_COLOR"),
                      int(cols) if cols.isdigit() else None)
    except Exception:  # noqa: BLE001
        line = ""
    sys.stdout.write((line or "◆ Claude") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
