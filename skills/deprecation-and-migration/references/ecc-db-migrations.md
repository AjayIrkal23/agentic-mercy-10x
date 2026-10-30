<!-- ecc:skills/database-migrations @25278e7d -->
# Database migrations (ECC graft)

- **Expand / contract:** add the new column, table or index first (expand); ship code that
  writes both and reads the new; backfill; switch reads; only then drop the old (contract),
  in a later release.
- **Backfill in batches:** bounded batches by primary key with a pause between them, resumable
  from the last id, never one giant `UPDATE`.
- **Reversible:** every migration has a down step, or a written reason it cannot have one
  plus a backup taken before it runs.
- Per ORM: Prisma `migrate dev` locally and `migrate deploy` in CI; Drizzle `generate` then
  `migrate`; Mongoose has no schema migrations, so write an idempotent backfill script; Go
  (goose / golang-migrate) keeps paired up/down SQL files.
