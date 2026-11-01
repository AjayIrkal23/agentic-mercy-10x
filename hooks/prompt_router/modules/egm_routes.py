"""egm_routes.py: the Elephant-Goldfish Model route (plugin ``egm@egm``).

EGM is a design-document workflow (fresh-eyes review, brainstorm, draft, drift report). Its skills
are ``disable-model-invocation``: the Skill tool refuses them and the skills index marks them hidden,
so the ranked skill list can never push them. This module adds a dedicated ROUTING line instead that
names the SKILL.md to Read and the resolved plugin root (``${CLAUDE_PLUGIN_ROOT}`` is only substituted
when a skill is invoked). Config: ``router.config.json`` ``additions.egm``. Santa Method stays the
reviewer of code diffs. Pure stdlib; never raises; the plugin absent or disabled adds nothing.
"""
from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[2]

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    _plat = None

# an entrypoint that names a remote / app / IDE client: its owner is present although the harness
# reports CLAUDE_CODE_SESSION_ATTENDED=0


def norm_path(p: str) -> str:
    return str(p).replace("\\", "/")


def _claude_dir() -> Path:
    try:
        if _plat is not None:
            return Path(_plat.claude_dir())
    except Exception:  # noqa: BLE001
        pass
    return _HOOKS.parent


def _json(path: Path) -> dict:
    import json  # noqa: PLC0415
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=4)
def plugin_root(pid: str) -> str:
    """Install root of plugin ``pid`` ("" when disabled, missing or without a ``skills`` dir). The seam
    tests monkeypatch."""
    try:
        base = _claude_dir()
        enabled = (_json(base / "settings.json").get("enabledPlugins")
                   or _json(base / "settings.template.json").get("enabledPlugins") or {})
        if enabled.get(pid) is not True:
            return ""
        entries = (_json(base / "plugins" / "installed_plugins.json").get("plugins") or {}).get(pid) or []
        entries = sorted((e for e in entries if isinstance(e, dict)), key=lambda e: e.get("scope") != "user")
        for e in entries:
            root = norm_path(e.get("installPath") or "")
            if root and Path(root).joinpath("skills").is_dir():
                return root
    except Exception:  # noqa: BLE001
        pass
    return ""


def skill_md(root: str, name: str) -> str | None:
    """Absolute SKILL.md of ``name``: the dash name, else the underscore one (old tag v0.1.0)."""
    for n in (name, name.replace("-", "_")):
        p = f"{norm_path(root)}/skills/{n}/SKILL.md"
        if Path(p).is_file():
            return p
    return None


def _attended(payload: dict) -> bool:
    env = os.environ
    if env.get("CLAUDE_WORKBENCH_UNATTENDED") == "1":
        return False
    # CLAUDE_CODE_SESSION_ATTENDED=0 alone is not "nobody there": the owner's remote/app sessions run
    # with it (entrypoint sdk-cli) while present (2026-10-31, same rule as settings-protection-gate).
    # Subagents, workflow scripts and restored sessions are still unattended through gate_mode.
    try:
        from lib import gate_mode as _gm  # noqa: PLC0415
        return _gm.decide(payload)[0] == "ask"
    except Exception:  # noqa: BLE001 - unsure: attended
        return True


def _rx(cfg: dict, key: str) -> re.Pattern | None:
    try:
        return re.compile(str(cfg[key]), re.IGNORECASE) if cfg.get(key) else None
    except re.error:
        return None


def _doc_target(prompt: str, paths, doc_path: re.Pattern | None) -> str:
    m = doc_path.search(prompt) if doc_path else None
    if m:
        return m.group(0)
    return next((p for p in paths or [] if str(p).endswith(".md")), "")


def pick(profile, prompt: str, cfg: dict, attended: bool) -> tuple[str, str] | None:
    """(skill, review-target) or None."""
    text = profile.text or prompt.lower()
    explicit = _rx(cfg, "explicit_rx")
    explicit = bool(explicit and explicit.search(prompt))
    question = _rx(cfg, "question_rx")
    if question and question.search(prompt.strip()):
        return None  # a question about EGM is not a request to run it
    if not explicit:
        if set(cfg.get("skip_intents") or []) & set(profile.intents):
            return None
        if profile.size == "S":
            return None
        skip = _rx(cfg, "skip_rx")
        if skip and skip.search(text):
            return None
    doc_noun, doc_path = _rx(cfg, "doc_noun_rx"), _rx(cfg, "doc_path_rx")
    target = _doc_target(prompt, profile.paths, doc_path)
    doc = bool(target or (doc_noun and doc_noun.search(text)))
    code_noun = _rx(cfg, "code_noun_rx")
    for r in cfg.get("routes") or []:
        if not isinstance(r, dict) or not r.get("skill"):
            continue
        if r.get("attended_only") and not attended:
            continue
        if r.get("needs") == "doc" and not doc:
            continue
        if r.get("no_ui") and profile.is_ui:
            continue
        if r.get("no_code_noun") and code_noun and code_noun.search(text):
            continue
        rx = _rx(r, "rx")
        hit = bool(rx and rx.search(text))
        inf = r.get("infer") or {}
        if not hit and inf:
            hit = max((profile.intent_score(c) for c in inf.get("intents_any") or []), default=0) \
                >= int(inf.get("min_score", 2))
        if hit:
            return str(r["skill"]), target
    if explicit:
        if doc:
            return "egm-review", target
        if attended:
            return "egm-brainstorm", ""
    return None


def items(profile, ctx: dict) -> list[dict]:
    """0 or 1 ROUTING item; sets ``ctx["_egm"]`` so the router drops Santa/WORKFLOW/act lines."""
    try:
        cfg = ((ctx.get("config") or {}).get("additions") or {}).get("egm") or {}
        if not cfg:
            return []
        from prompt_router import policy as _policy  # noqa: PLC0415
        if _policy.infra_routing(profile):
            return []
        payload = ctx.get("payload") or {}
        prompt = str(payload.get("prompt") or "")
        attended = _attended(payload)
        got = pick(profile, prompt, cfg, attended)
        if not got:
            return []
        skill, target = got
        root = plugin_root(str(cfg.get("plugin") or "egm@egm"))
        md = skill_md(root, skill) if root else None
        if not md:
            return []
        repo = ctx.get("repo")
        where = str(getattr(repo, "root", "") or payload.get("cwd") or "")
        # design docs belong to a project: a session in $HOME would put EGM's artifacts in ~/.claude/egm
        if not where or os.path.realpath(where) == os.path.realpath(os.path.expanduser("~")):
            return []
        base = norm_path(where)
        art = f"{base.rstrip('/')}/{str(cfg.get('artifact_dir') or '.claude/egm').strip('/')}"
        text_cfg = cfg.get("text") or {}
        text = str(text_cfg.get(skill) or "").format(md=md, root=norm_path(root), art=art)
        if not text:
            return []
        if skill == "egm-review" and not attended:
            text += str(text_cfg.get("unattended_review") or "")
        salt = hashlib.sha256(target.encode("utf-8")).hexdigest()[:8] if target else "any"  # dedup id only
        ctx["_egm"] = {"skill": skill}
        return [{"id": f"route:egm:{skill}:{salt}", "tier": 2, "section": "ROUTING", "text": text}]
    except Exception:  # noqa: BLE001
        return []


__all__ = ["items", "pick", "plugin_root", "skill_md", "norm_path"]
