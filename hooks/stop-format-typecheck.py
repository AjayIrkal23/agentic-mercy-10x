#!/usr/bin/env python3
"""stop-format-typecheck.py: Stop gate, once per human turn, 6 s link budget.

Checks only the files this turn edited (lib/turns.turn_written_files), batched per
project: the formatter in ``--check`` mode (biome > prettier for JS/TS, ruff for Python;
detection after ECC's resolve-formatter.js) and ``tsc --noEmit --incremental`` with the
tsbuildinfo under ``state/typecheck/`` (never written into the repo). Problems in edited
files block once with a reason <= 1,200 chars; errors elsewhere are counted, not blocking.

Never downloads a tool: ``node_modules/.bin/<tool>`` then ``shutil.which``. Skipped at
memory tier warn+ (lib/memwatch_state), with more than 20 edited files, past the time
budget, on ``stop_hook_active`` and under CLAUDE_HOOK_DOCTOR. State:
``state/<sid>.typecheck.json`` {turn_key, result: pass|block|skip|timeout, reason, tools,
files, other_errors, ts}. Output ``{"decision": "block", "reason": ...}`` or ``{}``.
Fails open on any error.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

from lib import platform as plat  # noqa: E402

DEADLINE_S = 5.4
TOOL_CAP_S = {"formatter": 2.5, "ruff_check": 1.5, "tsc": 3.0}
MIN_START_S = 0.4
MAX_FILES = 20
REASON_MAX = 1200
MAX_LINES = 20
JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
PY_EXT = (".py",)
TS_EXT = (".ts", ".tsx")
BIOME = ("biome.json", "biome.jsonc")
PRETTIER = (".prettierrc", ".prettierrc.json", ".prettierrc.js", ".prettierrc.cjs", ".prettierrc.mjs",
            ".prettierrc.yml", ".prettierrc.yaml", ".prettierrc.toml", ".prettierrc.json5", ".prettierrc.ts",
            "prettier.config.js", "prettier.config.cjs", "prettier.config.mjs", "prettier.config.ts")
RUFF = ("ruff.toml", ".ruff.toml")
ROOT_MARKERS = ("package.json", "pyproject.toml") + BIOME + PRETTIER + RUFF
TS_DIAG = re.compile(r"^(.+?)\((\d+),(\d+)\): error TS\d+")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
FIX = ("Fix: edit the named files, or run the formatter with --write / fix the TS errors through Bash, "
       "then finish.")


class _Budget(Exception):
    pass


class _Timeout(Exception):
    pass


def _safe(sid) -> str:
    return _UNSAFE.sub("_", str(sid))[:120]


def _key(p) -> str:
    """Path comparison key (case-insensitive on Windows)."""
    s = str(p).replace("\\", "/")
    return s.lower() if plat.IS_WINDOWS else s


def _ancestors(start: Path, limit: int = 40):
    """``start`` and its parents, stopping before HOME (HOME itself is never a project)."""
    home = _key(Path.home())
    for i, d in enumerate([start, *start.parents]):
        if i >= limit or _key(d) == home:
            return
        yield d


def _project_root(f: Path) -> Path:
    for d in _ancestors(f.parent):
        if any((d / m).exists() for m in ROOT_MARKERS):
            return d
    return f.parent


def _formatter(root: Path, is_py: bool) -> str | None:
    try:
        if is_py:
            if any((root / r).is_file() for r in RUFF):
                return "ruff"
            pp = root / "pyproject.toml"
            if pp.is_file() and "[tool.ruff" in pp.read_text(encoding="utf-8", errors="replace"):
                return "ruff"
            return None
        if any((root / b).is_file() for b in BIOME):
            return "biome"
        pkg = root / "package.json"
        if any((root / p).is_file() for p in PRETTIER):
            return "prettier"
        if pkg.is_file():
            d = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            if isinstance(d, dict) and "prettier" in d:
                return "prettier"
    except (OSError, ValueError):
        pass
    return None


def _tsconfig_dir(f: Path) -> Path | None:
    for d in _ancestors(f.parent, limit=20):
        if (d / "tsconfig.json").is_file():
            return d
    return None


def _bin(root: Path, name: str) -> str | None:
    local = root / "node_modules" / ".bin" / (name + ".cmd" if plat.IS_WINDOWS else name)
    if local.is_file():
        return str(local)
    return shutil.which(name)


def _write_state(path: Path, tk: str, result: str, **extra) -> None:
    rec = {"turn_key": None if tk == "?" else tk, "result": result, "ts": round(time.time(), 3), **extra}
    plat.atomic_write(path, json.dumps(rec, indent=1))


def _edited(transcript) -> list | None:
    from lib import turns
    raw = turns.turn_written_files(transcript)
    if raw is None:
        return None
    try:
        plugins = _key((plat.claude_dir() / "plugins").resolve()) + "/"
    except OSError:
        plugins = None
    out, seen = [], set()
    for p in raw:
        try:
            f = Path(p).resolve()
        except (OSError, ValueError):
            continue
        k = _key(f)
        if (k in seen or f.suffix not in JS_EXT + PY_EXT or "node_modules" in f.parts
                or (plugins and k.startswith(plugins)) or not f.is_file()):
            continue
        seen.add(k)
        out.append(f)
    return out


def _tsbuildinfo(tsdir: Path) -> Path:
    key = None
    try:
        from lib import model_mode
        key = model_mode.repo_key(str(tsdir))
    except Exception:  # noqa: BLE001
        key = None
    key = key or f"{tsdir.name}-{hashlib.sha256(str(tsdir).encode('utf-8')).hexdigest()[:12]}"
    d = plat.state_dir() / "typecheck"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_safe(key)}.tsbuildinfo"


def _check(files: list, t0: float) -> dict:
    """Run every batch; returns {tools, problems, labels, other, missing, stop}."""
    res = {"tools": set(), "problems": [], "labels": [], "other": 0, "missing": False, "stop": None}

    def run(cmd, cwd, cap):
        remaining = DEADLINE_S - (time.monotonic() - t0)
        if remaining < MIN_START_S:
            raise _Budget()
        cp = plat.run(cmd, cwd=cwd, timeout=min(cap, remaining))
        if cp.returncode == 124:
            raise _Timeout()
        return None if cp.returncode == 127 else cp

    def lines_of(cp) -> list:
        return [ln.rstrip() for ln in f"{cp.stdout or ''}\n{cp.stderr or ''}".splitlines() if ln.strip()]

    def flag(tool_label, lines):
        res["labels"].append(tool_label)
        res["problems"].extend(lines)

    fmt_batches: dict = {}
    ts_batches: dict = {}
    for f in files:
        root = _project_root(f)
        fmt = _formatter(root, f.suffix in PY_EXT)
        if fmt:
            fmt_batches.setdefault((root, fmt), []).append(f)
        if f.suffix in TS_EXT:
            tsdir = _tsconfig_dir(f)
            if tsdir is not None:
                ts_batches.setdefault(tsdir, []).append(f)
    try:
        for (root, fmt), batch in fmt_batches.items():
            exe = _bin(root, fmt)
            if not exe:
                res["missing"] = True
                continue
            names = [str(f) for f in batch]
            bases = {f.name for f in batch}
            first = {"biome": ["format"], "prettier": ["--check"], "ruff": ["format", "--check"]}[fmt]
            cp = run([exe, *first, *names], root, TOOL_CAP_S["formatter"])
            if cp is None:
                res["missing"] = True
                continue
            res["tools"].add(fmt)
            label = f"{fmt} {' '.join(first)}"
            if cp.returncode != 0:
                lines = lines_of(cp)
                flag(label, [ln for ln in lines if any(b in ln for b in bases)] or lines[:MAX_LINES])
            elif fmt == "ruff":
                cp = run([exe, "check", "--no-fix", *names], root, TOOL_CAP_S["ruff_check"])
                if cp is not None and cp.returncode != 0:
                    lines = lines_of(cp)
                    flag("ruff check", [ln for ln in lines if any(b in ln for b in bases)] or lines[:MAX_LINES])
        for tsdir, batch in ts_batches.items():
            exe = _bin(tsdir, "tsc")
            if not exe:
                res["missing"] = True
                continue
            cmd = [exe, "--noEmit", "--pretty", "false", "--incremental", "--tsBuildInfoFile",
                   str(_tsbuildinfo(tsdir)), "-p", str(tsdir)]
            cp = run(cmd, tsdir, TOOL_CAP_S["tsc"])
            if cp is None:
                res["missing"] = True
                continue
            res["tools"].add("tsc")
            if cp.returncode == 0:
                continue
            edited = {_key(f) for f in batch}
            hits = []
            for ln in lines_of(cp):
                m = TS_DIAG.match(ln)
                if not m:
                    continue
                p = Path(m.group(1).replace("\\", "/"))
                try:
                    p = (p if p.is_absolute() else tsdir / p).resolve()
                except (OSError, ValueError):
                    pass
                if _key(p) in edited:
                    hits.append(ln)
                else:
                    res["other"] += 1
            if hits:
                flag("tsc --noEmit", hits)
    except _Budget:
        res["stop"] = "budget"
    except _Timeout:
        res["stop"] = "timeout"
    return res


def _reason(labels: list, problems: list, other: int) -> str:
    head = (f"FORMAT/TYPECHECK GATE (once per turn): {', '.join(dict.fromkeys(labels))} reported problems "
            "in files you edited this turn:")
    diag = [ln[:200] for ln in problems[:MAX_LINES]]
    tail = ([f"other errors elsewhere: {other} (pre-existing, not blocking)"] if other else []) + [FIX]
    text = "\n".join([head, *diag, *tail])
    while len(text) > REASON_MAX and len(diag) > 1:
        diag.pop()
        text = "\n".join([head, *diag, *tail])
    return text[:REASON_MAX]


def main() -> int:
    t0 = time.monotonic()
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or payload.get("stop_hook_active") or os.environ.get("CLAUDE_HOOK_DOCTOR"):
        print("{}")
        return 0
    from lib import turns
    sid = _safe(payload.get("session_id") or "unknown")
    state = plat.state_dir() / f"{sid}.typecheck.json"
    transcript = payload.get("transcript_path")
    tk = turns.turn_key(transcript)
    try:
        prev = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    if tk != "?" and isinstance(prev, dict) and prev.get("turn_key") == tk:
        print("{}")
        return 0
    level = "ok"
    try:
        from lib import memwatch_state as mws
        level = mws.read(stale_s=30).level
    except Exception:  # noqa: BLE001 - no tier data reads as ok
        level = "ok"
    if level != "ok":
        _write_state(state, tk, "skip", reason=f"memory {level}")
        print("{}")
        return 0
    files = _edited(transcript)
    if not files:
        print("{}")
        return 0
    names = [str(f) for f in files]
    if len(files) > MAX_FILES:
        _write_state(state, tk, "skip", reason="too many files", files=names[:MAX_FILES])
        print("{}")
        return 0
    res = _check(files, t0)
    tools = sorted(res["tools"])
    if res["problems"]:
        _write_state(state, tk, "block", tools=tools, files=names, other_errors=res["other"])
        print(json.dumps({"decision": "block", "reason": _reason(res["labels"], res["problems"], res["other"])}))
        return 0
    if res["stop"] == "budget":
        _write_state(state, tk, "skip", reason="budget", tools=tools, files=names)
    elif res["stop"] == "timeout":
        _write_state(state, tk, "timeout", reason="tool timed out", tools=tools, files=names)
    elif res["missing"] and not tools:
        _write_state(state, tk, "skip", reason="no binary", files=names)
    else:
        _write_state(state, tk, "pass", tools=tools, files=names, other_errors=res["other"])
    print("{}")
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - fail open
        print("{}")
    sys.exit(0)
