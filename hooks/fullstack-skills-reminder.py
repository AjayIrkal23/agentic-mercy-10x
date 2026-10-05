#!/usr/bin/env python3
"""Unified mandatory-skills hook: frontend-only, backend-only, or fullstack reminders."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.platform import locked_update  # noqa: E402

# Alias -> canonical resolution (alias stub skills no longer exist on disk).
try:
    from lib.skill_aliases import canonical as _canonical
except Exception:  # noqa: BLE001 — fail open: identity mapping
    def _canonical(name: str) -> str:  # type: ignore[misc]
        return name

# Smart router — selects 3 ranked skills instead of dumping the whole list.
# Falls back gracefully if skill_router.py is missing or broken.
try:
    import importlib.util as _ilu
    _sr_path = SCRIPT_DIR / "skill_router.py"
    _sr_spec = _ilu.spec_from_file_location("skill_router", _sr_path)
    _sr_mod = _ilu.module_from_spec(_sr_spec)  # type: ignore[arg-type]
    _sr_spec.loader.exec_module(_sr_mod)  # type: ignore[union-attr]
    _select_skills = _sr_mod.select_skills
    _format_compact = _sr_mod.format_compact
    _SMART_ROUTER_AVAILABLE = True
except Exception:
    _SMART_ROUTER_AVAILABLE = False
    _select_skills = None  # type: ignore[assignment]
    _format_compact = None  # type: ignore[assignment]

# Canonical baseline sets (no aliases; every name is a real skills/<name>/SKILL.md).
# Consumed here (fallback reminder lines), by gen-agent-skill-blocks.py (agent
# `skills:` frontmatter) and by the weight updater (never weighted below baseline).
FRONTEND_SKILLS = [
    "frontend-standards-always-follow",
    "frontend-structure-standards",
    "frontend-response-handling",
    "frontend-server-data-patterns",
    "react-hooks-patterns",
    "tailwind-design-system",
    "shadcn",
    "motion-dev",
    "design-taste-frontend",
    "frontend-ui-engineering",
    "vite-react-best-practices",
    "webapp-testing",
    "api-contract-standards",
    "scaffold-standards",
    "higgsfield-generate",
    "owasp-security",
    "architect-system-design",
    "codebase-intel-first",
    "project-reference-linkage",
    "dead-code-and-change-audit",
    "debug-investigation",
    "doubt-driven-development",
    "verification-loop",
    "tool-and-doc-selection",
    "mcp-usage-standards",
]

BACKEND_SKILLS = [
    "backend-standards-always-follow",
    "backend-api-standards",
    "api-contract-standards",
    "service-layer-standards",
    "backend-error-handling",
    "backend-performance-standards",
    "scaffold-standards",
    "golang-patterns",
    "golang-testing",
    "postgres-patterns",
    "owasp-security",
    "code-review-and-quality",
    "tech-debt-audit",
    "architect-system-design",
    "codebase-intel-first",
    "project-reference-linkage",
    "dead-code-and-change-audit",
    "debug-investigation",
    "doubt-driven-development",
    "source-driven-development",
    "eval-harness",
    "tool-and-doc-selection",
    "mcp-usage-standards",
]

# Segments used to detect context for the extended one-liner
_AUTH_SEGMENTS = ["auth", "middleware", "session", "cookie", "guard", "jwt", "token"]
_GO_SEGMENTS = [".go", "internal/", "cmd/", "pkg/", "server/"]
_TEST_SEGMENTS = ["_test.go", ".test.", ".spec.", "__tests__", "test_"]

# Stack-neutral defaults; a repo overrides them in fullstack-skills-reminder.config.json.
DEFAULT_FE = ["client/", "frontend/", "apps/web"]
DEFAULT_BE = ["server/", "backend/", "api/", "internal/", "cmd/", "pkg/"]
DEFAULT_DOC = ["docs/", "server_docs/", "frontend_docs/", "PROJECT_LINKAGES.md"]

NATIVE_PATHS_NOTE = (
    "Native `paths:` will surface the rest as you read files; domain rules load from "
    "~/.claude/rules/frontend.md and ~/.claude/rules/backend.md."
)

CONFIG_PATH = SCRIPT_DIR / "fullstack-skills-reminder.config.json"
SKILL_ROOT = Path.home() / ".claude" / "skills"


def _skill_resolved(name: str) -> str:
    return str((SKILL_ROOT / _canonical(name) / "SKILL.md").resolve())


def _load_config() -> tuple[list[str], list[str], list[str]]:
    fe, be = list(DEFAULT_FE), list(DEFAULT_BE)
    doc = list(DEFAULT_DOC)
    if CONFIG_PATH.is_file():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            raw_fe = cfg.get("frontend_path_segments")
            raw_be = cfg.get("backend_path_segments")
            raw_doc = cfg.get("documentation_path_segments")
            if isinstance(raw_fe, list) and raw_fe:
                fe = [str(s).strip() for s in raw_fe if str(s).strip()]
            if isinstance(raw_be, list) and raw_be:
                be = [str(s).strip() for s in raw_be if str(s).strip()]
            if isinstance(raw_doc, list) and raw_doc:
                doc = [str(s).strip() for s in raw_doc if str(s).strip()]
        except (json.JSONDecodeError, OSError):
            pass
    return fe, be, doc


def _state_path(cid: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    d = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or SCRIPT_DIR / ".state")
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe}.fullstack.json"


def _load_state(cid: str) -> dict:
    p = _state_path(cid)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(cid: str, data: dict) -> None:
    """Locked merge onto the current file (audit J-01): first-write-skill-gate owns
    `skills_hint_surfaces` in the same file, and this hook's flags only go True."""
    def merge(fresh: dict) -> dict:
        hints = set(fresh.get("skills_hint_surfaces") or []) | set(data.get("skills_hint_surfaces") or [])
        fresh.update(data)
        if hints:
            fresh["skills_hint_surfaces"] = sorted(hints)
        return fresh
    locked_update(_state_path(cid), merge)


def _norm(p: str) -> str:
    return p.replace("\\", "/")


def _matches_any(path_norm: str, blob_norm: str, segments: list[str]) -> bool:
    for seg in segments:
        s = _norm(seg)
        if s and (s in path_norm or s in blob_norm):
            return True
    return False


def _path_hits_segments(path: str, roots: list[str], segments: list[str]) -> bool:
    n = _norm(path)
    if _matches_any(n, "", segments):
        return True
    for root in roots:
        try:
            full = _norm(str((Path(root) / path).resolve()))
            if _matches_any(full, "", segments):
                return True
        except (OSError, ValueError):
            continue
    return False


def _paths_from(ti: object) -> list[str]:
    if not isinstance(ti, dict):
        return []
    out = []
    for k in ("path", "file_path", "target_file", "file"):
        v = ti.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out


_FRONTEND_EXTENSIONS = {".tsx", ".jsx", ".vue", ".svelte", ".astro", ".css", ".scss", ".sass", ".less"}
_FRONTEND_TS_SEGMENTS = ("/components/", "/app/", "/pages/", "/routes/", "/client/", "/frontend/", "/apps/web/", "/packages/ui/")
_BACKEND_TS_SEGMENTS = ("/server/", "/backend/", "/api/", "/internal/", "/cmd/", "/pkg/")


def _surface_of_path(path: str, roots: list[str], fe_segs: list[str], be_segs: list[str]) -> tuple[bool, bool]:
    normalized = "/" + _norm(path).lower().lstrip("/")
    suffix = Path(normalized).suffix.lower()
    fe = _path_hits_segments(path, roots, fe_segs)
    be = _path_hits_segments(path, roots, be_segs)
    if suffix in _FRONTEND_EXTENSIONS:
        fe = True
    elif suffix == ".ts":
        fe = fe or any(segment in normalized for segment in _FRONTEND_TS_SEGMENTS)
        be = be or any(segment in normalized for segment in _BACKEND_TS_SEGMENTS)
    elif suffix == ".go":
        be = True
    return fe, be


def _skill_line(name: str) -> str:
    return f"  - {(SKILL_ROOT / _canonical(name) / 'SKILL.md').resolve()}"


def _classify(ti: dict, roots: list[str], fe_segs: list[str], be_segs: list[str]):
    paths = _paths_from(ti)
    if paths:
        surfaces = [_surface_of_path(path, roots, fe_segs, be_segs) for path in paths]
        return any(fe for fe, _ in surfaces), any(be for _, be in surfaces)
    blob = _norm(json.dumps(ti))
    fe = _matches_any("", blob, fe_segs)
    be = _matches_any("", blob, be_segs)
    return fe, be


def _doc_hit(ti: dict, roots: list[str], doc_segs: list[str]) -> bool:
    # Same rule as _classify: a real path decides; the blob (file content)
    # counts only when the call carries no path. Segments match whole path
    # components, so `docs/` does not hit `ant-docs/`.
    paths = _paths_from(ti)
    if paths:
        for p in paths:
            n = "/" + _norm(p).lstrip("/")
            if any(_norm(s) and "/" + _norm(s).lstrip("/") in n for s in doc_segs):
                return True
        return False
    return _matches_any("", _norm(json.dumps(ti)), doc_segs)


def _onb() -> str:
    return f"  - {(SKILL_ROOT / 'codebase-intel-first' / 'SKILL.md').resolve()} (orientation: index + graph before reading files)."


def _engineering_lines() -> list[str]:
    return [
        "",
        "[Hook: engineering workflow skills]",
        "**Invoke the matching skill when its trigger fires:**",
        f"  - `/debug-investigation` → bug cause unknown, unexpected test failure, behavior != expectation: {_skill_resolved('debug-investigation')}",
        f"  - `/test-driven-development` → new service methods, user says test-first, bug that must not recur: {_skill_resolved('test-driven-development')}",
        f"  - `/grill-with-docs` → before finalizing plan touching >3 files or new domain concepts: {_skill_resolved('grill-with-docs')}",
        f"  - `/to-prd` → user wants PRD, large new feature: {_skill_resolved('to-prd')}",
        f"  - `/to-issues` → after plan/PRD approval, break into vertical issues: {_skill_resolved('to-issues')}",
        f"  - `/tech-debt-audit` → user-invoked whole-repo debt / architecture audit: {_skill_resolved('tech-debt-audit')}",
        f"  - `/triage` → processing external issues/bug reports: {_skill_resolved('triage')}",
        "  - First engineering workflow in repo: skim `tool-and-doc-selection` and `codebase-intel-first` before deep work.",
    ]


def _attach_engineering_once(st: dict, lines: list[str]) -> list[str]:
    if st.get("engineering_skills_sent"):
        return lines
    st["engineering_skills_sent"] = True
    return [*lines, *_engineering_lines()]


def _fullstack_grouped_lines() -> list[str]:
    """De-dupe skills that appear in both FRONTEND_SKILLS and BACKEND_SKILLS."""
    fe_set = set(FRONTEND_SKILLS)
    be_set = set(BACKEND_SKILLS)
    shared = [s for s in FRONTEND_SKILLS if s in be_set]
    fe_only = [s for s in FRONTEND_SKILLS if s not in be_set]
    be_only = [s for s in BACKEND_SKILLS if s not in fe_set]
    lines: list[str] = []
    if shared:
        lines.append("### Shared (applies to fullstack work)")
        lines.extend(_skill_line(n) for n in shared)
    if fe_only:
        lines.append("### Frontend-only")
        lines.extend(_skill_line(n) for n in fe_only)
    if be_only:
        lines.append("### Backend-only")
        lines.extend(_skill_line(n) for n in be_only)
    return lines


def _extended_category_oneliner(ti: dict, is_first_write: bool) -> str:
    """Return a single ≤100-char line referencing relevant ENGINEERING_EXTENDED categories.

    Rules (mutually inclusive — all matching categories are shown):
    - auth/middleware/session path → Quality: owasp-security
    - Go file path              → golang-patterns, golang-testing
    - test file path            → test-driven-development
    - first write of session    → Workflow: workflow-orchestrator, code-execution-standard
    """
    paths = _paths_from(ti)
    blob_norm = _norm(json.dumps(ti)).lower()

    parts: list[str] = []

    # Auth / security context
    auth_hit = any(seg in blob_norm for seg in _AUTH_SEGMENTS)
    if auth_hit:
        parts.append("Quality: owasp-security, performance-optimization")

    # Go file context
    go_hit = any(
        any(seg in _norm(p).lower() for seg in _GO_SEGMENTS)
        for p in paths
    ) or any(seg in blob_norm for seg in [".go"])
    if go_hit and not auth_hit:
        parts.append("Quality: golang-patterns, golang-testing")
    elif go_hit and auth_hit:
        # merge into existing quality entry — keep it one line
        parts[-1] += ", golang-patterns, golang-testing"

    # Test file context
    test_hit = any(
        any(seg in _norm(p).lower() for seg in _TEST_SEGMENTS)
        for p in paths
    ) or any(seg in blob_norm for seg in _TEST_SEGMENTS)
    if test_hit:
        parts.append("Testing: test-driven-development")

    # First write — workflow reference
    if is_first_write:
        parts.append("Workflow: workflow-orchestrator, code-execution-standard")

    if not parts:
        return ""
    line = " | ".join(parts)
    # hard cap at 120 chars (one-liner intent)
    if len(line) > 120:
        line = line[:117] + "..."
    return f"Extended: {line}"


def _cross_cut_mode_for_path(fp: str) -> str | None:
    norm = fp.replace("\\", "/").lower()
    if any(k in norm for k in ("debug", "trace", "diagnose", "investigate")):
        return "debug"
    if any(k in norm for k in (".test.", ".spec.", "__tests__", "_test.")):
        return "verification"
    return "implementation"


def _post(payload: dict) -> dict:
    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        return {}

    roots = payload.get("workspace_roots") or []
    if not isinstance(roots, list):
        roots = []

    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        ti = {}

    fe_segs, be_segs, doc_segs = _load_config()
    fe_hit, be_hit = _classify(ti, roots, fe_segs, be_segs)
    dh = _doc_hit(ti, roots, doc_segs)

    if not fe_hit and not be_hit and not dh:
        return {}

    st = _load_state(cid)
    if fe_hit:
        st["frontend_touched"] = True
    if be_hit:
        st["backend_touched"] = True

    doc_lines: list[str] = []
    if dh and not st.get("doc_update_reminder_sent"):
        doc_lines = [
            "[Hook: documentation paths touched]",
            _skill_line("update-docs").strip() + " — read update-docs workflow.",
        ]
        st["doc_update_reminder_sent"] = True

    ft, bt = bool(st.get("frontend_touched")), bool(st.get("backend_touched"))
    out: dict = {}
    doc_merged = False

    def merge_doc(lines: list[str]) -> str:
        nonlocal doc_merged
        if doc_lines:
            doc_merged = True
            return "\n".join([*doc_lines, "", *lines])
        return "\n".join(lines)

    if ft and bt:
        if not st.get("fullstack_start_sent"):
            is_first = not st.get("frontend_start_sent") and not st.get("backend_start_sent")
            if _SMART_ROUTER_AVAILABLE:
                # Emit one compact block per surface (frontend path wins for MUST-READ)
                fp = _paths_from(ti)
                fp_str = fp[0] if fp else ""
                mode = _cross_cut_mode_for_path(fp_str)
                fe_skills = _select_skills(fp_str, "frontend", is_first_write=is_first, cross_cut_mode=mode)
                be_skills = _select_skills(fp_str, "backend", is_first_write=False, cross_cut_mode=mode)
                fe_block = _format_compact(fp_str, "frontend", fe_skills)
                be_block = _format_compact(fp_str, "backend", be_skills)
                lines = (
                    "[Hook: mandatory skills — fullstack start]\n"
                    + fe_block
                    + "\n---\n"
                    + be_block
                ).splitlines()
            else:
                lines = [
                    "[Hook: mandatory skills — fullstack start]",
                    "Touches **both** frontend and backend paths; baseline skills (shared names listed once):",
                    "",
                    *_fullstack_grouped_lines(),
                    "",
                    _onb(),
                    NATIVE_PATHS_NOTE,
                ]
            lines = _attach_engineering_once(st, lines)
            ext = _extended_category_oneliner(ti, is_first_write=is_first)
            if ext:
                lines = [*lines, ext]
            out["additionalContext"] = merge_doc(lines)
            st["fullstack_start_sent"] = True
    elif ft and fe_hit and not st.get("frontend_start_sent"):
        if _SMART_ROUTER_AVAILABLE:
            fp = _paths_from(ti)
            fp_str = fp[0] if fp else ""
            mode = _cross_cut_mode_for_path(fp_str)
            skills = _select_skills(fp_str, "frontend", is_first_write=True, cross_cut_mode=mode)
            compact = _format_compact(fp_str, "frontend", skills)
            lines = ("[Hook: mandatory skills — frontend start]\n" + compact).splitlines()
        else:
            lines = [
                "[Hook: mandatory skills — frontend start]",
                "Frontend baseline skills:",
                *[_skill_line(n) for n in FRONTEND_SKILLS[:3]],
                _onb(),
                NATIVE_PATHS_NOTE,
            ]
        lines = _attach_engineering_once(st, lines)
        ext = _extended_category_oneliner(ti, is_first_write=True)
        if ext:
            lines = [*lines, ext]
        out["additionalContext"] = merge_doc(lines)
        st["frontend_start_sent"] = True
    elif bt and be_hit and not st.get("backend_start_sent"):
        if _SMART_ROUTER_AVAILABLE:
            fp = _paths_from(ti)
            fp_str = fp[0] if fp else ""
            mode = _cross_cut_mode_for_path(fp_str)
            skills = _select_skills(fp_str, "backend", is_first_write=True, cross_cut_mode=mode)
            compact = _format_compact(fp_str, "backend", skills)
            lines = ("[Hook: mandatory skills — backend start]\n" + compact).splitlines()
        else:
            lines = [
                "[Hook: mandatory skills — backend start]",
                "Backend baseline skills:",
                *[_skill_line(n) for n in BACKEND_SKILLS[:3]],
                _onb(),
                NATIVE_PATHS_NOTE,
            ]
        lines = _attach_engineering_once(st, lines)
        ext = _extended_category_oneliner(ti, is_first_write=True)
        if ext:
            lines = [*lines, ext]
        out["additionalContext"] = merge_doc(lines)
        st["backend_start_sent"] = True

    if doc_lines and not doc_merged:
        out["additionalContext"] = "\n".join(_attach_engineering_once(st, list(doc_lines)))

    # No per-write manifest batches: the first write carries top-3 + cross-cuts and
    # native skill `paths:` frontmatter surfaces the rest as files are read.
    _save_state(cid, st)
    return out


def main() -> int:
    """`post-tool-use` is the only mode. The old `stop` mode (pre-close reminder +
    skill-effectiveness writer) was wired to no event since 2026-09-28 and was
    removed (audit B2-14); any other mode prints {}."""
    if len(sys.argv) < 2:
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0
    out = _post(payload) if sys.argv[1] == "post-tool-use" else {}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
