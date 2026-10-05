# /workflow-audit — Phase 0 details (environment, memory, baseline, inventory)

Loaded by `skills/workflow-audit/SKILL.md` section 2. Save every output under
`$AUDIT/raw/`.

### 2.1 Environment facts (save to `$AUDIT/raw/env.txt`)

`date -Is`; `lsb_release -ds`; `uname -r`; `claude --version`; `python3 --version`;
`node --version`; `tsc --version`; `git --version`; `nproc`; `free -h`;
`git -C ~/.claude rev-parse --abbrev-ref HEAD`; `git -C ~/.claude log --oneline -8`;
`git -C ~/.claude status --short`; for `PROJECT`: branch, `git status --short | head`,
and the stack markers present (`package.json`, lockfiles, `tsconfig.json`,
`vite.config.*`, `next.config.*`, `go.mod`, `pyproject.toml`, `requirements*.txt`,
`Cargo.toml`, `docker-compose*.yml`, `Dockerfile`, `Makefile`, `.github/workflows/*`,
`prisma/`, migrations folders), plus the test, lint, typecheck and build commands the
project declares (package.json scripts, Makefile targets).

### 2.2 Memory

1. `mcp__memory__search_nodes("agentic-mercy-10x")` and `search_nodes("<SLUG>")`.
2. Auto-memory: read `~/.claude/projects/-home-<user>/memory/MEMORY.md` and the project's
   own memory folder under `~/.claude/projects/<mangled PROJECT path>/memory/` if it
   exists. List memories relevant to this audit and any that look stale (an "IN
   PROGRESS" item that is done, a path that no longer exists).

### 2.5 Baseline checks (run all from `~/.claude`, save outputs in `$AUDIT/raw/`)

| Check | Command |
|---|---|
| doctor | `python3 installer/doctor.py` |
| tests | `python3 -m pytest hooks/tests tests -q` |
| skills | `python3 scripts/validate_skills.py` |
| mods | `python3 scripts/validate_mods.py` (a "rollout switch has mods off" WARN is not a failure) |
| portability | `python3 scripts/grep_gates.py` |
| trigger floor | `python3 hooks/build-trigger-floor.py --check` |
| generated | `python3 hooks/gen-invoke-skills.py --check`; `python3 hooks/gen-agent-skill-blocks.py --check` |
| render | `python3 installer/render.py --check` |
| vendored | `python3 scripts/vendor_skill.py --check` |
| mod types | `tsc -p mods/mercy` |
| mod contract | `claude plugin validate --strict mods/mercy`; `claude plugin test mods/mercy` |
| link matrix | `python3 hooks/tools/link-doctor.py` |
| MCP | `claude mcp list`; `python3 scripts/mcp_inventory.py` |
| plugins | `claude plugin list --json` (summarize name, version, enabled, what it adds) |

Read the rollout switch read-only:
`python3 -c "import json;print(json.load(open('$HOME/.claude.json'))['cachedGrowthBookFeatures'].get('tengu_plugin_hooks_modules'))"`
and check whether THIS session loaded the mod (are `mcp__mercy__*` tools available?).
Record both; a session that started with the switch off runs without the mod.

### 2.6 Computed inventory (`$AUDIT/inventory.md`)

Count with the command shown, then compare with `README.md` and `docs/`: local skills
(`ls skills/*/SKILL.md`), vendored (`hooks/skills-sources.json`), synced and plugin
skills (`claude plugin list --json` install paths), agents (`agents/*.md` minus
README), hook events registered (`settings.json` → `hooks`), links per event
(`hooks/dispatch.config.json` → `chains`), MCP servers (user, project, plugin;
connected, needs auth, failed), plugins and marketplaces, mods (`installer/manifest.json`
→ `mods.enabled`), rule files, generated files, local `CLAUDE.md` files
(`git -C ~/.claude ls-files '*CLAUDE.md'`). Any drift between computed and documented
numbers is a LOW finding.

Read the maps: `README.md`, `docs/INDEX.md`, the newest `docs/CHANGELOG.md` entry,
`hooks/README.md`, and every local `CLAUDE.md` in `~/.claude`.
