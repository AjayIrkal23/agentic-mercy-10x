<!-- ecc:rules/common/coding-style.md, agents/code-simplifier.md @25278e7d -->
# Coding style (ECC graft)

- **Immutability by default:** `const`, readonly types, new objects instead of in-place
  mutation; mutate only where measured performance needs it.
- **KISS / DRY / YAGNI:** the simplest code that passes the tests; extract on the third
  repetition, not the second; no flexibility nobody asked for.
- **File size:** ECC's soft ceiling is 800 lines; the local rule is stricter — 250 lines per
  file, split before you cross it.
- A simplification never changes behavior: tests green before and after.
