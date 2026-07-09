#!/usr/bin/env python3
"""SessionStart sub-script: auto-seed Memory MCP for any project.

Mirrors the jcodemunch-index-guard / graphify-index-guard pattern: detects
the active workspace, checks whether Memory MCP already has project entities
for it, and if not, extracts a small set of durable facts (name, primary
surfaces, key docs, conventions) and appends them to ~/mcp-data/memory.jsonl.

Runs once per workspace — subsequent sessions short-circuit on the existing
`repo::<slug>` entity (~50 ms). First session per project pays a 1–3 s
extraction cost.

Idempotent. Fail-open on any error (exit 0, no stdout). Skips repos that
look like dotfiles or temp dirs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HOME = Path.home()
MEMORY_FILE = HOME / "mcp-data" / "memory.jsonl"
STATE_DIR = HOME / ".claude" / "hooks" / ".state"
RESEED_AFTER_DAYS = 60  # Re-extract if older than this
MAX_DESCRIPTION_CHARS = 240
MAX_OBSERVATIONS_PER_ENTITY = 8


# --------------------------------------------------------------------------
# Workspace detection (matches jcodemunch + graphify pattern)
# --------------------------------------------------------------------------
def _find_workspace_root(payload: dict) -> Path | None:
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots:
        p = Path(str(roots[0]))
        if p.is_dir():
            return p

    cwd_str = payload.get("cwd") or os.getcwd()
    cwd = Path(cwd_str)
    if (cwd / ".git").exists():
        return cwd

    cur = cwd
    for _ in range(20):
        parent = cur.parent
        if parent == cur:
            break
        if (parent / ".git").exists():
            return parent
        cur = parent

    return cwd if cwd.is_dir() else None


def _looks_like_project(root: Path) -> bool:
    """Avoid bootstrapping dotfile dirs, /tmp, $HOME itself."""
    if root == HOME:
        return False
    if str(root).startswith("/tmp/") or str(root).startswith("/var/tmp/"):
        return False
    if root.name.startswith("."):
        return False
    # Require at least one project marker
    markers = [".git", "package.json", "go.mod", "Cargo.toml", "pyproject.toml",
               "README.md", "AGENTS.md", "CLAUDE.md"]
    return any((root / m).exists() for m in markers)


def _project_slug(root: Path) -> str:
    """`<dirname>#<sha1[:10]>` — matches the site-sync-vista convention."""
    h = hashlib.sha1(str(root).lower().encode()).hexdigest()[:10]
    return f"{root.name}#{h}"


# --------------------------------------------------------------------------
# Idempotency check
# --------------------------------------------------------------------------
def _entity_already_exists(slug: str) -> bool:
    """Quick grep — does `repo::<slug>` exist in memory.jsonl?"""
    if not MEMORY_FILE.exists():
        return False
    target = f'"name":"repo::{slug}"'
    try:
        with MEMORY_FILE.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if target in line:
                    return True
    except Exception:
        pass
    return False


def _bootstrap_state_path(slug: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.#-]", "_", slug)
    return STATE_DIR / f"{safe}.memory-bootstrap.json"


def _bootstrap_recently_done(slug: str) -> bool:
    state = _bootstrap_state_path(slug)
    if not state.exists():
        return False
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
        ts = float(data.get("ts", 0))
        import time
        age_days = (time.time() - ts) / 86400.0
        return age_days < RESEED_AFTER_DAYS
    except Exception:
        return False


def _mark_bootstrap_done(slug: str, count: int) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state = _bootstrap_state_path(slug)
    import time
    try:
        state.write_text(json.dumps({
            "slug": slug,
            "ts": time.time(),
            "entities_written": count,
        }), encoding="utf-8")
    except Exception:
        pass


# --------------------------------------------------------------------------
# Secret redaction
# --------------------------------------------------------------------------
_SECRET_PATTERNS = [
    re.compile(r'(?i)(?:aws_secret_access_key|aws_access_key_id|github_token|github_pat|api[_-]?key|password|secret|token|private[_-]?key|bearer)\s*[=:]\s*[\'"]?[A-Za-z0-9_\-/+=]{12,}[\'"]?'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),  # AWS access key
    re.compile(r'\bghp_[A-Za-z0-9]{20,}\b'),  # GitHub PAT
    re.compile(r'\bsk-(?:proj|[A-Za-z0-9]{2})-[A-Za-z0-9_\-]{20,}\b'),  # OpenAI
    re.compile(r'\bsk-ant-[A-Za-z0-9_\-]{20,}\b'),  # Anthropic
    re.compile(r'\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b'),  # JWT
]


def _redact_secrets(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


# --------------------------------------------------------------------------
# Fact extraction
# --------------------------------------------------------------------------
def _read_truncated(path: Path, max_chars: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def _extract_readme_description(root: Path) -> str:
    """Pull first non-header paragraph from README.md / readme.md."""
    for name in ["README.md", "Readme.md", "readme.md"]:
        readme = root / name
        if not readme.exists():
            continue
        text = _read_truncated(readme, 3000)
        # Strip headers / badges / images; pick first prose paragraph
        for para in re.split(r"\n\s*\n", text):
            stripped = para.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("!["):
                continue
            if stripped.startswith("```") or stripped.startswith("|"):
                continue
            # Skip Lovable template URL lines and bare URL paragraphs (C-12)
            if re.match(r'^\*\*URL\*\*:', stripped) or re.match(r'^https?://', stripped):
                continue
            result = stripped.replace("\n", " ").strip()[:MAX_DESCRIPTION_CHARS]
            return _redact_secrets(result)
    return ""


def _detect_languages_and_stack(root: Path) -> tuple[list[str], list[str]]:
    langs: list[str] = []
    stack: list[str] = []

    # package.json — JS/TS frameworks
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(_read_truncated(pkg, 10000))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            # Detect TS vs JS
            if "typescript" in deps or any((root / p).exists() for p in ["tsconfig.json", "tsconfig.base.json"]):
                langs.append("TypeScript")
            else:
                langs.append("JavaScript")
            stack_hints = {
                "react": "React", "next": "Next.js", "vue": "Vue", "svelte": "Svelte",
                "vite": "Vite", "@tanstack/react-query": "TanStack Query",
                "express": "Express", "fastify": "Fastify", "hono": "Hono",
                "@nestjs/core": "NestJS", "tailwindcss": "Tailwind",
                "@reduxjs/toolkit": "Redux Toolkit", "zustand": "Zustand",
                "prisma": "Prisma", "drizzle-orm": "Drizzle", "mongoose": "Mongoose",
                "@trpc/server": "tRPC", "playwright": "Playwright",
            }
            for dep, name in stack_hints.items():
                if dep in deps:
                    stack.append(name)
        except Exception:
            pass

    if (root / "go.mod").exists():
        langs.append("Go")
        try:
            text = _read_truncated(root / "go.mod", 4000)
            for hint, name in [("gin-gonic/gin", "Gin"), ("labstack/echo", "Echo"),
                               ("gofiber/fiber", "Fiber"), ("grpc", "gRPC")]:
                if hint in text:
                    stack.append(name)
        except Exception:
            pass

    if (root / "Cargo.toml").exists():
        langs.append("Rust")
        try:
            text = _read_truncated(root / "Cargo.toml", 4000)
            for hint, name in [("axum", "Axum"), ("actix-web", "Actix"),
                               ("tokio", "Tokio"), ("serde", "serde")]:
                if hint in text:
                    stack.append(name)
        except Exception:
            pass

    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists() or (root / "setup.py").exists():
        langs.append("Python")

    if any((root / m).exists() for m in ["pom.xml", "build.gradle", "build.gradle.kts"]):
        langs.append("Java/Kotlin")

    return langs, stack


def _detect_surfaces(root: Path) -> list[str]:
    """Common monorepo structure markers."""
    surfaces: list[str] = []
    candidates = [
        ("web", ["web", "apps/web", "frontend", "client"]),
        ("server", ["server", "apps/server", "backend", "api"]),
        ("mobile", ["mobile", "apps/mobile", "ios", "android"]),
        ("packages", ["packages"]),
        ("docs", ["docs"]),
    ]
    for label, paths in candidates:
        for p in paths:
            if (root / p).is_dir():
                surfaces.append(label)
                break
    if not surfaces and (root / "src").is_dir():
        surfaces.append("src")
    return surfaces


def _detect_entry_docs(root: Path) -> list[str]:
    """README, AGENTS, CLAUDE, CODEX, frontend_docs/server_docs entries."""
    docs: list[str] = []
    for name in ["README.md", "AGENTS.md", "CLAUDE.md", "CODEX.md",
                 "CONTRIBUTING.md", "ARCHITECTURE.md"]:
        if (root / name).exists():
            docs.append(name)
    for subdir in ["frontend_docs", "server_docs", "docs"]:
        readme = root / subdir / "README.md"
        if readme.exists():
            docs.append(f"{subdir}/README.md")
    return docs[:MAX_OBSERVATIONS_PER_ENTITY]


def _extract_conventions(root: Path) -> list[str]:
    """Pull short bullet-like lines from AGENTS.md / CLAUDE.md / CODEX.md."""
    conventions: list[str] = []
    sources = ["AGENTS.md", "CLAUDE.md", "CODEX.md"]
    for src in sources:
        path = root / src
        if not path.exists():
            continue
        text = _read_truncated(path, 8000)
        # Capture short imperative bullets that look like rules
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r'^[-*]\s+|^\d+\.\s+', stripped):
                # Strip leading bullet + truncate
                content = re.sub(r"^[-*]\s+|^\d+\.\s+", "", stripped)
                content = _redact_secrets(content)
                if 30 <= len(content) <= 240:
                    conventions.append(content)
            if len(conventions) >= MAX_OBSERVATIONS_PER_ENTITY:
                break
        if conventions:
            break  # Use first source that yielded conventions
    return conventions[:MAX_OBSERVATIONS_PER_ENTITY]


# --------------------------------------------------------------------------
# Entity writer
# --------------------------------------------------------------------------
def _append_entity(name: str, entity_type: str, observations: list[str]) -> bool:
    """Append a single entity JSON line to memory.jsonl (idempotent on name)."""
    if not observations:
        return False
    if not MEMORY_FILE.parent.exists():
        return False  # MCP not configured

    target = f'"name":"{name}"'
    if MEMORY_FILE.exists():
        try:
            with MEMORY_FILE.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if target in line:
                        return False  # Already there
        except Exception:
            return False

    entry: dict[str, Any] = {
        "type": "entity",
        "name": name,
        "entityType": entity_type,
        "observations": observations[:MAX_OBSERVATIONS_PER_ENTITY],
    }
    try:
        with MEMORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, separators=(',', ':')) + "\n")
        return True
    except Exception:
        return False


def _bootstrap(root: Path, slug: str) -> int:
    """Extract facts and write entities. Returns count written."""
    repo_name = f"repo::{slug}"
    description = _extract_readme_description(root)
    langs, stack = _detect_languages_and_stack(root)
    surfaces = _detect_surfaces(root)
    entry_docs = _detect_entry_docs(root)
    conventions = _extract_conventions(root)

    count = 0

    # Entity 1: repository
    repo_obs: list[str] = [f"Canonical root: {root}.", f"Repo name: {root.name}."]
    if description:
        repo_obs.append(f"Description: {description}")
    if langs:
        repo_obs.append(f"Primary languages: {', '.join(langs)}.")
    if surfaces:
        repo_obs.append(f"Primary surfaces: {', '.join(surfaces)}.")
    if entry_docs:
        repo_obs.append(f"Key docs: {', '.join(entry_docs)}.")
    if _append_entity(repo_name, "repository", repo_obs):
        count += 1

    # Entity 2: docs
    if entry_docs:
        doc_obs = [f"Entry docs: {', '.join(entry_docs)}."]
        if "AGENTS.md" in entry_docs:
            doc_obs.append("AGENTS.md present — read first for agent-targeted guidance.")
        if "CODEX.md" in entry_docs:
            doc_obs.append("CODEX.md present — project-specific decisions and patterns live here.")
        if "CLAUDE.md" in entry_docs:
            doc_obs.append("CLAUDE.md present — Claude Code-specific operating instructions.")
        doc_obs.append("Prefer code and docs over stale memory when they disagree.")
        if _append_entity(f"{repo_name}::docs", "documentation", doc_obs):
            count += 1

    # Entity 3: stack (only if we detected one)
    if stack or langs:
        stack_obs: list[str] = []
        if langs:
            stack_obs.append(f"Languages in use: {', '.join(langs)}.")
        if stack:
            stack_obs.append(f"Frameworks/libs detected: {', '.join(stack[:8])}.")
        if surfaces:
            stack_obs.append(f"Surface layout: {', '.join(surfaces)}.")
        if _append_entity(f"{repo_name}::stack", "stack", stack_obs):
            count += 1

    # Entity 4: conventions (only if AGENTS/CLAUDE/CODEX yielded useful bullets)
    if conventions:
        conv_obs = ["Store only durable repo knowledge, never secrets or .env values."]
        conv_obs.extend(conventions)
        if _append_entity(f"{repo_name}::conventions", "convention", conv_obs):
            count += 1

    return count


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> None:
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw)
    except Exception:
        payload = {}

    try:
        root = _find_workspace_root(payload)
        if root is None or not _looks_like_project(root):
            return  # Silent skip

        slug = _project_slug(root)

        # Idempotency: short-circuit if already done
        if _entity_already_exists(slug):
            if not _bootstrap_state_path(slug).exists():
                _mark_bootstrap_done(slug, 0)  # backfill state for legacy entries
            return
        if _bootstrap_recently_done(slug):
            return

        # Bootstrap path: extract + write
        count = _bootstrap(root, slug)
        if count > 0:
            _mark_bootstrap_done(slug, count)
            # Lightweight SessionStart additionalContext so the user knows seeding happened
            out = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": (
                        f"## Project Memory Bootstrap\n"
                        f"Seeded Memory MCP with {count} project entit"
                        f"{'y' if count == 1 else 'ies'} for `{root.name}` "
                        f"(slug `{slug}`).\n"
                        f"Subsequent sessions will load these via "
                        f"`memory-load-on-start.py`.\n"
                    ),
                }
            }
            print(json.dumps(out))
    except Exception:
        pass  # Fail open — never block SessionStart


if __name__ == "__main__":
    main()
