<!-- ecc:skills/production-audit, skills/deployment-patterns, scripts/release-approval-gate.js @25278e7d -->
# Release readiness (ECC graft)

## Four readiness lenses

- **Observability:** logs, metrics and an alert for the new path exist before release.
- **Rollback:** the previous version can be restored in minutes; the steps are written down.
- **Data:** migrations are reversible or have a backup; no destructive change ships with code
  that still reads the old shape.
- **Access:** secrets, permissions and feature flags are set per environment.

## Human release-decision gate

The release decision is the user's. Present the four lenses as PASS / GAP with evidence, the
known risks and the rollback steps, then stop and wait for an explicit go.
