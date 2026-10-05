"""Prompt-time symbol retrieval from the jcodemunch index.

The router already tells the agent *to use* jcodemunch (SUBSTRATE precedence).
This module makes the router *deliver* it: on a code-shaped prompt it queries the
local jcodemunch sqlite index directly and injects the symbols that actually
match, with their AI summaries, file paths, and line numbers.

Why sqlite and not MCP: this runs inside a UserPromptSubmit hook, which cannot
call MCP tools. The index is a plain sqlite file, so a keyword query over
`symbols` costs single-digit milliseconds on a 10k-symbol repo.

Degradation is deliberate. Symbols whose summary is a name echo ("Constant FOO",
"Function bar") carry no information, so they are never quoted as evidence —
they can still match by NAME, they just don't contribute a summary line. As
`jcodemunch-mcp index` populates real AI summaries, the same query gets sharper
without any change here.

Fails open on every error: a broken index must never block a prompt.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import time

INDEX_DIR = os.path.expanduser("~/.code-index")
MAX_SYMBOLS = 5
MAX_KEYWORDS = 5
_MIN_KEYWORD_LEN = 3
BUDGET_MS = 150  # hard wall-clock budget for one prompt's symbol lookup

# intent -> tool-intelligence.json playbook (path is hooks/-relative, not $HOME).
_TOOLMAP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "tool-intelligence.json")
_PLAYBOOK_STEPS = 5  # top N steps quoted per prompt (token-lean)
# Router intent category -> tool-intelligence.json intent key.
_INTENT_MAP = {
    "PLAN": "understand", "SPEC": "understand",
    "AUDIT": "audit",
    "IMPLEMENT": "implement", "TEST": "implement",
    "DEBUG": "debug",
    "REVIEW": "review",
    "CLEANUP": "refactor", "REFACTOR": "refactor",
}
_TOOLMAP_CACHE: dict | None = None

# Name-echo summaries the indexer synthesises when a symbol has no docstring.
_PLACEHOLDER = re.compile(
    r"^\s*(constant|function|class|variable|method|interface|type|enum|struct)\s+\S+\s*$",
    re.I,
)

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "into", "when", "what",
    "why", "how", "can", "you", "your", "please", "make", "use", "using", "need",
    "want", "add", "get", "set", "run", "all", "any", "not", "but", "are", "was",
    "has", "have", "will", "should", "would", "could", "there", "then", "than",
    "code", "file", "files", "function", "functions", "check", "fix", "now",
    "also", "just", "some", "more", "very", "into", "about", "where", "which",
}


def _keywords(text: str) -> list[str]:
    """Meaningful tokens from a prompt, longest first (most specific wins)."""
    raw = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text or "")
    seen, out = set(), []
    for w in raw:
        lw = w.lower()
        if lw in _STOP or len(lw) < _MIN_KEYWORD_LEN or lw in seen:
            continue
        seen.add(lw)
        out.append(lw)
    out.sort(key=len, reverse=True)
    return out[:MAX_KEYWORDS]


def _db_for_repo(repo_root: str) -> str | None:
    """Locate the index whose source_root contains repo_root (longest match)."""
    if not repo_root:
        return None
    try:
        root = os.path.realpath(repo_root)
    except OSError:
        return None
    best, best_len = None, -1
    for db in glob.glob(os.path.join(INDEX_DIR, "*.db")):
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                row = con.execute(
                    "select value from meta where key='source_root'"
                ).fetchone()
            finally:
                con.close()
        except sqlite3.Error:
            continue
        if not row or not row[0]:
            continue
        src = os.path.realpath(row[0])
        if (root == src or root.startswith(src + os.sep)) and len(src) > best_len:
            best, best_len = db, len(src)
    return best


def _is_placeholder(summary: str | None) -> bool:
    return not summary or not summary.strip() or bool(_PLACEHOLDER.match(summary))


def is_repo_symbol(repo_root: str, name: str) -> bool:
    """True when ``name`` is an exact (case-insensitive) symbol name in the repo's
    index — used to keep library-docs routes (context7) quiet for in-repo names."""
    if not name:
        return False
    db = _db_for_repo(repo_root)
    if not db:
        return False
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = con.execute("select 1 from symbols where lower(name)=? limit 1",
                              (name.lower(),)).fetchone()
        finally:
            con.close()
        return row is not None
    except sqlite3.Error:
        return False


def search(repo_root: str, prompt: str, limit: int = MAX_SYMBOLS,
           budget_ms: int = BUDGET_MS) -> list[dict]:
    """Rank indexed symbols against the prompt's keywords, within ``budget_ms``."""
    kws = _keywords(prompt)
    if not kws:
        return []
    db = _db_for_repo(repo_root)
    if not db:
        return []

    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return []

    deadline = time.monotonic() + max(0, budget_ms) / 1000.0
    scored: dict[str, dict] = {}
    try:
        con.execute("pragma query_only = ON")
        for kw in kws:
            if time.monotonic() > deadline:
                break
            like = f"%{kw}%"
            try:
                rows = con.execute(
                    "select name, kind, file, line, signature, summary "
                    "from symbols "
                    "where lower(name) like ? or lower(summary) like ? "
                    "   or lower(docstring) like ? "
                    "limit 200",
                    (like, like, like),
                ).fetchall()
            except sqlite3.Error:
                continue
            for name, kind, file, line, sig, summary in rows:
                lname = (name or "").lower()
                # Name hits are strong signal; summary hits only count when the
                # summary is real (an AI/docstring one, not a name echo).
                pts = 0
                if lname == kw:
                    pts = 100
                elif lname.startswith(kw) or kw in lname:
                    pts = 50
                if not _is_placeholder(summary) and kw in (summary or "").lower():
                    pts += 30
                if pts == 0:
                    continue
                key = f"{file}::{name}::{line}"
                cur = scored.get(key)
                if cur is None:
                    scored[key] = {
                        "name": name, "kind": kind, "file": file, "line": line,
                        "signature": sig, "summary": summary, "score": pts, "hits": 1,
                    }
                else:
                    cur["score"] += pts
                    cur["hits"] += 1
    finally:
        con.close()

    # Multi-keyword agreement is the best relevance signal available here.
    ranked = sorted(
        scored.values(), key=lambda r: (r["hits"], r["score"]), reverse=True
    )
    return ranked[:limit]


def build_item(profile, ctx: dict) -> dict | None:
    """Router item carrying concrete symbols for this prompt, or None."""
    try:
        repo = ctx.get("repo")
        if not repo:
            return None
        repo_root = getattr(repo, "root", None) or (
            repo.get("root") if isinstance(repo, dict) else None
        ) or (repo if isinstance(repo, str) else None)
        if not repo_root:
            return None

        text = getattr(profile, "text", "") or ""
        ci_cfg = (ctx.get("config") or {}).get("code_intel") or {}
        hits = search(str(repo_root), text,
                      limit=int(ci_cfg.get("max_symbols", MAX_SYMBOLS)),
                      budget_ms=int(ci_cfg.get("budget_ms", BUDGET_MS)))
        if not hits:
            return None

        lines = []
        for h in hits:
            loc = f"{h['file']}:{h['line']}"
            summ = "" if _is_placeholder(h["summary"]) else " ".join(h["summary"].split())
            if len(summ) > 72:  # the model reads the source next; this only disambiguates (C-11)
                summ = summ[:69].rstrip() + "..."
            desc = f" — {summ}" if summ else ""
            lines.append(f"  {h['name']} ({h['kind']}) {loc}{desc}")

        real = sum(1 for h in hits if not _is_placeholder(h["summary"]))
        tail = (
            "Verify with get_symbol_source / get_blast_radius before editing."
            if real
            else "Summaries are unpopulated in this index — run "
                 "`jcodemunch-mcp index <repo>` to enable semantic matching."
        )
        salt = "-".join(sorted(str(h["name"]).lower() for h in hits))[:60]
        return {
            "id": f"intel:symbols:{salt}",
            "tier": 1,
            "section": "INTEL",
            "text": "Indexed symbols matching this prompt (jcodemunch):\n"
                    + "\n".join(lines) + "\n" + tail,
        }
    except Exception:
        return None  # never block a prompt


def _load_toolmap() -> dict | None:
    """Load + memoise tool-intelligence.json (the intent->tool source of truth)."""
    global _TOOLMAP_CACHE
    if _TOOLMAP_CACHE is None:
        try:
            with open(_TOOLMAP_PATH, encoding="utf-8") as f:
                _TOOLMAP_CACHE = json.load(f)
        except Exception:
            _TOOLMAP_CACHE = {}
    return _TOOLMAP_CACHE or None


def build_playbook_item(profile, ctx: dict) -> dict | None:
    """Emit the ordered jcodemunch/graphify/jdocmunch playbook for the prompt's
    intent — the actionable half of 'jcodemunch is the primary engine'. The
    symbol item (build_item) says WHAT matches; this says WHICH TOOLS to use, in
    order, including semantic search. Fails open."""
    try:
        intents = getattr(profile, "intents", None) or {}
        top = max(intents, key=intents.get) if intents else None
        key = _INTENT_MAP.get(top) if top else None
        if key is None:
            key = "understand" if getattr(profile, "is_arch", False) else None
        if key is None:
            return None
        tm = _load_toolmap()
        if not tm:
            return None
        entry = (tm.get("intents") or {}).get(key)
        if not entry:
            return None
        lines = []
        for s in (entry.get("playbook") or [])[:_PLAYBOOK_STEPS]:
            eng = s.get("engine", "jcodemunch")
            prefix = "" if eng == "jcodemunch" else f"{eng} "
            sem = " [semantic]" if (s.get("modifiers") or {}).get("semantic") else ""
            lines.append(f"  {s.get('n')}. {prefix}{s.get('tool')}{sem} — {s.get('why','')}")
        if not lines:
            return None
        text = (
            f"jcodemunch playbook — intent {top or key.upper()} "
            f"(use these tools IN ORDER, not generic reads):\n"
            + "\n".join(lines)
            + "\n  Semantic search is live (all-minilm) — use search_symbols(semantic=true) "
              "when the exact name is unknown."
            + "\n  Full map: rules/references/tool-intelligence.md"
        )
        return {
            "id": f"intel:playbook:{key}",
            "tier": 1,
            "section": "INTEL",
            "text": text,
        }
    except Exception:
        return None  # never block a prompt
