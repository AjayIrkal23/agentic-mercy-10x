#!/usr/bin/env python3
"""ui-quality-autorun.py — PostToolUse advisory: run the UI linters after a UI file edit (2026-11-03).

After a Write/Edit of a UI file inside a project repo this link RUNS the deterministic design checks
itself, with no agent or skill involved, and hands the findings to the model:

- Impeccable ``detect --json <file>`` on every UI file, when the engine is already cached
  (``$IMPECCABLE_BIN``, else ``${IMPECCABLE_HOME:-~/.impeccable}/bin/<VERSION>/impeccable`` with the
  launcher's ``.verified`` stamp). The hook never downloads it; the design act's first run does.
- Hallmark ``sloplint`` (static tier) only on a file that carries the Hallmark stamp in its first
  40 lines: its Floor flags every page without a stamp, so elsewhere it would be noise.

Skipped: non-UI files, files outside a git repo, infra roots (``$HOME``, ``~/.claude``), build and
vendor dirs, missing runtimes. The same findings for the same file are reported once per session
(``<state>/<sid>.ui-autorun.json``; no writes under ``CLAUDE_HOOK_DOCTOR``). Every failure is silent.

stdin : PostToolUse payload {session_id, tool_name, tool_input, cwd}
stdout: {"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"…"}} | {}
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))
SKILLS = HOOKS.parent / "skills"

UI_EXT = (".html", ".htm", ".css", ".scss", ".jsx", ".tsx", ".vue", ".svelte", ".astro")
SKIP_DIRS = {"node_modules", "dist", "build", ".next", "out", "coverage", "vendor", ".git"}
TIMEOUT_S = 6
MAX_CHARS = 1400
MAX_FINDINGS = 8
STAMP_RX = re.compile(r"\bHallmark\b")
SLOP_RX = re.compile(r"^\s*(FAIL|REFLEX)\s+(\S+)\s+:(\d+)\s+(.*)$")


def _impeccable_cmd() -> list[str] | None:
    explicit = os.environ.get("IMPECCABLE_BIN")
    if explicit:
        return [explicit] if Path(explicit).is_file() else None
    try:
        version = (SKILLS / "impeccable" / "scripts" / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    home = Path(os.environ.get("IMPECCABLE_HOME") or Path.home() / ".impeccable")
    exe = ".exe" if os.name == "nt" else ""
    binary = home / "bin" / version / f"impeccable{exe}"
    # the launcher writes <binary>.verified only after the SHA-256 check against engine-checksums.txt
    if binary.is_file() and Path(f"{binary}.verified").is_file():
        return [str(binary)]
    return None


def _sloplint_cmd() -> list[str] | None:
    node = shutil.which("node")
    script = SKILLS / "hallmark" / "scripts" / "sloplint.mjs"
    return [node, str(script)] if node and script.is_file() else None


def _run(cmd: list[str], cwd: Path) -> str:
    try:
        cp = subprocess.run(cmd, cwd=str(cwd), capture_output=True, encoding="utf-8", errors="replace",
                            timeout=TIMEOUT_S, check=False, stdin=subprocess.DEVNULL)
        return cp.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def detect_findings(fp: Path, root: Path) -> list[str]:
    cmd = _impeccable_cmd()
    if not cmd:
        return []
    try:
        rows = json.loads(_run(cmd + ["detect", "--json", str(fp)], root) or "[]")
    except ValueError:
        return []
    out = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict):
            line = f":{r['line']}" if r.get("line") else ""
            out.append(f"impeccable {r.get('severity', 'warning')} {r.get('antipattern') or r.get('name')}{line}: "
                       f"{str(r.get('snippet') or r.get('name') or '')[:120]}")
    return out


def sloplint_findings(fp: Path, root: Path) -> list[str]:
    try:
        head = "\n".join(fp.read_text(encoding="utf-8", errors="replace").splitlines()[:40])
    except OSError:
        return []
    cmd = _sloplint_cmd() if STAMP_RX.search(head) else None
    if not cmd:
        return []
    out = []
    for line in _run(cmd + [str(fp)], root).splitlines():
        m = SLOP_RX.match(line)
        if m:
            out.append(f"hallmark {m.group(1)} {m.group(2)}:{m.group(3)} {m.group(4)[:140]}")
    return out


def _target(payload: dict) -> tuple[Path, Path] | None:
    ti = payload.get("tool_input") or {}
    fp = str(ti.get("file_path") or ti.get("path") or "")
    if not fp.lower().endswith(UI_EXT):
        return None
    p = Path(fp)
    if not p.is_absolute():
        p = Path(payload.get("cwd") or os.getcwd()) / p
    if not p.is_file() or SKIP_DIRS & set(p.parts):
        return None
    try:
        from lib import code_files as cf  # noqa: PLC0415
        from lib import repo_context as rc  # noqa: PLC0415
        root = rc.git_root(p)
        if root is None or cf.is_infra_root(root):
            return None
    except Exception:  # noqa: BLE001
        return None
    return p, Path(root)


def _new_for_session(sid: str, fp: Path, findings: list[str]) -> bool:
    """True when this file's findings differ from the last report this session."""
    digest = hashlib.sha256("\n".join(findings).encode("utf-8")).hexdigest()[:16]
    try:
        from lib import platform as plat  # noqa: PLC0415
        path = plat.state_dir() / f"{sid}.ui-autorun.json"
        try:
            seen = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            seen = {}
        if isinstance(seen, dict) and seen.get(str(fp)) == digest:
            return False
        if not os.environ.get("CLAUDE_HOOK_DOCTOR"):
            def put(state: dict) -> dict:
                state[str(fp)] = digest
                return state
            plat.locked_update(path, put, default={})
    except Exception:  # noqa: BLE001
        pass
    return True


def advise(payload: dict) -> str:
    hit = _target(payload)
    if hit is None:
        return ""
    fp, root = hit
    findings = detect_findings(fp, root) + sloplint_findings(fp, root)
    if not findings:
        return ""
    sid = str(payload.get("session_id") or "nosession")
    if not _new_for_session(sid, fp, findings):
        return ""
    try:
        rel = fp.relative_to(root).as_posix()
    except ValueError:
        rel = str(fp)
    shown = findings[:MAX_FINDINGS]
    more = f" (+{len(findings) - len(shown)} more)" if len(findings) > len(shown) else ""
    text = (f"UI auto-check ran on {rel}: {len(findings)} finding(s){more}. Fix the true positives now "
            "(a FAIL breaks the design floor); name any false positive.\n- " + "\n- ".join(shown))
    return text[:MAX_CHARS]


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        text = advise(payload) if isinstance(payload, dict) else ""
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}})
              if text else "{}")
    except Exception:  # noqa: BLE001
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
