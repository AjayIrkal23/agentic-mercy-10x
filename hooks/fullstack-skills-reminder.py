#!/usr/bin/env python3
"""Unified mandatory-skills hook: frontend-only, backend-only, or fullstack reminders."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# Smart router — selects 3 ranked skills instead of dumping all 20/15.
# Falls back gracefully if skill_router.py is missing or broken.
try:
    import importlib.util as _ilu
    _sr_path = Path(__file__).resolve().parent / "skill_router.py"
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

FRONTEND_SKILLS = [
    "agent-development",
    "api-contract-standards",
    "dead-code-and-change-audit",
    "debug-investigation",
    "domain-scaffold-patterns",
    "frontend-api-standards",
    "frontend-code-review",
    "frontend-response-handling",
    "frontend-server-data-patterns",
    "frontend-standards-always-follow",
    "frontend-structure-standards",
    "project-reference-linkage",
    "project-structure-map",
    "react-hooks-patterns",
    "scaffold-standards",
    "tailwind-design-system",
    "tool-and-doc-selection",
    "webapp-testing",
    "architect-system-design",
    "mcp-usage-standards",
    "owasp-security",
    "doubt-driven-development",
    "iterative-retrieval",
    "verification-loop",
    # Extended frontend skills
    "frontend-ui-engineering",
    "vite-react-best-practices",
    "browser-testing-with-devtools",
    # Design skills
    "design-extract",
    # Asset generation — Higgsfield (mandatory for all image/video/3D/audio assets)
    "higgsfield-generate",
]

BACKEND_SKILLS = [
    "backend-api-standards",
    "api-contract-standards",
    "backend-code-review",
    "backend-error-handling",
    "backend-performance-standards",
    "backend-standards-always-follow",
    "dead-code-and-change-audit",
    "debug-investigation",
    "domain-scaffold-patterns",
    "project-reference-linkage",
    "project-structure-map",
    "scaffold-standards",
    "service-layer-standards",
    "tool-and-doc-selection",
    "architect-system-design",
    "mcp-usage-standards",
    "owasp-security",
    "doubt-driven-development",
    "forensic-complexity-trends",
    "forensic-debt-quantification",
    "eval-harness",
    "source-driven-development",
    # Extended backend skills
    "golang-patterns",
    "golang-testing",
    "postgres-patterns",
    "api-and-interface-design",
    "security-and-hardening",
]

# Matt Pocock engineering bundle — https://github.com/mattpocock/skills/tree/main/skills/engineering
# Order: daily-driver flow (diagnose/grill/intake/architecture/setup → implementation → backlog)
ENGINEERING_SKILLS = [
    "diagnose",
    "grill-with-docs",
    "triage",
    "improve-codebase-architecture",
    "setup-matt-pocock-skills",
    "tdd",
    "to-issues",
    "to-prd",
    "zoom-out",
    "prototype",
]

# ENGINEERING_EXTENDED: quality / shipping / workflow — appended selectively in _post() and _stop()
QUALITY_SKILLS = [
    "performance-optimization",
    "security-and-hardening",
    "code-simplification",
    "debugging-and-error-recovery",
]

SHIPPING_SKILLS = [
    "ci-cd-and-automation",
    "git-workflow-and-versioning",
    "shipping-and-launch",
    "deprecation-and-migration",
    "documentation-and-adrs",
    "fix-lint-format",
]

WORKFLOW_SKILLS = [
    "workflow-orchestrator",
    "planning-and-task-breakdown",
    "context-engineering",
    "code-execution-standard",
    "spec-driven-development",
    "incremental-implementation",
    "codebase-start-point-guide",
]

# Segments used to detect context for ENGINEERING_EXTENDED one-liner
_AUTH_SEGMENTS = ["auth", "middleware", "session", "cookie", "guard", "jwt", "token"]
_GO_SEGMENTS = [".go", "internal/", "cmd/", "pkg/", "server/"]
_TEST_SEGMENTS = ["_test.go", ".test.", ".spec.", "__tests__", "test_"]

DEFAULT_FE = ["UDP_PLATFORM/client", "client/", "frontend/", "apps/web"]
DEFAULT_BE = [
    "UDP_PLATFORM/server",
    "server/",
    "backend/",
    "api/",
    "internal/",
    "cmd/",
    "pkg/",
]
DEFAULT_DOC = [
    "server_docs/",
    "frontend_docs/",
    "PROJECT_LINKAGES.md",
    "UDP_PLATFORM/server/server_docs",
    "UDP_PLATFORM/client/frontend_docs",
]

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "fullstack-skills-reminder.config.json"
SKILL_ROOT = Path.home() / ".claude" / "skills"
PLUGINS_ROOT = Path.home() / ".claude" / "plugins"
UDP_PLATFORM_SEGMENTS = ["UDP_PLATFORM/"]


def _discover_superpowers_skills_dir() -> Path | None:
    env = (os.environ.get("SUPERPOWERS_SKILLS_ROOT") or "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
    try:
        for super_dir in PLUGINS_ROOT.glob("**/superpowers"):
            if not super_dir.is_dir():
                continue
            for child in super_dir.iterdir():
                if child.is_dir() and (child / "skills").is_dir():
                    return child / "skills"
    except OSError:
        pass
    return None


def _skill_resolved(name: str) -> str:
    return str((SKILL_ROOT / name / "SKILL.md").resolve())


def _udp_workspace_hit(ti: dict, roots: list[str]) -> bool:
    paths = _paths_from(ti)
    blob = _norm(json.dumps(ti))
    if any(_path_hits_segments(p, roots, UDP_PLATFORM_SEGMENTS) for p in paths):
        return True
    return _matches_any("", blob, UDP_PLATFORM_SEGMENTS)


def _maybe_udp_vertical_slice_nudge(st: dict, ti: dict, roots: list[str], fe_hit: bool, be_hit: bool, msg: str) -> str:
    if st.get("udp_vertical_nudge_sent") or not (fe_hit or be_hit):
        return msg
    if not _udp_workspace_hit(ti, roots):
        return msg
    st["udp_vertical_nudge_sent"] = True
    inc = _skill_resolved("incremental-implementation")
    dca = _skill_resolved("dead-code-and-change-audit")
    extra = (
        "\n\n[Hook: GO_UDP vertical slice discipline — once per conversation]\n"
        f"- Before the next slice, skim **`incremental-implementation`**: `{inc}` "
        f"and **`dead-code-and-change-audit`**: `{dca}`.\n"
    )
    return msg + extra


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
    d = SCRIPT_DIR / ".state"
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
    _state_path(cid).write_text(json.dumps(data, indent=2), encoding="utf-8")


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


def _skill_line(name: str) -> str:
    return f"  - {(SKILL_ROOT / name / 'SKILL.md').resolve()}"


def _classify(ti: dict, roots: list[str], fe_segs: list[str], be_segs: list[str]):
    paths = _paths_from(ti)
    blob = _norm(json.dumps(ti))
    fe = any(_path_hits_segments(p, roots, fe_segs) for p in paths)
    be = any(_path_hits_segments(p, roots, be_segs) for p in paths)
    if not fe:
        fe = _matches_any("", blob, fe_segs)
    if not be:
        be = _matches_any("", blob, be_segs)
    return fe, be


def _doc_hit(ti: dict, roots: list[str], doc_segs: list[str]) -> bool:
    paths = _paths_from(ti)
    blob = _norm(json.dumps(ti))
    if any(_path_hits_segments(p, roots, doc_segs) for p in paths):
        return True
    return _matches_any("", blob, doc_segs)


def _onb() -> str:
    return f"  - {(SKILL_ROOT / 'codebase-start-point-guide' / 'SKILL.md').resolve()} (onboarding when repo defines doc order)."


def _engineering_lines() -> list[str]:
    return [
        "",
        "[Hook: engineering workflow skills — mattpocock/skills]",
        "**Invoke the matching skill when its trigger fires:**",
        f"  - `/diagnose` → bug cause unknown, unexpected test failure, behavior != expectation: {_skill_resolved('diagnose')}",
        f"  - `/tdd` → new service methods, user says test-first, bug that must not recur: {_skill_resolved('tdd')}",
        f"  - `/grill-with-docs` → before finalizing plan touching >3 files or new domain concepts: {_skill_resolved('grill-with-docs')}",
        f"  - `/to-prd` → user wants PRD, large new feature: {_skill_resolved('to-prd')}",
        f"  - `/to-issues` → after plan/PRD approval, break into vertical issues: {_skill_resolved('to-issues')}",
        f"  - `/prototype` → uncertain approach, throwaway spike resolves faster than discussion: {_skill_resolved('prototype')}",
        f"  - `/improve-codebase-architecture` → refactoring, tech debt, structural changes: {_skill_resolved('improve-codebase-architecture')}",
        f"  - `/zoom-out` → unfamiliar code area, need broader context: {_skill_resolved('zoom-out')}",
        f"  - `/triage` → processing external issues/bug reports: {_skill_resolved('triage')}",
        f"  - First engineering workflow in repo: skim `tool-and-doc-selection` and `codebase-start-point-guide` before deep work.",
    ]


def _attach_engineering_once(st: dict, lines: list[str]) -> list[str]:
    if st.get("engineering_skills_sent"):
        return lines
    st["engineering_skills_sent"] = True
    return [*lines, *_engineering_lines()]


def _surface_skill_list(surface: str) -> list[str]:
    if surface == "frontend":
        return list(FRONTEND_SKILLS)
    if surface == "backend":
        return list(BACKEND_SKILLS)
    return list(dict.fromkeys([*FRONTEND_SKILLS, *BACKEND_SKILLS]))


def _manifest_init(st: dict, surface: str, reminded: list[str]) -> None:
    key_pending = f"manifest_pending_{surface}"
    key_reminded = f"manifest_reminded_{surface}"
    if key_pending in st:
        return
    all_names = _surface_skill_list(surface)
    already = set(reminded or [])
    st[key_pending] = [n for n in all_names if n not in already]
    st[key_reminded] = list(already)


def _manifest_followup_lines(st: dict, surface: str, batch: int = 4) -> list[str]:
    key_pending = f"manifest_pending_{surface}"
    pending = st.get(key_pending)
    if not isinstance(pending, list) or not pending:
        return []
    chunk = [n for n in pending[:batch] if isinstance(n, str)]
    st[key_pending] = pending[len(chunk) :]
    if not chunk:
        return []
    lines = [
        f"[Hook: session skill manifest — {surface} ({len(chunk)} more mandatory skills)]",
        "Also read (compact paths):",
    ]
    lines.extend(_skill_line(n) for n in chunk)
    return lines


def _remember_stop_skills(st: dict, surface: str, skills: list[dict]) -> None:
    names = [s["name"] for s in skills if s.get("priority") != "CROSS-CUT"]
    pending = st.get(f"manifest_pending_{surface}")
    if isinstance(pending, list) and pending:
        names = list(dict.fromkeys([*names, *pending]))
    if not names:
        return
    if surface == "frontend":
        st["stop_fe_skills"] = names
    else:
        st["stop_be_skills"] = names


def _stop_path_for_surface(st: dict, surface: str) -> str:
    key = "last_fe_write_path" if surface == "frontend" else "last_be_write_path"
    saved = st.get(key) or st.get("last_write_path")
    if isinstance(saved, str) and saved.strip():
        return saved
    return "src/components/App.tsx" if surface == "frontend" else "internal/service/service.go"


def _stop_skill_reminder_lines(ft: bool, bt: bool, st: dict) -> list[str]:
    """One-line pre-close reminder using skills captured at first Write."""
    fe_saved = st.get("stop_fe_skills") if isinstance(st.get("stop_fe_skills"), list) else None
    be_saved = st.get("stop_be_skills") if isinstance(st.get("stop_be_skills"), list) else None

    if fe_saved or be_saved:
        lines = ["Re-verify mandatory skills from first Write:"]
        if ft and fe_saved:
            lines.append("- FE: " + ", ".join(f"`{n}`" for n in fe_saved))
        if bt and be_saved:
            lines.append("- BE: " + ", ".join(f"`{n}`" for n in be_saved))
        lines.append("Confirm compliance, then summarize.")
        return lines

    if _SMART_ROUTER_AVAILABLE:
        lines = ["Re-verify mandatory skills from first Write:"]
        if ft:
            fp = _stop_path_for_surface(st, "frontend")
            skills = _select_skills(fp, "frontend", is_first_write=False)
            primary = [s["name"] for s in skills if s.get("priority") != "CROSS-CUT"][:3]
            lines.append("- FE: " + ", ".join(f"`{n}`" for n in primary))
        if bt:
            fp = _stop_path_for_surface(st, "backend")
            skills = _select_skills(fp, "backend", is_first_write=False)
            primary = [s["name"] for s in skills if s.get("priority") != "CROSS-CUT"][:3]
            lines.append("- BE: " + ", ".join(f"`{n}`" for n in primary))
        lines.append("Confirm compliance, then summarize.")
        return lines

    if ft and bt:
        return [
            "Re-verify both stacks — see skills injected at first Write.",
            "Confirm compliance, then summarize.",
        ]
    if ft:
        return ["Re-verify frontend skills from first Write.", "Confirm compliance, then summarize."]
    return ["Re-verify backend skills from first Write.", "Confirm compliance, then summarize."]


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
    - auth/middleware/session path → Quality: security-and-hardening
    - Go file path              → golang-patterns, golang-testing
    - test file path            → test-driven-development
    - first write of session    → Workflow: workflow-orchestrator, incremental-implementation
    """
    paths = _paths_from(ti)
    blob_norm = _norm(json.dumps(ti)).lower()

    parts: list[str] = []

    # Auth / security context
    auth_hit = any(seg in blob_norm for seg in _AUTH_SEGMENTS)
    if auth_hit:
        parts.append("Quality: security-and-hardening, performance-optimization")

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
        parts.append("Testing: test-driven-development, tdd")

    # First write — workflow reference
    if is_first_write:
        parts.append("Workflow: workflow-orchestrator, incremental-implementation")

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
    fp = _paths_from(ti)
    if fp:
        st["last_write_path"] = fp[0]
        if fe_hit:
            st["last_fe_write_path"] = fp[0]
        if be_hit:
            st["last_be_write_path"] = fp[0]
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
                _manifest_init(st, "frontend", [s["name"] for s in fe_skills])
                _manifest_init(st, "backend", [s["name"] for s in be_skills])
                _remember_stop_skills(st, "frontend", fe_skills)
                _remember_stop_skills(st, "backend", be_skills)
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
                    "Touches **both** frontend and backend paths; read **every** skill below (shared names listed once):",
                    "",
                    *_fullstack_grouped_lines(),
                    "",
                    _onb(),
                    "Rule: ~/.claude/rules/mandatory-skill-protocol.mdc (Project Rules when home folder open).",
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
            _manifest_init(st, "frontend", [s["name"] for s in skills])
            _remember_stop_skills(st, "frontend", skills)
            compact = _format_compact(fp_str, "frontend", skills)
            lines = ("[Hook: mandatory skills — frontend start]\n" + compact).splitlines()
        else:
            lines = [
                "[Hook: mandatory skills — frontend start]",
                "Read every frontend SKILL.md:",
                *[_skill_line(n) for n in FRONTEND_SKILLS],
                _onb(),
                "Rule: ~/.claude/rules/mandatory-skill-protocol.mdc (Project Rules when home folder open).",
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
            _manifest_init(st, "backend", [s["name"] for s in skills])
            _remember_stop_skills(st, "backend", skills)
            compact = _format_compact(fp_str, "backend", skills)
            lines = ("[Hook: mandatory skills — backend start]\n" + compact).splitlines()
        else:
            lines = [
                "[Hook: mandatory skills — backend start]",
                "Read every backend SKILL.md:",
                *[_skill_line(n) for n in BACKEND_SKILLS],
                _onb(),
                "Rule: ~/.claude/rules/mandatory-skill-protocol.mdc (Project Rules when home folder open).",
            ]
        lines = _attach_engineering_once(st, lines)
        ext = _extended_category_oneliner(ti, is_first_write=True)
        if ext:
            lines = [*lines, ext]
        out["additionalContext"] = merge_doc(lines)
        st["backend_start_sent"] = True

    if doc_lines and not doc_merged:
        out["additionalContext"] = "\n".join(_attach_engineering_once(st, list(doc_lines)))

    ac_final = out.get("additionalContext")
    manifest_lines: list[str] = []
    if (ft and st.get("frontend_start_sent")) or st.get("fullstack_start_sent"):
        manifest_lines.extend(_manifest_followup_lines(st, "frontend"))
    if (bt and st.get("backend_start_sent")) or st.get("fullstack_start_sent"):
        manifest_lines.extend(_manifest_followup_lines(st, "backend"))
    if manifest_lines and not ac_final:
        out["additionalContext"] = "\n".join(manifest_lines)
        ac_final = out["additionalContext"]
    elif manifest_lines and isinstance(ac_final, str):
        out["additionalContext"] = ac_final + "\n\n" + "\n".join(manifest_lines)
        ac_final = out["additionalContext"]

    if isinstance(ac_final, str) and ac_final.strip():
        out["additionalContext"] = _maybe_udp_vertical_slice_nudge(st, ti, roots, fe_hit, be_hit, ac_final)

    _save_state(cid, st)
    return out


def _verification_close_followup_fragment() -> str:
    slugs: list[str] = []
    sp_dir_stop = _discover_superpowers_skills_dir()
    if sp_dir_stop:
        for sp_slug in (
            "verification-before-completion",
            "finishing-a-development-branch",
        ):
            if (sp_dir_stop / sp_slug / "SKILL.md").is_file():
                slugs.append(sp_slug)
    if (SKILL_ROOT / "code-review-and-quality" / "SKILL.md").is_file():
        slugs.append("code-review-and-quality")
    if not slugs:
        return ""
    return "Lifecycle: " + ", ".join(f"`{s}`" for s in slugs)


def _current_write_count(cid: str) -> int:
    """Read code_writes from desloppify state for stop-refill logic."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    p = SCRIPT_DIR / ".state" / f"{safe}.desloppify.json"
    if not p.is_file():
        return 0
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get("code_writes", 0))
    except Exception:
        return 0


def _write_effectiveness_record(cid: str, st: dict, ft: bool, bt: bool) -> None:
    """Diff reminded vs invoked skills; append one JSONL record to skill-effectiveness.jsonl.

    Reads:  ~/.claude/hooks/.telemetry/{safe_cid}.skill-invocations.jsonl  (from task 27)
    Writes: ~/.claude/hooks/.telemetry/skill-effectiveness.jsonl  (cross-session aggregate)
    """
    import datetime as _dt

    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    telemetry_dir = SCRIPT_DIR / ".telemetry"

    # Collect all reminded skills (both surfaces)
    reminded_fe: list[str] = list(st.get("manifest_reminded_frontend") or [])
    reminded_be: list[str] = list(st.get("manifest_reminded_backend") or [])
    reminded_all = list(dict.fromkeys(reminded_fe + reminded_be))  # preserve order, dedup

    if not reminded_all:
        return  # Nothing was reminded — nothing to measure

    # Collect all invoked skills from tracker JSONL
    invocations_path = telemetry_dir / f"{safe}.skill-invocations.jsonl"
    invoked_set: set[str] = set()
    if invocations_path.is_file():
        try:
            for line in invocations_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    skill = (entry.get("skill") or "").strip()
                    if skill:
                        invoked_set.add(skill)
                except (json.JSONDecodeError, AttributeError):
                    continue
        except OSError:
            pass

    reminded_set = set(reminded_all)
    not_invoked = sorted(reminded_set - invoked_set)
    invoked_list = sorted(invoked_set)

    surfaces: list[str] = []
    if ft:
        surfaces.append("frontend")
    if bt:
        surfaces.append("backend")

    write_count = _current_write_count(cid)

    record = {
        "ts":          _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "cid":         cid,
        "reminded":    reminded_all,
        "invoked":     invoked_list,
        "not_invoked": not_invoked,
        "surfaces":    surfaces,
        "write_count": write_count,
    }

    try:
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        effectiveness_path = telemetry_dir / "skill-effectiveness.jsonl"
        with effectiveness_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
    except OSError:
        pass  # Fail open — telemetry error must never block the stop hook


def _stop(payload: dict) -> dict:
    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        return {}

    # NOTE (P4-T9): the former `payload["status"]` gate is REMOVED — Claude Code's
    # Stop payload has no `status` field (verified root cause, Spec A §0), so the
    # gate always short-circuited here and the skill-effectiveness telemetry loop
    # never ran. Stop always proceeds now; the effectiveness record below is what
    # feeds the self-tuning weight updater.

    try:
        from documentation_lifecycle_hook import stop_followup_message as _doc_stop_followup
    except ImportError:
        _doc_stop_followup = None  # type: ignore[assignment,misc]

    life_msg = (
        (_doc_stop_followup(payload) or "").strip() if callable(_doc_stop_followup) else ""
    )

    verify_tail = _verification_close_followup_fragment()

    st = _load_state(cid)
    ft, bt = bool(st.get("frontend_touched")), bool(st.get("backend_touched"))

    # ── Telemetry: diff reminded vs invoked ───────────────────────────────────
    _write_effectiveness_record(cid, st, ft, bt)
    # ─────────────────────────────────────────────────────────────────────────

    stop_lines: list[str] | None = None

    quality_checks = "Quality: " + ", ".join(f"`{s}`" for s in QUALITY_SKILLS)
    ship_checks = "Ship: " + ", ".join(f"`{s}`" for s in SHIPPING_SKILLS)

    # ── Re-fire logic: replace boolean flag with write-count integer ──────────
    current_write_count = _current_write_count(cid)
    last_stop_wc = st.get("last_stop_write_count")
    REFILL_WRITES = 8  # re-fire stop reminder after 8 new writes

    if ft and bt:
        already_stopped = last_stop_wc is not None
        writes_since_last = (current_write_count - last_stop_wc) if already_stopped else 0
        if already_stopped and writes_since_last < REFILL_WRITES:
            _save_state(cid, st)
            return {}
        st["last_stop_write_count"] = current_write_count
        stop_lines = [
            "[Hook: pre-close — fullstack]",
            *_stop_skill_reminder_lines(True, True, st),
            quality_checks,
            ship_checks,
        ]
    elif ft:
        fe_last_wc = st.get("last_fe_stop_write_count")
        fe_already_stopped = fe_last_wc is not None
        fe_writes_since = (current_write_count - fe_last_wc) if fe_already_stopped else 0
        if fe_already_stopped and fe_writes_since < REFILL_WRITES:
            _save_state(cid, st)
            return {}
        st["last_fe_stop_write_count"] = current_write_count
        stop_lines = [
            "[Hook: pre-close — frontend]",
            *_stop_skill_reminder_lines(True, False, st),
            quality_checks,
            ship_checks,
        ]
    elif bt:
        be_last_wc = st.get("last_be_stop_write_count")
        be_already_stopped = be_last_wc is not None
        be_writes_since = (current_write_count - be_last_wc) if be_already_stopped else 0
        if be_already_stopped and be_writes_since < REFILL_WRITES:
            _save_state(cid, st)
            return {}
        st["last_be_stop_write_count"] = current_write_count
        stop_lines = [
            "[Hook: pre-close — backend]",
            *_stop_skill_reminder_lines(False, True, st),
            quality_checks,
            ship_checks,
        ]

    # Doc-only conversations: lifecycle marker merits Phase B nudge (+ same verification tail as FE/BE).
    if stop_lines is None:
        if not life_msg:
            return {}
        fragments = [life_msg]
        if verify_tail.strip():
            fragments.append(verify_tail.lstrip("\n"))
        _save_state(cid, st)
        return {"followup_message": "\n\n---\n\n".join(fragments)}

    msg = "\n".join(stop_lines)
    if verify_tail.strip():
        msg += "\n" + verify_tail.strip()
    if (
        (ft or bt)
        and st.get("engineering_skills_sent")
        and not st.get("engineering_stop_nudge_sent")
    ):
        st["engineering_stop_nudge_sent"] = True
        msg += (
            "\n\nEngineering: confirm `to-prd` / `to-issues` / `grill-with-docs` / `diagnose` if used this session."
        )

    if life_msg:
        msg += "\n\n---\n\n" + life_msg

    _save_state(cid, st)
    return {"followup_message": msg}


# ---------------------------------------------------------------------------
# BeforeSubmit — UserPromptSubmit surface detection + skill injection
# ---------------------------------------------------------------------------

# Keyword clusters for surface detection from prompt text
_PROMPT_FE_KEYWORDS = frozenset({
    "component", "tsx", "jsx", "react", "vite", "frontend", "client",
    "ui", "ux", "page", "hook", "store", "tailwind", "css", "html",
    "button", "modal", "form", "layout", "responsive", "design",
    "redux", "zustand", "context", "props", "state", "render",
    "next.js", "nextjs", "remix", "sveltekit", "vue", "angular",
})

_PROMPT_BE_KEYWORDS = frozenset({
    "service", "controller", "route", "endpoint", "api", "server",
    "database", "migration", "query", "sql", "backend", "go", "golang",
    "handler", "middleware", "auth", "jwt", "token", "session",
    "postgres", "mysql", "redis", "queue", "worker", "grpc",
    "fiber", "gin", "echo", "express", "fastify", "nest",
    "schema", "model", "repository", "usecase", "domain",
})

_PROMPT_IMPL_VERBS = frozenset({
    "implement", "build", "create", "add", "write", "make",
    "refactor", "fix", "update", "migrate", "integrate",
})


def _infer_surface_from_prompt(prompt: str) -> tuple[bool, bool]:
    """Return (is_fe, is_be) based on keyword presence in prompt."""
    words = set(re.findall(r"\b\w+\b", prompt.lower()))
    # Also check for compound patterns without word boundaries
    prompt_lower = prompt.lower()

    fe_score = len(words & _PROMPT_FE_KEYWORDS)
    be_score = len(words & _PROMPT_BE_KEYWORDS)

    # Boost scores for compound patterns
    if any(s in prompt_lower for s in ("next.js", "react query", "rtk query", "tanstack")):
        fe_score += 2
    if any(s in prompt_lower for s in ("rest api", "grpc", "graphql", "sqlc", "pgx")):
        be_score += 2

    # Require at least 1 impl verb + 1 surface keyword for a confident signal
    has_impl_verb = bool(words & _PROMPT_IMPL_VERBS)

    is_fe = fe_score >= 1 and (has_impl_verb or fe_score >= 2)
    is_be = be_score >= 1 and (has_impl_verb or be_score >= 2)

    return is_fe, is_be


def _before_submit(payload: dict) -> dict:
    """UserPromptSubmit handler — inject top-3 skills before any Write if not yet surfaced."""
    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        return {}

    st = _load_state(cid)

    # Skip if skills already surfaced by post-tool-use OR if before-submit already fired
    if (
        st.get("frontend_start_sent")
        or st.get("backend_start_sent")
        or st.get("fullstack_start_sent")
        or st.get("before_submit_sent")
    ):
        return {}

    # Extract prompt text
    prompt = str(
        payload.get("prompt")
        or payload.get("message")
        or payload.get("user_message")
        or ""
    )
    if not prompt.strip():
        return {}

    is_fe, is_be = _infer_surface_from_prompt(prompt)

    if not is_fe and not is_be:
        return {}  # Not enough signal — don't inject

    # Mark as sent (lighter flag — does NOT set frontend_start_sent)
    st["before_submit_sent"] = True
    _save_state(cid, st)

    lines: list[str] = ["[Hook: pre-submit mandatory skills — surfaced before first write]"]

    if is_fe and _SMART_ROUTER_AVAILABLE:
        # Use a synthetic FE path to get router-selected skills
        synthetic_path = "src/components/Feature.tsx"
        fe_skills = _select_skills(synthetic_path, "frontend", is_first_write=True)
        primary = [s["name"] for s in fe_skills if s.get("priority") != "CROSS-CUT"][:3]
        if primary:
            lines.append("FE (invoke before writing code):")
            lines.extend(_skill_line(n) for n in primary)
    elif is_fe:
        lines.append("FE (invoke before writing code):")
        for n in ["frontend-standards-always-follow", "project-reference-linkage", "architect-system-design"]:
            lines.append(_skill_line(n))

    if is_be and _SMART_ROUTER_AVAILABLE:
        synthetic_path = "internal/service/service.go"
        be_skills = _select_skills(synthetic_path, "backend", is_first_write=True)
        primary = [s["name"] for s in be_skills if s.get("priority") != "CROSS-CUT"][:3]
        if primary:
            lines.append("BE (invoke before writing code):")
            lines.extend(_skill_line(n) for n in primary)
    elif is_be:
        lines.append("BE (invoke before writing code):")
        for n in ["backend-standards-always-follow", "project-reference-linkage", "service-layer-standards"]:
            lines.append(_skill_line(n))

    if len(lines) <= 1:
        return {}  # Only the header line — nothing to inject

    return {"additionalContext": "\n".join(lines)}


def main() -> int:
    if len(sys.argv) < 2:
        return 0
    mode = sys.argv[1]
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0
    if mode == "post-tool-use":
        out = _post(payload)
        event_name = "PostToolUse"
    elif mode == "stop":
        out = _stop(payload)
        event_name = "Stop"
    elif mode == "before-submit":
        out = _before_submit(payload)
        event_name = "UserPromptSubmit"
    else:
        out = {}
        event_name = None

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
