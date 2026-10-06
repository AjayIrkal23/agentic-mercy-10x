"""surface.py — FE / BE / API / docs surface detection for the prompt router.

Answers "what is the user working on?" from four signals, most specific first:

  1. prompt path tokens   ``src/components/Hero.tsx`` -> frontend, ``handlers.go`` -> backend
  2. prompt vocabulary    React/component/tailwind -> frontend; endpoint/migration/Go -> backend
  3. cwd inside the repo  ``client|web|frontend|app|src/components`` -> frontend,
                          ``server|api|internal|cmd|backend`` -> backend (only when the
                          repo stack has that surface, or the stack is unknown)
  4. repo stack           fingerprint of package.json / go.mod / pyproject / components.json /
                          tailwind|vite|next config within 3 levels of the repo root, cached at
                          ``state/<repo.key>.stack.json`` keyed on the marker files' mtimes.

Prompt beats cwd beats stack. The winner is reported as ``source`` so the ranker
can weight a stack-only inference (project happens to be Go+React) lower than an
explicit prompt signal ("write a Go service"). Tags (``go sql clickhouse api three
scroll motion shadcn tailwind``) are additive: prompt tags always attach; stack
tags attach only when their side (backend / frontend) is in the final set, so a
React prompt in a Go+React repo never drags in golang-patterns.

Pure stdlib; never raises past ``detect`` (fail-open to an empty set).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[2]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

try:
    from lib import platform as _plat
    from lib import repo_context as _repo
except Exception:  # noqa: BLE001
    _plat = _repo = None  # type: ignore

# --------------------------------------------------------------------------- #
# 1. prompt paths
# --------------------------------------------------------------------------- #
# {0,255}, not *: an unbounded run made this quadratic on long '.'/'-' runs (Santa A3)
PATH_RE = re.compile(
    r"(?<![\w@])[\w./-]{0,255}\w\.(?:tsx|ts|jsx|js|vue|svelte|css|scss|html|go|sql|py|rs|proto|graphql)\b")
_FE_EXT = {"tsx", "jsx", "vue", "svelte", "css", "scss", "html"}
_BE_EXT = {"go", "sql", "py", "rs", "proto", "graphql"}
_FE_SEGS = ("client", "web", "frontend", "app", "components", "pages", "ui", "hooks", "store")
_BE_SEGS = ("server", "api", "internal", "cmd", "backend", "pkg", "services", "handlers",
            "controllers", "routes", "migrations", "db")
_FE_DIR_SUFFIX = ("-dashboard", "-frontend", "-web", "-client", "-ui", "-app")
_BE_DIR_SUFFIX = ("-server", "-api", "-backend", "-service", "-worker")


def prompt_paths(text: str) -> list[str]:
    """Path-like tokens mentioned in the prompt (lower-cased, deduped, ``/`` separators:
    a Windows ``src\\components\\Button.tsx`` is the same path, A4-10)."""
    seen: list[str] = []
    for m in PATH_RE.finditer((text or "").replace("\\", "/")):
        tok = m.group(0).lower()
        if tok.startswith(("http", "www.")) or tok in seen:
            continue
        # a bare "<name>.js" with no directory is a library name (three.js,
        # next.js, anime.js), not a file the user is pointing at
        if "/" not in tok and tok.endswith(".js"):
            continue
        seen.append(tok)
    return seen


def _path_surface(tok: str) -> str:
    ext = tok.rsplit(".", 1)[-1]
    parts = tok.split("/")[:-1]
    if any(p in _BE_SEGS or p.endswith(_BE_DIR_SUFFIX) for p in parts):
        return "backend"
    if any(p in _FE_SEGS or p.endswith(_FE_DIR_SUFFIX) for p in parts):
        return "frontend"
    if ext in _FE_EXT:
        return "frontend"
    if ext in _BE_EXT:
        return "backend"
    return ""


# --------------------------------------------------------------------------- #
# 2. prompt vocabulary
# --------------------------------------------------------------------------- #
def _rx(*alts: str) -> re.Pattern:
    return re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)", re.IGNORECASE)


# "a small go cli" / "the go program" name Go; "let's go program it" does not (Santa-2 A2)
_GO_NOUN_PHRASE = r"(?:a|an|the|this|my|our|small|simple|tiny|new) go (?:cli|program|tool)s?"


_FE_VOCAB = _rx(
    r"react", r"next\.?js", r"vue", r"svelte", r"angular", r"tailwind(?:css)?", r"shadcn",
    r"components?", r"tsx", r"jsx", r"css", r"scss", r"front-?end", r"ui", r"ux",
    r"landing page", r"hero section", r"tooltip", r"modal", r"navbar", r"sidebar", r"dropdown",
    r"responsive", r"typography", r"three\.?js", r"r3f", r"react-three-fiber", r"@react-three",
    r"webgl", r"glb", r"gltf", r"shader", r"parallax", r"scrollytelling", r"vite", r"storybook",
    r"web page", r"webpage", r"website", r"dark mode", r"animation",
)
_BE_VOCAB = _rx(
    r"endpoints?", r"rest", r"graphql", r"grpc", r"api", r"routes?", r"handlers?", r"controllers?",
    r"middleware", r"migrations?", r"schema", r"postgres(?:ql)?", r"sql", r"clickhouse", r"mongo(?:db)?",
    r"redis", r"kafka", r"queue", r"workers?", r"cron", r"udp", r"tcp", r"websocket", r"golang",
    r"go\.mod", r"go (?:service|module|package|code|server|handler|worker|struct|routine|binary)s?",
    _GO_NOUN_PHRASE,
    r"fastapi", r"express", r"fastify", r"django", r"flask", r"prisma", r"drizzle", r"back-?end",
    r"server", r"database", r"db", r"index on", r"webhook", r"ingest(?:ion)?", r"pipeline",
    r"batch(?:es|ing)?", r"retries", r"idempoten\w+", r"jwt", r"oauth", r"microservices?",
)
_DOCS_VOCAB = _rx(r"readme", r"docs?", r"documentation", r"changelog", r"adrs?", r"server_docs",
                  r"frontend_docs", r"project_linkages", r"\S+\.md")

_TAG_VOCAB = {
    "go": _rx(r"golang", r"\S+\.go", r"go\.mod",
              r"go (?:service|module|package|code|server|handler|worker|struct|routine|binary|test)s?",
              _GO_NOUN_PHRASE),
    "sql": _rx(r"sql", r"postgres(?:ql)?", r"rls", r"row-level security"),
    "clickhouse": _rx(r"clickhouse"),
    "api": _rx(r"endpoints?", r"rest", r"graphql", r"grpc", r"openapi", r"api"),
    "three": _rx(r"three\.?js", r"r3f", r"react-three-fiber", r"@react-three(?:/\w+)?", r"webgl",
                 r"glb", r"gltf", r"shaders?", r"3d (?:model|scene|viewer)s?"),
    "scroll": _rx(r"scroll(?:-| )?(?:animation|driven|telling|linked|scrubb\w*)s?", r"scrollytelling",
                  r"parallax", r"pinned sections?", r"apple-?style"),
    "motion": _rx(r"framer[- ]motion", r"motion\.dev", r"animations?", r"animate", r"transitions?",
                  r"micro-?interactions?"),
    "mobile": _rx(r"expo(?:-[\w-]+)?", r"react[- ]native", r"android", r"ios", r"iphone",
                  r"mobile apps?", r"app\.json"),
}
# bare "mobile" means the RN app only in a repo that has one, and only when the
# prompt names no web/backend surface ("cramped on mobile" is responsive web)
_BARE_MOBILE = _rx(r"mobile")
_MOBILE_DEPS = {"expo", "react-native", "expo-router"}
# "migration" means SQL only where the repo is not Mongo-only (C-06: a Mongoose
# backfill got postgres-patterns at rank 1).
_MIGRATION = _rx(r"migrations?")
_BE_TAGS = {"go", "sql", "clickhouse", "api"}
_FE_TAGS = {"three", "scroll", "motion", "shadcn", "tailwind"}


# "hook"/"hooks" is a React word ONLY with React context (react / component / jsx /
# tsx / a useX identifier). Otherwise — and with Claude-infra vocabulary — it means
# Claude Code hooks: "update my hooks so the MCPs fire" must never pull React skills.
_HOOK_WORD = _rx(r"hooks?")
_REACT_CTX = re.compile(r"(?<!\w)(?:react|components?|jsx|tsx|\S+\.(?:tsx|jsx))(?!\w)", re.IGNORECASE)
_USE_HOOK = re.compile(r"(?<!\w)use[A-Z]\w+")
_INFRA_VOCAB = _rx(r"skills?", r"mcps?", r"mcp servers?", r"rules?", r"dispatch(?:\.py|\.config\.json)?",
                   r"prompt[- ]router", r"subagents?", r"agents?", r"settings\.json", r"claude\.md",
                   r"slash commands?", r"pretooluse", r"posttooluse", r"sessionstart", r"subagentstart",
                   r"userpromptsubmit", r"claude code", r"statusline", r"plugins?")
_INFRA_PATH = re.compile(r"(?:~|\$home|/home/\w+)?/?\.claude/|~/\.claude\b", re.IGNORECASE)


def _react_context(t: str, raw: str) -> bool:
    return bool(_REACT_CTX.search(t) or _USE_HOOK.search(raw or ""))


def prompt_is_claude_infra(t: str, raw: str = "") -> bool:
    """Prompt-level Claude-infra signal: an explicit ``.claude/`` path, or the word
    hook(s) next to infra vocabulary (skills / MCPs / rules / dispatch / …) with no
    React context."""
    if _INFRA_PATH.search(t or ""):
        return True
    return bool(_HOOK_WORD.search(t or "") and _INFRA_VOCAB.search(t or "")
                and not _react_context(t, raw))


def _count(pat: re.Pattern, text: str) -> int:
    return len({m.group(0).lower() for m in pat.finditer(text)})


# --------------------------------------------------------------------------- #
# 3. cwd inside repo
# --------------------------------------------------------------------------- #
_CWD_FE = ("client", "web", "frontend", "app", "src/components", "components", "pages", "ui")
_CWD_BE = ("server", "api", "internal", "cmd", "backend", "pkg", "services")


def cwd_surface(cwd: str, root: str) -> str:
    """'frontend' | 'backend' | '' from cwd's path relative to the repo root."""
    try:
        rel = os.path.relpath(os.path.realpath(cwd), os.path.realpath(root)).replace("\\", "/")
    except (OSError, ValueError):
        return ""
    if rel in (".", "") or rel.startswith(".."):
        return ""
    parts = rel.lower().split("/")
    joined = "/".join(parts)
    for p in parts:
        if p in _CWD_BE or p.endswith(_BE_DIR_SUFFIX):
            return "backend"
    if "src/components" in joined:
        return "frontend"
    for p in parts:
        if p in _CWD_FE or p.endswith(_FE_DIR_SUFFIX):
            return "frontend"
    return ""


# --------------------------------------------------------------------------- #
# 4. repo stack fingerprint (cached on marker mtimes)
# --------------------------------------------------------------------------- #
_MARKERS = {"package.json", "go.mod", "pyproject.toml", "requirements.txt", "components.json"}
_MARKER_PREFIX = ("tailwind.config.", "vite.config.", "next.config.")
_SKIP_DIRS = {"node_modules", ".git", "dist", "build", "vendor", ".cache", "__pycache__", ".next",
              "coverage", ".venv", "venv", "target", "graphify-out", ".claude"}
_SCAN_DEPTH = 3
_SCAN_MAX_DIRS = 400  # ponytail: bounds a first-time scan of a huge monorepo; cache absorbs the rest
_FE_DEPS = {"react", "next", "vite", "vue", "svelte", "@angular/core", "tailwindcss", "three",
            "@react-three/fiber", "motion", "framer-motion", "astro", "solid-js"}
_BE_DEPS = {"express", "fastify", "@nestjs/core", "koa", "hono", "prisma", "@prisma/client",
            "mongoose", "typeorm", "drizzle-orm", "pg", "mysql2", "bullmq", "@clickhouse/client",
            "ioredis", "sequelize"}
_PY_BE = ("fastapi", "django", "flask", "sqlalchemy", "celery", "uvicorn", "starlette")


def _cache_dir() -> Path:
    if _plat is not None:
        return _plat.state_dir()
    d = Path("~/.claude/state").expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _scan(root: Path) -> tuple[list[Path], bool, bool, bool]:
    """(marker files, saw_sql_file, saw_migrations_dir, saw_clickhouse_dir) within depth."""
    markers: list[Path] = []
    sql = migrations = clickhouse = False
    root_depth = str(root).count(os.sep)
    seen_dirs = 0
    for dirpath, dirnames, filenames in os.walk(root):
        seen_dirs += 1
        if seen_dirs > _SCAN_MAX_DIRS:
            break
        depth = dirpath.count(os.sep) - root_depth
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        low = {d.lower() for d in dirnames}
        if low & {"migrations", "migrate"}:
            migrations = True
        if "clickhouse" in low:
            clickhouse = True
        for fn in filenames:
            if fn in _MARKERS or fn.startswith(_MARKER_PREFIX):
                markers.append(Path(dirpath) / fn)
            elif fn.endswith(".sql"):
                sql = True
        if depth >= _SCAN_DEPTH:
            dirnames[:] = []
    return markers, sql, migrations, clickhouse


def _deps(pkg: Path) -> set[str]:
    try:
        d = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return set()
    out: set[str] = set()
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        v = d.get(k)
        if isinstance(v, dict):
            out.update(str(x).lower() for x in v)
    return out


def _compute(root: Path, markers: list[Path], sql: bool, migrations: bool, ch: bool) -> dict:
    surfaces: set[str] = set()
    tags: set[str] = set()
    for m in markers:
        name = m.name
        if name == "package.json":
            deps = _deps(m)
            if deps & _MOBILE_DEPS:  # an RN app's `react` is not a web frontend (C-07)
                tags.add("mobile")
                continue
            if deps & _FE_DEPS:
                surfaces.add("frontend")
            if deps & _BE_DEPS:
                surfaces.add("backend")
            if deps & {"three", "@react-three/fiber"}:
                tags.add("three")
            if deps & {"motion", "framer-motion"}:
                tags.add("motion")
            if "tailwindcss" in deps:
                tags.add("tailwind")
            if "@clickhouse/client" in deps:
                tags.add("clickhouse")
            if deps & {"mongoose", "mongodb"}:
                tags.add("mongo")
        elif name == "go.mod":
            surfaces.add("backend")
            tags.add("go")
        elif name in ("pyproject.toml", "requirements.txt"):
            try:
                body = m.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                body = ""
            if any(p in body for p in _PY_BE):
                surfaces.add("backend")
        elif name == "components.json":
            surfaces.add("frontend")
            tags.add("shadcn")
        elif name.startswith("tailwind.config."):
            surfaces.add("frontend")
            tags.add("tailwind")
        elif name.startswith(("vite.config.", "next.config.")):
            surfaces.add("frontend")
    if sql or migrations:
        surfaces.add("backend")
        tags.add("sql")
    if ch:
        surfaces.add("backend")
        tags.add("clickhouse")
    return {"surfaces": sorted(surfaces), "tags": sorted(tags)}


def stack_fingerprint(repo) -> dict:
    """{'surfaces': [...], 'tags': [...]} for the repo, cached on marker mtimes."""
    if repo is None:
        return {}
    root = Path(getattr(repo, "root", "") or "")
    if not root.is_dir():
        return {}
    try:
        markers, sql, migrations, ch = _scan(root)
        sig = {str(m.relative_to(root)): int(m.stat().st_mtime) for m in markers}
        sig["_flags"] = int(sql) | (int(migrations) << 1) | (int(ch) << 2)
        sig["_v"] = 3  # bump when _compute derives new tags, so old caches recompute
    except OSError:
        return {}
    cache = _cache_dir() / f"{getattr(repo, 'key', 'repo')}.stack.json"
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("sig") == sig:
            return {"surfaces": cached.get("surfaces", []), "tags": cached.get("tags", [])}
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    result = _compute(root, markers, sql, migrations, ch)
    try:
        payload = json.dumps({"sig": sig, **result}, ensure_ascii=False)
        if _plat is not None and hasattr(_plat, "atomic_write"):
            _plat.atomic_write(cache, payload)
        else:
            cache.write_text(payload, encoding="utf-8")
    except OSError:
        pass
    return result


def _claude_dir() -> str:
    try:
        if _plat is not None:
            return os.path.realpath(str(_plat.claude_dir()))
    except Exception:  # noqa: BLE001
        pass
    return os.path.realpath(os.path.expanduser("~/.claude"))


def _is_claude_infra(repo, payload: dict) -> bool:
    """True when the active repo (or cwd) is the Claude Code config dir itself."""
    cd = _claude_dir()
    root = getattr(repo, "root", None) if repo is not None else None
    if root and os.path.realpath(str(root)) == cd:
        return True
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    if isinstance(cwd, str) and cwd:
        rc = os.path.realpath(cwd)
        return rc == cd or rc.startswith(cd + os.sep)
    return False


# --------------------------------------------------------------------------- #
# detect
# --------------------------------------------------------------------------- #
def detect(payload: dict, *, text: str | None = None) -> tuple[set[str], str, set[str]]:
    """Return (surfaces ∪ tags, source, weak).

    ``source`` is 'prompt' | 'cwd' | 'stack' | ''. ``weak`` is the subset of the
    returned set that came from the repo stack alone (not confirmed by the prompt
    or cwd) — the ranker half-weights those so a Go+React repo does not drag
    golang-patterns into a React prompt, nor clickhouse into a postgres one.
    """
    try:
        return _detect_impl(payload, text)
    except Exception:  # noqa: BLE001
        return set(), "", set()


def _detect_impl(payload: dict, text: str | None) -> tuple[set[str], str, set[str]]:
    t = (text if text is not None else str(payload.get("prompt") or "")).lower()

    raw = str(payload.get("prompt") or "") if isinstance(payload, dict) else ""
    fe = _count(_FE_VOCAB, t)
    if _HOOK_WORD.search(t) and _react_context(t, raw):
        fe += 1
    be = _count(_BE_VOCAB, t)
    for tok in prompt_paths(t):
        s = _path_surface(tok)
        if s == "frontend":
            fe += 2
        elif s == "backend":
            be += 2
    docs = _count(_DOCS_VOCAB, t) > 0
    tags = {name for name, pat in _TAG_VOCAB.items() if pat.search(t)}

    code: set[str] = set()
    source = ""
    weak: set[str] = set()
    repo = _repo.active_repo(payload) if _repo is not None else None
    if _is_claude_infra(repo, payload) or prompt_is_claude_infra(t, raw):
        # hooks / rules / skills config: "hook", "route", ".py" here are not FE/BE work
        out = {"claude-infra"}
        if docs:
            out.add("docs")
        return out, "cwd", set()

    if fe or be:
        source = "prompt"
        if fe and not be:
            code = {"frontend"}
        elif be and not fe:
            code = {"backend"}
        elif fe >= 2 * be:
            code = {"frontend"}
        elif be >= 2 * fe:
            code = {"backend"}
        else:
            code = {"frontend", "backend"}

    stack = stack_fingerprint(repo) if repo is not None else {}
    stack_surfaces = set(stack.get("surfaces") or [])
    stack_tags = set(stack.get("tags") or [])
    if _MIGRATION.search(t) and ("sql" in stack_tags or "mongo" not in stack_tags):
        tags.add("sql")
    if not code and "mobile" in stack_tags and _BARE_MOBILE.search(t):
        tags.add("mobile")
    if not code and "mobile" in tags:
        code, source = {"mobile"}, "prompt"

    if not code:
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        cs = cwd_surface(str(cwd), repo.root) if (repo is not None and isinstance(cwd, str) and cwd) else ""
        if cs and (not stack_surfaces or cs in stack_surfaces):
            code, source = {cs}, "cwd"
        elif stack_surfaces:
            code, source = set(stack_surfaces), "stack"
            weak |= code

    if ({"three", "scroll"} & tags) and not code:
        code, source = {"frontend"}, "prompt"
    if "backend" in code:
        weak |= (stack_tags & _BE_TAGS) - tags
        tags |= stack_tags & _BE_TAGS
    if "frontend" in code:
        weak |= (stack_tags & _FE_TAGS) - tags
        tags |= stack_tags & _FE_TAGS

    out = set(code) | tags
    if {"frontend", "backend"} <= out:
        out.add("fullstack")
        if {"frontend", "backend"} <= weak:
            weak.add("fullstack")
    if docs:
        out.add("docs")
    return out, source, weak


__all__ = ["detect", "prompt_paths", "cwd_surface", "stack_fingerprint", "prompt_is_claude_infra"]
