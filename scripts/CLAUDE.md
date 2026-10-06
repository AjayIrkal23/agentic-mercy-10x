<!-- dox:child v1 -->
# `scripts/` — local rules (dox)

> Local doc for this directory only. Update it when you add, remove, or rename a script.

## What lives here

Maintenance CLIs run by hand, by the installer's `post_steps`, or by CI. Not hooks —
nothing here is registered in `dispatch.config.json`.

## Local conventions

- Pure stdlib Python ≥ 3.10; `--check` / `--dry-run` modes exit non-zero on drift and
  never write.
- Skill tooling shares primitives through `skills_lib.py`; do not duplicate front-matter
  parsing or R10 hashing.
- Generators that write tracked files pass `newline="\n"` to `write_text` — on Windows the
  default would write CRLF and dirty every generated file on each run.

## Key files

| File | Role |
|------|------|
| `vendor_skill.py` | vendor third-party skills from `hooks/skills-sources.json` (`<name> [--ref]`, `--all`, `--check`); backs `/invoke-update` |
| `build_provenance.py` | R10 provenance registry → `hooks/skills-provenance.json` |
| `build_skills_index.py` | the one skills-index generator (shim `hooks/build-skills-index.py`); skips skills of plugins the template sets to `false` in `enabledPlugins` (NEW-08) |
| `validate_skills.py` | skill validator R1..R13 (installer post-step; fails the install on a broken catalog); R13 only WARNs on inert lowercase `intents` (C-03) |
| `validate_mods.py` | mods contract M1–M6 for `manifest.mods.enabled`, then `claude plugin validate --strict` + `claude plugin test` (`--static`, `--no-tests`; tests only WARN while Claude Code's rollout switch has mods off); installer post-step `validate-mods`, doctor row `mods` |
| `skills_lib.py` | shared front-matter / trigger-token / hashing primitives |
| `migrate_frontmatter.py` | one-shot native-frontmatter migration (2026-09-27), idempotent |
| `model-mode.py` | per-repo subagent model mode: `opus|sonnet|fable|clear|status`; `show` reads the global flags through `lib/model_mode.global_flags` (the files the guards read) |
| `add-db-mcp.py` | add read-only Supabase/MongoDB MCP to a repo's `.mcp.json` from `templates/mcp/` |
| `mcp_inventory.py` | print the live MCP inventory (user + project scope + plugins) |
| `dox_cleanup.py` | one-shot removal of untouched dox stubs under `~` |
| `grep_gates.py` | portability grep-gates G1–G6 over hooks, installer, scripts and `mods/`; G5 = no bare `read_text()`; G6 = no `/home/<user>/` or `/Users/<user>/` in any git-tracked `*.md` (the repo is public: write `~`). Wrapped by `tests/test_portability_gate.py` |
| `statusline.py` | Claude Code status line (settings `statusLine`, run on every refresh): reads the payload JSON on stdin, prints one line (model+effort │ ctx bar │ $ │ 5h/7d limits │ git │ ⏱ │ ±lines). Git cached 5 s in `$CLAUDE_STATUSLINE_CACHE_DIR` / `$XDG_RUNTIME_DIR` / `$TMPDIR` `$TEMP` `$TMP` when that directory exists, else `tempfile.gettempdir()` (imported only on that path; no `hashlib`: the cache key is crc32+adler32, so the warm path skips OpenSSL start-up); a failed `os.replace` removes its tmp file. Windows: git timeout 1.5 s (0.5 s elsewhere) and a real bound: `Popen` + `communicate(timeout)`, then the whole process tree is killed (`taskkill /T /F`; POSIX: own session + `killpg`), because `subprocess.run(timeout=)` kills only git and then waits for every child holding the stdout pipe (a fsmonitor hook, the `cmd\git.exe` launcher): 3.3 s per refresh became 2.2 s on a 3 s git. `GIT_ARGV` is the module constant tests point at a fake. On a timeout the entry is re-stamped and the last good summary is kept only while < 60 s old, else no git segment. stdin read as `utf-8-sig` (BOM), stdout UTF-8 (`errors="replace"`: a lone surrogate prints `?`) with LF newlines even without `PYTHONUTF8`. Rendered as `{{PYTHON_EXE}} scripts/statusline.py` (direct interpreter, no `py` launcher; hooks keep `{{PYTHON}}`). `NO_COLOR` and `COLUMNS` honoured; never raises (fallback `◆ Claude`). The file stays one module on purpose (a sibling import costs start-up on the 10 s hot path). Tests: `tests/test_statusline.py`, `tests/test_statusline_win.py` |
| `install-graphify.sh` | graphify MCP install helper |
| `github-mcp-launcher.py` | GitHub MCP launcher for Windows (manifest `windows_add`): reads `gh auth token` at launch, runs the server via `cmd /c npx` at the version pinned in the manifest |

## Gotchas / fragile spots

- `add-db-mcp.py` writes project scope only and never literal secrets (`${VAR}` only).
- `model-mode.py` is per repo; the global `state/*-only-mode` flags affect every project.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
