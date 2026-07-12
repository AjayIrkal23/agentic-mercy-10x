#!/usr/bin/env python3
"""
UI/UX six-skill stack orchestrator for Cursor hooks.

Stack (precedence in ui-ux-playbook.mdc): Impeccable → Huashu-Design →
UI/UX Pro Max → Taste-Skill → Frontend UI Engineering → designlang.

Modes (argv[1]):
  before-submit   — stdin: beforeSubmitPrompt payload; stdout: JSON
  post-tool-use   — stdin: postToolUse payload; stdout: JSON

Injects phase checklist + skill paths (~600 tok), not full SKILL.md dumps.
See ~/.claude/rules/ui-ux-playbook.mdc for the full workflow.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
HOOK_DIR = SCRIPT_PATH.parent
CONFIG_PATH = HOOK_DIR / "ui-ux-stack-orchestrator.config.json"
PLAYBOOK_PATH = Path.home() / ".claude" / "rules" / "ui-ux-playbook.mdc"
STATE_DIR = HOOK_DIR / ".state"

SKILL_ROOT = Path.home() / ".claude" / "skills"
UIPMAX_SEARCH = SKILL_ROOT / "ui-ux-pro-max" / "scripts" / "search.py"
IMPECCABLE_CTX = SKILL_ROOT / "impeccable" / "scripts" / "load-context.mjs"
TASTE_DIALS_PATH = HOOK_DIR / ".state" / "taste-dials.json"
FRONTEND_DESIGN_SKILL = (
    Path.home() / ".claude" / "plugins" / "marketplaces"
    / "claude-plugins-official" / "plugins" / "frontend-design"
    / "skills" / "frontend-design" / "SKILL.md"
)

_URL_RE = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')


# Design quality gate constants (merged from design-quality-gate.py)
_GATE_UI_EXTENSIONS = frozenset([
    ".tsx", ".jsx", ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte", ".html", ".astro",
])
_GATE_LOGIC_PATTERNS = (
    "/api/", "/hooks/", "/store/", "/types/", "/lib/", "/utils/",
    ".test.tsx", ".spec.tsx",
)
_GATE_DESIGN_MARKERS = frozenset([
    "design_system_searched", "impeccable_context_loaded", "before_submit_full_sent",
])
_GATE_BLOCK_THRESHOLD = 3
_GATE_IMPECCABLE_LOAD_CMD = "node ~/.claude/skills/impeccable/scripts/load-context.mjs"
_GATE_TRIGGER_HINT = (
    "Trigger: mention 'design', 'ui', or 'component' in your next prompt to "
    "auto-load context, or manually run: " + _GATE_IMPECCABLE_LOAD_CMD
)
_GATE_BLOCK_MSG = (
    "BLOCKED: Design preflight not loaded. Before writing UI files the design "
    "stack must be consulted. " + _GATE_TRIGGER_HINT
)
_GATE_ADVISORY_MSG = (
    "[Design Gate] Advisory: design preflight was skipped. Consider running "
    "/impeccable audit before shipping."
)


def _gate_is_logic_path(file_path: str) -> bool:
    p = file_path.replace("\\", "/").lower()
    return any(pat.lower() in p for pat in _GATE_LOGIC_PATTERNS)


def _gate_is_ui_file(file_path: str) -> bool:
    p = file_path.lower()
    return any(p.endswith(ext) for ext in _GATE_UI_EXTENSIONS)


def _gate_design_context_present(state: dict) -> bool:
    return any(state.get(m) for m in _GATE_DESIGN_MARKERS)


def _load_config() -> dict:
    defaults: dict[str, Any] = {
        "enable_auto_design_system_search": False,
        "auto_search_project_name": "Session",
        "auto_search_query_max_len": 280,
        "ui_path_suffixes": [".tsx", ".jsx", ".css", ".scss", ".vue", ".svelte", ".html"],
        "ui_keywords": ["ui", "ux", "design", "layout", "tailwind", "component", "page"],
        "exclude_keywords": [],
    }
    if CONFIG_PATH.is_file():
        try:
            merged = {**defaults, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


def _flatten_strings(obj: Any, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_strings(v, out)


def _collect_search_text(payload: dict) -> str:
    parts: list[str] = []
    p = payload.get("prompt")
    if isinstance(p, str):
        parts.append(p)
    att = payload.get("attachments")
    if isinstance(att, list):
        for a in att:
            if not isinstance(a, dict):
                continue
            fp = a.get("file_path")
            if isinstance(fp, str):
                parts.append(fp)
    _flatten_strings(payload.get("tool_input") or {}, parts)
    return " \n ".join(parts).lower()


def _paths_from_tool_input(ti: object) -> list[str]:
    if not isinstance(ti, dict):
        return []
    out: list[str] = []
    for k in ("path", "file_path", "target_file", "file"):
        v = ti.get(k)
        if isinstance(v, str) and v.strip():
            out.append(v.strip().lower())
    return out


def _ui_path_hit(paths: list[str], suffixes: list[str]) -> bool:
    for p in paths:
        for suf in suffixes:
            s = suf.lower() if suf.startswith(".") else f".{suf.lower()}"
            if p.endswith(s):
                return True
    return False


def _keyword_in_text(t: str, kw: str) -> bool:
    k = kw.lower().strip()
    if not k:
        return False
    # Short tokens must be whole words (avoid "no ui" matching "ui").
    if len(k) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", t) is not None
    return k in t


def _ui_negative_context(t: str) -> bool:
    """User explicitly scopes out UI work."""
    if re.search(r"\bno\s+ui\b", t) or re.search(r"\bnot?\s+ui\b", t):
        return True
    if "without ui" in t or "non-ui" in t or "nonui" in t:
        return True
    return False


def _classify_ui(text: str, paths: list[str], cfg: dict) -> bool:
    t = text.lower()
    if _ui_negative_context(t):
        return False
    for neg in cfg.get("exclude_keywords") or []:
        if isinstance(neg, str) and neg.lower() in t:
            return False

    suffixes = cfg.get("ui_path_suffixes") or []
    if _ui_path_hit(paths, [str(x) for x in suffixes]):
        return True

    for kw in cfg.get("ui_keywords") or []:
        if isinstance(kw, str) and _keyword_in_text(t, kw):
            return True
    return False


def _state_path(conversation_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in conversation_id)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{safe}.uiux-stack.json"


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


def _sanitize_query(raw: str, max_len: int) -> str:
    s = re.sub(r"\s+", " ", raw).strip()
    s = re.sub(r"[`$]", "", s)[:max_len]
    return s if s else "modern product ui"


def _maybe_run_design_system_search(query: str, project: str, cfg: dict) -> str | None:
    if not cfg.get("enable_auto_design_system_search"):
        return None
    if not UIPMAX_SEARCH.is_file():
        return None
    q = _sanitize_query(query, int(cfg.get("auto_search_query_max_len") or 280))
    proj = str(cfg.get("auto_search_project_name") or "Session").strip() or "Session"
    try:
        r = subprocess.run(
            [
                sys.executable,
                str(UIPMAX_SEARCH),
                q,
                "--design-system",
                "-p",
                proj,
            ],
            capture_output=True,
            text=True,
            timeout=12,
        )
        block = (r.stdout or "").strip()
        if r.stderr:
            block += "\n\n# stderr\n" + r.stderr.strip()
        if r.returncode != 0:
            block = f"(search.py exit {r.returncode})\n{block}"
        return block
    except (subprocess.TimeoutExpired, OSError) as e:
        return f"(design system search failed: {e})"


def _maybe_run_impeccable_context(workspace_roots: list[str] | None = None) -> str | None:
    if not IMPECCABLE_CTX.is_file():
        return None
    cwd = os.environ.get("PROJECT_ROOT") or ""
    if not cwd and workspace_roots:
        for root in workspace_roots:
            if isinstance(root, str) and root.strip() and Path(root).is_dir():
                cwd = root
                break
    if not cwd:
        cwd = os.getcwd()
    try:
        r = subprocess.run(
            ["node", str(IMPECCABLE_CTX)],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=cwd,
        )
        if r.returncode == 0 and r.stdout.strip():
            out = r.stdout.strip()
            if len(out) > 4000:
                out = out[:4000] + "\n...(context capped at 4000 chars — read full via load-context.mjs)"
            return out
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None


def _load_taste_dials() -> str:
    defaults = "DESIGN_VARIANCE=8, MOTION_INTENSITY=6, VISUAL_DENSITY=4"
    try:
        if TASTE_DIALS_PATH.is_file():
            d = json.loads(TASTE_DIALS_PATH.read_text(encoding="utf-8"))
            dv = d.get("design_variance", 8)
            mi = d.get("motion_intensity", 6)
            vd = d.get("visual_density", 4)
            return f"DESIGN_VARIANCE={dv}, MOTION_INTENSITY={mi}, VISUAL_DENSITY={vd}"
    except (json.JSONDecodeError, OSError):
        pass
    return defaults


def _detect_urls(text: str) -> list[str]:
    return _URL_RE.findall(text)[:3]


def _checklist_block_full(extra_search: str | None, impeccable_ctx: str | None, detected_urls: list[str] | None) -> str:
    home = str(Path.home())
    dials = _load_taste_dials()
    lines = [
        "[UI/UX] Design work detected → DISPATCH the frontend-uiux-designer agent NOW "
        "(Agent tool, subagent_type \"frontend-uiux-designer\", description prefix "
        "\"[opus] \", model:\"opus\"). Do NOT design in this context — the six-skill "
        "stack (impeccable → huashu-design → ui-ux-pro-max → taste-skill → "
        "frontend-ui-engineering → frontend-design, + design-extract for reference "
        "URLs) is the AGENT's business, not the main loop's.",
        f"Give the agent a compact brief: the user's request, product truth, target "
        f"files/components, taste dials ({dials} — override in chat), and the "
        f"auto-loaded context below.",
        "**ASSETS — HIGGSFIELD MANDATORY:** every image/video/3D/audio asset is GENERATED via "
        "Higgsfield (`mcp__higgsfield__generate_image|generate_video|generate_3d|generate_audio`, "
        "skill `higgsfield-generate`) — NO placeholders, stock URLs, CSS-fake gradients, or emoji-icons. "
        f"Boundary + capability map: {home}/.claude/rules/higgsfield-frontend-mandate.md",
        f"Alternative the user can type: /invoke-design (full orchestrated flow). "
        f"FALLBACK — only if agent dispatch is unavailable — read the stack yourself in "
        f"playbook order: {PLAYBOOK_PATH}",
    ]
    if impeccable_ctx:
        lines.extend(["", "### Impeccable context (auto-loaded — include in the agent's brief)", impeccable_ctx])
    if extra_search:
        lines.extend(["", "### UI/UX Pro Max — design system (auto — include in the agent's brief)", extra_search])
    if detected_urls:
        url_list = ", ".join(f"`{u}`" for u in detected_urls[:2])
        lines.extend(["", f"[designlang] URL detected: {url_list}. Pass to the agent — it can run design-extract / `npx designlang <url>` for tokens before implementing."])
    return "\n".join(lines)


def _checklist_block_short() -> str:
    dials = _load_taste_dials()
    return (f"[UI/UX] Design work → dispatch frontend-uiux-designer (subagent_type "
            f"\"frontend-uiux-designer\", \"[opus] \" prefix, model:\"opus\") — it owns the "
            f"six-skill stack + HIGGSFIELD assets (generated, never placeholders/stock). "
            f"Dials: {dials}. Alternative: /invoke-design.")


def handle_before_submit(payload: dict, cfg: dict) -> dict:
    text = _collect_search_text(payload)
    paths: list[str] = []
    att = payload.get("attachments")
    if isinstance(att, list):
        for a in att:
            if isinstance(a, dict) and isinstance(a.get("file_path"), str):
                paths.append(a["file_path"].lower())

    if not _classify_ui(text, paths, cfg):
        return {"continue": True}

    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    st = _load_state(cid) if cid else {}

    if st.get("before_submit_full_sent"):
        ctx = _checklist_block_short()
    else:
        prompt_text = payload.get("prompt") if isinstance(payload.get("prompt"), str) else text

        extra = _maybe_run_design_system_search(
            prompt_text,
            str(cfg.get("auto_search_project_name") or "Session"),
            cfg,
        )
        if extra:
            st["design_system_searched"] = True

        impeccable_ctx = _maybe_run_impeccable_context(
            payload.get("workspace_roots") if isinstance(payload.get("workspace_roots"), list) else None
        )
        if impeccable_ctx:
            st["impeccable_context_loaded"] = True
            st["design_gate_product_context"] = "loaded" if "PRODUCT" in impeccable_ctx or "product" in impeccable_ctx.lower() else "check-product-md"

        detected_urls = _detect_urls(prompt_text)
        if detected_urls:
            st["designlang_hint_shown"] = True

        st["taste_dials_injected"] = True

        ctx = _checklist_block_full(extra, impeccable_ctx, detected_urls)
        st["before_submit_full_sent"] = True
        if cid:
            _save_state(cid, st)

    out: dict = {"continue": True, "additionalContext": ctx}
    return out


def handle_post_tool_use(payload: dict, cfg: dict) -> dict:
    """PostToolUse handler — merged from ui-ux-stack-orchestrator + design-quality-gate.

    Single handler owns the shared state file exclusively — eliminates read-modify-write
    race between the two previously separate hooks.
    """
    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        return {}

    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        return {}

    # Extract file path for gate check
    file_path = ""
    for key in ("file_path", "path", "target_file", "file"):
        v = ti.get(key)
        if isinstance(v, str) and v.strip():
            file_path = v.strip()
            break

    # Determine UI classification via both path and keyword signals
    paths = _paths_from_tool_input(ti)
    blob = json.dumps(ti).lower()
    suffixes = [str(x) for x in (cfg.get("ui_path_suffixes") or [])]
    path_hit = _ui_path_hit(paths, suffixes)
    keyword_hit = _classify_ui(blob, paths, cfg)
    is_ui_context = path_hit or keyword_hit

    # Gate check: independent of keyword detection — based on file extension only
    is_gate_candidate = (
        file_path
        and _gate_is_ui_file(file_path)
        and not _gate_is_logic_path(file_path)
    )

    if not is_ui_context and not is_gate_candidate:
        return {}

    # Single state read for this write event
    st = _load_state(cid)

    messages: list[str] = []

    # --- Orchestrator advisory (once per conversation) ---
    if is_ui_context and not st.get("post_ui_write_sent"):
        st["post_ui_write_sent"] = True
        messages.append(
            "[UI/UX] UI file written. Run: /impeccable audit → polish. "
            "Verify: huashu verify.py on HTML."
        )

    # --- Design quality gate (merged from design-quality-gate.py) ---
    if is_gate_candidate:
        count: int = int(st.get("ui_write_count") or 0) + 1
        st["ui_write_count"] = count

        if not _gate_design_context_present(st):
            if count <= _GATE_BLOCK_THRESHOLD:
                messages.append(_GATE_BLOCK_MSG)
            else:
                messages.append(_GATE_ADVISORY_MSG)
        # If design context present: pass through silently (no message added)

    # Single state write for this write event
    _save_state(cid, st)

    if not messages:
        return {}

    return {"additionalContext": "\n\n".join(messages)}


def main() -> int:
    if len(sys.argv) < 2:
        print("{}")
        return 0
    mode = sys.argv[1]
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0

    cfg = _load_config()

    if mode == "before-submit":
        out = handle_before_submit(payload if isinstance(payload, dict) else {}, cfg)
        event_name = "UserPromptSubmit"
    elif mode == "post-tool-use":
        out = handle_post_tool_use(payload if isinstance(payload, dict) else {}, cfg)
        event_name = "PostToolUse"
    else:
        out = {}
        event_name = None

    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
