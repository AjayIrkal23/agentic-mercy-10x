<!-- ecc:commands/update-codemaps.md, scripts/codemaps, scripts/codemaps/generate.ts @25278e7d -->
# Codemaps (ECC graft)

ECC generates "codemaps": per-area summaries of what lives where. Here the same map is two
things that already exist, so no generator was added:

- **the dox tree** — root `CLAUDE.md` index plus a child `CLAUDE.md` per documented
  directory (what lives here, conventions, traps);
- **the jcodemunch repo map** — `get_repo_map` / `get_file_tree` for the symbol-level view.

Updating codemaps = Procedure C of this skill after a change.
