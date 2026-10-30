<!-- ecc:skills/tdd-workflow, rules/common/testing.md @25278e7d -->
# Test shape (ECC graft)

- **Arrange / Act / Assert:** three visible blocks per test, in that order; no assertions in
  Arrange, no setup in Assert.
- **One assertion focus:** a test checks one behavior; several `expect`s are fine when they
  describe the same outcome.
- **Test name = behavior:** "rejects an expired token", not "test validateToken 2".
- **Red seen before green:** run the new test, watch it fail for the expected reason, then
  write the code. A test never seen red proves nothing.
