#!/usr/bin/env python3
"""PreToolUse(Bash) hook: Block git commit when documentation hasn't been updated.

Scoped to the repo being committed (``git -C dir`` and ``cd dir &&`` honoured; the
command is tokenised, so ``git commit-tree`` and an ``--amend`` inside a ``-m``
message are not commits/amends — audit 2026-10-05 B1-10):

  * any repo with ``server_docs/`` or ``frontend_docs/`` at its root: the files going
    into the commit (staged, plus working-tree changes for ``-a`` or a same-line
    ``git add``) decide. Backend code (``server/``, ``backend/``, ``api/``) needs a
    ``server_docs/`` change, frontend code (``src/``, ``client/``, ...) a
    ``frontend_docs/`` change, and ``PROJECT_LINKAGES.md`` when the repo has one
    (``commit_docs_check.py``).
  * ``repo_markers`` repos (GO_UDP layout): the session state doc-update-enforcer.py
    writes, as before.

Committing ~/.claude after touching another repo is never blocked (A03-B12).

Before the docs rule, every commit (amends included) is scanned for secret material it would ADD
(PKG gates; ECC pre-bash-commit-quality + codex pre-commit): AWS / GitHub / Anthropic / OpenAI /
Slack / Google keys, private key headers and a staged `.env` deny (hard hits). Quoted credential
assignments whose value looks like a secret (no spaces, 16+ chars, two of letters / digits / symbols)
and staged `.env.*` files (not `.env.example`; Vite commits `.env.development`) are soft hits: they
ask interactively and deny when nobody can confirm (lib/gate_mode; REVIEW2 Fix 5). A placeholder
filter (EXAMPLE, REPLACE_ME, `<...>`, `${...}`, process.env) applies to both. Messages name
`file:line (kind)` only, never the value. Fail-open on any git error.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from commit_docs_check import _all_flag, _git, git_adds, git_commits, missing_docs, repo_root
from tool_compat import is_shell_tool, tool_name

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or SCRIPT_DIR / ".state")

GIT_COMMIT_RE = re.compile(r"\bgit\b.*\bcommit\b", re.DOTALL)

# Doc labels shown in the deny message — byte-identical GO_UDP defaults,
# overridable via doc-enforcement.config.json (P4-T4). Never raises.
_BE_LABEL, _FE_LABEL, _LINK_LABEL = "server_docs/", "frontend_docs/", "PROJECT_LINKAGES.md"
_REPO_MARKERS = ["/UDP_PLATFORM/", "/GO_UDP/"]
try:
    _cfg = json.loads((SCRIPT_DIR / "doc-enforcement.config.json").read_text(encoding="utf-8"))
    _BE_LABEL = _cfg.get("backend_doc_label", _BE_LABEL)
    _FE_LABEL = _cfg.get("frontend_doc_label", _FE_LABEL)
    _LINK_LABEL = _cfg.get("linkage_label", _LINK_LABEL)
    _REPO_MARKERS = list(_cfg.get("repo_markers", _REPO_MARKERS))
except Exception:  # noqa: BLE001
    pass


def _norm_dir(directory: str) -> str:
    """Resolved, "/"-separated, trailing slash (marker matching)."""
    try:
        directory = str(Path(os.path.expanduser(directory)).resolve())
    except Exception:
        pass
    return directory.replace("\\", "/") + "/"


def _in_marker_repo(directory: str) -> bool:
    return any(m in directory for m in _REPO_MARKERS)


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _state_path(cid: str) -> Path:
    return STATE_DIR / f"{_safe_cid(cid)}.doc-enforcer.json"


def _load_state(cid: str) -> dict | None:
    p = _state_path(cid)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _deny(reason: str) -> None:
    # PreToolUse requires the hookSpecificOutput wrapper (matches the working
    # dox-write-gate.py); the bare top-level form is recognized by no event and
    # silently fails open.
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


_PENDING_ASK = ""  # a soft secret hit's ask: printed instead of an allow, so a later deny still wins


def _allow() -> None:
    if _PENDING_ASK:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                 "permissionDecisionReason": _PENDING_ASK}}))
        return
    print("{}")


def _decide(payload) -> tuple:
    try:
        from lib import gate_mode
        return gate_mode.decide(payload, "ask")
    except Exception:  # noqa: BLE001 - gate_mode absent or broken: plain ask
        return "ask", "interactive"


# --- staged-secret scan (ECC pre-bash-commit-quality.js + codex-git-hooks/pre-commit) -------------------
_SECRET_PATTERNS = (
    ("AWS access key", re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED |PGP )?PRIVATE[ ]KEY")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI-style key", re.compile(r"(?<![\w-])sk-(?!ant-)[A-Za-z0-9]{20,}")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
)
_CRED = re.compile(r"(?i)\b(?:api[_-]?key|secret|password|passwd|token)\b\s*[:=]\s*['\"]([^'\"]{12,})['\"]")
_SOFT_KINDS = frozenset({"credential assignment", ".env.* file staged"})  # ask, never a silent deny
_SECRETISH = re.compile(r"^\S{16,}$")


def _looks_secret(val: str) -> bool:
    """No spaces, 16+ chars, two of letters / digits / symbols: UI text and short seeds are not secrets."""
    classes = (any(c.isalpha() for c in val), any(c.isdigit() for c in val), any(not c.isalnum() for c in val))
    return bool(_SECRETISH.match(val)) and sum(classes) >= 2
_PLACEHOLDER = re.compile(r"(?i)replace[_-]?me|change[_-]?me|your[_-]|example|sample|placeholder|dummy|fake"
                          r"|redacted|xxxx|<[^>]+>|\$\{|process\.env|os\.environ|\bTODO\b|\bTBD\b")
_SKIP_EXT = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".zip", ".gz", ".lock", ".woff", ".woff2",
                       ".ico", ".mp4"})
_SKIP_NAMES = frozenset({"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "Cargo.lock", "poetry.lock"})
_ENV_FILE = re.compile(r"^\.env(?:$|\.(?!example$|sample$|template$|test$|dist$))", re.IGNORECASE)
_HUNK = re.compile(r"\+(\d+)")
_MAX_LINES = 20000  # beyond this the diff is judged on its first 20k lines (fail-open on the rest)
_MAX_HITS = 10


_INTERACTIVE_ADD = {"-p", "--patch", "-i", "--interactive", "-e", "--edit"}


def _added_untracked(root: str, add_argvs: list) -> list:
    """Root-relative paths a same-command `git add` would add that are untracked now (SP-3). git does
    the pathspec logic: `add --dry-run` never touches the index. [] on any git error (fail-open)."""
    files: list = []
    for argv, directory in add_argvs[:5]:
        argv = [a for a in argv if a not in _INTERACTIVE_ADD]
        try:
            out = _git(directory or root, "add", "--dry-run", "--ignore-missing", *argv)
        except Exception:  # noqa: BLE001 - fail-open like the rest of the scan
            continue
        files += [ln[5:-1] for ln in out if ln.startswith("add '") and ln.endswith("'")]
    if not files:
        return []
    try:
        untracked = set(_git(root, "ls-files", "--others", "--exclude-standard"))
    except Exception:  # noqa: BLE001
        return []
    return [f for f in dict.fromkeys(files) if f in untracked][:200]


def _as_diff(root: str, rels: list) -> list:
    """Untracked files as added-only diff text (first 256 KB; binaries skipped)."""
    out: list = []
    for rel in rels:
        try:
            with open(Path(root) / rel, "rb") as fh:
                data = fh.read(262144)
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        out += [f"+++ b/{rel}", "@@ -0,0 +1 @@"]
        out += ["+" + ln for ln in data.decode("utf-8", "replace").splitlines() if ln.strip()]
    return out


def _staged_secret_hits(root: str, commit_args: list, add_seen: bool, add_argvs: list | None = None) -> list:
    """[('file:line', kind), ...] for secrets ADDED by this commit (staged; plus tracked working-tree changes
    for `-a` or a same-line `git add`, plus the untracked files that `git add` would add). Never the value.
    [] on any git error (fail-open)."""
    try:
        diff = _git(root, "diff", "--cached", "-U0", "--no-color", "--diff-filter=ACMR")
        if add_seen or _all_flag(commit_args):
            diff += _git(root, "diff", "-U0", "--no-color", "--diff-filter=ACMR")
    except Exception:  # noqa: BLE001 - OSError, timeout, undecodable output: nothing to check
        return []
    if add_seen and add_argvs:
        diff += _as_diff(root, _added_untracked(root, add_argvs))
    hits: list = []
    file, line_no, skip = "", 0, False
    for raw in diff[:_MAX_LINES]:
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            file = path[2:] if path.startswith("b/") else path
            base = file.rsplit("/", 1)[-1]
            skip = base in _SKIP_NAMES or os.path.splitext(base)[1].lower() in _SKIP_EXT
            if _ENV_FILE.match(base):  # `.env` is hard; `.env.development` etc. (Vite commits them) ask
                hits.append((file, ".env file staged" if base.lower() == ".env" else ".env.* file staged"))
                skip = True
            continue
        if raw.startswith("@@"):
            m = _HUNK.search(raw)
            line_no = int(m.group(1)) - 1 if m else 0
            continue
        if not raw.startswith("+") or skip:
            continue
        line_no += 1  # `_git` drops blank lines: a pointer ("about line"), exact for -U0 added text
        text = raw[1:]
        if _PLACEHOLDER.search(text):
            continue
        kind = next((k for k, rx in _SECRET_PATTERNS if rx.search(text)), None)
        if kind is None and any(_looks_secret(m.group(1)) for m in _CRED.finditer(text)):
            kind = "credential assignment"
        if kind:
            hits.append((f"{file}:{line_no}", kind))
        if len(hits) >= _MAX_HITS:
            break
    return hits[:_MAX_HITS]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        _allow()
        return 0

    if not is_shell_tool(tool_name(payload)):
        _allow()
        return 0

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not GIT_COMMIT_RE.search(command):
        _allow()  # cheap pre-filter; the tokenised parse below decides
        return 0

    global _PENDING_ASK
    base = str(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    commits, add_seen = git_commits(command, base)
    adds = git_adds(command, base) if add_seen else []
    # Staged-secret scan first, amends included: newly staged content is new content.
    soft: list = []
    for args, directory in commits:
        root = repo_root(directory)
        if not root:
            continue
        hits = _staged_secret_hits(root, args, add_seen, adds)
        listing = "\n".join(f"  - {where} ({kind})" for where, kind in hits)
        if any(kind not in _SOFT_KINDS for _, kind in hits):
            _deny("BLOCKED: this commit would add secret material (about line):\n\n" + listing
                  + "\n\nUnstage or scrub these lines (keep secrets in a gitignored .env or a secret store), then "
                  "commit again. A test fixture must be marked as such (EXAMPLE / placeholder) so the scanner "
                  "can tell.")
            return 0
        if hits:
            soft.append(listing)
    if soft:
        text = ("This commit adds credential-looking lines or an `.env.*` file (about line):\n\n" + "\n".join(soft)
                + "\n\nConfirm to commit if these are not secrets (UI text, a committed Vite `.env.development`); "
                "otherwise unstage them and keep the values in a gitignored .env or a secret store.")
        decision, why = _decide(payload)
        if decision != "ask":
            _deny(text + f"\n\nNo one can confirm in this {why} session: leave the commit for the user.")
            return 0
        _PENDING_ASK = text  # every allow below becomes this ask; a docs deny still wins
    # amends were committed once already; `--amend` must be a real argument (B1-10)
    commits = [(args, d) for args, d in commits if "--amend" not in args]
    if not commits:
        _allow()
        return 0

    for args, directory in commits:
        root = repo_root(directory)
        if root and not _in_marker_repo(root.replace("\\", "/") + "/"):
            missing = missing_docs(root, args, add_seen)
            if missing:
                _deny("BLOCKED: Cannot commit without documentation updates.\n\n"
                      f"Repo {root} keeps doc trees, and this commit changes code without them.\n"
                      "Missing documentation:\n" + "\n".join(missing)
                      + "\n\nUpdate and stage these before committing (rules/02-lifecycle.md Phase 7).")
                return 0

    # Marker repos (GO_UDP layout) keep the session-state check below.
    if not any(_in_marker_repo(_norm_dir(d)) for _, d in commits):
        _allow()
        return 0

    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        _allow()
        return 0

    state = _load_state(cid)
    if state is None:
        # No state tracked → no code files written this session → allow
        _allow()
        return 0

    be_touched = state.get("be_touched", False)
    fe_touched = state.get("fe_touched", False)
    be_docs_written = state.get("be_docs_written", False)
    fe_docs_written = state.get("fe_docs_written", False)
    linkages_written = state.get("linkages_written", False)
    code_files: list[str] = state.get("code_files", [])

    if not be_touched and not fe_touched:
        # No code surface touched → allow
        _allow()
        return 0

    missing: list[str] = []
    if be_touched and not be_docs_written:
        missing.append(f"- {_BE_LABEL} (backend code changed)")
    if fe_touched and not fe_docs_written:
        missing.append(f"- {_FE_LABEL} (frontend code changed)")
    if (be_touched or fe_touched) and not linkages_written:
        missing.append(f"- {_LINK_LABEL}")

    if not missing:
        _allow()
        return 0

    surfaces: list[str] = []
    if be_touched:
        be_count = sum(1 for f in code_files if "/server/" in f or ".go" in f)
        surfaces.append(f"backend ({be_count} file(s))")
    if fe_touched:
        fe_count = sum(1 for f in code_files if "/client/" in f or "/src/" in f)
        surfaces.append(f"frontend ({fe_count} file(s))")

    reason = (
        "BLOCKED: Cannot commit without documentation updates.\n\n"
        f"Code surfaces touched: {', '.join(surfaces)}\n"
        "Missing documentation:\n"
        + "\n".join(missing)
        + "\n\nUpdate these files before committing. "
        "Phase 7 (documentation update) is mandatory."
    )

    _deny(reason)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Fail open — never crash the hook and block all commits
        print("{}")
        raise SystemExit(0)
