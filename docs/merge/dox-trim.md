> APPLIED 2026-10 by the integrate package; history only, not instructions.

# dox trim (package doctrine-tokens; integrate applies)

dox `CLAUDE.md` files load whenever Claude reads in their directory, so a table cell that
grew into a changelog costs tokens on every visit. Cells over 800 chars move to
`docs/CHANGELOG.md` v4.3.0.

## Rule

- The dox cell keeps its first sentence (what the file is) plus
  ``history: `docs/CHANGELOG.md` v4.3.0 § <file>``.
- The rest of the cell moves verbatim under a CHANGELOG heading
  `### dox history moved 2026-10 — <path>` (path = the dox file, then the row's file name).
- Nothing else in the dox files changes; dox still owns them afterwards.

## Cells over 800 chars (measured 2026-10-29 in the merge worktree)

| dox file | line | row (first cell) | cell chars |
|---|---|---|---|
| `hooks/CLAUDE.md` | 46 | `dispatch.py` / `dispatch.config.json` | 1,210 |
| `hooks/CLAUDE.md` | 57 | `hard-completion-gate.py`, `invoke-suite-gate.py` | 968 |
| `hooks/CLAUDE.md` | 62 | `index-lifecycle.py` | 2,534 |
| `hooks/lib/CLAUDE.md` | 32 | `platform.py` (two cells) | 985 and 1,747 |
| `hooks/tools/CLAUDE.md` | 8 | `state-cleanup.py` | 1,285 |
| `hooks/tools/CLAUDE.md` | 9 | `selfheal-daily.py` | 2,215 |
| `mods/CLAUDE.md` | 62 | Autonomy | 1,073 |
| `mods/CLAUDE.md` | 150 | `mercy/tests/*.test.ts(x)` | 876 |
| `scripts/CLAUDE.md` | 36 | `statusline.py` | 1,540 |
| `tests/CLAUDE.md` | 42 | `test_statusline.py`, `test_statusline_win.py` | 820 |
| `tests/CLAUDE.md` | 52 | `test_wintools.py`, `test_wintools_reuse.py`, `test_wintools_deps.py` | 1,451 |
| `tests/CLAUDE.md` | 55 | `test_install_entry.py`, `test_install_entry_run.py`, … | 943 |

Line numbers move as other packages edit these files; re-measure right before applying.

## Re-measure (prints `file:line [cell lengths]`)

```python
import pathlib
for f in sorted(pathlib.Path(".").glob("**/CLAUDE.md")):
    if "node_modules" in f.parts or ".git" in f.parts:
        continue
    for n, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if ln.startswith("|"):
            big = [len(c.strip()) for c in ln.strip("|").split("|") if len(c.strip()) > 800]
            if big:
                print(f"{f}:{n}", big)
```

Run it from the repo root after the trim: it must print nothing.
