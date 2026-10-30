"""hookify_rules.py — parse, load and evaluate repo-local hookify rules (ECC hookify runtime, Python port).

A rule is `<repo>/.claude/hookify.<name>.local.md`: YAML-subset frontmatter (name, enabled, event, action,
pattern | conditions, tool_matcher) and a markdown body that becomes the message. Rule files are
UNTRUSTED input (a cloned repo can carry them), so every limit is hard and every failure fails open
with a short diagnostic that never echoes the file's content:

- symlinked files, files over 64 KB and git-TRACKED files are refused (only the user's own untracked
  rules count); when git cannot say what is tracked, no rule loads; at most 100 files are read;
- patterns are capped at 400 chars and screened for backreferences, lookbehind, nested quantifiers,
  quantified alternation and `.*x.*` (Python's `re` has no timeout: this screen, the pattern cap, the
  64 KB field cap and the 1 s deadline checked between rules are the whole defence);
- parsed rules are cached per (path, mtime_ns, size) in state/hookify-cache/<repo>.json.

Stdlib only; never raises out of `load_rules` / `evaluate`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import time
from pathlib import Path

try:
    from lib import platform as plat
except Exception:  # noqa: BLE001
    plat = None  # type: ignore

MAX_RULES = 100
MAX_RULE_BYTES = 64 * 1024
MAX_PATTERN = 400
MAX_FIELD = 64 * 1024
MAX_EVAL_S = 1.0
MAX_MESSAGE = 2000
MAX_SHOWN = 5
MAX_KEYS = 16
MAX_CONDITIONS = 16
EVENTS = frozenset({"bash", "file", "prompt", "stop", "all"})
ACTIONS = frozenset({"warn", "block"})
OPERATORS = frozenset({"regex_match", "contains", "equals", "not_contains", "starts_with", "ends_with"})
FIELDS = {"bash": ("command",), "file": ("file_path", "new_text", "old_text", "content"),
          "prompt": ("user_prompt",), "stop": ("last_assistant_message",)}
_KNOWN_FIELDS = frozenset(f for fs in FIELDS.values() for f in fs) | {"tool_name"}
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
_KV = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(?:[ \t]+(.*))?$")

_UNSAFE = (re.compile(r"\\[1-9]"), re.compile(r"\(\?<[=!]"),                      # backrefs, lookbehind
           re.compile(r"\((?:[^()\\]|\\.)*(?:[*+]|\{\d+,?\d*\})(?:[^()\\]|\\.)*\)\s*(?:[*+]|\{\d+,?\d*\})"),  # (a+)+
           re.compile(r"\((?:[^()\\]|\\.)*\|(?:[^()\\]|\\.)*\)\s*(?:[*+]|\{\d+,?\d*\})"),                      # (a|b)+
           re.compile(r"(?:\.\*|\.\+)[^|)]{0,32}(?:\.\*|\.\+)"))                                                # .*x.*
_RX: dict = {}  # compiled patterns, per process only


def is_safe_regex(p) -> bool:
    if not isinstance(p, str) or not p or len(p) > MAX_PATTERN or any(rx.search(p) for rx in _UNSAFE):
        return False
    try:
        re.compile(p, re.IGNORECASE)
    except re.error:
        return False
    return True


def _rx(p: str):
    rx = _RX.get(p)
    if rx is None:
        rx = _RX[p] = re.compile(p, re.IGNORECASE)
    return rx


# --- frontmatter (ECC hookify-frontmatter subset) -----------------------------------------------------
def extract(text: str) -> tuple:
    """(yaml, body). Linear: a line scan for the closing `---`, no lazy regex over the file."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter")
    pos = 4
    while True:
        nl = text.find("\n", pos)
        line = text[pos:] if nl < 0 else text[pos:nl]
        if line.rstrip() == "---":
            return text[4:pos], ("" if nl < 0 else text[nl + 1:])
        if nl < 0:
            raise ValueError("unterminated frontmatter")
        pos = nl + 1


def _strip_comment(line: str) -> str:
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _scalar(val: str):
    v = val.strip()
    if v[:1] in ("[", "{"):
        raise ValueError("flow collections are unsupported")
    if v[:1] in ("|", ">"):
        raise ValueError("block scalars are unsupported in this port")
    if v.startswith('"'):
        try:
            out = json.loads(v)
        except ValueError:
            raise ValueError("malformed double-quoted string") from None
        if not isinstance(out, str):
            raise ValueError("malformed double-quoted string")
        return out
    if v.startswith("'"):
        if len(v) < 2 or not v.endswith("'"):
            raise ValueError("malformed single-quoted string")
        return v[1:-1].replace("''", "'")
    if v in ("true", "false"):
        return v == "true"
    return v


def _str_field(d: dict, key: str, required: bool = False):
    v = d.get(key)
    if v is None or v == "":
        if required:
            raise ValueError(f"missing {key}")
        return None
    if not isinstance(v, str):
        raise ValueError(f"{key} must be a string")
    return v


def parse_rule(text: str) -> dict:
    """The rule dict, or ValueError with a short reason (never the pattern text)."""
    yaml, body = extract(text)
    data: dict = {}
    conditions = None
    in_cond, cur = False, None
    for raw in yaml.split("\n"):
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        s = line.strip()
        if not line[0].isspace():
            m = _KV.match(s)
            if not m:
                raise ValueError("malformed frontmatter line")
            key, val = m.group(1), (m.group(2) or "")
            if key in data or (key == "conditions" and conditions is not None):
                raise ValueError(f"duplicate key {key}")
            if len(data) + (conditions is not None) >= MAX_KEYS:
                raise ValueError("too many keys")
            in_cond = key == "conditions"
            if in_cond:
                if val.strip():
                    raise ValueError("conditions must be a block list")
                conditions, cur = [], None
                continue
            data[key] = _scalar(val)
            continue
        if not in_cond:
            raise ValueError("unexpected indented line")
        if s.startswith("-"):
            if len(conditions) >= MAX_CONDITIONS:
                raise ValueError("too many conditions")
            cur = {}
            conditions.append(cur)
            s = s[1:].strip()
            if not s:
                continue
        m = _KV.match(s)
        if cur is None or not m or m.group(1) not in ("field", "operator", "pattern") or m.group(1) in cur:
            raise ValueError("malformed condition")
        cur[m.group(1)] = _scalar(m.group(2) or "")
    return _validate(data, conditions, body)


def _validate(data: dict, conditions, body: str) -> dict:
    name = _str_field(data, "name", required=True)
    if not _NAME.match(name):
        raise ValueError("name must be kebab-case, 1-100 chars")
    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be true or false")
    event = _str_field(data, "event") or "all"
    if event not in EVENTS:
        raise ValueError("event must be bash|file|prompt|stop|all")
    action = _str_field(data, "action") or "warn"
    if action not in ACTIONS:
        raise ValueError("action must be warn|block")
    tool_matcher = _str_field(data, "tool_matcher")
    if tool_matcher is not None and not is_safe_regex(tool_matcher):
        raise ValueError("tool_matcher is too long or unsafe")
    pattern = _str_field(data, "pattern")
    if (pattern is None) == (not conditions):
        raise ValueError("exactly one of pattern / conditions is required")
    if pattern is not None:
        if len(pattern) > MAX_PATTERN:
            raise ValueError(f"pattern exceeds {MAX_PATTERN} chars")
        if not is_safe_regex(pattern):
            raise ValueError("pattern is invalid or unsafe (backrefs, lookbehind, nested quantifiers, .*x.*)")
    for c in conditions or []:
        if set(c) != {"field", "operator", "pattern"} or not all(isinstance(c[k], str) for k in c):
            raise ValueError("a condition needs field, operator and pattern")
        if c["field"] not in _KNOWN_FIELDS:
            raise ValueError("unknown condition field")
        if c["operator"] not in OPERATORS:
            raise ValueError("unknown condition operator")
        if len(c["pattern"]) > MAX_PATTERN:
            raise ValueError(f"condition pattern exceeds {MAX_PATTERN} chars")
        if c["operator"] == "regex_match" and not is_safe_regex(c["pattern"]):
            raise ValueError("condition pattern is invalid or unsafe")
    return {"name": name, "enabled": enabled, "event": event, "action": action, "pattern": pattern,
            "conditions": list(conditions or []), "tool_matcher": tool_matcher, "message": body.strip()}


# --- loading ------------------------------------------------------------------------------------------
def rules_dir(root) -> Path:
    return Path(root) / ".claude"


def candidates(root) -> list:
    return sorted(rules_dir(root).glob("hookify.*.local.md"))  # not recursive


def _tracked_paths(root):
    git = shutil.which("git")
    if not git:
        return None
    kw = plat.no_window_kwargs() if plat is not None else {}
    try:
        out = subprocess.run([git, "-C", str(root), "ls-files", "-z", "--", ".claude/"],
                             capture_output=True, timeout=2, **kw)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return {p.replace("\\", "/") for p in out.stdout.decode("utf-8", "replace").split("\0") if p}


def _cache_path(root) -> Path | None:
    if plat is None:
        return None
    return plat.state_dir() / "hookify-cache" / f"{plat.slugify_path(os.path.abspath(str(root)))}.json"


def _read_cache(path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def load_rules(root, *, now=None) -> tuple:
    """(rules, diagnostics). Refuses symlinks, > 64 KB, git-tracked files; caps at 100; caches parsed rules
    per (path, mtime_ns, size) in state/hookify-cache/<repo_key>.json. Any failure -> ([], [why])."""
    try:
        if os.path.islink(str(rules_dir(root))):
            return [], ["rules dir is a symlink: refused"]
        files = candidates(root)
    except OSError:
        return [], []
    if not files:
        return [], []
    tracked = _tracked_paths(root)
    if tracked is None:
        return [], ["tracking unknown: rules disabled"]
    cpath = _cache_path(root)
    cache = _read_cache(cpath) if cpath else {}
    new_cache: dict = {}
    rules: list = []
    diags: list = [f"{len(files) - MAX_RULES} rule files over the {MAX_RULES} cap ignored"] if len(files) > MAX_RULES else []
    for path in files[:MAX_RULES]:
        name = path.name
        try:
            st = os.lstat(str(path))
        except OSError:
            diags.append(f"{name}: unreadable")
            continue
        if stat.S_ISLNK(st.st_mode):
            diags.append(f"{name}: symlink refused")
            continue
        if not stat.S_ISREG(st.st_mode):
            diags.append(f"{name}: not a regular file")
            continue
        if st.st_size > MAX_RULE_BYTES:
            diags.append(f"{name}: oversize (> {MAX_RULE_BYTES // 1024} KB) refused")
            continue
        if f".claude/{name}" in tracked:
            diags.append(f"{name}: tracked by git, refused (only untracked local rules count)")
            continue
        key = str(path)
        ent = cache.get(key)
        if (isinstance(ent, dict) and ent.get("m") == st.st_mtime_ns and ent.get("s") == st.st_size
                and isinstance(ent.get("rule"), dict)):
            rule = ent["rule"]
        else:
            try:
                rule = parse_rule(path.read_text(encoding="utf-8", errors="replace"))
            except ValueError as e:
                diags.append(f"{name}: {str(e)[:120]}")
                continue
            except OSError:
                diags.append(f"{name}: unreadable")
                continue
        new_cache[key] = {"m": st.st_mtime_ns, "s": st.st_size, "rule": rule}
        rules.append(rule)
    if cpath and new_cache != cache:
        try:
            plat.atomic_write(cpath, json.dumps(new_cache))
        except Exception:  # noqa: BLE001
            pass
    return rules, diags


# --- evaluation ---------------------------------------------------------------------------------------
def _tool(payload) -> str:
    return str(payload.get("tool_name") or payload.get("tool") or "")


def event_alias(payload):
    """'bash' | 'file' | 'prompt' | 'stop' | None."""
    ev = str(payload.get("hook_event_name") or "")
    if ev == "UserPromptSubmit":
        return "prompt"
    if ev == "Stop":
        return "stop"
    if ev == "PreToolUse":
        try:
            from tool_compat import is_shell_tool, is_write_tool
        except Exception:  # noqa: BLE001
            return None
        tool = _tool(payload)
        if is_shell_tool(tool):
            return "bash"
        if is_write_tool(tool) or tool == "NotebookEdit":
            return "file"
    return None


def _clip(v) -> str:
    if v is None:
        return ""
    return (v if isinstance(v, str) else str(v))[:MAX_FIELD]


def field_values(alias, payload) -> dict:
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    tool = _tool(payload)
    if alias == "bash":
        return {"command": _clip(ti.get("command")), "tool_name": tool}
    if alias == "file":
        new = ti.get("new_string") or ti.get("content") or ti.get("new_source")
        if new is None and isinstance(ti.get("edits"), list):
            new = "\n".join(str(e.get("new_string") or "") for e in ti["edits"] if isinstance(e, dict))
        return {"file_path": _clip(str(ti.get("file_path") or ti.get("notebook_path") or "").replace("\\", "/")),
                "new_text": _clip(new), "old_text": _clip(ti.get("old_string")), "content": _clip(ti.get("content")),
                "tool_name": tool}
    if alias == "prompt":
        return {"user_prompt": _clip(payload.get("prompt"))}
    if alias == "stop":
        return {"last_assistant_message": _clip(payload.get("last_assistant_message"))}
    return {}


def _cond_holds(c: dict, values: dict) -> bool:
    v, p, op = values.get(c["field"], ""), c["pattern"], c["operator"]
    if op == "regex_match":
        return bool(_rx(p).search(v))
    if op == "contains":
        return p in v
    if op == "not_contains":
        return p not in v
    if op == "equals":
        return v == p
    if op == "starts_with":
        return v.startswith(p)
    return v.endswith(p)  # ends_with


def evaluate(rules, alias, payload, *, deadline) -> tuple:
    """(matched rules, diagnostics); stops (fail-open) once time.monotonic() reaches `deadline`."""
    values = field_values(alias, payload)
    tool = values.get("tool_name", "")
    texts = [v for k, v in values.items() if k != "tool_name"]
    matched, diags = [], []
    for rule in rules:
        if time.monotonic() >= deadline:
            diags.append(f"deadline: {rule.get('name')} not evaluated")
            continue
        if not rule.get("enabled", True) or rule.get("event") not in (alias, "all"):
            continue
        try:
            tm = rule.get("tool_matcher")
            if tm and not _rx(tm).fullmatch(tool):
                continue
            if rule.get("pattern"):
                hit = any(_rx(rule["pattern"]).search(t) for t in texts)
            else:
                hit = all(_cond_holds(c, values) for c in rule.get("conditions") or [])
        except (re.error, KeyError, TypeError, AttributeError):
            diags.append(f"{rule.get('name')}: not evaluated (bad rule)")
            continue
        if hit:
            matched.append(rule)
    return matched, diags


__all__ = ["MAX_RULES", "MAX_RULE_BYTES", "MAX_PATTERN", "MAX_FIELD", "MAX_EVAL_S", "MAX_MESSAGE", "MAX_SHOWN",
           "EVENTS", "ACTIONS", "OPERATORS", "FIELDS", "is_safe_regex", "extract", "parse_rule", "rules_dir",
           "candidates", "load_rules", "event_alias", "field_values", "evaluate"]
