<!-- dox:child v1 -->
# `library/` — local rules (dox)
Vendored ECC prose + 19 digests + the generated INDEX.json. Zero always-on tokens: nothing here is auto-loaded.
- Regenerate: `python3 scripts/vendor_library.py --source <ECC> --sha <sha>` then `python3 scripts/build_library_index.py`; CI and selfheal-daily run `--check`.
- Never edit `ecc/**` by hand (the next vendor run overwrites it); digests under `ecc/digests/` are hand-written and survive re-vendoring.
- Public repo: `scripts/validate_imports.py library` must stay clean (no personal paths, machine data, unicode tricks, unpinned npx, secrets).
- Surfaced by `hooks/prompt_router/modules/library_routes.py` (<= 2 `LIBRARY:` lines).
- Parent: [`../CLAUDE.md`](../CLAUDE.md). Children: none.
