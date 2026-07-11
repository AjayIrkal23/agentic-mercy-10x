# Testing patterns

- Red-green-refactor: failing test first, minimal pass, then clean up (see `references/loop.md`).
- Table-driven tests for input/output matrices (Go: see `golang-testing`).
- Test behaviour and contracts, not implementation details.
- One reason to fail per test; clear arrange/act/assert.
- Integration tests for real seams; unit tests for logic; e2e for critical flows.
- Deterministic: no wall-clock/network/order dependence; seed randomness.
