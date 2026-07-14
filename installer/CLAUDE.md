# `installer/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename an installer module or change the flow.

## What lives here

The **one-command, UI-only, fully-automatic** installer for the `~/.claude`
workbench. Entry points at the repo root (`install.py`, `install-ui.py`,
`install.sh`, `install.ps1`) all funnel through `bootstrap.py` → the visual UI →
the self-heal loop. There is **no CLI install path** and **no user interaction** —
the user runs one command and everything else (relocate → install → repair →
re-check) happens automatically until the doctor reports 0 FAIL.

## The flow (what runs, in order)

1. **`bootstrap.py`** — auto-detect canonical `~/.claude` (`$CLAUDE_CONFIG_DIR`
   else `~/.claude`). If this clone is elsewhere: `git checkout` the clone to
   pristine committed bytes (fixes Windows autocrlf drift at the *source*),
   merge-copy the bundle into `~/.claude` (overwrite bundle files, **preserve**
   user runtime — projects/, todos/, memory/, state/, settings.user.json; exclude
   `.git`), then **re-launch** from the target (guard env `AGENTIC_MERCY_RELOCATED`
   prevents an infinite loop). Otherwise launch the UI in place.
2. **`ui.py`** — stdlib web server on `127.0.0.1`. Auto-starts the self-heal loop
   on boot (no button); serves `ui.html`; `/api/progress` streams every step,
   `/api/status` is the live preflight grid (from `verify.collect`).
3. **`selfheal.py`** — the loop: install pass (`deps`) once → LF/R10 heal → doctor
   → repair FAILs → repeat until 0 FAIL or `max_rounds`. Success == 0 doctor FAIL.

## Local conventions

- **UI only.** Never re-add CLI verbs (`install`/`update`/`doctor`/`verify`) to
  the entry points — they were removed on purpose. Internal engine modules
  (`doctor`, `deps`, `verify`, `render`) stay importable; only the user-facing
  surface is UI.
- **Never guess line endings.** R10 (`dir_content_hash`) reads raw BYTES and the
  committed baseline legitimately mixes LF and CRLF (e.g. `ui-ux-pro-max/
  scripts/search.py`, `data/motion.csv`). The primary fix is
  `git_restore_worktree` (exact committed bytes); the fallback
  `repair_r10_drift` normalizes CRLF→LF per locked dir and **reverts** if the dir
  hash doesn't then match its baseline — so it can never corrupt a dir.
- **Relocation is merge-overwrite, never delete.** Copy the bundle in; keep every
  extra file the user already has at the target.
- Success is defined as **0 doctor FAIL**. MCP/plugin registration is *attempted*
  automatically (the `platform.run` Windows shell fallback runs the `claude` `.cmd`
  shim), but stays a non-blocking WARN when the `claude` CLI / network is absent —
  it never gates success.

## Key files

| File | Role |
|------|------|
| `bootstrap.py` | auto-detect + relocate (merge, git-restore, re-launch) + launch UI — the single entry |
| `selfheal.py` | install→repair→re-check loop; R10 heal (`git_restore_worktree` / `repair_r10_drift`) |
| `ui.py` / `ui.html` | stdlib visual installer; auto-runs the loop on boot; live progress + status |
| `deps.py` | idempotent deps/MCP/plugins/post-steps from `manifest.json` (post-step script = first `.py` arg — NOT `cmd[1]`; `{PYTHON}`→`py -3` shifts the index on Windows) |
| `doctor.py` | 13-check health verifier (link-doctor, palette, R9/R10, mcp-roster, …); its 0-FAIL is the loop's success gate |
| `verify.py` | read-only workflow status → the UI's live preflight sections |
| `detect.py`, `render.py`, `links.py`, `manifest.json` | env detection · settings.json render (equivalence gate) · skill links · install contract |

## Gotchas / fragile spots

- The doctor header prints `=== ~/.claude doctor ===` but actually checks the dir
  it runs *from* (`_ROOT`). A green run inside a clone folder ≠ installed for
  Claude Code — Claude Code only reads `~/.claude`. Bootstrap's relocate is what
  makes it real.
- `render-equivalence` / `interpreters` read via `read_text` (newline-normalized)
  → CRLF-immune. **Only R10 is byte-sensitive** — that is the sole line-ending
  repair target.
- `git checkout -- .` in `git_restore_worktree` discards worktree edits to restore
  pristine bundle bytes — intended for a fresh clone; user customizations belong
  in overlays/user files, not tracked bundle files.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
- Related: `../hooks/lib/platform.py` (the Windows `.cmd` shell fallback), root
  `install.py` / `install-ui.py` / `install.sh` / `install.ps1` (thin launchers).
