#!/usr/bin/env python3
"""split_machines_file.py — keep the imported machines file short (docs/merge/machines-split.md).

Moves the long tail of each bullet unit of the private, gitignored per-machine file
(imported by CLAUDE.md §10) into a journal beside it that is never imported, lifts the
standing-directive sentences back into the imported part, and appends a pointer line and a
3-line production-safety block. Idempotent; `--undo` restores the exact bytes. Never writes
into a git tree where the new files would be committable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent  # scripts/
ROOT = HERE.parent
if str(ROOT / "hooks") not in sys.path:
    sys.path.insert(0, str(ROOT / "hooks"))
try:
    from lib import platform as plat  # claude_dir, replace_file, no_window_kwargs
except Exception:  # noqa: BLE001 — replica without hooks/lib on path
    plat = None

MACHINES_NAME = "CLAUDE.machines.local.md"
JOURNAL_NAME = "CLAUDE.machines.journal.local.md"
TERMS_NAME = "grep_gates.machine_terms.json"
DEFAULT_BUDGET, CHECK_LIMIT = 550, 5200  # plan §5 row: 1,300 tok = 5,200 ch (final-fix 7; 550 leaves room for the prod-safety block)
UNIT_RE = re.compile(r"^\s{0,2}- \*\*")
HEADER_RE = re.compile(r"^<!-- machines-split v1 journal=(\S+) -->$")
CUT_RE = re.compile(r"^<!-- machines-split:cut id=(\d+) lifted=(\d+) -->$")
TAIL_RE = re.compile(r'^<!-- machines-split:tail id=(\d+) unit="(.*)" -->$')
END_RE = re.compile(r"^<!-- machines-split:end id=(\d+) -->$")
POINTER_MARK = "<!-- machines-split:pointer -->"
PROD_MARK = "<!-- machines-split:prod-safety -->"
POINTER_TEXT = ("Journal (SiteSync/Coolify history, replica setup detail, runbooks): "
                f"`{JOURNAL_NAME}` beside this file, not imported; read it when a task names those hosts.")
PROD_LINES = (
    "**Production safety (standing order).** Never edit Contabo or GCP production, and never run a "
    "cutover or rollback, without my explicit word in that turn.",
    "The GCP VM is read-only: no restarts, no config edits; dumps stream to this PC only.",
    "Servers run IST (Asia/Kolkata); never change a server timezone.",
)
JOURNAL_TITLE = "# Machines journal (private — gitignored, NOT imported)"
_KEEP_FALLBACK = (
    "never ask me to run sudo", "NEVER let the laptop sleep", "Full performance always",
    "falls back to a local ollama", "Read-only unless the user asks",
    "without my explicit word", "GCP VM is read-only", "Servers run IST",
)
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# `hostname`, up to 16 non-word chars (a wrapped line is "\n" + indent + "`"), the backticked name
_HOST_RE = re.compile(r"hostname\W{0,16}`([A-Za-z0-9][A-Za-z0-9._-]{2,})`")
# 24-26 char lowercase ids (app uuids), bare or backticked; the filter wants a letter and a digit
_ID_RE = re.compile(r"(?<![A-Za-z0-9])([a-z0-9]{24,26})(?![A-Za-z0-9])")
# machine names (bare or backticked): one hyphenated token, the filter wants >= 3 letters, >= 2 digits;
# a neighbouring . : / @ _ = rejects versions, file names, model tags, URLs and env refs
_NAME_RE = re.compile(r"(?<![\w./:@-])([A-Za-z0-9][A-Za-z0-9-]{8,38}[A-Za-z0-9])(?![\w./:@=-])")
_NAME_SKIP_RE = re.compile(r"^(?:[0-9-]+|.*-(?:x64|x86|amd64|arm64)-\d+)$")  # dates/digits, package arch


def norm(s: str) -> str:
    return " ".join(s.replace("`", "").replace("*", "").split())


def table_cells(row: str) -> list[str]:
    """Split a Markdown table row on `|` outside backtick spans (keys hold ` || `)."""
    s = row.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") else s
    cells, cur, code = [], [], False
    for ch in s:
        if ch == "`":
            code = not code
        if ch == "|" and not code:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    cells.append("".join(cur).strip())
    return cells


def load_keys(directives: Path | None = None) -> tuple[str, ...]:
    """sentence_key of every docs/DIRECTIVES.md row whose source names `machines`."""
    path = directives if directives is not None else ROOT / "docs" / "DIRECTIVES.md"
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return _KEEP_FALLBACK
    keys: list[str] = []
    cols: list[str] | None = None
    for ln in lines:
        if not ln.lstrip().startswith("|"):
            if cols is not None:
                break
            continue
        cells = table_cells(ln)
        if cols is None:
            if "sentence_key" in cells and "source" in cells:
                cols = cells
            continue
        if set(ln.replace("|", "").strip()) <= {"-", ":", " "} or len(cells) != len(cols):
            continue
        row = dict(zip(cols, cells))
        if "machines" not in row.get("source", ""):
            continue
        for span in re.findall(r"`([^`]*)`", row.get("sentence_key", "")):
            for k in span.split(" || "):
                if k.strip() and k.strip() not in keys:
                    keys.append(k.strip())
    return tuple(keys) or _KEEP_FALLBACK


def _cut(unit: list[str], budget: int) -> tuple[list[str], list[str]]:
    total, c = 0, None
    for i, ln in enumerate(unit):
        total += len(ln) + 1
        if total >= budget:
            c = i + 1
            break
    if c is None:
        return unit, []
    # an earlier cut's lifted lines + marker form one block; never cut inside it
    for i, ln in enumerate(unit):
        m = CUT_RE.match(ln)
        if m and i - int(m.group(2)) <= c <= i:
            c = i + 1
    tail = unit[c:]
    if not any(ln.strip() for ln in tail):
        return unit, []
    return unit[:c], tail


def _lift(tail: list[str], keys, prev: str = "") -> tuple[int, list[str]]:
    idx: set[int] = set()
    for key in keys:
        nk = norm(key)
        if not nk:
            continue
        for i, ln in enumerate(tail):
            if nk in norm(ln):
                idx.add(i)
                if i > 0 and norm(ln).startswith(nk):  # keep the subject ("nothing ...") of a wrapped sentence
                    idx.add(i - 1)
            elif i + 1 < len(tail) and nk not in norm(tail[i + 1]) and nk in norm(ln + " " + tail[i + 1]):
                idx.update((i, i + 1))
        if tail and prev and nk not in norm(prev) and nk not in norm(tail[0]) and nk in norm(prev + " " + tail[0]):
            idx.add(0)
    lifted = [tail[i] for i in sorted(idx)]
    return len(lifted), lifted


def _title(first: str) -> str:
    m = re.search(r"\*\*(.+?)\*\*", first)
    return (m.group(1) if m else first.strip()).replace('"', "'")[:60]


def split_text(text: str, budget: int = DEFAULT_BUDGET, keys=None, journal_name: str = JOURNAL_NAME,
               first_id: int = 1) -> tuple[str, list[tuple[int, str, list[str]]]]:
    """Pure. Returns (imported_text, tails). tails = [(id, unit_title, tail_lines)].
    Adds header/pointer/prod-safety only when their markers are absent (prod-safety: also when its
    first line is already there). A file within CHECK_LIMIT and never split comes back as is. Never reads disk
    except to load the keys when `keys` is None. `first_id` = 1 + the journal's highest id."""
    lines = text.split("\n")
    if len(text) <= CHECK_LIMIT and not any(HEADER_RE.match(ln) for ln in lines):
        return text, []  # short enough to import whole: nothing to move, nothing to append (R2-2)
    keys = tuple(keys) if keys is not None else load_keys()
    trailing = len(lines) > 1 and lines[-1] == ""
    if trailing:
        lines = lines[:-1]
    fstart = next((i for i, ln in enumerate(lines) if ln in (POINTER_MARK, PROD_MARK)), len(lines))
    while fstart < len(lines) and fstart > 0 and lines[fstart - 1] == "":
        fstart -= 1
    body, footer = lines[:fstart], lines[fstart:]
    next_id = max(max((int(m.group(1)) for ln in lines if (m := CUT_RE.match(ln))), default=0) + 1, first_id)
    starts = [i for i, ln in enumerate(body) if UNIT_RE.match(ln)]
    tails: list[tuple[int, str, list[str]]] = []
    if not starts:
        out = list(body)
    else:
        out = body[:starts[0]]
        bounds = starts + [len(body)]
        for a, b in zip(bounds, bounds[1:]):
            unit = body[a:b]
            head, tail = _cut(unit, budget)
            if not tail:
                out.extend(unit)
                continue
            blanks: list[str] = []
            while tail and not tail[-1].strip():
                blanks.insert(0, tail.pop())
            k, lifted = _lift(tail, keys, head[-1] if head else "")
            out.extend(head + lifted + [f"<!-- machines-split:cut id={next_id} lifted={k} -->"] + blanks)
            tails.append((next_id, _title(unit[0]), tail))
            next_id += 1
    if not any(HEADER_RE.match(ln) for ln in out + footer):
        out.insert(1 if out and out[0].startswith("# ") else 0,
                   f"<!-- machines-split v1 journal={journal_name} -->")
    out.extend(footer)
    if POINTER_MARK not in out:
        out += ["", POINTER_MARK, POINTER_TEXT]
    if PROD_MARK not in out and norm(PROD_LINES[0]) not in norm("\n".join(out)):
        out += ["", PROD_MARK, *PROD_LINES]
    if trailing:
        out.append("")
    return "\n".join(out), tails


def journal_text(existing: str | None, tails, source_name: str) -> str:
    if existing:
        parts = existing.rstrip("\n").split("\n")
    else:
        parts = [JOURNAL_TITLE, f"<!-- machines-split v1 source={source_name} -->",
                 f"Blocks moved out of `{source_name}` by `scripts/split_machines_file.py`; "
                 "`--undo` puts every one back."]
    for tid, title, tail in tails:
        parts += ["", f'<!-- machines-split:tail id={tid} unit="{title}" -->', *tail,
                  f"<!-- machines-split:end id={tid} -->"]
    return "\n".join(parts) + "\n"


def _drop_block(lines: list[str], marker: str, extra: int) -> None:
    if marker in lines:
        i = lines.index(marker)
        del lines[i:i + 1 + extra]
        if i > 0 and lines[i - 1] == "":
            del lines[i - 1]


def undo_text(imported: str, journal: str) -> tuple[str, str | None]:
    """Pure. Highest cut id first; returns (restored_imported, remaining_journal_or_None)."""
    lines = imported.split("\n")
    trailing = len(lines) > 1 and lines[-1] == ""
    if trailing:
        lines = lines[:-1]
    jl = (journal or "").split("\n")
    while True:
        cuts = [(int(m.group(1)), int(m.group(2)), i) for i, ln in enumerate(lines) if (m := CUT_RE.match(ln))]
        if not cuts:
            break
        cid, k, pos = max(cuts)
        s = next((i for i, ln in enumerate(jl) if (m := TAIL_RE.match(ln)) and int(m.group(1)) == cid), None)
        e = None if s is None else next(
            (i for i in range(s + 1, len(jl)) if (m := END_RE.match(jl[i])) and int(m.group(1)) == cid), None)
        if s is None or e is None:
            raise LookupError(cid)
        lines[pos - k:pos + 1] = jl[s + 1:e]
        del jl[(s - 1 if s > 0 and jl[s - 1] == "" else s):e + 1]
    lines = [ln for ln in lines if not HEADER_RE.match(ln)]
    _drop_block(lines, POINTER_MARK, 1)
    _drop_block(lines, PROD_MARK, len(PROD_LINES))
    if trailing:
        lines.append("")
    rest = None if not any(TAIL_RE.match(ln) for ln in jl) else "\n".join(jl)
    return "\n".join(lines), rest


def _count(t: str, test) -> int:
    return sum(1 for c in t if test(c))


def terms(text: str) -> list[str]:
    """IPv4 literals, hostnames (also wrapped), bare or backticked machine names, 24-26 char ids."""
    found = {ip for ip in _IP_RE.findall(text) if ip not in ("0.0.0.0", "127.0.0.1")}
    found |= set(_HOST_RE.findall(text))
    found |= {t for t in _ID_RE.findall(text) if _count(t, str.isalpha) and _count(t, str.isdigit)}
    found |= {t for t in _NAME_RE.findall(text) if "-" in t and _count(t, str.isalpha) >= 3
              and _count(t, str.isdigit) >= 2 and not _NAME_SKIP_RE.match(t)}
    return sorted(found)


def _terms_json(text: str, source: str) -> str:
    obj = {"schema": 1, "source": source, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "terms": terms(text)}
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def _read(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes().decode("utf-8")  # read_text would hide CRLF (universal newlines)
    return (raw.replace("\r\n", "\n"), True) if "\r\n" in raw else (raw, False)


def _write(path: Path, text: str) -> None:
    """Atomic, UTF-8, LF only (plat.atomic_write would turn LF into CRLF on Windows)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".swap")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        (plat.replace_file if plat else os.replace)(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _git(d: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(d), *args], capture_output=True, text=True, timeout=5,
                              **(plat.no_window_kwargs() if plat else {}))
    except (OSError, subprocess.SubprocessError):
        return None


def _refusal(targets: list[Path]) -> str | None:
    """Fail closed: inside a git work tree every new file must be gitignored."""
    for p in targets:
        d = p.parent if p.parent.is_dir() else p.parent.parent
        r = _git(d, "rev-parse", "--is-inside-work-tree")
        if r is None or r.returncode != 0 or r.stdout.strip() != "true":
            continue
        rel = Path(os.path.relpath(p, d)).as_posix()
        ig = _git(d, "check-ignore", "-q", rel)
        if ig is None or ig.returncode != 0:
            return (f"machines-split: REFUSED — {p.name} is not gitignored in {d} (public repo); "
                    "add the .gitignore line first")
    return None


def _terms_path(path: Path, terms_out: Path | None) -> Path | None:
    if terms_out is not None:
        return terms_out
    return path.parent / "scripts" / TERMS_NAME if (path.parent / "scripts").is_dir() else None


def check(path: Path) -> tuple[int, str]:
    if not path.is_file():
        return 0, f"machines-split: SKIP (no file at {path})"
    text, _ = _read(path)
    n, split = len(text), any(HEADER_RE.match(ln) for ln in text.split("\n"))
    if n > CHECK_LIMIT and not split:
        return 1, f"machines-split: NOT SPLIT ({n} chars > {CHECK_LIMIT}, no marker)"
    msg = f"machines-split: ok ({n} chars, split={'yes' if split else 'no'})"
    return 0, msg + (f" WARN over {CHECK_LIMIT}, run --apply" if split and n > CHECK_LIMIT else "")


def apply(path: Path, *, budget, journal: Path | None, terms_out: Path | None,
          force_unignored: bool, dry: bool, directives: Path | None = None) -> tuple[int, list[str]]:
    if not path.is_file():
        return 0, [f"machines-split: SKIP (no file at {path})"]
    text, crlf = _read(path)
    journal = journal or path.with_name(JOURNAL_NAME)
    existing = _read(journal)[0] if journal.is_file() else None
    used = [int(m.group(1)) for ln in (existing or "").split("\n") if (m := TAIL_RE.match(ln))]
    new, tails = split_text(text, budget, load_keys(directives), journal.name, max(used, default=0) + 1)
    if not tails and new == text and not crlf:
        return 0, [f"machines-split: unchanged ({len(text)} chars)"]
    plan = f"{len(tails)} blocks, {len(text)} -> {len(new)} chars"
    note = "; CRLF normalised to LF" if crlf else ""
    if dry:
        return 0, [f"machines-split: DRY RUN, would move {plan}{note}"]
    tpath = _terms_path(path, terms_out)
    if not force_unignored:
        refused = _refusal([journal] + ([tpath] if tpath else []))
        if refused:
            return 2, [refused]
    jtext = journal_text(existing, tails, path.name) if tails else existing
    tjson = _terms_json(new + "\n" + (jtext or ""), path.name) if tpath else None
    # Side files first, the imported file last: a failed side write leaves the file untouched and
    # nothing is lost. Journal tails the file does not reference yet are ignored by undo_text and
    # the next --apply numbers past them.
    try:
        if tpath:
            _write(tpath, tjson)
        if tails:
            _write(journal, jtext)
        _write(path, new)
    except OSError as exc:
        return 2, [f"machines-split: FAILED {type(exc).__name__} writing "
                   f"{getattr(exc, 'filename', None) or '?'}; {path.name} unchanged"]
    tnote = f"terms {tpath}" if tpath else f"terms skipped (no {path.parent / 'scripts'})"
    return 0, [f"machines-split: moved {plan}; journal {journal.name}; {tnote}{note}"]


def undo(path: Path, journal: Path | None, dry: bool) -> tuple[int, list[str]]:
    if not path.is_file():
        return 0, [f"machines-split: SKIP (no file at {path})"]
    text, _ = _read(path)
    journal = journal or path.with_name(JOURNAL_NAME)
    jtext = _read(journal)[0] if journal.is_file() else ""
    try:
        restored, rest = undo_text(text, jtext)
    except LookupError as exc:
        return 2, [f"machines-split: UNDO REFUSED tail id={exc.args[0]} missing"]
    msg = f"{len(text)} -> {len(restored)} chars; journal {'kept' if rest else 'removed'}"
    if dry:
        return 0, [f"machines-split: DRY RUN, undo would restore {msg}"]
    # file first: until it is restored the journal still holds every tail
    try:
        _write(path, restored)
        if rest is None:
            journal.unlink(missing_ok=True)
        else:
            _write(journal, rest)
    except OSError as exc:
        return 2, [f"machines-split: UNDO FAILED {type(exc).__name__} writing "
                   f"{getattr(exc, 'filename', None) or '?'}"]
    return 0, [f"machines-split: undone, {msg}"]


def write_terms(path: Path, journal: Path | None, terms_out: Path | None, force_unignored: bool,
                dry: bool) -> tuple[int, list[str]]:
    tpath = _terms_path(path, terms_out)
    if tpath is None:
        return 0, [f"machines-split: terms skipped (no {path.parent / 'scripts'})"]
    journal = journal or path.with_name(JOURNAL_NAME)
    text = _read(path)[0] + "\n" + (_read(journal)[0] if journal.is_file() else "")
    if dry:
        return 0, [f"machines-split: DRY RUN, would write {len(terms(text))} terms to {tpath}"]
    if not force_unignored:
        refused = _refusal([tpath])
        if refused:
            return 2, [refused]
    _write(tpath, _terms_json(text, path.name))
    return 0, [f"machines-split: {len(terms(text))} terms -> {tpath}"]


def _default_file() -> Path:
    base = plat.claude_dir() if plat else Path("~/.claude").expanduser()
    return base / MACHINES_NAME


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    act = ap.add_mutually_exclusive_group()
    for flag in ("--apply", "--check", "--undo", "--terms"):
        act.add_argument(flag, action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    ap.add_argument("--journal")
    ap.add_argument("--terms-out")
    ap.add_argument("--directives")
    ap.add_argument("--force-unignored", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        path = Path(a.file).expanduser() if a.file else _default_file()
        if not path.is_file():
            print(f"machines-split: SKIP (no file at {path})")
            return 0
        journal = Path(a.journal).expanduser() if a.journal else None
        terms_out = Path(a.terms_out).expanduser() if a.terms_out else None
        if a.check:
            rc, msg = check(path)
            print(msg)
            return rc
        if a.undo:
            rc, msgs = undo(path, journal, a.dry_run)
        elif a.terms:
            rc, msgs = write_terms(path, journal, terms_out, a.force_unignored, a.dry_run)
        else:
            rc, msgs = apply(path, budget=a.budget, journal=journal, terms_out=terms_out,
                             force_unignored=a.force_unignored, dry=a.dry_run or not a.apply,
                             directives=Path(a.directives) if a.directives else None)
        print("\n".join(msgs))
        return rc
    except Exception as exc:  # noqa: BLE001 — one line, never a traceback in selfheal output
        print(f"machines-split: ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
