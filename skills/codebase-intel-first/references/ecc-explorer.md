<!-- ecc:agents/code-explorer.md, skills/search-first @25278e7d -->
# Trace first, search the repo before the web (ECC graft)

- **Trace-first:** start from an entry point (route, command, event) and follow the calls
  with the symbol index (`get_call_hierarchy`, `find_references`) until the behavior in
  question is explained; record the path as `file:line` hops.
- **Research-first line:** search the repo before the web. The answer to "how do we do X
  here" is usually an existing module; library questions go to context7; the web is last.
