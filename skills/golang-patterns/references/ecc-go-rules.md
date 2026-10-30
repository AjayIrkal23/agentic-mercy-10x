<!-- ecc:skills/golang-patterns, rules/golang, rules/golang/coding-style.md, rules/golang/hooks.md, rules/golang/patterns.md, rules/golang/security.md, rules/golang/testing.md @25278e7d -->
# Go rules (ECC graft)

- **Errors:** wrap with `%w` (`fmt.Errorf("load user %d: %w", id, err)`); compare with
  `errors.Is` / `errors.As`, never by string. Handle or return every error once.
- **Context:** `ctx context.Context` is the first parameter of anything that does I/O or can
  block; never store a context in a struct; respect cancellation in loops.
- **No package-level mutable state:** pass dependencies explicitly (constructor injection);
  constants and read-only tables are fine.
- **No `init()` side effects:** no I/O, no flag parsing, no registration that depends on order.
- **Tests:** table-driven with named subtests (`t.Run(tc.name, ...)`).
- **The check hook:** `go vet ./...` and `staticcheck ./...` run on every change; a finding
  blocks like a failing test.
- **Security:** parameterised SQL only; `crypto/rand` for secrets; validate input at the
  handler boundary; set timeouts on every `http.Client` and server.
