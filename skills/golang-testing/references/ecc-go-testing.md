<!-- ecc:skills/golang-testing, commands/go-test.md @25278e7d -->
# Go testing (ECC graft)

- **Table-driven + subtests:** one table per behavior, `t.Run(tc.name, ...)` per row, and
  `t.Parallel()` in both the parent and the subtest when the cases share no state.
- **Fuzz targets for parsers:** any function that parses untrusted input gets a
  `FuzzXxx(f *testing.F)` with seed corpus entries from real bugs.
- **Race detector in CI:** `go test -race ./...` on every CI run (locally when concurrency
  changed).
- **Golden files:** large expected outputs live in `testdata/*.golden`; an `-update` flag
  rewrites them deliberately, never by default.
- Red first: run the new test and see it fail for the right reason before writing the fix.
