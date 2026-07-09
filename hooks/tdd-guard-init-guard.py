#!/usr/bin/env python3
"""tdd-guard-init-guard.py — auto-initialize & maintain tdd-guard per project.

Mirrors the jcodemunch / graphify index guards: the user never hand-creates a
tdd-guard config. Detects the project's stack(s), writes a scoped config.json,
and keeps its ignorePatterns in sync as the repo's files/folders change.

Modes (argv[1]):
  session  Full pass (SessionStart, via session-start-aggregator). Detects stacks,
           (re)generates config when the structure FINGERPRINT changed, else skips.
           -> "keep updating based on new files/folders, or ignore if no changes".
  prompt   Cheap pass (UserPromptSubmit, via token-stack-prompt-reminder). If a
           config already exists -> do nothing. If missing and the repo is a real
           code project -> initialize it.
           -> "auto-run on my prompt; if tdd exists ignore, else init properly".

Ownership model (so manual configs are never clobbered):
  A config is AUTO-MANAGED iff the sidecar  <data>/.autoinit.json  exists with
  "autoManaged": true. The guard only rewrites configs it owns. A user-created
  config.json with no sidecar is left untouched. Delete the sidecar to take
  manual control.

Enforcement scope it generates:
  guardEnabled = a real test runner exists (go.mod => go test; vitest/jest in a
  package.json; pytest). ignorePatterns exempt non-code, generated, vendor, mocks,
  migrations, cmd entrypoints, test files themselves, and any sub-package that has
  NO unit-test runner (e.g. a Vitest-less frontend).

NOT a PreToolUse gate — fails OPEN, never blocks. Emits {"additionalContext": ...}.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

DATA_REL = Path(".claude") / "tdd-guard" / "data"
CONFIG_NAME = "config.json"
SIDECAR_NAME = ".autoinit.json"
SCHEMA_VERSION = 1

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", ".next", "out",
    "coverage", "testdata", ".venv", "venv", "__pycache__", ".claude",
    "target", "bin", "obj", ".turbo", ".cache", "graphify-out",
}

UNIT_TEST_RUNNERS = ("vitest", "jest")  # JS/TS runners that imply unit-level TDD

# Always-ignore baseline (non-code + generated + noise + test files themselves).
BASE_IGNORE = [
    "**/*.md", "**/*.txt", "**/*.json", "**/*.yml", "**/*.yaml", "**/*.toml",
    "**/*.xml", "**/*.html", "**/*.css", "**/*.scss", "**/*.sql", "**/*.csv",
    "**/*.sum", "**/*.mod", "**/*.lock", "**/*.env", "**/*.sh",
    "**/node_modules/**", "**/vendor/**", "**/dist/**", "**/build/**",
    "**/.next/**", "**/coverage/**", "**/testdata/**", "**/.git/**",
    "**/*_test.go", "**/*.gen.go", "**/*_gen.go", "**/*.pb.go",
    "**/*.test.ts", "**/*.test.tsx", "**/*.test.js", "**/*.test.jsx",
    "**/*.spec.ts", "**/*.spec.tsx", "**/*.spec.js", "**/*.spec.jsx",
    "**/mocks/**", "**/__mocks__/**", "**/*_mock.go", "**/*.mock.ts",
    "**/migrations/**", "**/migrate/**", "**/cmd/**",
]


# --------------------------------------------------------------------------- #
# IO helpers
# --------------------------------------------------------------------------- #
def _read_payload() -> dict:
    try:
        raw = sys.stdin.read() or "{}"
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def _emit(text: str) -> None:
    print(json.dumps({"additionalContext": text}) if text else "{}")


def _git_root(start: Path) -> Path | None:
    cur = start if start.is_dir() else start.parent
    for _ in range(25):
        if (cur / ".git").exists():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def _find_root(payload: dict) -> Path | None:
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots:
        p = Path(str(roots[0]))
        if p.is_dir():
            return _git_root(p) or p
    for key in ("cwd", "project_dir"):
        v = payload.get(key)
        if v and Path(str(v)).is_dir():
            return _git_root(Path(str(v)))
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and Path(env).is_dir():
        return _git_root(Path(env))
    return _git_root(Path(os.getcwd()))


# --------------------------------------------------------------------------- #
# Project scan
# --------------------------------------------------------------------------- #
def _scan(root: Path, max_depth: int = 3) -> dict:
    """Bounded walk: find go modules, js packages (+runner), python test dirs."""
    go_mods: list[str] = []
    js_pkgs: list[tuple[str, bool]] = []
    py_dirs: list[tuple[str, bool]] = []
    top_dirs: list[str] = []

    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).resolve().relative_to(root)
        depth = len(rel.parts)
        if depth == 0:
            top_dirs = sorted(
                d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
            )
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if depth >= max_depth:
            dirnames[:] = []
        reldir = "" if str(rel) == "." else rel.as_posix()

        if "go.mod" in filenames:
            go_mods.append(reldir)
        if "package.json" in filenames:
            runner = False
            try:
                data = json.loads((Path(dirpath) / "package.json").read_text(encoding="utf-8"))
                deps = {}
                deps.update(data.get("dependencies", {}) or {})
                deps.update(data.get("devDependencies", {}) or {})
                runner = any(r in deps for r in UNIT_TEST_RUNNERS)
            except Exception:
                runner = False
            js_pkgs.append((reldir, runner))
        if "pyproject.toml" in filenames or "setup.cfg" in filenames:
            has_pytest = False
            for fn in ("pyproject.toml", "setup.cfg"):
                fp = Path(dirpath) / fn
                if fp.is_file():
                    try:
                        if "pytest" in fp.read_text(encoding="utf-8").lower():
                            has_pytest = True
                            break
                    except Exception:
                        pass
            py_dirs.append((reldir, has_pytest))

    return {
        "go_mods": sorted(go_mods),
        "js_pkgs": sorted(js_pkgs),
        "py_dirs": sorted(py_dirs),
        "top_dirs": top_dirs,
        "has_stack": bool(go_mods or js_pkgs or py_dirs),
    }


def _fingerprint(scan: dict) -> str:
    parts = []
    parts += [f"go:{m}" for m in scan["go_mods"]]
    parts += [f"js:{d}:{int(r)}" for d, r in scan["js_pkgs"]]
    parts += [f"py:{d}:{int(r)}" for d, r in scan["py_dirs"]]
    parts += [f"dir:{d}" for d in scan["top_dirs"]]
    return hashlib.sha1("|".join(sorted(parts)).encode("utf-8")).hexdigest()[:16]


def _generate(scan: dict) -> tuple[dict, list[str], bool]:
    ignore = list(BASE_IGNORE)
    runners: list[str] = []
    if scan["go_mods"]:
        runners.append("go")
    if any(r for _, r in scan["js_pkgs"]):
        runners.append("js")
    if any(r for _, r in scan["py_dirs"]):
        runners.append("py")
    # Exempt sub-packages with NO unit-test runner (e.g. a Vitest-less SPA).
    for reldir, runner in scan["js_pkgs"]:
        if reldir and not runner:
            ignore.append(f"{reldir}/**")
    for reldir, has_pytest in scan["py_dirs"]:
        if reldir and not has_pytest:
            ignore.append(f"{reldir}/**")
    enabled = bool(runners)
    config = {"guardEnabled": enabled, "ignorePatterns": sorted(dict.fromkeys(ignore))}
    return config, runners, enabled


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def _paths(root: Path) -> tuple[Path, Path, Path]:
    data = root / DATA_REL
    return data, data / CONFIG_NAME, data / SIDECAR_NAME


def _load_sidecar(sidecar: Path) -> dict | None:
    try:
        if sidecar.is_file():
            return json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _write(data: Path, config_path: Path, sidecar_path: Path,
           config: dict, runners: list[str], fp: str) -> None:
    data.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    sidecar_path.write_text(json.dumps({
        "autoManaged": True,
        "version": SCHEMA_VERSION,
        "fingerprint": fp,
        "runners": runners,
    }, indent=2) + "\n", encoding="utf-8")


def _status(verb: str, root: Path, runners: list[str], enabled: bool) -> str:
    if not enabled:
        return (f"tdd-guard: {verb} for `{root.name}` — DORMANT "
                f"(no unit-test runner detected; auto-enforces once one exists).")
    scope = "+".join(runners) if runners else "none"
    return (f"tdd-guard: {verb} for `{root.name}` — ACTIVE [{scope}] (warn mode). "
            f"Write-time TDD on test-bearing code; non-test surfaces + external files exempt.")


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
def run_session() -> int:
    payload = _read_payload()
    root = _find_root(payload)
    if root is None or not (root / ".git").exists():
        return _emit("") or 0

    data, config_path, sidecar_path = _paths(root)
    scan = _scan(root)
    if not scan["has_stack"]:
        return _emit("") or 0

    fp = _fingerprint(scan)
    config, runners, enabled = _generate(scan)
    sidecar = _load_sidecar(sidecar_path)

    if not config_path.exists():
        _write(data, config_path, sidecar_path, config, runners, fp)
        return _emit(_status("initialized", root, runners, enabled)) or 0

    if sidecar is None or not sidecar.get("autoManaged"):
        return _emit("") or 0  # manual config — never touch

    if sidecar.get("fingerprint") == fp:
        return _emit("") or 0  # auto-managed + unchanged — silent

    _write(data, config_path, sidecar_path, config, runners, fp)
    return _emit(_status("updated (structure changed)", root, runners, enabled)) or 0


def run_prompt() -> int:
    payload = _read_payload()
    root = _find_root(payload)
    if root is None or not (root / ".git").exists():
        return _emit("") or 0

    data, config_path, sidecar_path = _paths(root)
    if config_path.exists():
        return _emit("") or 0  # already initialized — ignore (cheap path)

    scan = _scan(root)
    if not scan["has_stack"]:
        return _emit("") or 0  # not a code project — don't init / don't pollute

    fp = _fingerprint(scan)
    config, runners, enabled = _generate(scan)
    _write(data, config_path, sidecar_path, config, runners, fp)
    return _emit(_status("initialized", root, runners, enabled)) or 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "session"
    try:
        return run_prompt() if mode == "prompt" else run_session()
    except Exception:
        return _emit("") or 0


if __name__ == "__main__":
    raise SystemExit(main())
