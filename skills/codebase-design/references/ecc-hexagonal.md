<!-- ecc:skills/hexagonal-architecture, agents/type-design-analyzer.md @25278e7d -->
# Ports and adapters, and type scoring (ECC graft)

## Ports and adapters

- The domain core depends on **ports** (interfaces it owns: `UserStore`, `Clock`, `Mailer`).
- **Adapters** implement ports at the edge (Postgres, HTTP, SMTP) and depend inward only.
- Tests drive the core through its ports with in-memory adapters; no framework in the core.

## Type scoring (0–10 each)

- **Precision:** does the type say exactly what is allowed (branded ids, literal unions)?
- **Invariants:** can an invalid value be constructed? (constructors/parsers that refuse it)
- **Narrowness:** does each function accept the narrowest type it needs?

A low score on a type at a module seam is a deepening opportunity.
