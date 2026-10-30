<!-- ecc:skills/change-impact @25278e7d -->
# Pre-change impact (ECC graft)

Before editing a shared symbol, list its impact in four places and keep the list for the
post-change audit:

- **Callers:** every reference (`find_references`, `get_blast_radius`), including dynamic
  and string-keyed lookups.
- **Config:** keys, env vars, feature flags or routes that name it.
- **Docs:** READMEs, dox `CLAUDE.md` files, API docs that describe it.
- **Tests:** tests that pin its current behavior, and the ones that will need to change.

After the change, walk the same list: every entry is updated, still valid, or reported.
