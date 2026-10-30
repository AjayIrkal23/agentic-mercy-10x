"""library_routes.py — <= 2 ROUTING lines pointing into library/ (zero cost when nothing matches).

Contract (router._library_items): items(profile, cwd: str, emitted: set[str]) -> list[dict]
  [{"id": "library:<entry id>", "tier": 2, "text": "LIBRARY: ..."}]. Never raises; [] on any error.
Rules, first wins per slot, max two lines: (1) a library stack tag in profile.surfaces -> that rules pack;
(2) REVIEW intent + stack -> agents/<stack>-reviewer.md; (3) >= 2 distinct trigger phrases of one
skill/digest/command/agent -> that entry, when one hit is the head word of the entry's name (`redis` of
redis-patterns, `prompt` of prompt-caching-strategy) or the entry's stack is named in the prompt / present in
profile.surfaces; an entry with `stacks` (or a stack word such as `ktor` in its name) always needs that stack,
and a review-surface entry needs REVIEW intent. Description words alone ("server", "auth", "caching") never
route. Entries with conflicts are never emitted. Dedup via `emitted`.
Reads library/INDEX.json through a compact cache in state/library-index.cache.json (sig = mtime_ns:size).
No subprocess, no network; the only write is the cache (atomic). `cwd` is accepted for the contract and
reserved: stack tags already come from surface.py's repo scan.
"""
from __future__ import annotations

import json
import re
import sys
import time
from functools import lru_cache
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[2]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    _plat = None  # type: ignore
try:
    from lib import hook_telemetry as _tel
except Exception:  # noqa: BLE001
    _tel = None  # type: ignore

_STACKS = ("python", "django", "fastapi", "rust", "java", "springboot", "kotlin", "android", "swift", "dart", "php",
           "ruby", "csharp", "fsharp", "cpp", "perl", "angular", "vue", "nuxt", "arkts")  # never go/typescript/react
_PACK_OF = {"django": "python", "fastapi": "python", "springboot": "java", "android": "kotlin"}  # tag -> rules dir
_REVIEWER_OF = {"python": "python-reviewer", "django": "django-reviewer", "fastapi": "fastapi-reviewer",
                "rust": "rust-reviewer", "java": "java-reviewer", "springboot": "java-reviewer",
                "kotlin": "kotlin-reviewer", "android": "kotlin-reviewer", "swift": "swift-reviewer",
                "dart": "flutter-reviewer", "php": "php-reviewer", "ruby": "ruby-reviewer",
                "csharp": "csharp-reviewer", "fsharp": "fsharp-reviewer", "cpp": "cpp-reviewer", "vue": "vue-reviewer",
                "nuxt": "vue-reviewer", "perl": None, "angular": None, "arkts": None}
_USER_OWNED = {"go", "typescript", "react", "nextjs"}  # the user's own skills cover these: no trigger routing
_INDEX_PATH = (_plat.claude_dir() if _plat else Path("~/.claude").expanduser()) / "library" / "INDEX.json"
_BUDGET_MS = 40
_MATCHERS: dict = {}  # sig -> KeywordMatcher over {entry id: phrases}
_CACHE_V = 2  # compact trigger row: [id, path, kind, title, phrases, head_word, stack_words, review_only]
_GENERIC_NAME = {"patterns", "pattern", "skill", "skills", "guide", "best", "practices", "reviewer", "review",
                 "agent", "command", "io"}
# stack names plus framework words that imply one (a name word in this set also gates on the prompt naming it)
_STACK_WORDS = frozenset(_STACKS) | {"ktor", "compose", "flutter", "laravel", "rails", "swiftui", "ios", "dotnet",
                                     "gradle", "quarkus", "jpa", "mybatis", "harmonyos", "celery", "pytorch"}
_WORD_RE = re.compile(r"[a-z0-9+#]+")


def _name_words(eid: str) -> list[str]:
    """Words of the entry's name in order, minus generic parts: redis-patterns -> [redis], x-api -> [x, api]."""
    name = eid.split(":", 1)[-1].replace("_", "-")
    return list(dict.fromkeys(w for w in name.split("-") if w and w not in _GENERIC_NAME))


def _cache_path() -> Path:
    base = _plat.state_dir() if _plat else Path("~/.claude/state").expanduser()
    return base / "library-index.cache.json"


def _sig(p: Path) -> str | None:
    try:
        st = p.stat()
    except OSError:
        return None
    return f"{st.st_mtime_ns}:{st.st_size}"


def _compact(index: dict, sig: str) -> dict:
    packs, reviewers, triggers = {}, {}, []
    for e in index.get("entries") or []:
        if not isinstance(e, dict) or e.get("conflicts"):
            continue
        eid, path, kind = str(e.get("id", "")), str(e.get("path", "")), str(e.get("kind", ""))
        if kind == "rules-pack":
            for s in e.get("stacks") or []:
                packs[s] = {"id": eid, "path": path, "files": ["coding-style.md", "patterns.md"]}
        if kind == "agent" and "review" in (e.get("surfaces") or []):
            reviewers[eid.split(":", 1)[-1]] = {"id": eid, "path": path}
        phrases = [str(t) for t in e.get("triggers") or [] if str(t).strip()]
        stacks = {str(s) for s in e.get("stacks") or []}
        if phrases and kind != "rules-pack" and not stacks & _USER_OWNED:
            names = _name_words(eid)
            head = names[0] if names and names[0] in phrases else ""  # x-api: `x` is no trigger -> no head
            review_only = "review" in (e.get("surfaces") or []) or eid.endswith(("-review", "-reviewer"))
            triggers.append([eid, path, kind, str(e.get("title") or eid), phrases, head,
                             sorted(stacks | (set(names) & _STACK_WORDS)), review_only])
    return {"v": _CACHE_V, "sig": sig, "packs": packs, "reviewers": reviewers, "triggers": triggers}


@lru_cache(maxsize=1)
def _load(sig: str) -> dict:
    cache = _cache_path()
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("v") == _CACHE_V and data.get("sig") == sig and "packs" in data:
            return data
    except (OSError, ValueError):
        pass
    index = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    if not isinstance(index, dict) or index.get("schema") != 1:
        return {"sig": sig, "packs": {}, "reviewers": {}, "triggers": []}
    data = _compact(index, sig)
    if _plat is not None:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            _plat.atomic_write(cache, json.dumps(data, separators=(",", ":")))
        except Exception:  # noqa: BLE001  best effort
            pass
    return data


def _matcher(compact: dict):
    sig = compact.get("sig")
    m = _MATCHERS.get(sig)
    if m is None:
        from prompt_router.classify import KeywordMatcher  # noqa: PLC0415
        m = KeywordMatcher({t[0]: t[4] for t in compact.get("triggers") or []})
        _MATCHERS.clear()
        _MATCHERS[sig] = m
    return m


def _stack_hits(profile) -> list[str]:
    surfaces = set(getattr(profile, "surfaces", set()) or set())
    weak = set(getattr(profile, "weak_surfaces", set()) or set())
    tags = [t for t in _STACKS if t in surfaces | weak]
    return [t for t in tags if t not in weak] + [t for t in tags if t in weak]


def _trigger_hit(compact: dict, text: str, surfaces: set[str] = frozenset(), review: bool = False) -> list | None:
    if not text or not compact.get("triggers"):
        return None
    hits = _matcher(compact).hits(text)
    if not hits:
        return None
    seen = set(_WORD_RE.findall(text)) | set(surfaces)
    best = None
    for t in compact["triggers"]:
        got = set(hits.get(t[0], []))
        if len(got) < 2 or (t[7] and not review):
            continue
        stack_ok = bool(set(t[6]) & seen)
        if (t[6] and not stack_ok) or not (t[5] in got or stack_ok):  # the name's head word, or its stack
            continue
        n = len(got)
        if best is None or n > best[0] or (n == best[0] and t[0] < best[1][0]):
            best = (n, t)
    return best[1] if best else None


def _match(profile, compact: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    stacks = _stack_hits(profile)
    review = "REVIEW" in (getattr(profile, "intents", None) or {})
    for tag in stacks:
        pack = compact["packs"].get(_PACK_OF.get(tag, tag))
        if pack:
            p = pack["path"]
            out.append((pack["id"], f"LIBRARY: {_PACK_OF.get(tag, tag)} rules pack — read {p}coding-style.md + "
                                    f"{p}patterns.md (ECC, vendored; promotion is manual)"))
            break
    if review:
        for tag in stacks:
            rev = compact["reviewers"].get(_REVIEWER_OF.get(tag) or "")
            if rev:
                out.append((rev["id"], f"LIBRARY: {_REVIEWER_OF[tag]} lane — run a general-purpose subagent with "
                                       f"{rev['path']} as its prompt (model per model-policy; it reviews, never edits)"))
                break
    hit = _trigger_hit(compact, str(getattr(profile, "text", "") or "").lower(), set(stacks), review)
    if hit:
        eid, path, kind, title = hit[:4]
        title = title if len(title) <= 80 else title[:77].rstrip() + "..."
        out.append((eid, f"LIBRARY: {kind} {title} — read {path} before acting"))
    return out


def items(profile, cwd: str, emitted: set[str]) -> list[dict]:
    try:
        sig = _sig(_INDEX_PATH)
        if sig is None or profile is None:
            return []
        t0 = time.perf_counter()
        compact = _load(sig)
        seen = set(emitted or ())
        out = [{"id": f"library:{eid}", "tier": 2, "text": text}
               for eid, text in _match(profile, compact) if f"library:{eid}" not in seen][:2]
        ms = (time.perf_counter() - t0) * 1000
        if ms > _BUDGET_MS and _tel is not None:
            try:
                _tel.record("UserPromptSubmit", "prompt_router.library_slow", ms=round(ms, 2))
            except Exception:  # noqa: BLE001
                pass
        return out
    except Exception:  # noqa: BLE001  fail-open: the router never breaks on the library
        return []
