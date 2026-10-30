<!-- ecc:skills/backend-patterns, rules/common/patterns.md @25278e7d -->
# Backend patterns (ECC graft)

Already in this skill set (no change): the response envelope (`api-contract-standards`),
the service layer (`service-layer-standards`), central error handling
(`backend-error-handling`).

Added here:

- **Repository pattern:** data access sits behind a repository per aggregate
  (`userRepo.findById`, `orderRepo.save`); services never build queries inline, so a store
  change touches one module and tests can swap an in-memory repository.
- **One transaction boundary per use case:** the service opens and closes it; repositories
  never commit on their own.
