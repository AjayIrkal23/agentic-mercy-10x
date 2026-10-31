#!/usr/bin/env python3
"""dangerous-bash-gate.py — PreToolUse hook on Bash and PowerShell.

Detects and blocks destructive shell commands before they execute.
Hard-blocks on first detection. Second attempt within same conversation is allowed
(logged as an intentional override — the model has been forced to acknowledge danger).

Patterns blocked:
  - rm -rf  (anywhere; suppressed only when every rm -rf segment targets temp paths)
  - payloads of `bash|sh -c '…'`, `eval '…'` and quoted SQL/JS given to a DB client
    (psql, mysql, sqlite3, mongosh, …) are scanned too
  - MongoDB dropDatabase() / db.<coll>.drop(); dd of=/dev/…; mkfs; curl|wget … | sh
  - rm --no-preserve-root (root filesystem destruction)
  - rm $VAR / rm ${VAR} (shell variable expansion bypass)
  - git push --force / git push -f
  - git reset --hard
  - DROP TABLE, DROP DATABASE, TRUNCATE TABLE (case-insensitive)
  - kubectl delete ns / namespace
  - aws s3 rm --recursive
  - chmod -R 777
  - find <path> -delete
  - Windows: Remove-Item/ri/del -Recurse, rd|rmdir|del /s, del /q on a drive root or bare
    wildcard (all suppressed when every target is under a temp dir; targets are split on
    whitespace AND commas), Format-Volume, Clear-Disk, `format X:`; git clean -f (not when THAT
    command has -n / --dry-run); also inside `cmd /c`, `powershell -c`, `iex`
  - PowerShell tool only: `rm|rd|rmdir -r` (Remove-Item aliases; Bash `rm -r` stays ungated)
  - Natural Windows spellings (`gate_win.py`): backtick line continuation, `git.exe` / a quoted path to
    git, `<producer> | Remove-Item` pipelines (any flags, unless the producer lists only temp paths),
    `[IO.Directory]::Delete(...)`, Git Bash's `cmd //c rd //s //q`
  - Every matcher is linear in the command length: a gate that times out decides nothing
  - Heredoc / here-string bodies fed to a shell, `ssh`, `eval`/`source` or a DB client are scanned
    (P9 issue 1); a heredoc into `cat` / `tee` / an interpreter stays a file write (bash-write-gate)
  - git hook bypass (`--no-verify`, commit `-n` clusters, `-c core.hooksPath|include.path`,
    `GIT_CONFIG_*` env, `HUSKY=0` / `SKIP=` before a commit/push (also exported or assigned earlier in
    the same command line, and a quoted `HUSKY="0"`), a persistent
    `git config core.hooksPath` to /dev/null, "" or a missing absolute dir): denied on EVERY attempt,
    the retry override never applies. A relative hooksPath (`.githooks`) passes. Known misses: an
    option value between a wrapper and git (`sudo -u user git commit -n`); deleting `.git/hooks/*`
    (a visible tree change, and the workbench secret scan still runs)
  - force push spellings: bundled `-fu`, `+refspec`; the backup/wip suppressor judges each segment
  - dev-server / long-running service start (`npm run dev`, `vite`, `uvicorn`, `pm2 start`, ...):
    ASK, not deny (CLAUDE.md §5), downgraded through lib/gate_mode to a once-per-command advisory
    when nobody can answer; skipped while the mercy mod's guard is live for this session
  - every deny / override-allow / ask / downgrade writes a telemetry row (dispatch logs no gate verdict)

Python 3.8+ stdlib only. Exit 0 always. Exception → stderr, exit 0 (never crash session).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
from bisect import bisect_left
from pathlib import Path

# ---------------------------------------------------------------------------
# State directory (shared with other hooks)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or SCRIPT_DIR / ".state")
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import gate_win  # noqa: E402
from tool_compat import is_shell_tool  # noqa: E402


# ---------------------------------------------------------------------------
# Destructive command pattern registry
# Each entry: (compiled_regex, human_name, safe_suppression_fn | None)
# safe_suppression_fn(command) -> bool: return True to SKIP the block
# ---------------------------------------------------------------------------

# LINEAR matching (SEC1-01): dispatch treats a gate timeout (5 s) as "no decision", so a regex that
# is quadratic on a padded command switches the gate off. The lazy `head[^;|&]*?tail` shape restarted
# its scan at every head word (32 KB of `del ` = 8 s), as did `[a-z]*r[a-z]*f` on `rm -rrrr…` (59 s at
# 50 KB). `_SegMatch` finds the LEFTMOST head in a segment and looks for the tail once after it (a tail
# behind a later head is behind the first one too); `_RmRf` judges the two words after each `rm`.
_SEG_END = re.compile(r"[\n;|&]")
_NL = re.compile(r"\n")


class _SegMatch:
    """`.search(text)`: some (head, tail) pair matches inside ONE segment, in O(len(text))."""

    def __init__(self, *pairs: tuple[str, str], split=_SEG_END):
        self.pairs = pairs
        self._rx = [(h if hasattr(h, "search") else re.compile(h, re.IGNORECASE), re.compile(t, re.IGNORECASE))
                    for h, t in pairs]  # a head may be a ready matcher (`_GitSub`)
        self._split = split

    def search(self, text: str):
        for seg in self._split.split(text):
            for head, tail in self._rx:
                m = head.search(seg)
                hit = tail.search(seg, m.end()) if m else None
                if hit:
                    return hit
        return None


class _RmRf:
    """`.search(text)`: an `rm -rf` in any spelling (-rf -fr -rfv -vfr, -r -f, -f -r, --recursive
    --force). The first word after `rm` is a flag cluster (`-` + letters only) holding r and f, or
    one of two separate flags; the second word may only START like a flag (same as the old regex)."""

    _HEAD = re.compile(r"\brm\s+(?=(\S+)(?:\s+(\S+))?)", re.IGNORECASE)  # lookahead: heads never overlap
    _FLAGS = re.compile(r"-[a-z]*")

    @staticmethod
    def _starts_with(word: str, letter: str) -> bool:
        return bool(re.match(rf"-[a-z]*{letter}", word))

    def search(self, text: str):
        for m in self._HEAD.finditer(text):
            a, b = m.group(1).lower(), (m.group(2) or "").lower()
            if self._FLAGS.fullmatch(a) and (
                    ("r" in a and "f" in a) or ("f" in a and self._starts_with(b, "r"))
                    or ("r" in a and self._starts_with(b, "f"))):
                return m
            if (a == "--recursive" and b.startswith("--force")) or (a == "--force" and b.startswith("--recursive")):
                return m
        return None


class _DbDrop:
    """`.search(text)`: `dropDatabase(` or Mongo's `db.<coll>.drop()` (`\\bdb\\.\\S*\\.drop\\s*\\(\\s*\\)`), in
    O(len(text)). The one regex retried its `\\S*` from every `db.` (50 KB of `db.` = 3.5 s); only the
    FIRST `db.` of a whitespace-free token counts (its `\\S*` reaches every `.drop` behind it) and every
    `.drop(` is located once, then looked up by bisect."""

    _DROPDB = re.compile(r"\bdropDatabase\s*\(", re.IGNORECASE)
    _HEAD = re.compile(r"\bdb\.", re.IGNORECASE)
    _DROP = re.compile(r"\.drop\s*\(\s*\)", re.IGNORECASE)
    _TOKEN = re.compile(r"\S+")

    def search(self, text: str):
        hit = self._DROPDB.search(text)
        if hit:
            return hit
        drops = [m.start() for m in self._DROP.finditer(text)]
        if not drops:
            return None
        for tok in self._TOKEN.finditer(text):
            head = self._HEAD.search(text, tok.start(), tok.end())
            if head:
                k = bisect_left(drops, head.end())
                if k < len(drops) and drops[k] < tok.end():
                    return head
        return None


class _RmVar:
    """`.search(text)`: `rm $VAR` or `rm ${…}` (`\\brm\\s+(?:\\$\\w+|\\$\\{[^}]+\\})`) in O(len(text)): the
    `[^}]+\\}` part succeeds iff a `}` follows the `${` and is not its very next char, so the last `}` is
    found once instead of rescanning to the end from every `rm ${`."""

    _HEAD = re.compile(r"\brm\s+(?:\$\w+|\$\{(?=[^}]))", re.IGNORECASE)

    def search(self, text: str):
        last = text.rfind("}")
        for m in self._HEAD.finditer(text):
            if not m.group().endswith("{") or last >= m.end():
                return m
        return None


_RMRF_RE = _RmRf()
_RM_VAR = _RmVar()
_SAFE_RM_PREFIXES = ("/tmp/", "/var/tmp/", "$TMPDIR", "${TMPDIR}", "$(mktemp")
_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\n|\|")
_REDIRECT_RE = re.compile(r"(?<!\d)\d*&?>>?\s*&?\S+|<\s*\S+")  # (?<!\d): one try per digit run, not per digit


# `R=/tmp/x` / `export R='/tmp/x'` / `R=$(mktemp -d)` as a whole segment (a `R=x cmd` prefix does not
# count: bash expands `$R` in that command before the prefix applies).
_ASSIGN_SEG = re.compile(r"(?:(?:export|declare|local|readonly)\s+)?([A-Za-z_]\w*)="
                         r"(\"[^\"\n]*\"|'[^'\n]*'|\$\(mktemp[^)\n]*\)|[^\s'\"]*)")
_VAR_REF = re.compile(r"\$\{(\w+)\}|\$(\w+)")
_SEPS = re.compile(r"(&&|\|\||\||;|\n)")
_FIRST_RM = re.compile(r"(?:^|[;&|\n(])\s*(?:sudo\s+)?(rm)\b")  # rm at a command position only


def _literal_vars(cmd: str) -> dict:
    """This command's own `NAME=value` statements that surely run before the first `rm`: assigned
    once, before that `rm`, with no `&&` / `||` / `|` ahead of the assignment, and the bare name
    nowhere else (`unset R`, `for R in`, `read R`, `R+=`, `R[0]=`, `local R` ...). The value must be a
    plain path (no `$`, backtick, glob or `..`; `$(mktemp …)` allowed). Anything else stays unknown
    and is never expanded (santa review 2026-10-31: order, control flow and reassignment)."""
    rm = _FIRST_RM.search(cmd)
    parts = _SEPS.split(cmd[: rm.start(1)] if rm else cmd)
    seen: dict = {}
    conditional = False
    for i, part in enumerate(parts):
        if i % 2:  # a separator
            conditional = conditional or part in ("&&", "||", "|")
            continue
        m = _ASSIGN_SEG.fullmatch(part.strip())
        if not m:
            continue
        name, val = m.group(1), m.group(2).strip("'\"")
        bare = len(re.findall(rf"(?<![\w${{]){re.escape(name)}(?!\w)", cmd))
        plain = val.startswith("$(mktemp") or not any(c in val for c in "$`*?[")
        ok = plain and ".." not in val and not conditional and bare == 1 and name not in seen
        seen[name] = val if ok else None
    return {k: v for k, v in seen.items() if v}


def _rm_is_safe(cmd: str, matcher=None) -> bool:
    """Suppress the rm -rf block only when EVERY rm -rf segment deletes nothing but
    temp paths (test scaffolding). Judged per segment and per argument, so
    `rm -rf /tmp/x && rm -rf ~/src` or `rm -rf /tmp/../etc` is not safe. `$R` / `${R}` resolve
    through the command's own literal `R=/tmp/...` statements (`_literal_vars`)."""
    matcher = matcher or _RMRF_RE
    env = _literal_vars(cmd)
    for seg in _SEGMENT_SPLIT.split(cmd):
        if not matcher.search(seg):
            continue
        seg = _REDIRECT_RE.sub(" ", seg)  # `2>/dev/null`, `>/dev/null 2>&1` are not targets
        m = re.search(r"\brm\b(.*)", seg)
        args = [a.strip("'\"") for a in (m.group(1).split() if m else []) if not a.startswith("-")]
        args = [_VAR_REF.sub(lambda v: env.get(v.group(1) or v.group(2), v.group(0)), a) for a in args]
        if not args or not all(a.startswith(_SAFE_RM_PREFIXES) and ".." not in a for a in args):
            return False
    return True


def _rm_var_is_safe(cmd: str) -> bool:
    """`rm $R` passes only when it sits in a segment and every target resolves to a temp path."""
    return any(_RM_VAR.search(s) for s in _SEGMENT_SPLIT.split(cmd)) and _rm_is_safe(cmd, _RM_VAR)


_SAFE_PUSH_REFS = ("backup/", "archive/", "bak/", "wip/")


def _git_push_force_is_safe(cmd: str) -> bool:
    """Suppress only when EVERY force-push segment names a backup/archive/bak/wip ref among its own
    non-flag words (audit 07 issue 3: `git push --force origin main && ls wip/` used to pass)."""
    seen = False
    for seg in _GIT_SEG.split(cmd):
        if not _GIT_PUSH_RE.search(seg):
            continue
        seen = True
        m = _GIT_PUSH_HEAD.search(seg)
        words = [w.strip("'\"") for w in seg[m.end():].split()] if m else []
        if not any(r in w for w in words if not w.startswith("-") for r in _SAFE_PUSH_REFS):
            return False
    return seen


# Windows / PowerShell deletes. Names count only at a command position, so `grep -ri x -r .`
# is not `ri`. Same target judgement as rm -rf: suppressed only when every target is temp.
_CMDPOS = r"(?<![\w./\\-])"
_R_FLAG = r"\s-r(?:ecurse|ecurs|ecur|ecu|ec|e)?(?![\w-])"  # -r .. -Recurse (PowerShell abbreviations)
_WIN_DELETE_RE = _SegMatch(
    (_CMDPOS + r"(?:remove-item|ri|del|erase)(?![\w./-])", _R_FLAG),
    (_CMDPOS + r"(?:rm|rd|rmdir)(?![\w./-])", r"\s-recurse(?![\w-])"),
    (_CMDPOS + r"(?:rd|rmdir|del|erase)(?![\w./-])", r"\s//?s(?![\w/\\.-])"),  # `//s`: Git Bash's cmd //c
)
# SANTA1-04: in the PowerShell tool rm / rd / rmdir ARE Remove-Item, so `-r` is `-Recurse`. Only at a
# real command position (segment start, or after `{` / `(`): `git rm -r --cached x` is git, not an alias.
_PS_DELETE_RE = _SegMatch(*_WIN_DELETE_RE.pairs, (r"(?:^|[{(\"'])\s*(?:rm|rd|rmdir)(?![\w./-])", _R_FLAG))
_DEL_Q_RE = _SegMatch((_CMDPOS + r"(?:del|erase)(?![\w./-])", r"\s//?q(?![\w/\\.-])"))
_WIN_WORD_RE = re.compile(_CMDPOS + r"(?:remove-item|ri|del|erase|rm|rd|rmdir)(?![\w./-])(.*)", re.IGNORECASE)
_WIN_TEMP = tuple(p.lower() for p in _SAFE_RM_PREFIXES) + (
    "$env:temp/", "$env:tmp/", "$env:tmpdir/", "${env:temp}/", "${env:tmp}/", "%temp%/", "%tmp%/")


def _win_args(seg: str) -> list[str]:
    """Targets of a delete segment: not -Flags, not cmd's one-letter /s /q. A PowerShell array
    (`$env:TEMP\\a,D:\\proj`, quoted or not) is several targets: split on whitespace AND commas."""
    m = _WIN_WORD_RE.search(_REDIRECT_RE.sub(" ", seg))
    text = (m.group(1) if m else "").replace('"', "").replace("'", "")
    return [a for a in re.split(r"[\s,]+", text)
            if a and not a.startswith("-") and not re.fullmatch(r"//?[A-Za-z]", a)]


def _all_temp(args: list[str]) -> bool:
    """Every (lower-cased, `/`-separated) target is under a temp dir; no target at all is not safe."""
    return bool(args) and all((a.startswith(_WIN_TEMP) or "/appdata/local/temp/" in a) and ".." not in a
                              for a in args)


def _win_delete_is_safe(cmd: str, rx=_WIN_DELETE_RE) -> bool:
    for seg in _SEGMENT_SPLIT.split(cmd):
        if rx.search(seg) and not _all_temp([a.replace("\\", "/").lower() for a in _win_args(seg)]):
            return False
    return True


def _ps_delete_is_safe(cmd: str) -> bool:
    return _win_delete_is_safe(cmd, _PS_DELETE_RE)


def _pipe_delete_is_safe(cmd: str) -> bool:
    """`<producer> | Remove-Item` is fine only when the producer (first stage) lists nothing but temp paths."""
    for stmt in gate_win.STATEMENT_SPLIT.split(cmd):
        if gate_win.PIPE_DELETE_PS.search(stmt) and not _all_temp(gate_win.pipeline_producer_args(stmt)):
            return False
    return True


def _dotnet_delete_is_safe(cmd: str) -> bool:
    hits = [m.group(1).strip().replace("\\", "/").lower() for m in gate_win.DOTNET_FIRST_ARG.finditer(cmd)]
    return _all_temp(hits)


def _del_q_is_narrow(cmd: str) -> bool:
    """`del /q` is a bulk delete only on a drive root or a bare wildcard (`*`, `*.*`, `X:\\*`)."""
    for seg in _SEGMENT_SPLIT.split(cmd):
        if _DEL_Q_RE.search(seg) and any(
                re.fullmatch(r"(?:[a-z]:)?(?:\.?/)?\*(?:\.\*)?|[a-z]:|", a.replace("\\", "/").lower().rstrip("/"))
                for a in _win_args(seg)):
            return False
    return True


class _GitSub:
    """`.search(text)`: `git` plus any global options (`-C <dir>`, `-c k=v`, `--git-dir <x>`, `--no-pager`,
    `--work-tree=<x>`) plus a subcommand matching ``sub``, so `git -C repo reset --hard` is still caught.
    Linear (SANTA1C-01): an option's argument never starts with `-` (`-C -C -C` is three plain flags, not
    `-C` eating `-C`: Fibonacci parses in the old nested regex), the options are walked token by token
    with no backtracking across tokens, and the next `git` is looked for past the options a failed start
    consumed (`git -C git -C git …` restarted the walk at every `git`: 98 s at 110 KB)."""

    _START = re.compile(r"\bgit(?:\.exe)?\s+", re.IGNORECASE)
    _OPT = re.compile(r"(?:-[Cc]\s+(?!-)\S+|--(?:git-dir|work-tree|namespace|config-env)\s+(?!-)\S+"
                      r"|--?\w[\w.-]*(?:=\S+)?)\s+")

    def __init__(self, sub: str):
        self._sub = re.compile(sub, re.IGNORECASE)

    def search(self, text: str, pos: int = 0):
        while True:
            m = self._START.search(text, pos)
            if not m:
                return None
            pos = m.end()
            while True:
                o = self._OPT.match(text, pos)
                if not o:
                    break
                pos = o.end()
            hit = self._sub.match(text, pos)
            if hit:
                return hit
# `git clean` judged per command segment (a lone `&` splits too, `2>&1` does not): the dry-run flag
# must be among THAT segment's own flags, not `git log -n 5` or `grep -rn` further down the line.
_GIT_SEG = re.compile(r"&&|\|\||;|\n|\||(?<!>)&(?!>)")
_GIT_CLEAN_HEAD = _GitSub(r"clean(?![\w-])")
# `-(?=[a-zA-Z]*f)[a-zA-Z]+` = `-[a-zA-Z]*f[a-zA-Z]*` here (the trailing guard makes the letter run whole),
# without the two-star backtracking: one 20 KB `-ffff…x-` word took 2.7 s (PKG gates)
_GIT_FORCE = r"(?<=\s)(?:-(?=[a-zA-Z]*f)[a-zA-Z]+|--force)(?![\w-])"
_GIT_CLEAN_RE = _SegMatch((_GIT_CLEAN_HEAD, _GIT_FORCE), split=_GIT_SEG)
_DRY_FLAG = re.compile(r"-[a-zA-Z]*n[a-zA-Z]*|--dry-run")
_GIT_PUSH_HEAD = _GitSub(r"push(?![\w-])")
# audit 07 issue 3: a bundled `-fu` and a `+refspec` force too; `--force-with-lease` / `--force-if-includes`
# stay out (after the first `-` comes `-`, not a letter)
# `-(?=[a-zA-Z]*f)[a-zA-Z]+(?![\w-])` decides exactly like `-[a-zA-Z]*f[a-zA-Z]*(?![\w-])` (the letter run
# must be whole either way) without the two-star backtracking that is quadratic on one long `-ffff…x` word
_GIT_PUSH_RE = _SegMatch((_GIT_PUSH_HEAD, r"(?<=\s)(?:--force(?![-\w])|-(?=[a-zA-Z]*f)[a-zA-Z]+(?![\w-])"
                                          r"|\+[\w./-]+(?::[\w./-]*)?)"), split=_GIT_SEG)


def _git_clean_is_dry(cmd: str) -> bool:
    """True when EVERY forced `git clean` in the command carries -n / --dry-run (before any `--`)."""
    head, force = _GIT_CLEAN_HEAD, re.compile(_GIT_FORCE, re.IGNORECASE)
    for seg in _GIT_SEG.split(cmd):
        m = head.search(seg)
        if not m or not force.search(seg, m.end()):
            continue
        for tok in seg[m.end():].split():
            tok = tok.strip("'\"")
            if tok == "--":
                return False
            if _DRY_FLAG.fullmatch(tok):
                break
        else:
            return False
    return True


# --- git hook bypass: a token walk per segment over shlex output (linear; no regex over the segment) ---
_GIT_HOOK_KEYS = re.compile(r"^(?:core\.hookspath|include\.path|includeif\..*\.path)$")  # keys are lower-cased
_GIT_PROTECTED = frozenset({"commit", "push", "merge", "cherry-pick", "rebase", "am", "revert"})
_GIT_GLOBAL_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env",
                                    "--exec-path"})
_COMMIT_VALUE_LETTERS = frozenset("mFCct")        # -mn is a message "n"; scanning stops here
_COMMIT_OPTIONAL_VALUE_LETTERS = frozenset("uS")   # -uno is --untracked-files=no
_GIT_ENV = re.compile(r"^GIT_CONFIG_(?:COUNT|PARAMETERS|KEY_\d+|VALUE_\d+)=")
_ASSIGN = re.compile(r"^[A-Za-z_]\w*=")
_WRAPPERS = frozenset({"env", "sudo", "command", "exec", "nohup", "time", "nice"})
# husky off / pre-commit's skip list; `HUSKY=` is a quoted value after quote stripping (`HUSKY="0"`): judged a switch
_HOOK_SWITCH_ENV = re.compile(r"^(?:HUSKY=0?|SKIP=\S*)$")
_EXPORTERS = frozenset({"export", "declare", "typeset"})
_CONFIG_SCOPE_FLAGS = frozenset({"--local", "--global", "--system", "--worktree", "--add", "--replace-all"})


def _has_files(d: str) -> bool:
    """A real hook dir: exists and is not empty (fail-closed False on any error)."""
    try:
        return os.path.isdir(d) and any(os.scandir(d))
    except OSError:
        return False


_GIT_BYPASS_NAME = "git hook bypass (--no-verify / -n / core.hooksPath / GIT_CONFIG_*)"
_NO_OVERRIDE = frozenset({_GIT_BYPASS_NAME})


def _tokens(seg: str) -> list:
    try:
        return shlex.split(seg.replace("\\", "/"), posix=True)  # values are never inspected: `\` -> `/` is safe
    except ValueError:
        return seg.split()


def _prog(tok: str) -> str:
    """`/usr/bin/git.exe` -> `git` (no str.removesuffix: Python 3.8)."""
    p = os.path.basename(tok).lower()
    for suf in (".exe", ".cmd"):
        if p.endswith(suf):
            p = p[:-len(suf)]
    return p


def _noverify_flag(tok: str, sub: str) -> bool:
    if tok.startswith("--"):
        return len(tok) >= 6 and "--no-verify".startswith(tok)   # git accepts any unambiguous prefix
    if sub != "commit" or not tok.startswith("-") or len(tok) < 2:
        return False
    for ch in tok[1:]:                                           # -an, -sn, -qn: clusters
        if ch == "n":
            return True
        if ch in _COMMIT_VALUE_LETTERS or ch in _COMMIT_OPTIONAL_VALUE_LETTERS:
            return False
    return False


class _Hit:
    """Truthy match stand-in carrying what the deny text names."""

    def __init__(self, why: str, sub: str = ""):
        self.why, self.sub = why, sub


class _GitBypass:
    """`.search(text)`: a git command that bypasses the repo's hooks, judged per segment over shlex
    tokens. Runs on the quote-stripped text, so `-m "… --no-verify"` is gone before the walk."""

    def search(self, text: str):
        armed = False  # `export HUSKY=0` / a bare `HUSKY=0` earlier in the line reaches a later git (REVERIFY R4)
        for seg in _GIT_SEG.split(text):
            if not armed and ("HUSKY=" in seg or "SKIP=" in seg):
                pre = _tokens(seg)
                if pre and (pre[0].lower() in _EXPORTERS or all(_ASSIGN.match(t) for t in pre)):
                    armed = any(_HOOK_SWITCH_ENV.match(t) for t in pre)
            if "git" not in seg.lower():                          # cheap pre-filter (GIT_CONFIG_ contains it)
                continue
            toks = _tokens(seg)
            env_hit, switch, i = False, False, 0
            while i < len(toks) and (_ASSIGN.match(toks[i]) or toks[i].lower() in _WRAPPERS
                                     or (i and toks[i - 1].lower() in ("sudo", "env") and toks[i].startswith("-"))):
                env_hit = env_hit or bool(_GIT_ENV.match(toks[i]))
                switch = switch or bool(_HOOK_SWITCH_ENV.match(toks[i]))
                i += 1
            if toks[:1] and toks[0].lower() == "export" and any(_GIT_ENV.match(t) for t in toks[1:]):
                return _Hit("GIT_CONFIG_* export")
            if i >= len(toks) or _prog(toks[i]) != "git":
                continue
            if env_hit:
                return _Hit("GIT_CONFIG_* override")
            i += 1
            while i < len(toks) and toks[i].startswith("-"):     # global options
                opt, _, val = toks[i].partition("=")
                if opt in ("-c", "--config-env"):              # --config-env=<key>=<ENVVAR> sets a key too
                    kv = val if val else (toks[i + 1] if i + 1 < len(toks) else "")
                    if _GIT_HOOK_KEYS.match(kv.split("=", 1)[0].lower()):
                        return _Hit("core.hooksPath / include.path override")
                    i += 1 if val else 2
                elif opt in _GIT_GLOBAL_WITH_VALUE and not val:
                    i += 2
                else:
                    i += 1
            sub = toks[i].lower() if i < len(toks) else ""
            if sub == "config":  # a persistent core.hooksPath to nowhere switches every hook off (SP-6)
                rest = [t for t in toks[i + 1:] if t not in _CONFIG_SCOPE_FLAGS]
                if len(rest) >= 2 and rest[0].lower() == "core.hookspath":
                    val = rest[1]  # a quoted value reads as "" after quote stripping: judged empty
                    if val in ("", "/dev/null", "NUL", "nul") or (os.path.isabs(val) and not _has_files(val)):
                        return _Hit("core.hooksPath set to an empty or missing hook dir", "config")
                continue
            if sub not in _GIT_PROTECTED:
                continue
            if switch or armed:  # husky / pre-commit read these to skip every hook
                return _Hit("HUSKY=0 / SKIP= hook switch", sub)
            for tok in toks[i + 1:]:
                if tok == "--":
                    break
                if _noverify_flag(tok, sub):
                    return _Hit("--no-verify", sub)
        return None


def _git_bypass_reason(hit) -> str:
    sub = getattr(hit, "sub", "") or "commit/push"
    return (f"BLOCKED: `git {sub}` bypasses the repo's git hooks (`--no-verify` / `-n` / `core.hooksPath` / "
            "`GIT_CONFIG_*`). Hooks are the user's policy; run the command without the bypass and fix what the "
            "hook reports, or ask the user to run it. This block does not lift on retry.")


_WIN_DELETE_NAME = "Remove-Item -Recurse / rd /s / del /s (recursive delete)"
_PIPE_DELETE_NAME = "pipeline into Remove-Item / del (deletes whatever the producer lists)"

DANGEROUS_PATTERNS: list[tuple[re.Pattern, str, object]] = [
    (
        _RMRF_RE,
        "rm -rf (recursive force delete)",
        _rm_is_safe,
    ),
    (
        # `--force(?![-\w])`: --force-with-lease / --force-if-includes refuse to
        # overwrite work the pusher has not seen; only a bare --force does (WP3)
        _GIT_PUSH_RE,
        "git push --force (overwrites remote history)",
        _git_push_force_is_safe,
    ),
    (
        _GitSub(r"reset\s+--hard\b"),
        "git reset --hard (discards uncommitted changes)",
        None,
    ),
    (
        _WIN_DELETE_RE,
        _WIN_DELETE_NAME,
        _win_delete_is_safe,
    ),
    (
        _DEL_Q_RE,
        "del /q on a drive root or wildcard (bulk delete)",
        _del_q_is_narrow,
    ),
    (
        re.compile(r"\b(?:Format-Volume|Clear-Disk)\b|(?:^|[;&|(]\s*)format(?:\.com)?\s+[A-Za-z]:", re.IGNORECASE),
        "Format-Volume / Clear-Disk / format (wipes a disk)",
        None,
    ),
    (
        _GIT_CLEAN_RE,
        "git clean -f (deletes untracked files)",
        _git_clean_is_dry,
    ),
    (_GitBypass(), _GIT_BYPASS_NAME, None),  # in _NO_OVERRIDE: denied on every attempt
    (
        re.compile(
            r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA|INDEX)\b",
            re.IGNORECASE,
        ),
        "SQL DROP statement (irreversible schema destruction)",
        None,
    ),
    (
        re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
        "TRUNCATE TABLE (deletes all rows, may not be transactional)",
        None,
    ),
    (
        re.compile(
            r"\bkubectl\s+delete\s+(?:ns|namespace)\b",
            re.IGNORECASE,
        ),
        "kubectl delete namespace (destroys all resources in namespace)",
        None,
    ),
    (
        _SegMatch((r"\baws\s+s3\s+(?:rm|delete)\b", r"--recursive"), split=_NL),
        "aws s3 rm --recursive (bulk S3 object deletion)",
        None,
    ),
    (
        re.compile(r"\bchmod\s+-R\s+777\b", re.IGNORECASE),
        "chmod -R 777 (world-writable recursive permission change)",
        None,
    ),
    (
        re.compile(
            r"\bfind\b.{0,80}\s-delete\b",
            re.IGNORECASE,
        ),
        "find -delete (recursive file deletion via find)",
        None,
    ),
    (
        _SegMatch((r"\brm\s+", r"--no-preserve-root\b"), split=_NL),
        "rm --no-preserve-root (root filesystem destruction)",
        None,  # no safe-suppression
    ),
    (
        _RM_VAR,
        "rm with shell variable expansion (potential bypass)",
        _rm_var_is_safe,
    ),
    (
        _DbDrop(),
        "MongoDB drop (irreversible collection/database destruction)",
        None,
    ),
    (
        _SegMatch((r"\bdd\b", r"\bof=/dev/(?!null\b|zero\b|stdout\b|stderr\b)")),
        "dd onto a device (overwrites a disk)",
        None,
    ),
    (
        # MULTILINE: a scanned heredoc / payload body starts on its own line (`bash <<EOF\nmkfs …`)
        re.compile(r"(?:^|[;&|(]\s*|\bsudo\s+)mkfs(?:\.\w+)?\b", re.IGNORECASE | re.MULTILINE),
        "mkfs (formats a filesystem)",
        None,
    ),
    (
        _SegMatch((r"\b(?:curl|wget)\b", r"\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b"), split=re.compile(r"[\n;&]")),
        "download piped to a shell (runs unreviewed remote code)",
        None,
    ),
    (gate_win.PIPE_DELETE, _PIPE_DELETE_NAME, _pipe_delete_is_safe),
    (gate_win.DOTNET_DELETE, ".NET recursive directory delete ([IO.Directory]::Delete)", _dotnet_delete_is_safe),
]
# Checked only for the PowerShell tool, after the table above; same name, so one override covers both.
_PS_ONLY_PATTERNS: list[tuple[object, str, object]] = [
    (_PS_DELETE_RE, _WIN_DELETE_NAME, _ps_delete_is_safe),
    (gate_win.PIPE_DELETE_PS, _PIPE_DELETE_NAME, _pipe_delete_is_safe),
]

# Quoted payloads that DO execute: `bash -c '…'`, `eval '…'`, SQL/JS handed to a DB
# client. Quote-stripping hid them; the head is matched on the stripped text so a
# commit message that merely mentions psql never qualifies.
_PAYLOAD_HEAD_RE = re.compile(  # standalone words only: not `eval-harness`, `db/mongo`
    # option walks capped at 16 tokens: unbounded, a flood of `-x=pwsh` restarted the walk at every
    # head word and went quadratic (SANTA2A-01); real launch lines carry a handful of options
    r"(?<![\w./-])(?:(?:ba|z|da|k)?sh\s+(?:-[a-zA-Z]+\s+){0,16}-c|(?:powershell|pwsh)(?:\.exe)?\s+(?:-\S+\s+){0,16}-c(?:ommand)?"
    r"|cmd(?:\.exe)?\s+(?:/\S+\s+){0,16}//?[ck]|iex|invoke-expression|eval|psql|mysql|mariadb|sqlite3|sqlcmd"
    # here-strings into a shell (`bash <<< '…'`, `bash -s <<< …`); tmux / screen run their quoted pane command
    r"|(?:ba|z|da|k)?sh\s*<<<|(?:ba|z|da|k)?sh\s+(?:-[a-zA-Z]+\s+){0,16}-s\b|tmux|screen"
    r"|clickhouse-client|mongosh|mongo)(?![\w./-])", re.IGNORECASE)

# Heredoc heads whose body is EXECUTED (P9 issue 1): a shell, ssh (runs on the remote), eval/source, a DB
# client. `cat`/`tee` heredocs are file writes (bash-write-gate's job); other interpreters are out of scope.
_HEREDOC_EXEC_RE = re.compile(
    r"(?<![\w./-])(?:(?:sudo\s+(?:-\S+\s+){0,4})?(?:(?:ba|z|da|k)?sh|ssh|eval|source)"
    r"|psql|mysql|mariadb|sqlite3|sqlcmd|clickhouse-client|mongosh|mongo)(?![\w./-])", re.IGNORECASE)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _state_path(cid: str) -> Path:
    return STATE_DIR / f"{_safe_cid(cid)}.dangerous-bash.json"


def _load_state(cid: str) -> dict:
    if not cid:
        return {"overridden_commands": []}
    p = _state_path(cid)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"overridden_commands": []}


def _save_state(cid: str, state: dict) -> None:
    if not cid:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state_path(cid).write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Detection + output
# ---------------------------------------------------------------------------

def _fingerprint(cmd: str, pattern_name: str) -> str:
    """Stable fingerprint of the FULL whitespace-normalised command + pattern name.

    The old 80-char prefix let `cd /long/path && rm -rf A` pre-authorise
    `cd /long/path && rm -rf B` (A03-B14). Only the identical command re-run
    matches now."""
    import hashlib
    norm = re.sub(r"\s+", " ", cmd.strip())
    return f"{pattern_name}::{hashlib.sha256(norm.encode('utf-8', 'replace')).hexdigest()[:24]}"


_HEREDOC_HEAD = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
_DQUOTE_RE = re.compile(r'"(?:\\.|[^"\\])*"')
_DQUOTE_OPEN = re.compile(r'"(?:\\.|[^"\\])*')  # same, without the closing quote: where a try gets stuck
_SQUOTE_RE = re.compile(r"'[^']*'")


def _heredoc_terminators(cmd: str) -> dict:
    """tag -> ([line start offsets], [line end offsets]) of every line that is just one word."""
    terms: dict = {}
    pos = 0
    for line in cmd.split("\n"):
        word = line.strip()
        if word and re.fullmatch(r"\w+", word):
            starts, ends = terms.setdefault(word, ([], []))
            starts.append(pos)
            ends.append(pos + len(line))
        pos += len(line) + 1
    return terms


def _heredoc_blocks(cmd: str):
    """Yield (head_start, head_line_end, body_end, block_end) for every TERMINATED `<<TAG` block, in
    order. Linear: terminator lines are indexed once and found by bisect (the lazy `.*?^TAG$` regex
    rescanned to the end for every unterminated `<<EOF`, 9 s on 50 KB of them)."""
    pos, nl, terms = 0, -1, None
    for m in _HEREDOC_HEAD.finditer(cmd):
        if m.start() < pos:
            continue
        if nl < m.end():
            nl = cmd.find("\n", m.end())
            if nl < 0:
                return
        terms = _heredoc_terminators(cmd) if terms is None else terms
        starts, ends = terms.get(m.group(2), ([], []))
        k = bisect_left(starts, nl + 1)
        if k < len(starts):
            yield m.start(), nl, starts[k], ends[k]
            pos = ends[k]


def _strip_heredocs(cmd: str) -> str:
    """Replace each `<<TAG` .. `TAG` block with a space. A head without a terminator line is left in place."""
    out: list[str] = []
    pos = 0
    for start, _nl, _body_end, end in _heredoc_blocks(cmd):
        out.append(cmd[pos:start])
        out.append(" ")
        pos = end
    return "".join(out) + cmd[pos:] if out else cmd


def _heredoc_bodies(cmd: str) -> list:
    """[(head_line, body)] for every terminated `<<TAG` block, in order (same walk as _strip_heredocs)."""
    out = []
    for start, nl, body_end, _end in _heredoc_blocks(cmd):
        line_start = cmd.rfind("\n", 0, start) + 1
        out.append((cmd[line_start:nl], cmd[nl + 1:body_end]))
    return out


def _dquoted(s: str):
    """Spans of the "…" strings in ``s``. Linear: when a `"` opens nothing, the next try starts past the
    point where that attempt got stuck (the end, or a backslash before a newline), because every `"`
    in between is an escaped one that gets stuck at the same place. `re.sub` retried each of them: 11 s
    on 50 KB of `\\"`."""
    i = 0
    while True:
        j = s.find('"', i)
        if j < 0:
            return
        m = _DQUOTE_RE.match(s, j)
        if m:
            yield m.span()
            i = m.end()
        else:
            i = _DQUOTE_OPEN.match(s, j).end() + 1


def _strip_quoted(cmd: str) -> str:
    """Remove heredoc bodies and single/double-quoted strings before matching, so
    `git commit -m "switch from rm -rf to trash"` or a heredoc that merely
    mentions `DROP TABLE` is not a destructive command."""
    try:
        s = _strip_heredocs(cmd)
        out, i = [], 0
        for a, b in _dquoted(s):
            out.append(s[i:a])
            out.append('""')
            i = b
        s = "".join(out) + s[i:]
        return _SQUOTE_RE.sub("''", s)
    except Exception:
        return cmd


# --- dev-server / long-running service start: ASK (Python twin of the mercy mod's guard.ts) ---
_PMS = frozenset({"npm", "pnpm", "yarn", "bun", "npx"})
_PM_VALUE_FLAGS = frozenset({"--prefix", "-C", "--dir", "--cwd", "--filter", "-F"})
_NPM_VALUE_FLAGS = frozenset({"-w", "--workspace"})
_SERVER_SCRIPT = re.compile(r"^(dev|start|serve|server|preview|develop|storybook)$|^(dev|start|serve)[:_-]")
_SERVER_TOOLS = frozenset({"vite", "next", "nuxt", "astro", "remix", "expo", "uvicorn", "gunicorn", "hypercorn",
                           "daphne", "nodemon", "ts-node-dev", "http-server", "live-server", "webpack-dev-server",
                           "json-server", "serve", "pm2", "flask", "air", "start-storybook"})
_SERVER_SUBCOMMANDS = {"next": {"dev", "start"}, "nuxt": {"dev", "start", "preview"}, "astro": {"dev", "preview"},
                       "remix": {"dev"}, "expo": {"start"}, "pm2": {"start", "restart", "reload"}, "flask": {"run"},
                       "vite": {"", "dev", "serve", "preview"}}   # "" = bare `vite`
_WRAP_SKIP = frozenset({"env", "sudo", "nohup", "exec", "command", "time", "nice", "npx", "pnpx", "bunx"})
_HELP_FLAGS = frozenset({"--help", "-h", "--version", "-v", "-V"})


def _dev_server_hit(cmd: str):
    """The segment text that starts a dev server / long-running service, or None. Runs on the
    quote-stripped scan, so `echo 'flask run'` never reaches it; a tmux/screen pane command is a quoted
    payload body appended to the scan, judged here as its own segment."""
    for seg in _GIT_SEG.split(cmd):
        toks = [t for t in _tokens(seg) if t]
        i = 0
        while i < len(toks) and (_ASSIGN.match(toks[i]) or toks[i].lower() in _WRAP_SKIP):
            i += 1
        if i < len(toks) and toks[i] == "timeout":          # `timeout 30 npm run dev` ends on its own
            try:
                if float(re.sub(r"[a-z]$", "", toks[i + 1])) <= 60:
                    continue
            except (IndexError, ValueError):
                pass
            i += 2
        if i >= len(toks):
            continue
        prog, rest = _prog(toks[i]), toks[i + 1:]
        if any(t in _HELP_FLAGS for t in rest):
            continue
        if prog in _PMS:
            j = 0
            while j < len(rest) and rest[j].startswith("-"):
                valued = rest[j] in _PM_VALUE_FLAGS or (prog == "npm" and rest[j] in _NPM_VALUE_FLAGS)
                j += 2 if (valued and "=" not in rest[j]) else 1
            args = rest[j:]
            script = args[1] if args[:1] and args[0] in ("run", "run-script") and len(args) > 1 else (
                args[0] if args else "")
            if args[:1] and args[0] in ("start", "restart"):
                script = "start"
            if _SERVER_SCRIPT.match(script):
                return seg.strip()
            continue
        if prog in ("python", "python3", "py") and "http.server" in rest:
            return seg.strip()
        if prog in _SERVER_TOOLS:
            subs = _SERVER_SUBCOMMANDS.get(prog)
            first = rest[0] if rest and not rest[0].startswith("-") else ""
            if subs is None or first in subs:
                return seg.strip()
    return None


def _mod_guard_live(sid: str, environ=None) -> bool:
    """The mercy mod's guard.ts answers dev-server starts in its own session while its beat is fresh
    (MERCY_MOD_OWNED naming any link proves the bridge is active)."""
    env = os.environ if environ is None else environ
    if not sid or env.get("MERCY_MOD_SESSION") != sid or not env.get("MERCY_MOD_OWNED", "").strip():
        return False
    try:
        age = time.time() - float(env.get("MERCY_MOD_BEAT", "0")) / 1000.0
    except ValueError:
        return False
    return 0 <= age <= 120


def _decide(payload) -> tuple:
    try:
        from lib import gate_mode
        return gate_mode.decide(payload, "ask")
    except Exception:  # noqa: BLE001 - oom-sentinel absent or broken: plain ask
        return "ask", "interactive"


def _once(sid: str, gate: str, key: str) -> bool:
    try:
        from lib import gate_mode
        return gate_mode.once_per_file(sid, gate, key)
    except Exception:  # noqa: BLE001
        return True


def _telemetry(**fields) -> None:
    """dispatch logs no gate verdict: this row is the only record (P9 issue 2). Never the full command."""
    try:
        from lib import hook_telemetry
        hook_telemetry.record("PreToolUse", "dangerous-bash-gate", **fields)
    except Exception:  # noqa: BLE001
        pass


def _emit_deny(pattern_name: str, cmd: str, hit=None) -> None:
    if pattern_name in _NO_OVERRIDE:
        reason = _git_bypass_reason(hit)
    else:
        reason = (
            f"DANGEROUS COMMAND BLOCKED: `{pattern_name}` detected.\n"
            f"Command: {cmd[:200]}\n\n"
            "This command is irreversible or high-risk. To proceed intentionally:\n"
            "  - Re-run the exact same command in this conversation (override accepted once).\n"
            "  - The second attempt will be allowed through and logged.\n\n"
            "If this was unintentional, choose a safer alternative."
        )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def _emit_allow_with_log(pattern_name: str, cmd: str) -> None:
    """Second attempt — allow but emit advisory context."""
    # Cannot emit additionalContext + permissionDecision in same response.
    # Just emit empty (allow) — the prior deny message already warned the model.
    print("{}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0

    try:
        tool = str(payload.get("tool_name") or payload.get("tool") or "")
        if not is_shell_tool(tool):
            print("{}")
            return 0

        ti = payload.get("tool_input") or {}
        cmd = str(ti.get("command") or "")
        if not cmd.strip():
            print("{}")
            return 0

        cid = str(payload.get("conversation_id") or payload.get("session_id") or "")
        state = _load_state(cid)
        overridden = set(state.get("overridden_commands") or [])

        norm = gate_win.normalise(cmd)  # a quoted path to git / powershell / cmd becomes the bare program
        scan = _strip_quoted(norm)
        # P9 issue 1: a heredoc body fed to a shell / ssh / DB client runs; re-add it (raw) to the scan
        exec_bodies = [body for head, body in _heredoc_bodies(norm) if _HEREDOC_EXEC_RE.search(_strip_quoted(head))]
        if exec_bodies:
            scan = scan + "\n" + "\n".join(exec_bodies)
        if _PAYLOAD_HEAD_RE.search(scan):
            bodies = [norm[a + 1:b - 1] for a, b in _dquoted(norm)] + [q[1:-1] for q in _SQUOTE_RE.findall(norm)]
            scan = scan + "\n" + "\n".join(bodies)
        # bash runs `git push \<nl> --force` (PowerShell: backtick-nl) as one line: the patterns and the
        # suppressors judge it that way
        ps = tool == "PowerShell"
        scan, joined = gate_win.join_lines(scan, ps), gate_win.join_lines(norm, ps)
        patterns = DANGEROUS_PATTERNS + (_PS_ONLY_PATTERNS if ps else [])
        head = re.sub(r"\s+", " ", norm).strip()[:80]

        def _never_lifts():
            """A no-override pattern anywhere on the line: the retry override of an earlier hit must not lift it."""
            for p, n, sup in patterns:
                if n in _NO_OVERRIDE:
                    h = p.search(scan)
                    if h and not (sup is not None and sup(joined)):
                        return n, h
            return None

        for pattern, name, suppress_fn in patterns:
            hit = pattern.search(scan)
            if not hit:
                continue

            # Check safe-suppression predicate
            if suppress_fn is not None and suppress_fn(joined):
                continue

            # Generate fingerprint for override tracking
            fp = _fingerprint(cmd, name)
            row = {"pattern": name, "fingerprint": fp, "head": head, "session": cid, "tool": tool}

            if fp in overridden and name not in _NO_OVERRIDE:
                nl = _never_lifts()
                if nl is not None:  # the line also bypasses git hooks: no override
                    _telemetry(decision="deny", **{**row, "pattern": nl[0]})
                    _emit_deny(nl[0], cmd, nl[1])
                    return 0
                # Second attempt — allow through, logged
                print(
                    f"[dangerous-bash-gate] Override accepted for '{name}': {cmd[:100]}",
                    file=sys.stderr,
                )
                _telemetry(decision="override_allow", **row)
                _emit_allow_with_log(name, cmd)
                return 0

            # First occurrence — block and record in state (git-bypass: block every time, record nothing)
            if name not in _NO_OVERRIDE:
                overridden.add(fp)
                state["overridden_commands"] = list(overridden)
                _save_state(cid, state)

            _telemetry(decision="deny", **row)
            _emit_deny(name, cmd, hit)
            return 0

        # No deny: a dev-server / long-running service start asks (skipped while the mod guard answers)
        hit = None if _mod_guard_live(cid) else _dev_server_hit(scan)
        if hit:
            decision, why = _decide(payload)
            reason = (f"`{hit[:90]}` starts a dev server or long-running service. The user runs apps themselves "
                      "(CLAUDE.md §5): verify with a build, the tests or a linter instead. Start it anyway?")
            fp = _fingerprint(cmd, "dev-server")
            row = {"pattern": "dev-server", "fingerprint": fp, "head": head, "session": cid, "tool": tool}
            if decision == "ask":
                _telemetry(decision="ask", **row)
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                         "permissionDecisionReason": reason}}))
                return 0
            if _once(cid, "dev-server", fp):
                _telemetry(decision="ask_downgraded", reason=why, **row)
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
                                  reason + f" (ask downgraded: {why}; unattended session, continuing)"}}))
                return 0

        # No dangerous pattern found
        print("{}")
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"[dangerous-bash-gate] Error: {exc}", file=sys.stderr)
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
