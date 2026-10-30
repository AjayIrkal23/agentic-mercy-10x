> APPLIED 2026-10 by the integrate package; history only, not instructions.

# Machines-file split (`scripts/split_machines_file.py`)

`CLAUDE.md` §10 imports `~/.claude/CLAUDE.machines.local.md` into every session and every
doctrine-loading subagent. The file had grown into a journal (host history, runbooks,
replica setup detail). The script keeps the imported part short and moves the rest into
`~/.claude/CLAUDE.machines.journal.local.md`, which nothing imports.

## What it keeps, moves and appends

- **Units**: every bullet with a bold name (`- **Name**`, top level or nested two spaces).
  Lines before the first unit stay whole.
- **Keeps** the first ~650 chars of each unit (cut at a line boundary) and lifts back every
  tail line that carries a standing-directive key: the `sentence_key` of each
  `docs/DIRECTIVES.md` row whose source is `machines` (sudo, laptop sleep, full
  performance, no local ollama fallback, read-only prod VM, the prod-safety block).
- **Moves** the full tail of each long unit into the journal (lifted lines included, so
  the journal reads complete).
- **Appends** a pointer line to the journal and a 3-line production-safety block
  (directive 30): no prod edits, cutover or rollback without the user's word in that turn;
  the GCP VM is read-only; servers run IST.

Result on this PC: the imported file drops from about 22,400 to 5,032 chars (budget 650;
it was 5,752 at budget 800, over the plan's 5,200-char row). A smaller budget on an already
split file cuts the kept heads again; `--undo` still restores the original exactly.

## Markers (HTML comments, one per line)

- `<!-- machines-split v1 journal=CLAUDE.machines.journal.local.md -->` (line 2)
- `<!-- machines-split:cut id=N lifted=K -->` where a tail was removed
- `<!-- machines-split:pointer -->` + 1 line, `<!-- machines-split:prod-safety -->` + 3 lines
- journal: `<!-- machines-split:tail id=N unit="..." -->` … `<!-- machines-split:end id=N -->`

The markers make the split idempotent (a second `--apply` prints `unchanged`), let a unit
that grew again get a new cut id, and make `--undo` exact (byte-identical restore).

## Commands

- `--apply` split; no action flag = dry run; `--dry-run` with `--apply` = dry run.
- `--check` exits 1 with `NOT SPLIT` when the file is over 5,200 chars and has no marker;
  over 5,200 with a marker it only warns (`WARN over 5200, run --apply`); selfheal-daily applies it.
- `--undo` puts every tail back; a missing tail block → `UNDO REFUSED`, exit 2.
- `--terms` rewrites only the G7 terms file.
- A missing file prints `SKIP` and exits 0 (CI, a fresh replica).

## Where it runs

On every machine: this PC via the `selfheal-daily` step `machines-split`, the Windows
replica via its own daily self-heal, and `installer/render.py` post-steps on install.
Nothing is hand-copied any more except the file itself.

## Gitignore requirement (fails closed)

Inside a git work tree the journal and the terms file must be gitignored before anything
is written. Otherwise: `machines-split: REFUSED — <name> is not gitignored in <dir>
(public repo); add the .gitignore line first`, exit 2, nothing written. `~/.claude/.gitignore`
needs `/CLAUDE.machines.journal.local.md` and `/scripts/grep_gates.machine_terms.json`.

Write order: the terms file and the journal first, the imported file last. A failed write
prints `machines-split: FAILED <error> writing <path>; <file> unchanged` and exits 2; journal
tails the file does not reference yet are harmless (`--undo` ignores them, the next `--apply`
numbers past them). `--undo` restores the file first, then trims the journal.

## Terms file and G7

`--apply` (when `scripts/` sits beside the file) and `--terms` write
`~/.claude/scripts/grep_gates.machine_terms.json`:
`{"schema": 1, "source", "generated_at", "terms": [...]}`. Terms are IPv4 literals (minus
`0.0.0.0` and `127.0.0.1`), backticked names after the word `hostname` (also when the name
wraps to the next line), bare or backticked machine names (one hyphenated token with at least
3 letters and 2 digits, not a date, version, file name or `-x64-N` package name), and bare or
backticked 24-26 char lowercase ids. No passwords, emails or env var names. Grep gate G7 bans each
term as a literal substring in tracked files; without the file (CI) G7 checks RFC1918
addresses only.
