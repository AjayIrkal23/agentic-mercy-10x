# library/ — the ECC reference vault

Vendored prose from Everything Claude Code (ECC), 19 hand-written digests of the ECC parts that were not vendored, and a generated catalogue. It costs zero always-on tokens: the harness loads nothing from here, and the prompt router names an entry only when the prompt or the repo points at it.

## Layout

- `ecc/skills/<name>/SKILL.md` (plus `references/` for the skills that keep them): ECC skills, sanitised and headed.
- `ecc/rules/<lang>/*.md` and `ecc/rules/README.md`: per-language rules packs with their `paths:` frontmatter.
- `ecc/agents/*.md`: agent prompts with the defense block and `model:` line removed.
- `ecc/commands/*.md`: command bodies.
- `ecc/examples/`: example CLAUDE.md files and small sample data (no code).
- `ecc/guides/`: the ECC README (install and marketing sections removed) and the three guides.
- `ecc/docs/troubleshooting.md`: four upstream troubleshooting sources merged under `## Source:` headings.
- `ecc/digests/*.md`: hand-written digests (what it is, the reusable idea, why not adopted, upstream paths).
- `ecc/VENDOR.json`: what to vendor and how (the input of `vendor_library.py`).
- `ecc/UPSTREAM.json`: repo, sha, commit date and per-kind file counts of the last vendor run.
- `ecc/catalogue.json`: command titles and skill trigger phrases that `vendor_library.py` read from the ECC checkout, so the index rebuilds without it.
- `INDEX.json`: the generated catalogue of every entry (id, path, kind, title, triggers, surfaces, stacks, token estimate, conflicts, upstream).

## What the harness loads from here: nothing

There is no `SKILL.md` directly under a top-level `skills/` directory and nothing under the repo-root `rules/` comes from this tree, so neither skills nor rules from `library/` reach the context on their own. Every file here is read only when someone opens it.

## How entries surface

`hooks/prompt_router/modules/library_routes.py` adds at most two `LIBRARY:` lines to the router's ROUTING section:

1. a language stack tag from the repo or the prompt (python, rust, java, kotlin, swift, php, ruby, dart, csharp, fsharp, cpp, perl, angular, vue, nuxt, arkts and their framework aliases) names that rules pack;
2. a review intent plus a stack names the matching `<lang>-reviewer` agent prompt;
3. two or more distinct trigger phrases of one skill, digest or command name that entry.

An entry that carries a conflict marker is never surfaced. Each id surfaces once per session (router manifest). Stacks the workbench's own skills already cover (go, typescript, react, nextjs) never route here.

## How to use an entry

Read the file the line names. For an agent prompt, run a `general-purpose` subagent with the file's body as its prompt; it reviews and reports, it does not edit. For a rules pack, read `coding-style.md` and `patterns.md` first; the other files of the pack are beside them.

## Promotion

Manual and user-approved only. Copy the file into `skills/<name>/SKILL.md` or `rules/<file>.md` (with `paths:` frontmatter), run `scripts/validate_skills.py`, and add it to `hooks/skills-sources.json` only if it should track upstream. The library copy stays where it is.

## Refresh

```
python3 scripts/vendor_library.py --source <ECC checkout> --sha <40-hex sha>
python3 scripts/build_library_index.py --ecc <ECC checkout>
```

The vendor run checks that the checkout is at the given sha, sanitises every file, runs `scripts/validate_imports.py` on the result and swaps it in only when that passes; the digests survive the swap. CI and the daily self-heal run `build_library_index.py --check`.

## Conflict markers

`<!-- ecc-conflict: commit|push|server|shell-write|no-verify|race -->` sits on the line above an upstream line that contradicts a workbench rule (committing or pushing on its own, starting a server, writing files through the shell, skipping hooks, a race-detector build). Follow the workbench rule, not the line.

## Licence

ECC is MIT licensed. Every vendored file starts with `<!-- ecc:<path>@<sha> -->` after its frontmatter. The skills with a different upstream licence carry a second line `<!-- licence: ... (upstream) -->`; eight logistics skills are Apache-2.0, and `osint-investigation` is CC-BY-SA-4.0, so adaptations of it stay CC-BY-SA.

## Six ECC items folded into INDEX.json

`COMMANDS-QUICK-REF.md`, `docs/COMMAND-AGENT-MAP.md`, `docs/COMMAND-REGISTRY.json`, `commands/ecc-guide.md`, `skills/ecc-guide` and `skills/ecc-recipes` were ECC's own catalogues. The generated `INDEX.json` replaces them: `vendor_library.py` stores the COMMAND-REGISTRY descriptions (command titles) and the context-pack trigger phrases in `ecc/catalogue.json`; `build_library_index.py` reads them from there, or straight from the checkout when given `--ecc <checkout>`.
