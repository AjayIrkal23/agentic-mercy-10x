---
name: ecc-digest-integrations-aura
description: ECC's AURA trust-check adapter, an opt-in read-only reputation lookup an agent calls before delegating work or settling a payment with another agent; the reusable idea is an explicit gate at a trust boundary with conservative defaults for unknown counterparties.
---
<!-- ecc-digest:integrations-aura@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# AURA integration

## What it is
`integrations/aura` is a small pure-Python package (an adapter module, an init file, tests, a README and a threat model). It answers one question before an agent delegates work to, or pays, another agent: can this counterparty be trusted? The only network call is one HTTP GET to the AURA service with the counterparty's decentralised identifier; no key, no signing, no wallet access. The caller either wraps an action with a gate function that raises when the verdict is not acceptable, or reads the verdict object directly: a verdict (trusted, caution, high risk, new, unknown), a human-readable reason, a composite score between 0 and 1 (or none when there is no history) and an ok flag. Nothing runs unless the caller imports and calls it: no global hook, no monkey-patching, no background calls. `THREAT_MODEL.md` lists the threats and which ones the caller still owns.

## The reusable idea
Place trust checks as explicit calls at the boundary where value moves, not as ambient middleware. Default to refusal for counterparties with no history ("new" and "unknown" are rejected by the gate unless the caller opts in), expose the score dimensions so policy stays with the caller, and say plainly in the threat model that a reputation score is backward-looking: high-value or irreversible actions still need a forward-looking risk check and human escalation. A threat model table with a "residual risk owned by caller" column is a good habit for any adapter.

## Why not adopted
The workbench does not delegate to third-party agents or settle payments, and the adapter calls an external service. It is kept as a reference for the trust-boundary pattern only.

## Upstream paths
- `integrations`
